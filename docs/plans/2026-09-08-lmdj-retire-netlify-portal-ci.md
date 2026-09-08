# Retire Netlify Portal CI

## Task

Owner has retired Netlify for Cloudflare. Remove obsolete Portal build entry points and deployment-status smoke, keeping the existing Cloudflare build, Preview and production smoke. Relates to #867; external Netlify App disconnection remains independently observable. Preserve historical snapshots and deleted-path scope ownership. Do not change Creator/Runtime release adapters.

Declared files:
- netlify.toml
- .github/workflows/architecture-portal-smoke.yml
- apps/architecture-portal/scripts/netlify-build.mjs
- apps/architecture-portal/package.json
- apps/architecture-portal/package-lock.json
- scripts/ci/hosted_runner_policy.json
- docs/governance/architecture-portal.md
- docs/deploy/architecture-portal.md
- apps/architecture-portal/docs/operations/documentation-governance.mdx
- docs/plans/2026-09-08-lmdj-retire-netlify-portal-ci.md

Verification: hosted runner policy, scope ownership, Cloudflare deploy contracts, locked Portal install and complete scripts/architecture-portal.sh check. No new gate.

## Version Management

Version impact: none — private Portal tooling; no product or Contract identities change.

## Documentation impact

Documentation impact: required
Affected portal pages: /operations/documentation-governance

## Pitfall disposition

No new entry: retain historical path classification; explicitly document external App removal rather than assuming local deletion stops its checks.

## Verification results

Locked npm 10.9.3 install passed. Removing netlify-cli reduces lockfile packages from 2,380 to 1,368 with no version changes at retained package paths. Hosted-runner policy: 6 passed; Cloudflare deploy contracts: 4 passed; staged scope ownership: 66 passed. Complete Portal check passed, including snapshot provenance, production build and 42 routes/internal links. No remote deploy or integration mutation was executed. GitHub installation API returned 403 with current credentials, so external Netlify repository disconnection remains unverified.
