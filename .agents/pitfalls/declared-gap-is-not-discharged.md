---
id: declared-gap-is-not-discharged
area: core
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/pull/1001
    observed_by: Claude Code (Opus 5)
exit: none
---

# Writing "no coverage here, and the exposed surface is small" into a plan discharges the paperwork, not the risk; the defect then lands in the gap the document named

## Why

[`acceptance-journey-truncation`](acceptance-journey-truncation.md) ends its
guidance with "if a leg cannot be exercised, record it as an explicit gap".
That is the right remedy for a journey silently cut to fit the implementation.
This entry is the failure mode of that remedy, and it is why the two are
separate: the gap here was not hidden. It was named, argued, reviewed, and
carried in the plan and the Pull Request body — and the defect lived in it
anyway.

#799's byte path added a reserved audition Bank pool to the realtime engine.
Its plan recorded, under "what these checks cannot express":

> Realtime safety of the audition path under contention — *accepted, reduced by
> the ruling.* The unit and component tiers drive the engine single-threaded,
> and this plan adds no `stress` test. Under the dedicated pool the audition
> never enters the pool `snapshot_publication_stress_test.cpp` races, so the
> surface is the audition slots' own state transitions rather than an
> interaction with Project publication — materially smaller than it would have
> been under the carved form.

Every clause of that is true. The conclusion drawn from it was wrong. A
use-after-free lived in exactly those "audition slots' own state transitions":
publication swapped the live slot and retired the outgoing Bank on the control
thread, so `retire_audition` could observe `active_voices == 0` while a voice
was between reading the Bank and counting itself against it, and the sweep
freed a `std::vector` that voice was still reading. `active_voices` was also
read across threads, a data race in its own right.

Three properties made the honest declaration actively harmful rather than
merely insufficient:

- **A named gap reads as a managed one.** "Recorded as an explicit acceptance
  gap" is the vocabulary of a decision, and a reviewer skimming for unmanaged
  risk finds none. The sentence that should have read as an alarm read as
  diligence.
- **The argument was about size, and the defect was about kind.** "Small
  surface" bounds how *much* can go wrong, not how *badly*. A two-slot state
  machine is a small surface that can still contain UB, and the ranking that
  matters for a realtime path is severity, not area.
- **The substitute evidence could not see it.** Single-threaded unit and
  component tests were offered in place of the stress test, and they passed —
  as did the plain-build stress test once written. Only TSan reported it. Green
  substitute coverage is what makes a declared gap feel discharged.

Found by review, not by the suite. Confirmed by building the pre-fix code under
ThreadSanitizer: `data race realtime_engine.cpp:312 in
RealtimeEngine::retire_audition`, reached from the control thread. The same
binary passes three runs out of three without a sanitizer, because a freed read
that stays mapped returns plausible bytes.

## How to apply

- **"The exposed surface is small" is an argument for a cheaper test, never for
  no test.** If the surface is genuinely small, the test is genuinely small —
  that is the same sentence read the other way, and it is the one to act on.
- When declaring a gap, write what would *close* it and what it would cost, not
  only what is missing. A gap whose closing cost is unstated is one nobody can
  weigh; the audition case cost one test function racing a rendering thread.
- Rank a declared gap by severity, not area. Anything touching lock-free or
  realtime state is UB-class: it cannot be discharged by argument, because the
  failure mode is unbounded and silent. Coverage there is a floor, not a
  judgement call.
- Do not let passing substitute coverage close the question. Ask which
  instrument would report the defect you are declining to test for. If the
  answer is "one this suite does not run" — a sanitizer, a browser, a real
  device — the gap is open regardless of how much green sits beside it.
- Where the class is UB, run the instrument before declaring anything. For this
  repository that is `scripts/core.sh test dev stress` plus a `tsan`
  configuration; neither is in `test dev full`, so neither runs unless asked.
  See `.agents/pitfalls/stress-tier-in-coverage-preset.md` for the related trap
  of a stress test that exists but is excluded from the preset that would run
  it.
- A test written for a race must prove its race fired. Assert that both
  outcomes actually occurred — in the audition case, that publications were
  both accepted and refused — because a concurrency test whose contention never
  materialises asserts nothing and reports green.

`exit: none` at recurrence 1. The judgement this entry governs — whether a
declared gap is acceptable — is not mechanically decidable, so it fails the
gate admission criteria and cannot become a check. The nearest mechanical
sibling that *is* decidable, "a new lock-free path must carry stress-tier
coverage", would need a definition of "lock-free path" that the tree does not
currently express. Until then this exits to review judgement, and to the
`issue-done` minimization step that already asks whether any coverage was
reduced to make a run green.
