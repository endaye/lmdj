# P1 offline bootstrap and current audio clock

The current offline branch has a real content conflict with protected Main in
Creator bootstrap: offline-shell registration and retained AudioContext clock
both add an import at the same location. Preserve both imports and retain the
actual combined bootstrap, including the clock factory seam and offline-shell
registration. Start this convergence from the inspected Main; retain every Main
blob except the explicitly declared existing offline Task files below. This
resolves a real conflict, and introduces no strict-update requirement.

## Task scope and verification

Declared files:
- `apps/creator-web/offline/worker.mjs`
- `apps/creator-web/offline/worker.node-test.mjs`
- `apps/creator-web/src/main.tsx`
- `apps/creator-web/src/runtime/offline_shell.ts`
- `apps/creator-web/test/offline_shell.test.ts`
- `apps/creator-web/test/package_test.py`
- `apps/creator-web/tools/package.py`
- `apps/docs-site/diagrams/web-runtime-platform.architecture.json`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/static/diagrams/web-runtime-platform.html`
- `apps/docs-site/static/diagrams/web-runtime-platform.svg`
- `apps/web-runtime-host/test/manifest_asset_role_parity_test.py`
- `apps/web-runtime-host/tools/asset_roles.py`
- `apps/web-runtime-host/tools/cloudflare_headers.py`
- `apps/web-runtime-host/tools/deployment_smoke.py`
- `docs/plans/2026-10-01-creator-p1-offline-shell.md`
- `docs/plans/2026-10-02-creator-p1-offline-main-convergence.md`
- `docs/plans/2026-10-02-creator-p1-offline-platform-layout.md`
- `docs/plans/2026-10-02-creator-p1-t4-current-main.md`
- `docs/plans/2026-10-03-p1-offline-synthetic-lifecycle-state.md`
- `packages/web-runtime-platform/src/manifest_gate.cpp`
- `packages/web-runtime-platform/test/manifest_gate_test.cpp`
- `scripts/creator-web.sh`
- `tests/platform/web/creator/creator_web_offline.spec.mjs`
- `tools/web-runtime/serve_distribution.py`
- `docs/plans/2026-10-03-p1-offline-bootstrap-current-main.md`

Lowest-tier checks: complete Creator units and TypeScript, Web Platform JavaScript
units, the standalone offline Worker tests and packaging/role parity tests.
The Creator bootstrap build catches an unresolved or missing import; the Worker
and inventory regressions retain exact identity/digest/origin admission. Run
ownership, whitespace and current portal checks before commit. After commit,
classify exact inputs again and complete every selected batch-only obligation,
retaining old negative and interrupted observations as historical evidence.

## Version Management

Version impact: none. The convergence inherits actual Main manifests and makes
no new Product, Host, Module, Provider or Contract allocation. Offline seven-role
activation remains the existing coordinated T8 Creator MAJOR obligation; a
legacy inventory is not offline acceptance.

Documentation impact: required. Existing offline Task facts remain on portal
routes /hosts/creator-web, /platform/web-runtime and
/core/modules/web-runtime-platform and their source diagram. Verify current
pages and derived identities through the stable portal check; retain immutable
Main snapshots without editing frozen metadata.
