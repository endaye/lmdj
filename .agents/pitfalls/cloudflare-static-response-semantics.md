---
id: cloudflare-static-response-semantics
area: ci-release
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/873
    observed_by: Codex
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/965
    observed_by: Codex
exit: none
---

# Netlify response rules need live Cloudflare verification before a fixed address is enabled.

## Why

Cloudflare combines headers from overlapping rules; copying Netlify cache rules
produced duplicate `no-store` values and conflicts with immutable asset rules.
HTML and JavaScript MIME responses lacked the UTF-8 charset required by the Host.
Preview URLs replace robots directives with `noindex`, and edge rejection of
encoded dot segments differs from the local emulator's normalization. A first
fixed-route enable also briefly returned an asset 404 although the version
Preview already passed. These are provider observations, not product behavior.

## How to apply

Render exact-asset rules with the shared Cloudflare header tool. Verify candidate
and fixed URLs independently against signed bytes and browser journeys; keep
Preview-only header allowances out of fixed-URL acceptance. Reconcile version
identity before rollback and use bounded readiness retries. Retain provider
differences explicitly instead of weakening existing Netlify checks. No offline
gate can establish the live provider's routing propagation or edge behavior,
so this entry remains open pending a durable live-acceptance mechanism.


The second occurrence is the isolated PR Preview's first deployment: API upload
and route state passed while early HTTP returned 404. #965 is the escalation
Issue and implements exact-entry readiness before unchanged full smoke. Live
edge propagation remains provider evidence; the deterministic retry tests do
not turn an upload receipt into HTTP acceptance. This entry remains open.
