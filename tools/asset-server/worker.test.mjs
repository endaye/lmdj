import {test} from "node:test";
import assert from "node:assert/strict";
import worker from "./worker.mjs";
const sha = "a".repeat(64);
function fixture(status = 200) {
  const calls = [];
  return {calls, env: {ASSETS: {fetch(request) {
    calls.push({path: new URL(request.url).pathname, method: request.method});
    return new Response(request.method === "HEAD" ? null : "asset", {status});
  }}}};
}
test("Catalog and immutable hashes resolve only declared static asset paths", async () => {
  const {calls, env} = fixture();
  const index = await worker.fetch(new Request("https://assets.test/catalog/index.json"), env);
  assert.equal(index.status, 200); assert.equal(index.headers.get("Access-Control-Allow-Origin"), "*");
  assert.ok(!index.headers.get("Cache-Control").includes("immutable"));
  const blob = await worker.fetch(new Request(`https://assets.test/object/blob/${sha}`), env);
  assert.equal(blob.headers.get("ETag"), `"${sha}"`);
  assert.ok(blob.headers.get("Cache-Control").includes("immutable"));
  assert.equal(blob.headers.get("Content-Type"), "audio/wav");
  const manifest = await worker.fetch(new Request(`https://assets.test/object/manifest/${sha}`, {method: "HEAD"}), env);
  assert.equal(manifest.headers.get("Content-Type"), "application/json"); assert.equal(await manifest.text(), "");
  assert.deepEqual(calls, [{path: "/catalog/index.json", method: "GET"}, {path: `/blob/${sha}`, method: "GET"}, {path: `/manifest/${sha}`, method: "HEAD"}]);
});
test("traversal, direct assets, query, non-hash and wrong kind never reach storage", async () => {
  const {calls, env} = fixture();
  for (const path of ["/RIGHTS.md", "/blob/" + sha, "/object/archive/" + sha, "/object/blob/%2e%2e%2fRIGHTS.md", "/object/blob/" + sha.toUpperCase(), "/catalog/index.json?redirect=bad"]) {
    const response = await worker.fetch(new Request("https://assets.test" + path), env);
    assert.ok([400, 404].includes(response.status));
  }
  assert.equal(calls.length, 0);
});
test("missing objects and storage errors stay uncached; writes are refused", async () => {
  for (const status of [404, 500]) {
    const {env} = fixture(status);
    const response = await worker.fetch(new Request(`https://assets.test/object/blob/${sha}`), env);
    assert.equal(response.status, status === 404 ? 404 : 502);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  }
  const {calls, env} = fixture();
  assert.equal((await worker.fetch(new Request("https://assets.test/health", {method: "POST"}), env)).status, 405);
  assert.equal((await worker.fetch(new Request("https://assets.test/health", {method: "OPTIONS"}), env)).status, 204);
  assert.deepEqual(await (await worker.fetch(new Request("https://assets.test/health"), env)).json(), {service: "lmdj-default-assets", ok: true});
  assert.equal(calls.length, 0);
});
