# P1 offline shell with current Main and slot acquisition

## Problem and Task

The offline candidate retains the seven-role favicon inventory and its
Native current/future manifest boundary, but its dependency head predates
current Main and T2. Compose the actual current T2 commit `b5e9fd3d2b8c6cbdac6fecdaa5185b7e6cd74746`
(which contains captured protected Main `f06581c2fe27d2171c5b7d64afd3a3240d4bbc99`)
with offline head `dd4cbbf45199896fda1b86b0d5f1ef015888ec59` in this isolated worktree.
The real merge-tree has no conflicts; all automatic changes are declared below.
Preserve every original offline cache/install/update, per-Pad acquisition,
first-gesture, receipt/lifecycle assertion and current Main identity/snapshot.
No dependency is represented as merged until it actually reaches protected Main.

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

These are exact automatic imports, with no additional Product logic repair.
The Main settings-update Runtime revision fix is imported unchanged. Historical
failed Sample playback/tone journeys remain negative evidence; importing this
fix does not establish their cause or prove either journey now passes.

## Verification

Inspect the actual complete staged inventory and original own-source retention.
Run the complete Creator component suite and TypeScript/Vite build, original
Platform suite, Worker cache graph suite, Creator package and historical-role
parity, version/dependency checks, staged path ownership, and official full
Portal check against this entire composition. These checks catch an incompatible
source combination, broken complete-cache/inventory admission, identity drift,
unowned imports and changed documented facts. Keep all budgets, selection and
journey legs. Run original packaged Sample and offline journeys on the rebuilt
committed artifact; retain every original failure and far-side assertion.

After the Conventional merge commit, derive canonical keys using this Source's
production classifier and actual captured Main base. Complete every selected
batch-only producer and fresh complete current-head review before guarded
shipping. Prior lane keys, reviews and owner adoptions do not approve this head.
T2's actual protected merge remains a shipping dependency. Browser fixture
passes cannot replace trusted physical Safari/iPad/MIDI, hearing or installed
browser acceptance.

## Version Management

Version impact: none for this composition. Existing active identities and the
immutable snapshot are exact imports from captured Main; no Build is allocated
and no historic identity or snapshot is rewritten. P1's coordinated Module
MINORs and further Creator offline-inventory MAJOR, with a new Product Build
and immutable testing snapshot, remain T8. No release, deployment, publication
or Channel promotion occurs.

Documentation impact: required. Preserve current Main additions to
`/core/modules/web-runtime-platform/`, `/assembly/lmdj/`,
`/operations/creator-changelog/` and `/operations/runtime-changelog/` together
with existing Creator offline facts. Run the official full Portal check. The
imported current identity projections derive from active manifests.
