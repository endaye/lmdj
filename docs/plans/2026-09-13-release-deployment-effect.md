# Bind both Host deployment effects to managed dispatch

Status: delivery integration of original `46e68ae7` onto Host validator `3c6147e4`.
No formal release or deployment is authorized or performed.

## Scope

Declared files:

- `tools/release/deployment_effect.py`
- `tests/build/release_deployment_effect_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-deployment-effect.md`

Compose actual read-only Runtime and Creator DeploymentEffect with managed
dispatch. Require original request/run/attempt correlation, successful jobs and
upload, unique authentic artifact, complete bounded ZIP and actual Host schema.
Compare tag, target, Build, Host, Site, archive/files and exact prior with the
trusted frozen projection. Constructor arguments are not original authority.
Recheck correlation/inventory/expiry at the final boundary. Acknowledgements,
pending, failure, ambiguity and recovery records never authorize progress/retry.

The original source uses unbounded archive.read. Repair that known flaw in this
Task before shipping: only STORED/DEFLATED evidence members and bounded decoder
output, with real forged-metadata regressions for both Hosts. Use authenticated
correlation expiry from the binding and preserve the final dual-deadline check.
This resource bound does not authenticate every byte of a compressed tail.

## Verification

Preserve all original 42 cases, including both real effects in one parent:
Runtime success then Creator success reaches promotion; Creator failure retains
Runtime proof, prevents promotion and causes no rollback/repost. Actual journals,
temporary Git, real dispatch consumer/client and actual isolated Host CLI are
used; remaining release legs and remote services are explicit fixtures.

First prove baseline; add and run both Host ZIP decoder negatives red on imported
source, then repair and rerun the complete suite. Keep wrong identity/attempt/Site/
prior, expired evidence (including shorter receipt expiry after final binding),
bad upload, duplicate/corrupt records, completed evidence drift and no-retry legs.
Register the original 120s integration budget; no existing test timeout changes.
Run related contracts, staged ownership, Portal and independent complete review.
Original-stack logs are historical, not verification of this delivery tree.

## Version Management

Version impact: none

Reason: internal release orchestration; no Product, Assembly or public Host API.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document retained deployment evidence and distinguish live Site proof.

## Acceptance boundaries

Current alias/HTTP/browser verification, authenticated frozen prior/configuration,
production factory/service, full candidate CI/signing and full release journey
remain required. Legacy promotion reader integration is still outstanding.
Pitfall disposition: executable interface/evidence regressions, no general gate.

## Current verification

Imported original 42/42 baseline passed in 62.728s, exit 0, before new ZIP cases.
Four new cases (two inherited by each Host) then failed with six assertions in
9.685s: max_length 1073741824 emitted 8392837/8393202 bytes, and both BZIP2/LZMA
were accepted. The actual decompressor was observed, not replaced. The repaired
complete suite passed 46/46 in 77.260s, exit 0. Logs:
`/tmp/lmdj-deployment-effect-delivery-baseline-v1.log` and
`/tmp/lmdj-deployment-effect-delivery-tests-v1.log`.

Independent complete five-file static review found no actionable finding. It
confirmed original cases and both Host journeys remain intact, actual Host CLI
and final authenticated expiry binding are retained, and no deployment log is
decompressed. It did not rerun the heavy 46-case suite. Actual registered CTest
deployment/publication/managed-dispatch/dispatch contracts passed 4/4 in 120.83s
total (individual 86.52s/16.48s/10.15s/7.67s), exit 0, with unchanged budgets.
Output: `/tmp/lmdj-deployment-effect-delivery-ctest-v1.log`.

Staged ownership passed 74/74 (6.131s). Locked npm ci and Portal check under
Node 22.22.2 exited 0, including 144 tests and 47 routes/internal links. Logs:
`/tmp/lmdj-deployment-effect-delivery-scope-v1.log` and
`/tmp/lmdj-deployment-effect-delivery-docs-v1.log`.
