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
// One thing the canonical-form rule buys beyond request-derived bytes, worth
// claiming because it is easy to miss: `CATALOG_UPSTREAM` is now pinned to its
// own canonical WHATWG serialization, so the configured base cannot be a
// spelling the parser silently rewrites into a different host. That closes
// operator-configuration surprise, not just caller influence.
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
  // On THIS side that is by construction: there is a WHATWG parser here, so
  // the rule is one comparison and cannot fall behind the parser. The proof
  // server has no such parser and cannot mirror it that way -- it decides the
  // same question with a closed grammar, and the two agree only as far as that
  // grammar is faithful. `CatalogUpstreamParityTest` drives both over one list
  // for exactly that reason; enumerating WHATWG's behaviours instead was tried
  // here first and two review passes kept finding spellings the enumeration
  // had missed, which is what a list of parser behaviours always does.
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
  // One strict token or nothing. `Number()` reads `0x10` as 16 and ` 2 ` as 2,
  // and `headers.get` joins duplicate headers with ", " -- so a lenient parse
  // disagreed with the proof server's `int()`, which instead honours PEP 515
  // underscores and takes only the first duplicate. Neither bound was ever
  // unenforced, but the two answered differently, which is the divergence the
  // check itself was added to close.
  const declared = upstream.headers.get("content-length");
  if (declared !== null) {
    if (!/^[0-9]+$/.test(declared)) return new Response(null, { status: 502 });
    if (Number(declared) > target.maximumBytes) {
      return new Response(null, { status: 502 });
    }
  }
  let body;
  try {
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
