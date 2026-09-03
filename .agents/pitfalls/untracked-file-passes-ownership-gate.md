---
id: untracked-file-passes-ownership-gate
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/587
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/595
    observed_by: claude-code/opus-5
exit: skill:.agents/skills/issue-done/SKILL.md
---

# Verifying before staging gives a false green, because the tracked-path ownership gate reads `git ls-files` and a new file is not in it yet.

## Why

`test_every_tracked_path_has_explicit_ownership_or_full_rule` in
`tests/build/ci_change_scope_test.py` derives its input from `git ls-files`. A
file that has been written but not staged is not tracked, so the gate cannot
see it and the suite reports green. The file becomes tracked at `git add`, and
the same suite then fails — but by then the local verification has already been
recorded as passing, and the failure surfaces on CI instead.

The gate is correct and the classification requirement is real. What fails is
the ordering: `issue-done` section 1 runs verification, and section 3 stages,
so the default flow runs the gate at the one moment it structurally cannot
observe the change under test.

Both recurrences were the same shape on the same day. PR #587 added
`.github/workflows/ci-self-hosted-core-benchmark.yml`; the suite passed before
`git add` and failed immediately after, because `.github/workflows/` has
per-file ownership and no catch-all prefix. PR #595 added
`tests/build/workflow_inventory.py`; the suite passed before `git add` and the
`CI contract` lane failed on the Pull Request, because `tests/build/` routes by
the `tests/build/ci_` prefix and a helper module does not match it. In both
cases the fix was one line in `scripts/ci/scope_policy.json`, and in both cases
the cost was a red lane rather than a local failure.

Directories with per-file ownership and no catch-all are where this bites:
`.github/workflows/`, `.github/scripts/`, and `tests/build/` for any file whose
name does not match an existing prefix rule.

## How to apply

- Re-run the Task's verification **after** `git add`, not only before it. Any
  check that reads `git ls-files`, the index, or the commit graph is blind to
  an unstaged file, so a green run before staging proves nothing about a new
  one.
- When a Task adds a tracked file, classify it in `scripts/ci/scope_policy.json`
  in the same commit. Check whether an existing prefix rule already covers the
  exact filename rather than assuming the directory is covered: a new helper in
  a directory routed by a `<dir>/<prefix>` rule is not covered unless its name
  carries that prefix.
- No gate exit yet. Widening the ownership test to include staged and
  untracked-but-unignored files would catch it at the right moment, but it
  would also fire on ordinary scratch files in a working tree; that trade
  needs its own Task. Escalate if this recurs after the ordering guidance
  lands.
