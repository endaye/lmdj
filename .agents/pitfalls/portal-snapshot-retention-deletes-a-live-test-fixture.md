---
id: portal-snapshot-retention-deletes-a-live-test-fixture
area: docs-governance
status: open
recurrences:
  - date: 2026-09-14
    occurrence: https://github.com/endaye/lmdj/pull/1310
    observed_by: deepseek-v4-flash
exit: none
---

# Trimming frozen Portal snapshots to a retention window silently deletes the fixture some test pins by name, and the test only turns red because the version it sampled happened to age out of the window.

## Why

The Portal keeps every frozen Product Build under `apps/architecture-portal/`
(`versioned_docs`, `versioned_sidebars`, `versioned_metadata`,
`versioned_provenance`, `static/versions/`) and lists them in `versions.json`.
Nothing prunes them, so the tree grew to 51 snapshots — 1,958 documents of
which 95%+ were frozen page copies that no current page links. A retention
policy (keep the latest N) is the obvious fix, and the removal is safe for the
product: `check-snapshot-projection.mjs` only judges snapshots the change
*adds* and explicitly tolerates a removal, and the release audit
(`tools/release/audit.py`) plus `check-release-docs.mjs` validate only the
*current* Product Build's snapshot. So the trimming itself is green.

The trap is the test suite. `apps/docs-site/test/content-inventory.test.mjs`
sampled a snapshot by hard-coded path:

```js
path.join(versionedDocsRoot, 'version-1.0.13.0/overview/index.mdx')
```

That version sat 38 builds below the head, so it was never in any plausible
retention window — it survived only because nothing had ever pruned old
snapshots. The moment a retention policy lands, the path disappears and the
test fails with `ENOENT`, not with the content assertion it was written to
make. A retention change therefore has two jobs: prune, and re-point every test
that named a version now outside the window.

Worse, that same pinned version hid a second, already-dead assertion. The test
was named "formal snapshot does not describe itself as current main
documentation" and asserted the page does **not** contain `随 \`main\` 演进` /
`current 文档` / `当前文档`. That was true of the v1.0.13.0-era page, which used
an `:::info[正式快照]` block. Since the BuildIdentity explainer was introduced,
**every** page — current or snapshot — carries the neutral sentence "上方 Build
Identity 会明确标出本页属于随 `main` 演进…", so the negative assertion is
unmeetable by any recently frozen page. Pinning the sample to the one ancient
version kept the test green while the invariant it claimed to check no longer
held for anything real. Trimming the archives did not create that rot; it only
exposed it.

## How to apply

- **When you add or change a snapshot retention window, grep every test for a
  hard-coded `version-X.Y.Z` path and re-point it to a version inside the
  window.** Do not sample a version by literal path; read the window from
  `versions.json` and take a real member (e.g. the oldest retained), so the
  next retention change cannot strand it again. `apps/docs-site/versioned_docs`
  and friends are symlinks into `apps/architecture-portal/`, so a path that
  resolves on the check host may not exist after piping through the symlink —
  resolve the retained version from the list, and read the file through the
  documented root.
- **A test green only because its fixture is frozen in the past is not testing
  the present.** When a pinned sample predates a governing concept (here: the
  BuildIdentity explainer that made the negative assertion universally false),
  re-derive what the assertion is actually able to decide and assert that
  instead; record in a comment why the old form is no longer decidable. Do not
  preserve a dead assertion by re-pinning to another old version.
- **Removing archived snapshots is a `Documentation impact: none` change with a
  real reason, not a silent one.** The retention rule itself belongs in
  `docs/governance/architecture-portal.md` in the same Task; old snapshots stay
  auditable at their historical Git revisions, so state that and confirm the
  current Product Build snapshot and its provenance remain intact
  (`check-release-docs.mjs`).
- **Before pruning, confirm no current content links the routes you are about
  to remove.** Versioned pages link only within their own snapshot; a link from
  `apps/docs-site/docs/` or a generated Release changelog into a specific
  `/versions/X.Y.Z/` route is the case that makes a removal break navigation
  while every gate stays green.

No mechanism exits this entry. "Which version a test should sample" and "is
this assertion still decidable" are authorial judgments about test intent, not
a mechanically decidable invariant over a moving retention window, so neither
half meets the gate admission criteria. If this recurs, the exit is a section
in the Portal/retention guidance requiring tests to resolve the retained sample
from `versions.json`.
