# Empty-Pad recording retains the current streaming parent

Adopt streaming7c3e6c254820e78964ddc696130366cb67030084, which owns actual
mainf739 Project Contract5.2, UI errors, FX gestures, Tempo controls and stage
layout. Preserve R7 capture-gesture identity, foreign-pointer cancellation
refusal and lifecycle cleanup; preserve R8 independent microphone Context
startup, abort and refusal. Retain typed primary touch/pen release activation.

The five overlaps retain capture state/callbacks beside the current App;
Input Controller's empty-pad ownership beside native cold-touch wake; native
primary pen/touch tests beside capture callbacks; both current portal facts
and recording ownership; and the exclusive recording journey. The incoming
legacy busy-journal assertion cannot apply after Capture refuses opening
that journal. The journey still proves refusal, playback continuity, discard,
fresh legal recording, replacement capture commit, exact identity and reload.
The independent main microphone user-language error assertions are retained.

## Declared files

- `.agents/pitfalls/asan-macos-fork-child-stack-depot-boundary.md`
- `.agents/pitfalls/local-audio-proof-inherits-output-device.md`
- `.agents/pitfalls/playwright-evaluation-grants-user-activation.md`
- `.agents/pitfalls/web-project-io-stack-scales-with-project-state.md`
- `.agents/skills/lmdj-release/SKILL.md`
- `.github/workflows/deploy-creator-web.yml`
- `.github/workflows/deploy-web-runtime-host.yml`
- `README.md`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/application-facade.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/application-facade.svg`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/audio-runtime.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/audio-runtime.svg`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/authoring-domain.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/authoring-domain.svg`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/foundation.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/foundation.svg`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/lmdj-core.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/lmdj-core.svg`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/lmdj-product.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/lmdj-product.svg`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/project-cooker.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/project-cooker.svg`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/project-io.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/project-io.svg`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/provider-sdk.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/provider-sdk.svg`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/web-runtime-platform.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/web-runtime-platform.svg`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/application-facade.html`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/application-facade.svg`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/audio-runtime.html`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/audio-runtime.svg`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/authoring-domain.html`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/authoring-domain.svg`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/foundation.html`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/foundation.svg`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/lmdj-core.html`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/lmdj-core.svg`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/lmdj-product.html`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/lmdj-product.svg`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/project-cooker.html`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/project-cooker.svg`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/project-io.html`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/project-io.svg`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/provider-sdk.html`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/provider-sdk.svg`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/web-runtime-platform.html`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/web-runtime-platform.svg`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/assembly/lmdj.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/artifact-audio.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/assembly.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/capability.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/cardputer-transfer.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/error-module-version.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/project-bundle.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/project.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/runtime-snapshot.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/slice-points.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/soundset-catalog.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/contracts/soundset.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/application-facade.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/audio-runtime.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/authoring-domain.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/foundation.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/project-cooker.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/project-io.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/provider-sdk.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/web-runtime-platform.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/history/legacy-patch-architecture.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/hosts/cardputer-host.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/hosts/core-cli.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/hosts/core-mcp.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/hosts/creator-web.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/hosts/native-host.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/hosts/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/hosts/web-runtime.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/operations/creator-changelog.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/operations/documentation-governance.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/operations/runtime-changelog.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/operations/testing-and-proof.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/operations/version-and-release.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/overview/index.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/platform/input.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/platform/native-audio.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/platform/storage.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/platform/web-runtime.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/product/capability-map.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/product/positioning.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/product/workflows.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/providers/local-proof.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/providers/local-sample-slice.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/providers/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/releases/1.0.61.0.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/releases/index.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/assembly/lmdj.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/artifact-audio.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/assembly.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/capability.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/cardputer-transfer.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/error-module-version.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/project-bundle.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/project.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/runtime-snapshot.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/slice-points.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/soundset-catalog.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/contracts/soundset.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/core/modules/application-facade.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/core/modules/audio-runtime.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/core/modules/authoring-domain.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/core/modules/foundation.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/core/modules/project-cooker.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/core/modules/project-io.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/core/modules/provider-sdk.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/core/modules/web-runtime-platform.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/core/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/history/legacy-patch-architecture.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/hosts/cardputer-host.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/hosts/core-cli.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/hosts/core-mcp.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/hosts/creator-web.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/hosts/native-host.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/hosts/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/hosts/web-runtime.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/operations/creator-changelog.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/operations/documentation-governance.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/operations/runtime-changelog.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/operations/testing-and-proof.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/operations/version-and-release.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/overview/index.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/platform/input.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/platform/native-audio.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/platform/storage.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/platform/web-runtime.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/product/capability-map.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/product/positioning.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/product/workflows.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/providers/local-proof.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/providers/local-sample-slice.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/providers/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/releases/1.0.61.0.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/releases/1.0.66.0.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/releases/index.mdx`
- `apps/architecture-portal/versioned_metadata/version-2.0.71.0.json`
- `apps/architecture-portal/versioned_metadata/version-2.0.75.0.json`
- `apps/architecture-portal/versioned_provenance/version-2.0.71.0-squash-witness.json`
- `apps/architecture-portal/versioned_provenance/version-2.0.75.0-squash-witness.json`
- `apps/architecture-portal/versioned_sidebars/version-2.0.71.0-sidebars.json`
- `apps/architecture-portal/versioned_sidebars/version-2.0.75.0-sidebars.json`
- `apps/architecture-portal/versions.json`
- `apps/cardputer-host/CMakeLists.txt`
- `apps/cardputer-host/module.json`
- `apps/core-cli/module.json`
- `apps/core-mcp/lmdj_core_mcp/__init__.py`
- `apps/core-mcp/lmdj_core_mcp/server.py`
- `apps/core-mcp/module.json`
- `apps/core-mcp/pyproject.toml`
- `apps/creator-web/index.html`
- `apps/creator-web/module.json`
- `apps/creator-web/package-lock.json`
- `apps/creator-web/package.json`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/capture_panel.tsx`
- `apps/creator-web/src/components/error_panel.tsx`
- `apps/creator-web/src/components/fx_slider_bank.tsx`
- `apps/creator-web/src/components/long_source_editor.tsx`
- `apps/creator-web/src/components/parameter_slider.tsx`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/project_overview.tsx`
- `apps/creator-web/src/components/project_surface.tsx`
- `apps/creator-web/src/components/recovery_prompt.tsx`
- `apps/creator-web/src/components/sample_controls.tsx`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/components/sequence_overview.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/takeover_panel.tsx`
- `apps/creator-web/src/components/value_slider.tsx`
- `apps/creator-web/src/components/waveform_editor.tsx`
- `apps/creator-web/src/ingest/long_source_ingest.ts`
- `apps/creator-web/src/main.tsx`
- `apps/creator-web/src/runtime/diagnostics_context.tsx`
- `apps/creator-web/src/runtime/project_takeover.ts`
- `apps/creator-web/src/runtime/runtime_context.tsx`
- `apps/creator-web/src/runtime/runtime_types.ts`
- `apps/creator-web/src/runtime/sample_actions.ts`
- `apps/creator-web/src/runtime/tap_tempo.ts`
- `apps/creator-web/src/state/creator_state.ts`
- `apps/creator-web/src/state/error_messages.ts`
- `apps/creator-web/src/state/last_project.ts`
- `apps/creator-web/src/state/perform_state.ts`
- `apps/creator-web/src/state/sample_state.ts`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/audio_lifecycle.test.tsx`
- `apps/creator-web/test/capture_panel.test.tsx`
- `apps/creator-web/test/creator_state.test.ts`
- `apps/creator-web/test/error_messages.test.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/creator-web/test/last_project.test.ts`
- `apps/creator-web/test/long_source_ingest.test.ts`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/project_create.test.tsx`
- `apps/creator-web/test/project_takeover.test.ts`
- `apps/creator-web/test/project_takeover_workspace.test.tsx`
- `apps/creator-web/test/recovery_prompt.test.tsx`
- `apps/creator-web/test/runtime_context.test.tsx`
- `apps/creator-web/test/sample_actions.test.ts`
- `apps/creator-web/test/sample_controls.test.tsx`
- `apps/creator-web/test/sample_state.test.ts`
- `apps/creator-web/test/sequence_surface.test.tsx`
- `apps/creator-web/test/setup.ts`
- `apps/creator-web/test/tap_tempo.test.ts`
- `apps/creator-web/test/value_slider.test.tsx`
- `apps/creator-web/test/waveform_editor.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/docs/assembly/lmdj.mdx`
- `apps/docs-site/docs/contracts/project.mdx`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/hosts/core-mcp.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/operations/creator-changelog.mdx`
- `apps/docs-site/docs/operations/runtime-changelog.mdx`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/docs/product/capability-map.mdx`
- `apps/docs-site/docs/product/workflows.mdx`
- `apps/docs-site/docs/releases/1.0.66.0.mdx`
- `apps/docs-site/docs/releases/index.mdx`
- `apps/docs-site/scripts/lib/snapshot-provenance.mjs`
- `apps/docs-site/test/repo-facts.test.mjs`
- `apps/native-host/module.json`
- `apps/native-host/src/main.cpp`
- `apps/web-runtime-host/module.json`
- `apps/web-runtime-host/src/main.mjs`
- `apps/web-runtime-host/test/cloudflare_deploy_test.py`
- `apps/web-runtime-host/test/cloudflare_host_test.py`
- `apps/web-runtime-host/test/cloudflare_transaction_test.py`
- `apps/web-runtime-host/tools/cloudflare_deploy.py`
- `apps/web-runtime-host/tools/cloudflare_transaction.py`
- `contracts/project/lmdj.project.v5.schema.json`
- `docs/plans/2026-09-30-creator-sample-parity.md`
- `docs/plans/2026-10-01-creator-p1-default-assets.md`
- `docs/plans/2026-10-01-creator-p1-first-use.md`
- `docs/plans/2026-10-01-creator-p1-fixture-transport-ownership.md`
- `docs/plans/2026-10-01-creator-p1-slot-inventory-proof.md`
- `docs/plans/2026-10-01-creator-project-takeover.md`
- `docs/plans/2026-10-01-project-io-web-stack.md`
- `docs/plans/2026-10-02-creator-p1-native-first-touch-proof.md`
- `docs/plans/2026-10-02-creator-p1-owner-loss-fixture-checkpoint.md`
- `docs/plans/2026-10-02-creator-p1-owner-loss-held-press.md`
- `docs/plans/2026-10-02-creator-p1-primary-pointer-proof.md`
- `docs/plans/2026-10-02-creator-p1-streaming-current-main.md`
- `docs/plans/2026-10-02-creator-p1-streaming-parent-convergence.md`
- `docs/plans/2026-10-02-creator-p1-streaming-touch-parent.md`
- `docs/plans/2026-10-02-creator-recovery-prompt-and-error-language.md`
- `docs/plans/2026-10-02-creator-sequence-grid.md`
- `docs/plans/2026-10-02-creator-tempo-metronome.md`
- `docs/plans/2026-10-02-project-io-web-stack-copies.md`
- `docs/prd/decisions/2026-10-01-web-audio-device-start-bound.md`
- `docs/prd/decisions/2026-10-02-creator-tempo-metronome.md`
- `docs/prd/decisions/2026-10-02-sequence-grid-editing.md`
- `docs/prd/questions/web-audio-activation-device-start-budget.md`
- `docs/quality/2026-10-01-sample-playback-parity-acceptance.md`
- `docs/release-evidence/2026-10-01-lmdj-1.0.66.0-promotion-dev.md`
- `docs/release-evidence/changelog-publications.json`
- `docs/release-evidence/release-intents.json`
- `packages/application-facade/CMakeLists.txt`
- `packages/application-facade/include/lmdj/facade/application.hpp`
- `packages/application-facade/module.json`
- `packages/application-facade/src/application.cpp`
- `packages/audio-runtime/module.json`
- `packages/authoring-domain/include/lmdj/domain/project.hpp`
- `packages/authoring-domain/module.json`
- `packages/authoring-domain/src/command_handler.cpp`
- `packages/authoring-domain/src/project.cpp`
- `packages/foundation/include/lmdj/foundation/error.hpp`
- `packages/foundation/src/artifact.cpp`
- `packages/project-cooker/include/lmdj/cooker/project_cooker.hpp`
- `packages/project-cooker/module.json`
- `packages/project-cooker/src/project_cooker.cpp`
- `packages/project-io/CMakeLists.txt`
- `packages/project-io/module.json`
- `packages/project-io/src/project_store.cpp`
- `packages/web-runtime-platform/module.json`
- `packages/web-runtime-platform/src/bridge.cpp`
- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/web-runtime-platform/test/performance_protocol.test.mjs`
- `packages/web-runtime-platform/test/protocol.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `packages/web-runtime-platform/test/source_boundary_test.py`
- `packages/web-runtime-platform/web/protocol.mjs`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `products/lmdj/README.md`
- `products/lmdj/assembly.json`
- `products/lmdj/assembly.lock.json`
- `products/lmdj/generated/web-runtime-identity.json`
- `products/lmdj/generated/web-runtime-identity.mjs`
- `products/lmdj/src/cardputer_assembly.cpp`
- `products/lmdj/src/compiled_assembly.cpp`
- `products/lmdj/version.json`
- `tests/build/creator_web_deploy_workflow_test.py`
- `tests/build/facade_surface_sharding_test.py`
- `tests/build/release_cli_orchestration_test.py`
- `tests/build/release_orchestration_test.py`
- `tests/build/version_test.py`
- `tests/build/web_runtime_deploy_workflow_test.py`
- `tests/conformance/module_graph_test.py`
- `tests/conformance/schema_contract_test.py`
- `tests/core/cooker/project_cooker_test.cpp`
- `tests/core/domain/project_test.cpp`
- `tests/core/facade/performance_gesture_admission_test.cpp`
- `tests/core/facade/performance_operation_contract_test.cpp`
- `tests/core/facade/sample_surface_test.cpp`
- `tests/fixtures/contracts/pad-playback-full.json`
- `tests/fixtures/contracts/project-v5-tone-parity-valid.json`
- `tests/host/mcp_stdio_test.py`
- `tests/host/native_host_source_boundary_test.py`
- `tests/host/performance_cli_test.py`
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- `tests/platform/web/creator/creator_web_capture.spec.mjs`
- `tests/platform/web/creator/creator_web_default_streaming.spec.mjs`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/creator/creator_web_takeover.spec.mjs`
- `tests/platform/web/creator/fixtures/creator_audio.mjs`
- `tests/platform/web/deployment/creator_web_deployment.spec.mjs`
- `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- `tests/platform/web/project_io/project_io_web_test.cpp`
- `tools/release/orchestration.py`
- `docs/plans/2026-10-02-creator-p1-capture-current-parent.md`

## Verification

Run capture/adapter/Input Controller tests, complete Creator units, TypeScript,
staged ownership and full portal before commit. Postcommit verify inherited
snapshot provenance against the introducing actual main parent. Before shipping,
run the committed head's selected batch lanes and current-head review. Native
and packaged capture journeys retain all legs; physical microphone, iPad and
Safari acceptance remains human. No test budget or assertion is reduced and
no new required gate is added.

## Version Management

Version impact: none. Retain actual main Product2.0.75.0, Contract5.2.0 and its
immutable snapshot/witness. T8 settles P1 identities from live reservations.
No allocation, release, tag or Creator deployment in this Task.

Documentation impact: required
Affected portal pages: /hosts/creator-web/, /contracts/project/,
/core/modules/project-io/, /product/workflows/, /assembly/lmdj/,
/operations/testing-and-proof/, /operations/version-and-release/.
Reason: keep both actual current main facts and exclusive recording semantics.
