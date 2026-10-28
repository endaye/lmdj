---
id: job-output-through-env-exceeds-string-limit
area: ci-release
status: open
recurrences:
  - date: 2026-10-27
    occurrence: https://github.com/endaye/lmdj/pull/2511
    observed_by: claude-opus-5-5
exit: none
---

# A step that receives a job output through an environment variable or an argument fails before it runs once that output passes 128 KiB, and its log shows no error from the step itself.

## Why

Linux refuses any single `argv` or environment string longer than
`MAX_ARG_STRLEN` (128 KiB) at `execve`. The PR Contract `release-freeze` job
passed the change-scope manifest as `MANIFEST: ${{ needs.change-scope.outputs.manifest }}`
and then as `--manifest-json "$MANIFEST"`. The manifest grows with the number
of changed paths, and #2511 changed 2,383 paths (276 KB), so bash never
started. The log stopped after printing the step's `env:` block, with no line
from the script, and the job was red with no freeze active. macOS allows much
longer strings, so the same command passes locally and hides the defect. Using
`fromJSON(...)` in an `if:` is unaffected, because it never reaches `execve`.

## How to apply

When a step needs data whose size scales with the PR (changed files,
inventories, review bodies), pass it as a file: write it in the producing job,
upload it as an artifact of the same run, and give the consumer a file path.
Do not use `env:`, an argument, or `${{ }}` text spliced into `run:`. A red
step whose log ends at its `env:` block, with no script output, is this
failure. Reproduce it on Linux, or measure the string's size; a macOS run
cannot reproduce it. The release-freeze wiring is held by
`tests/build/ci_workflow_topology_test.py`
(`test_pr_contract_release_freeze_reads_the_manifest_from_a_file`). No generic
gate exists yet, because "may this output grow past 128 KiB" is a judgment
about the data, not something decidable from workflow syntax.
