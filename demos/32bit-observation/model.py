"""Finite SC exploration, not a C++ weak-memory or target instruction model."""

from dataclasses import dataclass, replace

PUBLICATIONS = 3  # Third write can reuse a slot lent back too early by the mutant.

@dataclass(frozen=True)
class State:
    slots: tuple = ((0, 0), (0, 0), (0, 0))
    writer: int = 0
    reader: int = 1
    middle: int = 2
    dirty: bool = False
    write_number: int = 1
    write_pc: int = 0
    write_return: int = -1
    reads: int = 0
    read_pc: int = 0
    read_return: int = -1
    high: int = -1
    low: int = -1
    previous: int = 0


def successors(s, release_early=False):
    # Publisher: high write, low write, exchange, private-index assignment.
    if s.write_number <= PUBLICATIONS:
        if s.write_pc < 2:
            slots = [list(pair) for pair in s.slots]
            slots[s.writer][s.write_pc] = s.write_number
            yield replace(s, slots=tuple(map(tuple, slots)), write_pc=s.write_pc + 1)
        elif s.write_pc == 2:
            yield replace(s, middle=s.writer, dirty=True, write_return=s.middle, write_pc=3)
        else:
            yield replace(s, writer=s.write_return, write_number=s.write_number + 1, write_pc=0)
    # Two calls by one logical reader; an external mutex serializes API readers.
    if s.reads < 2:
        if s.read_pc == 0:
            yield replace(s, read_pc=1 if s.dirty else 3)
        elif s.read_pc == 1:
            # Negative control lends the newly acquired slot back before copying.
            yield replace(s, middle=s.middle if release_early else s.reader,
                          dirty=False, read_return=s.middle, read_pc=2)
        elif s.read_pc == 2:
            yield replace(s, reader=s.read_return, read_pc=3)
        elif s.read_pc == 3:
            yield replace(s, high=s.slots[s.reader][0], read_pc=4)
        elif s.read_pc == 4:
            yield replace(s, low=s.slots[s.reader][1], read_pc=5)
        else:
            assert s.high == s.low, f"torn snapshot: {s}"
            assert s.previous <= s.high <= PUBLICATIONS, f"regressed/unpublished snapshot: {s}"
            yield replace(s, reads=s.reads + 1, read_pc=0, previous=s.high)


def explore(release_early=False):
    pending = [State()]
    seen = set(pending)
    edges = terminals = 0
    while pending:
        s = pending.pop()
        following = list(successors(s, release_early))
        if not following:
            terminals += 1
            # Both actors quiescent, then a synchronized final read. No further
            # writer action is permitted to repair a missed last publication.
            latest = s.middle if s.dirty else s.reader
            assert s.slots[latest] == (PUBLICATIONS, PUBLICATIONS), f"lost final publication: {s}"
        for next_state in following:
            edges += 1
            if next_state not in seen:
                seen.add(next_state)
                pending.append(next_state)
    assert terminals > 0, "model never completed a journey"
    return len(seen), edges, terminals


def sequence_wrap_counterexample():
    # Two-bit even sequence wraps after two complete publications. Atomic halves
    # avoid UB but do not stop this SC reader accepting an unpublished pair.
    sequence, high, low = 0, 0, 3
    before, observed_high = sequence, high
    published = {(high, low)}
    for high, low in ((1, 0), (2, 1)):
        sequence = (sequence + 2) % 4
        published.add((high, low))
    observed = (observed_high, low)
    assert before == sequence and sequence % 2 == 0
    assert observed not in published, "wrap counterexample ceased to detect tearing"


if __name__ == "__main__":
    sequence_wrap_counterexample()
    print("PASS: finite-sequence wrap accepts an unpublished pair (negative example)")
    states, edges, terminals = explore()
    print(f"PASS: triple buffer SC model: {states} states, {edges} edges, {terminals} terminals")
    try:
        explore(release_early=True)
    except AssertionError as error:
        print(f"PASS: early-slot-release mutant rejected: {str(error).split(':')[0]}")
    else:
        raise AssertionError("model failed to detect deliberately broken slot ownership")
