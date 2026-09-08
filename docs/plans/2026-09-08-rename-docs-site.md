# Rename the active documentation site

## Scope

Rename active `apps/architecture-portal` source to `apps/docs-site`, npm package
to `@lmdj/docs-site`, visible name to LMDJ Docs, and primary command to
`scripts/docs-site.sh`. Keep a forwarding legacy command. Update current docs,
CI path ownership, workflow build inputs, deployment configuration and release
tool consumers. No Changelog feature, URL, Worker, Environment or workflow
identity changes; no remote operations in this implementation Task.

Frozen version directories, provenance and versions.json retain their original
Git paths in `apps/architecture-portal`; relative links expose them to the active
site. This preserves immutable history and authenticated introducing revisions.
Current projection generation accepts the renamed source root while historical
verification continues using original evidence paths. Do not rewrite snapshots.

Declared files: moved active site files and links, archive README, apps README,
AGENTS/CLAUDE, ignore rules and Wrangler config; current governance/deploy/source
docs; affected repo skills, CI workflows/policy/preflight, release tool consumers
and their path tests; new wrapper and this plan.

## Verification

- Site unit tests, including rename/provenance and tamper rejection.
- `scripts/docs-site.sh check` (docs, diagrams, facts, provenance, build, links).
- Legacy wrapper argument compatibility.
- CI scope and local preflight tests after staging.
- Affected build/deployment/release path tests; root active-tree check.
- Verify frozen archive has no modified/deleted tracked files and exact-path
  staging has no caches or build outputs. No physical/product acceptance claim.

## Version Management

Version impact: none. Private documentation package renamed; no Product Build,
Core Module, Provider or Contract identity changes, and no snapshot allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: / /operations/documentation-governance /operations/testing-and-proof /operations/version-and-release /core/overview /hosts/overview
Reason: new project identity, commands and current source paths; existing routes
and immutable historical contents remain unchanged.
