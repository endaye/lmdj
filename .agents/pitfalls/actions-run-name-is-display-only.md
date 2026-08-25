---
id: actions-run-name-is-display-only
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-25
    occurrence: https://github.com/endaye/lmdj/pull/318
    observed_by: OpenAI Codex GPT-5
exit: gate:tests/build/release_github_api_test.py
---

# GitHub Actions `run-name` is a dynamic display label, not the stable workflow identity release policy must authorize.

## Why

The Actions run and job REST projections expose the evaluated `run-name` as
`name` and `workflow_name`. Once CI added `run-name: Core CI / ...`, release
audit compared `Core CI / main` with policy identity `Core CI` and rejected a
successful exact-main full run. The stable identity lives in the workflow
metadata reached through the run's `workflow_id`; its ID and path must agree
with the run before its stable `name` can satisfy policy.

## How to apply

Resolve release workflow authority through the Actions workflow metadata
endpoint and bind its ID and path back to the selected run. Treat run and job
display names only as diagnostics; bind same-run jobs by exact run ID and head
SHA. `tests/build/release_github_api_test.py` enforces the live-shaped dynamic
name, stable metadata, cache, and mismatch cases.
