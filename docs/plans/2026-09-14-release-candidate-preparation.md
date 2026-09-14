# Compose owned candidate preparation

2026-09-14: superseded as the next standalone delivery by the
[release convergence plan](/Users/endaye/Projects/lmdj-release-convergence/docs/plans/2026-09-14-release-convergence.md).
Retain this WIP and its unresolved findings; selectively integrate necessary
behavior into the single end-to-end driver. Do not continue growing this parent
as a separate framework or treat its local prefix as complete release acceptance.

Status: implementation in progress on the local dependent stack at
`8c005a906b2cd474f292899d669a5437899a604e`. Upstream owner-adoption hold remains;
no remote business writes, provider, signing, release, deployment or host changes.

## Task

Compose the concrete request-bound source setup, source generator, official
snapshot executor and staged/committed cut Task checks. Persist intent before
each child, authenticate actual child evidence on recovery, and return the real
source/frozen/checked-cut inputs for the existing managed PR/witness transition.
Status observation must not allocate, reinstall, regenerate snapshots or rerun
Task commands. A missing original child enrollment after intent is unknown, not
permission to start over. Partial OLD/NEW source and cut work may resume only
through their existing authenticated recovery entrypoints. Freeze cut timestamp
once after snapshot completion; retain original author and source timestamp.

This closes the local request-to-checked-cut gap, not the service factory, CLI,
remote PR review/squash, complete CI, signing or complete real release acceptance.

## Declared files

- `tools/release/candidate_material.py`
- `tools/release/candidate_workspace.py`
- `tools/release/candidate_snapshot.py`
- `tools/release/candidate_checks.py`
- `tools/release/candidate_cut.py`
- `tools/release/publication_workspace.py`
- `tools/release/candidate_preparation.py`
- `tests/build/release_candidate_preparation_test.py`
- `tests/build/release_candidate_portal_journey.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- this plan

## Verification

Lowest tier: actual temporary Git repositories, provisioned catalogue, generated
source, real snapshot/cut journals and real command executor with explicitly
declared fixture entrypoints. Assert all legs and cold boundaries: setup,
source, snapshot, staged checks, committed checks, final observation. Cover
actual controller death after child success, missing enrollment/history, unknown
commands, drift and final authority loss. A callback return is not command proof.
Preserve every failed iteration, existing cases and timeout bounds.

Run relevant existing material/source/snapshot/cut/check groups and new tests;
run the official opt-in Portal rehearsal through the new parent, current Portal
check, staged ownership/admission and independent complete-diff review. Use the
already installed Command Line Tools Git by its original PATH directory with
Node/Python selections preserved. No system or global configuration changes.

## Version Management

Version impact: none

Reason: orchestration development only; versions and snapshots created during
tests belong exclusively to disposable fixture repositories.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Document the concrete composition and remaining service/real-release gaps.

## Acceptance ledger

Pending implementation, tests, actual rehearsal and review. No acceptance implied.
