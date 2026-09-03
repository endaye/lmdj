import {Buffer} from "node:buffer";
import {createHash} from "node:crypto";
import {describe, expect, test, vi} from "vitest";

import {encodePcm16Wav, encodePcm16WavHeader} from "../src/capture/wav_encoder";
import {
  OpfsPerformanceRecordingStorage,
  PerformanceRecordingStore,
} from "../src/record/performance_recording_store";

const PERFORMANCE_ID = "11111111-1111-4111-8111-111111111111";
const MAX_CHUNK_BYTES = 1024 * 1024;
const samples = Float32Array.from([0, 0.25, -0.5, 1]);
const wav = encodePcm16Wav([samples, samples]);

class BoundedFile {
  readonly size: number;
  readonly type = "audio/wav";
  readonly reads: number[] = [];
  wholeReads = 0;
  readonly #bytes: Uint8Array<ArrayBuffer>;

  constructor(bytes: Uint8Array<ArrayBuffer>) {
    this.#bytes = bytes.slice();
    this.size = bytes.length;
  }

  async arrayBuffer(): Promise<ArrayBuffer> {
    this.wholeReads += 1;
    throw new Error("whole-file arrayBuffer is forbidden");
  }

  slice(start = 0, end = this.size): {arrayBuffer(): Promise<ArrayBuffer>} {
    const boundedEnd = Math.min(end, this.size);
    this.reads.push(boundedEnd - start);
    const chunk = this.#bytes.slice(start, boundedEnd);
    return {arrayBuffer: async () => chunk.buffer};
  }
}

function fixture(bytes = wav) {
  const events: string[] = [];
  const temporaryFile = new BoundedFile(bytes);
  const temporaryHandle = {
    name: "perform-temp.wav",
    getFile: vi.fn(async () => temporaryFile),
  };
  const managedHandle = {name: "managed.wav"};
  const storage = {
    installManaged: vi.fn(async (artifact: unknown, source: unknown) => {
      events.push("install");
      expect(source).toBe(temporaryHandle);
      expect(artifact).not.toHaveProperty("path");
      return managedHandle;
    }),
    deleteTemporary: vi.fn(async (handle: unknown) => {
      events.push("delete-temp");
      expect(handle).toBe(temporaryHandle);
    }),
  };
  const facade = {
    bindPerformanceRecording: vi.fn(async (request: unknown) => {
      events.push("bind");
      return {committedRevision: 8, ...request as object};
    }),
    savePerformance: vi.fn(async (request: unknown) => {
      events.push("save");
      return {committedRevision: 8, ...request as object};
    }),
    discardPerformance: vi.fn(async (request: unknown) => {
      events.push("discard");
      return {committedRevision: 8, ...request as object};
    }),
  };
  const store = new PerformanceRecordingStore(
    temporaryHandle as never,
    storage as never,
    facade as never,
  );
  return {
    events, facade, managedHandle, storage, store, temporaryFile, temporaryHandle,
  };
}

function deferred<T = void>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {promise, reject, resolve};
}

describe("PerformanceRecordingStore", () => {
  test("finalizes exact identity and installs immutable managed bytes before bind", async () => {
    const {events, facade, managedHandle, store, storage, temporaryFile} = fixture();
    const expected = {
      sha256: createHash("sha256").update(wav).digest("hex"),
      mediaType: "audio/wav",
      byteLength: wav.length,
    } as const;

    expect(await store.finalize()).toEqual(expected);
    expect(storage.installManaged).toHaveBeenCalledWith(expected, expect.anything());
    expect(store.managedHandle).toBe(managedHandle);
    expect(events).toEqual(["install"]);
    expect(temporaryFile.wholeReads).toBe(0);
    expect(Math.max(...temporaryFile.reads)).toBeLessThanOrEqual(MAX_CHUNK_BYTES);

    await store.bind({expectedRevision: 7, performanceId: PERFORMANCE_ID});
    expect(events).toEqual(["install", "bind", "delete-temp"]);
    expect(facade.bindPerformanceRecording).toHaveBeenCalledWith({
      expectedRevision: 7,
      performanceId: PERFORMANCE_ID,
      recordingArtifact: expected,
    });
    expect(Object.keys(facade.bindPerformanceRecording.mock.calls[0]![0] as object).sort())
      .toEqual(["expectedRevision", "performanceId", "recordingArtifact"]);
    expect(store.hasTemporaryFile).toBe(false);
  });

  test("installs before save and passes only ArtifactRef through Facade", async () => {
    const {events, facade, store} = fixture();
    await store.save({
      expectedRevision: 7,
      performanceId: PERFORMANCE_ID,
      name: "Warehouse set",
    });
    expect(events).toEqual(["install", "save", "delete-temp"]);
    expect(facade.savePerformance.mock.calls[0]![0]).toEqual({
      expectedRevision: 7,
      performanceId: PERFORMANCE_ID,
      name: "Warehouse set",
      recordingArtifact: {
        sha256: createHash("sha256").update(wav).digest("hex"),
        mediaType: "audio/wav",
        byteLength: wav.length,
      },
    });
  });

  test("retains the unbound temp after retryable bind failure and deletes it after acknowledgement", async () => {
    const {events, facade, store, storage} = fixture();
    facade.bindPerformanceRecording
      .mockImplementationOnce(async () => {
        events.push("bind");
        throw Object.assign(new Error("busy"), {code: "PROJECT_BUSY"});
      });

    await expect(store.bind({expectedRevision: 7, performanceId: PERFORMANCE_ID}))
      .rejects.toMatchObject({code: "PROJECT_BUSY"});
    expect(events).toEqual(["install", "bind"]);
    expect(storage.deleteTemporary).not.toHaveBeenCalled();
    expect(store.hasTemporaryFile).toBe(true);

    await store.bind({expectedRevision: 7, performanceId: PERFORMANCE_ID});
    expect(events).toEqual(["install", "bind", "bind", "delete-temp"]);
    expect(store.hasTemporaryFile).toBe(false);
  });

  test("bind acknowledgement survives deletion failure and retry performs cleanup only", async () => {
    const {facade, store, storage} = fixture();
    storage.deleteTemporary.mockRejectedValueOnce(new Error("delete failed"));
    const request = {expectedRevision: 7, performanceId: PERFORMANCE_ID};

    let pending: unknown;
    try {
      await store.bind(request);
    } catch (error) {
      pending = error;
    }
    expect(pending).toMatchObject({
      code: "PERFORMANCE_RECORDING_CLEANUP_PENDING",
      operation: "bind",
      receipt: {committedRevision: 8},
    });
    expect(store.hasTemporaryFile).toBe(true);
    expect(facade.bindPerformanceRecording).toHaveBeenCalledTimes(1);

    await expect(store.save({...request, name: "must not save"}))
      .rejects.toMatchObject({
        code: "PERFORMANCE_RECORDING_OPERATION_CONFLICT",
        operation: "bind",
      });
    expect(facade.savePerformance).not.toHaveBeenCalled();

    const receipt = await store.bind(request);
    expect(receipt).toBe((pending as {receipt: unknown}).receipt);
    expect(facade.bindPerformanceRecording).toHaveBeenCalledTimes(1);
    expect(storage.deleteTemporary).toHaveBeenCalledTimes(2);
    expect(store.hasTemporaryFile).toBe(false);
  });

  test("identical concurrent save requests share one mutation and initial cleanup", async () => {
    const {facade, store, storage} = fixture();
    const deletion = deferred();
    storage.deleteTemporary.mockImplementationOnce(async () => deletion.promise);
    const request = {
      expectedRevision: 7,
      performanceId: PERFORMANCE_ID,
      name: "Warehouse set",
    };

    const first = store.save(request);
    const second = store.save({...request});
    expect(second).toBe(first);
    await vi.waitFor(() => {
      expect(facade.savePerformance).toHaveBeenCalledTimes(1);
      expect(storage.deleteTemporary).toHaveBeenCalledTimes(1);
    });

    deletion.resolve();
    const [firstReceipt, secondReceipt] = await Promise.all([first, second]);
    expect(secondReceipt).toBe(firstReceipt);
    expect(facade.savePerformance).toHaveBeenCalledTimes(1);
    expect(storage.deleteTemporary).toHaveBeenCalledTimes(1);
  });

  test("changed save payload conflicts while the first request is still active", async () => {
    const {facade, store, storage} = fixture();
    const deletion = deferred();
    storage.deleteTemporary.mockImplementationOnce(async () => deletion.promise);
    const request = {
      expectedRevision: 7,
      performanceId: PERFORMANCE_ID,
      name: "Warehouse set",
    };

    const first = store.save(request);
    await vi.waitFor(() => expect(storage.deleteTemporary).toHaveBeenCalledTimes(1));
    const changed = store.save({...request, name: "Different set"});
    deletion.resolve();

    await expect(first).resolves.toMatchObject({name: "Warehouse set"});
    await expect(changed).rejects.toMatchObject({
      code: "PERFORMANCE_RECORDING_OPERATION_CONFLICT",
      operation: "save",
    });
    expect(facade.savePerformance).toHaveBeenCalledTimes(1);
    expect(storage.deleteTemporary).toHaveBeenCalledTimes(1);
  });

  test("identical concurrent cleanup retries share one deletion and preserve the receipt", async () => {
    const {facade, store, storage} = fixture();
    storage.deleteTemporary.mockRejectedValueOnce(new Error("delete failed"));
    const request = {
      expectedRevision: 7,
      performanceId: PERFORMANCE_ID,
      name: "Warehouse set",
    };

    let pending: unknown;
    try {
      await store.save(request);
    } catch (error) {
      pending = error;
    }
    const deletion = deferred();
    storage.deleteTemporary.mockImplementationOnce(async () => deletion.promise);

    const firstRetry = store.save({...request});
    const secondRetry = store.save({...request});
    expect(secondRetry).toBe(firstRetry);
    await vi.waitFor(() => {
      expect(storage.deleteTemporary).toHaveBeenCalledTimes(2);
    });
    expect(facade.savePerformance).toHaveBeenCalledTimes(1);

    deletion.resolve();
    const [firstReceipt, secondReceipt] = await Promise.all([firstRetry, secondRetry]);
    expect(firstReceipt).toBe((pending as {receipt: unknown}).receipt);
    expect(secondReceipt).toBe(firstReceipt);
    expect(facade.savePerformance).toHaveBeenCalledTimes(1);
    expect(storage.deleteTemporary).toHaveBeenCalledTimes(2);

    await expect(store.save({...request})).resolves.toBe(firstReceipt);
    expect(facade.savePerformance).toHaveBeenCalledTimes(1);
    expect(storage.deleteTemporary).toHaveBeenCalledTimes(2);
  });

  test("changed save name conflicts with an acknowledged save without mutation or cleanup", async () => {
    const {facade, store, storage} = fixture();
    storage.deleteTemporary.mockRejectedValueOnce(new Error("delete failed"));
    const request = {
      expectedRevision: 7,
      performanceId: PERFORMANCE_ID,
      name: "Warehouse set",
    };
    await expect(store.save(request)).rejects.toMatchObject({
      code: "PERFORMANCE_RECORDING_CLEANUP_PENDING",
    });

    await expect(store.save({...request, name: "Different set"}))
      .rejects.toMatchObject({
        code: "PERFORMANCE_RECORDING_OPERATION_CONFLICT",
        operation: "save",
      });
    expect(facade.savePerformance).toHaveBeenCalledTimes(1);
    expect(storage.deleteTemporary).toHaveBeenCalledTimes(1);
    expect(store.hasTemporaryFile).toBe(true);
  });

  test("changed bind target conflicts with an acknowledged bind without mutation or cleanup", async () => {
    const {facade, store, storage} = fixture();
    storage.deleteTemporary.mockRejectedValueOnce(new Error("delete failed"));
    const request = {expectedRevision: 7, performanceId: PERFORMANCE_ID};
    await expect(store.bind(request)).rejects.toMatchObject({
      code: "PERFORMANCE_RECORDING_CLEANUP_PENDING",
    });

    await expect(store.bind({...request, performanceId: "other-performance"}))
      .rejects.toMatchObject({
        code: "PERFORMANCE_RECORDING_OPERATION_CONFLICT",
        operation: "bind",
      });
    expect(facade.bindPerformanceRecording).toHaveBeenCalledTimes(1);
    expect(storage.deleteTemporary).toHaveBeenCalledTimes(1);
    expect(store.hasTemporaryFile).toBe(true);
  });

  test("save acknowledgement survives deletion failure and retry performs cleanup only", async () => {
    const {facade, store, storage} = fixture();
    storage.deleteTemporary.mockRejectedValueOnce(new Error("delete failed"));
    const request = {
      expectedRevision: 7,
      performanceId: PERFORMANCE_ID,
      name: "Warehouse set",
    };

    let pending: unknown;
    try {
      await store.save(request);
    } catch (error) {
      pending = error;
    }
    expect(pending).toMatchObject({
      code: "PERFORMANCE_RECORDING_CLEANUP_PENDING",
      operation: "save",
      receipt: {committedRevision: 8},
    });
    expect(store.hasTemporaryFile).toBe(true);
    expect(facade.savePerformance).toHaveBeenCalledTimes(1);

    const receipt = await store.save(request);
    expect(receipt).toBe((pending as {receipt: unknown}).receipt);
    expect(facade.savePerformance).toHaveBeenCalledTimes(1);
    expect(storage.deleteTemporary).toHaveBeenCalledTimes(2);
    expect(store.hasTemporaryFile).toBe(false);
  });

  test("discard acknowledgement survives deletion failure and retry performs cleanup only", async () => {
    const {facade, store, storage} = fixture();
    storage.deleteTemporary.mockRejectedValueOnce(new Error("delete failed"));
    const request = {expectedRevision: 7, performanceId: PERFORMANCE_ID};

    let pending: unknown;
    try {
      await store.discard(request);
    } catch (error) {
      pending = error;
    }
    expect(pending).toMatchObject({
      code: "PERFORMANCE_RECORDING_CLEANUP_PENDING",
      operation: "discard",
      receipt: {committedRevision: 8},
    });
    expect(store.hasTemporaryFile).toBe(true);
    expect(facade.discardPerformance).toHaveBeenCalledTimes(1);

    const receipt = await store.discard(request);
    expect(receipt).toBe((pending as {receipt: unknown}).receipt);
    expect(facade.discardPerformance).toHaveBeenCalledTimes(1);
    expect(storage.deleteTemporary).toHaveBeenCalledTimes(2);
    expect(store.hasTemporaryFile).toBe(false);
  });

  test("deletes the temp only after successful discard acknowledgement", async () => {
    const {events, facade, store, storage} = fixture();
    facade.discardPerformance
      .mockImplementationOnce(async () => {
        events.push("discard");
        throw Object.assign(new Error("busy"), {code: "PROJECT_BUSY"});
      });
    await expect(store.discard({expectedRevision: 7, performanceId: PERFORMANCE_ID}))
      .rejects.toMatchObject({code: "PROJECT_BUSY"});
    expect(events).toEqual(["discard"]);
    expect(storage.deleteTemporary).not.toHaveBeenCalled();

    await store.discard({expectedRevision: 7, performanceId: PERFORMANCE_ID});
    expect(events).toEqual(["discard", "discard", "delete-temp"]);
    expect(store.hasTemporaryFile).toBe(false);
  });

  test("rejects bytes that are not a canonical PCM16 48 kHz stereo WAV", async () => {
    const invalid = wav.slice();
    new DataView(invalid.buffer).setUint32(24, 44_100, true);
    const {storage, store} = fixture(invalid);
    await expect(store.finalize()).rejects.toThrow("canonical");
    expect(storage.installManaged).not.toHaveBeenCalled();
  });

  test("streams a multi-chunk digest without allocating a view per SHA block", async () => {
    const frames = Math.ceil((MAX_CHUNK_BYTES * 2 + 17) / 4);
    const largeWav = new Uint8Array(44 + frames * 4);
    largeWav.set(encodePcm16WavHeader(frames, 2));
    const nativeDataView = globalThis.DataView;
    let viewConstructions = 0;
    vi.stubGlobal("DataView", new Proxy(nativeDataView, {
      construct(target, argumentsList, newTarget) {
        viewConstructions += 1;
        return Reflect.construct(target, argumentsList, newTarget);
      },
    }));

    try {
      const {store} = fixture(largeWav);
      await expect(store.finalize()).resolves.toMatchObject({
        sha256: createHash("sha256").update(largeWav).digest("hex"),
        byteLength: largeWav.length,
      });
    } finally {
      vi.unstubAllGlobals();
    }

    expect(viewConstructions).toBeLessThanOrEqual(2);
  });

  test("copies and verifies a multi-chunk managed WAV without whole-file reads", async () => {
    const frames = Math.ceil((MAX_CHUNK_BYTES * 2 + 17) / 4);
    const largeWav = new Uint8Array(44 + frames * 4);
    largeWav.set(encodePcm16WavHeader(frames, 2));
    const source = new BoundedFile(largeWav);
    const expectedName = `${createHash("sha256").update(largeWav).digest("hex")}.wav`;
    let installed = new Uint8Array(new ArrayBuffer(0));
    let promoted = false;
    const writeSizes: number[] = [];
    let installedFile: BoundedFile | null = null;
    const destination = {
      name: "managed.wav",
      createWritable: vi.fn(async () => {
        const chunks: Uint8Array<ArrayBuffer>[] = [];
        return {
          write: async (chunk: Uint8Array<ArrayBuffer>) => {
            writeSizes.push(chunk.byteLength);
            chunks.push(chunk.slice());
          },
          close: async () => {
            const size = chunks.reduce((total, chunk) => total + chunk.length, 0);
            installed = new Uint8Array(size);
            let offset = 0;
            for (const chunk of chunks) {
              installed.set(chunk, offset);
              offset += chunk.length;
            }
          },
          abort: async () => {},
        };
      }),
      getFile: vi.fn(async () => {
        installedFile = new BoundedFile(installed);
        return installedFile;
      }),
      move: vi.fn(async (name: string) => {
        expect(name).toBe(expectedName);
        promoted = true;
      }),
    };
    const managedDirectory = {
      getFileHandle: vi.fn(async (name: string, options?: {create?: boolean}) => {
        if (options?.create === true && name.startsWith(".perform-staging-")) {
          return destination;
        }
        if (name === expectedName && promoted) return destination;
        throw new DOMException("missing", "NotFoundError");
      }),
      removeEntry: vi.fn(async (_name: string) => {}),
    };
    const storage = new OpfsPerformanceRecordingStorage(
      {removeEntry: vi.fn(async () => {})} as never,
      managedDirectory as never,
    );
    const artifact = {
      sha256: expectedName.slice(0, -4),
      mediaType: "audio/wav" as const,
      byteLength: largeWav.length,
    };

    await expect(storage.installManaged(artifact, {
      name: "temp.wav",
      getFile: async () => source as never,
    })).resolves.toBe(destination);
    expect(Buffer.compare(
      Buffer.from(installed.buffer, installed.byteOffset, installed.byteLength),
      Buffer.from(largeWav.buffer, largeWav.byteOffset, largeWav.byteLength),
    )).toBe(0);
    expect(source.wholeReads).toBe(0);
    expect(Math.max(...source.reads)).toBeLessThanOrEqual(MAX_CHUNK_BYTES);
    expect(Math.max(...writeSizes)).toBeLessThanOrEqual(MAX_CHUNK_BYTES);
    expect(installedFile).not.toBeNull();
    expect(destination.getFile).toHaveBeenCalledTimes(1);
    expect(installedFile!.wholeReads).toBe(0);
    expect(Math.max(...installedFile!.reads)).toBeLessThanOrEqual(MAX_CHUNK_BYTES);
  });

  test("reuses an existing valid digest target without writing or removing it", async () => {
    const sha256 = createHash("sha256").update(wav).digest("hex");
    const existing = {
      name: `${sha256}.wav`,
      getFile: vi.fn(async () => new BoundedFile(wav)),
      createWritable: vi.fn(),
    };
    const managedDirectory = {
      getFileHandle: vi.fn(async (name: string, options?: {create?: boolean}) => {
        expect(name).toBe(`${sha256}.wav`);
        expect(options?.create).not.toBe(true);
        return existing;
      }),
      removeEntry: vi.fn(),
    };
    const storage = new OpfsPerformanceRecordingStorage(
      {removeEntry: vi.fn()} as never,
      managedDirectory as never,
    );

    await expect(storage.installManaged({
      sha256, mediaType: "audio/wav", byteLength: wav.length,
    }, {name: "temp.wav", getFile: async () => new BoundedFile(wav)} as never))
      .resolves.toBe(existing);
    expect(existing.createWritable).not.toHaveBeenCalled();
    expect(managedDirectory.removeEntry).not.toHaveBeenCalled();
  });

  test("fails closed on an invalid existing digest target without overwrite or deletion", async () => {
    const sha256 = createHash("sha256").update(wav).digest("hex");
    const invalid = wav.slice();
    invalid[44] = 127;
    const existing = {
      name: `${sha256}.wav`,
      getFile: vi.fn(async () => new BoundedFile(invalid)),
      createWritable: vi.fn(),
    };
    const managedDirectory = {
      getFileHandle: vi.fn(async () => existing),
      removeEntry: vi.fn(),
    };
    const storage = new OpfsPerformanceRecordingStorage(
      {removeEntry: vi.fn()} as never,
      managedDirectory as never,
    );

    await expect(storage.installManaged({
      sha256, mediaType: "audio/wav", byteLength: wav.length,
    }, {name: "temp.wav", getFile: async () => new BoundedFile(wav)} as never))
      .rejects.toThrow("existing managed performance recording");
    expect(existing.createWritable).not.toHaveBeenCalled();
    expect(managedDirectory.removeEntry).not.toHaveBeenCalled();
  });

  test("a new install verification failure removes only its unique staging entry", async () => {
    const sha256 = createHash("sha256").update(wav).digest("hex");
    const stagingBytes = wav.slice();
    stagingBytes[44] = 88;
    const staging = {
      name: ".perform-staging-test.wav",
      createWritable: vi.fn(async () => ({
        write: vi.fn(), close: vi.fn(), abort: vi.fn(),
      })),
      getFile: vi.fn(async () => new BoundedFile(stagingBytes)),
      move: vi.fn(),
    };
    const managedDirectory = {
      getFileHandle: vi.fn(async (name: string, options?: {create?: boolean}) => {
        if (options?.create === true && name.startsWith(".perform-staging-")) {
          return staging;
        }
        throw new DOMException("missing", "NotFoundError");
      }),
      removeEntry: vi.fn(async (_name: string) => {}),
    };
    const storage = new OpfsPerformanceRecordingStorage(
      {removeEntry: vi.fn()} as never,
      managedDirectory as never,
    );

    await expect(storage.installManaged({
      sha256, mediaType: "audio/wav", byteLength: wav.length,
    }, {name: "temp.wav", getFile: async () => new BoundedFile(wav)} as never))
      .rejects.toThrow("verification failed");
    expect(managedDirectory.removeEntry).toHaveBeenCalledTimes(1);
    expect(managedDirectory.removeEntry.mock.calls[0]?.[0]).toMatch(
      /^\.perform-staging-/,
    );
    expect(managedDirectory.removeEntry).not.toHaveBeenCalledWith(`${sha256}.wav`);
    expect(staging.move).not.toHaveBeenCalled();
  });

  test("source open failure after staging creation removes only that staging entry", async () => {
    const sha256 = createHash("sha256").update(wav).digest("hex");
    const targetName = `${sha256}.wav`;
    const staging = {
      name: ".perform-staging-source-failure.wav",
      createWritable: vi.fn(),
    };
    const managedDirectory = {
      getFileHandle: vi.fn(async (name: string, options?: {create?: boolean}) => {
        if (options?.create === true && name.startsWith(".perform-staging-")) {
          return staging;
        }
        throw new DOMException("missing", "NotFoundError");
      }),
      removeEntry: vi.fn(async (_name: string) => {}),
    };
    const storage = new OpfsPerformanceRecordingStorage(
      {removeEntry: vi.fn()} as never,
      managedDirectory as never,
    );

    await expect(storage.installManaged({
      sha256, mediaType: "audio/wav", byteLength: wav.length,
    }, {
      name: "temp.wav",
      getFile: async () => { throw new Error("source unavailable"); },
    } as never)).rejects.toThrow("source unavailable");

    expect(staging.createWritable).not.toHaveBeenCalled();
    expect(managedDirectory.removeEntry).toHaveBeenCalledTimes(1);
    expect(managedDirectory.removeEntry.mock.calls[0]?.[0]).toMatch(
      /^\.perform-staging-/,
    );
    expect(managedDirectory.removeEntry).not.toHaveBeenCalledWith(targetName);
  });

  test("serializes concurrent installs so only one staging file can claim a digest name", async () => {
    const sha256 = createHash("sha256").update(wav).digest("hex");
    const targetName = `${sha256}.wav`;
    let stagingCreated = 0;
    let promoted: object | null = null;
    const moves: string[] = [];
    const managedDirectory = {
      getFileHandle: vi.fn(async (name: string, options?: {create?: boolean}) => {
        if (name === targetName) {
          if (promoted !== null) return promoted;
          if (stagingCreated > 0) {
            await new Promise((resolve) => setTimeout(resolve, 0));
            if (promoted !== null) return promoted;
          }
          throw new DOMException("missing", "NotFoundError");
        }
        if (options?.create === true && name.startsWith(".perform-staging-")) {
          stagingCreated += 1;
          const handle = {
            name,
            createWritable: vi.fn(async () => ({
              write: vi.fn(), close: vi.fn(), abort: vi.fn(),
            })),
            getFile: vi.fn(async () => new BoundedFile(wav)),
            move: vi.fn(async (nextName: string) => {
              moves.push(nextName);
              promoted = handle;
            }),
          };
          return handle;
        }
        throw new DOMException("missing", "NotFoundError");
      }),
      removeEntry: vi.fn(async (_name: string) => {}),
    };
    const storage = new OpfsPerformanceRecordingStorage(
      {removeEntry: vi.fn()} as never,
      managedDirectory as never,
    );
    const artifact = {sha256, mediaType: "audio/wav" as const, byteLength: wav.length};
    const source = {name: "temp.wav", getFile: async () => new BoundedFile(wav)};

    const [first, second] = await Promise.all([
      storage.installManaged(artifact, source as never),
      storage.installManaged(artifact, source as never),
    ]);

    expect(first).toBe(second);
    expect(stagingCreated).toBe(1);
    expect(moves).toEqual([targetName]);
    expect(managedDirectory.removeEntry).not.toHaveBeenCalledWith(targetName);
  });
});
