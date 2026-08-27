import {
  HostProtocolError,
  MAX_ASSET_BYTES,
} from "./protocol.mjs";
import {canonicalJson, exactKeys, sha256Hex} from "./integrity.mjs";


const MAGIC = new TextEncoder().encode("LMDJBND1");
const HEADER_BYTES = 12;
const MAX_INDEX_BYTES = 4_194_304;
const MAX_ENTRIES = 4_096;
const MAX_PATH_BYTES = 255;
const MAX_ENTRY_BYTES = 67_108_864;
const MAX_PAYLOAD_BYTES = 536_870_912;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const PATH_PATTERN =
  /^(?!.*(?:^|\/)\.{1,2}(?:\/|$))[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)*$/;
const ROOT_KEYS = [
  "bundle_digest",
  "compression",
  "contract",
  "contract_version",
  "entries",
  "project_contract",
  "project_id",
  "uncompressed_bytes",
].sort();
const ENTRY_KEYS = ["bytes", "offset", "path", "sha256"].sort();
const SUMMARY_KEYS = [
  "asset_count",
  "assigned_pad_count",
  "bpm",
  "bundle_digest",
  "pattern_id",
  "project_id",
  "revision",
].sort();

function typedError(code, message) {
  return new HostProtocolError(code, message, {});
}

function invalid(message) {
  return typedError("INVALID_PROJECT", message);
}

function resourceLimit(message) {
  return typedError("WEB_RUNTIME_RESOURCE_LIMIT", message);
}

function bytesEqual(left, right) {
  return left.byteLength === right.byteLength &&
    left.every((byte, index) => byte === right[index]);
}

export function validBundlePath(path) {
  return typeof path === "string" && PATH_PATTERN.test(path);
}

async function readExact(file, start, end) {
  if (
    typeof file?.slice !== "function" ||
    !Number.isSafeInteger(file.size) ||
    file.size < 0
  ) {
    throw invalid("Project Bundle source is not a bounded browser File");
  }
  const part = file.slice(start, end);
  if (typeof part?.arrayBuffer !== "function") {
    throw invalid("Project Bundle source cannot be read");
  }
  const bytes = new Uint8Array(await part.arrayBuffer());
  if (bytes.byteLength !== end - start) {
    throw invalid("Project Bundle source ended unexpectedly");
  }
  return bytes;
}

async function readIndex(file, indexBytes, report) {
  const result = new Uint8Array(indexBytes);
  let offset = 0;
  while (offset < indexBytes) {
    const chunkBytes = Math.min(MAX_ASSET_BYTES, indexBytes - offset);
    const chunk = await readExact(
      file,
      HEADER_BYTES + offset,
      HEADER_BYTES + offset + chunkBytes,
    );
    result.set(chunk, offset);
    offset += chunkBytes;
    report(HEADER_BYTES + offset);
  }
  return result;
}

async function validateIndex(indexBytes, fileSize, crypto) {
  let text;
  try {
    text = new TextDecoder("utf-8", {fatal: true}).decode(indexBytes);
  } catch {
    throw invalid("Project Bundle index is not strict UTF-8");
  }
  let index;
  try {
    index = JSON.parse(text);
  } catch {
    throw invalid("Project Bundle index is not JSON");
  }
  if (!exactKeys(index, ROOT_KEYS)) {
    throw invalid("Project Bundle index shape is invalid");
  }
  const canonical = new TextEncoder().encode(canonicalJson(index));
  if (!bytesEqual(canonical, indexBytes)) {
    throw invalid("Project Bundle index is not canonical JSON");
  }
  if (
    index.contract !== "lmdj.project-bundle.v1" ||
    !["1.0.0", "1.1.0"].includes(index.contract_version) ||
    index.compression !== "none" ||
    !["lmdj.project.v1", "lmdj.project.v2", "lmdj.project.v3"]
      .includes(index.project_contract) ||
    !UUID_PATTERN.test(index.project_id) ||
    !SHA256_PATTERN.test(index.bundle_digest) ||
    !Array.isArray(index.entries) ||
    index.entries.length < 1
  ) {
    throw invalid("Project Bundle identity is invalid");
  }
  if (index.entries.length > MAX_ENTRIES) {
    throw resourceLimit("Project Bundle entry count exceeds the limit");
  }

  let expectedOffset = 0;
  let previousPath = null;
  const foldedPaths = new Set();
  for (const entry of index.entries) {
    if (
      !exactKeys(entry, ENTRY_KEYS) ||
      !Number.isSafeInteger(entry.bytes) ||
      entry.bytes < 0 ||
      !Number.isSafeInteger(entry.offset) ||
      entry.offset < 0 ||
      !validBundlePath(entry.path) ||
      new TextEncoder().encode(entry.path).byteLength > MAX_PATH_BYTES ||
      !SHA256_PATTERN.test(entry.sha256)
    ) {
      throw invalid("Project Bundle entry is invalid");
    }
    if (entry.bytes > MAX_ENTRY_BYTES) {
      throw resourceLimit("Project Bundle entry exceeds the limit");
    }
    if (entry.offset !== expectedOffset) {
      throw invalid("Project Bundle entry offsets are not contiguous");
    }
    if (previousPath !== null && previousPath >= entry.path) {
      throw invalid("Project Bundle paths are not canonically sorted");
    }
    const folded = entry.path.toLowerCase();
    if (foldedPaths.has(folded)) {
      throw invalid("Project Bundle paths collide");
    }
    foldedPaths.add(folded);
    previousPath = entry.path;
    expectedOffset += entry.bytes;
    if (!Number.isSafeInteger(expectedOffset) || expectedOffset > MAX_PAYLOAD_BYTES) {
      throw resourceLimit("Project Bundle payload exceeds the limit");
    }
  }
  if (
    !Number.isSafeInteger(index.uncompressed_bytes) ||
    index.uncompressed_bytes < 0 ||
    index.uncompressed_bytes !== expectedOffset ||
    fileSize !== HEADER_BYTES + indexBytes.byteLength + expectedOffset
  ) {
    throw invalid("Project Bundle payload boundary is invalid");
  }
  const {bundle_digest: _removed, ...digestSource} = index;
  const digest = await sha256Hex(
    new TextEncoder().encode(canonicalJson(digestSource)),
    crypto,
  );
  if (digest !== index.bundle_digest) {
    throw invalid("Project Bundle digest is invalid");
  }
  return index;
}

function throwIfAborted(signal) {
  if (signal?.aborted !== true) {
    return;
  }
  if (typeof DOMException === "function") {
    throw new DOMException("Project Bundle import was cancelled", "AbortError");
  }
  const error = new Error("Project Bundle import was cancelled");
  error.name = "AbortError";
  throw error;
}

async function sidecarDeclaration(bytes, crypto) {
  return {
    sidecar_bytes: bytes.byteLength,
    sidecar_sha256: await sha256Hex(bytes, crypto),
  };
}

function validateIdentity(value, index) {
  if (
    !exactKeys(value, ["bundle_digest", "entry_count", "project_id"].sort()) ||
    value.project_id !== index.project_id ||
    value.bundle_digest !== index.bundle_digest ||
    value.entry_count !== index.entries.length
  ) {
    throw typedError(
      "HOST_PROTOCOL_MISMATCH",
      "Project Bundle import identity is invalid",
    );
  }
}

export function normalizeLocalProjectSummary(value, {
  projectId = null,
  bundleDigest = null,
} = {}) {
  if (
    !exactKeys(value, SUMMARY_KEYS) ||
    (projectId !== null && value.project_id !== projectId) ||
    !UUID_PATTERN.test(value.project_id) ||
    !UUID_PATTERN.test(value.pattern_id) ||
    (bundleDigest !== null && value.bundle_digest !== bundleDigest) ||
    !SHA256_PATTERN.test(value.bundle_digest) ||
    !Number.isSafeInteger(value.revision) ||
    value.revision < 0 ||
    !Number.isSafeInteger(value.bpm) ||
    value.bpm < 40 ||
    value.bpm > 240 ||
    !Number.isSafeInteger(value.asset_count) ||
    value.asset_count < 0 ||
    !Number.isSafeInteger(value.assigned_pad_count) ||
    value.assigned_pad_count < 0 ||
    value.assigned_pad_count > 64
  ) {
    throw typedError(
      "HOST_PROTOCOL_MISMATCH",
      "Local Project summary is invalid",
    );
  }
  return Object.freeze({
    projectId: value.project_id,
    patternId: value.pattern_id,
    revision: value.revision,
    bpm: value.bpm,
    assetCount: value.asset_count,
    assignedPadCount: value.assigned_pad_count,
    bundleDigest: value.bundle_digest,
  });
}

export async function importProjectBundle(file, {
  send,
  crypto,
  signal,
  onProgress = () => {},
} = {}) {
  if (
    typeof send !== "function" ||
    typeof crypto?.randomUUID !== "function" ||
    typeof onProgress !== "function"
  ) {
    throw new TypeError("Project Bundle import dependencies are invalid");
  }
  throwIfAborted(signal);
  const totalBytes = file?.size;
  if (!Number.isSafeInteger(totalBytes) || totalBytes < HEADER_BYTES) {
    throw invalid("Project Bundle header is missing");
  }
  const report = (completedBytes) => {
    try {
      onProgress(Object.freeze({completedBytes, totalBytes}));
    } catch {
      // Progress observers cannot change the authoritative transfer outcome.
    }
  };
  const header = await readExact(file, 0, HEADER_BYTES);
  if (!bytesEqual(header.subarray(0, MAGIC.byteLength), MAGIC)) {
    throw invalid("Project Bundle magic is invalid");
  }
  const indexByteLength = new DataView(
    header.buffer,
    header.byteOffset,
    header.byteLength,
  ).getUint32(8, false);
  if (indexByteLength < 1) {
    throw invalid("Project Bundle index is empty");
  }
  if (indexByteLength > MAX_INDEX_BYTES) {
    throw resourceLimit("Project Bundle index exceeds the limit");
  }
  if (totalBytes < HEADER_BYTES + indexByteLength) {
    throw invalid("Project Bundle index is truncated");
  }
  report(HEADER_BYTES);
  const indexBytes = await readIndex(file, indexByteLength, report);
  const index = await validateIndex(indexBytes, totalBytes, crypto);
  const indexSha256 = await sha256Hex(indexBytes, crypto);
  const importToken = crypto.randomUUID();
  if (!UUID_PATTERN.test(importToken)) {
    throw typedError(
      "HOST_PROTOCOL_MISMATCH",
      "Project Bundle import token is invalid",
    );
  }

  let beginAttempted = false;
  let committed = false;
  let abortAttempted = false;
  const abortOnce = async () => {
    if (!beginAttempted || committed || abortAttempted) {
      return;
    }
    abortAttempted = true;
    await send("project.import.abort", {import_token: importToken});
  };

  try {
    throwIfAborted(signal);
    beginAttempted = true;
    await send("project.import.begin", {
      import_token: importToken,
      index_bytes: indexByteLength,
      index_sha256: indexSha256,
    });
    let indexOffset = 0;
    let identity = null;
    while (indexOffset < indexBytes.byteLength) {
      throwIfAborted(signal);
      const end = Math.min(indexOffset + MAX_ASSET_BYTES, indexBytes.byteLength);
      const chunk = indexBytes.subarray(indexOffset, end);
      const final = end === indexBytes.byteLength;
      identity = await send("project.import.index", {
        import_token: importToken,
        offset: indexOffset,
        final,
        sidecar: await sidecarDeclaration(chunk, crypto),
      }, chunk);
      indexOffset = end;
    }
    validateIdentity(identity, index);

    const payloadStart = HEADER_BYTES + indexByteLength;
    for (const [entryIndex, entry] of index.entries.entries()) {
      let entryOffset = 0;
      do {
        throwIfAborted(signal);
        const chunkBytes = Math.min(
          MAX_ASSET_BYTES,
          entry.bytes - entryOffset,
        );
        const chunk = await readExact(
          file,
          payloadStart + entry.offset + entryOffset,
          payloadStart + entry.offset + entryOffset + chunkBytes,
        );
        const final = entryOffset + chunkBytes === entry.bytes;
        await send("project.import.entry", {
          import_token: importToken,
          entry_index: entryIndex,
          offset: entryOffset,
          final,
          sidecar: await sidecarDeclaration(chunk, crypto),
        }, chunk);
        entryOffset += chunkBytes;
        report(payloadStart + entry.offset + entryOffset);
      } while (entryOffset < entry.bytes);
    }
    throwIfAborted(signal);
    const summary = normalizeLocalProjectSummary(
      await send("project.import.commit", {import_token: importToken}),
      {projectId: index.project_id, bundleDigest: index.bundle_digest},
    );
    committed = true;
    report(totalBytes);
    return summary;
  } catch (error) {
    try {
      await abortOnce();
    } catch {
      // The primary import/cancellation error remains authoritative.
    }
    throw error;
  }
}
