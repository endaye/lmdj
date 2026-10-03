export type OfflineShellPhase = "preparing" | "ready" | "waiting" | "unavailable";
async function digest(bytes: ArrayBuffer, crypto: Crypto): Promise<string> {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map(value => value.toString(16).padStart(2, "0")).join("");
}
function manifestIdentity(index: string): string {
  const match = /<meta name="lmdj-host-manifest-sha256" content="([0-9a-f]{64})">/.exec(index);
  if (match === null) throw new Error("offline index has no manifest identity");
  return match[1]!;
}
function workerUrl(value: unknown, base: string): string {
  if (typeof value !== "object" || value === null) throw new Error("offline manifest invalid");
  const manifest = value as {host_id?: unknown; assets?: unknown};
  if (manifest.host_id !== "creator-web" || !Array.isArray(manifest.assets)) throw new Error("offline manifest invalid");
  const workers = manifest.assets.filter(asset => asset?.role === "offline_worker");
  if (workers.length !== 1) throw new Error("offline worker inventory invalid");
  const asset = workers[0] as {path: unknown; sha256: unknown};
  if (typeof asset.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(asset.sha256) ||
      asset.path !== `assets/offline-worker.${asset.sha256}.js`) throw new Error("offline worker path invalid");
  return new URL(asset.path, base).href;
}
export async function registerOfflineShell(
  document: Document, navigator: Navigator, crypto: Crypto,
  fetch: typeof globalThis.fetch,
  observe: (phase: OfflineShellPhase) => void,
): Promise<void> {
  if (!("serviceWorker" in navigator)) {observe("unavailable"); return;}
  observe("preparing");
  const base = new URL("./", document.baseURI).href;
  const manifestPath = new URL("host-manifest.json", base).href;
  async function manifest(expected: string, probe = false): Promise<unknown> {
    const response = await fetch(manifestPath, {cache: "no-store", ...(probe ? {headers: {"X-LMDJ-Offline-Probe": "1"}} : {})});
    if (!response.ok) throw new Error("offline manifest unavailable");
    const bytes = await response.arrayBuffer();
    if (await digest(bytes, crypto) !== expected) throw new Error("offline manifest identity mismatch");
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  try {
    const expected = document.querySelector('meta[name="lmdj-host-manifest-sha256"]')?.getAttribute("content");
    if (expected === null || expected === undefined || !/^[0-9a-f]{64}$/.test(expected)) throw new Error("offline manifest identity unavailable");
    const currentUrl = workerUrl(await manifest(expected), base);
    let registration = await navigator.serviceWorker.register(currentUrl, {scope: base, type: "module", updateViaCache: "none"});
    const report = () => {
      if (registration.waiting) observe("waiting");
      else if (registration.active?.scriptURL === currentUrl) observe("ready");
    };
    const watchInstalling = () => {
      const installing = registration.installing;
      installing?.addEventListener("statechange", () => {
        if (installing.state === "redundant" && registration.active === null) observe("unavailable");
        else report();
      });
      report();
    };
    registration.addEventListener("updatefound", watchInstalling);
    watchInstalling();
    void navigator.serviceWorker.ready.then(report);
    // A cache-first active shell stays coherent. Probe the network only for a
    // future worker; registering it cannot replace an active performing page.
    try {
      const response = await fetch(new URL("index.html", base).href,
        {cache: "no-store", headers: {"X-LMDJ-Offline-Probe": "1"}});
      if (response.ok) {
        const latestUrl = workerUrl(await manifest(manifestIdentity(await response.text()), true), base);
        if (latestUrl !== currentUrl) {
          registration = await navigator.serviceWorker.register(latestUrl, {scope: base, type: "module", updateViaCache: "none"});
          registration.addEventListener("updatefound", watchInstalling);
          watchInstalling();
        }
      }
    } catch { /* A network probe cannot invalidate a complete offline build. */ }
  } catch {observe("unavailable");}
}
