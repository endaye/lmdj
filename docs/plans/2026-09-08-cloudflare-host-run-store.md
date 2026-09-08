# Durable local Host operation records

Relates to #873 and #924. Depends on the shared transaction delivered by #947.

## Task

A process that stops after a publication intent or loses its remote receipt must
not start another publication merely because its OS lock disappeared. Persist
operation boundaries and all transaction observations under a target-specific
file lock shared by cooperating worktrees on the same operator host. Flush each
record and its containing directory before returning control to the caller.
Never truncate or repair an incomplete record automatically. A fresh process can
inspect prior records but cannot adopt or restart an unfinished operation.

Declared files:
- `apps/web-runtime-host/tools/cloudflare_run_store.py`
- `apps/web-runtime-host/test/cloudflare_run_store_test.py`
- `scripts/web-runtime-host.sh` (register the tests)
- this plan.

The local store uses private regular files, no-follow opens, bounded records,
sequence/run/target validation and nonblocking flock. Only a confirmed terminal
transaction observation permits the caller to finish its run. Unknown receipts,
failed recovery, torn writes and death before durable completion remain pending.
The observer is wired to the real transaction in tests; a separate process test
exits immediately after its durable intent and proves the next process is refused.

Validation: run-store failure/process tests, transaction/API/target tests, shell
syntax, and staged ownership checks. No new required CI check or cloud mutation.

This is private operator state, not a public deployment evidence Contract. All
callers must choose the same root. The OS lock does not cover other machines or
Cloudflare dashboard operators; production command wiring must supply the shared
operator serialization policy. A reconciler still needs remote receipts and
signed artifact identity; this module does not infer them or automatically resume.
CLI staging/upload/verification and explicit recovery remain part of #924.

## Version Management

Version impact: none; internal operator tooling, no Product/Assembly or formal
Contract change. Existing Netlify evidence is not reused or relabeled.

## Documentation Impact

Documentation impact: none; this store is not yet wired into public deployment
commands, so current Portal deployment behavior remains unchanged.
