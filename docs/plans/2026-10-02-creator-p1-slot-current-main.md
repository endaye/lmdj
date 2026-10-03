# P1 per-slot Sound Set acquisition and current main convergence

## Scope

Resolve three actual conflicts between d00f867b79d4f506aa32b5531d22402f493c50fe and main f6dedbe53645b52446078ffa9a66710f83fbf24b. Retain the complete main Pattern event API and P1's three per-slot Catalog operations. The actual merged inventory has 98 unique operation names; its array size must cover exactly those names. Move unchanged per-slot documentation before Pad deletion sections while retaining the entire current main Pattern editing documentation. Preserve the remaining actual main merge, including default-neutral Pad DSP parameters, histories and source identities. No unrelated later main update is required here.

## Declared files

- `.agents/pitfalls/asan-macos-fork-child-stack-depot-boundary.md`
- `.agents/pitfalls/clean-text-merge-breaks-the-build.md`
- `.agents/pitfalls/local-ci-list-names-batch-lanes.md`
- `.agents/pitfalls/parity-check-between-agreeing-copies.md`
- `.agents/pitfalls/revert-proof-rebuild-skipped.md`
- `.agents/pitfalls/review-invalid-output-is-model-flake.md`
- `.agents/skills/issue-done/SKILL.md`
- `.agents/skills/lmdj-release/SKILL.md`
- `.github/workflows/pr-review.yml`
- `CMakeLists.txt`
- `apps/cardputer-host/main/CMakeLists.txt`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/authoring_history.tsx`
- `apps/creator-web/src/components/candidate_surface.tsx`
- `apps/creator-web/src/components/overview_display.tsx`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/components/sequence_grid.tsx`
- `apps/creator-web/src/components/sequence_overview.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/soundset_surface.tsx`
- `apps/creator-web/src/components/waveform_editor.tsx`
- `apps/creator-web/src/runtime/project_actions.ts`
- `apps/creator-web/src/runtime/runtime_types.ts`
- `apps/creator-web/src/state/creator_state.ts`
- `apps/creator-web/src/state/error_messages.ts`
- `apps/creator-web/src/state/perform_state.ts`
- `apps/creator-web/src/state/sequence_grid_model.ts`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/authoring_history.test.tsx`
- `apps/creator-web/test/candidate_surface.test.tsx`
- `apps/creator-web/test/creator_state.test.ts`
- `apps/creator-web/test/error_messages.test.ts`
- `apps/creator-web/test/hardware_console.test.tsx`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/sample_state.test.ts`
- `apps/creator-web/test/sequence_grid.test.tsx`
- `apps/creator-web/test/sequence_grid_model.test.ts`
- `apps/creator-web/test/sequence_pattern_overview.test.tsx`
- `apps/creator-web/test/sequence_surface.test.tsx`
- `apps/creator-web/test/shell_polish.test.tsx`
- `apps/creator-web/test/soundset_surface.test.tsx`
- `apps/creator-web/test/waveform_editor.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/docs/assembly/lmdj.mdx`
- `apps/docs-site/docs/contracts/runtime-snapshot.mdx`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/docs/core/modules/authoring-domain.mdx`
- `apps/docs-site/docs/core/modules/project-cooker.mdx`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `apps/docs-site/docs/product/workflows.mdx`
- `docs/governance/minimization-principle.md`
- `docs/plans/2026-09-30-creator-sample-parity.md`
- `docs/plans/2026-10-02-creator-p1-slot-current-main.md`
- `docs/plans/2026-10-02-creator-recovery-prompt-and-error-language.md`
- `docs/plans/2026-10-02-creator-sequence-grid.md`
- `docs/prd/decisions/2026-10-02-sample-voice-endings-and-stops.md`
- `docs/prd/decisions/2026-10-02-sequence-grid-live-edit.md`
- `docs/quality/core-test-policy.md`
- `packages/application-facade/CMakeLists.txt`
- `packages/application-facade/src/application.cpp`
- `packages/audio-runtime/CMakeLists.txt`
- `packages/audio-runtime/include/lmdj/audio/detail/voice_dsp.hpp`
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/offline_renderer.cpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `packages/audio-runtime/src/voice_dsp.cpp`
- `packages/authoring-domain/include/lmdj/domain/commands.hpp`
- `packages/authoring-domain/include/lmdj/domain/project.hpp`
- `packages/authoring-domain/src/command_handler.cpp`
- `packages/authoring-domain/src/project.cpp`
- `packages/project-cooker/CMakeLists.txt`
- `packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp`
- `packages/project-cooker/src/project_cooker.cpp`
- `packages/project-cooker/src/runtime_content.cpp`
- `packages/project-io/include/lmdj/project_io/project_store.hpp`
- `packages/project-io/src/project_store.cpp`
- `packages/web-runtime-platform/src/bridge.cpp`
- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/web-runtime-platform/test/protocol.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `packages/web-runtime-platform/web/protocol.mjs`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `scripts/ci/pr-agent/runtime.toml`
- `scripts/ci/pr_agent_review.py`
- `scripts/ci/review_pipeline.py`
- `scripts/ci/review_scope.py`
- `tests/build/cardputer_host_build_test.py`
- `tests/build/ci_pr_agent_review_test.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `tests/build/ci_review_pipeline_test.py`
- `tests/build/release_deployment_effect_test.py`
- `tests/build/release_dispatch_evidence_test.py`
- `tests/build/release_durable_dispatch_test.py`
- `tests/build/release_publication_effect_test.py`
- `tests/core/audio/master_fx_stress_test.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- `tests/core/audio/voice_dsp_disabled_test.cpp`
- `tests/core/audio/voice_dsp_parity_test.cpp`
- `tests/core/audio/voice_dsp_test.cpp`
- `tests/core/cooker/project_cooker_test.cpp`
- `tests/core/cooker/runtime_content_test.cpp`
- `tests/core/cooker/voice_dsp_neutrality_cases.hpp`
- `tests/core/domain/authoring_delta_test.cpp`
- `tests/core/domain/command_handler_test.cpp`
- `tests/core/domain/project_test.cpp`
- `tests/core/facade/pattern_events_edit_test.cpp`
- `tests/core/project_io/authoring_history_test.cpp`
- `tests/core/project_io/project_store_test.cpp`
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/creator/creator_web_soundset.spec.mjs`
- `tools/release/deployment_effect.py`
- `tools/release/dispatch_evidence.py`
- `tools/release/durable_dispatch.py`
- `tools/release/entry_composition.py`
- `tools/release/github_api.py`
- `tools/release/publication_effect.py`

## Task verification

Stage only the declared merge files and capture the tested index tree. Before commit run stable Core configure/build and the complete fast tiers (unit and component), Platform protocol/session tests, staged ownership tests and the complete portal check. Require 98 unique supported operation names including the main Pattern event edit and all three per-slot operations; the existing native and protocol tests cover their routing and typed validation. These checks catch lost Core/Facade/Platform behavior, an undersized/empty operation entry, partial acquisition/install regressions, unowned paths and inaccurate rendered documentation. After commit derive the actual production plan and run any changed batch inputs on the clean committed head. Reuse complete receipts only after exact current key equality is authenticated.

Earlier complete passes and actual failures remain historical evidence; this convergence cannot reuse changed inputs. Independent current-head review, complete required batch evidence, live conversations/protection and guarded merge remain separate. No risk acceptance, test de-selection or budget/floor change is introduced.

## Version Management

Version impact: none for this convergence. Preserve actual main identities and immutable snapshots. The P1 per-slot API debt is still settled by the coordinated integration Task from live manifests and reservations; this merge allocates no identity.

Documentation impact: required
Reason: preserve current main Pad DSP and Pattern edit documentation together with the per-slot Sound Set store, Facade and Platform API facts.
Affected portal pages: /core/modules/project-io/, /core/modules/application-facade/, /core/modules/web-runtime-platform/, /core/modules/audio-runtime/, /core/modules/authoring-domain/, /core/modules/project-cooker/, /contracts/runtime-snapshot/, /assembly/lmdj/, /hosts/creator-web/, /operations/testing-and-proof/
