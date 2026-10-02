# T3 retains the current main source

Adopt actual main f73980bd4a6269ba0cb6e2c0ddd9312814c93d5c into the existing
p1-default-assets-main Task. Automatic merging required no conflict resolution. Preserve
main Tempo controls, FX gestures, stage layout, user-language errors, recovery
prompt and heap-owned Project I/O. Preserve this Task's original corpus/Worker
or offline-cache assertions and fixtures. No P1 streaming/capture/System
implementation is introduced by this convergence.

## Declared files

- `.agents/pitfalls/asan-macos-fork-child-stack-depot-boundary.md`
- `.agents/pitfalls/web-project-io-stack-scales-with-project-state.md`
- `.agents/skills/lmdj-release/SKILL.md`
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
- `apps/architecture-portal/versioned_metadata/version-2.0.75.0.json`
- `apps/architecture-portal/versioned_provenance/version-2.0.75.0-squash-witness.json`
- `apps/architecture-portal/versioned_sidebars/version-2.0.75.0-sidebars.json`
- `apps/architecture-portal/versions.json`
- `apps/cardputer-host/CMakeLists.txt`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/capture_panel.tsx`
- `apps/creator-web/src/components/error_panel.tsx`
- `apps/creator-web/src/components/fx_slider_bank.tsx`
- `apps/creator-web/src/components/long_source_editor.tsx`
- `apps/creator-web/src/components/parameter_slider.tsx`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/project_overview.tsx`
- `apps/creator-web/src/components/project_surface.tsx`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/components/sequence_overview.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/value_slider.tsx`
- `apps/creator-web/src/ingest/long_source_ingest.ts`
- `apps/creator-web/src/runtime/diagnostics_context.tsx`
- `apps/creator-web/src/runtime/sample_actions.ts`
- `apps/creator-web/src/runtime/tap_tempo.ts`
- `apps/creator-web/src/state/creator_state.ts`
- `apps/creator-web/src/state/error_messages.ts`
- `apps/creator-web/src/state/perform_state.ts`
- `apps/creator-web/src/state/sample_state.ts`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/audio_lifecycle.test.tsx`
- `apps/creator-web/test/capture_panel.test.tsx`
- `apps/creator-web/test/creator_state.test.ts`
- `apps/creator-web/test/error_messages.test.ts`
- `apps/creator-web/test/long_source_ingest.test.ts`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/project_create.test.tsx`
- `apps/creator-web/test/sample_actions.test.ts`
- `apps/creator-web/test/sample_state.test.ts`
- `apps/creator-web/test/sequence_surface.test.tsx`
- `apps/creator-web/test/tap_tempo.test.ts`
- `apps/creator-web/test/value_slider.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/docs/assembly/lmdj.mdx`
- `apps/docs-site/docs/contracts/project.mdx`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `apps/native-host/src/main.cpp`
- `apps/web-runtime-host/src/main.mjs`
- `contracts/project/lmdj.project.v5.schema.json`
- `docs/plans/2026-09-30-creator-sample-parity.md`
- `docs/plans/2026-10-02-creator-recovery-prompt-and-error-language.md`
- `docs/plans/2026-10-02-project-io-web-stack-copies.md`
- `packages/application-facade/src/application.cpp`
- `packages/authoring-domain/src/command_handler.cpp`
- `packages/authoring-domain/src/project.cpp`
- `packages/foundation/include/lmdj/foundation/error.hpp`
- `packages/project-io/src/project_store.cpp`
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
- `products/lmdj/assembly.json`
- `products/lmdj/assembly.lock.json`
- `products/lmdj/generated/web-runtime-identity.json`
- `products/lmdj/generated/web-runtime-identity.mjs`
- `products/lmdj/src/cardputer_assembly.cpp`
- `products/lmdj/src/compiled_assembly.cpp`
- `products/lmdj/version.json`
- `tests/build/release_cli_orchestration_test.py`
- `tests/build/release_orchestration_test.py`
- `tests/build/version_test.py`
- `tests/conformance/schema_contract_test.py`
- `tests/core/facade/performance_gesture_admission_test.cpp`
- `tests/core/facade/performance_operation_contract_test.cpp`
- `tests/fixtures/contracts/project-v5-tone-parity-valid.json`
- `tests/host/performance_cli_test.py`
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- `tests/platform/web/creator/creator_web_capture.spec.mjs`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/project_io/project_io_web_test.cpp`
- `tools/release/orchestration.py`
- `docs/plans/2026-10-02-creator-p1-t3-current-main.md`

## Verification

Run complete Creator units, TypeScript, staged scope ownership and the full
portal. T3 additionally checks deterministic assets/rights/schema and Worker
security. Postcommit portal validates inherited immutable metadata on its
actual introducing main parent. Before shipping, run each own committed-head
selected batch lane and current-head review. Keep historical negative logs;
no assertions or budgets are reduced and no new required gate is introduced.

## Version Management

Version impact: none. Inherit actual main Product 2.0.75.0 and Project Contract
5.2.0; retain its immutable snapshot and squash witness unchanged. No new
allocation, release, tag or Creator deployment. Coordinated P1 identity debt
is settled only in T8 from live manifests and reservations.

Documentation impact: required
Affected portal pages: /hosts/creator-web/, /contracts/project/,
/core/modules/project-io/, /product/workflows/, /assembly/lmdj/,
/operations/testing-and-proof/, /operations/version-and-release/.
Reason: retain actual main documented source facts with this Task's existing
first-use facts. Incoming snapshot files are immutable historical evidence.
