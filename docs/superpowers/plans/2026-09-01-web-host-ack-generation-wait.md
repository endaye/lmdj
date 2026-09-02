# Web Runtime Host Acknowledgement Wait Implementation Plan

**Issue:** #310
**Authority:** existing packaged Web Runtime Host browser proof and the
asynchronous AudioWorklet acknowledgement contract already used by recovery
readiness and PR #294's release-response barrier.

## Outcome

The 44.1 kHz Snapshot acceptance path in
`tests/platform/web/host/web_runtime_host_browser.spec.mjs` waits for
`host.status.acknowledged_generation` to equal the published Snapshot
generation instead of sampling it once. A timeout is a test failure that names
the last observed `control_generation` / `acknowledged_generation` pair. A
Snapshot that is never acknowledged still fails.

## File audit

Immediate `acknowledged_generation` reads after a publishing call in this spec:

| Site | After | Current behaviour |
| --- | --- | --- |
| 44.1 kHz Snapshot acceptance | `snapshot.reload` | samples `host.status` once — this Task |
| `waitForRecoveryReadiness` | visibility recovery | already polls until generations match |
| 48 kHz republish | `snapshot.reload` | does not read `acknowledged_generation` |
| Stage 9 reload-visible truth | `snapshot.reload` | does not read `acknowledged_generation` |
| WebKit status | none | asserts `state` only |

The class of immediate post-publish acknowledgement samples is this one site.

## Implementation

1. Add `waitForAcknowledgedGeneration(page, expectedGeneration)` beside the
   existing recovery wait. It polls `host.status` with `expect.poll` (the
   contract's own signal; no `waitForTimeout` sleep) until both
   `control_generation` and `acknowledged_generation` equal the expected
   generation, or a 10 s budget expires with a typed diagnosis.
2. Replace the 44.1 kHz path's immediate `host.status` sample and generation
   equality asserts with that wait.
3. Leave production Runtime, Host, and Controller code unchanged. PR #413
   already waits inside a running `snapshot.reload`; this Task still makes the
   proof observe the acknowledgement boundary it asserts about.

## Version Management

Version impact: none.

Reason: test synchronization only. No Product, Module, Host, Provider,
Contract, Assembly, or Channel identity changes.

## Documentation Impact

Documentation impact: none.

Reason: No portal route describes individual assertions inside the Web Runtime
Host browser proof; the lane's contract in `operations/testing-and-proof` is
unchanged.

## Verification

- `node --check tests/platform/web/host/web_runtime_host_browser.spec.mjs`
- `python3 apps/web-runtime-host/test/web_host_source_boundary_test.py apps/web-runtime-host`
- `scripts/web-runtime-host.sh test`

Ten consecutive loaded `ci-web-heavy` runs are not a local gate. Exact-head CI
on the `web-runtime-host` lane is the merge evidence.

## Constraints

- One Conventional Commit on `fix/web-host-ack-generation-wait` in an isolated
  worktree from `origin/main`.
- Declared files: this plan and
  `tests/platform/web/host/web_runtime_host_browser.spec.mjs`.
- Do not modify production Runtime, Host source, manifests, Product Assembly,
  portal pages, or snapshots.
- Push, Pull Request, Integration Queue merge, and Issue closure are
  authorized. Tag, Release, publication, deployment, and Channel promotion are
  not.
