# P1 default streaming with current Main and offline recovery

## Problem and Task

Default Bank A streaming currently contains the earlier offline candidate.
Compose its exact head `e2684085fccf09044d4d63b2df946c0e10b4a9c6` with actual offline
commit `89b3bcf6936489ed98c2239240ea7ff21ca5b662`, which retains captured protected
Main `f06581c2fe27d2171c5b7d64afd3a3240d4bbc99` and the current T2 slot dependency.
Use a real no-rewrite dual-parent merge in this isolated short-lived worktree.
The inspected real merge-tree has no conflicts. Preserve the exact default
controller's continuously owning receipt admission, first-auto-Project scope,
per-slot progressive publication, durable user edits and all offline boundaries.
Dependency imports are local candidates; T2 and T4 must actually reach protected
Main before this PR ships. Existing negative and older-head evidence remains
historical; none preapproves this changed Source.

## Declared files

The complete automatic first-parent import inventory is:

- `.agents/pitfalls/batch-key-omits-executed-host-test.md`
- `.agents/pitfalls/hand-copied-identity-pin-drifts.md`
- `.agents/pitfalls/shared-host-runner-capacity.md`
- `.github/workflows/ci.yml`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/application-facade.html`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/application-facade.svg`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/audio-runtime.html`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/audio-runtime.svg`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/authoring-domain.html`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/authoring-domain.svg`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/foundation.html`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/foundation.svg`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/lmdj-core.html`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/lmdj-core.svg`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/lmdj-product.html`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/lmdj-product.svg`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/project-cooker.html`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/project-cooker.svg`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/project-io.html`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/project-io.svg`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/provider-sdk.html`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/provider-sdk.svg`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/web-runtime-platform.html`
- `apps/architecture-portal/static/versions/2.0.82.0/diagrams/web-runtime-platform.svg`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/assembly/lmdj.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/artifact-audio.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/assembly.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/capability.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/cardputer-transfer.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/error-module-version.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/project-bundle.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/project.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/runtime-snapshot.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/slice-points.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/soundset-catalog.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/contracts/soundset.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/core/modules/application-facade.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/core/modules/audio-runtime.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/core/modules/authoring-domain.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/core/modules/foundation.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/core/modules/project-cooker.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/core/modules/project-io.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/core/modules/provider-sdk.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/core/modules/web-runtime-platform.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/core/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/history/legacy-patch-architecture.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/hosts/cardputer-host.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/hosts/core-cli.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/hosts/core-mcp.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/hosts/creator-web.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/hosts/native-host.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/hosts/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/hosts/web-runtime.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/operations/creator-changelog.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/operations/documentation-governance.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/operations/runtime-changelog.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/operations/testing-and-proof.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/operations/version-and-release.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/overview/index.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/platform/input.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/platform/native-audio.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/platform/storage.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/platform/web-runtime.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/product/capability-map.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/product/positioning.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/product/workflows.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/providers/local-proof-stem.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/providers/local-proof.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/providers/local-sample-slice.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/providers/overview.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/releases/1.0.61.0.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/releases/1.0.66.0.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.82.0/releases/index.mdx`
- `apps/architecture-portal/versioned_metadata/version-2.0.82.0.json`
- `apps/architecture-portal/versioned_provenance/version-2.0.82.0-squash-witness.json`
- `apps/architecture-portal/versioned_sidebars/version-2.0.82.0-sidebars.json`
- `apps/architecture-portal/versions.json`
- `apps/cardputer-host/CMakeLists.txt`
- `apps/cardputer-host/module.json`
- `apps/core-cli/module.json`
- `apps/core-mcp/lmdj_core_mcp/__init__.py`
- `apps/core-mcp/module.json`
- `apps/core-mcp/pyproject.toml`
- `apps/creator-web/module.json`
- `apps/creator-web/package-lock.json`
- `apps/creator-web/package.json`
- `apps/docs-site/docs/assembly/lmdj.mdx`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/operations/creator-changelog.mdx`
- `apps/docs-site/docs/operations/runtime-changelog.mdx`
- `apps/docs-site/test/repo-facts.test.mjs`
- `apps/native-host/module.json`
- `apps/web-runtime-host/module.json`
- `docs/plans/2026-10-04-batch-lane-input-closure.md`
- `docs/plans/2026-10-04-p1-offline-main82-composition.md`
- `docs/plans/2026-10-04-p1-slot-latest-main-input-closure.md`
- `docs/plans/2026-10-04-p1-slot-latest-main-prd-composition.md`
- `docs/plans/2026-10-04-p1-slot-main82-version-composition.md`
- `docs/plans/2026-10-04-p1-slot-main82-witness-composition.md`
- `docs/prd/decisions/2026-10-04-sequence-hardware-ui-revision.md`
- `docs/prd/questions/hardware-control-mapping.md`
- `docs/prd/questions/pad-colour-source.md`
- `docs/prd/questions/pattern-length-change-and-copy.md`
- `packages/application-facade/module.json`
- `packages/audio-runtime/module.json`
- `packages/project-cooker/module.json`
- `packages/project-io/module.json`
- `packages/web-runtime-platform/module.json`
- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `products/lmdj/assembly.json`
- `products/lmdj/assembly.lock.json`
- `products/lmdj/generated/web-runtime-identity.json`
- `products/lmdj/generated/web-runtime-identity.mjs`
- `products/lmdj/src/cardputer_assembly.cpp`
- `products/lmdj/src/compiled_assembly.cpp`
- `products/lmdj/version.json`
- `scripts/ci/local_preflight.py`
- `tests/build/ci_build_acceleration_test.py`
- `tests/build/ci_local_preflight_test.py`
- `tests/build/version_test.py`
- `tests/conformance/module_graph_test.py`
- `tests/host/native_host_source_boundary_test.py`

- this plan

This Task adds no Product logic. All original default-streaming App/controller,
state/journal, Pad, input and packaged journey bytes must remain exact. Preserve
incoming current Main identity, immutable snapshot, Runtime settings repair,
classifier whole-input closure and offline Native/Worker implementations.

## Verification

Verify the declared stage and both sides' exact source retention. Run complete
Creator components and TypeScript/Vite, full Platform components, default seed
cases within that complete Creator suite, original Worker/package/role suites,
version/graph checks and staged ownership. Run the original full official Portal
against a private normal checkout of the exact staged tree with its legitimate
ordered parents; that verification identity is not the implementation head.
These checks catch state/UI inheritance loss, incompatible offline inventory,
identity drift, unowned files and incorrect current documented facts. Retain all
assertions, scopes, budgets and negatives. Then make the actual Conventional
merge commit, inspect its exact parents/files/clean status, and derive canonical
lane keys from that committed Source and captured Main.

Complete original current-input producers for every selected batch obligation,
packaged default/Project/lifecycle journeys and fresh complete independent review
before protected merge. Older actual producer results remain bound to their own
Source/input identity; they cannot be presented as new-head executions. Physical
Safari/iPad/MIDI, mic/master hearing and formal installed-browser offline rows
remain separate unverified acceptance.

## Version Management

Version impact: none. This composition imports existing active manifests and
the immutable current Main snapshot unchanged; no Product Build, Module/Host
identity or historic snapshot is allocated or rewritten. Coordinated P1 API
MINORs, further Creator offline inventory MAJOR and a new Product Build with
immutable canary snapshot remain T8. No publication, release, deployment or
Channel promotion occurs.

Documentation impact: required. Preserve current Main updates to
`/assembly/lmdj/`, `/core/modules/web-runtime-platform/`,
`/operations/creator-changelog/` and `/operations/runtime-changelog/` alongside
the current Creator default streaming and offline ownership facts. All identity
projections derive from active manifests; run the full official Portal check.
