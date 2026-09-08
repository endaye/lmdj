# Cloudflare fixed site names

The owner authorized Cloudflare deployment and selected the prefixes `docs`,
`lab`, and `creator` on 2026-09-08. Custom domains remain unchanged.

Account: `0b62b8881c07f48f7935f5380a1f55db`; workers.dev subdomain: `lmdj`.

## Tasks

- Portal: prepare Git-triggered deployment to `docs.lmdj.workers.dev`.
  Existing local Portal preview remains independent until the Git path is ready.
- Creator: independently verify the signed published `lmdj-v1.0.42.0` archive,
  stage its exact bytes and generated security/cache headers, upload with the
  main route disabled, validate the candidate, then enable and verify the fixed
  `creator.lmdj.workers.dev` route. Disable the route on failed initial promotion.
- Lab: use the existing formal Diagnostic Web Runtime Host, consistent with
  the three-Netlify-site migration scope; the independent Audio Lab is excluded.
  Stage the Runtime asset from the same signed Release and verify its fixed URL.
- Portal publication: add a main-push GitHub workflow using the existing
  ci-general runner and a protected-branch deployment Environment. Validate
  new-site publication, preview failure, exact-prior recovery and lost receipts.
- Retain explicit version identities and HTTP/browser evidence. Existing
  Netlify deployments and custom DNS are preserved throughout this operation.

## Version Management

Version impact: none. Hosting configuration does not modify signed Product
assets, Product identity, or deployment evidence Contracts. Cloudflare pilot
observations must not be emitted as Netlify production evidence.

## Documentation impact

Documentation impact: required. Update the Portal and Creator deployment
runbooks with fixed targets and configuration state. Verify configuration JSON,
Wrangler local HTTP behavior, exact signed-byte comparisons including rejection
of corrupted expected payloads, and the Creator browser deployment suite.
Run the Portal check for documented source facts before commit.

Encoded dot segments can be rejected at the edge or normalized by the local
emulator. Acceptance requires validated 400/404 or exact verified index bytes.
Unknown assets remain 404. Preview-only robots overrides do not
apply to the fixed domain. These are explicit provider observations, without
changing existing Netlify checks or serialized deployment evidence Contracts.
