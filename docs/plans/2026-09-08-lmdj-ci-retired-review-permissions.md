# T4c — Retire Core CI Review Permissions

Status: product-execution permission prerequisite only. No automatic trigger,
candidate evidence protocol, runner budget, test inventory or protection change.

## Declared Files

- `.github/workflows/ci.yml`
- `tests/build/ci_claude_review_workflow_test.py`
- `tests/build/ci_grok_review_workflow_test.py`
- `tests/build/ci_workflow_topology_test.py`
- `tests/build/ci_phase_gate_test.py`
- `tests/build/ci_runner_fallback_test.py`
- `tests/build/ci_self_test_workflow_test.py`
- `tests/build/ci_advisory_review_liveness_test.py` (retired signature assertion only)
- This plan.

## Change and Compatibility

Remove the retired selector, Claude and Grok jobs from Core CI. Its only live
entries remain the existing scheduled and manual product self-tests; review is
already owned by `pr-review.yml`. Remove the pre-heavy gate's reviewer ordering
and review-thread API query, retaining the actual product preflight judge and
its exact eight result inputs. Core CI requests only contents/actions read.
Reusable workflow permission compatibility must not rely on a skipped job's
permissions being ignored, and the caller must not gain write scopes merely
to accommodate a retired callee job.

All sixteen product suites, fixed-target complete/manual evidence, self-test
verdict, resource locks, timeouts, stress repetitions and coverage floors stay
unchanged. The historical thread validator and Grok script behavior tests stay;
only obsolete workflow assertions migrate to the active independent reviewer.
Claude runtime trust, exact action pins, explicit token, read-only tools and
vendored-command provenance remain asserted. Grok runtime pin/tool isolation
and script behavior remain asserted. Missing review stays visible rather than
restoring the retired continue-on-error-as-success contract.

T2b owns `pr-review.yml`, its workflow tests and liveness collector. Its runtime
pin checks no longer require the retired Core CI copy. Final verification
uses the merged T2b prerequisite. This Task additionally migrates only the old
liveness signature test from the removed Core CI prompt to the trusted publisher;
the historical liveness collector and its behavioral tests remain intact.

## Verification

Lowest tier: Python workflow/contract tests. Two new topology regressions were
observed red on the original Core CI: retired jobs were present and PR/issue
permission declarations exceeded product execution needs.

- Run complete `ci_*_test.py` discovery after the T2b prerequisite is present.
- Run the supported pinned actionlint on workflows; retain only the existing
  queue-key compatibility exemption, not any permission or syntax exemption.
- Stage only the declared files, run ownership (`ci_change_scope_test.py`) and
  `git diff --cached --check`, inspect the full staged diff and commit contents.
- Compare before/after product job blocks to prove only the retired jobs and
  review-only pre-heavy wiring changed; all complete suites remain present.

No new workflow_call path is enabled here. Actual reusable-call permission
validation and platform execution remain T4 integration/O1 evidence, not a local
lint claim. No remote write is performed by this Task's implementation agent.

Final local baseline: merged T2b at `0bcb14e9ada890f4c0e6b549f72dcdce05cf9c1c`.
Complete CI Python discovery passed 1122 tests (one existing skip). Pinned
actionlint 1.7.12 passed with only the existing queue-key exemption. The liveness
signature regression now exercises the actual trusted publisher with injected
API fixtures and an in-memory writer, asserting both review and inline markers;
this is not evidence of a remote publication.

## Documentation Impact

Documentation impact: none — removal of unreachable review copies does not
change current product-test triggers, Portal behavior or projected identities.

## Version Management

Version impact: none — CI permission cleanup allocates no Product Build or
product/module/host/provider/Contract identity and performs no release action.

Pitfall impact: none — existing permission, fake-platform and gate-diagnostic
guidance applied; no platform permission failure is claimed from local tests.
