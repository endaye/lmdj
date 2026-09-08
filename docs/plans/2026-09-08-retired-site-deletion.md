# Retired hosting deletion and current documentation

## Authority and Task

The owner authorized old sites and hosted data deletion on 2026-09-08, replacing
the earlier retention decision for these four resources. One documentation Task
records the verified operations and removes obsolete current-use instructions.
Relates to #927 and #873. No product or deployment implementation changes.

## Declared files

- `docs/plans/2026-09-08-retired-site-deletion.md`
- `docs/deploy/2026-09-08-retired-site-deletion.md`
- `docs/deploy/architecture-portal.md`
- `docs/deploy/creator-web.md`
- `docs/deploy/web-runtime-host.md`
- `apps/docs-site/docs/operations/documentation-governance.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/web-runtime.mdx`

## Verification

For each exact target: authenticated identity and dependency inventory → disable
old workflow and read disabled state → DELETE receipt → authenticated absence.
Check current Cloudflare deployment/route identity and HTTP before/after; retain
any concurrent Git-driven production change separately from this operation.
No forced deletion or blind retry after an unknown mutation result.

Run `scripts/docs-site.sh check` for edited current pages and linked runbooks,
then staged `python3 tests/build/ci_change_scope_test.py` for the two new paths
and `git diff --cached --check`. No new gate or product test is needed for this
documentation-only Task. Physical acceptance and stable observation remain open.

## Version Management

Version impact: none. Hosting retirement does not change Product, Host, Module,
Provider or Contract identities, release archives, tags or Channels.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/documentation-governance /hosts/creator-web /hosts/web-runtime
Reason: Current hosting and recovery instructions must stop naming deleted sites
as usable targets. Historical evidence and frozen snapshots remain unchanged.

## Pitfall Impact

Pitfall impact: none — reason: authorized resource lifecycle work; no new process
defect or recurrence was discovered.
