import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import net from "node:net";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";

import {
  CATALOG_OBJECT_KINDS,
  createFetchCatalogClient,
  normalizeCatalogEndpoint,
} from "../web/soundset_catalog.mjs";

const REPO_ROOT = fileURLToPath(new URL("../../..", import.meta.url));
const FOUNDRY_MANIFEST =
  "33175f66912a9add3e4e551d19d85072adcd1f0331fcc9fed80ab0bc18dd9111";
const DIGEST = "a".repeat(64);

// A refusal test proves nothing when a client between it and the code under
// test repairs the very target under test. `undici` normalises a URL before it
// writes the request line, and an HTTP server framework normalises it again
// before a handler sees it, so both would certify a refusal that never
// happened. Every assertion below therefore reads the literal first line of
// the request as it arrived on a raw socket. Do not "simplify" this to
// `node:http`.
function rawRequestLineServer(respond) {
  const lines = [];
  const server = net.createServer((socket) => {
    let buffered = "";
    socket.on("data", (chunk) => {
      buffered += chunk.toString("latin1");
      const end = buffered.indexOf("\r\n\r\n");
      if (end < 0) return;
      lines.push(buffered.slice(0, buffered.indexOf("\r\n")));
      const {status = 200, body = "ok", headers = []} = respond?.(
        lines.at(-1),
      ) ?? {};
      const payload = Buffer.from(body, "latin1");
      socket.end(
        `HTTP/1.1 ${status} X\r\nContent-Length: ${payload.byteLength}\r\n` +
          headers.map((header) => `${header}\r\n`).join("") +
          `Connection: close\r\n\r\n${payload.toString("latin1")}`,
      );
    });
    socket.on("error", () => {});
  });
  const ready = new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve());
  });
  return {
    lines,
    ready,
    get origin() {
      return `http://127.0.0.1:${server.address().port}`;
    },
    close: () => new Promise((resolve) => server.close(() => resolve())),
  };
}

test("addresses an object by exactly {object_kind, sha256} on the wire", async () => {
  const server = rawRequestLineServer();
  await server.ready;
  after(() => server.close());
  const client = createFetchCatalogClient({endpoint: server.origin, fetch});

  await client.readObject({object_kind: "blob", sha256: DIGEST});
  await client.readObject({object_kind: "manifest", sha256: DIGEST});
  await client.readIndex();

  assert.deepEqual(server.lines, [
    `GET /object/blob/${DIGEST} HTTP/1.1`,
    `GET /object/manifest/${DIGEST} HTTP/1.1`,
    "GET /catalog/index.json HTTP/1.1",
  ]);
  assert.deepEqual([...CATALOG_OBJECT_KINDS], ["manifest", "blob"]);
});

test("an endpoint path prefix stays one normalised path", async () => {
  const server = rawRequestLineServer();
  await server.ready;
  after(() => server.close());
  const client = createFetchCatalogClient({
    endpoint: `${server.origin}/sound-sets`,
    fetch,
  });

  await client.readObject({object_kind: "blob", sha256: DIGEST});

  assert.deepEqual(server.lines, [
    `GET /sound-sets/object/blob/${DIGEST} HTTP/1.1`,
  ]);
});

test("refuses every request that is not {object_kind, sha256}", async () => {
  const server = rawRequestLineServer();
  await server.ready;
  after(() => server.close());
  const client = createFetchCatalogClient({endpoint: server.origin, fetch});

  const refused = [
    // Not the two locked fields.
    {},
    {sha256: DIGEST},
    {object_kind: "blob"},
    {object_kind: "blob", sha256: DIGEST, url: "http://example.invalid/x"},
    {object_kind: "blob", sha256: DIGEST, byte_length: 1},
    {object_kind: "blob", sha256: DIGEST, path: "blob/x"},
    // Not one of the two locked kinds. There is no index, archive or entry
    // read on this surface, and no cross-kind redirect.
    {object_kind: "index", sha256: DIGEST},
    {object_kind: "archive", sha256: DIGEST},
    {object_kind: "catalog", sha256: DIGEST},
    {object_kind: "", sha256: DIGEST},
    {object_kind: "../blob", sha256: DIGEST},
    {object_kind: "blob/../manifest", sha256: DIGEST},
    {object_kind: ["blob"], sha256: DIGEST},
    // Not a lowercase sha256, so not an address at all.
    {object_kind: "blob", sha256: DIGEST.toUpperCase()},
    {object_kind: "blob", sha256: `${DIGEST}/../${DIGEST}`},
    {object_kind: "blob", sha256: "../../etc/passwd"},
    {object_kind: "blob", sha256: `/${DIGEST}`},
    {object_kind: "blob", sha256: `${DIGEST}?full=1`},
    {object_kind: "blob", sha256: DIGEST.slice(0, 63)},
    {object_kind: "blob", sha256: `${DIGEST}a`},
    {object_kind: "blob", sha256: 42},
    // Not an object at all.
    null,
    "blob",
    [],
  ];
  for (const request of refused) {
    assert.throws(
      () => client.readObject(request),
      (error) => error.code === "HOST_PROTOCOL_MISMATCH",
      `expected a refusal for ${JSON.stringify(request)}`,
    );
  }

  // The point of the test: not one of those reached the wire. One real
  // request follows as a barrier, so a refusal that had already dispatched a
  // request cannot slip past an assertion made before the socket saw it.
  await client.readObject({object_kind: "manifest", sha256: DIGEST});
  assert.deepEqual(server.lines, [
    `GET /object/manifest/${DIGEST} HTTP/1.1`,
  ]);
});

test("refuses a Catalog endpoint that is not an absolute http origin", () => {
  for (const endpoint of [
    undefined,
    "",
    "soundset-catalog/",
    "/soundset-catalog/",
    "file:///tmp/catalog/",
    "ftp://example.invalid/",
    "http://example.invalid/catalog?token=1",
    "http://example.invalid/catalog#objects",
    "http://example.invalid//catalog/",
  ]) {
    assert.throws(
      () => normalizeCatalogEndpoint(endpoint),
      (error) => error.code === "HOST_PROTOCOL_MISMATCH",
      `expected a refusal for ${String(endpoint)}`,
    );
  }
  assert.equal(
    normalizeCatalogEndpoint("http://example.invalid/catalog"),
    "http://example.invalid/catalog/",
  );
  assert.throws(
    () => createFetchCatalogClient({endpoint: "http://example.invalid/"}),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
});

test("a Catalog that does not resolve the address is unreachable, not fatal", async () => {
  const server = rawRequestLineServer((line) =>
    line.includes("/catalog/index.json")
      ? {status: 302, headers: ["Location: /elsewhere"], body: ""}
      : {status: 404, body: ""},
  );
  await server.ready;
  after(() => server.close());
  const client = createFetchCatalogClient({endpoint: server.origin, fetch});

  await assert.rejects(
    client.readObject({object_kind: "blob", sha256: DIGEST}),
    (error) =>
      error.code === "IO_ERROR" &&
      error.details.reason === "catalog_unavailable",
  );
  // A redirect is never followed to another target.
  await assert.rejects(
    client.readIndex(),
    (error) =>
      error.code === "IO_ERROR" &&
      error.details.reason === "catalog_unavailable",
  );
  assert.deepEqual(server.lines, [
    `GET /object/blob/${DIGEST} HTTP/1.1`,
    "GET /catalog/index.json HTTP/1.1",
  ]);
});

test("an object larger than the Host bound never reaches Core", async () => {
  const server = rawRequestLineServer(() => ({body: "x".repeat(64)}));
  await server.ready;
  after(() => server.close());
  const client = createFetchCatalogClient({
    endpoint: server.origin,
    fetch,
    maximumObjectBytes: 16,
  });

  await assert.rejects(
    client.readObject({object_kind: "blob", sha256: DIGEST}),
    (error) =>
      error.code === "IO_ERROR" &&
      error.details.reason === "catalog_unavailable",
  );
});

test("an unreachable Catalog endpoint is catalog_unavailable", async () => {
  const server = rawRequestLineServer();
  await server.ready;
  const origin = server.origin;
  await server.close();
  const client = createFetchCatalogClient({endpoint: origin, fetch});

  await assert.rejects(
    client.readIndex(),
    (error) =>
      error.code === "IO_ERROR" &&
      error.details.reason === "catalog_unavailable",
  );
});

// The corpus server admits exactly the three shapes this transport spells, so
// pointing one at the other proves the two agree without either being edited
// to match the test.
test("resolves the fixture corpus through the fixture Catalog server", async () => {
  const server = spawn(
    "python3",
    [
      "tools/soundset-fixtures/catalog_fixture_server.py",
      "--root",
      "tests/fixtures/soundset",
    ],
    {cwd: REPO_ROOT, stdio: ["ignore", "pipe", "inherit"]},
  );
  after(() => server.kill("SIGTERM"));
  const origin = await new Promise((resolve, reject) => {
    let buffered = "";
    server.stdout.on("data", (chunk) => {
      buffered += chunk.toString("utf8");
      const match = /at (http:\/\/[^\s]+)/.exec(buffered);
      if (match !== null) resolve(match[1]);
    });
    server.once("error", reject);
    server.once("exit", (code) =>
      reject(new Error(`fixture Catalog server exited with ${code}`)));
  });

  const client = createFetchCatalogClient({endpoint: origin, fetch});
  const index = await client.readIndex();
  const parsed = JSON.parse(new TextDecoder().decode(index));
  assert.equal(parsed.contract, "lmdj.soundset-catalog.v1");
  assert.ok(parsed.entries.some((entry) =>
    entry.manifest_sha256 === FOUNDRY_MANIFEST));

  const manifest = await client.readObject({
    object_kind: "manifest",
    sha256: FOUNDRY_MANIFEST,
  });
  assert.ok(manifest.byteLength > 0);
  const {slots} = JSON.parse(new TextDecoder().decode(manifest));
  const artifact = slots.find((entry) => entry.artifact !== undefined).artifact;
  const blob = await client.readObject({
    object_kind: "blob",
    sha256: artifact.sha256,
  });
  assert.equal(blob.byteLength, artifact.byte_length);

  // A manifest digest is not a blob, and the server never redirects across
  // the two kinds.
  await assert.rejects(
    client.readObject({object_kind: "blob", sha256: FOUNDRY_MANIFEST}),
    (error) => error.details.reason === "catalog_unavailable",
  );
});
