# Stage 12 L5: Candidate audition and explicit Host adoption

Task #1042. Baseline main 01d9f5052d4b46da5f1e823d4883dea9ab3fd1d7
contains K5 and completed L1–L4. Approved authority is the confirmed R2-A–F
contract-candidate decision and its incorporated review. No new SDK Candidate
ABI, Project Contract or Provider platform policy is allocated here.

Baseline: existing Candidate component binary from the identical L4 product
source passes when run against this checkout; Platform protocol tests pass 29/29.
The coordinator owns integration, version closure, documentation, commits and
shipping. Workers own disjoint source files and report actual local evidence.

## Behavior and interface agreement

Add typed `CandidateAuditionRequest` with project_path, project_id,
expected_revision, job_id, set_id and candidate_id, and its own
`CandidateAuditionAudio` containing artifact, sample_rate, channels,
source_frames and shared_ptr<const cooker::PcmSample> prepared. Add
`Application::audition_candidate`. The Facade owns all active-set/terminal/recipe,
complete source binding and byte validation, bounded interval selection and PCM
preparation. It retains Workspace eligibility through preparation, checks the
current expected revision, and creates no files, Assets, Pads or revision.
Source and Pattern events remain unchanged. Use existing PCM16 mono/stereo
44.1/48 kHz profile and limits; no Host materializes bytes or parses bundles.

Facade JSON query `candidate.audition` has exactly operation plus the request
fields above. Its result reports job_id, set_id, candidate_id, artifact,
sample_rate, channels and source_frames; the normal envelope reports the
validated Project revision. CLI/MCP report metadata, without a playback claim.
Engine-owning Native/Web Hosts consume the typed prepared PCM through their
existing audition pool and report `played` only for actual voice admission.
Host-only `candidate.audition.stop` takes no selector and stops the audition;
it does not invent a Facade stop operation or alter Project Truth.

Route existing candidate.job.run/inspect/cancel, candidate.set.discard and
candidate.adopt through Native, MCP and Web public surfaces. Web payloads reject
filesystem paths and obtain the retained Project path only inside the Host.
Programmatic RuntimeSession methods follow the existing Provider snake_case
request convention:

- runCandidateJob: job_id, attempt_id, project_id, asset_id, expected_revision,
  parameters, data_classification, platform, region, required_permissions.
- inspectCandidateJob(jobId), cancelCandidateJob(jobId, attemptId),
  discardCandidateSet(jobId, setId).
- auditionCandidate: project_id, expected_revision, job_id, set_id, candidate_id.
- stopCandidateAudition(): no selectors.
- adoptCandidates: project_id, expected_revision, command_id, job_id, set_id,
  selections[{candidate_id, bank, pad}].

Results preserve the Facade fields except that the Web ControlRuntime removes
Host-owned `project_path` from Job history intent sources and Set sources before
exposing them to JavaScript. The transport/types never accept or own paths; all
source identity and recipe fields remain intact. Web normalizes the envelope Project revision
into result.project_revision as existing Provider/Sound Set routing does.
RuntimeSession validates request and response shapes and serializes mutations.
Expose this group on the packaged Host public object, beside existing providers,
so both diagnostic and Creator browser journeys exercise the actual distribution.

Creator adds a Slice surface. Source choices come from Facade project inspection
(never bundle parsing), including retained unassigned Assets. Provider selection
and permission grant are explicit user controls; default policy/selection stays
unchanged. `provider.list` additionally returns current `granted_permissions`
from Host policy so an explicit Slice grant preserves other permissions; absent
readback is not treated as an empty grant list. The reference Provider's existing test platform is not relabeled.
A stable UI Job ID `slice-${projectId}-${assetId}` fits the existing 128-byte ID
bound and lets reload inspect the same durable Job without another list API or
hidden UI persistence. Each run/retry uses a fresh Attempt ID. Existing Assembly admits only public
classification; the UI requires an explicit source checkbox before sending the
public/test/local request, preserving the current policy and local-only execution.

Show active interval recipes and a clear successful no-onset/zero-result state.
Preview/stop act only on audition state; stop on mode/project change and teardown.
No target Pad is prefilled: the user explicitly adds recipe/Bank/Pad selections,
may choose the same recipe for different Pads and cannot repeat a target. Adopt
once with a fresh command/current revision, refresh Project projection, preserve
recorded Pattern events and retain the original source. After an unknown commit
response inspect before offering a new command; never silently retry adoption.
Discard is explicit and preserves adopted Truth. A stale/source/unavailable or
quota refusal leaves every target and revision unchanged. UI copy uses ordinary
user concepts; implementation identities are not dumped into the workflow.

## Declared source and verification files

Follow-up review fixes own `apps/creator-web/src/runtime/sample_actions.ts` and
`apps/creator-web/test/sample_actions.test.ts`: normalize acknowledged public
Snapshot reload for a selected non-current Pattern; test malformed responses.
Workspace tests press Pads during deferred/failed preparation and after retry;
actual multi-Pattern browser adoption proves selection does not trap retry.


Core owner (coordinator owns integration extensions):
- packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp (document Project-only reclaimed bytes)
- packages/audio-runtime/src/realtime_engine.cpp (audition pool reclamation must not refund Project PCM reservations)
- tests/core/audio/realtime_engine_test.cpp (audition-only and mixed reclamation exact byte regression)
- packages/audio-runtime/module.json (PATCH for corrected reserved-pool accounting)
- apps/native-host/CMakeLists.txt (apply existing MCP sanitizer environment to mixed Host suite)
- CMakeLists.txt (include new audition component in existing coverage target inventory; initialize existing MCP sanitizer environment before Host registration; no gate/threshold change)
- packages/application-facade/include/lmdj/facade/application.hpp
- packages/application-facade/src/application.cpp
- packages/application-facade/CMakeLists.txt
- products/lmdj/CMakeLists.txt (new audition test Assembly linkage only)
- tests/core/facade/candidate_audition_test.cpp (new component suite)

Web Platform owner:
- packages/web-runtime-platform/src/bridge.cpp (existing operation allowlist must admit seven Candidate operations; source-boundary check plus actual browser journey)
- packages/web-runtime-platform/src/control_runtime.cpp
- packages/web-runtime-platform/web/protocol.mjs
- packages/web-runtime-platform/web/runtime_types.d.ts
- packages/web-runtime-platform/web/runtime_session.mjs
- packages/web-runtime-platform/test/control_runtime_test.cpp
- packages/web-runtime-platform/test/protocol.test.mjs
- packages/web-runtime-platform/test/runtime_session.test.mjs

Native/MCP owner:
- apps/native-host/src/main.cpp
- apps/core-mcp/lmdj_core_mcp/server.py
- tests/host/provider_owner_test.py
- tests/host/mcp_stdio_test.py (existing exhaustive tool/schema inventory must include all six new routes)
- tests/host/mcp_facade_parity_test.py
- tests/host/native_host_test.py

Creator owner:
- apps/creator-web/src/components/candidate_surface.tsx (new)
- apps/creator-web/src/state/candidate_state.ts (new, if needed for explicit plan)
- apps/creator-web/src/components/mode_rail.tsx
- apps/creator-web/src/app.tsx
- apps/creator-web/src/runtime/runtime_types.ts
- apps/creator-web/src/styles.css
- apps/creator-web/test/candidate_surface.test.tsx (new)
- apps/creator-web/test/candidate_state.test.ts (new, if state module used)
- apps/creator-web/test/workspace_shell.test.tsx
- apps/creator-web/test/shell_polish.test.tsx
- tests/platform/web/creator/creator_web_candidate.spec.mjs (new real UI journey)

Coordinator browser acceptance and integration:
- tests/platform/web/creator/creator_web_accessibility.spec.mjs (include Slice in
  the exact complete keyboard rail, derive walk length from that explicit list,
  and retain Perform as the final asserted stop; all three viewport regressions)
- apps/creator-web/src/state/creator_state.ts (invalidate adopted audio until verified publication; reject stale/foreign publication)
- apps/creator-web/test/creator_state.test.ts (saved/runtime revision separation and publication identity)
- scripts/creator-web.sh (generate and pass dedicated Candidate UI fixture through official proof)
- tests/platform/web/creator/fixtures/make_candidate_fixture.py (public CLI-authored assigned Pad and nonempty Pattern, canonical bundle packing; actual UI import is the consumer gate)
- apps/creator-web/src/runtime/project_actions.ts (accept active Project v5 in the existing immutable Pattern projection)
- apps/creator-web/test/project_actions.test.ts (v5 projection and malformed slot rejection; preserve unknown-version refusal)
- scripts/ci/scope_policy.json (route shared Candidate journey to both consuming Host lanes; staged ownership suite)
- .agents/pitfalls/cpython-asan-exception-runtime.md (record compiler/CPython preload ordering observed by actual MCP refusal)
- .agents/pitfalls/playwright-option-label-value-collision.md (record ambiguous string selection at the browser tool boundary)
- tests/platform/web/candidate_journey.mjs (new shared actual Web Host journey)
- tests/platform/web/host/web_runtime_host_candidate.spec.mjs (new)
- tests/platform/web/creator/creator_web_candidate_runtime.spec.mjs (new)
- docs/plans/2026-09-10-stage12-l5-candidate-host-preview.md (this plan)

If implementation needs another file, declare the exact path and its defect/test
before editing. Do not add broad gates or remove existing journey legs.

Integration defects reduced before fixing:
- Independent review F1: adoption refreshed visible Pads but kept the old
  Runtime Bank. Creator must invalidate old playback, prepare the selected
  Pattern through the public snapshot route, and expose explicit preparation
  retry after a durable commit without repeating adoption. Workspace component
  tests cover publication/failure/retry; packaged UI checks play adopted audio
  before reopen, including replacement of an occupied Pad.
- Creator's inherited projection rejected active Project v5 after Core opened
  it successfully. Extend the existing v4 Pattern projection to v5, whose new
  Asset lineage does not change that projection. The component first failed
  on valid v5; unknown-version and malformed-slot refusals remain covered.
- Audition-only reclaimed Banks were included in Project reservation byte refunds,
  causing actual Web close failure. Engine regression first asserts the exact
  distinct accounting; Core budget, pool capacity, lifetime and ramp rules stay.
- The mixed Host suite loads C ABI through CPython but omitted the existing MCP
  sanitizer environment. Apply the same scoped environment, preserving native
  C++ leak checks and all actual transport cases. On GNU/Linux, preload the
  compiler-resolved C++ runtime after libasan so its exception interceptor can
  initialize before ctypes loads C ABI. The real MCP binding-refusal journey
  reproduced the interceptor failure and passes with both runtimes present.

Creator packaging and both official proof/freeze paths require clean source.
Create a local source commit after component/native/ASAN verification, then run
packaged browser acceptance and official proofs before shipping. Any fixes and
the official snapshot are folded into this Task's final single commit.

## Lowest-tier tests and acceptance

Core audition component: real Slice terminal -> eligible recipe -> prepared PCM
with exact interval samples/rate/resampling; preview repeated/reopen leaves full
Project files, revision, Pad bindings, Pattern events, source bytes and owner
state unchanged. Reject malformed/stale/unknown/discarded/superseded/missing or
corrupt source/output; full far-side equality for each refusal. Existing L2/L4
adoption/lifecycle suites remain integration companions.

Native/CLI/MCP actual transports: analyze/inspect -> metadata or admitted engine
preview -> stop where an engine exists -> explicit repeated-recipe distinct-Pad
adoption -> inspection -> process close/reopen. Assert one revision, distinct
Assets, full lineage/source retention, Pattern preservation and typed refusals.
MCP schema advertises exact required/extra-key and numeric boundaries. Native
no-device execution proves engine PCM/state, not physical-device sound.

Platform unit/component: strict private protocol payloads/sidecars/path rejection,
retained Project ownership, metadata vs played, audition stop, mutation ordering,
malformed response rejection and revision refresh. Preserve existing resource,
recovery and closed-host behavior.

Creator component/state: explicit provider/permission actions, source switching,
no-onset success, no hidden Pad default, duplicate target rejection, same recipe
on distinct targets, preview/stop cleanup, stale-response protection, successful
refresh and refusal/unknown-response behavior. Run the React quality checklist.

Real pinned browser journeys through each packaged Web Host, plus actual Creator
UI: analyze -> recipes -> preview -> stop -> unchanged Project; explicit targets
-> adopt once -> saved truth -> reload/reopen with full Asset/lineage and Pattern
assertions; zero-onset and stale/source/unavailable refusal legs. Observe actual
engine output/admission and stop; synthetic blur alone is not audio evidence.
Use Emscripten 6.0.5, Node 22 and locked Playwright browsers through the stable
web-runtime-host.sh/creator-web.sh proof entry points. Browser verification skills
apply when servers run. No physical-device, complete CI or release claim.

The two isolated Pad-audio assertions select and prepare a newly authored empty Pattern while stopped,
while retaining and asserting the original recorded Pattern unchanged. Otherwise
its automatic A1 loop mixes negative fixture PCM into B1's positive Pad output;
the complete recorded-Pattern adoption/reopen journey remains separate and intact.

## Version Management

Version impact: required
Fresh baseline has Product 1.0.53.0. Planned additive identities: Facade 5.3.0,
Web Platform 5.3.0, Native/MCP 3.4.0, Creator/Web Runtime Host 4.3.0. Generic CLI
has only an exact Facade dependency rebuild, PATCH 3.3.5. Audio Runtime receives PATCH 4.0.3 for audition reclamation incorrectly refunding
Project PCM reservations; exact consumers update their dependency identities.
Other Modules, Providers, Contracts and SDK ABI remain unchanged. Recheck then-live manifests before final
allocation; Product 1.0.54.0 is the next available Assembly Build, with its
immutable canary documentation snapshot. This is no Release or promotion.

Declared closure files:
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
- apps/architecture-portal/versions.json
- apps/architecture-portal/versioned_metadata/version-1.0.54.0.json
- apps/architecture-portal/versioned_sidebars/version-1.0.54.0-sidebars.json
- Exact official Build54 generated inventory: 44 current MDX documents under
  apps/architecture-portal/versioned_docs/version-1.0.54.0/ and 20 canonical HTML/SVG
  assets under apps/architecture-portal/static/versions/1.0.54.0/; enumerate and
  inspect exact outputs before staging, preserving every older snapshot.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/audio-runtime/ /core/modules/application-facade/ /core/modules/web-runtime-platform/ /hosts/core-cli/ /hosts/core-mcp/ /hosts/native-host/ /hosts/web-runtime/ /hosts/creator-web/ /product/workflows/ /overview/ /assembly/lmdj/ /operations/creator-changelog/ /operations/runtime-changelog/

Declared current documentation/diagram files:
- apps/docs-site/docs/core/modules/audio-runtime.mdx
- apps/docs-site/docs/core/modules/application-facade.mdx
- apps/docs-site/docs/core/modules/web-runtime-platform.mdx
- apps/docs-site/docs/hosts/core-cli.mdx
- apps/docs-site/docs/hosts/core-mcp.mdx
- apps/docs-site/docs/hosts/native-host.mdx
- apps/docs-site/docs/hosts/web-runtime.mdx
- apps/docs-site/docs/hosts/creator-web.mdx
- apps/docs-site/docs/product/workflows.mdx
- apps/docs-site/docs/overview/index.mdx
- apps/docs-site/docs/assembly/lmdj.mdx
- apps/docs-site/docs/operations/creator-changelog.mdx
- apps/docs-site/docs/operations/runtime-changelog.mdx
- apps/docs-site/diagrams/audio-runtime.architecture.json
- apps/docs-site/static/diagrams/audio-runtime.html
- apps/docs-site/static/diagrams/audio-runtime.svg
- apps/docs-site/diagrams/application-facade.architecture.json
- apps/docs-site/diagrams/web-runtime-platform.architecture.json
- apps/docs-site/static/diagrams/application-facade.html
- apps/docs-site/static/diagrams/application-facade.svg
- apps/docs-site/static/diagrams/web-runtime-platform.html
- apps/docs-site/static/diagrams/web-runtime-platform.svg

The overview's inherited stale Build/provider/Contract count prose, observed by
L4 review, is corrected here with manifest-derived identity or references to the
active generated inventory, never new hand-entered current identity/count claims.
Actual source facts, portals and diagrams update in this Task. Run full portal
verification and official clean-source freeze; inspect actual introducing squash
provenance after merge and generate a separate official witness if required.
