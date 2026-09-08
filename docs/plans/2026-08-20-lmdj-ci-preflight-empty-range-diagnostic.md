# LMDJ CI Pre-flight Empty Range Diagnostic Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the advisory local CI pre-flight say when its resolved base is `HEAD` and no changes exist, without conflating that condition with a changed scope that selects zero lanes.

**Architecture:** `build_plan()` already resolves `base_sha`, `head_sha`, and the working inventory before it invokes the production Change Scope classifier. Preserve the classifier and `scope_policy.json` unchanged; render the empty-range diagnostic only when equal SHAs and an empty inventory prove no changes exist. A changed range with an empty selected list continues to render `nothing selected`.

**Tech Stack:** Python 3 standard library, checked-in Change Scope classifier and policy, `unittest`, Git.

## Global Constraints

- Work only on `fix/ci-preflight-empty-range`; never commit to `main`.
- Change only this plan, `scripts/ci/local_preflight.py`, and `tests/build/ci_local_preflight_test.py`.
- Do not change classifier or policy lane selection, cache keys, CLI exit semantics, or advisory boundary.
- The empty-range diagnostic must contain `base equals HEAD` and `no changes to check`, and requires equal SHAs plus no changed paths so uncommitted edits remain checkable.
- A changed range with zero selected lanes must retain `nothing selected`.
- Version impact: none. This changes repository-local CI diagnostic text only, not a Product Build, Assembly, Module, Provider, Host, Contract, or versioned schema identity.
- Documentation impact: none. Current governance and portal pages describe commands and lane verdicts, not ambiguous empty-range wording; no product, operational procedure, or portal route changes.

---

## File Structure

- Create: `docs/plans/2026-08-20-lmdj-ci-preflight-empty-range-diagnostic.md` — scope, TDD, version, documentation, and acceptance record.
- Modify: `tests/build/ci_local_preflight_test.py` — `TemporaryRepository` regression tests that exercise real `build_plan()` inputs, plus one rendering-only zero-selection contract.
- Modify: `scripts/ci/local_preflight.py` — separate empty-range summary from existing zero-lane policy output.

### Task 1: Add regression coverage for the two zero-lane meanings

**Files:**

- Modify: `tests/build/ci_local_preflight_test.py` before `AdvisoryBoundaryTest`.
- Test: `tests/build/ci_local_preflight_test.py`.

**Interfaces:**

- Consumes: `_render(plan: Mapping[str, object], results: Sequence[LaneResult], declaration: DeclarationResult | None = None) -> str`.
- Produces: assertions that real `build_plan()` base SHA, head SHA, and changed-path inventory drive the visible diagnostic, plus a separate contract for an empty selected list.

- [ ] **Step 1: Write the failing test**

```python
class EmptyRangeDiagnosticTest(unittest.TestCase):
    def setUp(self) -> None:
        self.preflight = load_module("local_preflight_empty_range", PREFLIGHT_PATH)
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.close)

    def render_plan(self) -> tuple[dict[str, object], str]:
        plan = self.preflight.build_plan(
            self.repository.path, self.repository.base_sha,
        )
        return plan, self.preflight._render(plan, [])

    def test_equal_base_and_head_says_no_changes_to_check(self) -> None:
        plan, rendered = self.render_plan()
        self.assertEqual(plan["base_sha"], plan["head_sha"])
        self.assertEqual(plan["changed_paths"], [])
        self.assertIn("base equals HEAD", rendered)
        self.assertIn("no changes to check", rendered)
        self.assertNotIn("nothing selected", rendered)

    def test_modified_tracked_readme_with_equal_shas_is_not_an_empty_range(self) -> None:
        self.repository.write("README.md", "modified locally\n")
        plan, rendered = self.render_plan()
        self.assertEqual(plan["base_sha"], plan["head_sha"])
        self.assertEqual(plan["changed_paths"], ["README.md"])
        self.assertNotIn("no changes to check", rendered)

    def test_untracked_file_with_equal_shas_is_not_an_empty_range(self) -> None:
        self.repository.write("untracked.txt", "new locally\n")
        plan, rendered = self.render_plan()
        self.assertEqual(plan["base_sha"], plan["head_sha"])
        self.assertEqual(plan["changed_paths"], ["untracked.txt"])
        self.assertNotIn("no changes to check", rendered)

    def test_changed_plan_without_selected_lanes_keeps_nothing_selected(self) -> None:
        rendered = self.preflight._render(
            {"base_sha": "base", "head_sha": "head", "mode": "focused", "selected": [], "changed_paths": ["future-owned/thing.py"]},
            [],
        )
        self.assertIn("nothing selected", rendered)
        self.assertNotIn("base equals HEAD", rendered)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 tests/build/ci_local_preflight_test.py`

Expected: against the old production rendering hunk, the clean `TemporaryRepository` test fails because `_render()` emits `nothing selected`; the tracked-README and untracked-file cases demonstrate that actual local changes must not become an empty-range diagnostic.

### Task 2: Render the resolved empty range separately

**Files:**

- Modify: `scripts/ci/local_preflight.py` inside `_render()` summary construction.
- Test: `tests/build/ci_local_preflight_test.py`.

**Interfaces:**

- Consumes: `plan["base_sha"]`, `plan["head_sha"]`, and `plan["selected"]` from `build_plan()`.
- Produces: `base equals HEAD; no changes to check` only when equal resolved SHAs and no changed paths prove an empty range; otherwise preserves `nothing selected` when no lane result exists.

- [ ] **Step 1: Write minimal implementation**

```python
    if plan["base_sha"] == plan["head_sha"] and not plan.get("changed_paths"):
        summary = "base equals HEAD; no changes to check"
    else:
        summary = summary or "nothing selected"
```

Use the resulting `summary` in the existing `pre-flight: mode=... lanes=... (...)` line. Do not inspect paths again or modify the manifest, classifier, or policy.

- [ ] **Step 2: Run the regression suite and verify GREEN**

Run: `python3 tests/build/ci_local_preflight_test.py`

Expected: exit 0; a clean temporary repository reports both required phrases, while a modified tracked `README.md` and a new untracked file do not report an empty range.

### Task 3: Verify the scoped CI contract and documentation gate, then commit

**Files:**

- Create: `docs/plans/2026-08-20-lmdj-ci-preflight-empty-range-diagnostic.md`.
- Modify: `scripts/ci/local_preflight.py`.
- Modify: `tests/build/ci_local_preflight_test.py`.

**Interfaces:**

- Consumes: complete regression and Change Scope contract suites plus the portal gate.
- Produces: one local Conventional Commit, `fix(ci): distinguish empty preflight range`.

- [ ] **Step 1: Run complete scoped verification**

```bash
python3 tests/build/ci_local_preflight_test.py
python3 tests/build/ci_change_scope_test.py
scripts/architecture-portal.sh check
```

Expected: every command exits 0. The first proves the diagnostic; the second proves classifier/policy behavior is unchanged.

- [ ] **Step 2: Inspect, stage, and commit the exact boundary**

```bash
git branch --show-current
git status --short
git add docs/plans/2026-08-20-lmdj-ci-preflight-empty-range-diagnostic.md scripts/ci/local_preflight.py tests/build/ci_local_preflight_test.py
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "fix(ci): distinguish empty preflight range"
```

Expected: the branch is `fix/ci-preflight-empty-range`; the staged list has exactly the three declared paths; the whitespace check is silent; no push, PR, merge, tag, release, deployment, or Issue state mutation occurs.

- [ ] **Step 3: Inspect post-commit evidence**

```bash
git show --format= --name-only HEAD
git status --short --branch
```

Expected: the commit lists exactly the declared files and the worktree is clean.

## Version Management

Version impact: none. The change is limited to local CI pre-flight diagnostic text and contract tests; no Product Build, Assembly, Module SemVer, Provider SemVer, Contract SemVer, manifest, tag, or channel identity changes.

## Documentation Impact

Documentation impact: none
Reason: the existing governance and portal documentation does not enumerate the ambiguous empty-range output, and this internal diagnostic refinement changes neither an operational workflow nor any product or architecture fact represented by a portal route.

## Acceptance Criteria

- A clean `TemporaryRepository` through real `build_plan()` visibly states `base equals HEAD` and `no changes to check`.
- A modified tracked `README.md` and a new untracked file through real `build_plan()` do not claim an empty range despite equal resolved SHAs.
- A changed prebuilt plan with zero selected lanes retains `nothing selected`; it does not claim this is a current policy path.
- Change Scope classifier and policy files remain untouched.
- Scoped pre-flight and Change Scope suites plus Architecture Portal check pass.
- Exactly the three declared tracked files are committed in one Conventional Commit; no remote or release action occurs.
