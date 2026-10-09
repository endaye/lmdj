# Cloudflare Portal Preview broad activation with bounded monthly budget

Relates to #873, #921, #922, #867.

## Background

The migration pilot (#963) proved the isolated exact-head Preview pipeline and was
deactivated on 2026-09-08. The build workflow remains gated on the per-branch
pilot variable `CLOUDFLARE_PREVIEW_PILOT_BRANCH`, so no PR currently receives a
Preview. Three issue rows remain open for the same reason:

- #921: resolve the ongoing monthly hosted allocation and automatic monitoring
  before broad activation;
- #922: demonstrate dependency-complete trigger behavior and measured pilot
  demand before broader previews;
- #867: complete the operational activation boundary.

## Measured demand (evidence base)

- Pilot builds: 179 s, 182 s, 291 s — average ≈ 3.6 minutes per build
  (#921 ledger, runs 34224803448, 34227805535, 34224803448/2).
- September 2026: 822 squash-merged PRs; 1,007 same-repo PR head events on the
  Preview Build workflow; 301 of 822 PRs (37%) touched Preview-relevant inputs
  (classified with this plan's pattern set). Projected demand ≈ 1,007 × 0.37 ×
  3.6 ≈ **1,340 hosted Linux minutes/month**.
- Account Actions usage is already metered beyond included minutes
  (2026-09: net $37.24; 2026-10 to date within included). No paid-plan change
  is involved; Preview usage joins the existing metered consumption.

## Decision

- **Ongoing monthly allocation: 2,000 hosted Linux minutes** for Portal
  Preview builds (`CLOUDFLARE_PREVIEW_BUDGET_MINUTES=2000`). Measured demand is
  ~67% of it; worst-case marginal cost ≈ $14.40/month at the published Linux
  rate. Revoking `CLOUDFLARE_PREVIEW_ENABLED` deactivates Previews instantly.
- Alerts at 50/75/90% of the monthly budget, posted automatically to the
  operations Issue recorded in `CLOUDFLARE_PREVIEW_BUDGET_ISSUE`; new builds
  stop at 90% (fail-closed gate inside the build job). This replaces the
  operator-owned pilot ledger with an automatic monitor.

## Declared files

- `.github/workflows/cloudflare-preview-build.yml` — activation variable,
  dependency-complete `paths:` filter, budget gate step, `actions: read` for
  the gate.
- `.github/workflows/cloudflare-preview-publish.yml` — activation variable.
- `.github/workflows/cloudflare-preview-budget.yml` — new daily automatic
  monitor (alerts only; trusted, no deployment credential).
- `scripts/ci/cloudflare_preview_publish.py` — pilot-branch check becomes the
  activation flag.
- `scripts/ci/cloudflare_preview_budget.py` — new: monthly consumption
  accounting, fail-closed gate, threshold alert ledger.
- `scripts/ci/cloudflare_preview_paths.json` — new: canonical dependency-complete
  Preview input patterns with per-entry evidence.
- `tests/build/ci_cloudflare_preview_workflow_test.py` — updated contracts.
- `tests/build/ci_cloudflare_preview_publish_test.py` — activation env.
- `tests/build/ci_cloudflare_preview_paths_test.py` — new producer/consumer
  coverage proof.
- `tests/build/ci_cloudflare_preview_budget_test.py` — new gate/ledger tests.
- `scripts/ci/scope_policy.json` — ownership/lane rules for the new files.
- `apps/docs-site/docs/operations/documentation-governance.mdx` — current
  activation model.
- `docs/deploy/architecture-portal.md` — runbook state update.

## Design

### Dependency-complete trigger (#922 row)

The `pull_request` trigger gains a `paths:` filter whose canonical copy lives in
`scripts/ci/cloudflare_preview_paths.json`. The set was derived by tracing every
filesystem read of `npm --prefix apps/docs-site run check` that escapes
`apps/docs-site/` (repo-facts projections, changelog generators, test-tier
content asserts, executed shell entry points). Unknown paths cannot be excluded
silently: a new external read requires editing code under `apps/docs-site/`,
which is itself covered, and a new top-level tree fails the coverage test until
explicitly dispositioned. `tests/build/ci_cloudflare_preview_paths_test.py`
asserts set equality between the workflow YAML and the JSON, coverage of every
traced input, liveness of every pattern against `git ls-files`, and a negative
set (core sources, e2e tests, prd docs stay out). Irrelevant PRs then produce no
workflow run at all — zero hosted cost.

### Bounded allocation and automatic monitoring (#921 row)

`cloudflare_preview_budget.py` computes month-to-date consumption from the
Actions API: `run_duration_ms` of every completed Preview Build run since the
UTC month start, plus a full 20-minute timeout reservation for each
in-progress/queued run. Two modes:

- `--gate` (build job, first step, trusted base checkout): exits nonzero with
  `why`/`remedy` once consumption reaches 90% of the monthly budget. Requires
  `CLOUDFLARE_PREVIEW_BUDGET_MINUTES`; a missing/invalid budget fails closed.
- `--report` (daily scheduled workflow, `actions: read` + `issues: write`, no
  deployment credential): posts one comment per newly crossed 50/75/90%
  threshold to the operations Issue, deduplicated by a machine marker
  (`cloudflare-preview-budget:YYYY-MM:NN`).

The build job keeps running untrusted PR code with no secrets; the only new
permission is `actions: read` on the build job, which exposes run metadata
(already public to anyone with repo read access), never artifact contents or
credentials. The publisher keeps its existing credential boundary unchanged.

### Activation model

Both workflows switch from `CLOUDFLARE_PREVIEW_PILOT_BRANCH` (per-branch
pilot) to `CLOUDFLARE_PREVIEW_ENABLED == '1'`. Activation therefore requires
three explicit repository settings: the enabled flag, the monthly budget, and
the alert Issue. External (fork) PRs remain excluded exactly as before.

## Verification

- `python3 tests/build/ci_cloudflare_preview_paths_test.py`
- `python3 tests/build/ci_cloudflare_preview_budget_test.py`
- `python3 tests/build/ci_cloudflare_preview_workflow_test.py`
- `python3 tests/build/ci_cloudflare_preview_publish_test.py`
- `python3 tests/build/ci_cloudflare_preview_artifact_test.py`
- `python3 tests/build/ci_cloudflare_preview_download_test.py`
- `python3 tests/build/ci_change_scope_test.py` (staged new-file ownership)
- `scripts/local-ci.sh --lanes portal` equivalent: `scripts/docs-site.sh check`
  (current portal page changes)

Live acceptance (after merge, separate evidence on the tracking issues):
set the three repository variables, open a Preview-relevant PR, and verify the
exact-head build, trusted publication, immutable version URL, GitHub status on
the same SHA, and the budget ledger comment path; verify an irrelevant PR
produces no run.

## Version Management

Version impact: none. CI/deployment tooling, tests and docs only; no Product,
Module, Provider or Contract identity changes.

## Documentation impact

Documentation impact: required. Affected portal routes:
`/operations/documentation-governance`. The same Task updates the runbook
`docs/deploy/architecture-portal.md`; `scripts/docs-site.sh check` runs before
commit.
