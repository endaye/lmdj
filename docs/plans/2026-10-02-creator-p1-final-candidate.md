# P1 final reviewed-source candidate

Settle all independent-review repairs and retain main e4e17e7f before freezing
the final integration source. The verified live main still declares Build 71;
the retained unpublished candidate declares Build 74 and Creator 5.0.2. Derive
Build 75 by incrementing that candidate BUILD and resetting PATCH, and derive
Creator 5.0.3 by one PATCH increment. The candidate is absent from both
local/live release intents and exact remote tags. Other Module/Host manifests
and dependency pins remain as already settled. No release or Creator deployment.

## Declared files and verification

- `apps/architecture-portal/versions.json`
- `apps/creator-web/module.json`
- `apps/creator-web/package-lock.json`
- `apps/creator-web/package.json`
- `apps/docs-site/docs/operations/creator-changelog.mdx`
- `apps/docs-site/test/repo-facts.test.mjs`
- `products/lmdj/assembly.json`
- `products/lmdj/assembly.lock.json`
- `products/lmdj/generated/web-runtime-identity.json`
- `products/lmdj/generated/web-runtime-identity.mjs`
- `products/lmdj/src/compiled_assembly.cpp`
- `products/lmdj/version.json`
- `tests/build/version_test.py`
- `docs/plans/2026-10-01-creator-p1-integration-proof.md`
- `docs/plans/2026-10-02-creator-p1-final-candidate.md`
- The exact 211 tracked files of unpublished 2.0.72.0, 2.0.73.0 and 2.0.74.0
  under `apps/architecture-portal/versioned_docs/version-BUILD/`,
  `versioned_metadata/version-BUILD.json`,
  `versioned_sidebars/version-BUILD-sidebars.json`, and
  `static/versions/BUILD/diagrams/` (HTML and SVG).

Remove only those unpublished snapshots from the final inventory. Their
original Git commits and negative/partial proof evidence remain immutable;
never regenerate their metadata or invent a squash witness. They were not on
main. The source projection of each old introduced snapshot predates the
repairs, so none can represent this PR's own landing tree. All 71 files of
main's 2.0.71.0 snapshot, diagrams, metadata, sidebar and real squash witness
must remain byte-identical to retained main. Do not prune unrelated history.

Run manifest verification, generated Assembly/Runtime identity checks, the
version suite, staged scope and current portal source facts. The full pre-freeze
portal command must be run and its expected missing-new-snapshot refusal
retained; that is not a complete portal pass. Official freezing requires clean
HEAD, so commit the settled source, then immediately run the stable snapshot
command in the separate documentation Task. Full portal and PR own-tree
snapshot-projection proof must pass after freezing. All eleven selected
batch-only lanes and the final independent current-source review must bind the
new candidate inputs; old 74 passes never stand in for changed inputs.

## Version Management

Version impact: new Product Build and Creator Host PATCH, mechanically derived
from verified retained manifests. Keep additive Core/Platform MINOR and offline
Creator MAJOR settlement already in this branch. Preserve prior published
identities. Freeze an immutable canary snapshot with `scripts/docs-site.sh
version` after the clean source commit. No tag, publication, Creator deployment
or Channel promotion is authorized.

Documentation impact: required
Affected portal pages: /hosts/creator-web/, /operations/creator-changelog/ and
generated component/version routes, plus the immutable candidate inventory.
Reason: revised source identities and truthful own-tree snapshot provenance.
