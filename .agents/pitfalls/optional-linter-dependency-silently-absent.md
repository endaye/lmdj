---
id: optional-linter-dependency-silently-absent
area: ci-release
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/actions/runs/34175405275/job/101904005023
    observed_by: Codex
exit: none
---

# A local actionlint pass without its optional ShellCheck executable does not cover the shell checks a runner enables automatically.

## Why

The CI contract job above failed at actionlint 1.7.12 before running Python
tests: ShellCheck reported SC2034 for the unused TSan preflight loop variable.
Local Python CI contracts had passed 1657 tests, and local actionlint had been
used, but ShellCheck was absent locally. The PR-review semantic-parser test
also deliberately passes `-shellcheck=` because its scope is YAML semantics.
Neither result proves that the workflow's embedded shell passed the checks
performed on a runner where ShellCheck is installed. A correct tool version
alone does not establish the same enabled analysis surface.

With Ubuntu ShellCheck 0.9.0 extracted to a temporary directory and passed via
actionlint's explicit `-shellcheck` path, the original source reproduced the
exact remote warning. Logging the actual loop index fixed the warning while
retaining all ten mandatory starts and immediate infrastructure-failure exit.

## How to apply

- When verifying embedded workflow shell, check and record both actionlint and
  ShellCheck availability/version. Supply the ShellCheck executable explicitly
  when the local environment does not provide it on PATH.
- Distinguish YAML semantic tests, shell analysis and behavioral shell tests in
  evidence. Do not describe one as covering the others.
- Do not suppress the warning or lower runtime budgets to compensate for a
  verification-environment mismatch. Fix the exact source defect and rerun
  the actual enabled tools.

`exit: none`: the current CI invokes ShellCheck through actionlint, but there is
no common local verification entry point enforcing optional-tool parity. This
first occurrence records that gap without adding a new global gate; the narrow
nightly regression proves the startup diagnostic behavior, not general parity.
