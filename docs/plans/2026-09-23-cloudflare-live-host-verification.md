# Fresh Cloudflare Host verification at managed deployment boundaries

Task: [#1503](https://github.com/endaye/lmdj/issues/1503).
Base: `2e24cacff4e4470d1f08510b987570762ea77dd8`.

## Scope and declared files

One Task restores `LiveHostVerifier` and `LiveDeploymentEffect` against the
Cloudflare sources. It reads the same canonical deployment/route parser as
`cloudflare_host.py inspect`, derives both origins with the deployment-evidence
URL functions, and uses the public-origin observer. Recorded `DeploymentEffect`
field comparisons and deployment evidence contracts remain unchanged.
Production composition is a separate decision; no deployment is performed.

- `tools/release/live_host.py`
- `apps/web-runtime-host/tools/cloudflare_smoke.py`
- `apps/web-runtime-host/tools/deployment_smoke.py`
- `tests/build/release_live_host_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-23-cloudflare-live-host-verification.md`

The trusted caller supplies the frozen Worker, exact deployment and version,
Product Build, Host version, and signed index/manifest digests. The read-only
transport permits only GET for the configured Worker's deployments/subdomain,
with fixed account/origin, bounded responses, duplicate-key rejection and no
redirects. Public requests never receive the API token.

## Verification journey

1. Authenticate the original managed dispatch, successful run and retained
   evidence through the unchanged `DeploymentEffect`. Reread the actual artifact
   and require the same authenticated digest before HTTP.
2. Read the Worker deployment and enabled production/Preview routes. Require
   the exact frozen deployment ID and version at 100 percent, not just the
   eight-character Preview URL prefix or the same version in a later deployment.
3. Check immutable then production: root/index identity, frozen entry digests
   before manifest parsing/asset downloads, every asset's length and digest,
   security headers, unknown routes and encoded traversal behavior. Reuse the
   Cloudflare edge rejection/normalized-exact-index rules; Preview-only robots
   allowances never apply to production.
4. Observe production with `cloudflare_site_observation`, match the frozen
   identity/digests, and reread the deployment and routes. Changed or unknown
   state refuses. This is point-in-time HTTP evidence, not continuous or browser
   acceptance; a stable evidence digest never avoids new I/O.
5. Reauthenticate retained evidence after HTTP. Through real journals and
   `DispatchTransition`/`ReleaseDriver`, assert successful progression, repeated
   fresh verification on resume, drift blocking the successor, pending original
   intent and exactly one deployment POST after failed verification/retry.

Use real loopback HTTP with canonical Runtime/Creator payload fixtures and the
real Cloudflare parsers, Host validators, artifact consumer and managed driver.
Only transport routing is replaced. Public TLS/DNS, Cloudflare edge behavior,
credentials and production composition are not exercised or claimed.

Lowest-tier checks:

- `python3 tests/build/release_live_host_test.py -v`
- `python3 tests/build/release_deployment_effect_test.py`
- `python3 tests/build/release_managed_dispatch_test.py`
- `python3 apps/web-runtime-host/test/deployment_smoke_test.py`
- `python3 apps/creator-web/test/deployment_smoke_test.py`
- Cloudflare API, origin observation and smoke target suites under
  `apps/web-runtime-host/test/`.
- `scripts/core.sh configure dev` and registered `build.release_live_host` CTest.
- `python3 tests/build/ci_change_scope_test.py` after staging new files.
- `scripts/docs-site.sh check`.

The restored contract test has its original 90-second budget. It catches fresh
verification being bypassed, observing another deployment/bytes, credential
leakage, or a managed retry repeating deployment. Existing gates and budgets
are not weakened. Independent current-head review precedes merge.

## Version Management

Version impact: none

Reason: internal release verification; no Product, Assembly, Module, Host,
Provider or Contract identity changes and no Product Build allocation.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release

Replace the retired Netlify live-verifier description with the Cloudflare
implementation and keep missing composition and live acceptance explicit.

## Local evidence

Final registered live Host suite: 56/56, Python 3.14.7, 54.09 seconds, CTest
exit 0; raw output in `build/core/dev/Testing/Temporary/LastTest.log` and
`/tmp/lmdj-1503-ctest-v5.log`. Baseline managed dispatch: 20/20. Unchanged
DeploymentEffect: 57/57. Runtime smoke: 35/35; Creator smoke: 9/9. Cloudflare
API/origin/target suites: 18/9/6. All exit 0.

Portal `scripts/docs-site.sh check`: exit 0, 170/170 tests, 10 diagram sources /
20 outputs, 48 routes and internal links. Raw output:
`/tmp/lmdj-1503-docs-check-v1.log`. This is local verification, not a deployment.

Earlier evidence is retained: `/tmp/lmdj-1503-red.log` records the unavailable
live module; `live-v1` was terminated (143) after finding an unpatched observer
transport, not counted as verification. `live-v2` failed six managed fixtures
because their migrated prior projection/digest disagreed; corrected fixtures
passed 6/6 in `managed-live-v3`. `live-v4` passed 51/52 but its distribution smoke
fixture retained a legacy Runtime manifest Host ID. `ctest-v5` uses the current
Host ID and verifies all 56 tests without changing production identity rules.
All these logs share the `/tmp/lmdj-1503-` prefix. No live provider acceptance
is inferred from the interrupted run or any loopback test.

Pitfall disposition: no new entry or recurrence. The known Cloudflare robots,
traversal and explicit User-Agent guidance was applied. Fixture migrations and
verification logic are expressed directly by tests; no new external platform
behavior was established.
