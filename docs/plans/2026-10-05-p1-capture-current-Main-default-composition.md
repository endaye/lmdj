# P1 Pad capture with current Main and default streaming

Relates to #1664. Compose the actual current default-streaming dependency into
the retained Pad-take implementation. The real ordered parents are
`d7d920aad834105a8abe0710de06a26d33453ae3` and
`2fb618761ee10686e820cf7c6d835f3348ad5dfb`; the latter genuinely contains captured
Main `57f8803599a2eedee0312582971125a3596840f3`. This does not authorize a release,
Creator deployment, new Channel or worktree cleanup.

## Declared files

The following complete incoming index inventory is imported byte-exact from the
second parent. The current Creator portal page and this plan are the only
additional edits. Historical versioned pages, diagrams, metadata and witness
bytes remain exact the genuine captured Main snapshot; no snapshot is rewritten.

- `.agents/pitfalls/batch-key-omits-executed-host-test.md`
- `.agents/pitfalls/hand-copied-identity-pin-drifts.md`
- `.agents/pitfalls/review-input-generated-bytes-exhaust-limit.md`
- `.agents/pitfalls/shared-host-runner-capacity.md`
- `.github/workflows/ci.yml`
- `.github/workflows/pr-review.yml`
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
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/operations/creator-changelog.mdx`
- `apps/docs-site/docs/operations/runtime-changelog.mdx`
- `apps/docs-site/test/repo-facts.test.mjs`
- `apps/native-host/module.json`
- `apps/web-runtime-host/module.json`
- `docs/README.md`
- `docs/deploy/esp32-firmware.md`
- `docs/plans/2026-09-09-esp32-firmware-handbook.md`
- `docs/plans/2026-10-04-batch-lane-input-closure.md`
- `docs/plans/2026-10-04-p1-default-main82-composition.md`
- `docs/plans/2026-10-04-p1-offline-main82-composition.md`
- `docs/plans/2026-10-04-p1-slot-latest-main-input-closure.md`
- `docs/plans/2026-10-04-p1-slot-latest-main-prd-composition.md`
- `docs/plans/2026-10-04-p1-slot-main82-version-composition.md`
- `docs/plans/2026-10-04-p1-slot-main82-witness-composition.md`
- `docs/plans/2026-10-05-esp32-firmware-handbook-recovery.md`
- `docs/plans/2026-10-05-p1-capture-current-Main-default-composition.md`
- `docs/plans/2026-10-05-p1-default-current-Main-handbook-composition.md`
- `docs/plans/2026-10-05-p1-default-current-T2-review-tooling-composition.md`
- `docs/plans/2026-10-05-p1-default-offline-inventory-portal-composition.md`
- `docs/plans/2026-10-05-p1-offline-inventory-portal-boundary.md`
- `docs/plans/2026-10-05-p1-slot-main-handbook-composition.md`
- `docs/plans/2026-10-05-p1-slot-main-portal-provenance-composition.md`
- `docs/plans/2026-10-05-p1-slot-main-review-artifact-composition.md`
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
- `scripts/ci/review_wait.py`
- `tests/build/ci_build_acceleration_test.py`
- `tests/build/ci_local_preflight_test.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `tests/build/ci_review_wait_test.py`
- `tests/build/version_test.py`
- `tests/conformance/module_graph_test.py`
- `tests/host/native_host_source_boundary_test.py`

## Behavior and verification

Keep the actual reviewed R23 Workspace-owned Pad controller, original Project,
Pad, buffer and per-take callback generation. Runtime replacement still joins
permission/startup/source cleanup and admitted saves before closing its Session.
Only explicit Save uses a current ready Session for the original Project and
empty target. Keep the default streaming controller's continuous target ownership,
terminal journal, original command recovery and capture admission barrier.
The complete Creator source, component tests and packaged browser journeys are
byte-exact the first parent. The dependency imports current IO/Facade/Platform,
Assembly, review tooling and their own strict tests through the real merge.

Resolve independent documentation finding F1 in the current Creator page: saved
Performance replay and recovery remain available, while internal playback uses
native empty-Pad capture and explicit interrupted-take Save/Discard. The page
must no longer promise removed manual start/end-frame resample controls.

Lowest Task verification is the complete unchanged Creator component suite and
TypeScript/Vite build against the composed manifests, followed by staged path
ownership, whitespace and the complete official Portal check. The first normal Portal
producer used actual first-parent HEAD and second-parent MERGE_HEAD and refused
release-document provenance because the inherited snapshot is not yet present
at that precommit HEAD. Its whole raw/exit remains retained. The next normal
producer starts at the genuine dependency HEAD, merges the genuine first parent,
and stages these exact two additional edits. Its complete index and actual
files must equal this Task's final tree, with both real parent objects and
captured Main present. This validates the existing snapshot through real Git
history without inventing a private implementation commit. After committing the
Task with its original ordered parents, rerun the complete original Portal on
that actual committed Source before push; retain both preceding observations.

Complete committed-head selected batch-only inputs, independent current-head
review, live conversations/conflicts/protection and guarded shipping remain
separate requirements. Preserve every original raw failure and every unchanged
journey leg, timeout and coverage floor. Task/component or automated browser
results do not establish trusted Safari/iPad/MIDI, audible microphone/master
capture or installed-browser offline lifecycle acceptance.

## Version Management

Version impact: carries existing Module/Host/Product identities and the immutable
snapshot already allocated on actual captured Main. Every imported manifest,
generated identity, versioned page, diagram, metadata and witness is byte-exact
the incoming genuine dependency. This Task allocates no identity, rewrites no
historical snapshot and makes no release or deployment. P1's coordinated T8
IO/Facade/Platform and offline Creator Host version settlement, new candidate
Build and matching immutable snapshot remain outstanding.

## Documentation impact

Documentation impact: required — current `/hosts/creator-web/` corrects F1;
`/assembly/lmdj/`, `/core/modules/web-runtime-platform/`,
`/operations/creator-changelog/` and `/operations/runtime-changelog/` retain the
real current Main/default/offline dependency facts. Their imported Source and
all frozen snapshots remain authentic; run the original whole Portal check.
