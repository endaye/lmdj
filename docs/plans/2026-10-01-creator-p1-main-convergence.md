# P1 convergence with concurrent main

Retain main's inactive-audio Sample mutations and takeover proof without an
artificial wake, release evidence, snapshot squash witnesses and settled Module
identities. P1 adds per-slot acquisition, first-input audio and the new Creator
workflow to those already allocated components; derive additional MINOR versions
for Project I/O, Facade and Web Runtime Platform from main's manifests. Derive
consumer PATCH versions from main, and Creator PATCH from the retained P1
candidate. Generate exact Assembly pins, lock, compiled sources and Runtime
identity through version tooling.

## Immutable snapshot reconciliation

Concurrent branches both allocated 2.0.71.0. Main's protected integration
snapshot is authoritative and remains byte-identical, including its squash
witness. The superseded unpublished P1 snapshot remains in its original Git
commit b78a536616f037e6e79ee80cfc21b6b484394b30 and is not substituted for main's
snapshot. Preserve P1 2.0.72.0 and 2.0.73.0 byte-identically. Derive the next
unused BUILD from the retained P1 candidate and check live tags and intents;
freeze its snapshot from clean committed source. No release or deployment.

## Declared files and verification

The exact merge-resolution inventory is listed below. Verification: full Creator
components and TypeScript, strict version and graph fixtures, scope classifier,
unchanged immutable snapshot comparisons, and current portal checks. A clean
committed source is a prerequisite for the new snapshot; retain the expected
missing-snapshot check before freezing, then rerun the complete portal check.
Rerun complete selected Host/Core/ASan/coverage and batch proofs against the
converged candidate; prior source passes remain prior source evidence.

- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/web-runtime-platform.html`
- `apps/architecture-portal/static/versions/2.0.71.0/diagrams/web-runtime-platform.svg`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/assembly/lmdj.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/application-facade.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/project-io.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/core/modules/web-runtime-platform.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/hosts/creator-web.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/operations/creator-changelog.mdx`
- `apps/architecture-portal/versioned_docs/version-2.0.71.0/platform/web-runtime.mdx`
- `apps/architecture-portal/versioned_metadata/version-2.0.71.0.json`
- `apps/architecture-portal/versioned_provenance/version-2.0.71.0-squash-witness.json`
- `apps/cardputer-host/CMakeLists.txt`
- `apps/cardputer-host/module.json`
- `apps/core-cli/module.json`
- `apps/core-mcp/lmdj_core_mcp/__init__.py`
- `apps/core-mcp/module.json`
- `apps/core-mcp/pyproject.toml`
- `apps/creator-web/module.json`
- `apps/creator-web/package-lock.json`
- `apps/creator-web/package.json`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/docs/assembly/lmdj.mdx`
- `apps/docs-site/docs/operations/creator-changelog.mdx`
- `apps/docs-site/docs/releases/1.0.66.0.mdx`
- `apps/docs-site/docs/releases/index.mdx`
- `apps/docs-site/scripts/lib/snapshot-provenance.mjs`
- `apps/docs-site/test/repo-facts.test.mjs`
- `apps/native-host/module.json`
- `apps/web-runtime-host/module.json`
- `docs/plans/2026-09-30-creator-sample-parity.md`
- `docs/release-evidence/changelog-publications.json`
- `docs/release-evidence/release-intents.json`
- `packages/application-facade/module.json`
- `packages/audio-runtime/module.json`
- `packages/authoring-domain/module.json`
- `packages/project-cooker/module.json`
- `packages/project-io/module.json`
- `packages/web-runtime-platform/module.json`
- `products/lmdj/assembly.json`
- `products/lmdj/assembly.lock.json`
- `products/lmdj/generated/web-runtime-identity.json`
- `products/lmdj/generated/web-runtime-identity.mjs`
- `products/lmdj/src/cardputer_assembly.cpp`
- `products/lmdj/src/compiled_assembly.cpp`
- `products/lmdj/version.json`
- `tests/build/version_test.py`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/creator/creator_web_takeover.spec.mjs`
- `docs/plans/2026-10-01-creator-p1-main-convergence.md`

- `apps/architecture-portal/versions.json`
- `tests/conformance/module_graph_test.py`
- `tests/host/native_host_source_boundary_test.py`

- `apps/docs-site/docs/operations/runtime-changelog.mdx`

## Version Management

Version impact: required. Product BUILD advances from the retained P1 candidate;
component versions derive from authoritative manifests as described above. Failed
and superseded Build numbers are never reused. Portal identities are generated.

Documentation impact: required
Reason: retained concurrent Module identities and combined P1 behavior change the
current Assembly and documented source facts.
Affected portal pages: /hosts/creator-web/ /assembly/lmdj/ /core/modules/project-io/ /core/modules/application-facade/ /core/modules/web-runtime-platform/
