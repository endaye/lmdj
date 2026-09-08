# Cloudflare Host operator commands

Use `scripts/cloudflare-host.sh` for signed Creator and Runtime inputs. This is
an explicit operator workflow, not automatic deployment on main. Release
publication and Channel promotion retain their own authorization.

## Operator ownership and inputs

Use one operator host at a time and the same private state root across all its
worktrees: `$HOME/.local/state/lmdj/cloudflare-host`. Create its parent privately
before first use. The file lock only serializes that host; coordinate an exclusive
maintenance window with other hosts and dashboard operators. API checks detect
observed changes but are not a remote compare-and-swap.

Supply `GITHUB_TOKEN` for fresh signed tag/Release/package verification and
`CLOUDFLARE_API_TOKEN` for the fixed LMDJ account. The command isolates the two
credentials in child processes. Tokens belong in the process environment, not
command arguments, configuration files or journal records.

Targets are `creator-web`, `web-runtime-host`, `creator-recovery` and
`runtime-recovery`. Production maps to the fixed `creator` and `lab` Workers;
isolated tests map to `creator-recovery` and `lab-recovery`. Select the tag from
the verified release audit and take version/deployment IDs from exact receipts.

## Candidate, verify, promote and recover

Candidate upload requires Node 22.16.0 and Wrangler 4.129.1 installed beforehand.
Pass their absolute executable/module paths; the command validates the versions.
It generates a private upload configuration, preserves signed assets and reads
Wrangler's structured receipt. An existing target must already have Preview URLs
enabled. Uploading a candidate must leave its active deployment and route intact.

```bash
scripts/cloudflare-host.sh candidate "$TAG" --target "$TARGET" \
  --state-root "$HOME/.local/state/lmdj/cloudflare-host" \
  --node "$NODE_EXECUTABLE" --wrangler "$WRANGLER_MODULE"

scripts/cloudflare-host.sh verify "$TAG" --target "$TARGET" \
  --state-root "$HOME/.local/state/lmdj/cloudflare-host" --version "$CANDIDATE_VERSION"

scripts/cloudflare-host.sh promote "$TAG" --target "$TARGET" \
  --state-root "$HOME/.local/state/lmdj/cloudflare-host" --version "$CANDIDATE_VERSION" \
  --prior-tag "$CURRENT_SIGNED_TAG"

scripts/cloudflare-host.sh recover "$PRIOR_SIGNED_TAG" --target "$TARGET" \
  --state-root "$HOME/.local/state/lmdj/cloudflare-host" --version "$PRIOR_VERSION" \
  --prior-tag "$CURRENT_SIGNED_TAG"
```

`recover` deliberately promotes the exact retained prior version, after checking
both its signed bytes and the current version needed for failure recovery. It
never rebuilds/uploads a replacement under the same version ID. Enabled
production with a different version requires its signed prior tag. Each command
revalidates release inputs; retained staging receipts alone are not authorization.
Keep the original signed releases available throughout the recovery window.

For a positively absent target only, append `--initialize` to `candidate`. This
uses an initial deployment with the stable workers.dev route disabled, verifies
the returned version and Preview bytes, and checks that the stable route remains
disabled. It refuses to overwrite an existing target. Initial promotion is a
separate command. A failed first publication disables the stable route again;
existing production recovery restores and rechecks the exact prior version.

## Unknown outcomes and explicit reconciliation

Timeouts, invalid upload receipts, concurrent changes and unconfirmed recovery
leave the operation pending. Do not rerun uploads, delete state directories or
manually truncate journals to bypass this condition. Preserve staged assets,
Wrangler receipts and the journal. Torn or corrupt journals require separate
manual evidence recovery; the tool will not rewrite them.

Inspect the journal and authenticated live state:

```bash
scripts/cloudflare-host.sh inspect --target "$TARGET" \
  --state-root "$HOME/.local/state/lmdj/cloudflare-host"
```

After the operator establishes the intended current deployment, bind all returned
identities explicitly. Reconciliation re-verifies signed inputs, version Preview
and the fixed URL when enabled, then rereads deployment and route. Only an exact
match completes the pending local record; it performs no cloud mutation.

```bash
scripts/cloudflare-host.sh reconcile "$CURRENT_SIGNED_TAG" --target "$TARGET" \
  --state-root "$HOME/.local/state/lmdj/cloudflare-host" \
  --version "$CURRENT_VERSION" --expected-deployment "$CURRENT_DEPLOYMENT" \
  --expected-run "$PENDING_RUN" --expected-sequence "$LAST_SEQUENCE" --route enabled
```

If an uncertain first upload left no Worker, use `reconcile --absent` with only
`--target`, `--state-root`, `--expected-run` and `--expected-sequence`. Two
positive absence reads are required; authentication failure, a generic 404 or a
network error cannot prove absence. This creates no cloud resource.

Use `--route disabled` only when that is the observed and intended state. Keep
both the unresolved history and reconciliation receipt. Reconciliation establishes
current state; it does not retroactively claim an uncertain upload succeeded.

## Acceptance boundaries

CLI HTTP verification checks signed resource bytes, lengths, headers and negative
paths. It does not prove browser audio, service-worker update, cross-origin
storage migration, human hearing or manual acceptance. Complete those Host-specific
journeys before claiming migration acceptance. Isolated HTTP exercises and
production operations must be recorded separately.
