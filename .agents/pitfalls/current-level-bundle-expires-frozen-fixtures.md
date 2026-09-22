---
id: current-level-bundle-expires-frozen-fixtures
area: ci-release
status: open
recurrences:
  - date: 2026-09-22
    occurrence: https://github.com/endaye/lmdj/pull/1596
    observed_by: Kimi Code (k3)
exit: none
---

# A frozen Project Bundle fixture dies at every Contract level bump.

## Why

Project Bundles carry no backward compatibility during active development
(`docs/prd/decisions/2026-09-15-project-bundle-current-level-only.md`):
readers accept exactly the current envelope. Any test fixture that freezes a
bundle as bytes — the Creator deployment spec's base64 fixture froze
`lmdj.project.v3` / bundle contract `1.1.0` — becomes invalid the moment the
writer level moves, and the failure surfaces far from the cause (a deployed
Host rejecting the import with `INVALID_PROJECT` inside a browser journey,
not a fixture test). The batch proofs never caught it because they regenerate
their fixtures at proof time; only the frozen deployment fixture went stale.
UI renames have the same shape: the spec's `heading "Sequence"` assertion
outlived the D01-D04 rename to `GROOVE / NN` while the surface rendered fine.

## How to apply

When a Task bumps the Project or Bundle Contract level, regenerate frozen
deployment fixtures in the same Task with the current writer (the procedure
in `scripts/creator-web.sh generate_project_fixture`, then gzip+base64 into
the fixture module), and grep deployment specs for locators that name
headings the redesign renamed — prefer stable region/aria labels over heading
text. No eligible gate exists yet: freshness of a frozen fixture against the
writer level is not mechanically decidable today, so the entry stays open
with `exit: none`.
