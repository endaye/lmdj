# Meter / capture progress integration — 2026-10-21

One follow-up conflict-resolution Task on published PR #2430. Previous head
7a765145a4df8ed6baee4252da5bfa4b777204d8 remains unchanged in history.
Integration target: main19e8ce3c5e84cf98dd3dd8fac9348585018002de.

## Refreshed premise dispositions

- Live PR #2430 is CONFLICTING with current main, not merely behind. git
  merge-tree independently identifies the same four content conflicts.
- Main already delivered saved metadata query/retirement, capture progress
  #2440 and optional-telemetry isolation #2441. Preserve their source, tests,
  queue and lifetime semantics; no duplicate implementation or old whole files.
- Meter owner/ACK, actual-clock projection and two valid finding fixes remain
  developed at7a765145, unmerged. Preserve current-owner versus foreign-owner
  ACK isolation and trusted-only native error admission, including tests.
- Original Draft #2383/3cdf and every downstream original published stack head
  remain unchanged. #2430's old fixed finding threads remain unresolved until
  real automatic repair receipts or the pending owner exception permits them.
  Conflict work does not authorize hand-resolution or waive independent review.

## Exact Task scope

Resolve four declared conflicts by retaining both independent features:

- apps/docs-site/docs/core/modules/web-runtime-platform.mdx
- apps/docs-site/docs/platform/web-runtime.mdx
- packages/web-runtime-platform/web/performance_master_capture.mjs
- packages/web-runtime-platform/web/runtime_session.mjs

Add this plan and, if needed to cover composition, owning regressions in
packages/web-runtime-platform/test/performance_master_capture.test.mjs and
packages/web-runtime-platform/test/runtime_session.test.mjs.

Use one normal merge commit to preserve both already-published histories. The
merge imports the exact current-main files listed below; no other session's
changes are staged. Upstream release-owned files are already on main and must
remain byte-identical to it; they are not edited or included in the net PR diff.
No force/amend, scope/gate/budget/timeout change or withdrawn COUNT-IN consumer.

## Verification

Inspect all auto-merged source/type/test unions and keep every old case.
Run complete Platform Node, strict SDK/Creator types, Perform callers,
dependencies/source boundaries, official target source-diagram render plus
unrelated output hashes, complete Portal and staged/committed ownership.
Repeat existing four semantic meter controls with exact fresh restores; add
composition assertion if existing tests cannot cover simultaneous owners.
After a verified clean commit, official pinned Creator configure/build/package,
full normal+actual-render-fault meter journeys and full current-main Perform/
touch selection must pass, including actual capture-progress journey. Preserve
all original transition legs, budgets, PCM/SHA/Stop/close/reopen/owner assertions.
Parent receipts and retained graph/alias negatives remain separately scoped;
current-head independent review and real repair publication remain required.

## Version Management

Version impact: none beyond existing compatible Platform JS API MINOR debt in
#2237. Composition of two approved optional capabilities; preserve higher debt.
No Native ABI/Contract/persistence/manifest/Product/Build/Channel/snapshot change.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/web-runtime-platform/ /platform/web-runtime/
Preserve meter, saved metadata and capture progress facts; correct the stale
meter paragraph's claim that capture has no applied started ACK. Keep existing
source diagram/outputs; regenerate officially only if the renderer requires it.

## Pitfall Impact

Pitfall impact: none; content conflicts and composition behavior are directly
covered by source checks/tests. Existing live-phase-polling-alias record and
escalation #2382 are preserved without a new recurrence claim.

## Shipping authority and evidence boundaries

User authorizes ordinary sequential integration plus safe postmerge cleanup.
No merge until Task checks, exact-head review, findings/conversations/conflicts
and live protection pass. Original fixed threads are not hand-resolved.
Root main and dirty WIPs stay untouched. No auto-merge/tag/Release/Runtime
 deployment/Channel; frozen paths remain absent from the PR's main-relative diff.

## Exact upstream-import inventory

- .agents/pitfalls/gate-failure-readability.md
- .agents/pitfalls/live-phase-polling-alias.md
- CMakeLists.txt
- apps/docs-site/diagrams/web-runtime-platform.architecture.json
- apps/docs-site/docs/core/modules/application-facade.mdx
- apps/docs-site/docs/core/modules/project-cooker.mdx
- apps/docs-site/docs/core/modules/project-io.mdx
- apps/docs-site/docs/core/modules/web-runtime-platform.mdx
- apps/docs-site/docs/platform/storage.mdx
- apps/docs-site/docs/platform/web-runtime.mdx
- apps/docs-site/static/diagrams/web-runtime-platform.html
- apps/docs-site/static/diagrams/web-runtime-platform.svg
- docs/plans/2026-10-19-performance-artifact-scan.md
- docs/plans/2026-10-19-performance-capture-progress.md
- docs/plans/2026-10-19-performance-recording-metadata-query.md
- docs/plans/2026-10-19-performance-recording-metadata-reader.md
- docs/plans/2026-10-19-stereo-output-meter-producer.md
- docs/plans/2026-10-19-storage-range-reader.md
- docs/plans/2026-10-19-streaming-wav-metadata.md
- docs/plans/2026-10-20-meter-review-isolation.md
- docs/plans/2026-10-20-performance-recording-bounded-verification.md
- docs/plans/2026-10-20-project-discovery-bounded-inventory.md
- docs/plans/2026-10-21-capture-progress-telemetry-isolation.md
- packages/application-facade/CMakeLists.txt
- packages/application-facade/include/lmdj/facade/application.hpp
- packages/application-facade/include/lmdj/facade/performance_recording_metadata.hpp
- packages/application-facade/src/application.cpp
- packages/application-facade/src/performance_recording_metadata.cpp
- packages/project-cooker/CMakeLists.txt
- packages/project-cooker/include/lmdj/cooker/wav_metadata_inspector.hpp
- packages/project-cooker/src/sample_analysis.cpp
- packages/project-cooker/src/wav_metadata_inspector.cpp
- packages/project-io/CMakeLists.txt
- packages/project-io/include/lmdj/project_io/project_store.hpp
- packages/project-io/include/lmdj/project_io/storage_platform.hpp
- packages/project-io/src/native/storage_platform.cpp
- packages/project-io/src/project_bundle_transfer.cpp
- packages/project-io/src/project_store.cpp
- packages/project-io/src/testing_hooks.hpp
- packages/project-io/src/web/library_opfs_storage.js
- packages/project-io/src/web/storage_platform.cpp
- packages/web-runtime-platform/CMakeLists.txt
- packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp
- packages/web-runtime-platform/src/bridge.cpp
- packages/web-runtime-platform/src/control_runtime.cpp
- packages/web-runtime-platform/src/recording_metadata_queries.cpp
- packages/web-runtime-platform/src/recording_metadata_queries.hpp
- packages/web-runtime-platform/test/performance_master_capture.test.mjs
- packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs
- packages/web-runtime-platform/test/performance_protocol.test.mjs
- packages/web-runtime-platform/test/protocol.test.mjs
- packages/web-runtime-platform/test/recording_metadata_query_test.cpp
- packages/web-runtime-platform/test/runtime_session.test.mjs
- packages/web-runtime-platform/web/performance_master_capture.mjs
- packages/web-runtime-platform/web/performance_master_tap_worklet.js
- packages/web-runtime-platform/web/protocol.mjs
- packages/web-runtime-platform/web/runtime_session.mjs
- packages/web-runtime-platform/web/runtime_types.d.ts
- scripts/ci/scope_policy.json
- tests/build/release_cli_orchestration_test.py
- tests/build/release_draft_step_test.py
- tests/build/release_entry_enrollment_test.py
- tests/build/release_github_api_test.py
- tests/build/release_orchestration_driver_test.py
- tests/build/release_prepared_step_test.py
- tests/build/release_transitions_test.py
- tests/core/cooker/wav_metadata_inspector_test.cpp
- tests/core/facade/performance_recording_metadata_test.cpp
- tests/core/project_io/performance_recording_scan_test.cpp
- tests/core/project_io/performance_recording_verification_test.cpp
- tests/core/project_io/project_bundle_transfer_test.cpp
- tests/core/project_io/storage_platform_contract_test.cpp
- tests/platform/web/audio/realtime_audio_worklet.spec.mjs
- tests/platform/web/creator/creator_web_output_meter.spec.mjs
- tests/platform/web/creator/creator_web_perform.spec.mjs
- tests/platform/web/project_io/CMakeLists.txt
- tests/platform/web/project_io/opfs_writer_error_test.mjs
- tests/platform/web/project_io/project_io_web_conformance.spec.mjs
- tests/platform/web/project_io/project_io_web_test.cpp
- tools/release/carriers.py
- tools/release/cli.py
- tools/release/commands.py
- tools/release/deployment_effect.py
- tools/release/draft_step.py
- tools/release/entry_composition.py
- tools/release/github_api.py
- tools/release/orchestration.py
- tools/release/orchestration_driver.py
- tools/release/prepared_step.py
- tools/release/publication_effect.py
- tools/release/transitions.py

## Verified source before the follow-up commit

Initial automatic union preserves all632 existing cases. Added one owning
real-processor VM composition journey; full Platform633/633 PASS1.852s,
zero skips. It changes meter owner during real counted capture, preserves
4800 delivered frames, includes1216 final partial, asserts closed-form6016
rendered frames, and confirms meter ownerB continues after capture stopped.
This is actual Worklet source in Node VM, not physical device/audio acceptance.

All four existing semantic controls RED1 / fresh byte-identical restore GREEN0,
then the complete633 selection above. Strict SDK/Creator tsc, Perform170,
dependencies/Runtime/Host boundaries/pitfall15 PASS. Official diagrams unchanged
across all20 output hashes. Full Portal179tests/53pages/51routes PASS59.951s.
Staged ownership76 PASS9.267s. Previous7a603/browser/repair receipts remain
parent evidence. The precommit scope resolver sees old HEAD and therefore its
full result is not the final committed17-file main-relative ownership result.

The staged merge contains83 main-import/conflict/plan paths relative to7a;
all upstream-only staged blobs equal main19e8ce3c exactly. Net PR is precisely
original16 meter paths plus this plan; frozen-path net inventory is empty.
No unrelated staged/unstaged/untracked work existed before this Task. Main
refresh remains19e8ce3c; all seven governance hashes unchanged. Production,
browser, committed scope and exact-head review remain pending at this clean
source checkpoint and must finish before push/merge.
