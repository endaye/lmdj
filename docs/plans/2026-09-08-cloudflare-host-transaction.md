# Shared Host promotion and recovery transaction

Relates to #873 and #924. Depends on the API transport delivered by #941.

## Task

Connect retained-version validation, candidate validation, guarded publication,
production checks and exact-prior recovery. Declared files:
- `apps/web-runtime-host/tools/cloudflare_api.py` (bind publication to POST deployment ID)
- `apps/web-runtime-host/test/cloudflare_api_test.py`
- `apps/web-runtime-host/tools/cloudflare_transaction.py`
- `apps/web-runtime-host/test/cloudflare_transaction_test.py`
- `scripts/web-runtime-host.sh` (register tests)
- this plan.

The API publication result must match both the version and the deployment ID
returned by its POST; observing the same version under another deployment ID is
an unknown/superseded outcome, not proof of ownership.

The trusted caller provides a strict boolean exact-version verification callback
and a durable observer. Validate the served prior version on both its immutable
and fixed addresses before publishing; verify the candidate; reconcile deployment
and route state; publish the same version; verify fixed production and final state.
On failure, restore only if a positive deployment receipt still matches the live
ID (including when another operator republishes the same version). Recheck both
prior addresses and final state before recording recovery. Failed first publication
disables the route and verifies it. Unknown mutation receipts stop for explicit
reconciliation without another mutation. Version previews must already be enabled.

Validation: 14 transaction tests, 15 API tests, shell syntax, 66 staged scope tests.
Existing nonbrowser Host tests execute the suite; no additional merge gate.

This component does not upload or rebuild an artifact. The caller must bind each
version to independently verified signed Release bytes, implement full HTTP/browser
checks and durable observations, and hold a shared operator lock. Pre/post state
checks are not atomic compare-and-swap. Process death and resumed crash recovery
require the forthcoming durable CLI, not an in-memory exception handler. No live
Host mutation or complete #924 acceptance is claimed by component tests.

## Version Management

Version impact: none; internal tooling, no Product, Assembly or serialized
Contract change. Observer events are internal callback data, not Netlify evidence.

## Documentation Impact

Documentation impact: none; the transaction is not yet wired into public deploy
commands, so current Portal deployment behavior and facts remain unchanged.
