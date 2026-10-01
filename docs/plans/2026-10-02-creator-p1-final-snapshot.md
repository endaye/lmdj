# P1 final candidate snapshot

Freeze the settled clean source 809da94ba5e212041ad1d070a7aa52fba772328b
with the supported `scripts/docs-site.sh version 2.0.75.0 canary` command.
The preceding allocation Task derives these identities from verified manifests.
The snapshot describes the reviewed P1 repairs and retained main recovery fixes.

## Declared files and verification

- `apps/architecture-portal/versions.json`
- `apps/architecture-portal/versioned_docs/version-2.0.75.0/**`
- `apps/architecture-portal/versioned_metadata/version-2.0.75.0.json`
- `apps/architecture-portal/versioned_sidebars/version-2.0.75.0-sidebars.json`
- `apps/architecture-portal/static/versions/2.0.75.0/diagrams/**`
- `docs/plans/2026-10-02-creator-p1-final-snapshot.md`

Run the complete official freeze, including current/frozen document validation,
49 portal tests, diagram checks, snapshot provenance, TypeScript, production
build and all route/link assertions. Inspect the exact staged inventory and
run `python3 tests/build/ci_change_scope_test.py` before commit. Then run the
PR own-tree snapshot projection against the committed snapshot head and retained
main. Preserve all 71 files of main's Build 71 snapshot and real squash witness
byte-identically. No metadata rewrite or invented witness is permitted.

All selected final-candidate batch-only lanes remain required before merge;
the freeze is documentation evidence and does not replace their source proofs.

## Version Management

Version impact: none. This Task freezes the identities already allocated and
verified by the preceding source Task; it does not change a manifest.

Documentation impact: required
Affected portal pages: immutable /versions/2.0.75.0/ routes and the version
inventory. Reason: preserve reproducible documentation for the canary candidate.
No tag, release publication, Creator deployment or Channel promotion is covered.
