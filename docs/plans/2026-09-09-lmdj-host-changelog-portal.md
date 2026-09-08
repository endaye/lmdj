# Host prepared-changelog portal projection

Part of T4 in the canary plan and the result-driven delivery plan. This Task
implements the prepared-record projection only. Authenticated deployment and
promotion addenda remain a later integration; a prepared record is not either
receipt, a complete candidate or proof of AI semantic correctness.

## Declared files

- `apps/docs-site/scripts/lib/host-changelogs.mjs`
- `apps/docs-site/scripts/generate-host-changelogs.mjs`
- `apps/docs-site/test/host-changelogs.test.mjs`
- `apps/docs-site/package.json`
- `apps/docs-site/sidebars.ts`
- `apps/docs-site/scripts/check-build.mjs`
- `apps/docs-site/docs/operations/creator-changelog.mdx`
- `apps/docs-site/docs/operations/runtime-changelog.mdx`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `.agents/pitfalls/rspack-cache-stalls-corrected-mdx-build.md`
- This plan.

Read each Host's active `module.json` and optional `CHANGELOG.md` produced by
`tools/canary/preparation.py`. Do not create historical records or bump versions.
Render newest first, with exact commit links and separate input/assessment/entry
digests. Reject corrupt or ambiguous machine records. Legacy prose is not an
authenticated structured entry and is not evaluated as MDX.

Generate tracked static pages explicitly using `npm run changelogs` in the docs
site. Build/check compare source-derived expected bytes without rewriting them;
future allocation PRs regenerate the pages before freezing snapshots. Frozen
pages never import a mutable current changelog feed. No version snapshot is
created by this Task. Ordinary documentation projection is not a deployment.

## Verification and far-side evidence

Node tests exercise Python-producer interoperability; independent Host versions
and unchanged Host; shared dependency prose; no invented reverted changes;
escaped model prose; malformed/duplicate/foreign identities; missing versus
unreadable input; stale-page rejection without rewriting; current regeneration
leaving old static snapshot bytes unchanged. The status test proves only that
prepared records cannot claim deployment/promotion. Real authenticated addenda,
promotion of an older stable manual, and their end-to-end receipt presentation
remain open T4 acceptance, not simulated passes.

Run `node --test test/host-changelogs.test.mjs` from the docs site, the complete
`scripts/architecture-portal.sh check`, staged and committed new-file ownership,
diff whitespace checks and final committed-range local-CI classification.
Use current-head review and authorized squash shipping. No new required PR
check, coverage change, Product test, allocation or deployment is introduced.

During verification, the first build rejected an HTML comment in generated MDX;
the generator now emits an MDX comment and the test actually compiles/renders
both empty and populated pages. Subsequent local builds stalled in Rspack with
unchanged CPU time. Preserving and moving only the owned Rspack cache allowed
the unchanged corrected source to build cold in about 15 seconds and pass all
44 route/link checks. The ledger records this environment observation without
asserting a particular corrupt cache object or weakening checks.

Final local verification: 26 focused tests and the complete 112-test Portal suite
passed with zero skipped. The standard Portal check then passed 41 current
pages, 10 diagram sources / 20 outputs, existing snapshot identity/provenance,
typecheck, production build and 44 route/link checks. Staged ownership passed
66 tests; the ledger passed 15 tests. Dependency installation reported 29
advisories (1 low, 10 moderate, 18 high), with no dependency edits in this Task.

## Version Management

Version impact: none. Presentation tooling only; Host manifests, Product Build,
Assembly, Contracts and frozen snapshots are unchanged.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/creator-changelog/ /operations/runtime-changelog/ /operations/version-and-release/
Reason: expose independently prepared Host changelogs without conflating them
with publication, deployment or promotion evidence. No architecture boundary or
source diagram changes.
