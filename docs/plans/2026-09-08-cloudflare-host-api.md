# Shared Host Cloudflare API transport

Relates to #873 and #924.

## Task

Provide the shared fixed-target API layer needed by Creator and Runtime candidate,
promotion and recovery commands. Declared files:
- `apps/web-runtime-host/tools/cloudflare_api.py`
- `apps/web-runtime-host/test/cloudflare_api_test.py`
- `scripts/web-runtime-host.sh` (register the suite)
- this plan.

The client fixes account and target selection, rejects credential redirects,
bounds API responses, validates single-version deployment and version identities,
and performs same-version publication and route updates with pre/post state checks.
A failed mutation receipt is unknown and is never automatically retried. A caller
must reconcile state before another mutation. Observed concurrency checks are not
an atomic compare-and-swap or a distributed lock; serialized orchestration remains
required. Empty/multi-version targets fail closed and require explicit bootstrap
or reconciliation. Recovery target names reserve isolated destinations; this Task
does not create them or mutate any live Worker.

Validation: API suite, shell syntax, staged change-scope ownership suite, and
read-only authenticated deployment/version/route observations on existing Hosts.
No full Host build is required for this transport-only change. The suite is wired
into existing nonbrowser Host tests; no new merge gate is introduced.

This library is not yet an end-to-end deployment adapter. Signed archive and tag
verification, credential-free staging, candidate upload, HTTP/browser smoke,
operator serialization, durable observations and CLI integration remain in #924.
Do not emit these dictionaries as Netlify evidence Contracts. No serialized
Contract is introduced by this internal module.

API reference: https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/

## Version Management

Version impact: none; internal deployment tooling, no Product/Assembly or
serialized Contract changes.

## Documentation Impact

Documentation impact: none; internal transport not yet connected to a deployment
entry point, so current published deployment behavior and Portal facts are unchanged.
