# Restore Cardputer feedback test registration

## Scope

Declared files:

- `tests/platform/cardputer/CMakeLists.txt`
- `docs/plans/2026-09-13-cardputer-feedback-test-registration.md`

Release automation's test registration verification exposed a baseline CMake
error: `platform.cardputer.input.feedback_interleaving` is registered twice.
The first registration invokes the actual dedicated Facade-boundary executable.
The second comes from the input-controller scenario loop, but that executable
has no `feedback_interleaving` case and returns 2 for it. Remove only this
nonexistent scenario registration. Keep the real interleaving executable,
its exact existing test identity/tier, and all eleven real input scenarios.
No product code, assertion, tier, timeout or required journey is changed.

## Verification

Retain the original failed `configure dev` log at
`/tmp/lmdj-dispatch-receipt-configure.log` (exit 1). Verify the original base
file has both registrations and the input controller has no matching case.
After the fix run `scripts/core.sh configure dev`, build both input and
interleaving executables, inspect the CTest command inventory, and execute
all `platform.cardputer.input.*` cases. The required far-side observation is
exactly one interleaving test using the dedicated executable, plus all eleven
real input scenarios; all twelve must execute and pass. Also run the newly
registered release dispatch test through CTest to establish its discovery.
Run staged ownership and whitespace checks before the atomic commit.

## Version Management

Version impact: none

Reason: removes an invalid duplicate test registration; product contents and
all real test behavior remain unchanged.

## Documentation Impact

Documentation impact: none

Reason: CTest registration repair only; no Portal page, diagram, manifest,
projected identity or documented product fact changes.

## Results

`configure dev` exit 0; both named executables built with exit 0. CTest
executed 13/13 passing tests: the twelve Cardputer cases plus
`build.release_dispatch_receipt` (its twelve internal assertions/tests).
The post-build JSON CTest inventory was independently checked for exactly
one dedicated interleaving executable with no scenario argument and all
eleven precise input-controller commands. Invoking the latter executable
with the removed nonexistent scenario returned 2, confirming that renaming
that duplicate registration would not have repaired it.

Raw evidence:
`/tmp/lmdj-cardputer-registration-{configure,build,ctest,scope}.log` and
`/tmp/lmdj-cardputer-registration-inventory-built.json`.
Staged ownership 74/74, exit 0. No full Core, stress, hardware, release or
deployment acceptance is claimed. Independent source review confirmed no
real test coverage was removed. Pitfall disposition: no new entry; CMake's
existing duplicate-name failure and actual CTest command/execution evidence
cover this registration defect without adding another required gate.
