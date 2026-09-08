# LMDJ CI Heavy Failure Short-Circuit Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop selected native-heavy CI work before it starts after a gating preflight failure, and stop later selected native-heavy jobs after the first selected heavy failure while preserving exact failure evidence and the final PR Gate verdict.

**Architecture:** A pure Hosted `Pre-heavy Gate` validates the eight non-macOS preflight results against the existing scope manifest and policy. The five `lmdj-native-heavy` jobs then form a sparse, scope-aware sequence `Portal -> Core Ubuntu -> Package -> Coverage -> ASan`; the existing PR Gate remains the sole aggregate verdict and adds primary-failure, unexpected-skip, downstream-blocked, and scope-skip diagnostics. macOS remains parallel and is adjudicated only by PR Gate.

**Tech Stack:** GitHub Actions YAML, Python 3.11 standard library, `unittest`, actionlint `1.7.12`, Markdown, Docusaurus/MDX.

## Global Constraints

- Work only on `fix/ci-heavy-failure-short-circuit` in `/Users/endaye/Projects/lmdj/.worktrees/ci-fail-fast-design`; never modify or commit on `main`.
- Treat this workflow/script/test/documentation migration as one repository Task and create one final Conventional Commit for all files changed in this user turn.
- Gating preflight jobs are exactly `docs-static`, `ci-contract`, `deploy-contract`, `chameleon-lab`, `web-toolchain-conformance`, `web-runtime-host`, `creator-web`, and `web-runtime-lab`.
- The macOS selector, primary, fallback, `core-macos`, and `core-asan-macos` remain outside `Pre-heavy Gate`; their selected semantic failure does not block Linux native-heavy work and still fails PR Gate.
- Native-heavy order is exactly `portal`, `core-ubuntu`, `package`, `core-coverage`, `core-asan`.
- Every selected gating preflight result must be `success`; every unselected gating preflight result must be `skipped`; missing, extra, unknown, malformed, or selected-but-skipped input fails closed.
- A selected heavy job may start only after `pre-heavy-gate=success` and every earlier selected heavy job succeeded; an earlier unselected heavy job is a legal skip and does not block it.
- Keep `lmdj-native-heavy`, `queue: max`, and `cancel-in-progress: false` on all five heavy jobs. Do not add workflow permissions, retry semantic work, call the Actions cancel API, or change runner routing.
- `PR Gate` remains the only aggregate pass/fail decision. `pre-heavy-gate` is a support dependency, not a new formal result key in `scope_policy.json`.
- Every new fail-closed diagnostic must state both `why` and `remedy`, following `.agents/pitfalls/gate-failure-readability.md`.
- Preserve logs, failure artifacts, Playwright traces, coverage reports, ccache statistics, cleanup steps, exact base/head validation, queue metadata, trust rules, macOS fallback, and release evidence semantics.
- Version impact: none. This Task changes internal CI orchestration, diagnostics, tests, and current documentation only; it allocates no Product Build, Module, Host, Provider, Contract, Channel, or release identity.
- Documentation impact: required for `/operations/testing-and-proof`; update `docs/quality/core-test-policy.md` and the current Portal page, and create no immutable Portal snapshot.
- A local commit does not authorize push, Pull Request creation, merge, remote run cancellation, deployment, release, publication, or Channel promotion.

---

### Task 1: Atomically add the phase gate, sparse heavy chain, adjudication diagnostics, and current documentation

**Files:**
- Create: `docs/plans/2026-08-31-lmdj-ci-heavy-failure-short-circuit.md`
- Create: `scripts/ci/phase_gate.py`
- Create: `tests/build/ci_phase_gate_test.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/ci/pr_gate.py`
- Modify: `tests/build/ci_pr_gate_test.py`
- Modify: `tests/build/ci_workflow_topology_test.py`
- Modify: `tests/build/ci_build_acceleration_test.py`
- Modify: `docs/quality/core-test-policy.md`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

**Interfaces:**
- Consumes: `scripts/ci/change_scope.py` manifest validation and `scripts/ci/scope_policy.json` lane-to-job ownership without changing either file.
- Produces: `GATING_JOBS`, `HEAVY_JOBS`, `PhaseGateReport`, `normalize_needs()`, `validate_phase_gate()`, and `render_summary()` in `scripts/ci/phase_gate.py`.
- `validate_phase_gate(policy, manifest, results, *, change_scope_result="success") -> PhaseGateReport` accepts normalized job-id/result strings and never reads network or runner state.
- `PhaseGateReport` contains `ok`, `errors`, `primary_failures`, `unexpected_skips`, and `scope_skips`, all immutable tuples.
- Extends `scripts/ci/pr_gate.py::validate_gate(policy, manifest, results, expected_head_sha, *, expected_base_sha, change_scope_result="success", expected_queue=None, pre_heavy_gate_result="success") -> GateReport` without weakening its selected-success/unselected-skipped truth table.
- Extends `GateReport` with immutable `primary_failures`, `unexpected_skips`, `downstream_blocked`, and `scope_skips` tuples used only for diagnosis; `ok` remains derived from the existing closed verdict errors.
- Workflow passes `needs.pre-heavy-gate.result` separately to PR Gate; it never inserts `pre-heavy-gate` into `FORMAL_RESULTS_JSON` or `scope_policy.json`.

- [x] **Step 1: Write the pure phase-gate tests first**

Create `tests/build/ci_phase_gate_test.py`. Load `phase_gate.py` with the same `importlib.util` pattern used by `ci_pr_gate_test.py`, load the real policy, and build valid manifests through `change_scope.classify(policy, (), base_sha=BASE_SHA, head_sha=HEAD_SHA, event_name="workflow_dispatch", draft=False, labels=(), requested_lanes=lanes, trusted_head=trusted_head)` so the tests exercise the production manifest validator rather than hand-waving schema validity.

The test helper must expose this shape:

```python
def requested_manifest(module, policy, lanes, *, trusted_head=True):
    return module.change_scope.classify(
        policy,
        (),
        base_sha="b" * 40,
        head_sha="a" * 40,
        event_name="workflow_dispatch",
        draft=False,
        labels=(),
        requested_lanes=lanes,
        trusted_head=trusted_head,
    )

def expected_results(module, manifest):
    selected = set(manifest["required_jobs"])
    return {
        job: "success" if job in selected else "skipped"
        for job in module.GATING_JOBS
    }
```

Cover all of these exact behaviors:

```python
class PhaseGateTest(unittest.TestCase):
    def test_exact_gating_sets_are_closed(self):
        self.assertEqual(self.module.GATING_JOBS, (
            "docs-static", "ci-contract", "deploy-contract", "chameleon-lab",
            "web-toolchain-conformance", "web-runtime-host", "creator-web",
            "web-runtime-lab",
        ))
        self.assertEqual(self.module.HEAVY_JOBS, (
            "portal", "core-ubuntu", "package", "core-coverage", "core-asan",
        ))

    def test_selected_success_and_unselected_skip_pass(self):
        manifest = requested_manifest(self.module, self.policy, ("docs_static",))
        report = self.module.validate_phase_gate(
            self.policy, manifest, expected_results(self.module, manifest)
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.scope_skips, tuple(sorted(
            set(self.module.GATING_JOBS) - {"docs-static"}
        )))

    def test_selected_failure_cancel_and_skip_fail_closed(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static",)
        )
        for result in ("failure", "cancelled", "skipped"):
            with self.subTest(result=result):
                results = expected_results(self.module, manifest)
                results["docs-static"] = result
                report = self.module.validate_phase_gate(
                    self.policy, manifest, results
                )
                self.assertFalse(report.ok)
                if result == "skipped":
                    self.assertEqual(report.unexpected_skips, ("docs-static",))
                    self.assertEqual(report.primary_failures, ())
                else:
                    self.assertEqual(report.primary_failures, ("docs-static",))
                    self.assertEqual(report.unexpected_skips, ())
                self.assertTrue(report.errors)
                self.assertTrue(all(
                    "why:" in error and "remedy:" in error
                    for error in report.errors
                ))

    def test_unselected_job_that_runs_fails_closed(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static",)
        )
        for result in ("success", "failure", "cancelled"):
            with self.subTest(result=result):
                results = expected_results(self.module, manifest)
                results["ci-contract"] = result
                report = self.module.validate_phase_gate(
                    self.policy, manifest, results
                )
                self.assertFalse(report.ok)
                self.assertNotIn("ci-contract", report.scope_skips)
                self.assertIn("why:", report.errors[0])
                self.assertIn("remedy:", report.errors[0])

    def test_untrusted_selected_gating_skip_is_unexpected(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static",), trusted_head=False
        )
        results = expected_results(self.module, manifest)
        results["docs-static"] = "skipped"
        report = self.module.validate_phase_gate(
            self.policy, manifest, results
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.unexpected_skips, ("docs-static",))
        self.assertNotIn("docs-static", report.scope_skips)

    def test_change_scope_result_and_closed_json_shape_fail_closed(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static",)
        )
        valid = expected_results(self.module, manifest)
        cases = []
        missing = dict(valid)
        del missing["docs-static"]
        cases.append(missing)
        cases.append(dict(valid, invented={"result": "skipped"}))
        cases.append(dict(valid, **{"docs-static": "unknown"}))
        for results in cases:
            with self.subTest(results=results):
                self.assertFalse(self.module.validate_phase_gate(
                    self.policy, manifest, results
                ).ok)
        self.assertFalse(self.module.validate_phase_gate(
            self.policy, manifest, valid, change_scope_result="failure"
        ).ok)
        invalid_manifest = dict(manifest, invented=True)
        self.assertFalse(self.module.validate_phase_gate(
            self.policy, invalid_manifest, valid
        ).ok)
        self.assertFalse(self.module.validate_phase_gate(
            self.policy, manifest, []
        ).ok)
        with self.assertRaises(ValueError):
            self.module._load_json('{"x":1,"x":2}')

    def test_summary_uses_display_names_and_closed_categories(self):
        manifest = requested_manifest(
            self.module, self.policy, ("docs_static", "ci_contract")
        )
        results = expected_results(self.module, manifest)
        results["docs-static"] = "failure"
        results["ci-contract"] = "skipped"
        report = self.module.validate_phase_gate(
            self.policy, manifest, results
        )
        summary = self.module.render_summary(report)
        self.assertIn("| Result | fail |", summary)
        self.assertIn("Docs / static (`docs-static`)", summary)
        self.assertIn("CI contract (`ci-contract`)", summary)
        self.assertIn("Primary failure", summary)
        self.assertIn("Unexpected skip", summary)
        self.assertIn("Scope skip", summary)
        self.assertIn("why:", summary)
        self.assertIn("remedy:", summary)
```

- [x] **Step 2: Run the new phase-gate tests and observe RED**

Run:

```bash
python3 tests/build/ci_phase_gate_test.py
```

Expected: FAIL because `scripts/ci/phase_gate.py` does not exist. Preserve this output in the task report as the TDD RED evidence.

- [x] **Step 3: Implement the minimal pure phase gate and make it GREEN**

Create `scripts/ci/phase_gate.py` using only the Python standard library. Dynamically load `change_scope.py` exactly as `pr_gate.py` does. Define:

```python
FORMAL_RESULTS = frozenset({"success", "failure", "cancelled", "skipped"})
GATING_JOBS = (
    "docs-static", "ci-contract", "deploy-contract", "chameleon-lab",
    "web-toolchain-conformance", "web-runtime-host", "creator-web",
    "web-runtime-lab",
)
HEAVY_JOBS = (
    "portal", "core-ubuntu", "package", "core-coverage", "core-asan",
)

@dataclass(frozen=True)
class PhaseGateReport:
    ok: bool
    errors: tuple[str, ...]
    primary_failures: tuple[str, ...]
    unexpected_skips: tuple[str, ...]
    scope_skips: tuple[str, ...]
```

`validate_phase_gate` must first call `change_scope._validate_policy(policy)` and `change_scope.validate_manifest(manifest, policy)`. It derives selected gating jobs as `set(manifest["required_jobs"]) & set(GATING_JOBS)`, requires the result key set to equal `GATING_JOBS`, and applies:

```python
if selected and result == "success":
    pass
elif selected and result in {"failure", "cancelled"}:
    primary_failures.append(job)
elif selected and result == "skipped":
    unexpected_skips.append(job)
elif not selected and result == "skipped":
    scope_skips.append(job)
else:
    errors.append(topology_contradiction(job, result))
```

Every invalid-input and non-success error must contain literal `why:` and `remedy:` clauses. `render_summary` displays job display names plus job IDs and never guesses a root cause. The CLI takes `--policy`, `--manifest-json`, `--results-json`, `--change-scope-result`, and `--summary`, writes the summary even on invalid input, prints errors to stderr, and exits 0 only when `report.ok`.

Run:

```bash
python3 tests/build/ci_phase_gate_test.py
python3 -m py_compile scripts/ci/phase_gate.py
```

Expected: all phase-gate tests pass and compilation exits 0.

- [x] **Step 4: Write failing workflow topology and PR Gate classification tests**

Before editing workflow or `pr_gate.py`, modify the three existing contract suites.

In `ci_workflow_topology_test.py` add exact constants:

```python
GATING_PREFLIGHT_JOBS = (
    "docs-static", "ci-contract", "deploy-contract", "chameleon-lab",
    "web-toolchain-conformance", "web-runtime-host", "creator-web",
    "web-runtime-lab",
)
HEAVY_JOBS = (
    "portal", "core-ubuntu", "package", "core-coverage", "core-asan",
)
```

Add tests proving:

- `pre-heavy-gate` is a fourth Hosted Ubuntu control-plane job with timeout 3, `if: ${{ !cancelled() }}`, exact static needs `{change-scope, *GATING_PREFLIGHT_JOBS}`, no role label, no workflow permission increase, and an exact eight-key result JSON.
- macOS selector/primary/fallback/adjudicators are absent from the phase-gate needs and JSON.
- PR Gate needs `pre-heavy-gate` in addition to `change-scope` and the 17 formal results, passes `needs.pre-heavy-gate.result` separately, and keeps the formal result JSON at 17 keys.
- Every heavy job directly needs `change-scope`, `pre-heavy-gate`, and every earlier heavy job; no heavy job needs a later heavy job.
- Every heavy job condition contains its own lane, trusted-head, `needs.pre-heavy-gate.result == 'success'`, and for every earlier heavy job the sparse rule `!lane_selected || needs.<earlier>.result == 'success'`.
- `portal` retains its reusable `uses:` shape and carries the same gate/sequence contract without a caller `runs-on`.
- `select-macos-runner` still needs only `change-scope`; no macOS job needs `pre-heavy-gate` or a heavy job.
- Workflow-level cancellation semantics and PR Gate `always() && !cancelled()` remain unchanged.

Update the existing role/topology assertions whose comments or exact `needs:` spelling assume every heavy job needs only `change-scope`; do not relax role, trust, lane, or job-count assertions.

In `ci_build_acceleration_test.py`, retain the five exact `lmdj-native-heavy` concurrency blocks and add the exact heavy sequence. Update string assertions that only recognize scalar `needs: change-scope` so list-form heavy dependencies are accepted without weakening ccache, role, `queue: max`, or `cancel-in-progress: false` checks.

In `ci_pr_gate_test.py`, add tests for:

```python
def test_primary_downstream_and_scope_categories_do_not_change_verdict(self):
    manifest = self.manifest(tuple(self.policy["lanes"]))
    results = self.matching_results(manifest)
    results["creator-web"] = "failure"
    for job in self.module.HEAVY_JOBS:
        results[job] = "skipped"
    report = self.module.validate_gate(
        self.policy, manifest, results, HEAD_SHA,
        expected_base_sha=OTHER_HEAD_SHA,
        pre_heavy_gate_result="failure",
    )
    self.assertFalse(report.ok)
    self.assertIn("creator-web", report.primary_failures)
    self.assertEqual(report.downstream_blocked, self.module.HEAVY_JOBS)
    self.assertEqual(report.unexpected_skips, ())

def test_heavy_failure_blocks_only_later_selected_heavy_jobs(self):
    manifest = requested_manifest(
        self.module, self.policy,
        ("portal", "core_ubuntu", "core_coverage", "core_asan"),
    )
    results = self.matching_results(manifest)
    results["core-ubuntu"] = "failure"
    results["core-coverage"] = "skipped"
    results["core-asan"] = "skipped"
    report = self.module.validate_gate(
        self.policy, manifest, results, HEAD_SHA,
        expected_base_sha=OTHER_HEAD_SHA,
        pre_heavy_gate_result="success",
    )
    self.assertEqual(report.primary_failures, ("core-ubuntu",))
    self.assertEqual(
        report.downstream_blocked, ("core-coverage", "core-asan")
    )
    self.assertIn("package", report.scope_skips)

def test_selected_heavy_skip_without_a_blocker_is_unexpected(self):
    manifest = requested_manifest(
        self.module, self.policy, ("portal", "core_ubuntu")
    )
    results = self.matching_results(manifest)
    results["core-ubuntu"] = "skipped"
    report = self.module.validate_gate(
        self.policy, manifest, results, HEAD_SHA,
        expected_base_sha=OTHER_HEAD_SHA,
        pre_heavy_gate_result="success",
    )
    self.assertEqual(report.unexpected_skips, ("core-ubuntu",))
    self.assertEqual(report.downstream_blocked, ())

def test_macos_failure_is_primary_but_does_not_block_heavy(self):
    manifest = self.manifest(tuple(self.policy["lanes"]))
    results = self.matching_results(manifest)
    results["core-macos"] = "failure"
    report = self.module.validate_gate(
        self.policy, manifest, results, HEAD_SHA,
        expected_base_sha=OTHER_HEAD_SHA,
        pre_heavy_gate_result="success",
    )
    self.assertFalse(report.ok)
    self.assertIn("core-macos", report.primary_failures)
    self.assertEqual(report.downstream_blocked, ())
    self.assertTrue(all(
        results[job] == "success" for job in self.module.HEAVY_JOBS
    ))

def test_unselected_macos_skip_is_scope_skip(self):
    report = self.validate()
    self.assertTrue(report.ok)
    self.assertIn("core-macos", report.scope_skips)
    self.assertIn("core-asan-macos", report.scope_skips)

def test_pre_heavy_result_is_required_but_not_a_formal_result_key(self):
    manifest = self.manifest(lanes={"docs_static"})
    results = self.matching_results(manifest)
    for result in ("failure", "cancelled", "skipped", "unknown"):
        with self.subTest(result=result):
            report = self.module.validate_gate(
                self.policy, manifest, results, HEAD_SHA,
                expected_base_sha=OTHER_HEAD_SHA,
                pre_heavy_gate_result=result,
            )
            self.assertFalse(report.ok)
    self.assertEqual(set(results), set(VALID_RESULTS))
    self.assertNotIn("pre-heavy-gate", results)
```

- [x] **Step 5: Run the focused contracts and observe RED**

Run:

```bash
python3 -m unittest \
  tests.build.ci_pr_gate_test \
  tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test
```

Expected: FAIL because `pre-heavy-gate`, the heavy dependency chain, and PR Gate diagnostic fields do not exist. Preserve the expected failures in the task report.

- [x] **Step 6: Extend PR Gate diagnostics without changing its truth table**

In `scripts/ci/pr_gate.py`, add the exact heavy order, the four diagnostic tuples, and immutable `observed_results` job/result tuples to `GateReport`, keeping defaults only where needed by existing fail-closed construction sites. Add keyword-only `pre_heavy_gate_result: str = "success"` to `validate_gate` and require it to be one of the four formal results and exactly `success` for an ordinary non-cancelled adjudication.

Classify known formal results after validating the closed key set:

```python
selected = set(requested)
primary = sorted(
    job for job in selected
    if results.get(job) in {"failure", "cancelled"}
)
scope_skips = sorted(
    job for job in skipped if results.get(job) == "skipped"
)

blocked = pre_heavy_gate_result != "success"
downstream = []
unexpected = []
for job in HEAVY_JOBS:
    if job not in selected:
        continue
    result = results.get(job)
    if result == "skipped":
        if blocked:
            downstream.append(job)
        else:
            unexpected.append(job)
            blocked = True
    elif result in {"failure", "cancelled"}:
        blocked = True

for job in sorted(selected - set(HEAVY_JOBS)):
    if results.get(job) == "skipped":
        unexpected.append(job)
```

Retain the existing generic verdict errors (`selected job JOB is RESULT, expected success`, `unselected job JOB is RESULT, expected skipped`) so external behavior does not weaken. `render_summary` adds one row for each non-empty category and explicitly renders `none` for an empty category; every observed category entry renders the canonical workflow display name, exact job ID, and observed result. The CLI adds required `--pre-heavy-gate-result` and passes it into `validate_gate`. Regression coverage includes a middle unexpected selected-heavy skip followed by a downstream-selected skip, a middle cancelled selected-heavy job followed by a downstream-selected skip, and exact category rendering for primary failure, unexpected skip, downstream blocked, and scope skip.

If `pre-heavy-gate` is non-success while an earlier selected formal gating job already reports failure/cancelled/unexpected skip, do not list the aggregate gate as a second primary workload failure. Its scalar result still produces a fail-closed control-plane error and explains why selected heavy skips are downstream blocked.

- [x] **Step 7: Add the Hosted phase gate and sparse heavy workflow chain**

In `.github/workflows/ci.yml`, add:

```yaml
  pre-heavy-gate:
    name: Pre-heavy Gate
    needs: [change-scope, docs-static, ci-contract, deploy-contract, chameleon-lab, web-toolchain-conformance, web-runtime-host, creator-web, web-runtime-lab]
    if: ${{ !cancelled() }}
    runs-on: ubuntu-24.04
    timeout-minutes: 3
    steps:
      - uses: actions/checkout@v6
      - name: Admit native-heavy work after selected preflight success
        env:
          PREFLIGHT_RESULTS_JSON: >-
            {"docs-static":{"result":"${{ needs.docs-static.result }}"},"ci-contract":{"result":"${{ needs.ci-contract.result }}"},"deploy-contract":{"result":"${{ needs.deploy-contract.result }}"},"chameleon-lab":{"result":"${{ needs.chameleon-lab.result }}"},"web-toolchain-conformance":{"result":"${{ needs.web-toolchain-conformance.result }}"},"web-runtime-host":{"result":"${{ needs.web-runtime-host.result }}"},"creator-web":{"result":"${{ needs.creator-web.result }}"},"web-runtime-lab":{"result":"${{ needs.web-runtime-lab.result }}"}}
          SCOPE_MANIFEST: ${{ needs.change-scope.outputs.manifest }}
          CHANGE_SCOPE_RESULT: ${{ needs.change-scope.result }}
        run: >-
          python3 scripts/ci/phase_gate.py
          --policy scripts/ci/scope_policy.json
          --manifest-json "$SCOPE_MANIFEST"
          --results-json "$PREFLIGHT_RESULTS_JSON"
          --change-scope-result "$CHANGE_SCOPE_RESULT"
          --summary "$GITHUB_STEP_SUMMARY"
```

Change heavy job dependencies and conditions to the exact sequence. Each job lists all earlier heavy jobs, not only its immediate predecessor, so its expression can distinguish legal scope skips from a failed selected predecessor. The final ASan shape is the complete example:

```yaml
    needs: [change-scope, pre-heavy-gate, portal, core-ubuntu, package, core-coverage]
    if: >-
      ${{
        !cancelled()
        && needs.pre-heavy-gate.result == 'success'
        && fromJSON(needs.change-scope.outputs.manifest).lanes.core_asan
        && needs.change-scope.outputs.trusted-head == 'true'
        && (!fromJSON(needs.change-scope.outputs.manifest).lanes.portal || needs.portal.result == 'success')
        && (!fromJSON(needs.change-scope.outputs.manifest).lanes.core_ubuntu || needs.core-ubuntu.result == 'success')
        && (!fromJSON(needs.change-scope.outputs.manifest).lanes.package || needs.package.result == 'success')
        && (!fromJSON(needs.change-scope.outputs.manifest).lanes.core_coverage || needs.core-coverage.result == 'success')
      }}
```

Apply the same prefix rule to Portal, Core Ubuntu, Package, and Coverage. Keep every workload step, runner label, timeout, artifact, cleanup/statistics step, and concurrency block byte-for-byte unless dependency/condition formatting requires movement.

Add `pre-heavy-gate` to PR Gate `needs`, add `PRE_HEAVY_GATE_RESULT: ${{ needs.pre-heavy-gate.result }}`, and pass `--pre-heavy-gate-result "$PRE_HEAVY_GATE_RESULT"`. Do not add it to `FORMAL_RESULTS_JSON`.

- [x] **Step 8: Run focused tests and make the workflow/diagnostics GREEN**

Run:

```bash
python3 -m unittest \
  tests.build.ci_phase_gate_test \
  tests.build.ci_pr_gate_test \
  tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test
```

Expected: all focused tests pass with zero failures and no warnings. If a test fails, fix production behavior rather than weakening the exact set, trust, sparse-scope, or truth-table assertions.

- [x] **Step 9: Update current CI policy and Portal documentation**

Update `docs/quality/core-test-policy.md` and `apps/architecture-portal/docs/operations/testing-and-proof.mdx` with the same facts:

- Eight non-macOS preflight jobs complete in parallel before Hosted `Pre-heavy Gate` decides whether native-heavy work is admitted.
- macOS remains parallel and outside that gate; selected macOS failure remains a PR Gate primary failure but does not block Linux heavy work.
- The five heavy jobs retain one repository-wide `queue: max` capacity group and use the exact sparse order Portal, Core Ubuntu, Package, Coverage, ASan.
- A gating or earlier selected heavy failure produces downstream skips, not extra product failures; legal unselected skips remain scope skips.
- PR Gate still requires selected success/unselected skip and remains the only aggregate verdict; `pre-heavy-gate` is a support dependency outside the 17 formal result keys.
- Hosted control-plane job count is now four: Change Scope, Pre-heavy Gate, PR Gate, and macOS selector. The two macOS adjudicators remain Hosted non-workload jobs.
- Green-run timing must separate runner queue, gating execution, Gate ready, native-heavy global-slot wait, heavy execution, and end-to-end span. A 75-minute Web Runtime Host execution timeout is not an upper bound on Gate wait.
- No API cancellation, workflow permission increase, retry, runner change, Product Build allocation, or immutable Portal snapshot is introduced.

Do not rewrite unrelated historical capacity, release, or physical-acceptance evidence.

- [x] **Step 10: Run the complete local verification required by the specification**

Run fresh, in this order:

```bash
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
python3 -m py_compile scripts/ci/phase_gate.py scripts/ci/pr_gate.py
bash tests/build/test_active_tree.sh
PATH=/opt/homebrew/opt/node@22/bin:$PATH scripts/architecture-portal.sh check
```

Then run the workflow's pinned actionlint contract from a temporary directory, preserving its one approved schema-lag exception:

```bash
tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "$tmp_dir"' EXIT
curl --fail --silent --show-error --location \
  --output "$tmp_dir/actionlint.tar.gz" \
  https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz
printf '%s  %s\n' \
  8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 \
  "$tmp_dir/actionlint.tar.gz" | shasum -a 256 --check
tar -xzf "$tmp_dir/actionlint.tar.gz" -C "$tmp_dir" actionlint
"$tmp_dir/actionlint" \
  -ignore 'unexpected key "queue" for "concurrency" section'
```

Expected: every command exits 0; all CI contracts pass; Portal reports all tests/docs/diagrams/facts/build routes valid; actionlint emits no unignored diagnostics.

- [x] **Step 11: Apply the pitfall and atomic-commit gates**

Re-read `.agents/pitfalls/gate-failure-readability.md` and `.agents/pitfalls/github-concurrency-pending-replacement.md`. This Task applies their existing absorbed guidance and tests rather than recording a new recurrence: the observed problem is the new short-circuit feature request, not a failure of either existing exit mechanism. Confirm no other open `area: ci-release` entry describes a newly recurring invariant; if evidence proves one does, follow `issue-done` before committing.

Inspect the exact changed-file set and require it to equal the ten declared files above. Then run:

```bash
git diff --check
git status --short
git add \
  docs/plans/2026-08-31-lmdj-ci-heavy-failure-short-circuit.md \
  scripts/ci/phase_gate.py \
  tests/build/ci_phase_gate_test.py \
  .github/workflows/ci.yml \
  scripts/ci/pr_gate.py \
  tests/build/ci_pr_gate_test.py \
  tests/build/ci_workflow_topology_test.py \
  tests/build/ci_build_acceleration_test.py \
  docs/quality/core-test-policy.md \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --name-status
git diff --cached --check
```

Expected: only the declared Task files are staged and the cached diff has no whitespace errors.

Commit once:

```bash
git commit -m "fix(ci): short-circuit doomed native-heavy work"
```

After commit, inspect:

```bash
git show --name-status --stat --oneline HEAD
git status --short --branch
```

Expected: the commit contains only the declared files and the worktree is clean. Stop before push, Pull Request, merge, remote run probes, deployment, release, or publication.
