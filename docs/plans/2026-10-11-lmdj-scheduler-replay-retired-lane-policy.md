# Tolerate retired lanes in historical policy replay

Relates to #1048 (kept open for remote acceptance). Source Task: restore the
self-test scheduler/report controllers, down since PR #1997 merged, by letting
read-only historical-policy replay parse policy documents from the retired
`chameleon_lab` era without weakening current admission.

## Premise dispositions at base 67d66bf20d7701d339ab2554ac2090bae78ec483

- The defect is **live** at this base. `git log 305b76608..base` over
  `scripts/ci/{change_scope,test_scope,batch_controller,batch_runtime,report_runtime,review_merge_map,review_merge_map_reader,review_failure_report}.py`
  is empty: no merged successor fix exists. `change_scope._validate_policy`
  (`scripts/ci/change_scope.py:324`) still requires
  `tuple(lanes) == _CANONICAL_LANES`, the exact `_CANONICAL_LANE_JOBS` mapping
  and the exact `_CANONICAL_SELF_HOSTED_JOBS` set, with no opt-in tolerance,
  and every `policy_at`/`parse_policy` callsite is strict.
- PR #1997 (merge `305b76608`, 2026-10-10T17:06:46Z) removed the
  `chameleon_lab` lane from the canonical tuple, lane jobs, self-hosted set
  and routing rules. Verified pre-removal facts from `git show
  305b76608^:scripts/ci/change_scope.py` and
  `305b76608^:scripts/ci/scope_policy.json` / `self_test_policy.json`:
  - canonical lanes tuple position: between `deploy_contract` and `package`
    (index 12 of 14);
  - lane jobs: `"chameleon_lab": ("chameleon-lab",)`;
  - canonical self-hosted set: `chameleon-lab` between `deploy-contract` and
    `package`;
  - routing rules naming the lane: `demos/chameleon-lab/` and
    `apps/chameleon-lab/` prefixes (`["portal", "chameleon_lab"]`, the latter
    with a note) and exact `scripts/chameleon-lab.sh` (`["chameleon_lab"]`);
  - self-test inventory suite `chameleon_lab` between `deploy_contract` and
    `package`; `test_scope_policy.json` is byte-identical across the removal.
- The failure path is confirmed in the code: scheduler journal replay calls
  `GitInputs.policy_at(request["control"])` (`batch_controller.py:134`) →
  `test_scope.parse_policy` → `change_scope._validate_policy`, so every
  pre-#1997 control raises `ValueError("lanes do not match the closed v1
  allowlist")`, wrapped as `test_scope.ScopeError` (`test_scope.py:75`). A
  read-only replay via `report_runtime.scheduler_state` reproduces exactly
  that error (done 2026-10-11; not repeated here).
- `self_test.parse_policy` validates suite shape only and never consults the
  canonical lane registry, so the pre-#1997 inventory (which still contains
  the `chameleon_lab` suite) needs no change; the `test_scope.parse_policy`
  routing↔inventory cross-check (`test_scope.py:90-95`) is era-consistent and
  stays unchanged.
- `ScopePolicy.digest` is `self_test.digest_of` over the three raw documents
  (`test_scope.py:103-104`), independent of validation mode, so a tolerant
  parse preserves digest semantics and historical digest comparisons
  (`batch_runtime.py:376`) still match.

## Declared files

- `scripts/ci/change_scope.py`
- `scripts/ci/test_scope.py`
- `scripts/ci/batch_controller.py`
- `scripts/ci/batch_runtime.py`
- `scripts/ci/report_runtime.py`
- `scripts/ci/review_merge_map.py`
- `scripts/ci/review_merge_map_reader.py`
- `scripts/ci/review_failure_report.py`
- `tests/build/ci_change_scope_test.py`
- `tests/build/ci_test_scope_test.py`
- `tests/build/ci_batch_controller_test.py`
- `tests/build/ci_batch_runtime_test.py`
- `docs/plans/2026-10-11-lmdj-scheduler-replay-retired-lane-policy.md`
- `.agents/pitfalls/retired-lane-breaks-historical-policy-replay.md`

## Behavior

`change_scope.py` gains a closed retired-lane registry recording each retired
lane's exact pre-removal facts — the current canonical lane before which it
stood, its lane jobs, and the subset of those jobs the canonical self-hosted
set held (initially only `chameleon_lab`: before `package`, jobs
`("chameleon-lab",)`, all self-hosted). `_validate_policy` gains an opt-in
keyword `allow_retired_lanes=False`. Strict mode is byte-for-byte unchanged.
Tolerant mode requires the policy lanes to equal the current canonical tuple
with any subset of retired lanes interleaved at their recorded historical
positions; shared lanes' jobs must match the current mapping exactly, retired
entries must match the registry, and the self-hosted set must equal the
canonical set plus the registered self-hosted jobs of the retired lanes
present. Every other check (schemas, rules, full rules, expensive families,
draft lanes, SLOs) is unchanged; era routing rules naming a retired lane keep
passing the unchanged subset check against the era lane set.

`test_scope.parse_policy` and `GitInputs.policy_at` gain the same opt-in
keyword, default strict. The `GitInputs` policy cache is keyed by
`(control, allow_retired_lanes)` so a tolerant replay parse can never satisfy
a later strict admission read of the same control.

Callsite classification (every `policy_at`/`parse_policy` consumer audited):

| Callsite | Mode | Reason |
| --- | --- | --- |
| `batch_controller.py:134` (`_replay`) | tolerant | historical reconstruction of journal enqueue/admit events |
| `batch_controller.py:80` (`interval_selection`) | strict (unchanged) | errors are already swallowed to `None`, and `select_across_policies` falls back to full whenever an old policy's suite set differs from current — a retired-era policy always differs, so tolerance there cannot narrow a new selection |
| `batch_controller.py:209` (current control) | strict | current admission |
| `batch_controller.py:218` (explicit enqueue) | strict | admits NEW execution; an explicit request under a retired-era control is refused fail-closed and must be re-issued under a current control, because the retired lane's job no longer exists in `ci.yml` |
| `batch_controller.py:248` (queued admit) | strict | admits NEW execution under the queued request's control; same fail-closed reasoning as `:218` |
| `batch_runtime.py:374` (`result_for` policy) | tolerant | validates already-executed evidence against its era policy |
| `batch_runtime.py:376` (candidate digest comparison) | tolerant | historical reconstruction; digest over raw documents is mode-independent |
| `batch_runtime.py:455`, `:478` (`self.control`) | strict | current-control admission/preflight |
| `report_runtime.py:57` (`runtime.control`) | strict | current control identity (`GITHUB_SHA` of the live run); replay default policy, never an era read |
| `report_runtime.py:124`, `:256`, `:295` | tolerant | report-side replay/reconstruction over historical request controls |
| `review_merge_map_reader.py:93` | strict | current control |
| `review_merge_map_reader.py:96` | tolerant | historical scope-record control |
| `review_merge_map.py:122` via `policy_at` | tolerant | historical scope-record control (beyond the briefing's list; same defect class) |
| `review_failure_report.py:331` | tolerant | validates an archived review run against its historical control (beyond the briefing's list; same defect class) |
| `change_scope.py:406`, `:602`, `:869`, `:961` | strict (unchanged) | current policy load/classify/manifest validation; `:869` reads a merge-base policy but fails closed to `None` (full upgrade) and tolerance there could narrow current admission |

`batch.reduce` receives the tolerant era policy for historical enqueue/admit
events, so era selections naming `chameleon_lab` validate against the era
suite inventory end-to-end (`incremental_batch._request` rebuilds the request
under that same policy and the recorded policy digest still matches).

## Verification

Failing tests first, then implementation:

- `tests/build/ci_change_scope_test.py`: the registry pins `chameleon_lab`'s
  exact historical position/jobs/self-hosted facts; strict validation still
  rejects the era-faithful document; tolerant validation accepts exactly the
  era-faithful document and rejects a wrong retired job tuple, a retired lane
  at the wrong position, an unknown extra lane, a missing current lane, and a
  missing retired self-hosted job; a current-era document still parses under
  tolerant mode.
- `tests/build/ci_test_scope_test.py`: era documents (routing + inventory +
  config, constructed from the current documents plus exactly the verified
  pre-#1997 deltas) fail `parse_policy` strict with `invalid upstream policy:
  lanes do not match the closed v1 allowlist` and parse with
  `allow_retired_lanes=True`; the tolerant policy's digest equals
  `digest_of` over the raw era documents; non-registry variations stay
  rejected; an era selection naming `chameleon_lab` round-trips through
  `incremental_batch.make_request`/`_request` under the tolerant policy.
- `tests/build/ci_batch_controller_test.py`: a real-Git replay regression —
  a temp repository whose first commit carries the era documents and whose
  tip carries the current documents; a journal with an observe/admit/claim/
  result/advance history whose request freezes the era control replays
  successfully and yields `processed == era control`; the strict admission
  read of the same era control still fails closed.

Then: the four focused suites, the complete
`python3 -m unittest discover -s tests/build -p 'ci_*_test.py'` run (the CI
invocation from `.github/workflows/ci.yml:305`), and the staged ownership
gate `python3 tests/build/ci_change_scope_test.py` (the two new non-Python
files land under the existing `docs/` and `.agents/` prefix rules; verified
by the gate itself).

## Version Management

Version impact: none
Reason: CI control-plane parsing only; no Product, Host, Module, Contract,
Assembly, tag, allocation or snapshot identity changes.

## Documentation Impact

Documentation impact: none
Reason: `apps/docs-site/docs/operations/testing-and-proof.mdx` documents
suite inventories, scheduler/report operations and recovery commands, none of
which change — the suite inventory, workflows, operations and current
admission contract are untouched, and the retired-lane tolerance is an
internal historical-replay parsing detail the page never states.
