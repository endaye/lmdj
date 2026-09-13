# Generate candidate build materials from the durable reservation

Delivery base: `423b4b2c5b0ec4c0403335fa03c7ec4f8e002d17`.
Reapply Task `0289895c1dde149e44b5a21758db3989c1efe73a`, preserving the
newer passive Git reader, bounded journal writer and persistent request aliases.

## Task and files

Connect actual CandidateReservations to passive exact-Git input export and
the canonical scripts/version.py Assembly generators. Return the four build
files and complete path/length/digest binding. Keep rendering side-effect free
for the source tree; the reservation is durable before rendering starts.

Declared files:

- scripts/version.py
- tools/release/candidate_material.py
- tests/build/release_candidate_material_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-candidate-build-material.md

The version tool accepts an explicit passive root in its shared generator and
verification internals; existing callers keep their original default root.
Do not change a global module root or import/execute code from the candidate.
Export Product files, Provider sources, Contracts and all direct Core/Host
module manifests from verified Git blobs. Core/Host implementation bytes stay
frozen by CandidateInputs even though the lock generator does not consume them.
Reject links/Gitlinks in generator inputs. Bound the selected blob inventory,
verify batch framing and actual Git object byte hashes before materialization.
Validate original version/Assembly/lock/compiled source before generating new
material. Preserve component identities and product line, use the verified new
BUILD with PATCH zero. A refused generator leaves its reservation consumed.

Remaining candidate obligations: authenticated parent/main/baseline-CI binding,
canonical service enrollment, durable installation/commit of the materials,
official Portal snapshot, reviewed cut PR, guarded squash, official witness PR
and actual post-squash target proof. No real Product Build is allocated here;
no source files, Git index/refs, remote PR, release, signer or Site are mutated.

## Verification

Real Git export + actual reservation + canonical generator integration. Verify
the exact four material files with the existing lock/compiled verifier after
installing them only in a temporary fixture. Check full digest/length bindings,
unchanged source/index/refs, deterministic restart, dirty/untracked isolation,
wrong input Assembly/compiled rejection with reservation retention, passive
source roots owning hashes, arbitrary line/PATCH refusal and corrupted blob
bytes. Run existing version and conformance lock tests unchanged, registered
candidate suites, staged ownership and Portal check. No added full-PR gate.

Original-stack results remain historical, not current-head acceptance.
Current delivery evidence:

- Direct `python3 tests/build/release_candidate_material_test.py`: 11/11,
  25.676s, exit 0; `/tmp/lmdj-candidate-material-delivery-tests-v1.log`.
- Existing `python3 tests/build/version_test.py` and
  `python3 tests/conformance/version_lock_test.py` ran unchanged, both exit 0
  with their respective PASS markers (script assertions, not unittest counts).
  Logs: `/tmp/lmdj-candidate-material-delivery-version-v1.log` and
  `/tmp/lmdj-candidate-material-delivery-lock-v1.log`.
- Independent reviewer `/root/release_journal_review` inspected all six files
  and the actual generator/reservation/export path, with no actionable finding.
  Independently executed the materialized-path capacity test: 1/1, 1.462s,
  exit 0; diff check passed. This local review is not owner adoption or remote
  PR merge eligibility.
- Registered CTest selection
  `^(build\.release_(candidate_material|candidate|candidate_inputs)|build\.version|conformance\.version_lock)$`:
  5/5, 76.10s, exit 0. Actual child populations: material 11, reservation 20,
  input 16, plus unchanged version / lock scripts with PASS markers. No skips;
  original test budgets preserved. CTest completed before the Portal build.
  Log: `/tmp/lmdj-candidate-material-delivery-ctest-v1.log`; actual child
  output: `build/core/dev/Testing/Temporary/LastTest.log` in this worktree.
- Staged ownership/admission after all six declared files were staged: 74/74,
  6.545s, exit 0; `/tmp/lmdj-candidate-material-delivery-scope-v1.log`.
- Node 22 locked dependencies and `scripts/docs-site.sh check`: 144/144 tests,
  zero skips, 47 pages and built routes, exit 0:
  `/tmp/lmdj-candidate-material-delivery-docs-v1.log`. An explicit read of
  generated `apps/docs-site/build/operations/version-and-release/index.html`
  confirmed the material producer, byte identity and remaining cut obligations
  are present; exit 0, `/tmp/lmdj-candidate-material-delivery-rendered-v1.log`.
  This proves local rendering, not live publication or an immutable snapshot.

No real Product Build allocation, release, signing, deployment or remote CI
dispatch is performed. Pitfall disposition: source regressions express the
passive-input, generator and capacity invariants; no new process-only ledger
rule is claimed. All six declared source/doc files belong to this Task; actual
Product files remain unchanged outside temporary fixtures.

## Version Management

Version impact: none

Reason: generator implementation only; material generation tests use temporary
fixtures, not a real Product Build allocation or Assembly modification.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
