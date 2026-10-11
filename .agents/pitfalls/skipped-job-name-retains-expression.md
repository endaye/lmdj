---
id: skipped-job-name-retains-expression
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-10
    occurrence: https://github.com/endaye/lmdj/actions/runs/38096694071
    observed_by: Codex
exit: gate:tests/build/ci_review_wait_test.py
---

# A skipped Actions job can retain its unexpanded name expression in the check inventory.

## Why

PR #2009 gave the skipped metadata Portal job a conditional name so it would
not shadow the real `Architecture Portal provenance` check. In the actual
edited-event run, GitHub's jobs API returned the expression text containing
both possible names, rather than the expected metadata alias. Actionlint and
a local expression fixture do not establish the check identity GitHub emits.

## How to apply

Inspect the actual jobs/check inventory before claiming a conditional name's
platform behavior. Match provenance names exactly, not by substring: the
unevaluated expression contains the real check name but proves nothing.
`ci_review_wait_test.py` retains the observed name and verifies that it cannot
mask successful real provenance, supply missing provenance, or supersede a
real failure. Do not interpret a skipped job as a successful source check.
