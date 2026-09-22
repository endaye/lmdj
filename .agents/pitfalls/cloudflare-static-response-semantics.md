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
  - date: 2026-09-22
    occurrence: https://github.com/endaye/lmdj/actions/runs/35677810942
    observed_by: Kimi Code (k3)
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
and route state passed while early HTTP returned 404. #965 implements
exact-entry readiness before unchanged full smoke, and is closed. Live edge
propagation remains provider evidence; the deterministic retry tests do not
turn an upload receipt into HTTP acceptance, so #965 is a recurrence and not
the mechanism this entry waits for.

The third occurrence is the 1.0.61.0 Runtime promote: the post-cutover
exact-identity check failed and the transaction's recovery re-published the
prior version, after which production verified clean on the prior bytes and a
later full deployment succeeded unchanged — cutover propagation, not a
product defect.

The escalation Issue is
https://github.com/endaye/lmdj/issues/985, which names what would close this:
a live-acceptance mechanism asserting signed bytes, combined response headers,
charset, robots directives and bounded readiness against the fixed address
rather than a Preview. Under `pitfall-ledger.md` gate admission this cannot
become a CI gate -- violation is decidable only against a live deployment, and
propagation timing is not deterministic -- so the exit will be a `skill:<path>`
section, and naming it is the work #985 tracks. This entry remains open.
