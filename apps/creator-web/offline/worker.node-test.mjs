import {test} from "node:test";
import assert from "node:assert/strict";
import {webcrypto, createHash} from "node:crypto";
import {readFileSync} from "node:fs";
import {createOfflineShell} from "./worker.mjs";
const scope = "https://creator.test/";
const digest = data => createHash("sha256").update(data).digest("hex");
const headers = {"Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp", "Cross-Origin-Resource-Policy": "same-origin"};
function cachesFixture() {
  const stores = new Map();
  return {stores, async keys() {return [...stores.keys()];}, async delete(key) {return stores.delete(key);},
    async open(key) {
      if (!stores.has(key)) stores.set(key, new Map());
      const store = stores.get(key);
      const url = request => typeof request === "string" ? request : request.url;
      return {async put(request, response) {store.set(url(request), response.clone());},
        async match(request) {return store.get(url(request))?.clone();},
        async keys() {return [...store.keys()].map(value => new Request(value));}};
    }};
}
function fixture(label = "first", caches = cachesFixture()) {
  const payloads = new Map();
  const roles = ["host_main", "runtime_script", "runtime_wasm", "host_style", "capture_worklet", "perform_master_tap_worklet", "host_favicon"];
  const assets = roles.map((role, index) => {
    const bytes = role === "host_favicon" ? readFileSync(new URL("../public/favicon.svg", import.meta.url)) : Buffer.from(`${label}-${role}`);
    const hash = digest(bytes);
    const path = `assets/asset-${index}.${hash}.${role === "runtime_wasm" ? "wasm" : role === "host_style" ? "css" : role === "host_favicon" ? "svg" : "js"}`;
    payloads.set(scope + path, bytes);
    return {bytes: bytes.length, path, role, sha256: hash};
  });
  const worker = Buffer.from("worker-" + label);
  const workerHash = digest(worker);
  const workerAsset = {bytes: worker.length, path: `assets/offline-worker.${workerHash}.js`, role: "offline_worker", sha256: workerHash};
  payloads.set(scope + workerAsset.path, worker);
  const build = {product_build: "test-" + label, host_version: "6.0.0", assets};
  const manifest = Buffer.from(JSON.stringify({host_id: "creator-web", product_build: build.product_build, host_version: build.host_version, assets: [...assets, workerAsset]}));
  payloads.set(scope + "host-manifest.json", manifest);
  payloads.set(scope + "index.html", Buffer.from(`<meta name="lmdj-host-manifest-sha256" content="${digest(manifest)}"><script src="./${assets[0].path}"></script><link href="./${assets[3].path}"><link rel="icon" href="./${assets[6].path}">${label}`));
  const calls = [];
  let offline = false;
  const fetch = async request => {
    const url = typeof request === "string" ? request : request.url;
    calls.push(url);
    if (offline) throw new Error("offline");
    const data = payloads.get(url);
    return new Response(data ?? "missing", {status: data ? 200 : 404, headers});
  };
  const shell = createOfflineShell({build, caches, fetch, crypto: webcrypto, scope, scriptUrl: scope + workerAsset.path});
  return {shell, payloads, calls, caches, assets, setOffline(value) {offline = value;}};
}
test("complete verified shell reopens offline with original security headers and all asset bytes", async () => {
  const f = fixture();
  await f.shell.install(); await f.shell.activate(); f.setOffline(true);
  const index = await f.shell.respond(new Request(scope));
  assert.ok((await index.text()).endsWith("first"));
  assert.equal(index.headers.get("Cross-Origin-Embedder-Policy"), "require-corp");
  for (const asset of f.assets) {
    const response = await f.shell.respond(new Request(scope + asset.path));
    assert.equal(digest(Buffer.from(await response.arrayBuffer())), asset.sha256);
  }
  assert.ok((await f.shell.respond(new Request(scope + "host-manifest.json"))).ok);
  await assert.rejects(f.shell.respond(new Request(scope + "soundset-catalog/catalog/index.json")), /offline/);
});
test("missing or corrupt update keeps the prior complete shell and removes partial caches", async () => {
  for (const defect of ["missing", "corrupt", "manifest", "favicon"]) {
    const prior = fixture(); await prior.shell.install();
    const update = fixture("second", prior.caches);
    const address = scope + (defect === "manifest" ? "host-manifest.json" : defect === "favicon" ? update.assets[6].path : update.assets[2].path);
    if (defect === "missing") update.payloads.delete(address);
    else update.payloads.set(address, Buffer.from("bad bytes"));
    await assert.rejects(update.shell.install());
    prior.setOffline(true);
    assert.ok((await (await prior.shell.respond(new Request(scope))).text()).endsWith("first"));
    assert.equal((await prior.caches.keys()).length, 1);
  }
});
test("complete waiting update does not replace the active build until activation", async () => {
  const prior = fixture(); await prior.shell.install();
  const update = fixture("second", prior.caches); await update.shell.install();
  prior.setOffline(true); update.setOffline(true);
  assert.ok((await (await prior.shell.respond(new Request(scope))).text()).endsWith("first"));
  assert.equal((await prior.caches.keys()).length, 2);
  await update.shell.activate();
  assert.ok((await (await update.shell.respond(new Request(scope))).text()).endsWith("second"));
  assert.equal((await prior.caches.keys()).length, 1);
});
test("shell installation refuses responses that cannot preserve isolation headers", async () => {
  const f = fixture();
  const shell = createOfflineShell({build: {product_build: "x", host_version: "5.0.0", assets: []},
    caches: f.caches, crypto: webcrypto, scope, fetch: async () => new Response("not isolated")});
  await assert.rejects(shell.install(), /response refused/);
  assert.equal((await f.caches.keys()).length, 0);
});


test("cache reads stay inside the build graph and an asset probe reaches the network", async () => {
  const f=fixture(); await f.shell.install();
  const ready=await f.caches.open((await f.caches.keys())[0]);
  await ready.put(scope+"unrelated",new Response("injected"));
  const outsider=await f.shell.respond(new Request(scope+"unrelated"));
  assert.equal(outsider.status,404);
  const asset=f.assets[0]; f.payloads.set(scope+asset.path,Buffer.from("fresh network witness"));
  assert.equal(await (await f.shell.respond(new Request(scope+asset.path,{headers:{"X-LMDJ-Offline-Probe":"1"}}))).text(),"fresh network witness");
  assert.equal(digest(Buffer.from(await (await f.shell.respond(new Request(scope+asset.path))).arrayBuffer())),asset.sha256);
});

test("an index bound to another favicon cannot publish a ready shell", async () => {
  const f = fixture();
  f.payloads.set(scope + "index.html", Buffer.from(
    f.payloads.get(scope + "index.html").toString().replace(`./${f.assets[6].path}`, "./old-favicon.svg")));
  await assert.rejects(f.shell.install(), /offline index binds another build/);
  assert.equal((await f.caches.keys()).length, 0);
});
