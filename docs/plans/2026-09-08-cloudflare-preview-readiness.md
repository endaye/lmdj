# Cloudflare Preview first-version readiness

Relates to #965 and #922.

## Task

A first upload receipt can precede HTTP availability. Before full smoke, wait
for the exact verified entry bytes, with a fixed 60-second readiness deadline
and 10-second request cap inside the existing 600-second publisher timeout.
Every final route, snapshot, header and artifact assertion remains unchanged.

Declared files:
- `apps/docs-site/scripts/cloudflare-preview-smoke.mjs`
- `apps/docs-site/test/cloudflare-preview-smoke.test.mjs`
- `docs/deploy/architecture-portal.md`
- `.agents/pitfalls/cloudflare-static-response-semantics.md`
- this plan

Lowest-tier verification: Node Preview smoke tests reproduce unavailable then
ready, permanent unavailability, wrong bytes, missing entry and late readiness.
Run `scripts/docs-site.sh check` for documented source facts and full existing
smoke regression; run staged ownership and diff checks. No new required check,
expanded timeout, skipped lane or reduced assertion is introduced.

Live journey: reconcile the first failed immutable version; ship trusted-main
fix; exercise the same authorized pilot PR within its remaining hosted budget;
verify version URL, exact head status and unchanged disabled stable route.
Do not declare live acceptance from component tests alone.

## Version Management

Version impact: none; no product or serialized identity changes.

## Documentation Impact

Documentation impact: none for current Portal pages; the existing page remains
accurate and the deployment runbook documents the additional readiness phase.

## Pitfall Impact

Pitfall impact: recurrence cloudflare-static-response-semantics. Escalation #965
tracks the second live provider occurrence; retain it as open provider evidence.
