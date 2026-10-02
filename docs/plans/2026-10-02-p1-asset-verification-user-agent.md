# P1 deployed asset verification uses an explicit tool identity

Protected deployment run `37014873365` uploaded the reviewed original corpus and Worker, then its real WAV GET returned HTTP 403. Retain that actual failed run and artifact. Fresh requests for the same object show default urllib receiving 403 and an explicit LMDJ tool User-Agent receiving HTTP 200 with the expected 43,244 bytes and digest. No account security setting changes are needed for this repair.

## Task and declared files

Give the live verifier an explicit descriptive LMDJ tool User-Agent. Keep no-redirect, exact HTTP 200, exact byte/hash/length, CORS, immutable-object and health assertions, 30-second per-request budget, all nineteen GETs and the protected deployment route.

- `tools/asset-server/kit_test.py`
- `tools/asset-server/live_test.py`
- `.agents/pitfalls/workers-dev-bot-fight-mode-filters-automation-clients.md`
- `docs/plans/2026-10-02-p1-asset-verification-user-agent.md`

## Verification

The real urllib admission suite has one new far-side test: a loopback server refuses the default request identity and serves bytes to an explicitly identified LMDJ tool. Removing the production header must fail this test at object admission; restore with a fresh mtime and rerun the complete suite. Run the stable asset check and complete live verifier against the already deployed origin, recording literal exit statuses and authenticated bytes. These checks precede commit along with staged ownership and whitespace checks. Derive the committed input-key obligations and perform independent current-head review before guarded shipping. Rerunning the protected deployment after the fix is a separate verification boundary; the failed original run remains failed.

## Version Management

Version impact: none. Deployment observation tooling and its tests change; no Product, Host, Module, Provider, Contract or asset identity changes.

Documentation impact: none
Reason: No Architecture Portal source fact changes. This Task repairs the deployment observer and records the existing platform pitfall's second occurrence and bounded mechanism.
