// The browser side of the Web Host's Sound Set `CatalogTransport`.
//
// S11-D6 gives a Catalog adapter exactly one power: resolve an immutable
// object addressed by `{object_kind, sha256}`. Core ships no network code, so
// this module is the Host's network adapter for that one read, and the bytes
// it resolves cross the bridge to Core, which keeps every Contract, hash and
// eligibility decision. A Sound Set is a logical package, not an archive:
// nothing here unpacks, lists, searches or follows a redirect, and there is no
// third object kind to be redirected to.
//
// The Catalog index is the second, separate read. It is the Host's own
// endpoint knowledge, carries no content address, and never travels on the
// object surface below.

export const CATALOG_OBJECT_KINDS = Object.freeze(["manifest", "blob"]);

/**
 * The Host's Catalog adapter as Core's callers see it: one index read and one
 * object read addressed by `{object_kind, sha256}`.
 *
 * @typedef {{
 *   readIndex: () => Promise<Uint8Array>,
 *   readObject: (
 *     request: {object_kind: string, sha256: string},
 *   ) => Promise<Uint8Array>,
 * }} CatalogClient
 */

// Two paths, and no way to spell a third. Both are built from values this
// module has already validated, never from caller text.
const CATALOG_INDEX_PATH = "catalog/index.json";
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

// A Catalog object larger than this is not a Sound Set object. Core's own
// `resource_limits.maximum_soundset_*` keys still decide what may be
// published; this is only the bound on what the Host will hold in memory
// before Core has seen it.
const MAX_CATALOG_OBJECT_BYTES = 8 * 1024 * 1024;
const MAX_CATALOG_INDEX_BYTES = 1024 * 1024;

export class CatalogTransportError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "CatalogTransportError";
    this.code = code;
    this.details = Object.freeze({...details});
  }
}

function refusal(message, details = {}) {
  // A shape this transport never declared is a Host protocol fault, not an
  // unreachable Catalog: it must never be retried and never be reported as a
  // Catalog outage.
  return new CatalogTransportError("HOST_PROTOCOL_MISMATCH", message, details);
}

function unavailable(message, details = {}) {
  return new CatalogTransportError("IO_ERROR", message, {
    reason: "catalog_unavailable",
    ...details,
  });
}

function isPlainObject(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function hasExactKeys(value, expected) {
  if (!isPlainObject(value)) {
    return false;
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return (
    actual.length === wanted.length &&
    actual.every((key, index) => key === wanted[index])
  );
}

// A Catalog endpoint is an absolute `http`/`https` origin plus an optional
// path prefix, normalised to end in a single `/`. A relative endpoint, another
// scheme, or an endpoint carrying a query or fragment is refused here rather
// than being resolved against whatever page happens to be loaded.
export function normalizeCatalogEndpoint(endpoint) {
  if (typeof endpoint !== "string" || endpoint.length === 0) {
    throw refusal("Catalog endpoint is required");
  }
  let parsed;
  try {
    parsed = new URL(endpoint);
  } catch {
    throw refusal("Catalog endpoint is not an absolute URL");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw refusal("Catalog endpoint is not an http or https URL");
  }
  if (parsed.search !== "" || parsed.hash !== "") {
    throw refusal("Catalog endpoint carries a query or fragment");
  }
  const path = parsed.pathname.endsWith("/")
    ? parsed.pathname
    : `${parsed.pathname}/`;
  // A path prefix that repeats `/` would put a second empty segment on the
  // wire, which is a target this transport never declared.
  if (path.includes("//")) {
    throw refusal("Catalog endpoint path is not normalised");
  }
  return `${parsed.origin}${path}`;
}

// The complete address of one Catalog object, and the only thing this
// transport accepts. Extra keys, a missing key, a kind outside the two locked
// ones, and a digest that is not 64 lowercase hex characters are all refused
// before a request is made.
function catalogObjectPath(request) {
  if (!hasExactKeys(request, ["object_kind", "sha256"])) {
    throw refusal(
      "a Catalog object is addressed by exactly {object_kind, sha256}",
    );
  }
  const {object_kind: objectKind, sha256} = request;
  if (
    typeof objectKind !== "string" || !CATALOG_OBJECT_KINDS.includes(objectKind)
  ) {
    throw refusal("Catalog object_kind must be manifest or blob", {
      object_kind: String(objectKind),
    });
  }
  if (typeof sha256 !== "string" || !SHA256_PATTERN.test(sha256)) {
    throw refusal("Catalog sha256 must be 64 lowercase hex characters");
  }
  return `object/${objectKind}/${sha256}`;
}

async function readBoundedBody(response, maximumBytes) {
  const declared = response.headers?.get?.("content-length");
  if (declared !== null && declared !== undefined && declared !== "") {
    const length = Number(declared);
    if (!Number.isSafeInteger(length) || length < 0 || length > maximumBytes) {
      throw unavailable("Catalog object is larger than the Host bound");
    }
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > maximumBytes) {
    throw unavailable("Catalog object is larger than the Host bound");
  }
  return new Uint8Array(buffer);
}

async function readTarget(fetchImpl, target, maximumBytes) {
  let response;
  try {
    // `manual` keeps a redirect from silently becoming a second request to
    // some other target: this transport resolves the address it was given or
    // nothing at all.
    response = await fetchImpl(target, {
      method: "GET",
      redirect: "manual",
      cache: "no-store",
    });
  } catch (error) {
    throw unavailable("Catalog endpoint could not be reached", {
      cause: String(error?.message ?? error),
    });
  }
  if (response?.type === "opaqueredirect" || response?.redirected === true) {
    throw unavailable("Catalog endpoint answered with a redirect");
  }
  if (typeof response?.status !== "number" || response.status !== 200) {
    throw unavailable("Catalog endpoint did not resolve the address", {
      status: Number(response?.status ?? 0),
    });
  }
  return readBoundedBody(response, maximumBytes);
}

// The Host's network Catalog adapter. `readObject` is the whole of the
// S11-D6 transport surface; `readIndex` is the Host's own endpoint read.
export function createFetchCatalogClient({
  endpoint = "",
  fetch: fetchImpl = /** @type {typeof globalThis.fetch | null} */ (null),
  maximumObjectBytes = MAX_CATALOG_OBJECT_BYTES,
  maximumIndexBytes = MAX_CATALOG_INDEX_BYTES,
} = {}) {
  const base = normalizeCatalogEndpoint(endpoint);
  if (typeof fetchImpl !== "function") {
    throw refusal("a Catalog fetch implementation is required");
  }
  return Object.freeze({
    endpoint: base,
    readIndex() {
      return readTarget(fetchImpl, `${base}${CATALOG_INDEX_PATH}`, maximumIndexBytes);
    },
    readObject(request) {
      // Thrown, not rejected: a request that is not `{object_kind, sha256}` is
      // a caller fault that no retry can repair.
      const path = catalogObjectPath(request);
      return readTarget(fetchImpl, `${base}${path}`, maximumObjectBytes);
    },
  });
}
