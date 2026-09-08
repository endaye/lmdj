// Preserve the Host contract: both / and /index.html serve identical bytes.
// Other paths go directly to static assets without invoking this Worker.
//
// #901, the S11-D6 Catalog proxy. The Creator is served `connect-src 'self'`,
// and that directive is not protecting its two same-origin fetches -- it is the
// exfiltration barrier around the Projects and captured audio the Creator holds
// in OPFS. Naming a Catalog origin in `connect-src` would hand every line of
// code running in the page, including a compromised dependency, somewhere to
// send that. So the page is never given a foreign origin at all: it reaches its
// Catalog through a same-origin prefix, and the barrier stands untouched.
//
// Two properties keep this a forwarder rather than a relay. Both are
// structural: they hold because of how the target is built, not because of a
// check that a later edit could drop.
//
//   1. THE DESTINATION IS NOT IN THE REQUEST. The page sends a path. The target
//      is composed from `CATALOG_UPSTREAM` plus tokens this Worker re-derives:
//      a string literal, an element read back out of a frozen two-element
//      array, and a digest re-matched against `[0-9a-f]{64}`. The request's own
//      text is never concatenated into the target, so no header, query or path
//      segment can move it to another host. A relay takes its destination from
//      its caller; this cannot be made to.
//
//   2. THE PATH GRAMMAR IS CLOSED. `soundset_catalog.mjs` can only spell
//      `catalog/index.json` and `object/(manifest|blob)/<64 hex>` --
//      `catalogObjectPath` throws before a request is built for anything else
//      -- so those two shapes are the entire production surface, and the entire
//      surface this admits.
//
// What that leaves a compromised bundle is the choice of *which* object is
// fetched from the one configured Catalog: 64 lowercase hex characters per GET
// to a fixed host, readable only by whoever runs that Catalog. That is the
// residual channel, and it is the whole of it.
//
// A deployment that offers no Catalog sets no `CATALOG_UPSTREAM`, and every
// prefixed path answers 404 -- S11-D6's "browses only the Sets its Workspace
// Set Store already holds". The diagnostic Lab has no Sound Set surface, so it
// sets neither the variable nor the route: that gate is closed twice, by
// absence at both ends, rather than by a condition someone could delete.
const CATALOG_PREFIX = "/soundset-catalog/";
const CATALOG_INDEX_SUFFIX = "catalog/index.json";
const OBJECT_SUFFIX = /^object\/([a-z]+)\/([0-9a-f]{64})$/;
const OBJECT_KINDS = Object.freeze(["manifest", "blob"]);
// The Host's bound on what it will hold before Core has seen it, matching
// `soundset_catalog.mjs`. Core's `resource_limits.maximum_soundset_*` keys
// still decide what may be published.
const MAXIMUM_OBJECT_BYTES = 8 * 1024 * 1024;
const OBJECT_CONTENT_TYPES = Object.freeze({
  manifest: "application/json",
  blob: "application/octet-stream",
});

// A misconfigured binding fails closed rather than becoming a plaintext or
// parameterised forwarder. Production Catalogs are https; the proof server has
// its own loopback rule and does not share this code.
function upstreamBase(env) {
  const configured = env?.CATALOG_UPSTREAM;
  if (typeof configured !== "string" || configured.length === 0) return null;
  let parsed;
  try {
    parsed = new URL(configured);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:") return null;
  if (parsed.search !== "" || parsed.hash !== "") return null;
  const path = parsed.pathname.endsWith("/")
    ? parsed.pathname
    : `${parsed.pathname}/`;
  if (path.includes("//")) return null;
  return `${parsed.origin}${path}`;
}

// Returns the target composed from `base` and re-derived tokens, or null for
// every shape the transport cannot spell.
function catalogTarget(base, suffix) {
  if (suffix === CATALOG_INDEX_SUFFIX) {
    return {
      url: `${base}${CATALOG_INDEX_SUFFIX}`,
      contentType: "application/json",
      immutable: false,
    };
  }
  const match = OBJECT_SUFFIX.exec(suffix);
  if (match === null) return null;
  const kindIndex = OBJECT_KINDS.indexOf(match[1]);
  if (kindIndex < 0) return null;
  // `kind` is read back out of the frozen array rather than taken from the
  // match, so the host and every path segment but the digest are this file's
  // own literals.
  const kind = OBJECT_KINDS[kindIndex];
  const digest = match[2];
  return {
    url: `${base}object/${kind}/${digest}`,
    contentType: OBJECT_CONTENT_TYPES[kind],
    immutable: true,
  };
}

async function proxyCatalog(request, env, url) {
  // The transport issues one shape: GET, no query, no fragment.
  if (request.method !== "GET") return new Response(null, { status: 405 });
  if (url.search !== "") return new Response(null, { status: 404 });
  const base = upstreamBase(env);
  if (base === null) return new Response(null, { status: 404 });
  const target = catalogTarget(base, url.pathname.slice(CATALOG_PREFIX.length));
  if (target === null) return new Response(null, { status: 404 });
  let upstream;
  try {
    // A fresh request: none of the page's headers, cookies or credentials
    // travel upstream, and `manual` stops a redirecting Catalog from turning
    // one forward into a fetch of some other target.
    upstream = await fetch(target.url, {
      method: "GET",
      redirect: "manual",
      headers: { Accept: target.contentType },
    });
  } catch {
    return new Response(null, { status: 502 });
  }
  // A missing object stays a missing object; everything else the Catalog does
  // is one failure the transport reports as `catalog_unavailable`.
  if (upstream.status === 404) return new Response(null, { status: 404 });
  if (upstream.status !== 200 || upstream.redirected) {
    return new Response(null, { status: 502 });
  }
  let body;
  try {
    body = await upstream.arrayBuffer();
  } catch {
    return new Response(null, { status: 502 });
  }
  if (body.byteLength > MAXIMUM_OBJECT_BYTES) {
    return new Response(null, { status: 502 });
  }
  return new Response(body, {
    status: 200,
    headers: {
      // This Worker's content type for the shape it resolved, never the
      // upstream's: a Catalog does not get to decide how the page reads bytes.
      "Content-Type": target.contentType,
      "Cache-Control": target.immutable
        ? "public, max-age=31536000, immutable"
        : "no-store",
      "Cross-Origin-Resource-Policy": "same-origin",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export default {
  fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith(CATALOG_PREFIX)) {
      return proxyCatalog(request, env, url);
    }
    if (url.pathname === "/") url.pathname = "/index.html";
    return env.ASSETS.fetch(new Request(url, request));
  },
};
