# Portal fixed canonical origin

Relates to #873 and #923.

## Task

The published Portal still emits the old Netlify origin in canonical metadata.
Use the confirmed fixed `https://docs.lmdj.workers.dev` origin in Docusaurus and
align current governance. Declared files: this plan,
`apps/docs-site/docusaurus.config.ts`,
`apps/docs-site/docs/operations/documentation-governance.mdx`, and
`docs/governance/architecture-portal.md`.

Validation: `scripts/docs-site.sh check`; inspect generated canonical
and Open Graph URL attributes and sitemap locations for the fixed origin;
`python3 tests/build/ci_change_scope_test.py` for staged ownership.
Do not edit frozen sources, snapshot metadata, custom DNS or old Netlify routing.
The Git-triggered deployment and live metadata verification follow merge.

## Version Management

Version impact: none; hosting metadata only, no Product/Assembly identity changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/documentation-governance/
