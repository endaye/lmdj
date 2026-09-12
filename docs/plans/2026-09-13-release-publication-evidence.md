# R3c.3: verified publication evidence patch

Status: locally verified implementation, stacked on publication collector
`04b48949`; not pushed, merged or production-exercised.

## Scope

`scripts/release.sh publication-patch TAG RELEASE_ID PLAN_SHA256` reruns the
complete published verifier and emits a Git-applicable patch, without writing
local evidence files or remote objects. The patch changes exactly the selected
intent's disposition to published, appends its exact publication record, adds
its frozen version page, updates the index, and increments the independently
reviewed source-document count by the declared new page count. It cannot
rewrite a historical version or immutable snapshot. Complete local/canonical
intent equality is checked before generating the disposition change.

An already byte-identical complete evidence update produces an empty patch.
Existing record conflicts, missing/modified/unknown pages, unsafe local source
paths and stale canonical intent fail closed. A corrupt independent count is
not repaired by counting observed documents; the normal Portal check retains
that separate completeness responsibility.

This is the evidence PR's content producer, not PR shipping or website
acceptance. The durable backend still must retain the patch, apply it in its
owned Task worktree, verify the exact output, commit/review/merge the same PR,
and verify public-site content before admitting deployments. A partial local
application must reconcile its saved operation, not generate a new publication.
No Release, asset, tag, snapshot or deployment write occurs in this Task.

Declared files:

- `tools/release/publication_evidence.py`
- `tools/release/publication.py`
- `tools/release/cli.py`
- `tests/build/release_publication_evidence_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-publication-evidence.md`

## Verification

Run evidence patch tests, existing publication/binding tests, staged ownership,
Python compilation, full Portal check and independent review.

The journey is fixture prepare→Draft→publication→verified patch→real Git apply→
exact published ledger/record/page/pin assertions→repeat collection returns
empty. Assert original Release body/assets and all external write counters
unchanged. Retain a previous release's page and ledger line byte-for-byte;
assert changed paths are exactly five and no immutable snapshot changes.
Separate negative cases cover Draft, local authority drift, stale generated
pages, publication record conflict, symlink, missing/unknown inventory and
post-collection source drift refused by real Git apply. These are local/mock
tests, not authenticated publication, protected review or online acceptance.

Results: evidence patch 16/16, publication 10/10, changelog binding 13/13,
release skill 13/13 and staged ownership 74/74 passed (exit 0); Python
compilation and stable command help passed. Full Portal check passed 124/124
tests, production build and 47 routes/internal links (exit 0). Logs:
`/tmp/lmdj-evidence-patch-tests-v3.log`, `/tmp/lmdj-evidence-binding.log`,
`/tmp/lmdj-evidence-scope.log`, `/tmp/lmdj-evidence-docs-check.log`.

Independent reviewer `/root/release_journal_review` found a Unicode line-framing
defect: Python splitlines treated Unicode content as Git line boundaries.
Replaced it with literal-LF framing in both ledger rewrite and diff generation;
real Git apply/reverse and JSON-content preservation regressions passed. Final
independent review reran all 16 tests and found no further actionable finding.
The invariant is fully expressed in code regressions, so no process-only
pitfall entry was added. The dependent stack remains local behind PR #1266.

## Version Management

Version impact: none

Reason: internal evidence preparation interface; no product identity allocation,
Assembly, public Contract or published package bytes change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document the new patch-producing command and its non-shipping boundary.
