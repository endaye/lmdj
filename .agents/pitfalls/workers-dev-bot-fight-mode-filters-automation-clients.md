---
id: workers-dev-bot-fight-mode-filters-automation-clients
area: ci-release
status: open
recurrences:
  - date: 2026-09-22
    occurrence: https://github.com/endaye/lmdj/pull/1592
    observed_by: Kimi Code (k3)
exit: none
---

# Cloudflare Bot Fight Mode filters deployment HTTP clients before requests reach the Worker.

## Why

The LMDJ account's workers.dev hostnames sit behind Cloudflare Bot Fight Mode.
Requests with automation User-Agents (the urllib default `Python-urllib/3.x`)
are blocked with HTTP 403 at the security layer (`source: bic` in account
security events) and never reach the Worker, while browsers on the same URL
succeed. Every deploy-time production observation and smoke leg failed this
way, and the 403 reads exactly like a disabled workers.dev route — checking
`subdomain.enabled` over the API does not distinguish the two. This is account
platform behaviour, not derivable from product code.

## How to apply

Any deployment or smoke HTTP client must send an explicit tool User-Agent; the
shared request builder in `apps/web-runtime-host/tools/deployment_smoke.py`
owns this. When a workers.dev URL returns 403 to a tool but 200 to a browser,
do not touch the route toggle: query account security events
(`firewallEventsAdaptive`, filter by datetime/host) for `source`/`ruleId`
before changing anything. Related transient symptom from the same platform:
immediately after a promote, the fixed URL can briefly keep serving the prior
deployment, so an exact-identity check right at cutover can fail and the
transaction's recovery restores the prior version — verify what production
actually serves before concluding a defect (see
`cloudflare-static-response-semantics`). No eligible gate exists yet: the
account security posture is Owner-controlled and not mechanically assertable
from CI, so the entry stays open with `exit: none`.
