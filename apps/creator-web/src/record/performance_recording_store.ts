export interface PerformanceArtifactRef {
  readonly sha256: string;
  readonly mediaType: "audio/wav";
  readonly byteLength: number;
}

export const PERFORMANCE_RECORDING_CHUNK_BYTES = 1024 * 1024;

export interface RecordingBlob {
  readonly size: number;
  readonly type: string;
  slice(start?: number, end?: number): Pick<Blob, "arrayBuffer">;
}

export interface RecordingFileHandle {
  readonly name: string;
  getFile(): Promise<RecordingBlob>;
}

export interface ManagedRecordingHandle {
  readonly name: string;
}

export interface PerformanceRecordingStorage {
  installManaged(
    artifact: PerformanceArtifactRef,
    source: RecordingFileHandle,
  ): Promise<ManagedRecordingHandle>;
  deleteTemporary(handle: RecordingFileHandle): Promise<void>;
}

export interface PerformanceRecordingFacade {
  bindPerformanceRecording(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
    recordingArtifact: PerformanceArtifactRef;
  }>): Promise<unknown>;
  savePerformance(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
    name: string;
    recordingArtifact: PerformanceArtifactRef;
  }>): Promise<unknown>;
  discardPerformance(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
  }>): Promise<unknown>;
}

export type PerformanceRecordingOperation = "bind" | "save" | "discard";

function operationFingerprint(
  operation: PerformanceRecordingOperation,
  mutationPayload: readonly (number | string)[],
): string {
  return JSON.stringify([operation, ...mutationPayload]);
}

export class PerformanceRecordingCleanupPendingError extends Error {
  readonly code = "PERFORMANCE_RECORDING_CLEANUP_PENDING";
  readonly operation: PerformanceRecordingOperation;
  readonly receipt: unknown;

  constructor(
    operation: PerformanceRecordingOperation,
    receipt: unknown,
    cause: unknown,
  ) {
    super(
      `Performance recording ${operation} succeeded; temporary cleanup is pending`,
      {cause},
    );
    this.name = "PerformanceRecordingCleanupPendingError";
    this.operation = operation;
    this.receipt = receipt;
  }
}

export class PerformanceRecordingOperationConflictError extends Error {
  readonly code = "PERFORMANCE_RECORDING_OPERATION_CONFLICT";
  readonly operation: PerformanceRecordingOperation;

  constructor(operation: PerformanceRecordingOperation) {
    super(`Performance recording is already acknowledged by ${operation}`);
    this.name = "PerformanceRecordingOperationConflictError";
    this.operation = operation;
  }
}

const SHA256_ROUND_CONSTANTS = Uint32Array.from([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
  0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
  0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
  0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
  0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
  0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function rotateRight(value: number, bits: number): number {
  return (value >>> bits) | (value << (32 - bits));
}

class IncrementalSha256 {
  readonly #state = Uint32Array.from([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  readonly #buffer = new Uint8Array(64);
  readonly #schedule = new Uint32Array(64);
  #bufferLength = 0;
  #bytesHashed = 0;

  update(bytes: Uint8Array): void {
    this.#bytesHashed += bytes.length;
    let offset = 0;
    if (this.#bufferLength > 0) {
      const take = Math.min(64 - this.#bufferLength, bytes.length);
      this.#buffer.set(bytes.subarray(0, take), this.#bufferLength);
      this.#bufferLength += take;
      offset = take;
      if (this.#bufferLength === 64) {
        this.#transform(this.#buffer, 0);
        this.#bufferLength = 0;
      }
    }
    while (offset + 64 <= bytes.length) {
      this.#transform(bytes, offset);
      offset += 64;
    }
    if (offset < bytes.length) {
      this.#buffer.set(bytes.subarray(offset), 0);
      this.#bufferLength = bytes.length - offset;
    }
  }

  digestHex(): string {
    const bitLength = this.#bytesHashed * 8;
    this.#buffer[this.#bufferLength] = 0x80;
    this.#bufferLength += 1;
    if (this.#bufferLength > 56) {
      this.#buffer.fill(0, this.#bufferLength);
      this.#transform(this.#buffer, 0);
      this.#bufferLength = 0;
    }
    this.#buffer.fill(0, this.#bufferLength, 56);
    const view = new DataView(this.#buffer.buffer);
    view.setUint32(56, Math.floor(bitLength / 0x1_0000_0000), false);
    view.setUint32(60, bitLength >>> 0, false);
    this.#transform(this.#buffer, 0);
    return Array.from(this.#state, (value) =>
      value.toString(16).padStart(8, "0")).join("");
  }

  #transform(bytes: Uint8Array, offset: number): void {
    for (let index = 0; index < 16; index += 1) {
      const word = offset + index * 4;
      this.#schedule[index] = (
        (bytes[word]! << 24) |
        (bytes[word + 1]! << 16) |
        (bytes[word + 2]! << 8) |
        bytes[word + 3]!
      ) >>> 0;
    }
    for (let index = 16; index < 64; index += 1) {
      const before15 = this.#schedule[index - 15]!;
      const before2 = this.#schedule[index - 2]!;
      const sigma0 = rotateRight(before15, 7) ^ rotateRight(before15, 18) ^
        (before15 >>> 3);
      const sigma1 = rotateRight(before2, 17) ^ rotateRight(before2, 19) ^
        (before2 >>> 10);
      this.#schedule[index] = (
        this.#schedule[index - 16]! + sigma0 +
        this.#schedule[index - 7]! + sigma1
      ) >>> 0;
    }
    let a = this.#state[0]!;
    let b = this.#state[1]!;
    let c = this.#state[2]!;
    let d = this.#state[3]!;
    let e = this.#state[4]!;
    let f = this.#state[5]!;
    let g = this.#state[6]!;
    let h = this.#state[7]!;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choice = (e & f) ^ (~e & g);
      const first = (h + sum1 + choice + SHA256_ROUND_CONSTANTS[index]! +
        this.#schedule[index]!) >>> 0;
      const sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const second = (sum0 + majority) >>> 0;
      h = g; g = f; f = e; e = (d + first) >>> 0;
      d = c; c = b; b = a; a = (first + second) >>> 0;
    }
    this.#state[0] = (this.#state[0]! + a) >>> 0;
    this.#state[1] = (this.#state[1]! + b) >>> 0;
    this.#state[2] = (this.#state[2]! + c) >>> 0;
    this.#state[3] = (this.#state[3]! + d) >>> 0;
    this.#state[4] = (this.#state[4]! + e) >>> 0;
    this.#state[5] = (this.#state[5]! + f) >>> 0;
    this.#state[6] = (this.#state[6]! + g) >>> 0;
    this.#state[7] = (this.#state[7]! + h) >>> 0;
  }
}

async function readChunk(
  file: RecordingBlob,
  start: number,
  end: number,
): Promise<Uint8Array<ArrayBuffer>> {
  const bytes = new Uint8Array(await file.slice(start, end).arrayBuffer());
  if (bytes.length !== end - start) {
    throw new Error("Performance recording changed while being read");
  }
  return bytes;
}

function ascii(bytes: Uint8Array, start: number, text: string): boolean {
  for (let index = 0; index < text.length; index += 1) {
    if (bytes[start + index] !== text.charCodeAt(index)) return false;
  }
  return true;
}

async function validateCanonicalWav(file: RecordingBlob): Promise<void> {
  if (!Number.isSafeInteger(file.size) || file.size < 44 ||
      file.size > 0xffff_ffff + 8) {
    throw new TypeError("Performance recording is not a canonical audio/wav file");
  }
  const header = await readChunk(file, 0, 44);
  const view = new DataView(header.buffer, header.byteOffset, header.byteLength);
  const dataBytes = file.size - 44;
  if (!ascii(header, 0, "RIFF") || view.getUint32(4, true) !== file.size - 8 ||
      !ascii(header, 8, "WAVE") || !ascii(header, 12, "fmt ") ||
      view.getUint32(16, true) !== 16 || view.getUint16(20, true) !== 1 ||
      view.getUint16(22, true) !== 2 || view.getUint32(24, true) !== 48_000 ||
      view.getUint32(28, true) !== 192_000 || view.getUint16(32, true) !== 4 ||
      view.getUint16(34, true) !== 16 || !ascii(header, 36, "data") ||
      view.getUint32(40, true) !== dataBytes || dataBytes % 4 !== 0) {
    throw new TypeError("Performance recording is not a canonical audio/wav file");
  }
}

async function hashFile(file: RecordingBlob): Promise<string> {
  const hash = new IncrementalSha256();
  for (let offset = 0; offset < file.size; offset += PERFORMANCE_RECORDING_CHUNK_BYTES) {
    const end = Math.min(file.size, offset + PERFORMANCE_RECORDING_CHUNK_BYTES);
    hash.update(await readChunk(file, offset, end));
  }
  return hash.digestHex();
}

async function describeWav(file: RecordingBlob): Promise<PerformanceArtifactRef> {
  await validateCanonicalWav(file);
  const sha256 = await hashFile(file);
  return Object.freeze({
    sha256,
    mediaType: "audio/wav" as const,
    byteLength: file.size,
  });
}

export class PerformanceRecordingStore {
  #temporaryHandle: RecordingFileHandle | null;
  readonly #storage: PerformanceRecordingStorage;
  readonly #facade: PerformanceRecordingFacade;
  #artifact: PerformanceArtifactRef | null = null;
  #managedHandle: ManagedRecordingHandle | null = null;
  #operation: {
    kind: PerformanceRecordingOperation;
    fingerprint: string;
    state: "in-flight";
    token: object;
    promise: Promise<unknown>;
  } | {
    kind: PerformanceRecordingOperation;
    fingerprint: string;
    state: "acknowledged";
    receipt: unknown;
    cleanupPromise: Promise<unknown> | null;
    cleaned: boolean;
  } | null = null;

  constructor(
    temporaryHandle: RecordingFileHandle,
    storage: PerformanceRecordingStorage,
    facade: PerformanceRecordingFacade,
  ) {
    this.#temporaryHandle = temporaryHandle;
    this.#storage = storage;
    this.#facade = facade;
  }

  get hasTemporaryFile(): boolean { return this.#temporaryHandle !== null; }
  get managedHandle(): ManagedRecordingHandle | null { return this.#managedHandle; }

  async finalize(): Promise<PerformanceArtifactRef> {
    if (this.#artifact !== null) return this.#artifact;
    const temporary = this.#requireTemporary();
    const artifact = await describeWav(await temporary.getFile());
    const managed = await this.#storage.installManaged(artifact, temporary);
    this.#artifact = artifact;
    this.#managedHandle = managed;
    return artifact;
  }

  bind(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
  }>): Promise<unknown> {
    const fingerprint = operationFingerprint("bind", [
      request.expectedRevision,
      request.performanceId,
    ]);
    return this.#runOperation("bind", fingerprint, async () => {
      const recordingArtifact = await this.finalize();
      return this.#facade.bindPerformanceRecording({
        expectedRevision: request.expectedRevision,
        performanceId: request.performanceId,
        recordingArtifact,
      });
    });
  }

  save(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
    name: string;
  }>): Promise<unknown> {
    const fingerprint = operationFingerprint("save", [
      request.expectedRevision,
      request.performanceId,
      request.name,
    ]);
    return this.#runOperation("save", fingerprint, async () => {
      const recordingArtifact = await this.finalize();
      return this.#facade.savePerformance({
        expectedRevision: request.expectedRevision,
        performanceId: request.performanceId,
        name: request.name,
        recordingArtifact,
      });
    });
  }

  discard(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
  }>): Promise<unknown> {
    const fingerprint = operationFingerprint("discard", [
      request.expectedRevision,
      request.performanceId,
    ]);
    return this.#runOperation(
      "discard",
      fingerprint,
      () => this.#facade.discardPerformance({
        expectedRevision: request.expectedRevision,
        performanceId: request.performanceId,
      }),
    );
  }

  #runOperation(
    kind: PerformanceRecordingOperation,
    fingerprint: string,
    mutation: () => Promise<unknown>,
  ): Promise<unknown> {
    const current = this.#operation;
    if (current !== null) {
      if (current.kind !== kind || current.fingerprint !== fingerprint) {
        return Promise.reject(
          new PerformanceRecordingOperationConflictError(current.kind),
        );
      }
      if (current.state === "in-flight") return current.promise;
      return this.#finishAcknowledged(current);
    }

    const token = {};
    const promise = Promise.resolve().then(
      () => this.#mutateAndFinish(kind, fingerprint, token, mutation),
    );
    this.#operation = {kind, fingerprint, state: "in-flight", token, promise};
    return promise;
  }

  async #mutateAndFinish(
    kind: PerformanceRecordingOperation,
    fingerprint: string,
    token: object,
    mutation: () => Promise<unknown>,
  ): Promise<unknown> {
    let receipt: unknown;
    try {
      receipt = await mutation();
    } catch (error) {
      if (this.#operation?.state === "in-flight" &&
          this.#operation.token === token) {
        this.#operation = null;
      }
      throw error;
    }
    const acknowledged = {
      kind,
      fingerprint,
      state: "acknowledged" as const,
      receipt,
      cleanupPromise: null,
      cleaned: false,
    };
    this.#operation = acknowledged;
    return this.#finishAcknowledged(acknowledged);
  }

  #finishAcknowledged(acknowledged: {
    kind: PerformanceRecordingOperation;
    fingerprint: string;
    state: "acknowledged";
    receipt: unknown;
    cleanupPromise: Promise<unknown> | null;
    cleaned: boolean;
  }): Promise<unknown> {
    if (acknowledged.cleaned) return Promise.resolve(acknowledged.receipt);
    if (acknowledged.cleanupPromise !== null) {
      return acknowledged.cleanupPromise;
    }

    const cleanupPromise = Promise.resolve().then(async () => {
      try {
        await this.#deleteTemporary();
        acknowledged.cleaned = true;
        return acknowledged.receipt;
      } catch (error) {
        throw new PerformanceRecordingCleanupPendingError(
          acknowledged.kind,
          acknowledged.receipt,
          error,
        );
      } finally {
        acknowledged.cleanupPromise = null;
      }
    });
    acknowledged.cleanupPromise = cleanupPromise;
    return cleanupPromise;
  }

  #requireTemporary(): RecordingFileHandle {
    if (this.#temporaryHandle === null) {
      throw new Error("Performance recording temporary file is unavailable");
    }
    return this.#temporaryHandle;
  }

  async #deleteTemporary(): Promise<void> {
    const temporary = this.#temporaryHandle;
    if (temporary === null) return;
    await this.#storage.deleteTemporary(temporary);
    this.#temporaryHandle = null;
  }
}

export class OpfsPerformanceRecordingStorage implements PerformanceRecordingStorage {
  static readonly #installs = new WeakMap<
    FileSystemDirectoryHandle,
    Map<string, Promise<FileSystemFileHandle>>
  >();
  readonly #temporaryDirectory: FileSystemDirectoryHandle;
  readonly #managedDirectory: FileSystemDirectoryHandle;

  constructor(
    temporaryDirectory: FileSystemDirectoryHandle,
    managedDirectory: FileSystemDirectoryHandle,
  ) {
    this.#temporaryDirectory = temporaryDirectory;
    this.#managedDirectory = managedDirectory;
  }

  async installManaged(
    artifact: PerformanceArtifactRef,
    source: RecordingFileHandle,
  ): Promise<FileSystemFileHandle> {
    const name = `${artifact.sha256}.wav`;
    const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
    if (locks !== undefined) {
      return locks.request(
        `lmdj-perform-artifact-${artifact.sha256}`,
        () => this.#installManaged(name, artifact, source),
      );
    }
    // Tests and non-Window Hosts lack Web Locks. Coalesce by directory-handle
    // identity there; production Web Locks cover cooperating same-origin
    // contexts before the existence check and atomic promotion.
    let installs = OpfsPerformanceRecordingStorage.#installs.get(
      this.#managedDirectory,
    );
    if (installs === undefined) {
      installs = new Map();
      OpfsPerformanceRecordingStorage.#installs.set(this.#managedDirectory, installs);
    }
    const active = installs.get(name);
    if (active !== undefined) return active;
    const install = this.#installManaged(name, artifact, source);
    installs.set(name, install);
    try {
      return await install;
    } finally {
      if (installs.get(name) === install) installs.delete(name);
    }
  }

  async #installManaged(
    name: string,
    artifact: PerformanceArtifactRef,
    source: RecordingFileHandle,
  ): Promise<FileSystemFileHandle> {
    const existing = await this.#findManaged(name);
    if (existing !== null) {
      await this.#verifyManaged(existing, artifact, "existing managed performance recording");
      return existing;
    }

    const stagingName = `.perform-staging-${artifact.sha256}-${
      crypto.randomUUID()}-${OpfsPerformanceRecordingStorage.#nextStagingId++}.wav`;
    const staging = await this.#managedDirectory.getFileHandle(
      stagingName,
      {create: true},
    );
    let stagingNeedsCleanup = true;
    try {
      const sourceFile = await source.getFile();
      const writable = await staging.createWritable({keepExistingData: false});
      try {
        for (let offset = 0; offset < sourceFile.size;
          offset += PERFORMANCE_RECORDING_CHUNK_BYTES) {
          const end = Math.min(
            sourceFile.size,
            offset + PERFORMANCE_RECORDING_CHUNK_BYTES,
          );
          await writable.write(await readChunk(sourceFile, offset, end));
        }
        await writable.close();
      } catch (error) {
        await writable.abort(error).catch(() => {});
        throw error;
      }

      await this.#verifyManaged(
        staging,
        artifact,
        "Managed performance recording staging verification failed",
      );
      const raced = await this.#findManaged(name);
      if (raced !== null) {
        await this.#verifyManaged(
          raced,
          artifact,
          "existing managed performance recording is invalid",
        );
        await this.#managedDirectory.removeEntry(stagingName);
        return raced;
      }
      const movable = staging as FileSystemFileHandle & {
        move?: (name: string) => Promise<void>;
      };
      if (typeof movable.move !== "function") {
        throw new Error("OPFS atomic performance recording promotion is unavailable");
      }
      try {
        await movable.move(name);
        stagingNeedsCleanup = false;
      } catch (moveError) {
        const concurrent = await this.#findManaged(name);
        if (concurrent === null) throw moveError;
        await this.#verifyManaged(
          concurrent,
          artifact,
          "existing managed performance recording is invalid",
        );
        await this.#managedDirectory.removeEntry(stagingName).catch(() => {});
        return concurrent;
      }
      // The atomic move preserves the already verified staging entry's bytes.
      // Resolve its managed name, but do not hash the same entry a second time.
      return this.#managedDirectory.getFileHandle(name);
    } finally {
      if (stagingNeedsCleanup) {
        await this.#managedDirectory.removeEntry(stagingName).catch(() => {});
      }
    }
  }

  static #nextStagingId = 1;

  async #findManaged(name: string): Promise<FileSystemFileHandle | null> {
    try {
      return await this.#managedDirectory.getFileHandle(name);
    } catch (error) {
      if (error instanceof DOMException && error.name === "NotFoundError") return null;
      throw error;
    }
  }

  async #verifyManaged(
    handle: FileSystemFileHandle,
    artifact: PerformanceArtifactRef,
    message: string,
  ): Promise<void> {
    let installedArtifact: PerformanceArtifactRef;
    try {
      installedArtifact = await describeWav(await handle.getFile());
    } catch (error) {
      throw new Error(message, {cause: error});
    }
    if (installedArtifact.sha256 !== artifact.sha256 ||
        installedArtifact.byteLength !== artifact.byteLength ||
        installedArtifact.mediaType !== artifact.mediaType) {
      throw new Error(message);
    }
  }

  async deleteTemporary(handle: RecordingFileHandle): Promise<void> {
    await this.#temporaryDirectory.removeEntry(handle.name);
  }
}
