"""Bounded SC experiments for claim admission and cancel/reclaim ownership.

No product imports, real-time clock, weak-memory simulation or target code.
"""

from dataclasses import dataclass, replace

CLAIMED = 8


@dataclass(frozen=True)
class Claim:
    q: int = 1
    closed: bool = False
    audio_pc: int = 0
    audio_expected: int = 0
    audio_failures: int = 0
    control_pc: int = 0
    control_expected: int = 0
    attempts: int = 0


def claim_steps(s, admission):
    if s.audio_pc == 0:
        yield replace(s, closed=True, audio_pc=1)
    elif s.audio_pc == 1:
        yield replace(s, audio_expected=s.q, audio_pc=2)
    elif s.audio_pc == 2:
        # Model a non-spurious CAS implementation of fetch_or. One C++ RMW
        # call may execute this step repeatedly on the target machine.
        if s.q == s.audio_expected:
            yield replace(s, q=s.q | CLAIMED, audio_pc=3)
        else:
            yield replace(s, audio_expected=s.q, audio_failures=s.audio_failures + 1)
    elif s.audio_pc == 3:
        yield replace(s, q=0, audio_pc=4)
    elif s.audio_pc == 4:
        yield replace(s, closed=False, audio_pc=5)

    if s.attempts < 3:
        if s.control_pc == 0:
            if not admission or not s.closed:
                yield replace(s, control_pc=1)
            # A blocked check is a read-only self-loop, omitted from the graph.
        elif s.control_pc == 1:
            yield replace(s, control_expected=s.q, control_pc=2)
        else:
            can_modify = s.q == s.control_expected and not (s.q & CLAIMED)
            # Fresh bounded identities ensure each replacement changes Q;
            # cancellation/reuse safety is checked by the separate model below.
            yield replace(s, q=s.attempts + 2 if can_modify else s.q,
                          control_pc=0, attempts=s.attempts + 1)


def claim_graph(admission, initial_q):
    todo = [Claim(q=initial_q)]
    seen = set(todo)
    maximum = terminals = 0
    while todo:
        s = todo.pop()
        maximum = max(maximum, s.audio_failures)
        following = list(claim_steps(s, admission))
        if not following:
            assert s.audio_pc == 5 and s.attempts == 3, "claim/control deadlock"
            assert not s.closed, "admission not reopened after claim"
            terminals += 1
        for next_state in following:
            if next_state not in seen:
                seen.add(next_state)
                todo.append(next_state)
    assert terminals, "claim model has no completed journey"
    return len(seen), maximum, terminals


@dataclass(frozen=True)
class Cancel:
    # Entry already claimed by audio; local metadata still protects its slot.
    a: int = 1
    generation: int = 0x100000001
    local_generation: int = 0x100000001
    slot: str = "pending"
    audio_owns: bool = True
    audio_pc: int = 0
    control_pc: int = 0
    cancelled: bool = False
    activated: bool = False
    reused: bool = False


def cancel_steps(s, early_reclaim):
    if s.audio_pc == 0:
        # Pause here represents a delayed activation CAS with an old slot token.
        yield replace(s, audio_pc=1)
    elif s.audio_pc == 1:
        assert s.generation == s.local_generation, "audio activation saw a reused generation"
        if s.a == 1:
            yield replace(s, a=1 | CLAIMED, activated=True, audio_pc=2)
        else:
            yield replace(s, audio_pc=2)
    elif s.audio_pc == 2:
        assert s.generation == s.local_generation, "audio finalization touched reused slot"
        # No further payload access after releasing ownership on the cancel path.
        yield replace(s, slot="current" if s.activated else "reclaimable",
                      audio_owns=s.activated, audio_pc=3)
    elif s.audio_pc == 3:
        yield replace(s, a=0, audio_pc=4)

    if s.control_pc == 0:
        # Authority validation snapshots full identity, never just a slot token.
        yield replace(s, control_pc=1)
    elif s.control_pc == 1:
        won = s.a == 1
        yield replace(s, a=0 if won else s.a, cancelled=won, control_pc=2,
                      slot="reclaimable" if won and early_reclaim else s.slot)
    elif s.control_pc == 2:
        if s.slot == "reclaimable":
            assert not s.audio_owns, "control reclaimed an audio-owned slot"
            yield replace(s, slot="empty", control_pc=3)
        else:
            # Reclamation is non-blocking: may find nothing this time.
            yield replace(s, control_pc=3)
    elif s.control_pc == 3:
        if s.slot == "empty":
            yield replace(s, slot="pending", generation=s.generation + 1,
                          reused=True, control_pc=4)
        else:
            yield replace(s, control_pc=4)


def cancel_graph(early_reclaim=False):
    todo = [Cancel()]
    seen = set(todo)
    outcomes = set()
    reuse_seen = False
    while todo:
        s = todo.pop()
        assert not (s.cancelled and s.activated), "cancel and activate both won"
        following = list(cancel_steps(s, early_reclaim))
        if not following:
            assert s.audio_pc == 4 and s.control_pc == 4, "incomplete cancel journey"
            assert s.cancelled != s.activated, "cancel/activate has no unique winner"
            outcomes.add("cancel" if s.cancelled else "activate")
            reuse_seen |= s.reused
            if s.activated:
                assert s.slot == "current" and not s.reused, "current slot reclaimed"
            elif not s.reused:
                assert s.slot == "reclaimable", "cancelled slot never becomes reclaimable"
        for next_state in following:
            if next_state not in seen:
                seen.add(next_state)
                todo.append(next_state)
    assert outcomes == {"cancel", "activate"}, "model omitted one race winner"
    assert reuse_seen, "model omitted post-cancel slot reuse"
    return len(seen)


if __name__ == "__main__":
    for initial_q in (0, 1):
        for enabled in (False, True):
            states, failures, terminals = claim_graph(enabled, initial_q)
            assert failures == (1 if enabled else 3), "claim interference bound changed"
            print(f"PASS: initial Q={initial_q}, admission={enabled}: {states} states, "
                  f"max CAS failures={failures}, {terminals} terminals")
    print(f"PASS: cancel/activate/reclaim: {cancel_graph()} states, both winners and reuse reached")
    try:
        cancel_graph(early_reclaim=True)
    except AssertionError as error:
        assert str(error) == "control reclaimed an audio-owned slot", error
        print(f"PASS: early-reclaim mutant rejected: {error}")
    else:
        raise AssertionError("model accepted deliberately unsafe early reclamation")
