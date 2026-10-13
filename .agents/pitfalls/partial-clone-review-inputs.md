---
id: partial-clone-review-inputs
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-13
    occurrence: https://github.com/endaye/lmdj/actions/runs/38346303442/attempts/2
    observed_by: Codex (GPT-6)
  - date: 2026-10-13
    occurrence: https://github.com/endaye/lmdj/actions/runs/38350197877/attempts/1
    observed_by: Codex (GPT-6)
exit: gate:tests/build/ci_review_pipeline_test.py
---

# Fetching fixed commits does not make a persistent partial clone's review blobs available

## Why

A runner can retain `remote.origin.promisor=true` and `blob:none` across jobs.
Fetching a new immutable head then provides its commit and trees while omitting
blob contents. The isolated collector correctly disables lazy fetch, so it
refuses the full diff before review. A warm cache or another runner's successful
read does not establish availability for this checkout and head.

Guarded read-only probes reproduced both occurrences: U03 runner 01 lacked
15 of 27 changed sides; U10 runner 02 lacked 9 of 16. Their original isolated
fixed diffs exited 128. A bounded manual cache recovery is not a durable
per-run preparation mechanism.

## How to apply

Use the trusted pipeline's explicit preparation before isolated collection:
inventory fixed changed blob sides without rename matching, include relevant
committed base attributes, fetch only missing OIDs, then read them back without
network access. Preserve checkout metadata and the collector's canonical rename,
attribute isolation and complete-input bounds. Never enable collector lazy
fetch or execute PR files to make collection pass.

The exit suite exercises real `file://` partial clones, independently cold
caches and a new head created after clone, followed by authenticated complete
source/diff comparison. It also preserves generated-boundary refusals, base
attribute semantics and unchanged checkout metadata. This absorbs the source
regression; actual current-runner acceptance remains UNRUN until a fresh review
uses the merged trusted control and publishes eligible evidence. The absorbed
ledger status does not settle all acceptance work in Issue #2118.
