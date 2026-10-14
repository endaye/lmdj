# Test ownership and coverage budget follow-ups (round 3)

Status: in execution. Owner approved all three Tasks on 2026-10-14.

## Outcome and authority

[The follow-up plan](2026-10-14-script-hygiene-followups.md) closed F1–F11 and
surfaced three remaining items. The owner asked on 2026-10-14 to combine them
into one plan and execute it. Each Task is one reviewable Conventional Commit
shipped through `issue-done` under the standing Task authorization.

Goal: the coverage lane no longer depends on a component test finishing inside
its last 10% of budget, the budget report sees every registration, and no
tracked Python test file can exist without a lane that runs it.

## Facts this plan relies on

Recorded at `origin/main` `92534e17a9e1ec292c33ac991d52c24431458021`.
Every Task re-runs `issue-done` §0 at its own base before editing.

- #2238: on netcup (clang/llvm-cov 22.1.8) `facade.pattern_count_in` used
  89–91% of its 30 s component budget on every coverage run, and
  `facade.pattern_transport_controller` once exceeded it (normally ~47%).
- #2238: `tests/quality/test_budget_report.py` parses registrations with
  `lmdj_add_test\((?P<body>.*?)\n\s*\)`, which needs the closing parenthesis on
  its own line, so 45 registrations are invisible to the warning list.
- `tests/platform/web/audio/count_in_observer_server_test.py` (added by #2202)
  is run by no lane command, script or workflow.
- Ownership guards exist only per directory: `apps/*/test` (#2183) and
  `tests/quality` (#2221). Tracked Python tests live in about twenty
  directories (`tests/build`, `tests/host`, `tests/conformance`, `tests/e2e`,
  `tests/platform/web/*`, `tools/*/tests`, `demos/*/test`, `packages/*/test`
  and others).

## G1 — Coverage component budget headroom (#2238)

1. Fix the budget report parser so every `lmdj_add_test` registration is seen
   regardless of where its closing parenthesis sits; add a test with both
   layouts and prove the 45 registrations now appear.
2. Reduce `facade.pattern_count_in`'s wall time under coverage without
   weakening it: split it into focused tests (one fact each) or remove
   avoidable waiting in its fixture. Every assertion keeps a far-side check.
3. Investigate `facade.pattern_transport_controller`'s single timeout: rerun
   it repeatedly under coverage on netcup and decide between host contention
   and an intermittent slow path; fix a real slow path, otherwise record the
   evidence on #2238.
4. Never widen a timeout, raise a multiplier or drop an assertion to make a
   run green (minimization principle). Prove the result with a full
   `core_coverage` lane run on netcup.

Pitfall: bump `facade-surface-test-budget-headroom` if this is a recurrence.

## G2 — Every tracked Python test is run by some lane

1. Wire `tests/platform/web/audio/count_in_observer_server_test.py` into the
   lane that owns `tests/platform/web/audio` and the code it tests.
2. Replace the per-directory guards with one repository-wide guard: every
   tracked `*_test.py` and unittest `test_*.py` must be named or discovered by
   a lane command that appears in that lane's workflow job, on a lane its
   route selects. Keep an explicit, reasoned allowlist for files that are
   helpers rather than tests, and fail on any new unowned file with a
   why/remedy message. Include red cases.
3. Wire or explicitly dispose of any other orphan the guard finds; report
   orphans whose correct lane is not clear instead of guessing.

## G3 — Record F11's Pull Request number

The follow-up plan's F11 line now names #2221 (`3545b745c`). Delivered with
this plan.

## Order

G1 and G2 are independent and run in parallel. G3 ships with this plan.

## Version Management

Version impact: none. Test tooling, tests, CI routing and plan documents only;
no Module, Host, Provider, Contract or Product Build identity changes.

## Documentation Impact

Documentation impact: none. Reason: `docs/plans` is not projected by the
portal. G1 and G2 check `/operations/testing-and-proof` and declare their own
impact.

## Pitfall Impact

G1 may bump `facade-surface-test-budget-headroom`; G2 may bump
`unregistered-test-file-reads-as-coverage`.
