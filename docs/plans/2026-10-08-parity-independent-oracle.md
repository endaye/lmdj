# Independent oracles for parity verification

## Task and declared files

Deliver the skill mechanism requested by #1787. Shared omissions and shared
implementation defects can satisfy a parity comparison, so the shipping flow
must require an independent assertion and a discriminating proof before calling
that invariant verified.

- `.agents/skills/issue-done/SKILL.md`
- `.agents/pitfalls/parity-check-between-agreeing-copies.md`
- `docs/plans/2026-10-08-parity-independent-oracle.md`

No product source, acceptance boundary, numerical threshold, lane, test budget,
release state or version identity changes. The concurrent #1878 Task owns the
CI-triage skill and macOS Git-overhead pitfall; its files are separate.

## Mechanism

Add a co-located shipping section triggered when a Task adds, changes or relies
on a parity/agreement test. Its completion requires the shared blind spot in a
test comment, a separate assertion against an independent oracle, and retained
proof that the assertion rejects the shared defect while the parity comparison
still agrees. Reuse §1's fresh-artifact procedure. Keep an unavailable oracle or
unexecuted proof visible as incomplete verification within the declared scope.

Mark the existing pitfall absorbed with a skill exit. Preserve both historical
recurrences without appending this administrative absorption as a new incident.
Condense its application guidance to the authoritative skill pointer.

## Three-case walkthrough

Review these existing cases against the steps; this is a review of the mechanism,
not a claim that their historical binaries or new product tests were run here.

| Shared defect | Independent oracle and existing assertion | Discriminating case |
| --- | --- | --- |
| Both Web transport inventories omit `soundset.audition` (#799) | Producer `control_runtime` Sound Set inventory must be a subset of each consumer; `check_served_operations_are_reachable` in `packages/web-runtime-platform/test/source_boundary_test.py` | Remove the operation from both consumers while retaining it in the producer: consumer parity agrees, producer assertion names the unreachable operation. Non-table branches remain an explicit gap. |
| Both realtime/offline paths cut a ringing filtered voice (#1780) | Absolute output end bound and exact zero in `a_released_filtered_voice_ends_without_a_step`, `tests/core/audio/realtime_engine_test.cpp` | Shared kernel without the output declick can agree on the step; the independent last-frame bound rejects it. |
| Both paths swell after release during attack (#1780) | Closed-form attack-level-scaled release samples in `a_release_during_a_user_attack_fades_from_the_attack_level`, the same realtime test file | Shared release behavior can agree at the wrong scale; the independent frame-by-frame formula rejects the rise. |

The walkthrough must identify the authority, blind spot and discriminating
assertion in each case; independent review checks these mappings before merge.

## Verification

Run existing `ci_issue_done_skill_test.py` and `ci_pitfall_ledger_test.py` for the
skill/ledger contracts. Stage the three files, run `ci_change_scope_test.py` for
new-plan ownership, and inspect the staged diff/whitespace. No mirror text test
is added: whether an oracle is independent requires review judgment. Classify
the committed range, validate the PR body and satisfy any actual batch-only
obligation. Independent current-head review and conversation checks still apply.

## Version Management

Version impact: none
Reason: Agent verification guidance changes no Product, Module, Host, Provider,
Contract or Channel identity and allocates no Product Build.

## Documentation Impact

Documentation impact: none
Reason: This agent shipping procedure changes no Portal page, product behavior,
public API, projected identity or documented product operating procedure.

## Pitfall Impact

Pitfall impact: recurrence parity-check-between-agreeing-copies
Reason: Absorb the existing recurrence-2 escalation into the shipping skill;
retain the two recorded incidents and add no occurrence for this absorption.
