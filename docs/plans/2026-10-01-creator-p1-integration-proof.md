# P1 T8: integrated version settlement and proof

Relates to #1662, #1663, #1664 and #1665. Integrates the seven preceding P1 Tasks
on live main `0d9156edcff2ae384c2096caf1f5447007137f5f`, preserving the newly merged
reverse, pitch, pan and loop editor. No release, Creator deployment or Channel
promotion is authorized by this Task.

## Declared files

- `packages/{project-io,application-facade,web-runtime-platform}/module.json` and
  `apps/{core-cli,core-mcp,native-host,cardputer-host,web-runtime-host,creator-web}/module.json`.
- `products/lmdj/{version.json,assembly.json,assembly.lock.json,src/compiled_assembly.cpp}` and
  `products/lmdj/generated/web-runtime-identity.{json,mjs}`.
- `tools/web-runtime/runtime-identity.json`,
  `apps/web-runtime-host/tools/asset_roles.py`.
- Creator `package.json` and `package-lock.json` Host identity,
  `apps/creator-web/deploy/wrangler.json`,
  `apps/web-runtime-host/deploy/cloudflare_worker.mjs` and its existing Node test.
- Existing `apps/creator-web/test/package_test.py` fixtures and
  `tests/build/version_test.py` and `apps/docs-site/test/repo-facts.test.mjs`
  exact component pins, and generated current Creator and Runtime Host changelog projections.
- This plan, the P1 first-use plan, `docs/operations/default-assets.md`, and current
  `/hosts/creator-web/` portal page. The immutable snapshot is a separate documentation Task after the settled
  source commit, so its provenance names a retained clean source revision.

## Behavior and verification

Activate the complete seven-role offline inventory under the Creator MAJOR
identity. Retain the explicit historical six-role inventory and five-role legacy
inventory. Bind Creator's same-origin Catalog proxy to the independently deployed
original-kit Worker; preserve explicit Catalog overrides, strict path grammar,
GET-only forwarding, stripped viewer headers and bounded responses. Failure
stays a recoverable Catalog error. Deploying the Creator remains out of scope.

Lowest-tier checks: manifest producer/validator parity and actual packaging,
version verification and generated identity freshness, service-binding path and
credential exclusion, full Creator components, TypeScript and portal checks.
Then run complete packaged Creator and Web Runtime Host proofs sequentially.
Record complete far-side journeys for progressive default initialization,
first-gesture voice acknowledgement, mic/master capture identity after reopening,
System navigation transport continuity and offline close/reopen. Fake devices and
unsupported automated WebKit do not satisfy physical Chrome/Safari/iPad rows.

Selected batch-only lanes require committed-head evidence. Missing Linux lanes,
a review backend failure, binary-input refusal and an undeployed asset service
remain explicit gates, not inferred passes or owner-approved risks.

## Version Management

Version impact: new Product Build, additive Module MINOR and Creator Host MAJOR.
The Product Build is mechanically derived from the verified integration main's
version manifest by incrementing BUILD, retaining its M2 line and resetting
PATCH; the exact number must be absent from live tags and release-intent inventory.
The version CLI has no allocation operation: use `scripts/version.py lock` to
produce the lock and compiled Assembly, then generate Runtime identity. Module
MINOR increments come from their live manifests; Creator MAJOR activates the new
inventory. Unchanged consumer Hosts receive PATCH identity increments when their
exact dependency pins change. Create the immutable canary portal snapshot with
`scripts/docs-site.sh version` on the clean settled source before delivery.

Documentation impact: required
Affected portal pages: /hosts/creator-web/ and generated component/version routes.
Reason: the active distribution inventory, Assembly identity and independent
Catalog binding change. Historical snapshots stay immutable.
