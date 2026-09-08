---
id: workflow-self-subscription-unvalidated
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/actions/runs/34187049368
    observed_by: Codex
exit: gate:tests/build/ci_workflow_event_graph_test.py
---

# Valid local workflow tests do not prove GitHub accepts a workflow subscribing to its own completion.

## Why

PR #898 installed `Self-test Report` with its own name in
`on.workflow_run.workflows`. The resulting run above failed with zero jobs.
A real manual settle dispatch was rejected with HTTP 422 and
`Workflow 'Self-test Report' cannot listen to itself`; it created no run.
Existing local checks had not rejected the event graph. A job guard cannot
repair a workflow GitHub rejects before evaluating jobs.

This is an event-graph validation gap, not the existing fake-tool-stub issue:
the failure was a platform-rejected subscription, not a mocked response shape.

## How to apply

Run the workflow event-graph regression when changing triggers. It rejects a
workflow's direct self-subscription with why/remedy; it does not certify arbitrary
cross-workflow cycles or prove remote event delivery. Preserve independent
scheduled recovery and obtain real dispatch/callback evidence, complete parent
associations and far-side journal assertions after changing completion routing.
Do not infer an infinite working chain from a relay's local tests or bypass
platform restrictions by adding permissions or weakening active-run checks.
