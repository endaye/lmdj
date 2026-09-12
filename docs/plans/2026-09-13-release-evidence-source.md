# R3: actual publication Task and squash source proof

Status: local implementation under verification, based on `c42d0e3a`.

## Scope

Verify the real Git source for the evidence PR controller. Reconstruct the
complete expected Task tree from the immutable base and freshly verified frozen
publication record using the existing planner; compare the exact declared head
tree and its single parent. A named file list or matching digest in a PR body
does not substitute for actual committed bytes.

For merge proof, require a distinct single-parent squash commit reachable from
canonical main. Reproject the same publication on its actual parent and compare
the whole resulting tree. Ordinary main progress is retained without changing
the frozen candidate; a squash that drops that progress or introduces extra
changes is refused. Current main must still contain the complete publication
record/page projection. Later append-only promotions leave the historical
publication proof stable, but this gate does not verify promotion acceptance.

The PublishedPrSourceGate wrapper calls the existing live signed-publication
collector, checks protected main before/after source verification and rechecks
ancestry/current publication on the final main observation. It is a source
component, not the full original-authority, Task-test, review/conversation,
historical-review or effective-protection gate. Production controller assembly,
remote branch push, public run/status/resume and service integration remain
unfinished; no release/deployment operation is enabled by this Task.

Private indexes and expected blobs may be added to the local Git object store.
No working files, real index, refs or remote state are written; missing history
is not implicitly fetched. Only passive bounded source blobs are materialized,
never hooks or candidate executables. Existing isolated Git environment handling
prevents config/index/replace-ref/graft injection.
The shared local-only Git runner disables lazy fetch and every transport, so
partial-clone promisor objects cannot trigger implicit network access, including
on Git versions without the dedicated lazy-fetch environment switch.

Declared files:

- `tools/release/evidence_source.py`
- `tools/release/publication_workspace.py`
- `tests/build/release_evidence_source_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-evidence-source.md`

## Verification

Use actual temporary Git commits and the real publication workspace/planner to
exercise exact head → real squash → unrelated main progress → repeated proof,
with negative extra-file/content/parent/reachability/drop/revert mutations.
The source fixture replaces synthetic target IDs with an actual ancestor;
this fixture change is not a signed-publication or real candidate acceptance.
Wrapper composition tests isolate the publication collector and exercise the
real source verifier plus changing branch observations. Existing publication
collector regressions separately own signed-publication fixture verification.
No real GitHub review, remote merge or public deployment is exercised.

Run staged ownership, related PR/publication/workspace regressions, full Portal
check and independent read-only review. First fixture run incorrectly passed
the frozen Mapping directly to the JSON-only changelog binding validator;
fixed the fixture using the existing thaw helper, without loosening validation.
Retain `/tmp/lmdj-evidence-source-tests.log` and subsequent versioned runs.

Independent review identified the partial-clone lazy-fetch gap in the reused
runner. A real filtered file-remote clone now proves it is non-shallow and lacks
the selected blob; after pointing its promisor remote at a loopback observer,
the production reader refuses the blob, sends zero HTTP requests and leaves the
blob missing. This regression does not contact GitHub or a production host.

Final local results: source 19/19 (`/tmp/lmdj-evidence-source-tests-v5.log`),
workspace 19/19 (`/tmp/lmdj-evidence-source-workspace-v2.log`), publication
10/10, evidence PR 23/23 and staged ownership 74/74 all passed. Portal check
passed 139 tests, production build and 47-route/internal-link validation
(`/tmp/lmdj-evidence-source-docs.log`). The strengthened partial-clone test
first proves ordinary Git reaches the loopback observer, then proves the
production reader makes zero requests and does not acquire the missing blob.

Independent read-only review identified the lazy-fetch defect; the fix and
strengthened regression were independently rechecked with no remaining
actionable finding. The reviewer did not repeat the final complete 19-test
source suite; the implementing session ran that suite and the shared workspace
regressions. Earlier failed fixture logs remain retained.

Pitfall disposition: no matching lazy-fetch/promisor ledger entry exists. The
local-only transport invariant is now directly enforced in the shared runner
and causally exercised by the real partial-clone regression; no additional
process-only rule is introduced. This local verification does not establish
GitHub review eligibility, actual remote squash, signing, production deployment
or end-to-end release acceptance. Shipping remains separate from this commit.

## Version Management

Version impact: none

Reason: internal release source verification; no Product Build, Assembly,
Module, Provider or public Contract change and no immutable snapshot rewrite.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish actual squash/source verification from the remaining gates.
