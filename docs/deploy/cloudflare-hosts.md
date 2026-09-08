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

A Catalog configured this way reaches only the deployment whose `wrangler.json`
carries the variable. **The `creator-recovery`, `creator-initialization` and
version-preview Workers are separate deployments**, so a Release archive that
names `https://creator.lmdj.workers.dev/soundset-catalog/` in its meta has no
Catalog when served from any of them: the page asks a prefix those Workers do
not forward, and the surface reports an unreachable Catalog. That is safe, and
it is also invisible unless you are looking for it — do not read an empty
Sound Set surface on a recovery or preview address as a Catalog outage.

Configuring the Worker is only half of it: the page has to be told to use the
prefix. That is the `lmdj-soundset-catalog` meta in `apps/creator-web/index.html`
(or `window.__LMDJ_SOUNDSET_CATALOG__`), and its value must be **this
deployment's own origin plus `/soundset-catalog/`** — absolute, because
`normalizeCatalogEndpoint` refuses a relative endpoint rather than resolve it
against whatever page is loaded, and same-origin, because `connect-src 'self'`
still stands. An off-origin value there is #901 again. Note that the meta lives
inside the signed Release archive, so changing it is a Product Build; the
Worker's `CATALOG_UPSTREAM` is not, which is the point of splitting them — the
page names a stable same-origin prefix once, and which Catalog that prefix
reaches is a deploy-time variable.

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

The forward is not a relay, and two things keep it that way. They are not the
same kind of thing, and an earlier version of this page said they were.

**The destination is structural.** It is composed from `CATALOG_UPSTREAM` plus
a literal, an element read back out of a frozen pair, and a digest re-matched
against `[0-9a-f]{64}`. That alphabet carries no `/ \ . : @ % ? #` and no
control character, so the only request-derived bytes in the target cannot
terminate a path segment, introduce an authority, or change the scheme or port.
Two independent adversarial reviews attacked this and neither could move the
destination off the configured host, by any path, query, header or encoding, on
either implementation. This is the constraint carrying the security property.

**The admitted grammar is a check, not a composition.** It is an equality, a
frozen-kind lookup and a regex, kept deliberately equal to the two shapes
`packages/web-runtime-platform/web/soundset_catalog.mjs` can spell. It is
tempting to borrow that module's refusal and call the grammar closed by
construction, but the threat this whole design is built against is a
compromised dependency running in the page, and such code never calls the
transport: it calls `fetch("/soundset-catalog/…")` directly, which
`connect-src 'self'` permits. Under that threat model the transport contributes
nothing and the Worker's own check is the only thing in the way, so widening it
widens the residual channel.

**The residual channel runs both ways.** Outbound it is the choice of which of
three admitted targets is fetched from the one configured Catalog, and for two
of them a 64-hex digest — repeatable at whatever rate the page likes, since
nothing throttles and the transport asks for `no-store`, and readable by
whoever operates that Catalog and by anyone terminating TLS in front of it.
Inbound, the Catalog's answer comes back into the page: 404-versus-200 per
request plus up to the shape's bound of bytes of the Catalog's choosing. So
`connect-src 'self'` is a command-and-control barrier as well as an
exfiltration barrier, and the forward punches through it in both directions for
one fixed host. Anyone who can place content in the configured Catalog can feed
a compromised bundle attacker-chosen bytes same-origin.

What remains true, and is why this is still narrower than naming a Catalog in
`connect-src`: the far end is one host the deployment chose rather than an
origin the attacker chose, and the request grammar reaching it is closed.

Whether the Workers runtime attaches the viewer's IP to a subrequest is **not
established** and must not be assumed either way; if it does, that is a further
request-derived component reaching the Catalog.

One behaviour worth knowing before reading a log: `new URL` resolves dot
segments and maps `\` to `/`, so several request spellings reach the Worker as
one admitted path and appear as distinct entries in an edge cache. Every alias
resolves to the same target — the Worker suite pins that — and the proof server
refuses them outright, which is a deliberate, recorded difference rather than
an oversight.

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
