# Prepare fixed PR review objects

Date: 2026-10-13
Issue: [#2118](https://github.com/endaye/lmdj/issues/2118)
Status: implementation; verification and shipping pending.

## Premises and scope

Fresh main and Task base: `de1baf121949557e53a38820372721c852214e47`.
The live Issue and open successors were inspected before editing. The
preparation defect remains: `collect_t2` fetches base/head commits, then the
isolated collector refuses missing blobs. Existing `blob:none` checkout
configuration survives the ordinary fetch. No successor implements per-run
object preparation. The collector's refusal is correct and must remain.

Historical failures are retained: #2117 run 38341334753 attempts 1/2;
#2121 run 38348619991 attempt 1; #2119 run 38346303442 attempt 2;
#2128 run 38350197877 attempt 1. The last two were independently reproduced
under guarded read-only access to their actual runners: runner 01 lacked
15 of 27 changed sides for U03, runner 02 lacked 9 of 16 for U10. Both
original fixed diffs exited 128. The separate bounded cache recoveries for
U02a/U11 do not constitute a durable repair or prepare another runner.

One atomic infra Task, exactly these nine files (Root admitted the ledger and
narrow historical-finding preparation extensions before they were written):

- `scripts/ci/pr_agent_input.py`
- `scripts/ci/review_pipeline.py`
- `scripts/ci/review_recheck.py`
- `tests/build/ci_pr_agent_input_test.py`
- `tests/build/ci_review_pipeline_test.py`
- `tests/build/ci_review_recheck_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `docs/plans/2026-10-13-pr-review-fixed-object-preparation.md`
- `.agents/pitfalls/partial-clone-review-inputs.md`

No product, workflow, installed engine/provider, host configuration, branch
protection or release changes. U03/U10 heads remain frozen. Root owns remote
recovery admission, independent current-head review and guarded merge.

## Implementation boundary

After trusted target resolution and fixed merge-base/control identity, discover
required objects from bounded immutable tree metadata before calling the
unchanged collector. Use no-renames inventory first because canonical rename
detection itself can need missing blobs. Include changed old/new blobs and
committed base attributes needed for their paths. Add/delete candidates across
generated boundaries remain visible; gitlink targets are not fetched as blobs.

The pipeline owns one explicit missing-OID fetch from its existing authenticated
origin. No lazy fetch is enabled in discovery, readback or collection. Fetch
must not change refs, HEAD, index, working files, config or FETCH_HEAD; it disables
tags, maintenance, pruning and submodule recursion. Recheck complete object
availability before canonical collection. Missing/invalid/incomplete input
still refuses before model execution or publication. Preserve every existing
file, blob, diff, represented-input, output and deadline bound, attribute
isolation, generated exclusion and current-target recheck.

The independent publisher prepares its own fixed input before canonical rename
inventory; a warm collector cache cannot stand in for that separate checkout.
Explicit transport owns a process group and terminates its descendants on
timeout, stdout/stderr overflow and exit, without touching other processes.

Historical-finding collection and publication retain their existing review,
path, ancestor, live-head and conversation authentication. A required source
reader prepares only the authenticated path's old/current blobs and relevant
committed attributes from the original review head, then reads through the
same no-network isolated Git view. It never inventories or hydrates unrelated
historical changes. Single/batch repair limits and publication compensation
remain unchanged.

## Verification

First retain an actual RED from the original pipeline using a real file://
partial clone: materialize base/control, create a new head after cloning, fetch
commits, prove new blobs absent, then attempt complete collection.

Required journeys and regressions:

1. Partial clone missing objects → explicit preparation → unchanged full
   collector → real adapter authentication → independent complete source/diff
   comparison; repeat with a fresh head and independent cache.
2. Modified/add/delete/rename inputs and nested base attributes retain exact
   bytes and semantics. Generated-only and cross-boundary rename refusals stay.
3. A transport failure, absent/wrong-type object, invalid identity, bounded
   output/time failure or target movement emits no successful publication.
4. Exact metadata snapshots remain identical around preparation; hooks,
   external diff/textconv and PR-file sentinels never execute. A local request
   observer proves collection itself never fetches.
5. A cold independent publisher completes canonical rename inventory and the
   original review/label journey. Real timeout and output-overflow children
   have exited when explicit transport returns.
6. A cold historical finding prepares only its selected old/current source and
   original attributes; unrelated historical blobs stay absent. Authentication
   refusals happen before source preparation, and preparation failure never
   resolves a thread. Collection and independent publication retain every
   existing recheck, race and compensation journey.

Run both complete owning suites and the unchanged workflow contract. The
conservative selector requires full `ci_*_test.py` discovery plus the real
handler seam for this PR-Agent boundary. Whole Portal, scope (including new
plan ownership), whitespace and declaration checks are required. Root schedules
heavy verification; source/lightweight checks may run first. No reduced lane,
timeout, assertion or acceptance journey can substitute for a failed check.

After merge, a fresh whole review using the actual trusted control must
demonstrate preparation and eligible current-head publication on an affected
runner. Old attempts execute old control code. Local success and cache repair
are distinct from this production acceptance; record any remaining gap.

## Documentation impact

Documentation impact: required

Route: `/operations/testing-and-proof`. Document the preparation/collector
boundary and distinguish local source verification from current-runner proof.

## Pitfall ledger

Persistent partial-clone transport and isolated collection are a CI ordering
boundary, not a product regression alone. No existing matching entry was found.
The new `partial-clone-review-inputs` entry records this agent's actual U03/U10
observations and exits to the real partial-clone pipeline suite. Its absorbed
source invariant does not imply production acceptance or Issue completion.

## Version Management

Version impact: none. This repairs CI input preparation without changing any
Product, Module, Host, Provider or public Contract identity.

## Results

Raw receipts are retained in ignored `build/verification/2118/`:

- `partial-clone-red.log`: original source fails complete collection after the
  fixture proves two new head blobs absent; exit 1. The same regression passes
  after explicit preparation (`partial-clone-green-first.log`, exit 0).
- `producer-complete-v1.log`: 47 tests PASS, exit 0;
  `pipeline-complete-v1.log`: 82 tests PASS with one existing skip, exit 0;
  `workflow-contract.log`: 39 tests PASS with one existing skip, exit 0.
- Subsequent focused checks for missing base binary attributes, bounded
  ancestor expansion and generated-only/cross-boundary disposition each PASS.
  These additions still require the final complete discovery run.
- Final test self-review found a misplaced gitlink assertion in an adjacent
  missing-commit case (`misplaced-gitlink-assertion-red.log`, exit 1). It was
  moved to the actual gitlink fixture; both affected cases PASS in
  `preparation-gitlink-corrected.log`, exit 0. The earlier pipeline-first
  negative log also remains, including the repaired diagnostic-evidence loss.
- Independent review found two additional cold-cache consumers and a transport
  descendant lifetime gap. The original seven-file patch and SHA manifest are
  retained as `source-review-snapshot.patch` and
  `source-review-seven-files-manifest.json`.
- `transport-descendants-red.log` proves real timeout/stdout/stderr failures
  leave child processes running with the old helper. The three focused tests
  PASS after owned process-group cleanup (`transport-descendants-green.log`).
- `cold-publisher-red.log` fails in independent canonical rename inventory;
  the new cold-cache and original pure/edited rename journeys PASS together in
  `cold-publisher-green.log`. The later complete pipeline run retained two
  synthetic-identity fixture failures; their preparation seam was updated
  without reducing publication assertions.
- `cold-repair-red.log` first caught a test policy-path setup error, not the
  product defect. After fixing that fixture, `cold-repair-red-source.log`
  reaches authenticated historical source and fails `git show` with exit 128.
  `recheck-complete-v2.log` passes all 42 cases, including cold collector and
  independent publisher, unchanged metadata, unrelated historical blobs still
  missing, hostile local attributes, and transport failure before any reply or
  resolution. The complete discovery run remains authoritative for final code.
- Final owning suites on Python 3.11: producer 50 PASS; pipeline 84 PASS and
  one pre-existing skip (85 total); recheck 42 PASS. All exited 0. The first
  pipeline run after the required reader API caught its synthetic batch
  fixture still using the real source reader; that negative receipt remains.
  Supplying the same existing fixture source through the new required seam
  restored both authenticated requests without changing any assertion.

The conservative contract plan selects all 95 `ci_*_test.py` files and the
unchanged real handler seam. This full run and whole Portal are UNRUN at this
source review checkpoint. Official CPython 3.12.15 source was downloaded,
verified against the official SHA-256 and extracted under ignored
`build/toolchains/`; configure, `make -j4` and `make altinstall` each exited 0
under the coordinator's exclusive window. `python-build.json` and the three
step logs retain commands/results. The prefix-local runtime reports Python
3.12.15 and OpenSSL 3.6.3. It supplies only this Task's isolated seam runtime;
system defaults and shared configuration are unchanged.

Production acceptance remains UNRUN: a fresh whole review on an affected runner
must use the merged trusted control. The implementation PR relates to #2118;
the Issue stays open until that separate evidence exists.
