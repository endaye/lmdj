# P1 default Catalog origin binding

Bind Creator's existing production same-origin Catalog proxy to the independently deployed default asset Worker. Without this setting, the production Worker deliberately answers 404 for every Catalog request and progressive Bank A initialization cannot fetch its Set. The independent service has actual public health/Catalog/manifest/16-WAV verification; this Task does not deploy Creator.

## Declared files

- `apps/creator-web/deploy/wrangler.json`
- `docs/plans/2026-10-02-p1-default-origin-binding.md`

Set the existing `CATALOG_UPSTREAM` Host binding to the canonical HTTPS root of `lmdj-default-assets.lmdj.workers.dev`. Keep the Worker, route-first asset handling, main route policy and all existing admission rules.

## Task verification

Load the actual committed configuration into the unchanged production Worker module and request all 18 Catalog/manifest/WAV routes against the actual independent service. Assert HTTP200, complete exact source bytes, digest, byte length and same-origin response policy. This checks the configured endpoint at the far side rather than merely asserting a literal in JSON. Run existing Worker route/redirect/validation tests and Python Catalog upstream/response parity tests, plus staged ownership. Selected complete batch-only proof remains a separate exact-head shipping obligation.

No new test or required gate is added; existing validation and the bounded read-only live experiment cover the endpoint wiring. Real Creator deployment, first-user boot and audible/device acceptance remain distinct obligations.

## Version Management

Version impact: none — the existing Host deployment setting selects its already-supported Catalog upstream. No API, Product Build, Assembly or immutable snapshot changes.

Documentation impact: none
Reason: This Task fills the existing deployment setting without changing the documented Catalog proxy, initialization contract or portal architecture. The plan records the actual endpoint and verification boundary; it does not claim a Creator deployment.
