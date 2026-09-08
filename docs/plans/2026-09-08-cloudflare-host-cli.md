# Cloudflare Host operator commands

Relates to #873 and #924. Depends on retained signed staging in PR #954.

## Task

Provide one stable `scripts/cloudflare-host.sh` entry point for candidate upload,
exact-version HTTP verification, same-version promotion and recovery. Reuse the
existing signed Host stage commands, fixed-account API, strict HTTP verifier,
transaction and durable per-target journal. Existing production sites do not
follow main automatically.

Declared files: this plan; `scripts/cloudflare-host.sh`;
`apps/web-runtime-host/tools/cloudflare_host.py`;
`apps/web-runtime-host/test/cloudflare_host_test.py`;
`scripts/web-runtime-host.sh`; `scripts/ci/scope_policy.json` for entry-point ownership; shared `cloudflare_run_store.py`, `cloudflare_api.py` and their tests; both Host deployment runbooks and `docs/deploy/cloudflare-hosts.md`; affected current
Portal Host pages when public command behavior is ready for publication.

Every command binds an explicit target, signed tag and exact retained version.
Revalidate release inputs without passing Cloudflare credentials to GitHub/source
children. Upload only a private generated configuration and verified assets;
consume Wrangler's structured version-upload receipt, never scrape console text.
Persist intent before upload and preserve uncertain receipts for reconciliation.
Verify candidate bytes before promotion. Check the previous known version and
routing state before mutation; recover only an owned positive receipt. Never
silently overwrite concurrent changes or restart an uncertain operation.

One operator host uses one private state root across worktrees. Local flock does
not serialize another machine or dashboard; the runbook must require exclusive
operator ownership. An incomplete journal refuses new cloud writes. Explicit
reconciliation binds the pending run/sequence and verified live deployment/route;
empty-target initialization uses explicit `--initialize`, positive absence and a
disabled stable route. Both paths need full validation before declaring
all of #924 done; a refusal alone is not their acceptance.

Validation: command component tests covering signed-input mismatch, exact receipt
identity, timeout/unknown output, unchanged production during candidate upload,
prior-version binding, successful promotion and recovery failure. Keep all legs
of the existing isolated Host recovery journey for final CLI cloud acceptance.
Test mocks are not real Cloudflare or browser acceptance.

## Version Management

Version impact: none planned; internal operator receipts are not a serialized
public deployment Contract. No Product or Assembly allocation.

## Documentation Impact

Documentation impact: required when shipping the public command behavior.
Affected portal pages: /hosts/creator-web /hosts/web-runtime
Update operator runbooks and these current pages, then run docs-site check.
