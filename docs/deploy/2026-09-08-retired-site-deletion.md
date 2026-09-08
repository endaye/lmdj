# Retired site deletion — 2026-09-08

Relates to #927 and #873.

The owner explicitly authorized deleting the old sites and data after reviewing
the three new pipeline statuses. This supersedes the earlier 30-day retention
requirement for the old hosted deployments and the promise to retain the old
Creator origin. It does not mark Host physical acceptance, the seven-day
observation window, or broad Preview activation complete.

## Deleted resources

| Platform | Exact target | Positive receipt | Independent verification |
| --- | --- | --- | --- |
| Cloudflare, LMDJ account | Worker `lmdj`, tag `7c3f89e6af8546caa03806a8b5e5026b` | DELETE 200, matching tag | Authenticated Worker inventory excludes `lmdj` |
| Netlify | `lmdj`, `d91d32de-26eb-4a5e-9dce-0304ddcfd8f5` | DELETE 204 | Exact Site GET 404 |
| Netlify | `lmdj-creator`, `59b1da0c-b80f-4673-88e3-56e6352b525a` | DELETE 204 | Exact Site GET 404 |
| Netlify | `lmdj-runtime`, `c58831b8-adbb-4025-a370-5a08daf2b005` | DELETE 204 | Exact Site GET 404 |

Before deletion, all Netlify targets had no Git connection, custom domain or
domain aliases. The old Worker matched its previously audited tag, had no
bindings or tail consumers, and the account had no Workers custom domains.
Its two Builds triggers had already been removed. Deletions were sequential,
without force, with a saved intent, positive receipt and far-side API check.
Old hosted deployments are no longer available as rollback targets. This records
provider resource deletion, not a claim about physical erasure of provider backups.

The two legacy GitHub workflows were disabled before deleting their targets:
`deploy-creator-web.yml` (348168397) and `deploy-web-runtime-host.yml` (330384060).
Both independently report `disabled_manually`; their latest runs were terminal.
Their source and Netlify adapters remain for historical audit, not as usable
production/recovery consumers. Re-enabling them is not part of current operations.

## Preserved resources and data boundary

Current Workers `docs`, `creator`, `lab`, and `portal-preview` are outside the
deletion set, as are the separate initialization/recovery targets. Custom DNS,
shared GitHub App grants, Release assets, immutable tags and Channels were not
changed. Current Host operations use [the Cloudflare CLI](cloudflare-hosts.md).

Deleting hosting does not clear IndexedDB/OPFS in users' browser profiles. No
browser-local Project data was inspected, exported, migrated or deleted here.
The old Creator origin is no longer served; #961 remains the separate formal
Project export/import design task, without a promise to keep that origin alive.

Historical GitHub failures and private migration evidence remain retained under
the existing evidence-retention period. Sanitized per-target API observations,
intents, receipts and current-target verification are retained locally under
`~/.local/state/lmdj/cloudflare-migration-retention/2026-09-08/retired-site-deletion/`.

Post-deletion verification found `docs`, `creator`, `lab`, and `portal-preview`
deployment and subdomain responses unchanged from the pre-deletion inventory.
All three fixed production entries returned HTTP 200 with identical before/after
bytes. This is a deletion-impact check, not another complete product acceptance.

API procedure references: [Cloudflare Delete Worker](https://developers.cloudflare.com/api/typescript/resources/workers/subresources/scripts/methods/delete/)
and [Netlify API site deletion](https://docs.netlify.com/api-and-cli-guides/api-guides/get-started-with-api/).
