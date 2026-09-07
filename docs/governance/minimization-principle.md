# Minimization Principle

This document is the canonical statement of the minimization principle for
LMDJ. It applies equally to human contributors and coding agents, at every
stage of a Task: designing a feature, writing a plan, implementing code,
writing tests, and adding or changing a gate.

"Minimization" names three different rules at three different layers. Each
rule says what gets smaller and, just as importantly, what must never shrink.
Confusing the layers is how "keep it minimal" turns into "make it pass".

| Layer | What is minimized | What must never shrink |
| --- | --- | --- |
| Gates | The set of required checks | Coverage of the invariants those checks defend |
| Tests | The number of reasons a test can fail | The strictness of what the test asserts |
| Changes | The distance from a red gate to its cause | The Task's declared scope |

## 1. Gates: minimize the required check set

A required check exists to keep a specific class of defect out of `main`, not
to run because it can. Every required check must answer one question: *if
this fails, which defect got in?* A check that cannot answer it is not a gate;
it is information, and it runs as a non-blocking advisory instead.

The reason is arithmetic. Every required check adds its false-positive rate
to the Pull Request's. Ten checks that each fail spuriously 5% of the time
send roughly four Pull Requests in ten back for a rerun with no defect
behind it, and people learn to rerun on red. At that point the gate no longer
gates anything.

The correct form of a small gate set is the fewest checks that still cover
every invariant that must hold, not fewer invariants. Concretely:

- A check graduates to a gate only under the admission criteria in
  [`pitfall-ledger.md`](pitfall-ledger.md): the invariant is settled, its
  violation is mechanically decidable, and the check is deterministic.
  Otherwise it exits to skill guidance, not to CI.
- Every gate fails with a message naming both the violated invariant and its
  remedy. A gate whose failure needs a diagnosis round-trip costs more than it
  saves.
- Conservative lane selection is not the opposite of this rule.
  `scripts/ci/scope_policy.json` deliberately over-selects consumer lanes for
  shared code, fixtures, and generated inputs; that over-selection is the
  fail-closed direction and stays. The principle governs *which checks exist
  and are required*, never how cautiously a change selects among them.
- Thresholds are instruments, not gates to tune. Coverage floors, test
  timeouts, and stress budgets measure the tree; a red reading is a finding
  about the code or the measurement. Raise coverage, fix the busy-spin, or
  re-measure under review — never edit the number to go green.
  `docs/quality/core-test-policy.md` owns the floors and the rule that they
  may rise but must not be lowered for a green run.

## 2. Tests: minimize the reasons a test can fail

A test should have exactly one reason to go red, and that reason should be
the defect. Three habits follow:

- **Minimal assertion.** A failure message must point at the broken behavior,
  not at "somewhere in this flow". When a test guards several facts, it is
  several tests, or one test whose per-step assertions each name their step.
- **Minimal fixture.** Set up only what the behavior under test needs.
  Scaffolding that exists to make the test run, rather than to state the
  behavior, is where unrelated changes turn a correct test red.
- **Minimal reproduction before the fix.** Reduce a defect to the smallest
  input that shows it, print both sides of the failing assertion, and write
  the test from that reproduction. A fix written before the cause is verified
  fixes a guess.

Select the lowest tier that reaches the behavior through its public boundary,
as the Test Selection Rule in `docs/quality/core-test-policy.md` requires; a
higher tier is promotion, not padding.

Two cases look like exceptions and are not:

- **Multi-leg acceptance journeys** stay whole. Shortening a journey to the
  last state the implementation already reaches is
  [`acceptance-journey-truncation`](../../.agents/pitfalls/acceptance-journey-truncation.md),
  not minimization. The minimal form of a journey is one observable far-side
  assertion after every specified transition, so that a failure names the leg.
- **Synthetic stand-ins** for platform behavior — a dispatched `blur`, a
  stubbed device, a forced state — must reproduce every side effect of the
  real thing or record the gap beside the test. Omitting a side effect makes
  the test smaller and blind; see
  [`synthetic-event-omits-platform-side-effects`](../../.agents/pitfalls/synthetic-event-omits-platform-side-effects.md).

The anti-pattern to watch for is minimizing the test until it passes: a
`focus()` added to appease jsdom, an assertion loosened to accept the current
output, a leg dropped because it is hard. Minimization targets the test's
complexity; it never targets its strictness.

## 3. Changes: minimize the distance from a red gate to its cause

A gate can only say "this change, taken whole, is wrong". The smaller the
change, the shorter the path from that verdict to the line that caused it.
This is why the workflow in [`git-workflow.md`](git-workflow.md) §3–§4 is
shaped the way it is:

- One Task is one reviewable Conventional Commit. If a Task cannot form one
  reviewable unit, split it along a behavior boundary before implementing,
  not into one large control-plane Pull Request afterwards.
- Stage only the Task's declared files. A stray file in the commit is a
  second variable the reviewer and the gate cannot separate from the first.
- Land a control-plane change — CI workflows, the scope policy, the queue
  controller — as its own Pull Request before the ordinary work that depends
  on it. `.agents/skills/issue-done/SKILL.md` §4 names the paths.
- Authorization boundaries follow the same rule. A commit does not authorize
  push, push does not authorize a Pull Request, and merge does not authorize
  release or deployment (`git-workflow.md` §7). Each boundary caps the blast
  radius of a mistake at the previous state.

In an implementation plan this shows up per Task: the plan names each Task's
declared files, the lowest-tier tests that prove it, and — when a Task adds a
gate — the defect that gate catches. A plan Task that cannot say those three
things is not yet small enough to implement.

## 4. Where each rule applies

| Stage | Gates | Tests | Changes |
| --- | --- | --- | --- |
| Design | Name which invariants are settled enough to gate and which stay as review judgment | Decide which behaviors need a test at which tier | Cut the feature at behavior boundaries that can each ship alone |
| Plan | Any proposed gate states its defect, admission criteria, and failure message | Each Task lists its lowest-tier tests | Each Task lists its declared files; control-plane work is its own Task |
| Implement | Do not add a required check the Task cannot justify | Reduce before fixing; print both sides | Touch declared files only; split when the diff outgrows the Task |
| Test | Keep advisory output advisory | One failure reason per test; journeys keep every leg | Task-specific tests first, full pre-flight second |
| Review | Ask "what defect does this check catch?" of every new required check | Ask "what does this fail for?" of every new test | Ask "why is this file here?" of every staged path |

## 5. What this principle never permits

- lowering a coverage floor, widening a timeout, or raising a stress budget to
  make a run green;
- deleting or skipping a test to make a suite smaller;
- de-selecting a lane a changed path conservatively owns;
- dropping a leg from a specified acceptance journey;
- declaring an impact as `none` to avoid the work it would require;
- bundling unrelated changes because they are "small".

Each of these makes something smaller. None of them is minimization.

## 6. Relationship to existing policy

This document introduces no new gate and changes no threshold. It names a
principle that the following documents already apply in their own domain, so
that a reader can see the three as one rule:

- [`git-workflow.md`](git-workflow.md) §3–§4 and §7 — change and authorization
  minimization;
- `docs/quality/core-test-policy.md` — Test Selection Rule and Coverage
  Thresholds;
- [`pitfall-ledger.md`](pitfall-ledger.md) — gate admission criteria and
  failure-message contract;
- `.agents/skills/issue-done/SKILL.md` §1, §3 and §4 — journey mapping,
  declared-file staging, and the control-plane split.

Where a future document appears to conflict with this one, the conflict is
resolved by asking which of the three layers it is about and what it would
shrink; if the answer is coverage, strictness, or declared scope, the other
document is not applying minimization and must say what it is applying instead.
