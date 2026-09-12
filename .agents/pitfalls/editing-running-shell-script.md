---
id: editing-running-shell-script
area: core
status: open
recurrences:
  - date: 2026-09-12
    occurrence: https://github.com/endaye/lmdj/issues/1230
    observed_by: Codex
exit: none
---

# Editing a shell script while it is executing can corrupt the interpreter's remaining input even when the final file passes syntax checks.

## Why

During the WebKit writer-lock prerequisite, a test invocation was inserted into
`web-toolchain-conformance.sh` while its `build-project-io` invocation was still
running. Both build targets completed, but the shell then reported an unmatched
quote at EOF and returned failure. The unchanged final file passed `bash -n` and
a fresh invocation completed successfully. The running shell retained an input
position that no longer matched the modified file. This was not a compiler or
browser defect, and the failed invocation was not a successful build result.

## How to apply

Collect the executing script's terminal result before editing that script.
If an edit is necessary immediately, stop and collect the owned invocation first,
then edit, check syntax and rerun it. Keep the interrupted or failed result
separate from the later verification. Do not restart merely because observation
timed out: first confirm the original process is terminal.

No repository mechanism currently knows all externally launched interpreters
and their input files; a source-only gate cannot enforce this operational rule.
