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

Targets are `creator-web`, `web-runtime-host`, `creator-recovery`,
`runtime-recovery`, `creator-initialization` and `runtime-initialization`. Production maps to the fixed `creator` and `lab` Workers;
recovery tests map to `creator-recovery` and `lab-recovery`. First-deployment
acceptance maps to separate `creator-initialization` and `lab-initialization`
Workers. Retain their versions after acceptance; never delete a recovery Worker
to manufacture an empty target. The standalone HTTP verifier requires
`--initialization-target` for these addresses. Select the tag from
the verified release audit and take version/deployment IDs from exact receipts.

## Sound Set Catalog forwarding

The Creator reaches its Sound Set Catalog through the same-origin prefix
`/soundset-catalog/`, and `apps/web-runtime-host/deploy/cloudflare_worker.mjs`
forwards it. The page is never given a foreign origin, so `connect-src 'self'`
-- the exfiltration barrier around the Projects and captured audio the Creator
holds in OPFS -- stays exactly as it is. Nothing about the Content Security
Policy changes when a Catalog is configured.

Pin the Catalog in `vars.CATALOG_UPSTREAM` in the tracked
`apps/creator-web/deploy/wrangler.json`, never in a dashboard variable: the
Catalog a deployment forwards to must be diffable, reviewable in a Pull
Request, and auditable afterwards. It must be an absolute `https` base with no
query or fragment; anything else fails closed and the prefix answers 404.

**No Catalog is configured today, and that is deliberate**: there is no
production LMDJ Catalog, so `vars` carries no `CATALOG_UPSTREAM` and every
prefixed path answers 404. That is S11-D6's "a Host that offers no Catalog
browses only the Sets its Workspace Set Store already holds", and it is also
why the deployed smoke's "unknown paths return 404" assertion needs no
exception. Configuring a Catalog changes that answer for exactly the two paths
the transport can spell, and the smoke expectation has to be extended in the
same change.

The diagnostic Lab has no Sound Set surface. It sets neither `CATALOG_UPSTREAM`
nor the `run_worker_first` route, so it forwards nothing -- the gate is closed
by absence at both ends rather than by a condition in the shared Worker that
someone could delete.

The forward is not a relay, and both reasons are structural rather than
checked. The destination is composed from `CATALOG_UPSTREAM` plus tokens the
Worker re-derives -- a literal, an element read back out of a frozen pair, and
a digest re-matched against `[0-9a-f]{64}` -- so no request text is
concatenated into the target and no header, query or path segment can move it
to another host. And the admitted grammar is exactly `catalog/index.json` and
`object/(manifest|blob)/<64 hex>`, which is the whole of what
`packages/web-runtime-platform/web/soundset_catalog.mjs` can spell. What that
leaves a compromised page bundle is the choice of which object is fetched from
the one configured Catalog: 64 hex characters per GET to a fixed host.

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
