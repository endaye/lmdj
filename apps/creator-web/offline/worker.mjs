const READY_PREFIX = "lmdj.creator.offline.ready.";
const STAGE_PREFIX = "lmdj.creator.offline.stage.";
const encoder = new TextEncoder();
async function sha256(crypto, bytes) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map(value => value.toString(16).padStart(2, "0")).join("");
}
function security(response) {
  return response.headers.get("Cross-Origin-Opener-Policy") === "same-origin" &&
    response.headers.get("Cross-Origin-Embedder-Policy") === "require-corp" &&
    response.headers.get("Cross-Origin-Resource-Policy") === "same-origin";
}
export function createOfflineShell({build, caches, fetch, crypto, scope, scriptUrl}) {
  const root = new URL("index.html", scope).href;
  const manifestUrl = new URL("host-manifest.json", scope).href;
  const marker = new URL(".lmdj-offline-ready", scope).href;
  const assetUrls = new Set(build.assets.map(asset => new URL(asset.path, scope).href));
  if (scriptUrl) assetUrls.add(scriptUrl);
  const name = sha256(crypto, encoder.encode(JSON.stringify(build))).then(hash => READY_PREFIX + hash);
  async function downloaded(url) {
    const response = await fetch(url, {cache: "reload", credentials: "same-origin"});
    if (!response.ok || response.status !== 200 || !security(response)) throw new Error("offline shell response refused");
    return response;
  }
  async function install() {
    const readyName = await name;
    const ready = await caches.open(readyName);
    if (await ready.match(marker)) return readyName;
    const stagingName = STAGE_PREFIX + crypto.randomUUID();
    const staging = await caches.open(stagingName);
    try {
      const indexResponse = await downloaded(root);
      const index = await indexResponse.clone().text();
      const match = /<meta name="lmdj-host-manifest-sha256" content="([0-9a-f]{64})">/.exec(index);
      if (match === null) throw new Error("offline shell has no manifest identity");
      const manifestResponse = await downloaded(manifestUrl);
      const manifestBytes = await manifestResponse.clone().arrayBuffer();
      if (await sha256(crypto, manifestBytes) !== match[1]) throw new Error("offline manifest hash mismatch");
      const manifest = JSON.parse(new TextDecoder().decode(manifestBytes));
      if (manifest.host_id !== "creator-web" || manifest.product_build !== build.product_build ||
          manifest.host_version !== build.host_version || !Array.isArray(manifest.assets) ||
          JSON.stringify(manifest.assets.filter(asset => asset.role !== "offline_worker")) !== JSON.stringify(build.assets) ||
          manifest.assets.filter(asset => asset.role === "offline_worker").length !== 1) {
        throw new Error("offline shell build graph mismatch");
      }
      for (const role of ["host_main", "host_style"]) {
        const asset = manifest.assets.find(asset => asset.role === role);
        if (!index.includes(`./${asset.path}`)) throw new Error("offline index binds another build");
      }
      const paths = new Set();
      for (const asset of manifest.assets) {
        if (typeof asset.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(asset.sha256) ||
            !/^assets\/[a-z0-9-]+\.[0-9a-f]{64}\.(js|css|wasm)$/.test(asset.path) ||
            !asset.path.includes(`.${asset.sha256}.`) || paths.has(asset.path) ||
            !Number.isSafeInteger(asset.bytes) || asset.bytes <= 0) {
          throw new Error("offline asset descriptor refused");
        }
        paths.add(asset.path);
        const url = new URL(asset.path, scope).href;
        const response = await downloaded(url);
        const bytes = await response.clone().arrayBuffer();
        if (bytes.byteLength !== asset.bytes || await sha256(crypto, bytes) !== asset.sha256) {
          throw new Error("offline asset bytes mismatch");
        }
        await staging.put(url, response);
      }
      await staging.put(root, indexResponse);
      await staging.put(manifestUrl, manifestResponse);
      // The marker is published last: readers never serve a partial graph.
      for (const request of await staging.keys()) await ready.put(request, await staging.match(request));
      await ready.put(marker, new Response("ready"));
      return readyName;
    } catch (error) {
      if (!(await ready.match(marker))) await caches.delete(readyName);
      throw error;
    } finally {
      await caches.delete(stagingName);
    }
  }
  async function activate() {
    const keep = await name;
    const ready = await caches.open(keep);
    if (!(await ready.match(marker))) throw new Error("offline activation requires a complete cache");
    for (const key of await caches.keys()) {
      if (key.startsWith(READY_PREFIX) && key !== keep) await caches.delete(key);
    }
  }
  async function respond(request) {
    if (request.method !== "GET") return fetch(request);
    const url = new URL(request.url);
    const scopeUrl = new URL(scope);
    if (url.origin !== scopeUrl.origin || !url.pathname.startsWith(scopeUrl.pathname)) return fetch(request);
    if (request.headers.get("X-LMDJ-Offline-Probe") === "1") {
      return fetch(request);
    }
    const ready = await caches.open(await name);
    if (!(await ready.match(marker))) return fetch(request);
    const shellPath = url.pathname === scopeUrl.pathname || url.pathname === new URL(root).pathname;
    if (!shellPath && url.href !== manifestUrl && !assetUrls.has(url.href)) return fetch(request);
    const cached = await ready.match(shellPath ? root : url.href);
    return cached ?? fetch(request);
  }
  return Object.freeze({install, activate, respond});
}
if (typeof self !== "undefined" && self.registration && self.LMDJ_CREATOR_OFFLINE_GRAPH) {
  const shell = createOfflineShell({build: self.LMDJ_CREATOR_OFFLINE_GRAPH, caches: self.caches,
    fetch: self.fetch.bind(self), crypto: self.crypto, scope: self.registration.scope, scriptUrl: self.location.href});
  self.addEventListener("install", event => event.waitUntil(shell.install()));
  self.addEventListener("activate", event => event.waitUntil(shell.activate()));
  self.addEventListener("fetch", event => event.respondWith(shell.respond(event.request)));
  // Browser waiting/activation semantics preserve active documents and audio.
}
