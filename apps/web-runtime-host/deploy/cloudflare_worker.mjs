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
// Two properties keep this a forwarder rather than a relay. They are not the
// same kind of property, and an adversarial review of this file established
// that the difference matters:
//
//   1. THE DESTINATION IS NOT IN THE REQUEST -- and this one is structural. The
//      page sends a path. The target is composed from `CATALOG_UPSTREAM` plus a
//      string literal, an element read back out of a frozen two-element array,
//      and a digest re-matched against `[0-9a-f]{64}`. That alphabet contains
//      no `/ \ . : @ % ? #` and no control character, so the only
//      request-derived bytes in the target cannot terminate a path segment,
//      introduce an authority, change the scheme or port, or add a query. A
//      relay takes its destination from its caller; this cannot be made to, and
//      no path, query, header or encoding tried against it could.
//
//   2. THE PATH GRAMMAR IS A CHECK, not a composition, and calling it
//      structural would be wrong. It is an equality, a frozen-kind `indexOf`
//      and a regex, kept deliberately equal to the two shapes
//      `soundset_catalog.mjs` can spell -- `catalog/index.json` and
//      `object/(manifest|blob)/<64 hex>`, which `catalogObjectPath` throws
//      before exceeding. It is tempting to borrow that throw and call the
//      grammar closed by construction, but the threat this whole design is
//      built against is a compromised dependency running in the page, and such
//      code never calls the transport: it calls `fetch("/soundset-catalog/…")`
//      directly, which `connect-src 'self'` permits. Under that threat model
//      `catalogObjectPath` contributes nothing and the check below is the only
//      thing in the way. Widening it widens the residual channel.
//
// THE RESIDUAL CHANNEL, stated without flattery, and it runs BOTH WAYS.
//
// Outbound: a compromised bundle can choose which of three admitted targets is
// fetched from the one configured Catalog, and for two of them a 64-hex digest
// -- 256 bits plus roughly 1.6 -- repeatable at whatever rate the page likes,
// since nothing here throttles and the transport asks for `no-store`. It is
// readable by whoever operates that Catalog and by anyone terminating TLS in
// front of it.
//
// Inbound, which an earlier version of this comment missed: the Catalog's
// answer comes back into the page. That is 404-versus-200 per request plus up
// to the shape's bound of bytes of the Catalog's choosing, at a content type
// this Worker sets. So under this threat model `connect-src 'self'` is a
// command-and-control barrier as well as an exfiltration barrier, and the
// forward punches through it in both directions for one fixed host. Anyone who
// can place content in the configured Catalog can feed a compromised bundle
// attacker-chosen bytes same-origin.
//
// What is still true, and is the whole reason this is narrower than naming a
// Catalog in `connect-src`: the far end is one host the deployment chose, not
// an origin the attacker chose, and the request grammar reaching it is the
// narrow check below rather than anything a caller can widen.
//
// One thing the canonical-form rule retains beyond request-derived bytes,
// worth claiming because it is easy to miss: after explicit character
// admission, `CATALOG_UPSTREAM` is pinned to its own canonical WHATWG
// serialization, so the configured base cannot be a spelling the parser
// silently rewrites into a different host. That closes operator-configuration
// surprise, not just caller influence; WHATWG serialization alone is not the
// admission policy.
//
// Whether the Workers runtime attaches the viewer's IP to a subrequest is NOT
// established here and must not be assumed either way; if it does, that is a
// further request-derived component reaching the Catalog.
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
// The Host's bounds on what it will hold before Core has seen it, one per
// shape, matching `soundset_catalog.mjs`'s `MAX_CATALOG_OBJECT_BYTES` and
// `MAX_CATALOG_INDEX_BYTES`. Core's `resource_limits.maximum_soundset_*` keys
// still decide what may be published. One bound for both shapes would leave
// this eight times more permissive than its only client for the index.
const MAXIMUM_OBJECT_BYTES = 8 * 1024 * 1024;
const MAXIMUM_INDEX_BYTES = 1024 * 1024;
const OBJECT_CONTENT_TYPES = Object.freeze({
  manifest: "application/json",
  blob: "application/octet-stream",
});

// Character admission mirrors CANONICAL_UPSTREAM in serve_distribution.py,
// with production restricted to HTTPS. URL serialization alone is insufficient:
// Node 22 preserves a literal path caret while Node 26 encodes it. Keep this
// grammar local so the standalone Worker needs no runtime imports. The final
// negative lookahead is an absolute end assertion (unlike `$` before a newline).
// This is admission only; retain the parsed canonical URL defenses below.
const CANONICAL_UPSTREAM = /^https:\/\/(\[[^\[\]/?#%]+\]|[a-z0-9][a-z0-9._\-]*)(?::[1-9][0-9]{0,4})?((?:\/[A-Za-z0-9!$%&'()*+,\-.:;=@\[\]_|~]*)*\/)(?![\s\S])/;

// A misconfigured binding fails closed rather than becoming a plaintext or
// parameterised forwarder. Production Catalogs are https; the proof server has
// its own loopback rule and does not share this code.
function upstreamBase(env) {
  const configured = env?.CATALOG_UPSTREAM;
  if (typeof configured !== "string" || !CANONICAL_UPSTREAM.test(configured)) return null;
  let parsed;
  try {
    parsed = new URL(configured);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:") return null;
  if (parsed.search !== "" || parsed.hash !== "") return null;
  // Refused rather than dropped. `URL.origin` discards userinfo silently, so
  // an operator who believed they had configured credentials would get
  // unauthenticated forwards and no signal; the proof server would keep them
  // and behave unlike this. Neither half of that is worth having.
  if (parsed.username !== "" || parsed.password !== "") return null;
  // WHATWG accepts port 0 and `origin` keeps it, so the canonical-form rule
  // below would admit it. It is not a port anything listens on, and the proof
  // server's grammar refuses it, so refusing here keeps the two in step.
  if (parsed.port === "0") return null;
  const path = parsed.pathname.endsWith("/")
    ? parsed.pathname
    : `${parsed.pathname}/`;
  if (path.includes("//")) return null;
  const base = `${parsed.origin}${path}`;
  // The configured value must already be the base this composes, or it is
  // refused. Parsing normalises -- it resolves dot segments, maps `\` to `/`,
  // lowercases and punycodes the host, rewrites numeric host spellings, drops
  // a default port, trims whitespace, percent-encodes a dozen path bytes, and
  // terminates the authority at a backslash so `https://a\@b/` becomes host
  // `a`. Every one of those is a way for the deployment to forward somewhere
  // the operator did not write.
  //
  // Character admission above fixes the common allowed alphabet; this
  // comparison still refuses host, port and dot-segment rewrites within it.
  // The Python proof server checks those canonical forms explicitly.
  // CatalogUpstreamParityTest exercises both implementations on the same
  // accepted/refused and generated corpus under Node 22 and Node 26.
  if (configured !== base) return null;
  return base;
}

// Returns the target composed from `base` and re-derived tokens, or null for
// every shape the transport cannot spell.
function catalogTarget(base, suffix) {
  if (suffix === CATALOG_INDEX_SUFFIX) {
    return {
      url: `${base}${CATALOG_INDEX_SUFFIX}`,
      contentType: "application/json",
      immutable: false,
      maximumBytes: MAXIMUM_INDEX_BYTES,
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
    maximumBytes: MAXIMUM_OBJECT_BYTES,
  };
}

// Reads at most `maximumBytes`, or returns null the moment the upstream goes
// past it. The reader is cancelled so a Catalog cannot hold the subrequest open
// by continuing to send.
async function readBounded(response, maximumBytes) {
  if (response.body === null) return new Uint8Array(0);
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maximumBytes) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock?.();
  }
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
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
  // Bounded before it is held, not after. `arrayBuffer()` would materialise
  // whatever a Catalog chose to send and only then measure it, so a hostile or
  // compromised upstream -- which is exactly a third party, not this Host's
  // trust domain -- could exhaust the isolate before the check ran. The
  // declared length is refused first, then the stream is read with a running
  // total and abandoned the moment it exceeds the bound.
  // One strict token or nothing, because `Number()` reads `0x10` as 16 while
  // the proof server's `int()` reads `5_0` as 50 under PEP 515. That much this
  // check does close.
  //
  // What it does NOT close, and what an earlier version of this comment
  // wrongly claimed it did, is the two cases where the two sides never see the
  // same string at all. Measured, with every spelling quoted rather than laid
  // out in columns -- the padded case is about trailing spaces, and a
  // space-aligned table cannot show trailing spaces at all:
  //
  //   * a single header whose value is `  2  ` (padded both sides):
  //       this Worker sees `2`     the proof server sees `2  `
  //   * two `Content-Length: 2` headers on one response:
  //       this Worker sees `2, 2`  the proof server sees `2`
  //
  // Fetch's `Headers` normalises each value and joins repeats with ", " before
  // `get` is ever called, so this side cannot be lenient about padding -- the
  // padding is gone by then -- and cannot see only the first of a repeat.
  // `email.message.get` does neither. A rule applied to two different strings
  // is not one rule, so the proof server reproduces this view rather than
  // matching this rule; see `read_catalog_object`. Both bounds were always
  // authoritative on both sides -- what differed was the answer, not the
  // enforcement.
  let body;
  try {
    // Inside the guard with the read: a `headers` accessor that throws is not
    // something the runtime produces, but it costs nothing to not depend on
    // that.
    const declared = upstream.headers.get("content-length");
    if (declared !== null) {
      if (!/^[0-9]+$/.test(declared)) return new Response(null, { status: 502 });
      if (Number(declared) > target.maximumBytes) {
        return new Response(null, { status: 502 });
      }
    }
    body = await readBounded(upstream, target.maximumBytes);
  } catch {
    return new Response(null, { status: 502 });
  }
  if (body === null) return new Response(null, { status: 502 });
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
