// The Cloudflare Worker that fronts both Web Hosts, and in particular the
// #901 Catalog proxy it grew.
//
// These cases are about the two properties that make the proxy a forwarder
// rather than a relay: that the destination cannot be moved by anything in the
// request, and that the admitted path grammar is exactly the two shapes
// `soundset_catalog.mjs` can spell. A case that only checked "a good request
// works" would pass against an open relay.
import assert from "node:assert/strict";
import test from "node:test";

import { readFileSync } from "node:fs";

import worker from "../deploy/cloudflare_worker.mjs";
import { createFetchCatalogClient } from
  "../../../packages/web-runtime-platform/web/soundset_catalog.mjs";

const UPSTREAM = "https://catalog.example.test/sets/";
const DIGEST = "a".repeat(64);
const OTHER_DIGEST = "b".repeat(63) + "c";

// A stand-in for the static asset binding, so a case can tell "served as an
// asset" apart from "answered by the proxy".
function assetsBinding(seen) {
  return {
    fetch(request) {
      seen.push(new URL(request.url).pathname);
      return new Response("asset", { status: 200 });
    },
  };
}

// Replaces global fetch for the duration of one case and records every target
// the Worker actually reached for.
function withUpstream(handler, run) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (target, options) => {
    calls.push({ target, options });
    return handler(target, options);
  };
  return (async () => {
    try {
      return { result: await run(), calls };
    } finally {
      globalThis.fetch = original;
    }
  })();
}

function creatorEnv(overrides = {}) {
  return { ASSETS: assetsBinding([]), CATALOG_UPSTREAM: UPSTREAM, ...overrides };
}

function get(path, init = {}) {
  return new Request(`https://creator.lmdj.workers.dev${path}`, init);
}

test("the Host contract is unchanged: / and /index.html reach the same asset", async () => {
  const seen = [];
  const env = { ASSETS: assetsBinding(seen) };
  await worker.fetch(get("/"), env);
  await worker.fetch(get("/index.html"), env);
  assert.deepEqual(seen, ["/index.html", "/index.html"]);
});

test("a Host with no CATALOG_UPSTREAM answers 404 and never reaches the network", async () => {
  // The diagnostic Lab, and any Creator deployment that offers no Catalog.
  const { result, calls } = await withUpstream(
    () => {
      throw new Error("the Worker must not fetch without a configured upstream");
    },
    () => worker.fetch(get(`/soundset-catalog/${"catalog/index.json"}`), {
      ASSETS: assetsBinding([]),
    }),
  );
  assert.equal(result.status, 404);
  assert.deepEqual(calls, []);
});

test("an index request reaches exactly the configured upstream", async () => {
  const { result, calls } = await withUpstream(
    () => new Response('{"sets":[]}', { status: 200 }),
    () => worker.fetch(get("/soundset-catalog/catalog/index.json"), creatorEnv()),
  );
  assert.equal(result.status, 200);
  assert.equal(result.headers.get("content-type"), "application/json");
  assert.equal(result.headers.get("cache-control"), "no-store");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].target, `${UPSTREAM}catalog/index.json`);
  assert.equal(calls[0].options.redirect, "manual");
  assert.equal(calls[0].options.method, "GET");
});

test("an object request composes the upstream, the kind and the digest", async () => {
  for (const kind of ["manifest", "blob"]) {
    const { result, calls } = await withUpstream(
      () => new Response(new Uint8Array([1, 2, 3]), { status: 200 }),
      () => worker.fetch(
        get(`/soundset-catalog/object/${kind}/${DIGEST}`), creatorEnv(),
      ),
    );
    assert.equal(result.status, 200);
    assert.equal(calls[0].target, `${UPSTREAM}object/${kind}/${DIGEST}`);
    assert.equal(
      result.headers.get("content-type"),
      kind === "manifest" ? "application/json" : "application/octet-stream",
    );
    assert.equal(
      result.headers.get("cache-control"),
      "public, max-age=31536000, immutable",
    );
  }
});

test("nothing in the request can move the destination off the configured host", async () => {
  // An absolute URL in the path, a protocol-relative host, and a query string
  // carrying another origin. Each stays inside the prefix, so each reaches the
  // proxy and each must be refused there without touching the network.
  const refusedByTheProxy = [
    "/soundset-catalog/https://attacker.example/steal",
    "/soundset-catalog//attacker.example/steal",
    "/soundset-catalog/object/manifest/" + DIGEST + "?to=https://attacker.example",
    "/soundset-catalog/catalog/index.json?to=https://attacker.example",
  ];
  for (const attempt of refusedByTheProxy) {
    const seen = [];
    const { result, calls } = await withUpstream(
      (target) => {
        throw new Error(`the Worker reached ${target} for ${attempt}`);
      },
      () => worker.fetch(get(attempt), creatorEnv({ ASSETS: assetsBinding(seen) })),
    );
    assert.equal(result.status, 404, attempt);
    assert.deepEqual(calls, [], attempt);
    assert.deepEqual(seen, [], attempt);
  }
});

test("a traversal out of the prefix becomes an ordinary asset miss, not a fetch", async () => {
  // `new URL` resolves dot segments and decodes `%2e`, so both of these leave
  // the prefix before the Worker branches: they are handled as asset requests
  // and answer 404 under `not_found_handling: none`. Cloudflare's edge may
  // instead reject an encoded dot segment before the Worker runs -- the
  // `cloudflare-static-response-semantics` pitfall records that difference from
  // the local emulator. Either way the request never reaches the network, which
  // is the property under test here.
  for (const attempt of [
    "/soundset-catalog/../../attacker",
    "/soundset-catalog/%2e%2e/%2e%2e/attacker",
  ]) {
    const seen = [];
    const { calls } = await withUpstream(
      (target) => {
        throw new Error(`the Worker reached ${target} for ${attempt}`);
      },
      () => worker.fetch(get(attempt), creatorEnv({ ASSETS: assetsBinding(seen) })),
    );
    assert.deepEqual(calls, [], attempt);
    assert.deepEqual(seen, ["/attacker"], attempt);
  }
});

test("request headers do not travel upstream", async () => {
  const { calls } = await withUpstream(
    () => new Response("{}", { status: 200 }),
    () => worker.fetch(
      get("/soundset-catalog/catalog/index.json", {
        headers: {
          Cookie: "session=must-not-leak",
          Authorization: "Bearer must-not-leak",
          "X-Forwarded-Host": "attacker.example",
        },
      }),
      creatorEnv(),
    ),
  );
  const forwarded = calls[0].options.headers;
  assert.deepEqual(Object.keys(forwarded), ["Accept"]);
});

test("the admitted grammar is exactly the two shapes the transport can spell", async () => {
  const refused = [
    "/soundset-catalog/",
    "/soundset-catalog/catalog/index.jsonx",
    "/soundset-catalog/catalog/other.json",
    "/soundset-catalog/object/archive/" + DIGEST,
    "/soundset-catalog/object/manifest/" + DIGEST.toUpperCase(),
    "/soundset-catalog/object/manifest/" + DIGEST.slice(0, 63),
    "/soundset-catalog/object/manifest/" + DIGEST + "extra",
    "/soundset-catalog/object/manifest/" + OTHER_DIGEST + "/again",
    "/soundset-catalog/object/manifest",
  ];
  for (const path of refused) {
    const { result, calls } = await withUpstream(
      (target) => {
        throw new Error(`the Worker reached ${target} for ${path}`);
      },
      () => worker.fetch(get(path), creatorEnv()),
    );
    assert.equal(result.status, 404, path);
    assert.deepEqual(calls, [], path);
  }
});

test("a normalised alias resolves to the same target, never a different one", async () => {
  // `new URL` resolves dot segments and maps `\` to `/`, so several spellings
  // reach the Worker as one admitted path. The proof server matches the raw
  // target and refuses them, and that divergence is left open on purpose:
  // closing it means refusing requests the runtime normalised, which cannot be
  // tested against the real edge and would risk refusing the two legitimate
  // shapes. What is pinned instead is that an alias can only ever resolve to
  // the SAME target -- so a future edit cannot turn one into a different fetch.
  const canonical = `${UPSTREAM}object/manifest/${DIGEST}`;
  for (const alias of [
    `/soundset-catalog/x/../object/manifest/${DIGEST}`,
    `/soundset-catalog/object/./manifest/${DIGEST}`,
    `/soundset-catalog/object\\manifest\\${DIGEST}`,
    `/soundset-catalog/a/%2e%2e/object/manifest/${DIGEST}`,
    `/soundset-catalog/object/manifest/../manifest/${DIGEST}`,
  ]) {
    const { result, calls } = await withUpstream(
      () => new Response(new Uint8Array([1]), { status: 200 }),
      () => worker.fetch(get(alias), creatorEnv()),
    );
    if (result.status === 200) {
      assert.equal(calls.length, 1, alias);
      assert.equal(calls[0].target, canonical, alias);
    } else {
      assert.deepEqual(calls, [], alias);
    }
  }
});

test("the endpoint the shipped index.html configures reaches this Worker", async () => {
  // The seam. `index.html` tells an operator what to configure, the transport
  // composes a URL from it, and this Worker decides whether that URL is a
  // Catalog path. Those three live in two languages and two deployment units,
  // and nothing asserted they agreed -- the agreement was only ever checked by
  // reading. This composes the real request from the real instruction and the
  // real transport, so it fails if any of the three moves.
  //
  // It does NOT cover Cloudflare's own routing: `run_worker_first` decides
  // whether the request reaches this Worker at all, and whether its `*` glob
  // spans multiple path segments is unverified from here. See the runbook.
  const html = readFileSync(
    new URL("../../creator-web/index.html", import.meta.url), "utf8",
  );
  const configured = html.match(
    /content="(https:\/\/[^"]*soundset-catalog[^"]*)"/,
  )?.[1];
  assert.ok(
    configured,
    "index.html no longer shows an operator a soundset-catalog endpoint",
  );

  const asked = [];
  const client = createFetchCatalogClient({
    endpoint: configured,
    fetch: async (target) => {
      asked.push(target);
      return new Response("{}", { status: 200 });
    },
  });
  await client.readIndex();
  await client.readObject({ object_kind: "manifest", sha256: DIGEST });
  assert.equal(asked.length, 2);

  for (const target of asked) {
    const servedAsAsset = [];
    const { result, calls } = await withUpstream(
      () => new Response("{}", {
        status: 200,
        headers: { "content-length": "2" },
      }),
      () => worker.fetch(
        new Request(target),
        { ASSETS: assetsBinding(servedAsAsset), CATALOG_UPSTREAM: UPSTREAM },
      ),
    );
    assert.equal(result.status, 200, `${target} was not forwarded`);
    assert.deepEqual(
      servedAsAsset, [],
      `${target} fell through to the asset store instead of the forward`,
    );
    assert.equal(calls.length, 1);
    assert.ok(calls[0].target.startsWith(UPSTREAM), calls[0].target);
  }
});

test("only GET is admitted", async () => {
  for (const method of ["POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]) {
    const { result, calls } = await withUpstream(
      (target) => {
        throw new Error(`the Worker reached ${target} for ${method}`);
      },
      () => worker.fetch(
        get("/soundset-catalog/catalog/index.json", { method }), creatorEnv(),
      ),
    );
    assert.equal(result.status, 405, method);
    assert.deepEqual(calls, [], method);
  }
});

test("a malformed or non-https upstream fails closed", async () => {
  // Every value here is one that parsing would silently reinterpret, or that
  // this Worker will not forward to at all. `UPSTREAM_PARITY_REFUSED` in
  // `apps/creator-web/test/server_test.py` is the full shared corpus: the two
  // implementations must refuse the same set, because a value one accepts and
  // the other rewrites is how a proof server stops standing in for production.
  const rejected = [
    "http://catalog.example.test/",
    "ftp://catalog.example.test/",
    "not-a-url",
    "",
    // Explicit character admission must not depend on the URL parser version.
    "https://catalog.example.test/a^b/",
    "https://catalog!example.test/b/",
    "https://catalog~example.test/b/",
    "https://catalog{example}.test/b/",
    "https://.catalog.example.test/b/",
    "https://-catalog.example.test/b/",
    "https://catalog.example.test/?query=1",
    "https://catalog.example.test/#fragment",
    "https://catalog.example.test//double/",
    // Credentials, including an empty userinfo that `URL.origin` would drop.
    "https://user:pass@catalog.example.test/",
    "https://user@catalog.example.test/",
    "https://@catalog.example.test/",
    "https://:@catalog.example.test/",
    // A backslash terminates the authority, so this resolves to `evil.test`.
    "https://evil.test\\@catalog.example.test/",
    // Normalisations: dot segments, encoded dot segments, non-ASCII host,
    // uppercase host, surrounding whitespace, a default port, and a base that
    // does not already end in `/`.
    "https://catalog.example.test/a/../b/",
    "https://catalog.example.test/a/%2e%2e/b/",
    "https://exämple.test/b/",
    "https://CATALOG.Example.Test/b/",
    "  https://catalog.example.test/b/  ",
    "https://catalog.example.test:443/b/",
    "https://catalog.example.test",
  ];
  for (const upstream of rejected) {
    const { result, calls } = await withUpstream(
      (target) => {
        throw new Error(`the Worker reached ${target} for upstream ${upstream}`);
      },
      () => worker.fetch(
        get("/soundset-catalog/catalog/index.json"),
        creatorEnv({ CATALOG_UPSTREAM: upstream }),
      ),
    );
    assert.equal(result.status, 404, upstream);
    assert.deepEqual(calls, [], upstream);
  }
});

test("an upstream that redirects, errors or oversizes is not passed through", async () => {
  const cases = [
    [() => Response.redirect("https://attacker.example/steal", 302), 502],
    [() => new Response(null, { status: 500 }), 502],
    [() => new Response(null, { status: 403 }), 502],
    [() => new Response(null, { status: 404 }), 404],
    [() => new Response(new Uint8Array(8 * 1024 * 1024 + 1), { status: 200 }), 502],
    [() => {
      throw new Error("upstream unreachable");
    }, 502],
  ];
  for (const [handler, expected] of cases) {
    const { result } = await withUpstream(
      handler,
      () => worker.fetch(get("/soundset-catalog/catalog/index.json"), creatorEnv()),
    );
    assert.equal(result.status, expected);
  }
});

test("each shape carries its own bound, and the body is bounded before it is held", async () => {
  // One 8 MiB bound for both shapes would leave this eight times more
  // permissive than the transport for the index, whose own bound is 1 MiB.
  const oversizeIndex = new Uint8Array(1024 * 1024 + 1);
  const { result: indexResult } = await withUpstream(
    () => new Response(oversizeIndex, { status: 200 }),
    () => worker.fetch(get("/soundset-catalog/catalog/index.json"), creatorEnv()),
  );
  assert.equal(indexResult.status, 502);
  // The same body is inside the object bound.
  const { result: objectResult } = await withUpstream(
    () => new Response(oversizeIndex, { status: 200 }),
    () => worker.fetch(get(`/soundset-catalog/object/blob/${DIGEST}`), creatorEnv()),
  );
  assert.equal(objectResult.status, 200);

  // A declared length past the bound is refused before the body is read at all.
  let bodyWasRead = false;
  const { result: declared } = await withUpstream(
    () => new Response(new Uint8Array(4), {
      status: 200,
      headers: { "content-length": String(9 * 1024 * 1024) },
    }),
    () => worker.fetch(get(`/soundset-catalog/object/blob/${DIGEST}`), creatorEnv()),
  );
  assert.equal(declared.status, 502);
  assert.equal(bodyWasRead, false);

  // And an undeclared body that runs past the bound is abandoned mid-stream
  // rather than buffered whole: the reader is cancelled and never drained.
  let cancelled = false;
  let chunksServed = 0;
  const endless = new ReadableStream({
    pull(controller) {
      chunksServed += 1;
      controller.enqueue(new Uint8Array(1024 * 1024));
    },
    cancel() {
      cancelled = true;
    },
  });
  const { result: streamed } = await withUpstream(
    () => new Response(endless, { status: 200 }),
    () => worker.fetch(get(`/soundset-catalog/object/blob/${DIGEST}`), creatorEnv()),
  );
  assert.equal(streamed.status, 502);
  assert.equal(cancelled, true);
  assert.ok(chunksServed <= 12, `read ${chunksServed} MiB before stopping`);
});

test("the upstream's own content type never reaches the page", async () => {
  const { result } = await withUpstream(
    () => new Response("{}", {
      status: 200,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    }),
    () => worker.fetch(get("/soundset-catalog/catalog/index.json"), creatorEnv()),
  );
  assert.equal(result.headers.get("content-type"), "application/json");
  assert.equal(result.headers.get("x-content-type-options"), "nosniff");
});

test("a Catalog path is never served out of the asset store", async () => {
  const seen = [];
  await withUpstream(
    () => new Response("{}", { status: 200 }),
    () => worker.fetch(
      get("/soundset-catalog/catalog/index.json"),
      { ASSETS: assetsBinding(seen), CATALOG_UPSTREAM: UPSTREAM },
    ),
  );
  assert.deepEqual(seen, []);
});
