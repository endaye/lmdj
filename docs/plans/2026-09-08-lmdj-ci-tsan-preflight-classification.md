# TSan prerequisite failure classification

## Task and declared files

- `.github/workflows/core-nightly.yml`
- `tests/build/ci_nightly_workflow_test.py`
- `docs/plans/2026-09-08-lmdj-ci-tsan-preflight-classification.md`

One classification fix only; no permission, runner, sysctl state, toolchain,
threshold, stress command or runtime/verdict schema change. Relates to #782;
the existing failure bucket and historical verdicts remain unchanged.

## Evidence and cause

Read-only job/log API for bootstrap run 34155431379, job 101850463226:
https://github.com/endaye/lmdj/actions/runs/34155431379/job/101850463226

The TSan prerequisite step failed with `sysctl: permission denied on key
'vm.mmap_rnd_bits'` under `/usr/bin/bash -e`. Toolchain verification, configure,
build and test steps were all skipped. The original unguarded command-substitution
assignment exited before the only infrastructure_failure output (inside bits>28).
The consumer consequently had no host-prerequisite classification flag.

Capture the read's nonzero exit explicitly, write infrastructure_failure=true
before exiting nonzero, and provide why/remedy without changing the host. Reject
empty/nondecimal/oversized values before numeric comparison; they cannot prove
the prerequisite and must not make a failed comparison look like success.
The existing >28 cap remains. Known valid values <=28 still continue normally.

The existing reusable workflow output and observations_from_needs already carry
the flag into scoped verdicts. A failed selected TSan prerequisite becomes
infrastructure_failure with verification_debt=true, no product failures list,
scheduler outcome infrastructure, and a failed batch—not passed evidence.
Do not broaden this to an ERR trap over the build/test steps: actual product
failures must remain product failures. Underlying host read restrictions still
need separate diagnosis; this task does not claim to repair runner execution.

## Verification

Lowest tier: `python3 tests/build/ci_nightly_workflow_test.py` executes the actual
embedded shell under bash -e using a strict exact-argv sysctl stand-in. The red
run reproduced absent classification on nonzero reads and false continuation on
invalid values. Cases cover permission denied, nonzero-with-28-stdout, empty,
malformed, negative, multiple and huge values, entropy 32, and valid 0/27/28.
Each rejection checks nonzero exit, exact output flag, why/remedy, and no far-side
build sentinel. The complete projection journey consumes those actual flag bytes
through the existing reusable output links, observations_from_needs and scoped
verdict, asserting infrastructure debt, empty failures and failed batch status.

Also run all CI contracts, staged ownership, whitespace and pinned actionlint
with only the exact pre-existing queue syntax compatibility exemption. Run
`scripts/architecture-portal.sh check` before commit and record its actual result,
including dependency-related failures; it is not silently counted as passed.
No new required check or reduced testing/coverage budget is introduced.

Precommit portal check was actually run and exited 1: 57 Node tests, 54 passed,
3 failed with missing dependency ERR_MODULE_NOT_FOUND (including `glob`). Later
portal validation/build stages were not reached. This is an explicit unverified
environment dependency boundary, not a portal pass; no dependencies or Portal
sources were changed to hide it. The 13 targeted Nightly tests passed.
All 1,424 CI contracts also passed without skips using pinned actionlint. Direct
workflow lint passed with only the exact existing queue syntax exemption.

The fixture proves output semantics, not live Actions output propagation or a
successful TSan execution on a repaired host. The real job/log evidence identifies
where this failure occurred, not why host policy forbids sysctl. No remote write,
retry, Issue closure, release or deployment is part of this Task.

Pitfall impact: none — existing sanitizer startup and strict fixture guidance
applied. This explicit shell/output classification defect is fully expressed by
the regression; it is not another proven silent sanitizer runtime startup event
or a diagnosis of host hardening. Those existing broader entries remain open.

## Version Management

Version impact: none — workflow classification only, no product version identity.

## Documentation Impact

Documentation impact: none — no Portal pages or projected product facts change.
The plan records classification and outstanding host/O1 boundaries.
