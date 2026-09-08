# Authenticate historical closed-review mapping receipts

## Scope

Declared files:

- `scripts/ci/review_failure_report.py`
- `tests/build/ci_review_failure_report_test.py`
- `docs/plans/2026-09-08-lmdj-ci-historical-closed-mapping.md`

Real GET-only collector probes for `34155232043/1` and `34158645559/1`
reject successful historical closed-mapping runs because their workflow differs
from current main. Original evidence is retained in
`/tmp/lmdj-discovery-backlog.W3X9lA/collector-probes.json`.
The existing current-workflow path remains unchanged. A new fallback requires
the exact successful mapping run/job/steps/artifact and closed map schema,
repository/workflow/PR/head/merge/control identities, historical source equality,
complete first-parent main ancestry, and actual changed paths including rename
origins. It returns only not-applicable-to-backend-failure, never valid AI review
or focused scope. Incomplete scope evidence remains incomplete.

API-only ancestry uses a bounded, deduplicated complete compare inventory and
walks actual first-parent links. Missing/truncated inventories or unknown parent
links reject rather than guessing. Merge-file pagination cannot silently exceed
the API's 3000-file ceiling. No PR API or extra token permissions are added.
This fallback supports the repository's single-parent squash mapping only;
multi-parent merge-file semantics are rejected, not silently treated as an
unambiguous first-parent delta. See the [GitHub commit API](https://docs.github.com/en/rest/commits/commits)
for paginated compare commits and the commit-file inventory ceiling.

## Verification

Baseline: 23 consumer tests pass on `ecf524ee`. Add a minimal historical-map
regression and observe its rejection before implementation. Cover successful
old-source receipt, incomplete-scope/non-review meaning, wrong identities and
head associations, missing/ambiguous/expired ZIP, failed mapper/upload,
source/ancestry disagreement, truncated/duplicate compare inventories, missing
parents and rename paths. Preserve all real review producer source checks.
Run focused consumer tests, full CI contracts with pinned actionlint and
explicit ShellCheck, and staged ownership. No AI, report, dispatch or Issue
mutation is performed; real historical collector reads may verify compatibility.

Actual verification evidence:

- Baseline 23 tests passed; the new historical-map case failed before the fix
  (`/tmp/lmdj-historical-map-red.log`). Final focused coverage is 38 passing
  tests (`/tmp/lmdj-historical-map-target-final.log`), including merge equal to
  control, between control and main, and earlier than control; a side-parent
  ancestor does not satisfy the last case.
- GET-only production collector probes now return not-applicable for
  `34155232043/1` and `34158645559/1`. The actual review producer
  `34151840695/1` remains rejected for source mismatch. Results are retained in
  `/tmp/lmdj-historical-map-real-green.json`. These are actual HTTP reads, not
  injected fixture successes, and do not replay AI or deliver any report.
- The real PR 806 map has `complete: false` and no scope records. Acceptance
  here means only a proven historical closed-mapping run, not a valid AI review
  or a repaired scope record. Fixture pagination/cap tests exercise fail-closed
  handling against the documented API contract; they do not claim a live
  3000-file boundary experiment.
- Staged ownership: 66 tests passed
  (`/tmp/lmdj-historical-map-ownership.log`). An earlier full CI run passed
  1726 tests with actionlint 1.7.12 and explicitly available ShellCheck 0.9.0
  (`/tmp/lmdj-historical-map-ci.log`); final added ancestry regressions are
  reverified below, not counted as part of that earlier run.
- Final full CI: 1728 tests passed in 37.817 seconds, no skips reported,
  with the same explicit actionlint/ShellCheck paths
  (`/tmp/lmdj-historical-map-ci-final.log`).

## Version Management

Version impact: none — only backend-failure receipt authentication changes;
no Product, Assembly, Contract, snapshot or release identity changes.

## Documentation Impact

Documentation impact: none — repair the documented historical-source evidence
boundary internally without changing operator commands, current Portal facts,
pages, diagrams or testing/release authority. Portal tooling is unchanged;
the full Portal build is not applicable, not claimed passed.

## Pitfall Impact

Pitfall impact: none — the source-equality-to-current-main defect is directly
derivable from the collector and captured by exact historical-source regression.
The broader existing API fixture pitfalls remain unchanged.

Root reviews the final diff before local commit and owns subsequent shipping.
