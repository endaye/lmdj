# Tolerate retired job names in historical batch evidence validation

Relates to #1048 (kept open for remote acceptance). Second site of the
retired-identity defect class delivered for policy parsing by #2023.

## Premise dispositions at base 9ffd1f71121a04dbfdb393822a8af72a3ae11ae9

- Policy-parse layer: **delivered** by #2023 (`2099461d7`,
  `_validate_policy(historical=True)`); verified live by a clean local
  read-only replay of the #807 scheduler journal at `9555be7b8` and green
  controller run 38141745640. Not repeated here.
- Evidence-validation layer: **still outstanding**. PR #1997 (`305b76608`)
  also removed `"chameleon-lab": "Chameleon Lab"` from `JOB_NAMES` in
  `scripts/ci/batch_evidence_validation.py`. The controller cannot settle
  active batch `:1000` (executor run 38068960168, terminal): its verdict
  observations name the retired job, so `validate_job_observations`
  fail-closes with `why: product job has no reviewed API name mapping`
  (`batch_evidence_validation.py:84`), reproduced locally at `9ffd1f71`
  via `Runtime.result_for` — the exact `batch-error` at stage `reconcile`
  seen on tick 38145001790. No successor PR or open issue covers this site
  (searched 2026-10-11).
- Shared implementation: `tools/release/batch_evidence.py` imports the same
  `validate_job_observations`; one implementation, one fix.

## Declared files

- `scripts/ci/batch_evidence_validation.py`
- `tests/build/ci_batch_runtime_test.py`
- `tests/build/ci_batch_controller_test.py`
- `tests/build/ci_daily_evidence_test.py`
- `docs/plans/2026-10-11-lmdj-evidence-retired-job-names.md`
- `.agents/pitfalls/retired-identity-breaks-historical-consumers.md`

## Behavior

Add a closed `_RETIRED_JOB_NAMES` registry (initially
`{"chameleon-lab": "Chameleon Lab"}`, the exact pre-#1997 entry) consulted
only as a fallback when `JOB_NAMES` has no mapping. Evidence validation only
ever authenticates already-executed runs, so the registry is a historical
fact table, not an admission list: current admission cannot select a retired
lane because policy parsing (`#2023`), `execution_plan`, and the ci.yml
manifest checks all remain strict. An unknown job name is still rejected
with the same `why`/`remedy`.

## Verification

Failing tests first in `ci_batch_runtime_test.py`:

- a verdict observation for `chameleon-lab` with the exact historical API
  job `Execute incremental batch / Chameleon Lab` validates (currently
  raises the production error);
- an unknown job name still raises `no reviewed API name mapping`;
- the retired registry stays disjoint from `JOB_NAMES` and exactly covers
  the lane retired by #1997.

Then: the focused suite, complete
`python3 -m unittest discover -s tests/build -p 'ci_*_test.py'`, and the
staged ownership gate `python3 tests/build/ci_change_scope_test.py`.
Far-side proof after merge: a controller tick settles batch `:1000` instead
of fail-closing at stage `reconcile`.

## Version Management

Version impact: none
Reason: CI control-plane evidence validation only; no Product, Host, Module,
Contract, Assembly, tag, allocation or snapshot identity changes.

## Documentation Impact

Documentation impact: none
Reason: restores documented controller behavior on historical evidence; no
portal page, diagram, tooling or projected identity changes.
