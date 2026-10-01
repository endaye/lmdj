# P1 T3: original default kit and independent asset service

Relates to #1663. Approved scope: sixteen original synthesized percussion sounds,
CC0 rights declaration, an independent Cloudflare asset Worker using the existing
account, and Creator's existing same-origin Catalog proxy. No Creator deployment,
Product release or Channel promotion is initiated here.

## Declared files

- `products/lmdj/assets/default-kit/` corpus and rights declaration
- `tools/asset-server/{kit.py,worker.mjs,wrangler.json,kit_test.py,worker.test.mjs}`
- `scripts/asset-server.sh` and `.github/workflows/deploy-default-assets.yml`
- `scripts/creator-web.sh`
- Creator proxy upstream configuration is bound in T5 to the verified service URL,
  after deployment returns its actual account subdomain.
- `scripts/ci/{scope_policy.json,lane_registry.json,hosted_runner_policy.json}` and relevant ownership tests
- `docs/operations/default-assets.md`, current Creator portal page and this plan

## Implementation and verification

Generate original percussion from deterministic synthesis with no sampled source
recordings or third-party input. Store only canonical manifest and immutable
content-addressed PCM16 WAV. Validate complete schema, license, distinct playable
slots, hash/length, total unique bytes and deterministic regeneration. Serve only
Catalog/manifest/blob/health GET/HEAD routes, immutable caching for content hashes,
explicit CORS and bounded errors. Route tests catch traversal and arbitrary asset
exposure. A real GET with content hash comparison is required for live readiness;
source/local tests are insufficient.

## Version Management

Version impact: default corpus addition and deployment configuration; coordinated
Product/Host identity debt is settled in P1 T8. Existing Contract IDs unchanged.

## Documentation impact

Documentation impact: required
Affected portal route: /hosts/creator-web/
Reason: default content provenance and independent Catalog hosting.

## Current-main conflict reconciliation

Refresh against protected main and retain its current identities, immutable Build
snapshot, takeover, IndexedDB and Sample playback source. The sole textual
conflict is two independently appended Creator portal sections: keep both the
asset provenance/service section and Continue in another tab. The reconciliation
owns this plan and the Creator portal page, in addition to the unchanged imported
main merge inventory; asset corpus, Worker and deployment behavior are unchanged.
Run the full asset validator/Worker suite, scope ownership tests, and full portal
check before committing. Recompute every selected batch input key on the clean
new head; old-head proof is reusable only for identical lane inputs. A binary
review collector refusal remains missing independent review, never approval.
No asset deployment or Product Build is created by reconciliation.
