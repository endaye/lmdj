# R3c.1: Product release changelog portal projection

Status: locally verified projection, stacked on publication binding `d14b09ee`.

## Scope

Generate `/releases/` and one `/releases/PRODUCT_BUILD/` page per published,
frozen changelog. A closed reviewed publication inventory records exact tag,
target, numeric Release ID, public date and plan/content/notes digests. The
generator requires the corresponding published intent and matching frozen
content; an unbound historical release is not backfilled. Initial inventory is
empty because no such verified publication records have been collected.

Python uses the same renderer as Release creation, not a second transcription.
Node calls the read-only projector and handles generated files. Existing version
pages cannot be overwritten, missing historical pages cannot silently disappear,
and index updates are allowed. All sources/output checks precede writes. Check
mode writes nothing. No existing versioned_docs or frozen snapshot is modified.
Version pages record publication, never infer deployment or promotion.

Normal build/start checks both Host and Product release projections. Sidebar and
Host pages link the Product index, which links back to Host logs. Generation is a
source operation; production remains Git-triggered. The release driver must
collect records from verify-published and ship them through review. Neither a
reviewed record nor this generator replaces far-side API or public-site checks.

Declared files:

- `tools/release/changelog_site.py`
- `tests/build/release_changelog_site_test.py`
- `CMakeLists.txt`
- `docs/release-evidence/changelog-publications.json`
- `apps/docs-site/scripts/generate-release-changelogs.mjs`
- `apps/docs-site/scripts/check-build.mjs`
- `apps/docs-site/scripts/lib/release-changelogs.mjs`
- `apps/docs-site/test/release-changelogs.test.mjs`
- `apps/docs-site/scripts/lib/host-changelogs.mjs`
- `apps/docs-site/scripts/lib/snapshot-provenance.mjs`
- `apps/docs-site/package.json`
- `apps/docs-site/README.md`
- `apps/docs-site/sidebars.ts`
- `apps/docs-site/docs/releases/index.mdx`
- `apps/docs-site/docs/operations/creator-changelog.mdx`
- `apps/docs-site/docs/operations/runtime-changelog.mdx`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-changelog-site.md`

Collection from real Release API, mandatory new-request admission, public-site
smoke, and an explicit append-only correction interface remain unfinished. No
actual release, deployment or production upload occurs in this Task.
The independent snapshot source-page pin increases from 46 to 47 for the new
index. Future publication Tasks adding version pages must update that pin in
the same reviewed change; deriving it from the observed file count would remove
its missing-page protection and is not permitted.

## Verification

Run Python release_changelog_site tests, Node release-changelogs tests, actual
Node→Python generation/check, staged ownership, Python compilation, Portal check
and independent review. Assertions cover shared notes bytes, exact identities,
dates/digests, published-only admission, missing records, generated file/path
safety, stale check-only behavior, append/new index, no frozen-page overwrite
and no silently removed history. Temporary filesystem/API records are not actual
published Release or website acceptance. No gate or timeout is loosened.

Verified 2026-09-13: Python 7/7, Node 8/8 (including actual Python projection
and MDX compilation), staged ownership 74/74, Python compilation, complete
Portal check with 124/124 tests, and final built-route check with 47 required
routes/internal links, all exit 0. The first Portal run correctly failed at the
unchanged 46-page snapshot pin; adding the index and increasing that independent
pin to 47 repaired the inventory. The final build check derives every version
route from validated publication projections, not just existing HTML files.
Independent review of implementation and follow-up changes found no actionable
findings. No new pitfall entry: page inventory synchronization is an existing
explicit gate; projection faults are covered by regression tests.

## Version Management

Version impact: none

Reason: release tooling and current portal only; no Product Build allocation,
snapshot rewrite, Module, Host, Provider or public Contract identity change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /releases/ /operations/version-and-release/
/operations/creator-changelog/ /operations/runtime-changelog/

Future version routes derive exclusively from reviewed frozen identities.
