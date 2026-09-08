# Clarify the internal release marker in the portal

## Task

The current version-and-release page spells the internal release marker schema
as if it were a product Contract ID. The portal correctly rejects unknown
Contract IDs; `tools/release/transitions.py` and `tools/release/audit.py` confirm
this marker is internal release metadata, not an Assembly Contract.

Use the same descriptive internal-metadata wording already used by the adjacent
v2 paragraph. Preserve marker version v3, the complete batch reference and
`executor_event` requirements, and the no-migration rule. Do not change any
schema, source identity, Contract validation, or release operation.

Declared files:

- `apps/architecture-portal/docs/operations/version-and-release.mdx`
- this plan

Lowest-tier verification: `npm run validate:docs` in the portal. Required
verification: `scripts/architecture-portal.sh check`, staged ownership and
whitespace checks. No new gate or test is necessary for this prose correction.

## Version Management

Version impact: none — descriptive documentation only; all actual marker and
Product/Module/Contract identities remain unchanged.

## Documentation impact

Documentation impact: required
Affected portal pages: /operations/version-and-release

## Pitfall disposition

No new entry: this correction uses the existing adjacent internal-marker wording
and preserves the established Contract gate, without introducing a process rule.

## Verification results

`scripts/architecture-portal.sh check` passed: all 57 unit tests, current
document validation, 10 diagram sources and 20 outputs, generated facts,
release snapshot provenance, TypeScript, production build, and 42 route/internal
link checks. Staged-index ownership passed all 66 tests. No remote operation
or release audit was performed.
