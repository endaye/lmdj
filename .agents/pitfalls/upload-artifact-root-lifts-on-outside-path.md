---
id: upload-artifact-root-lifts-on-outside-path
area: ci-release
status: open
recurrences:
  - date: 2026-09-27
    occurrence: https://github.com/endaye/lmdj/pull/1587
    observed_by: claude-code/opus-5.5
exit: none
---

# Adding one path outside the workspace to an `upload-artifact` step silently nests every other member one level deeper.

## Why

`actions/upload-artifact` roots the archive at the least common ancestor of all
matched paths. #1587 added `${{ runner.temp }}/host-state-…/diagnostics` (under
`_work/_temp`) beside `build/deploy/<host>/evidence.json` (under
`_work/lmdj/lmdj`), which lifted the root to `_work/` and stored the evidence as
`lmdj/lmdj/build/deploy/<host>/evidence.json`. Both deployments of 1.0.61.0 went
green, but Channel promotion and the release driver select `evidence.json` by
exact root name and rejected the artifact as `deployment evidence artifact is
invalid`. Neither the workflow nor its source-text contract test showed the
break. It surfaced only when a consumer read a real artifact.

## How to apply

When a consumer reads an artifact member by name, keep every path in that upload
under one directory. Upload anything that lives elsewhere, such as
`runner.temp` state, as a separate artifact. The two Host deployment workflow
tests now pin the exact evidence upload path list. Any other artifact that is
read by member name needs the same pin. No general gate spans all workflows
yet, because consumers select members in different ways.
