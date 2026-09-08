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
  Policy`. This was #901, and it is fixed: the Creator now reaches its Catalog
  through a same-origin prefix the Host forwards, so `connect-src 'self'` --
  the exfiltration barrier around the Projects and audio in OPFS -- never has
  to name a foreign origin at all.
- A cross-origin response carrying no `Access-Control-Allow-Origin` makes
  `fetch` reject with `Failed to fetch` (Chromium) or `Load failed` (WebKit)
  before any status reaches the adapter.

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

Reaching a cross-origin endpoint **directly** from a page needs two things
together, and either one missing produces the same indistinguishable
`catalog_unavailable`: the page's `connect-src` must admit the origin, and the
response must carry `Access-Control-Allow-Origin`.

An earlier revision of this entry, and #901 itself, also demanded
`Cross-Origin-Resource-Policy: cross-origin`, on the grounds that the page is
cross-origin isolated. **That is wrong, and it was measured wrong.** The
cross-origin resource policy check returns *allowed* whenever the request's
mode is not `no-cors`, and a `fetch()` is `cors` by default, so COEP's CORP
requirement binds `no-cors` subresource loads and not this call. Driving the
deployed COOP/COEP/CSP header shape against a second origin under all four
header combinations, in Chromium and WebKit, on a page reporting
`crossOriginIsolated === true`: `Access-Control-Allow-Origin` alone answers
200 with `type: "cors"`; CORP alone is blocked, and Chromium names the missing
ACAO as the reason. The original #674 observation appears to have measured the
both-absent case and attributed it to both headers. The cost of the error was
a requirement on every third-party Catalog operator that nothing in the
platform actually imposes.

`tools/soundset-fixtures/catalog_fixture_server.py --cross-origin` sends both
and remains the reference shape for a Catalog meant to be read directly by a
page. The LMDJ Creator no longer is such a page: it forwards through
`/soundset-catalog/`, so its Catalog needs neither header.
`tests/platform/web/creator/creator_web_soundset.spec.mjs` is the browser leg,
and it runs the fixture **without** `--cross-origin` precisely so that a
rewiring back to a direct fetch fails instead of passing quietly.

`exit: none` because the general rule is not mechanically decidable: no
deterministic check can tell that a given module will run in a page and that
its only proof runs under Node. The Sound Set Catalog instance is covered by
the browser spec named above, and that spec is red until #900 is fixed; a
second network adapter would need its own leg.
