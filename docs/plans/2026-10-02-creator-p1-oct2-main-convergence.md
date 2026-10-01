# P1 convergence with concurrent main on October 2

Retain main e4e17e7fc916017a8e71964527ce8d960fe1e778 and the P1 native touch/capture fixes.
Keep the new interrupted-recording prompt outside the creative page container,
with diagnostics still in System. Preserve heap-owned Project IO state and adapt
the P1 empty-slot guard to the same ownership. Current documentation combines
exclusive recording owners with the native owner-loss recovery already on main.

## Declared files and verification

- `.agents/pitfalls/asan-macos-fork-child-stack-depot-boundary.md`
- `.agents/pitfalls/web-project-io-stack-scales-with-project-state.md`
- `.github/workflows/deploy-creator-web.yml`
- `.github/workflows/deploy-web-runtime-host.yml`
- `README.md`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/recovery_prompt.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/recovery_prompt.test.tsx`
- `apps/creator-web/test/sequence_surface.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `apps/docs-site/docs/product/workflows.mdx`
- `apps/web-runtime-host/test/cloudflare_deploy_test.py`
- `apps/web-runtime-host/test/cloudflare_host_test.py`
- `apps/web-runtime-host/test/cloudflare_transaction_test.py`
- `apps/web-runtime-host/tools/cloudflare_deploy.py`
- `apps/web-runtime-host/tools/cloudflare_transaction.py`
- `docs/plans/2026-10-01-project-io-web-stack.md`
- `docs/plans/2026-10-02-creator-recovery-prompt-and-error-language.md`
- `docs/plans/2026-10-02-creator-sequence-grid.md`
- `docs/prd/decisions/2026-10-02-sequence-grid-editing.md`
- `packages/foundation/include/lmdj/foundation/error.hpp`
- `packages/foundation/src/artifact.cpp`
- `packages/project-io/CMakeLists.txt`
- `packages/project-io/src/project_store.cpp`
- `products/lmdj/README.md`
- `tests/build/creator_web_deploy_workflow_test.py`
- `tests/build/web_runtime_deploy_workflow_test.py`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/deployment/creator_web_deployment.spec.mjs`
- `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- `tests/platform/web/project_io/project_io_web_test.cpp`
- `docs/plans/2026-10-02-creator-p1-oct2-main-convergence.md`

Run full Creator unit tests and TypeScript, native Project IO and Facade
Sound Set/empty-target tests plus the staged scope check. Run the complete
portal gate for current documentation. Retain all incoming recovery, Sequence
editing decision, stack-headroom, deployment smoke and raw-byte verification
journey legs. Final committed-candidate packaged lanes and independent review
remain required after version settlement.

## Version Management

Version impact: included in the next coordinated P1 Product Build and Creator
PATCH; preserve current main manifest versions and the published 2.0.71.0
snapshot and squash witness. This convergence allocates no identity.

Documentation impact: required
Affected portal pages: /hosts/creator-web/, /core/modules/project-io/,
/operations/version-and-release/ and /product/workflows/.
Reason: combine current main facts with P1 behavior without losing either.
