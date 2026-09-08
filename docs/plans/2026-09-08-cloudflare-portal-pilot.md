# Cloudflare Portal pilot configuration

Relates to #873 and #867. Implements the approved migration design's portable
static configuration and first version-preview verification. It does not complete
the umbrella or authorize production cutover. The approved design and broader
plan are retained in the local docs/cloudflare-migration-design branch.

## Task

Declared files: root wrangler.json and .node-version; Portal static/_headers;
scripts/ci/scope_policy.json and tests/build/ci_change_scope_test.py;
docs/deploy/architecture-portal.md; current documentation-governance Portal page;
this plan. One implementation commit owns the portable config and its routing.

1. Bind configuration to the API-observed account and existing Worker.
2. Pin Node and npm; retain the complete Portal check and source dependency tree.
3. Preserve static 404 handling and security headers.
4. Register both new root files with explicit CI ownership and regression cases.
5. Verify credential-free build, root configuration dry-run and staged ownership.
6. Commit exact files, then rebuild generated revision for committed HEAD before
   any authorized non-production version upload. The uploader skips custom builds
   so the token is not inherited by npm/build scripts.
7. Smoke the resulting immutable Preview and prove active deployment unchanged.
   GitHub current-head status and managed branch triggers remain separate work.

## Version Management

Version impact: none. Static deployment tooling only; no Product/Assembly,
Module, Host or Contract identity changes or snapshot allocation.

## Documentation Impact

Documentation impact: required. Update /operations/documentation-governance and
the deployment runbook with its source Mermaid flow. Run architecture-portal.sh
check. Keep current production hosting claims accurate during the pilot.
