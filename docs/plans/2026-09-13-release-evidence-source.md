# R3: actual publication Task and squash source proof

Status: delivery integration under verification, based on the actual PR #1278
squash `427d2a9f51cf8fd4e43e921d7e39c39307d928b9`. The unpublished source
Task was rebased alone onto this merged dependency; the PR discovery and POST
preflight repairs remain intact, without replaying the old stacked PR commit.

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

## Historical stack verification

The results and temporary paths below belong to the original stacked commit
`54831b509c0b922394ef5ae0b6355c4b6f4eb64c`, not the refreshed delivery tree.
The passive Git runner fix is already present in merged PR #1277; this delivery
preserves that runner byte-for-byte, including its newer raw-byte, filter and
atomic-install safeguards, rather than replaying the old implementation.

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

## Delivery verification

The initial refreshed source suite passed 19/19 (51.095 seconds), independently
19/19 (53.668 seconds). The registered Python 3.14 CTest then timed out at the
unchanged 60-second budget. That failed run is retained in this session's raw
tool output; it is not overridden by the earlier standalone passes.

Each source case was rebuilding the complete publication-workspace fixture.
The fixture now generates its seed once through the real workspace/planner and
clones the emitted Git objects into an independent, non-hardlinked repository
per test. All 19 source cases and assertions remain. Registered CTest passed in
26.32 seconds with the original 60-second limit. This is fixture setup reduction,
not a replacement of the emitted bytes with handcrafted publication evidence.

Before that fixture-only change: publication collector 10/10, evidence PR 32/32,
staged ownership 74/74; clean Node 22 install, Portal 144/144, production build
and 47-route/internal-link validation passed. After the fixture change, source
19/19 passed locally in 26.346 seconds and independently in 25.459 seconds;
workspace 25/25 passed in 40.900 seconds. Independent review confirms separate
per-case repositories and all original assertions retained. No full production
release is proven. Final staged ownership passed 74/74 in 5.792 seconds; diff
check passed. These results preceded the dependency's final merge.

The dependency is now merged and this Task is being reverified on its actual
main base. The shared `publication_workspace.py` is unchanged by this Task.

Actual merged-base revalidation (source code and all 19 assertions unchanged):

- Source suite 19/19, 26.905 seconds; registered Python 3.14 CTest 1/1,
  27.10 seconds under the unchanged 60-second budget.
- Publication workspace 25/25, 44.547 seconds; evidence PR 36/36;
  publication collector 10/10; GitHub API 39/39; ownership/admission 74/74.
- Node 22 Portal check 144/144, metadata for 47 pages, 10 diagram sources and
  20 outputs, snapshot consistency, typecheck, production build and all 47
  routes/internal links passed. No Product Build or snapshot was allocated.
- `git diff --check` passed. Independent review of the complete rebased
  five-file Task is clean; independent source suite 19/19, 26.965 seconds.
  No host, signer, provider or production API was used
  by these fixture tests; the partial-clone observer is loopback-only.

## Version Management

Version impact: none

Reason: internal release source verification; no Product Build, Assembly,
Module, Provider or public Contract change and no immutable snapshot rewrite.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish actual squash/source verification from the remaining gates.
