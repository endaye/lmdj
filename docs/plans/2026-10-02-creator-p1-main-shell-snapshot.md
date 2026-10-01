# P1 main-shell candidate snapshot

Freeze clean Source f1228516fb7b076189e4d380d2c06bededb9e7b2 using
`scripts/docs-site.sh version 2.0.76.0 canary`. This source retains main's
actual shell and workflow changes together with all reviewed P1 repairs.

## Declared files and verification

- `apps/architecture-portal/versions.json`
- `apps/architecture-portal/versioned_docs/version-2.0.76.0/**`
- `apps/architecture-portal/versioned_metadata/version-2.0.76.0.json`
- `apps/architecture-portal/versioned_sidebars/version-2.0.76.0-sidebars.json`
- `apps/architecture-portal/static/versions/2.0.76.0/diagrams/**`
- `docs/plans/2026-10-02-creator-p1-main-shell-snapshot.md`

The complete official freeze verifies current/frozen documents, all portal
tests, diagrams, provenance, TypeScript, production build and every route/link.
Run staged scope before commit, then own-tree projection with exact committed
head and retained main 1e0e1293fa9da81e96f412b9a52dbb967d00059d. Preserve all
existing main frozen files and real witnesses. The superseded unpublished75
snapshot remains in its original Git history; never rewrite or reuse it.

All eleven selected final-candidate lanes and current-head independent review
remain required. This snapshot alone does not establish shipping acceptance.

## Version Management

Version impact: none. Freeze the identities mechanically allocated in the
preceding Source Task; no manifest changes occur here.

Documentation impact: required
Affected portal pages: immutable /versions/2.0.76.0/ routes and version inventory.
Reason: reproducible documentation for the actual main-shell P1 candidate.
No release, Creator deployment or Channel promotion is performed.
