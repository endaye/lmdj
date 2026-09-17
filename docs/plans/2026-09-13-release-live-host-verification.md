# Fresh Host verification at managed deployment boundaries

## Scope

Delivery base: `ccb4bb7deee826edb193caee9bea3cce3d3d25c5` (local recorded
deployment prerequisite). Reapply the bounded live Host Task from
`969cdf34dcb82231fd80bed1c2876d284acbb7b3`, retaining the new prerequisite
artifact expiry and decompression bounds. This is not production request or
configuration binding, deployment authorization, or whole-release acceptance.

Declared files:

- `tools/release/live_host.py`
- `apps/web-runtime-host/tools/deployment_smoke.py`
- `apps/web-runtime-host/test/deployment_smoke_test.py`
- `tests/build/release_live_host_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-live-host-verification.md`

Reuse canonical Netlify Site parsing and shared Runtime/Creator HTTP smoke
from installed trusted sources, never candidate code. SiteReader permits only
GET on the fixed API origin and closed Site path, bounds responses, refuses
duplicate JSON keys and redirects, and closes inherited deployment transports.
The API token must never reach a public Host or appear in diagnostics.
Caller-supplied Site IDs and byte digests are not themselves authority: trusted
parent composition must supply the authenticated frozen projection.

LiveHostVerifier snapshots that projection, checks the current Site pointer,
verifies immutable and production URLs (every asset, security headers and
negative routes), compares original index/manifest digests and rereads the
pointer. Every call performs fresh I/O; a stable identity digest is neither a
cache nor continuous observation. LiveDeploymentEffect reauthenticates actual
recorded evidence on both sides of this HTTP check. Unknown or changed evidence
cannot advance the managed DispatchTransition/ReleaseDriver or repeat a POST.
Optional frozen digests on shared smoke are checked before manifest parsing
and asset inventory reads; existing callers keep their behavior.

## Verification

The primary integration uses existing canonical Host payloads and real loopback
HTTP for API/public content, replacing only opener routing. Logical production
URLs remain HTTPS-only; public TLS/DNS is not exercised. Real Site parsing,
Host validators, dispatch client and journals run without real credentials.
Runtime fixture adds the Host ID meta tag emitted by the current packager.

Assert both URLs/every asset, repeated fresh reads, isolated API token, wrong or
changing pointer, corrupt assets, self-consistent changed index, missing
headers, redirected/duplicate/oversized API responses, invalid scope and closed
create/publish/disable routes. Managed cases assert fresh proof on resume,
successor refusal without redeployment, and retained-artifact drift during
HTTP. Each failure retains its pending intent and original deployment.

Run the live integration, Runtime/Creator smoke, related registered deployment
and dispatch tests, staged ownership and Portal checks plus independent review
of all seven files. New CTest budget: 90 seconds, inherited from this Task's
original registration; no existing timeout, population or gate is relaxed.

## Version Management

Version impact: none

Reason: internal release verification only; no Product, Assembly or public API.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Keep historical browser proof distinct from fresh HTTP proof and final
production acceptance. The Portal continues to name missing composition.

## Evidence

Delivery preimplementation red: all three new canonical frozen-digest tests
errored in 1.580 seconds because `smoke_http` did not yet accept the new digest
arguments (exit 1). This is an API-availability red, not evidence of a schema
bypass. Original-stack fixture corrections and test logs remain historical
evidence in the original Task; they are not current delivery verification.

Current delivery evidence (all commands exit 0):

- `python3 tests/build/release_live_host_test.py`: 30/30, 29.578 seconds
  (`/tmp/lmdj-live-host-delivery-tests-v1.log`).
- Runtime canonical smoke: 34/34, 17.340 seconds
  (`/tmp/lmdj-live-host-delivery-runtime-smoke-v1.log`); Creator smoke: 8/8,
  3.726 seconds (`/tmp/lmdj-live-host-delivery-creator-smoke-v1.log`).
- `scripts/core.sh configure dev` selected Python 3.14.7. Registered CTest
  live Host / deployment effect / managed dispatch: 3/3, 138.43 seconds total,
  respectively 31.37 / 97.32 / 9.69 seconds; unchanged budgets
  (`/tmp/lmdj-live-host-delivery-configure-v1.log`,
  `/tmp/lmdj-live-host-delivery-ctest-v1.log`).
- Staged new-file ownership/admission: 74/74, 6.077 seconds
  (`/tmp/lmdj-live-host-delivery-scope-v1.log`).
- Fresh locked `npm ci` and Portal check under Node 22.22.2: 144/144 tests,
  47 routes/internal links (`/tmp/lmdj-live-host-delivery-deps-v1.log`,
  `/tmp/lmdj-live-host-delivery-docs-v1.log`).
- Independent `release_journal_review` inspected the complete seven-file diff
  and found no actionable functional finding; it did not rerun these suites.

The final diagnostic-only refinement gives all three new digest refusals an
explicit why/remedy without changing their conditions. Final complete Runtime
smoke rerun: 34/34, 17.592 seconds, exit 0
(`/tmp/lmdj-live-host-delivery-runtime-smoke-v2.log`). The independent reviewer
rechecked all seven files including diagnostics and evidence; clean, with no
heavy-suite rerun or external action by that reviewer.

No real Site, credential, public TLS, browser, production factory or complete
release journey is exercised. Pitfall disposition: directly testable protocol
and identity invariants; no new process-ledger entry is indicated.
