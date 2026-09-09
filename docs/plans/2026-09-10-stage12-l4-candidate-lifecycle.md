# Stage 12 L4: Candidate lifecycle and eligibility ownership

Implementation subplan for #1041; original baseline main 1fb5c60e, integrated
with L2 at de1b9fca6ceb0d6fdd9b1a6010e2487b356ec5fb.
Authority: approved R2-A–F and Stage12 contract-candidate decision.
Coordinator owns final integration, version closure, verification, snapshot,
independent current-head review and authorized Task shipping.

## Declared files

- docs/plans/2026-09-10-stage12-l4-candidate-lifecycle.md (this plan)
- packages/application-facade/internal/lmdj/facade/candidate_store.hpp
- packages/application-facade/src/candidate_store.cpp
- packages/application-facade/src/application.cpp
- tests/core/facade/candidate_fixture.hpp (observe release of the real Project writer lease)
- tests/core/facade/candidate_job_test.cpp
- tests/core/facade/candidate_store_test.cpp
- products/lmdj/CMakeLists.txt (internal header access for eligibility tests)

Report outside repository: /tmp/stage12-l4-report.md.

## Implementation and lowest-tier verification

Persist cancelled Attempt intent and discarded Set tombstones using L1's single
Workspace owner-state replacement, retaining Job execution ownership and all
immutable terminals, history, and blobs. Cancellation addresses the exact Attempt
so a delayed command cannot cancel a newer retry. Published Attempts refuse
cancellation explicitly. A cancelled pending Attempt never reconciles or publishes.
Discard clears its active pointer in the same replacement and has no GC or TTL.

Add Facade dispatch operations and a move-only active-set eligibility lease that
holds the same Workspace mutation ownership through the L2 Project commit.
Coordinate exact interface names with coordinator. Lifecycle operations do not
need valid output bytes to persist tombstones; eligibility still verifies output
bytes and derived recipes, and L2 must check complete Project source binding.

Lowest tier: existing facade.candidate_job component suite for cancel/discard,
strict dispatch shape, refusals, immutable evidence, unavailable bytes and lease
serialization. Existing facade.candidate_store independent-process suite for
cancel before terminal, cancel after terminal before publication, discard and
supersession durable boundaries, process restart and both ownership orders.
Keep existing L1 recovery tests; run candidate_store_stress because ownership
behavior is concurrent. Build at most four jobs. No new general gate.

Each fault test must inspect far-side Job history, active pointer, tombstones,
Project equality and immutable terminal bytes where terminal exists. Interrupt
before/after lifecycle state replacements and after interruption recovery.
At the original worker baseline L2 was absent. The adoption integration section
below supplies and verifies those real Project-commit race assertions.

## Version Management

Version impact: required for additive Facade operations. Final allocation and
exact dependent closure are declared below after fresh manifest audit.
No SDK ABI or Project Contract change. Private Workspace format accepts added
cancelled/discarded statuses; it remains outside Project Truth.

## Documentation Impact

Documentation impact: required at integration for /core/modules/application-facade/
and corresponding diagram plus creator/runtime changelogs for allocated build.
Coordinator owns portal updates together with final availability/version claims;
this worker plan records only local implementation and remaining evidence.

## Local implementation evidence

Coordinator approved `candidate.job.cancel`, `candidate.set.discard` and
`CandidateStore::lease_active` naming. Dev Candidate component, independent-process
recovery (including existing L1 regressions) and provider-owner tests pass 3/3.
The 100-iteration independent-process stress suite passes with original live
exclusion plus cancellation and eligibility scenarios. ASan/UBSan component, recovery, stress and provider-owner suites pass 4/4
(104.37 seconds). Explicit remaining L2 race obligations and command evidence
are in /tmp/stage12-l4-report.md.
The original worker changed no numeric versions or portal availability claims;
final coordinator closure is declared below.

## Adoption integration

Coordinator integrated the lifecycle changes onto main 73c8009a after L3;
the three existing Candidate/provider-owner suites pass on that baseline.
Extend the declared candidate_job_test.cpp with actual candidate.adopt
refusals after discard and successful supersession, checking exact Project
files, terminal bytes, persisted history and restart. These checks require
L2 before they can pass. Subsequent process-fenced adoption/lifecycle tests
must cover the reverse ownership order, pending retry publication, failed or
cancelled retries and failed Project commits; pure lease checks do not close
those acceptance obligations.

The declared candidate_store_test.cpp adds a pipe-fenced independent discard
process while adoption is paused before manifest publication. Assert job_busy
on the competing command, then full committed Asset identity/lineage and one
revision, followed by successful discard and reopen retaining adopted truth.
Also pause a real retry after intent creation, adopt the old active set, and
finish the retry while adoption owns eligibility. Successful terminal evidence
must remain pending until restart publishes it once; an explicitly cancelled
retry must remain cancelled even when its Provider returns success. Both paths
retain the adopted Artifact and lineage through repeated reopen.
The failed-retry companion uses a real Provider parameter refusal, then adopts
the retained active set and checks both immutable Attempt records after reopen.
Use L2's storage failure seam to refuse manifest publication during adoption,
then immediately discard and reopen; assert original Project state and source
bytes, no derived Assets, retained immutable terminal and a durable tombstone.
Keep every existing 100-iteration stress leg and add the actual adoption versus
discard and both retry completion paths to that same process stress loop.

Integration on de1b9fca exposed a test-fence error: pausing inside source read
retains ProjectIO writer ownership and prevents the intended adoption interleave.
Observe the real writer lease release in the declared fixture, then pause the
retry after its owned input read has returned bytes and released that lock.
Keep the real Provider execution, terminal/publication and all far-side checks;
this changes test synchronization only and adds no product hook.

## Final integration closure

Fresh main still allocates Product 1.0.52.0. After integrated lifecycle verification,
allocate Facade 5.2.0 for additive cancel/discard operations. Exact dependency
rebuilds allocate Web Platform 5.2.2, CLI/MCP/Native 3.3.4 and Web/Creator 4.2.4.
Other Modules, Providers and Contracts retain existing identities. Product 1.0.53.0
is the next available Assembly build; recheck remote allocation before commit.
No Release, deployment, promotion, TTL, GC or physical playback claim.

Additional declared closure files:

- packages/application-facade/module.json
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
- tests/core/facade/application_test.cpp
- tests/host/native_host_source_boundary_test.py
- apps/docs-site/test/repo-facts.test.mjs
- apps/docs-site/docs/core/modules/application-facade.mdx
- apps/docs-site/diagrams/application-facade.architecture.json
- apps/docs-site/static/diagrams/application-facade.html
- apps/docs-site/static/diagrams/application-facade.svg
- apps/docs-site/docs/assembly/lmdj.mdx
- apps/docs-site/docs/operations/creator-changelog.mdx
- apps/docs-site/docs/operations/runtime-changelog.mdx
- apps/architecture-portal/versions.json
- apps/architecture-portal/versioned_metadata/version-1.0.53.0.json
- apps/architecture-portal/versioned_sidebars/version-1.0.53.0-sidebars.json
- Official generated snapshot 1.0.53.0 inventory: exactly the 44 current MDX
  routes under apps/architecture-portal/versioned_docs/version-1.0.53.0/ and
  the 20 canonical diagram HTML/SVG outputs under
  apps/architecture-portal/static/versions/1.0.53.0/; enumerate and inspect the
  generator output before staging, preserving all older immutable versions.

Lowest-tier closure verification: Candidate component/recovery/adoption/owner
suites and explicit 100-iteration process stress; ASan/UBSan same affected suites
including stress. Version/dependency/source-boundary fixtures, path ownership
and full portal checks cover the closure. Source and snapshot commits follow the
canonical clean-source freeze boundary; actual introducing squash provenance is
verified after merge and the official witness is shipped separately if required.
Documentation impact: required
Affected portal pages: /core/modules/application-facade/ /assembly/lmdj/ /operations/creator-changelog/ /operations/runtime-changelog/

Integrated source evidence: four Candidate/owner suites pass (9.90 seconds),
100-iteration native process stress passes (84.88 seconds), and affected
ASan/UBSan suites pass 5/5 (301.96 seconds, stress 273.73 seconds). These are
pre-allocation source results; rebuild and run identity-dependent checks after
closure. Source-reader-fence failure is retained in /tmp/l4-integrated-tests.log;
corrected synchronization and unchanged far-side assertions are verified in
/tmp/l4-fence-tests.log and /tmp/l4-integrated-asan-tests.log.
