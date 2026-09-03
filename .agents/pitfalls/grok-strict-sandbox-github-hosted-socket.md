---
id: grok-strict-sandbox-github-hosted-socket
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/598
    observed_by: grok-4.6
exit: gate:tests/build/ci_grok_review_workflow_test.py
---

# Grok `--sandbox strict` cannot start on GitHub-hosted Ubuntu because `/run/podman/podman.sock` is unreadable, and bwrap fail-closes.

## Why

Grok's Linux sandbox builds a deny list that includes the runtime socket
`/run/podman/podman.sock`. On GitHub-hosted `ubuntu-24.04` that path exists
but is not readable by the runner user (`Permission denied`), so profile
resolution fails with `runtime-socket deny resolution failed` and Grok
refuses to start. The same Pull Request already had a read-only tool
allowlist; the sandbox was extra hardening that made the job red before any
review ran.

## How to apply

Do not pass `--sandbox strict` or `--sandbox read-only` to Grok in
GitHub-hosted workflows. Keep isolation through `--tools` allowlisting
read-only tools and `--deny` on credential paths. The contract test in
`tests/build/ci_grok_review_workflow_test.py` fails if `--sandbox` returns to
the review command.
