# Stage 12 L1: durable Workspace Slice jobs and candidates

Status: implementation verified; clean-source snapshot and shipping pending. Baseline main 5b1db209; Issue #1038.
Authority: ../prd/decisions/2026-09-09-stage12-contract-candidate.md and the
R2-A–F field/transition tables in ../design/2026-09-09-stage12-contract-candidate-review.md.

## Behavior and boundaries

Facade owns a Workspace CandidateStore. SDK retains its singular immutable
terminal Candidate. New `candidate.job.run` accepts one source Project/Asset,
current revision, Job and Attempt IDs and explicit execution policy. It binds
complete source Artifact identity and original revision before execution.
`candidate.job.inspect` recovers only recorded pending Attempts and returns
ordered history, the active Set and its interval recipes. SDK output reads use
a new checked accessor rather than teaching Facade the private terminal layout.

One execution lease per Job spans execution. A separate Workspace mutation
lease serializes short state transitions; it does not span Provider execution.
Cooperating native processes and browser runtimes use the existing storage
platform writer lease; an additional process-local mutex covers its reentrant
lease semantics. Recovery never mistakes a live executor for interruption.

Persist an intent with newly allocated Set identity before invoking Provider.
Validate successful terminal identity, bound source and output bytes before
expanding intervals. Publish Job history, new Set, active pointer and previous
Set supersession in one atomic owner-state replacement. Failed retries retain
old active Sets. Recovery publishes a recorded successful Attempt once; absent
terminal becomes interrupted, never automatically reruns. IDs survive restart.
Zero onset gives a successful empty Set. Otherwise boundaries are unique
0/onsets/EOF and every adjacent nonempty interval becomes a recipe.

Candidate reads never change Project Truth. L2 owns adoption; L3 owns persisted
lineage; L4 adds cancel/discard operations and lifecycle/adoption race coverage;
L5 owns Host UI and transient preview. L1 already proves basic crash recovery
and cross-process exclusion. Do not defer those guarantees to L4.

## Declared files

Create:
- this plan;
- packages/application-facade/internal/lmdj/facade/candidate_store.hpp;
- packages/application-facade/src/candidate_store.cpp;
- tests/core/facade/candidate_store_test.cpp;
- tests/core/facade/candidate_job_test.cpp;
- tests/core/facade/candidate_fixture.hpp;
- tests/core/provider/attempt_output_read_test.cpp.

Modify:
- CMakeLists.txt (coverage target registration);
- CMakePresets.json (exclude repeated Candidate stress from coverage);
- products/lmdj/CMakeLists.txt (actual-Assembly consumer test linkage);
- packages/application-facade/src/application.cpp;
- packages/application-facade/CMakeLists.txt;
- packages/provider-sdk/include/lmdj/provider/attempt_store.hpp;
- packages/provider-sdk/src/attempt_store.cpp;
- tests/core/provider/CMakeLists.txt;
- tests/build/version_test.py (exact module-version/dependency fixture);
- tests/conformance/module_graph_test.py (exact manifest fixture);
- tests/host/native_host_source_boundary_test.py (exact manifest fixture);
- tests/conformance/version_lock_test.py (exact composition/version fixture);
- apps/docs-site/test/repo-facts.test.mjs (exact composition/version fixture);
- tests/core/provider/conformance_test.cpp (exact composition/version fixture);
- tests/core/provider/sample_slice_test.cpp (exact composition/version fixture);
- tests/core/provider/spec_regression_test.cpp (exact composition/version fixture);
- tests/core/facade/assembly_loader_test.cpp (exact composition/version fixture);
- tests/core/facade/application_test.cpp (exact composition/version fixture);
- packages/application-facade/module.json;
- packages/provider-sdk/module.json;
- packages/web-runtime-platform/module.json;
- apps/core-cli/module.json;
- apps/core-mcp/module.json;
- apps/native-host/module.json;
- apps/web-runtime-host/module.json;
- apps/creator-web/module.json;
- apps/creator-web/package.json (Host package identity);
- apps/creator-web/package-lock.json (Host package identity);
- providers/local-proof-success/module.json;
- providers/local-proof-failure/module.json;
- providers/local-sample-slice/module.json;
- providers/local-proof-success/CMakeLists.txt (compiled Provider identity);
- providers/local-proof-success/src/provider.cpp (compiled Provider identity);
- providers/local-proof-failure/CMakeLists.txt (compiled Provider identity);
- providers/local-proof-failure/src/provider.cpp (compiled Provider identity);
- providers/local-sample-slice/CMakeLists.txt (compiled Provider identity);
- providers/local-sample-slice/src/provider.cpp (compiled Provider identity);
- products/lmdj/version.json;
- products/lmdj/assembly.json;
- products/lmdj/assembly.lock.json;
- products/lmdj/src/compiled_assembly.cpp;
- products/lmdj/generated/web-runtime-identity.json;
- products/lmdj/generated/web-runtime-identity.mjs;
- apps/docs-site/docs/core/modules/application-facade.mdx;
- apps/docs-site/docs/core/modules/provider-sdk.mdx;
- apps/docs-site/docs/operations/creator-changelog.mdx;
- apps/docs-site/docs/operations/runtime-changelog.mdx;
- apps/docs-site/diagrams/application-facade.architecture.json;
- apps/docs-site/static/diagrams/application-facade.html;
- apps/docs-site/static/diagrams/application-facade.svg;
- apps/docs-site/diagrams/provider-sdk.architecture.json;
- apps/docs-site/static/diagrams/provider-sdk.html;
- apps/docs-site/static/diagrams/provider-sdk.svg;

Verify manifest/generated filenames before editing. Amend this inventory for
any mechanically demonstrated dependent fixture or routing change before making
it; do not weaken existing tests to accommodate new operations or identities.
The clean-source snapshot is a separate generated commit in the same PR, with
its exact generated paths recorded before staging. Use the official generator
and post-squash witness procedure.

## Verification and defect mapping

Baseline: existing facade.provider_owner component suite.
New component suites cover stable recipes, no-onset, leading/tail intervals,
failed retry retention, identity/context refusals, corrupt output bytes,
concurrent Job refusal, Workspace serialization, and malformed owner state.
SDK output tests prove a reader cannot read unbound artifacts and verifies hash
and length. Facade integration invokes the registered real Provider and checks
full Project equality and terminal immutability after inspect/restart.
Independent-process tests kill after intent, after terminal and after owner
publication; each restart inspects stable IDs and actual far-side state.
Concurrency changes also run facade.candidate_store_stress (100 synchronized independent-process races) and the new suites under ASan/UBSan. The deterministic single race stays in normal coverage.

Run registered new suites and affected Facade/Provider tests, Core dependency,
version and module graph checks. Stage new paths before ci_change_scope_test.
Run scripts/core.sh proof and scripts/docs-site.sh check against the final clean
source/snapshot. Browser storage evidence is separate; L5 must exercise the
complete shipped browser journey. No new general merge gate is introduced.

## Version Management

Version impact: required. SDK 2.1.0 -> 2.2.0 adds a nonvirtual verified output
read; Facade 4.1.0 -> 4.2.0 adds Job operations. Preserve C ABI version and the
singular SDK result. Exact dependents receive patch bumps: proof Providers
2.0.1 -> 2.0.2, slice Provider 1.0.1 -> 1.0.2, Web platform 5.1.0 -> 5.1.1,
CLI/MCP/native Hosts 3.3.0 -> 3.3.1, Web/Creator Hosts 4.2.0 -> 4.2.1.
Product 1.0.48.0 -> 1.0.49.0 with canary documentation snapshot; recheck remote
allocation before freezing. No Project Contract or model changes. Workspace
state is new and private, not Project Truth or a cross-language Contract.
No tags, release, deployment or Channel promotion in this Task; rollback uses
the prior immutable build, never a moved tag.

## Documentation Impact

Documentation impact: required.
Affected portal pages: /core/modules/application-facade/ /core/modules/provider-sdk/ /operations/creator-changelog/ /operations/runtime-changelog/
Update current availability and generated identities with the implementation;
freeze the allocated Build and verify provenance at the actual merged revision.

## Verification evidence before snapshot

- `ctest --preset release -R '^(facade\.|provider\.)' -LE '^stress$'`: 43/43 PASS.
- `python3 tests/build/version_test.py`, `python3 tests/conformance/version_lock_test.py`,
  `python3 tests/conformance/module_graph_test.py`: PASS.
- Core dependency verifier and staged new-file ownership (66 tests): PASS.
- ASan/UBSan new Candidate/SDK suites plus 100 cross-process races: 4/4 PASS (33.97s).
- `npm run check:current` in apps/docs-site: PASS, including 44 built routes.
- New process suite covers three crash boundaries both with and without a prior
  active Set, plus synchronized live-owner inspect/retry contention. Recovery
  preserves old Sets for interruption and atomically supersedes on success.
- Full `scripts/core.sh proof` and `scripts/docs-site.sh check` must pass after
  clean-source snapshot generation. Initial full runs exposed missing LFS fixture
  bytes, stale compiled Provider version constants and exact version fixtures;
  these are corrected and the affected suites above pass. Snapshot-dependent
  release checks cannot pass before the allocated Build snapshot exists.
- No new pitfall ledger entry: output/store refusal defects are expressed by
  regression tests; no new shared process invariant was discovered.
