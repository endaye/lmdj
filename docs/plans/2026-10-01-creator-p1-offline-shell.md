# P1 T4: complete same-build offline shell

Relates to #1663. Cache the entire verified Creator shell, not only OPFS samples.

## Declared files

- `apps/creator-web/offline/{worker.mjs,worker.node-test.mjs}`
- `apps/creator-web/src/{main.tsx,runtime/offline_shell.ts}` and registration tests
- `apps/creator-web/{tools/package.py,test/package_test.py}`
- Shared `apps/web-runtime-host/tools/{asset_roles.py,cloudflare_headers.py,deployment_smoke.py}`
  and role/header/history tests
- `tools/web-runtime/{runtime-identity.json,serve_distribution.py}` and server tests
- Native Web manifest gate and JS identity validation with their focused tests
- Creator proof entry and packaged offline browser journey
- Current Creator/Web Platform portal pages, `apps/docs-site/diagrams/web-runtime-platform.architecture.json` and this plan

## Implementation and verification

The worker is a declared hashed distribution asset. Embed the build's complete
six-asset graph in its bytes, avoiding an index/manifest hash cycle. Validate the
manifest digest from the index and each asset's hash/length/security headers before
publishing a ready cache marker. Failed install preserves the prior complete
cache. Navigation uses the active build's cached shell; do not skip waiting or
claim a performing document. Browser lifecycle activates a replacement after prior
documents close. Cache only this same-build shell, manifest, JS, Wasm and worklets;
Project samples remain the Facade-owned durable OPFS artifacts.

Lowest tests cover complete install, partial/incorrect byte refusal, prior-cache
retention, security headers and same-build fetch. Packaged journey closes the first
document and reopens offline with real stored samples; update remains waiting while
the old document is active. Historical inventory tests retain pre-offline Hosts.

## Version Management

Version impact: Creator Host MAJOR asset-inventory addition. It is incompatible to
emit this inventory under the prior Host identity. Coordinated P1 version settlement
must precede offline activation and final packaged offline acceptance. Before
settlement, the packager retains the prior exact inventory and omits the worker;
registration reports unavailable. Source implementation and current-inventory
proof can merge independently. No old immutable package is changed.

## Documentation impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /core/modules/web-runtime-platform/
/platform/web-runtime/
Reason: complete offline shell and historical distribution inventory compatibility.
