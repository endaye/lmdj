# Risk-Based CI Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unconditional Pull Request matrix with a fail-closed, path-aware `Change Scope` classifier and one manifest-driven `PR Gate`, while preserving every selected lane's existing semantic and infrastructure behavior.

**Architecture:** A dependency-free Python classifier reads the exact base/head Git diff and a checked-in JSON policy, then emits a closed `lmdj.ci-scope.v1` manifest. Every formal lane and its deterministic selector/primary support jobs are conditionally selected from that manifest and fan into a Python gate validator in the same workflow run; the Architecture Portal is called as a reusable workflow job so it participates in the same `needs` graph. The conditional macOS fallback remains an internal dependency, and existing primary/fallback/adjudication semantics remain unchanged.

**Tech Stack:** GitHub Actions YAML, Python 3.11 standard library, JSON policy files, Bash, existing CMake/Core scripts, Node.js 22, Docusaurus, actionlint.

## Global Constraints

- Work only on a short-lived `feat/<task>` branch in an isolated worktree based on the latest `origin/main`; never implement on `main`.
- The approved design is `docs/superpowers/specs/2026-08-11-risk-based-ci-gating-design.md`; implementation must not weaken its fail-closed rules.
- `Change Scope` uses only checkout, Git, shell, and Python 3.11 standard library. It must not run `npm install`, `pip install`, CMake, browsers, toolchain setup, or runner-inventory queries.
- Use exact local Git objects and `git diff --name-status -z BASE HEAD`. Do not use GitHub PR Files/Compare responses for normal classification, so their approximately 3,000-file silent truncation cannot become evidence; inability to prove a complete inventory is a classification failure.
- The v1 lane allowlist is exactly `docs_static`, `portal`, `ci_contract`, `core_ubuntu`, `core_asan`, `core_coverage`, `core_macos`, `web_toolchain`, `web_runtime_host`, `creator`, `web_runtime_lab`, `deploy_contract`, `chameleon_lab`, and `package`.
- Paths use union semantics: every matching rule adds lanes; no first-match rule and no rule may subtract a lane.
- Unknown top-level paths, central CI self-modification, root/shared CMake, shared fixtures, Contracts, Product Assembly, `ci:full`, `main` push, and manual dispatch select `full`.
- Draft mode runs only lightweight evidence and cannot replace the Ready event's formal result.
- `PR Gate` validates same-run formal lane jobs plus deterministic `select-ubuntu-runner`, `select-macos-runner`, and `macos-primary` support jobs. Conditional `macos-fallback` remains transitively enforced through the published `core-macos` and `core-asan-macos` adjudicators and is not a manifest-required job.
- A selected lane/support job must be `success`; an unselected lane/support job must be `skipped`. Missing, cancelled, failed, unexpectedly successful, unknown, or SHA-mismatched evidence fails closed.
- Semantic compile, Proof, test, sanitizer, and Coverage failures are final. Preserve the existing one-time macOS hosted fallback only for missing terminal infrastructure results.
- Keep Web Toolchain and Creator on GitHub-hosted Ubuntu; keep current self-hosted Linux/macOS selection and ccache behavior. Do not add runners, hosted retry, or cache/toolchain reuse in this implementation.
- SLOs are summary-only observations. Hard job limits remain independent and must not turn a slow successful job into a semantic failure.
- The implementation PR must carry `ci:full`, declare expected selected/skipped lanes in its body, and execute the complete old and new matrix before migration.
- No push, PR, merge, branch-protection mutation, tag, release, deployment, Product Build allocation, or Channel promotion is authorized by this plan.

## File and Responsibility Map

| File | Responsibility |
| --- | --- |
| `scripts/ci/scope_policy.json` | Versioned closed lane/job/path ownership policy. |
| `scripts/ci/change_scope.py` | Parse exact Git inventory, fetch live PR labels, classify mode/lanes, validate and emit manifest/summary. |
| `scripts/ci/pr_gate.py` | Validate manifest/SHA/job-result correspondence and render non-blocking timing/SLO observations. |
| `tests/build/ci_change_scope_test.py` | Classifier, policy, rename, overlap, unknown-path, Draft/Ready/full and inventory contract tests. |
| `tests/build/ci_pr_gate_test.py` | Gate truth table, schema closure, SHA and lane/job mapping contract tests. |
| `tests/build/ci_workflow_topology_test.py` | Event, concurrency, same-run fan-in, lane condition, timeout and no-label-trigger workflow contracts. |
| `.github/workflows/architecture-portal.yml` | Reusable Portal verification job with explicit impact-check inputs. |
| `.github/workflows/ci.yml` | Main Change Scope, focused lane topology, selectors, Portal call, artifact retention and PR Gate. |
| `tests/build/ci_runner_fallback_test.py` | Preserve selector, fixture hydration and macOS infrastructure fallback invariants after new `needs`. |
| `tests/build/ci_build_acceleration_test.py` | Preserve ccache and bounded-parallelism invariants after new `needs`. |
| `docs/quality/core-test-policy.md` | Current risk-based lane ownership, no-retry, fallback, Draft/Ready and SLO policy. |
| `docs/governance/git-workflow.md` | `ci:full`, rerun, focused gate, required-check migration and rollback workflow. |
| `apps/architecture-portal/docs/operations/testing-and-proof.mdx` | Current Portal description of implemented Change Scope and PR Gate behavior. |
| `.github/pull_request_template.md` | Required CI scope declaration next to version/documentation impact. |

---

### Task 1: Fail-Closed Change Scope Classifier

**Files:**
- Create: `scripts/ci/scope_policy.json`
- Create: `scripts/ci/change_scope.py`
- Create: `tests/build/ci_change_scope_test.py`

**Interfaces:**
- Consumes: base/head 40-hex SHAs; event name; Draft boolean; live PR labels; `git diff --name-status -z` bytes; `scripts/ci/scope_policy.json`.
- Produces: `parse_name_status_z(payload: bytes) -> tuple[ChangedFile, ...]`, `classify(policy: Mapping[str, object], changed: Sequence[ChangedFile], *, base_sha: str, head_sha: str, event_name: str, draft: bool, labels: Collection[str], force_full: bool = False) -> dict[str, object]`, and one compact `lmdj.ci-scope.v1` JSON manifest.
- Produces CLI: `python3 scripts/ci/change_scope.py --policy scripts/ci/scope_policy.json --event EVENT --base-sha SHA --head-sha SHA --repository OWNER/REPO --pr-number NUMBER --manifest-out PATH --github-output PATH --summary PATH`.

- [ ] **Step 1: Write policy-closure and classification tests**

Create `tests/build/ci_change_scope_test.py` with a temporary Git repository helper and these exact contract groups:

```python
LANES = {
    "docs_static", "portal", "ci_contract", "core_ubuntu", "core_asan",
    "core_coverage", "core_macos", "web_toolchain", "web_runtime_host",
    "creator", "web_runtime_lab", "deploy_contract", "chameleon_lab",
    "package",
}

CASES = {
    "docs/guide.md": {"docs_static"},
    "docs/governance/git-workflow.md": {"docs_static", "portal"},
    "apps/creator-web/README.md": {"docs_static", "portal", "creator"},
    "apps/web-runtime-host/src/main.mjs": {"portal", "web_runtime_host"},
    "apps/chameleon-lab/src/main.js": {"portal", "chameleon_lab"},
    "tests/core/audio/render_test.cpp": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos"
    },
    "tests/platform/web/creator/editor.spec.mjs": {"creator"},
    "tests/build/ci_runner_fallback_test.py": {"ci_contract"},
    "tools/web-runtime/verify_emscripten.py": {
        "web_toolchain", "web_runtime_host", "creator"
    },
    "packaging/core/CMakeLists.txt": {"core_ubuntu", "package"},
    "netlify.toml": {"portal", "ci_contract"},
    ".gitattributes": {
        "core_ubuntu", "core_asan", "core_coverage", "core_macos",
        "web_runtime_host", "creator", "package", "ci_contract"
    },
}
```

Add methods with these exact names and assertions:

- `test_policy_has_exact_closed_lanes_and_all_current_top_levels`: compare set equality with `LANES` and the top-level set below.
- `test_every_case_uses_union_semantics`: classify each `CASES` entry and compare the true-lane set exactly.
- `test_rename_classifies_old_and_new_paths`: rename a Creator path to a Web Host path and require the union of both consumers.
- `test_deleted_known_path_keeps_its_consumers`: parse `D\0apps/web-runtime-host/src/main.mjs\0` and require `web_runtime_host`.
- `test_unknown_top_level_upgrades_to_full`: classify `future-system/config.json` and require mode `full`, all lanes true, and an unknown-top-level reason.
- `test_central_ci_files_upgrade_to_full`: classify `.github/workflows/ci.yml`, `scripts/ci/change_scope.py`, `scripts/ci/pr_gate.py`, and `scripts/ci/scope_policy.json` as full.
- `test_three_expensive_families_upgrade_to_full_but_docs_portal_do_not_count`: require Core + Web + Creator to become full, but docs + Portal + Web to remain focused.
- `test_ci_full_upgrades_ready_pr_to_full`: compare the same Ready diff with and without the label and require only the labeled case to be full.
- `test_main_and_dispatch_are_full`: require both event modes to select all 14 lanes.
- `test_draft_emits_only_docs_static_and_ci_contract_evidence`: use a Core diff and require only those two lanes while retaining a deferred-full reason.
- `test_invalid_sha_noncanonical_path_duplicate_path_and_unknown_status_fail`: use subtests for every rejected input category.
- `test_git_inventory_uses_complete_base_to_head_range_not_last_commit`: create two commits changing different lanes and require both from the base-to-head inventory.
- `test_name_status_parser_handles_add_modify_delete_and_rename_nul_records`: compare the exact immutable records for `A`, `M`, `D`, and `R100` payloads.
- `test_missing_git_object_or_failed_diff_is_a_hard_error`: require a nonzero CLI exit and no manifest file.
- `test_manifest_is_compact_deterministic_and_schema_closed`: run classification twice, compare bytes, reject an injected key, and assert no newline in the compact output.

The current top-level allowlist assertion must equal:

```python
{
    ".gitattributes", ".github", ".gitignore", "AGENTS.md", "CLAUDE.md",
    "CMakeLists.txt", "CMakePresets.json", "README.md", "apps", "cmake",
    "contracts", "docs", "netlify.toml", "output", "packages", "packaging",
    "products", "providers", "references", "scripts", "testdata", "tests",
    "tools", "workers",
}
```

- [ ] **Step 2: Run the classifier test and confirm the red state**

Run:

```bash
python3 tests/build/ci_change_scope_test.py
```

Expected: FAIL because `scripts/ci/scope_policy.json` and `scripts/ci/change_scope.py` do not exist.

- [ ] **Step 3: Add the closed v1 policy**

Create `scripts/ci/scope_policy.json` with this top-level schema and exact lane-to-formal-job mapping:

```json
{
  "schema": "lmdj.ci-scope-policy.v1",
  "manifest_schema": "lmdj.ci-scope.v1",
  "lanes": [
    "docs_static", "portal", "ci_contract", "core_ubuntu", "core_asan",
    "core_coverage", "core_macos", "web_toolchain", "web_runtime_host",
    "creator", "web_runtime_lab", "deploy_contract", "chameleon_lab", "package"
  ],
  "lane_jobs": {
    "docs_static": ["docs-static"],
    "portal": ["portal"],
    "ci_contract": ["ci-contract"],
    "core_ubuntu": ["select-ubuntu-runner", "core-ubuntu"],
    "core_asan": ["select-ubuntu-runner", "core-asan"],
    "core_coverage": ["select-ubuntu-runner", "core-coverage"],
    "core_macos": ["select-macos-runner", "macos-primary", "core-macos", "core-asan-macos"],
    "web_toolchain": ["web-toolchain-conformance"],
    "web_runtime_host": ["select-ubuntu-runner", "web-runtime-host"],
    "creator": ["creator-web"],
    "web_runtime_lab": ["select-ubuntu-runner", "web-runtime-lab"],
    "deploy_contract": ["deploy-contract"],
    "chameleon_lab": ["chameleon-lab"],
    "package": ["package"]
  }
}
```

Add `known_top_levels`, `full_rules`, `rules`, `expensive_families`, `draft_lanes`, and `slo_seconds` in the same file. Encode every ownership row from design §§8–9. Use only closed match objects of these forms:

```json
{"kind": "exact", "value": "netlify.toml"}
{"kind": "prefix", "value": "apps/creator-web/"}
{"kind": "suffix", "value": ".md"}
```

Reject unknown match kinds and unknown keys. Put specific file/prefix additions and the generic Markdown suffix in separate rules so union behavior is structural, not priority-based. Map the four expensive families exactly as `core`, `web-runtime`, `creator`, and `deploy-package`; do not count Docs, Portal, CI Contract, or Chameleon.

- [ ] **Step 4: Implement the classifier and exact inventory reader**

Create `scripts/ci/change_scope.py` with immutable records and explicit validation:

```python
@dataclass(frozen=True)
class ChangedFile:
    status: str
    paths: tuple[str, ...]

ALLOWED_MANIFEST_KEYS = {
    "schema", "base_sha", "head_sha", "mode", "reasons",
    "changed_files", "lanes", "required_jobs",
}
ALLOWED_MODES = {"draft", "focused", "full"}
ALLOWED_RESULTS = {"added", "copied", "deleted", "modified", "renamed", "type_changed"}
```

Implement these rules literally:

1. validate both SHAs as exactly 40 lowercase or uppercase hexadecimal characters and normalize to lowercase;
2. reject absolute paths, empty components, `.`/`..`, backslashes, duplicate logical paths, unmerged status, and status codes outside `A/C/D/M/R/T`;
3. parse rename/copy records as old/new path pairs and classify both paths;
4. load the JSON policy with duplicate-key rejection via `json.load(policy_file, object_pairs_hook=reject_duplicates)`;
5. union every matching rule's lanes, then apply full upgrades;
6. in Draft mode publish only `docs_static` and `ci_contract`, while recording any deferred Ready/full reason in `reasons`;
7. derive sorted `required_jobs` only from true lanes and `lane_jobs`;
8. emit deterministic compact JSON using `sort_keys=True, separators=(",", ":")`;
9. write the manifest file, `manifest=<compact-json>` to `$GITHUB_OUTPUT`, and a human-readable Markdown table to `$GITHUB_STEP_SUMMARY`;
10. fetch current PR metadata with `urllib.request` from `/repos/{repository}/pulls/{number}` using `GITHUB_TOKEN`; accept only the returned `draft` boolean and `labels[].name` strings. Do not request runner or Checks APIs;
11. run `git cat-file -e SHA^{commit}` for both endpoints and `git diff --name-status -z BASE HEAD`; if either command fails, exit nonzero instead of querying PR Files/Compare.

- [ ] **Step 5: Run focused classifier verification**

Run:

```bash
python3 tests/build/ci_change_scope_test.py
python3 -m py_compile scripts/ci/change_scope.py tests/build/ci_change_scope_test.py
git diff --check
```

Expected: all classifier tests PASS, compilation succeeds, and `git diff --check` prints nothing.

- [ ] **Step 6: Commit Task 1**

```bash
git add scripts/ci/scope_policy.json scripts/ci/change_scope.py tests/build/ci_change_scope_test.py
git diff --cached --name-status
git diff --cached --check
git diff --cached
git commit -m "feat(ci): add fail-closed change scope classifier"
git show --name-status --format= HEAD
git status --short --branch
```

Expected committed paths: exactly the three Task 1 files; final task worktree is clean.

---

### Task 2: Manifest-Driven PR Gate Validator

**Files:**
- Create: `scripts/ci/pr_gate.py`
- Create: `tests/build/ci_pr_gate_test.py`

**Interfaces:**
- Consumes: Task 1 policy and manifest; `needs`-shaped JSON `{job_id: {result: RESULT}}`; current 40-hex head SHA; optional current-run jobs API data used only for summaries.
- Produces: `validate_gate(policy: Mapping[str, object], manifest: Mapping[str, object], results: Mapping[str, str], expected_head_sha: str) -> GateReport` and exit status `0` only for an exact selected-success/unselected-skipped match.
- Produces CLI: `python3 scripts/ci/pr_gate.py --policy PATH --manifest-json JSON --results-json JSON --head-sha SHA --summary PATH`.

- [ ] **Step 1: Write the complete gate truth-table tests**

Create `tests/build/ci_pr_gate_test.py` with one valid focused manifest fixture and parameterized mutations:

```python
VALID_RESULTS = {
    "docs-static": "success",
    "portal": "success",
    "ci-contract": "skipped",
    "select-ubuntu-runner": "success",
    "select-macos-runner": "skipped",
    "macos-primary": "skipped",
    "core-ubuntu": "skipped",
    "core-asan": "skipped",
    "core-coverage": "skipped",
    "core-macos": "skipped",
    "core-asan-macos": "skipped",
    "web-toolchain-conformance": "skipped",
    "web-runtime-host": "success",
    "creator-web": "skipped",
    "web-runtime-lab": "skipped",
    "deploy-contract": "skipped",
    "chameleon-lab": "skipped",
    "package": "skipped",
}
```

Add methods with these exact names and assertions:

- `test_exact_required_success_and_unrequired_skipped_passes`: `VALID_RESULTS` returns `GateReport.ok == True` and no errors.
- `test_required_skipped_failure_and_cancelled_fail`: mutate each requested result and require one deterministic error per mutation.
- `test_unrequired_success_failure_and_cancelled_fail`: mutate an unrequested result and require a topology-mismatch error.
- `test_missing_or_extra_formal_job_fails`: delete one key and add `invented-job`, requiring exact key-set diagnostics.
- `test_unknown_result_fails`: use `neutral` and require rejection before truth-table evaluation.
- `test_unknown_schema_mode_lane_manifest_key_or_job_fails`: mutate each closed allowlist independently and require rejection.
- `test_duplicate_required_job_and_lane_job_conflict_fail`: duplicate `portal`, then remove the job implied by a true lane, and require both to fail.
- `test_manifest_head_sha_must_equal_current_head_sha`: use two distinct valid 40-hex SHAs and require failure.
- `test_full_manifest_requires_every_formal_job`: set all lanes true and require all 18 lane/support results to be success.
- `test_core_macos_requires_both_published_adjudicators`: require both `core-macos` and `core-asan-macos` when `core_macos` is true.
- `test_needs_json_normalizer_ignores_outputs_but_requires_result`: accept arbitrary `outputs`, reject a missing `result`.
- `test_timing_api_failure_is_a_warning_and_never_changes_gate_result`: inject an HTTP failure, retain a passing gate, and require `timing unavailable` in the summary.
- `test_slo_overage_is_reported_but_success_stays_success`: provide timestamps above the lane SLO, retain a passing gate, and require an `SLO missed` row.

- [ ] **Step 2: Run the gate test and confirm the red state**

Run:

```bash
python3 tests/build/ci_pr_gate_test.py
```

Expected: FAIL because `scripts/ci/pr_gate.py` does not exist.

- [ ] **Step 3: Implement strict manifest and result validation**

Create `scripts/ci/pr_gate.py` with:

```python
@dataclass(frozen=True)
class GateReport:
    ok: bool
    errors: tuple[str, ...]
    requested_jobs: tuple[str, ...]
    skipped_jobs: tuple[str, ...]

FORMAL_RESULTS = {"success", "failure", "cancelled", "skipped"}
```

Validation order must be deterministic:

1. validate policy closure and manifest through the Task 1 manifest validator;
2. require manifest `head_sha == expected_head_sha`;
3. rebuild expected required jobs from true lanes and compare byte-for-byte after canonical sorting;
4. require the results key set to equal the policy's complete 18-job lane/support result set;
5. require each selected job to be `success` and each unselected job to be `skipped`;
6. accumulate every mismatch into the summary, print errors to stderr, and return exit `1`;
7. normalize GitHub `toJSON(needs)` objects by reading only each direct dependency's `result` field. The workflow must pass the 15 formal lane jobs plus `select-ubuntu-runner`, `select-macos-runner`, and `macos-primary`; it must not pass `change-scope` or conditional `macos-fallback` as result keys.

Add an optional standard-library Actions jobs API reader for the current run. It may compute `created_at -> started_at` queue time and `started_at -> completed_at` execution time for completed formal jobs and compare them with `slo_seconds`; API absence, pagination failure, or incomplete timestamps prints `timing unavailable` and never changes `GateReport.ok`.

- [ ] **Step 4: Run focused gate verification**

Run:

```bash
python3 tests/build/ci_pr_gate_test.py
python3 tests/build/ci_change_scope_test.py
python3 -m py_compile scripts/ci/change_scope.py scripts/ci/pr_gate.py tests/build/ci_pr_gate_test.py
git diff --check
```

Expected: both contract suites PASS and static checks are clean.

- [ ] **Step 5: Commit Task 2**

```bash
git add scripts/ci/pr_gate.py tests/build/ci_pr_gate_test.py
git diff --cached --name-status
git diff --cached --check
git diff --cached
git commit -m "feat(ci): add manifest-driven PR gate"
git show --name-status --format= HEAD
git status --short --branch
```

Expected committed paths: exactly the two Task 2 files; final task worktree is clean.

---

### Task 3: Reusable Architecture Portal Workflow

**Files:**
- Modify: `.github/workflows/architecture-portal.yml`
- Create: `tests/build/ci_workflow_topology_test.py`

**Interfaces:**
- Consumes: `workflow_call` inputs `check_documentation_impact: boolean`, `base_sha: string`, `head_sha: string`, and `pull_request_body: string`.
- Produces: reusable workflow job result `portal`, callable as `uses: ./.github/workflows/architecture-portal.yml` from Task 4's main CI workflow.

- [ ] **Step 1: Write reusable-workflow contract tests**

Create `tests/build/ci_workflow_topology_test.py`. At this task boundary add four methods:

- `test_portal_exposes_workflow_call_with_typed_inputs`: require the exact typed input block below.
- `test_portal_impact_check_uses_explicit_base_and_head_inputs`: require both input expressions and reject event-derived SHAs inside the called impact step.
- `test_portal_reusable_job_keeps_fetch_depth_zero_node_22_and_full_check`: require all three existing contracts.
- `test_portal_does_not_use_checks_api_or_cross_run_polling`: reject `api.github.com`, `/check-runs`, `gh api`, and polling loops.

The test must require these literal inputs and commands:

```yaml
workflow_call:
  inputs:
    check_documentation_impact:
      required: false
      type: boolean
      default: false
    base_sha:
      required: false
      type: string
      default: ""
    head_sha:
      required: false
      type: string
      default: ""
    pull_request_body:
      required: false
      type: string
      default: ""
```

```bash
git diff --name-only "${{ inputs.base_sha }}" "${{ inputs.head_sha }}"
scripts/architecture-portal.sh check
```

- [ ] **Step 2: Run the Portal workflow contract and confirm the red state**

Run:

```bash
python3 tests/build/ci_workflow_topology_test.py
```

Expected: FAIL because `workflow_call` and explicit inputs are absent.

- [ ] **Step 3: Expose Portal verification through `workflow_call`**

Modify `.github/workflows/architecture-portal.yml` to add the typed `workflow_call` interface while temporarily retaining the existing PR/push triggers until Task 4 installs the caller. Keep `permissions: contents: read`, fetch-depth zero, Node 22 locked install, documentation-impact validation, and `scripts/architecture-portal.sh check`.

Use input-based impact checking only for called runs:

```yaml
- name: Check Pull Request documentation impact
  if: ${{ inputs.check_documentation_impact }}
  env:
    PORTAL_PR_BODY: ${{ inputs.pull_request_body }}
    PORTAL_BASE_SHA: ${{ inputs.base_sha }}
    PORTAL_HEAD_SHA: ${{ inputs.head_sha }}
  run: |
    set -euo pipefail
    [[ "$PORTAL_BASE_SHA" =~ ^[0-9a-fA-F]{40}$ ]]
    [[ "$PORTAL_HEAD_SHA" =~ ^[0-9a-fA-F]{40}$ ]]
    changed_files="$(git diff --name-only "$PORTAL_BASE_SHA" "$PORTAL_HEAD_SHA")"
    PORTAL_CHANGED_FILES="$changed_files" npm --prefix apps/architecture-portal run check:impact
```

Retain the current event-based branch for direct PR runs during this intermediate commit so the commit remains deployable before Task 4 removes duplicate triggers.

- [ ] **Step 4: Run Portal and workflow verification**

Run:

```bash
python3 tests/build/ci_workflow_topology_test.py
scripts/architecture-portal.sh check
git diff --check
```

Expected: workflow contract PASS; Portal reports 41 passing tests, valid docs/diagrams, successful typecheck/build, and valid internal links.

- [ ] **Step 5: Commit Task 3**

```bash
git add .github/workflows/architecture-portal.yml tests/build/ci_workflow_topology_test.py
git diff --cached --name-status
git diff --cached --check
git diff --cached
git commit -m "refactor(ci): expose portal verification as a reusable workflow"
git show --name-status --format= HEAD
git status --short --branch
```

Expected committed paths: exactly the Portal workflow and its topology contract.

---

### Task 4: Focused Main CI Topology, Governance, and Same-Run Gate

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/architecture-portal.yml`
- Modify: `tests/build/ci_workflow_topology_test.py`
- Modify: `tests/build/ci_runner_fallback_test.py`
- Modify: `tests/build/ci_build_acceleration_test.py`
- Modify: `docs/quality/core-test-policy.md`
- Modify: `docs/governance/git-workflow.md`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `.github/pull_request_template.md`

**Interfaces:**
- Consumes: Task 1 compact manifest output and Task 2 CLI; Task 3 reusable Portal workflow.
- Produces: one `PR Gate` job name, same-run formal lane results, retained `ci-scope-<head-sha>` artifact, focused PR execution, full `main`/dispatch execution, and documented operator policy.

- [ ] **Step 1: Extend topology tests for events, concurrency and lane fan-out**

Add these exact test methods to `tests/build/ci_workflow_topology_test.py` before modifying workflows. Each method extracts one job block with the same anchored regular-expression helper used by the existing runner tests:

- `test_main_workflow_has_no_workflow_level_paths_filter`: reject `paths:` and `paths-ignore:` inside the event block.
- `test_pr_events_exclude_labeled_and_unlabeled`: compare the event type set exactly with the five approved types.
- `test_pr_group_is_per_pr_and_cancels_but_main_group_is_per_sha_and_does_not_cancel`: require PR number, SHA, and event-dependent cancel expression.
- `test_change_scope_has_three_minute_limit_zero_dependency_install_and_live_pr_read`: require fetch-depth zero, Task 1 invocation and PR token; reject npm, pip, CMake, browser, emsdk, runner API and secrets other than `GITHUB_TOKEN`.
- `test_every_formal_lane_depends_directly_on_change_scope`: loop over all 15 formal lane IDs and require `change-scope` in `needs`; separately require the three deterministic support jobs to depend on `change-scope`.
- `test_creator_no_longer_needs_web_toolchain_or_core`: reject both old dependencies and retain hosted Ubuntu.
- `test_linux_selector_runs_only_when_a_linux_pool_consumer_is_selected`: require the exact five lane booleans.
- `test_macos_selector_runs_only_when_core_macos_is_selected`: require exactly the `core_macos` boolean.
- `test_portal_is_same_run_reusable_job_and_pr_gate_needs_it`: require local reusable-workflow `uses` and the `portal` fan-in key.
- `test_pr_gate_has_every_formal_lane_in_static_needs_and_runs_with_always`: compare the complete `needs` set and require `always() && !cancelled()`.
- `test_scope_and_gate_timeouts_are_three_minutes_and_lane_limits_match_policy`: compare each declared hard limit with design §13.
- `test_scope_manifest_is_uploaded_and_summarized`: require upload-artifact, head-SHA artifact naming, `$GITHUB_OUTPUT`, and `$GITHUB_STEP_SUMMARY`.
- `test_no_job_uses_retry_for_semantic_workloads`: reject retry actions, retry loops, and a second invocation of any existing proof/sanitizer/coverage command.
- `test_architecture_portal_no_longer_has_duplicate_pr_or_main_triggers`: require `workflow_call` and reject direct PR/push events after Task 4.

Update existing runner tests so `workflow_job()` accepts the new direct `change-scope` dependency while retaining the selector dependency. For example, Linux consumers must contain:

```yaml
needs: [change-scope, select-ubuntu-runner]
```

and the selector itself must contain `needs: change-scope` plus a manifest-driven `if:`. Preserve every existing assertion about fork routing, pool labels, LFS hydration, ccache, macOS terminal-result fallback and published check names.

- [ ] **Step 2: Run workflow contracts and confirm the red state**

Run:

```bash
python3 tests/build/ci_workflow_topology_test.py
python3 tests/build/ci_runner_fallback_test.py
python3 tests/build/ci_build_acceleration_test.py
```

Expected: new topology tests FAIL against the unconditional workflow; pre-existing fallback/acceleration assertions remain green until their `needs` expectations are deliberately updated.

- [ ] **Step 3: Add events, permissions, concurrency and Change Scope**

Modify `.github/workflows/ci.yml`:

```yaml
on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, ready_for_review, converted_to_draft]
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pull-requests: read
  actions: read

concurrency:
  group: ${{ github.event_name == 'pull_request' && format('core-ci-pr-{0}', github.event.pull_request.number) || format('core-ci-sha-{0}', github.sha) }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

Add `change-scope` first. It runs on `ubuntu-24.04`, has `timeout-minutes: 3`, checks out with `fetch-depth: 0`, invokes Task 1, uploads the manifest with `actions/upload-artifact@v4`, and publishes compact `manifest` output. Pass `GITHUB_TOKEN`, exact event/base/head/repository/PR-number values, and `$GITHUB_OUTPUT`/`$GITHUB_STEP_SUMMARY`; manual dispatch sets `--force-full`.

- [ ] **Step 4: Add lightweight and missing formal lanes**

Add these jobs, each depending directly on `change-scope` and guarded by its lane boolean:

```yaml
docs-static:
  timeout-minutes: 10
  # checkout fetch-depth 0, validate exact base/head with git diff --check

ci-contract:
  timeout-minutes: 10
  # run actionlint plus all ci_* Python contracts

deploy-contract:
  timeout-minutes: 15
  # run web_runtime_deploy_workflow_test.py and
  # web_runtime_public_deployment_docs_test.py; do not deploy

chameleon-lab:
  timeout-minutes: 10
  # setup Node 22/Python 3.11 and run scripts/chameleon-lab.sh test

package:
  timeout-minutes: 35
  # setup Python 3.11, LFS hydration and bounded acceleration,
  # then run scripts/core.sh package without publishing a release
```

In `ci-contract`, run:

```bash
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
```

and use `docker://rhysd/actionlint:1.7.7` only in this conditionally selected CI-control lane. Do not install Node, CMake, browser, or Emscripten in `change-scope` or `docs-static`.

- [ ] **Step 5: Make all existing formal lanes manifest-driven and parallel**

For every existing formal lane, add `change-scope` to `needs` and a condition of the form:

```yaml
if: ${{ !cancelled() && fromJSON(needs.change-scope.outputs.manifest).lanes.web_runtime_host }}
```

Use the corresponding closed lane name. Change `creator-web` from:

```yaml
needs: [web-toolchain-conformance, core-ubuntu]
```

to:

```yaml
needs: change-scope
```

Preserve its hosted runner and exact proof steps. Make `select-ubuntu-runner` depend on `change-scope` and run only when at least one of `web_runtime_host`, `web_runtime_lab`, `core_ubuntu`, `core_asan`, or `core_coverage` is true. Make `select-macos-runner` depend on `change-scope` and run only for `core_macos`.

Keep macOS internal topology:

```text
change-scope -> select-macos-runner -> macos-primary -> optional macos-fallback
                                                \-> core-macos
                                                \-> core-asan-macos
```

Expose `select-ubuntu-runner`, `select-macos-runner`, and `macos-primary` as conditional support result keys. Do not expose `macos-fallback`: it is legitimately skipped after a successful primary and remains transitively enforced through the two required published adjudicators.

- [ ] **Step 6: Call Portal in the same run and add the single PR Gate**

Remove direct `pull_request` and `push` triggers from `.github/workflows/architecture-portal.yml`; leave `workflow_call` only. Add this main-workflow job:

```yaml
portal:
  needs: change-scope
  if: ${{ !cancelled() && fromJSON(needs.change-scope.outputs.manifest).lanes.portal }}
  uses: ./.github/workflows/architecture-portal.yml
  with:
    check_documentation_impact: ${{ github.event_name == 'pull_request' }}
    base_sha: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || github.event.before }}
    head_sha: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}
    pull_request_body: ${{ github.event_name == 'pull_request' && github.event.pull_request.body || '' }}
```

Add `pr-gate` with display name exactly `PR Gate`, `runs-on: ubuntu-24.04`, `timeout-minutes: 3`, and static `needs` containing `change-scope` plus all 18 lane/support job IDs from Task 2. Use `if: ${{ always() && !cancelled() }}`. Pass exactly the 18 result entries to Task 2; do not pass `change-scope` or `macos-fallback` as a manifest result. Use Task 2's optional Actions API timing read only for summaries; correctness comes exclusively from same-run `needs` and the manifest.

Construct the result object explicitly rather than passing raw `toJSON(needs)`:

```yaml
env:
  FORMAL_RESULTS_JSON: >-
    {"docs-static":"${{ needs.docs-static.result }}","portal":"${{ needs.portal.result }}","ci-contract":"${{ needs.ci-contract.result }}","select-ubuntu-runner":"${{ needs.select-ubuntu-runner.result }}","select-macos-runner":"${{ needs.select-macos-runner.result }}","macos-primary":"${{ needs.macos-primary.result }}","core-ubuntu":"${{ needs.core-ubuntu.result }}","core-asan":"${{ needs.core-asan.result }}","core-coverage":"${{ needs.core-coverage.result }}","core-macos":"${{ needs.core-macos.result }}","core-asan-macos":"${{ needs.core-asan-macos.result }}","web-toolchain-conformance":"${{ needs.web-toolchain-conformance.result }}","web-runtime-host":"${{ needs.web-runtime-host.result }}","creator-web":"${{ needs.creator-web.result }}","web-runtime-lab":"${{ needs.web-runtime-lab.result }}","deploy-contract":"${{ needs.deploy-contract.result }}","chameleon-lab":"${{ needs.chameleon-lab.result }}","package":"${{ needs.package.result }}"}
  SCOPE_MANIFEST: ${{ needs.change-scope.outputs.manifest }}
run: >-
  python3 scripts/ci/pr_gate.py
  --policy scripts/ci/scope_policy.json
  --manifest-json "$SCOPE_MANIFEST"
  --results-json "$FORMAL_RESULTS_JSON"
  --head-sha "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
  --summary "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 7: Update current governance and operator documentation**

Update the four documentation surfaces with the implemented facts:

1. `docs/quality/core-test-policy.md`: add a “Risk-Based PR Selection” section defining Draft/focused/full, path ownership, test inheritance, selector routing, single Gate truth table, SLO-not-timeout boundary, no retry and `main` full.
2. `docs/governance/git-workflow.md`: replace “every configured job” wording with “every manifest-selected formal lane plus PR Gate”; document `ci:full` label followed by waiting/cancelling and “Re-run all jobs”; document the two-stage rollback that forces all PRs full before old contexts are restored.
3. `apps/architecture-portal/docs/operations/testing-and-proof.mdx`: update “CI 责任” to describe Change Scope, same-run Portal fan-in, formal lanes, full `main`, SLO evidence, and retained macOS fallback; keep Product Build `1.0.16.5` facts unchanged.
4. `.github/pull_request_template.md`: add:

```markdown
## CI Scope

Expected mode: focused
Expected selected lanes: <!-- Closed lane names, space-separated. -->
Expected skipped lanes: <!-- Closed lane names, space-separated. -->
`ci:full` required: no
Reason: <!-- Explain path ownership or the full-upgrade trigger. -->
```

The implementation PR itself must use `Expected mode: full`, list all 14 lanes as selected, list no skipped lanes, and use `ci:full required: yes`.

- [ ] **Step 8: Run all local CI-control and documentation verification**

Run serially:

```bash
python3 tests/build/ci_change_scope_test.py
python3 tests/build/ci_pr_gate_test.py
python3 tests/build/ci_workflow_topology_test.py
python3 tests/build/ci_runner_fallback_test.py
python3 tests/build/ci_build_acceleration_test.py
python3 tests/build/web_runtime_deploy_workflow_test.py
python3 tests/build/web_runtime_public_deployment_docs_test.py
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git diff --check
```

Expected: every command exits `0`; Portal reports all tests/pages/diagrams/typecheck/build/routes valid; no command runs Core Proof, sanitizer, Coverage, browser installation, deployment, release, or runner mutation locally.

If `actionlint` is installed locally, also run:

```bash
actionlint .github/workflows/ci.yml .github/workflows/architecture-portal.yml
```

Expected: no diagnostics. If it is not installed, the conditionally selected `ci-contract` workflow job remains the authoritative actionlint evidence on the implementation PR; do not install an unpinned local binary.

- [ ] **Step 9: Commit Task 4**

```bash
git add .github/workflows/ci.yml .github/workflows/architecture-portal.yml \
  .github/pull_request_template.md \
  tests/build/ci_workflow_topology_test.py \
  tests/build/ci_runner_fallback_test.py \
  tests/build/ci_build_acceleration_test.py \
  docs/quality/core-test-policy.md docs/governance/git-workflow.md \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --name-status
git diff --cached --check
git diff --cached
git commit -m "feat(ci): route pull requests through risk-based gates"
git show --name-status --format= HEAD
git status --short --branch
```

Expected committed paths: exactly the nine declared Task 4 files; final task worktree is clean.

---

## Version Management

Version impact: none.

Reason: this implementation changes only CI classification, orchestration, aggregation, documentation, and observations. It does not change Product Build, Core Module, Host, Provider, Contract, Product Assembly identity, or runtime artifacts. Do not allocate a Product Build, create a snapshot/tag, or promote a Channel.

## Documentation Impact

Documentation impact: required.

Affected portal pages: `/operations/testing-and-proof/`

Reason: the implemented PR selection, required-check, testing evidence, fallback and rollback workflow become current operational facts. Task 4 updates the Portal page, `docs/quality/core-test-policy.md`, `docs/governance/git-workflow.md`, and the PR template in the same implementation unit. No architecture source diagram changes because module/host/provider/contract boundaries do not change.

## Authorized Remote Migration Checklist

These steps are intentionally outside local implementation and require separate authorization at each boundary:

1. Rebase the unshared feature branch onto the latest `origin/main` after inventorying every worktree/index; rerun Task 4 verification.
2. Push the feature branch and open a PR with `ci:full`, all 14 lanes selected in the body, and no skipped lane.
3. Verify the retained scope manifest, job summary, old full matrix, new formal results, and `PR Gate` on the implementation PR.
4. Add `PR Gate` as required while retaining `core (ubuntu-latest)` and `core (macos-latest)`.
5. Merge only after all three required contexts and every selected formal lane succeed.
6. Verify the merge commit's `main` run is `full`, per-SHA, non-cancelling, and publishes all formal results.
7. Under separate branch-protection authorization, remove the old two Core contexts; confirm strict branch update and conversation resolution remain enabled.
8. Observe one week of focused/full ratio, queue/execution P50/P95, hosted minutes, manual `ci:full`, misclassification, selector serialization, and Web bootstrap versus semantic time.
9. If rollback is required, keep `PR Gate` required, first merge a configuration that forces every PR to full, prove docs-only PRs publish the old Core contexts, restore those contexts as required, and only then remove `PR Gate`.

No checklist item authorizes the next item automatically.
