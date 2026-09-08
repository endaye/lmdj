---
id: node-hosted-browser-transport-misses-cors
area: web-host
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/901
    observed_by: claude-code/opus-5
exit: none
---

# A browser network adapter proved only under Node passes every test and is still unreachable from the page, because the page's own policies stop the request before the adapter runs and the refusal arrives as an ordinary outage.

## Why

The Web Host's Sound Set `CatalogTransport`
(`packages/web-runtime-platform/web/soundset_catalog.mjs`) was proved against
the real fixture server in
`packages/web-runtime-platform/test/soundset_catalog.test.mjs`, which runs
under `node --test`. Node's `fetch` enforces no Content Security Policy, no
CORS and no `Cross-Origin-Embedder-Policy`, so that suite is green for a
Catalog no browser could read. Measured in a real browser during the #674
acceptance run, two independent layers refuse first, and both look identical to
an unreachable endpoint:

- The packaged Creator is served `connect-src 'self'`
  (`apps/creator-web/deploy/_headers:5`, `tools/web-runtime/serve_distribution.py:26`).
  Every real Catalog is on another origin, so the browser refuses:
  `Refused to connect because it violates the document's Content Security
  Policy`. This is #901.
- The page is also cross-origin isolated
  (`Cross-Origin-Embedder-Policy: require-corp`), so even with `connect-src`
  widened, a response carrying neither `Access-Control-Allow-Origin` nor
  `Cross-Origin-Resource-Policy: cross-origin` makes `fetch` reject with
  `Failed to fetch` (Chromium) or `Load failed` (WebKit) before any status
  reaches the adapter.

In both cases the adapter cannot tell a policy fault from a dead endpoint, so
it reports the locked `catalog_unavailable`, and the surface says "Catalog
unreachable". A deployment or policy defect reads on screen as someone else's
outage. Nothing in the transport, the schema or the Host manifest states either
requirement.

## How to apply

When a module issues network requests **from the page**, its acceptance
evidence must come from a real browser, against a real second origin, under the
distribution's real security headers. Keep the Node suite for shape and refusal
logic; add one browser leg that reads the network log rather than intercepting
it. A `page.route` stub, a same-origin server, or a proof server with relaxed
headers proves nothing about this class of failure — all three were tried
during #674 and all three hide it.

Reaching a cross-origin endpoint from this distribution needs **three** things
together, and any one missing produces the same indistinguishable
`catalog_unavailable`: the page's `connect-src` must admit the origin, the
response must carry `Access-Control-Allow-Origin`, and it must carry
`Cross-Origin-Resource-Policy: cross-origin`.
`tools/soundset-fixtures/catalog_fixture_server.py --cross-origin` is the
reference shape for the last two;
`tests/platform/web/creator/creator_web_soundset.spec.mjs` is the browser leg.

`exit: none` because the general rule is not mechanically decidable: no
deterministic check can tell that a given module will run in a page and that
its only proof runs under Node. The Sound Set Catalog instance is covered by
the browser spec named above, and that spec is red until #900, #901 and #902
are fixed; a second network adapter would need its own leg.
