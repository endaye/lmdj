# Per-slot acquisition converges with current main

Merge main 1e0e1293 into verified fixture head 4dee2545. Preserve independent
slot acquisition, strict Facade-eight/native-five inventory and the complete
crash/reopen journeys. Reconcile the one ProjectStore conflict by retaining
empty-target collision/replay checks with main heap-owned loaded state. Keep
main Web stack headroom, recovery prompts, shell and persisted snapshot bytes.

## Declared files and verification

- `.agents/pitfalls/asan-macos-fork-child-stack-depot-boundary.md`
- `.agents/pitfalls/local-audio-proof-inherits-output-device.md`
- `.agents/pitfalls/web-project-io-stack-scales-with-project-state.md`
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
- `apps/architecture-portal/versioned_metadata/version-2.0.71.0.json`
- `apps/architecture-portal/versioned_provenance/version-2.0.71.0-squash-witness.json`
- `apps/architecture-portal/versioned_sidebars/version-2.0.71.0-sidebars.json`
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
- `apps/creator-web/src/components/error_panel.tsx`
- `apps/creator-web/src/components/parameter_slider.tsx`
- `apps/creator-web/src/components/recovery_prompt.tsx`
- `apps/creator-web/src/components/sample_controls.tsx`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/takeover_panel.tsx`
- `apps/creator-web/src/components/waveform_editor.tsx`
- `apps/creator-web/src/main.tsx`
- `apps/creator-web/src/runtime/project_takeover.ts`
- `apps/creator-web/src/runtime/runtime_context.tsx`
- `apps/creator-web/src/runtime/runtime_types.ts`
- `apps/creator-web/src/state/last_project.ts`
- `apps/creator-web/src/state/sample_state.ts`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/audio_lifecycle.test.tsx`
- `apps/creator-web/test/creator_state.test.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/creator-web/test/last_project.test.ts`
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
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/docs/product/capability-map.mdx`
- `apps/docs-site/docs/product/workflows.mdx`
- `apps/docs-site/docs/releases/1.0.66.0.mdx`
- `apps/docs-site/docs/releases/index.mdx`
- `apps/docs-site/scripts/lib/snapshot-provenance.mjs`
- `apps/docs-site/test/repo-facts.test.mjs`
- `apps/native-host/module.json`
- `apps/web-runtime-host/module.json`
- `apps/web-runtime-host/test/cloudflare_deploy_test.py`
- `apps/web-runtime-host/test/cloudflare_host_test.py`
- `apps/web-runtime-host/test/cloudflare_transaction_test.py`
- `apps/web-runtime-host/tools/cloudflare_deploy.py`
- `apps/web-runtime-host/tools/cloudflare_transaction.py`
- `docs/plans/2026-09-30-creator-sample-parity.md`
- `docs/plans/2026-10-01-creator-project-takeover.md`
- `docs/plans/2026-10-01-project-io-web-stack.md`
- `docs/plans/2026-10-02-creator-p1-slot-main-convergence.md`
- `docs/plans/2026-10-02-creator-recovery-prompt-and-error-language.md`
- `docs/plans/2026-10-02-creator-sequence-grid.md`
- `docs/plans/2026-10-02-creator-tempo-metronome.md`
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
- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/web-runtime-platform/test/protocol.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `packages/web-runtime-platform/web/protocol.mjs`
- `packages/web-runtime-platform/web/runtime_session.mjs`
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
- `tests/build/version_test.py`
- `tests/build/web_runtime_deploy_workflow_test.py`
- `tests/conformance/module_graph_test.py`
- `tests/core/cooker/project_cooker_test.cpp`
- `tests/core/domain/project_test.cpp`
- `tests/core/facade/sample_surface_test.cpp`
- `tests/fixtures/contracts/pad-playback-full.json`
- `tests/host/mcp_stdio_test.py`
- `tests/host/native_host_source_boundary_test.py`
- `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/creator/creator_web_takeover.spec.mjs`
- `tests/platform/web/deployment/creator_web_deployment.spec.mjs`
- `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- `tests/platform/web/project_io/project_io_web_test.cpp`

Run complete Creator units, TypeScript, scope ownership, current portal and
stable native configure/build plus the Sound Set, Project Store and Facade
component tests before commit. Recompute all selected lane keys and validate
all changed inputs on the clean committed head. Retain prior full and reduced
Runtime negatives; only a new complete pass settles the lane.

## Version Management

Version impact: none. Preserve main identities and settle compatible API debt
only in the approved coordinated P1 T8 candidate. No release or deployment.

Documentation impact: required
Affected portal routes: /core/modules/project-io/ /core/modules/application-facade/
/core/modules/web-runtime-platform/ /hosts/creator-web/ /operations/version-and-release/
/product/workflows/. Reason: retain current main source facts and per-slot APIs.

## Imported snapshot verification boundary

The precommit portal check authenticates all current tests, pages and diagrams.
The incoming main snapshot cannot resolve its introduction until the merge
commit makes that parent part of HEAD. Retain that exact precommit refusal;
a complete postcommit portal pass is mandatory before push or shipping.
