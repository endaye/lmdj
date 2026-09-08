# T4g — Actions-only authenticated merge-map reader

## Declared files

- `scripts/ci/review_merge_map_reader.py`
- `tests/build/ci_review_merge_map_reader_test.py`
- This plan.

## Boundary

`MergeMapReader(repository, repository_id, workflow_id, git_inputs, api_get,
download_artifact)(interval)` returns the existing GitInputs advice shape
`{complete, labels}`. Its `diagnostics` retain why/remedy without raw API errors
or credentials. Only Actions and contents GET/download callbacks are invoked;
no PR API, AI, write token grant, workflow or protocol change.

Recompute the complete Git interval, page bounded repository artifact inventory
and consider every matching mapping for every first-parent commit, not last
mapping wins or net diff. Missing, expired, incomplete, untrusted or ambiguous
evidence returns incomplete/full. This can sacrifice optimization when an older
map remains incomplete; it never permits a newer map to erase prior scope.

Reuse the existing map schema validator. Independently check archive identity,
exact attempt run/workflow/repository, completed mapping-only jobs and steps,
main first-parent control/merge, actual source workflow and per-commit paths.
Closed Actions runs may retain PR head while associations become empty; compare
exact PR/merge identity and workflow bytes, not display names or merge-only
head filtering. Recompute every nested record under its historical JSON policy.
Keep AI additions and historical effective consumer suites; unknown historical
suite or full record conservatively becomes full.

Caller supplies independently authenticated repository/workflow IDs and refreshed
GitInputs main. It must not expose callbacks that silently substitute unauthenticated
data. Map writer is trusted only after the above independent run/source checks;
the map digest never supplies trust. Historical producer receipts inside a
trusted map remain claims authenticated by that mapper; no PR API requery occurs.

## Verification

Lowest tier: mapping reader tests, mapping/scope/controller regressions, then
full CI contracts and staged ownership. Fixtures cover the actual empty PR-array
and PR-head run shape observed read-only in 34151840695/34152096875. They do not
prove a successful real complete mapping, token permissions, API races or actual
workflow source semantics. Those remain O1 acceptance; this task makes no
production execution, publication or release claim.

Pitfall impact: external Actions-shape recurrence was recorded in the separate
preceding merged-review identity fix; no new occurrence claimed here.

## Documentation Impact

Documentation impact: none

Reason: Internal callable CI reader only; no Portal routes or product identities.

## Version Management

Version impact: none

Reason: No product/module/provider/contract identity changes.
