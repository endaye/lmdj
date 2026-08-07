import assert from "node:assert/strict";
import {webcrypto} from "node:crypto";
import test from "node:test";

import {HostProtocolError} from "../web/protocol.mjs";
import {importProjectBundle} from "../web/project_bundle_reader.mjs";


const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
const PATTERN_ID = "22222222-2222-4222-8222-222222222222";
const IMPORT_TOKEN = "33333333-3333-4333-8333-333333333333";
const MAX_CHUNK_BYTES = 1_048_576;

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

async function sha256(bytes) {
  const digest = await webcrypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function bundleFixture(payloads = [
  new TextEncoder().encode("manifest"),
  new Uint8Array(MAX_CHUNK_BYTES + 17).fill(7),
]) {
  let offset = 0;
  const entries = [];
  for (const [index, payload] of payloads.entries()) {
    entries.push({
      bytes: payload.byteLength,
      offset,
      path: payloads.length === 1
        ? "manifest.json"
        : index === 0 ? "assets/0.wav" : "manifest.json",
      sha256: await sha256(payload),
    });
    offset += payload.byteLength;
  }
  const digestSource = {
    compression: "none",
    contract: "lmdj.project-bundle.v1",
    contract_version: "1.0.0",
    entries,
    project_contract: "lmdj.project.v1",
    project_id: PROJECT_ID,
    uncompressed_bytes: offset,
  };
  const index = {
    bundle_digest: await sha256(new TextEncoder().encode(
      canonicalJson(digestSource),
    )),
    ...digestSource,
  };
  const indexBytes = new TextEncoder().encode(canonicalJson(index));
  const header = new Uint8Array(12);
  header.set(new TextEncoder().encode("LMDJBND1"));
  new DataView(header.buffer).setUint32(8, indexBytes.byteLength, false);
  return {
    index,
    bytes: new Blob([header, indexBytes, ...payloads]),
    indexBytes,
  };
}

function trackedFile(blob) {
  const reads = [];
  return {
    reads,
    size: blob.size,
    slice(start, end) {
      reads.push({start, end, bytes: end - start});
      return blob.slice(start, end);
    },
  };
}

function successfulSend(calls, index) {
  return async (operation, payload, sidecar) => {
    calls.push({operation, payload, bytes: sidecar?.byteLength ?? 0});
    if (operation === "project.import.index" && payload.final) {
      return {
        project_id: PROJECT_ID,
        bundle_digest: index.bundle_digest,
        entry_count: index.entries.length,
      };
    }
    if (operation === "project.import.commit") {
      return {
        project_id: PROJECT_ID,
        pattern_id: PATTERN_ID,
        revision: 4,
        bpm: 120,
        asset_count: 1,
        assigned_pad_count: 16,
        bundle_digest: index.bundle_digest,
      };
    }
    return {};
  };
}

test("streams a validated bundle in bounded ordered chunks and returns a summary", async () => {
  const fixture = await bundleFixture();
  const file = trackedFile(fixture.bytes);
  const calls = [];
  const progress = [];
  const result = await importProjectBundle(file, {
    crypto: {
      ...webcrypto,
      subtle: webcrypto.subtle,
      randomUUID: () => IMPORT_TOKEN,
    },
    onProgress: (value) => progress.push(value),
    send: successfulSend(calls, fixture.index),
  });

  assert.deepEqual(result, {
    projectId: PROJECT_ID,
    patternId: PATTERN_ID,
    revision: 4,
    bpm: 120,
    assetCount: 1,
    assignedPadCount: 16,
    bundleDigest: fixture.index.bundle_digest,
  });
  assert.equal(calls[0].operation, "project.import.begin");
  assert.deepEqual(calls[0].payload, {
    import_token: IMPORT_TOKEN,
    index_bytes: fixture.indexBytes.byteLength,
    index_sha256: await sha256(fixture.indexBytes),
  });
  assert.equal(calls.at(-1).operation, "project.import.commit");
  assert.equal(calls.some(({operation}) => operation === "project.import.abort"), false);
  assert.equal(calls.every(({bytes}) => bytes <= MAX_CHUNK_BYTES), true);
  assert.equal(file.reads.every(({bytes}) => bytes <= MAX_CHUNK_BYTES), true);
  assert.deepEqual(progress.at(-1), {
    completedBytes: file.size,
    totalBytes: file.size,
  });
  const entryCalls = calls.filter(({operation}) =>
    operation === "project.import.entry");
  assert.deepEqual(entryCalls.map(({payload}) => ({
    entry_index: payload.entry_index,
    offset: payload.offset,
    final: payload.final,
  })), [
    {entry_index: 0, offset: 0, final: true},
    {entry_index: 1, offset: 0, final: false},
    {entry_index: 1, offset: MAX_CHUNK_BYTES, final: true},
  ]);
});

test("rejects header, canonical-index, and limit violations before mutation", async () => {
  const fixture = await bundleFixture([new TextEncoder().encode("manifest")]);
  const raw = new Uint8Array(await fixture.bytes.arrayBuffer());
  const malformed = [];

  const wrongMagic = new Uint8Array(raw);
  wrongMagic[0] = 0;
  malformed.push(new Blob([wrongMagic]));

  const prettyIndex = new TextEncoder().encode(JSON.stringify(fixture.index, null, 2));
  const prettyHeader = new Uint8Array(12);
  prettyHeader.set(new TextEncoder().encode("LMDJBND1"));
  new DataView(prettyHeader.buffer).setUint32(8, prettyIndex.byteLength, false);
  malformed.push(new Blob([
    prettyHeader,
    prettyIndex,
    raw.subarray(12 + fixture.indexBytes.byteLength),
  ]));

  const oversizedHeader = new Uint8Array(12);
  oversizedHeader.set(new TextEncoder().encode("LMDJBND1"));
  new DataView(oversizedHeader.buffer).setUint32(8, 4_194_305, false);
  malformed.push(new Blob([oversizedHeader]));

  const gap = structuredClone(fixture.index);
  gap.entries[0].offset = 1;
  const gapBytes = new TextEncoder().encode(canonicalJson(gap));
  const gapHeader = new Uint8Array(12);
  gapHeader.set(new TextEncoder().encode("LMDJBND1"));
  new DataView(gapHeader.buffer).setUint32(8, gapBytes.byteLength, false);
  malformed.push(new Blob([gapHeader, gapBytes, new Uint8Array(1)]));

  for (const blob of malformed) {
    const calls = [];
    await assert.rejects(
      importProjectBundle(trackedFile(blob), {
        crypto: {subtle: webcrypto.subtle, randomUUID: () => IMPORT_TOKEN},
        send: async (...args) => calls.push(args),
      }),
      (error) => ["INVALID_PROJECT", "WEB_RUNTIME_RESOURCE_LIMIT"].includes(
        error.code,
      ),
    );
    assert.deepEqual(calls, []);
  }
});

test("cancellation aborts exactly once", async () => {
  const fixture = await bundleFixture([new TextEncoder().encode("manifest")]);
  const calls = [];
  const controller = new AbortController();
  const send = successfulSend(calls, fixture.index);

  await assert.rejects(
    importProjectBundle(trackedFile(fixture.bytes), {
      crypto: {subtle: webcrypto.subtle, randomUUID: () => IMPORT_TOKEN},
      signal: controller.signal,
      send: async (...args) => {
        const result = await send(...args);
        if (args[0] === "project.import.index" && args[1].final) {
          controller.abort();
        }
        return result;
      },
    }),
    (error) => error.name === "AbortError",
  );
  assert.equal(calls.filter(({operation}) =>
    operation === "project.import.abort").length, 1);
  assert.equal(calls.some(({operation}) =>
    operation === "project.import.entry"), false);
});

test("typed rejection aborts once and abort failure never hides the primary error", async () => {
  const fixture = await bundleFixture([new TextEncoder().encode("manifest")]);
  const calls = [];
  const primary = new HostProtocolError(
    "INVALID_PROJECT", "entry hash rejected", {},
  );

  await assert.rejects(
    importProjectBundle(trackedFile(fixture.bytes), {
      crypto: {subtle: webcrypto.subtle, randomUUID: () => IMPORT_TOKEN},
      send: async (operation, payload, sidecar) => {
        calls.push({operation, payload, bytes: sidecar?.byteLength ?? 0});
        if (operation === "project.import.index" && payload.final) {
          return {
            project_id: PROJECT_ID,
            bundle_digest: fixture.index.bundle_digest,
            entry_count: fixture.index.entries.length,
          };
        }
        if (operation === "project.import.entry") {
          throw primary;
        }
        if (operation === "project.import.abort") {
          throw new HostProtocolError("IO_ERROR", "abort failed", {});
        }
        return {};
      },
    }),
    (error) => error === primary,
  );
  assert.equal(calls.filter(({operation}) =>
    operation === "project.import.abort").length, 1);
});

test("an ambiguous begin rejection still attempts the known token abort once", async () => {
  const fixture = await bundleFixture([new TextEncoder().encode("manifest")]);
  const operations = [];
  const primary = new HostProtocolError("HOST_TIMEOUT", "begin timed out", {});
  await assert.rejects(
    importProjectBundle(trackedFile(fixture.bytes), {
      crypto: {subtle: webcrypto.subtle, randomUUID: () => IMPORT_TOKEN},
      send: async (operation) => {
        operations.push(operation);
        if (operation === "project.import.begin") {
          throw primary;
        }
        return {};
      },
    }),
    (error) => error === primary,
  );
  assert.deepEqual(operations, [
    "project.import.begin",
    "project.import.abort",
  ]);
});
