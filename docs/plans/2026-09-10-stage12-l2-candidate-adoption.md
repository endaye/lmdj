# Stage 12 L2 — atomic Candidate adoption

Authority: #1039 and approved R2 in the Stage 12 Contract/Candidate decision.
Baseline: fresh main with L3 PR #1126. Local implementation only; coordinator
owns version closure, final integration verification and shipment.

## Command and invariants

`candidate.adopt` takes exactly operation, project_path, project_id,
expected_revision, command_id, job_id, set_id, selections. Each selection takes
exactly candidate_id, bank, pad. The nonempty list belongs to one active set;
sort Bank/Pad, reject duplicate or invalid targets and unknown recipes before
materialization. Same recipe on different Pads creates distinct deterministic
Asset IDs and incurs separate prepared charges. This is a new explicit command,
not a Sound Set install or an idempotent public replay API.

Hold Workspace eligibility through preflight and commit. Compare Project ID,
current expected revision and source Asset/full ArtifactRef before materializing
and again under the Project writer. Preserve analysis revision in lineage.
Materialize bounded PCM16 mono/stereo 44.1/48 kHz intervals through Cooker;
replace all target charges in the final-binding quota ledger. Persist one v5
revision with complete terminal-authoritative lineage and retain source bytes.
No CandidateIndex adopted write. Distinct persisted adoption identity participates
in staged blob rollback, recovery and identity validation.

## Declared files

- This plan.
- packages/authoring-domain/include/lmdj/domain/commands.hpp
- packages/authoring-domain/src/command_handler.cpp
- packages/project-io/include/lmdj/project_io/project_store.hpp
- packages/project-io/src/project_store.cpp
- packages/project-cooker/include/lmdj/cooker/wav_selection.hpp
- packages/project-cooker/src/wav_selection.cpp
- packages/application-facade/internal/lmdj/facade/candidate_store.hpp
- packages/application-facade/src/candidate_store.cpp
- packages/application-facade/src/application.cpp
- packages/authoring-domain/CMakeLists.txt
- packages/project-io/CMakeLists.txt
- packages/application-facade/CMakeLists.txt
- products/lmdj/CMakeLists.txt (test linkage only)
- tests/core/cooker/wav_selection_test.cpp
- tests/core/support/candidate_adoption.hpp
- tests/core/domain/candidate_adoption_test.cpp
- tests/core/project_io/candidate_adoption_test.cpp
- tests/core/facade/candidate_adoption_test.cpp
- tests/core/facade/candidate_fixture.hpp
- apps/docs-site/diagrams/application-facade.architecture.json
- apps/docs-site/static/diagrams/application-facade.svg
- apps/docs-site/static/diagrams/application-facade.html
- apps/docs-site/docs/core/modules/authoring-domain.mdx
- apps/docs-site/docs/core/modules/project-io.mdx
- apps/docs-site/docs/core/modules/project-cooker.mdx
- apps/docs-site/docs/core/modules/application-facade.mdx

The only L4 prerequisite copied is Eligibility plus lease_active; no lifecycle
cancel/discard implementation. Actual lifecycle/adoption race journeys remain
for coordinator integration with L4 and must be reported as unexercised here.

## Verification

Lowest tiers: Domain unit checks atomic multi-target validation and lineage;
ProjectIO component checks writer freshness, full persisted command identity,
prepublication fault rollback and reopen/recovery; Facade component exercises
real Provider terminal -> eligibility -> materialization -> quota -> one revision
-> reopen with full artifact/hash/length/lineage assertions. Include duplicates,
unknown/cross-set recipes, unrelated revision, old-revision repeat, missing or
changed source, same-recipe separate charges, cross-Bank replacement accounting,
lease exclusion/unwind, malformed/preparation/materialization failure.
Register using existing lmdj_add_test taxonomy, run focused targets with at most
4 build jobs, then full Core. Existing version fixtures may await coordinator
closure; record actual failures without weakening expectations. No new gate.

## Version Management

Version impact: required. Domain MINOR: add named adoption structures and an
apply overload without changing the existing public Command variant or layouts.
ProjectIO MINOR: additive named request and method; persisted adoption is a
new internal command with complete source identity. Cooker MINOR: additive
bounded profile-preserving selector; existing stereo selector semantics remain.
Facade MINOR: additive public JSON command and internal eligibility helper.
No Contract successor: use the already landed closed v5 lineage carrier.
Coordinator allocates dependent versions, Product Build, Assembly and snapshot
against fresh manifests after final source; no numeric reservation here.

## Documentation Impact

Documentation impact: required. Update /core/modules/authoring-domain/,
/core/modules/project-io/, /core/modules/project-cooker/ and
/core/modules/application-facade/ with actual command/source/atomicity behavior.
Coordinator owns generated identities and immutable snapshot closure.

## Coordinator version and shipment closure

Fresh allocation baseline: origin/main
`bfe0e755c24dd40bc8faea914a511bc3d5d2b603`, Product 1.0.51.0.
Allocate Domain 4.1.0, ProjectIO 4.1.0, Cooker 1.2.0 and Facade 5.1.0
for the additive APIs above. Exact dependency rebuilds: Audio 4.0.2,
Web Platform 5.2.1, CLI/MCP/Native 3.3.3, Web Runtime/Creator 4.2.3.
Product 1.0.52.0 integrates those identities with a canary documentation
snapshot; this allocates no tag, Release, deployment or promotion.

Additional declared closure files, before editing:
- packages/authoring-domain/module.json
- packages/project-io/module.json
- packages/project-cooker/module.json
- packages/application-facade/module.json
- packages/audio-runtime/module.json
- packages/web-runtime-platform/module.json
- apps/core-cli/module.json
- apps/core-mcp/module.json
- apps/core-mcp/pyproject.toml
- apps/core-mcp/lmdj_core_mcp/__init__.py
- apps/native-host/module.json
- apps/web-runtime-host/module.json
- apps/creator-web/module.json
- apps/creator-web/package.json
- apps/creator-web/package-lock.json
- products/lmdj/version.json
- products/lmdj/assembly.json
- products/lmdj/assembly.lock.json
- products/lmdj/src/compiled_assembly.cpp
- products/lmdj/generated/web-runtime-identity.json
- products/lmdj/generated/web-runtime-identity.mjs
- tests/build/version_test.py
- tests/conformance/module_graph_test.py
- apps/docs-site/test/repo-facts.test.mjs
- tests/core/facade/application_test.cpp
- apps/docs-site/docs/assembly/lmdj.mdx
- apps/docs-site/docs/operations/creator-changelog.mdx
- apps/docs-site/docs/operations/runtime-changelog.mdx
- Official snapshot generator output for Product 1.0.52.0 under
  apps/architecture-portal/versioned_docs/version-1.0.52.0/,
  apps/architecture-portal/versioned_metadata/version-1.0.52.0.json,
  apps/architecture-portal/static/versions/1.0.52.0/ and
  apps/architecture-portal/versions.json (inspect its exact output inventory).

Additional affected portal routes: /assembly/lmdj/,
/operations/creator-changelog/, /operations/runtime-changelog/.
Run manifest/dependency consistency and current portal validation before the
source commit; generate the immutable snapshot from that clean source commit,
then verify full portal and Core on the snapshot head. A generated snapshot
commit belongs to this same Task/PR. Verify post-squash provenance against the
actual introducing commit and create the official witness if required.

Local implementation evidence: final focused Domain/IO/Facade adoption and
Cooker tests passed 4/4. Initial complete Core passed 140/146; six failures and
three portal test failures were traced to pending Assembly source identity and
snapshot closure. Rerun those prerequisites after the generated identities.
Actual lifecycle/adoption process competition belongs to L4; preview and Host
journeys belong to L5. Those are not claimed as L2 evidence.

Coordinator closure verification before source commit: version tests, module
conformance and dependency checks pass. Current portal preflight passes all
116 tests and validates 44 built routes. The affected Domain/ProjectIO/Facade/
Cooker run passed 60/61; its sole stale Facade version fixture was synchronized
and the rebuilt facade.application test passed. ASan/UBSan adoption, recovery
and 100-iteration process stress pass 5/5 (43.43 seconds). New-file staged
ownership passes 70 tests. Full Core and immutable-snapshot validation remain
for the clean generated snapshot head.

## Independent review corrections

Review of head 1365569a found a public ProjectIO write/read profile mismatch:
an accurately bound non-WAV or over-16-MiB source could be persisted although
the adoption transaction reader rejects it. Reduce this in the already declared
ProjectIO adoption test, then share source-profile validation between the writer
and parser and document the refusal before publication. Also declare
`tests/host/native_host_source_boundary_test.py` to synchronize its exact
Facade/Audio dependency fixture; preserve every source/link boundary assertion.
The final Core run at that head passed 145/146 with only this Native fixture red.
These corrections complete the same unpublished additive API; no additional
version identity or frozen snapshot rewrite is required. Retain the official
1.0.52.0 snapshot and verify its post-squash source provenance, adding the
official witness if the mutable-source corrections require it.

The reduced ProjectIO regression failed on the old writer accepting the
unsupported source. Shared profile validation now follows full source freshness
under the writer, preserving the existing mismatch error order and refusing
before publication. Both accurately bound unsupported profiles reopen the
original state after refusal. Focused ProjectIO/Facade adoption plus Native Host
source-boundary checks pass 3/3 (12.28 seconds); full portal check again passes
116 tests and 44 routes. Frozen snapshot files are unchanged.
