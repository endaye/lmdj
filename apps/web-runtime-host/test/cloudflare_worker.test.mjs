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

import worker from "../deploy/cloudflare_worker.mjs";

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
  const rejected = [
    "http://catalog.example.test/",
    "ftp://catalog.example.test/",
    "not-a-url",
    "",
    "https://catalog.example.test/?query=1",
    "https://catalog.example.test/#fragment",
    "https://catalog.example.test//double/",
    // Credentials are refused, not silently dropped by `URL.origin`.
    "https://user:pass@catalog.example.test/",
    "https://user@catalog.example.test/",
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
