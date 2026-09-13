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

Crash-recovery boundary found during delivery review: rerunning preserves
complete, byte-identical pages, but an interrupted write can leave a truncated
version page or `.index-*` temporary file. The standalone generator safely
refuses those states; it does not yet automatically reconcile arbitrary crash
residue. Durable publication-workspace integration must cover this remaining
leg before the complete orchestration can claim crash recovery. This is a
known acceptance gap, not a smaller definition of the overall release goal.

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

## Delivery revalidation on current main

Replayed the declared 18-file Task onto main
`01cc1aa34c5122da1ec7d3abb65230a17379e601` after PR #1271 merged.
Earlier local-stack results above remain historical. Delivery caught a real
byte-integrity defect: UTF-8 decoding can turn an invalid byte into the same
U+FFFD character present in valid frozen content. The old string comparison
accepted that corrupted page. The new positive-baseline/one-byte corruption
regression failed with `Missing expected rejection` on the original code
(exit 1, `/tmp/lmdj-site-delivery-utf8-red.log`). Comparing raw Buffers now
rejects both check and write while preserving the corrupted bytes for diagnosis.

Delivery Python projection 7/7, Node 22 projection 9/9 (including actual Python
rendering and MDX compilation), source 19/19, publication binding 13/13,
model 28/28 and staged ownership 74/74 passed. Official generation followed by
check produced the same single empty index; no historical publication was
invented. CMake configure, registered `build.release_changelog_site` (0.10s)
and Python compilation passed. Node log: `/tmp/lmdj-site-delivery-node-v2.log`;
ownership log: `/tmp/lmdj-site-delivery-ownership.log`.
Clean Node 22 `npm ci --ignore-scripts` preceded complete Portal check: 125/125
tests, production build and 47 routes/internal links passed (exit 0), with the
actual `/releases/` HTML confirming the empty inventory statement.
Log: `/tmp/lmdj-site-delivery-portal.log`.

Independent agent `/root/release_journal_review` read the complete 18-file Task,
ran Python 7/7 and Node 8/8 before the added byte regression (its Node was 26,
not a substitute for primary Node 22 evidence), and separately reviewed the
byte-integrity fix and clarified recovery boundary. No unresolved code finding;
the crash-residue acceptance gap above remains open. No new pitfall: the byte
defect is directly expressed by its regression. Real publication collection,
Git-triggered online acceptance, mandatory admission, corrections and complete
driver/service integration remain required subsequent work.

### Remote review disposition and retained recovery obligations

PR #1272 review run `34739796206/1` identified missing fsync barriers and
interrupted final-page/index staging writes. Both are accepted limitations of
the standalone local generator, deferred within the still-open full release
goal, not fixed by this projection Task. Source generation is not a durable
release transition: it must still pass exact Git review/commit and website
verification. Committed historical truth is not rewritten by recovery, and a
stale, truncated or unknown output remains a failed check. Before admitting the
generator to an unattended workflow, durable publication-workspace integration
must demonstrate interrupted write, link/install, index replacement and restart
recovery with per-transition byte checks. File/directory fsync and any hardlink
recovery window must be covered; no copy fallback may bypass create-only history.

The same review questioned the plan digest's trust source. A projector cannot
reconstruct the complete plan from this ledger alone: signed asset identities
and complete verified Release state are not its inputs. Keep the digest, but
label it explicitly as a reviewed publication-record value; only Content/Notes
digests are recomputed here. The upcoming `publication-record` collector must
use the full published Release verifier before producing that input. This
clarification does not authenticate existing records or stand in for the
collector, and the initial inventory remains empty.

Clarification verification: Python projection 7/7, Node 22 projection 9/9 and
registered CTest (0.28s) passed, as did compilation and complete Portal check
(125 tests, production build, 47 routes/internal links, exit 0;
`/tmp/lmdj-site-delivery-record-label-portal.log`). Independent review read the
three-file clarification and confirmed the trust-boundary wording, not a repair
or waiver of the two remaining crash/durability findings.

## Version Management

Version impact: none

Reason: release tooling and current portal only; no Product Build allocation,
snapshot rewrite, Module, Host, Provider or public Contract identity change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /releases/ /operations/version-and-release/
/operations/creator-changelog/ /operations/runtime-changelog/

Future version routes derive exclusively from reviewed frozen identities.
