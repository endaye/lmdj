import {describe, expect, test} from "vitest";

import {
  CAPTURE_FILE_NAME,
  cancelSamplePreviewJourney,
  captureCommitJourney,
  commitSampleDraft,
  importAssignSampleJourney,
  inspectSampleJourney,
  previewSampleDraftJourney,
  queryWaveformJourney,
  resetSampleJourney,
  retryPrepareJourney,
  updateSampleJourney,
} from "../src/runtime/sample_actions";
import {COMMIT_MAX_FRAMES, CaptureBuffer} from "../src/capture/capture_buffer";
import {encodePcm16Wav} from "../src/capture/wav_encoder";
import type {
  CreatorSampleRuntimeSession,
  RuntimeHostState,
  RuntimeOutcome,
  RuntimeVoiceState,
  SampleCommit,
  TransferProgress,
  SampleInspect,
  SnapshotPublication,
  WaveformEnvelope,
} from "../src/runtime/runtime_types";
import {
  beginSampleDraft,
  updateSampleDraft,
} from "../src/state/sample_state";

const playback = Object.freeze({
  trimStartFrame: 10,
  trimEndFrame: 900,
  triggerMode: "gate" as const,
  gainMillidb: -1_200,
  muted: false,
});

const inspect: SampleInspect = Object.freeze({
  projectRevision: 42,
  slot: 17,
  assetId: "11111111-1111-4111-8111-111111111111",
  playback,
  metadata: Object.freeze({
    sampleRate: 48_000,
    channels: 2,
    sourceFrames: 1_000,
  }),
  waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/2`,
});

const waveform: WaveformEnvelope = Object.freeze({
  metadata: inspect.metadata!,
  algorithmVersion: 1,
  buckets: Object.freeze([
    Object.freeze({startFrame: 0, endFrame: 500, peakMagnitude: 32_768}),
    Object.freeze({startFrame: 500, endFrame: 1_000, peakMagnitude: 12}),
  ]),
  projectRevision: 42,
});

const published: SampleCommit = Object.freeze({
  committedRevision: 43,
  runtimeRevision: 43,
  runtimePublished: true,
  snapshotError: null,
});

const retried: SnapshotPublication = Object.freeze({
  projectId: "22222222-2222-4222-8222-222222222222",
  projectRevision: 43,
  patternId: "33333333-3333-4333-8333-333333333333",
  runtimeReady: true,
  generation: 8,
  snapshotError: null,
  runtimeRevision: 43,
});

function fixture() {
  const calls: Array<{method: string; arguments: readonly unknown[]}> = [];
  const session: CreatorSampleRuntimeSession = {
    start: async () => true,
    close: async () => true,
    listLocalProjects: async () => [],
    importProject: async () => { throw new Error("unused"); },
    openProject: async () => ({}),
    inspectProject: async () => ({}),
    reloadSnapshot: async () => ({}),
    activateAudio: async () => true,
    suspendAudio: async () => true,
    trigger: async () => false,
    requestMidi: async () => true,
    subscribeDiagnostics: () => () => {},
    subscribeHostState: (_listener: (state: RuntimeHostState) => void) => () => {},
    subscribeRuntimeOutcome: (_listener: (outcome: RuntimeOutcome) => void) => () => {},
    diagnostics: () => ({
      state: "running",
      error_code: null,
      error_details: {},
      product_build: "1.0.16.3",
      host_id: "creator-web",
      host_version: "1.0.2",
      platform_version: "0.1.2",
      protocol_version: 1,
      capabilities: {
        secureContext: true, crossOriginIsolated: true, sharedArrayBuffer: true,
        webAssembly: true, audioWorklet: true, opfs: true,
        opfsSyncAccessHandle: true, opfsWritableReplace: true, webMidi: false,
      },
      trigger_admitted_count: 0,
      trigger_outcome_count: 0,
      trigger_rejected_count: 0,
    }),
    async inspectSample(slot) {
      calls.push({method: "inspectSample", arguments: [slot]});
      return inspect;
    },
    async queryWaveform(request) {
      calls.push({method: "queryWaveform", arguments: [request]});
      return waveform;
    },
    async importAssignSample(file, options) {
      calls.push({method: "importAssignSample", arguments: [file, options]});
      return published;
    },
    async updatePad(request) {
      calls.push({method: "updatePad", arguments: [request]});
      return published;
    },
    async resetPad(request) {
      calls.push({method: "resetPad", arguments: [request]});
      return published;
    },
    async setSamplePreview(slot, value) {
      calls.push({method: "setSamplePreview", arguments: [slot, value]});
      return true;
    },
    async clearSamplePreview(slot) {
      calls.push({method: "clearSamplePreview", arguments: [slot]});
      return true;
    },
    async release(slot, source) {
      calls.push({method: "release", arguments: [slot, source]});
      return true;
    },
    async stopPad(slot) {
      calls.push({method: "stopPad", arguments: [slot]});
      return true;
    },
    async stopAll() {
      calls.push({method: "stopAll", arguments: []});
      return true;
    },
    async retryPrepare(patternId) {
      calls.push({method: "retryPrepare", arguments: [patternId]});
      return retried;
    },
    subscribeVoiceState(_listener: (event: RuntimeVoiceState) => void) {
      calls.push({method: "subscribeVoiceState", arguments: []});
      return () => true;
    },
  };
  return {calls, session};
}

function expectProtocolMismatch(promise: Promise<unknown>) {
  return expect(promise).rejects.toMatchObject({code: "HOST_PROTOCOL_MISMATCH"});
}

describe("Creator Sample actions", () => {
  test("validates and freezes authoritative inspect and waveform journeys", async () => {
    const {calls, session} = fixture();
    const inspected = await inspectSampleJourney(session, 17);
    const envelope = await queryWaveformJourney(session, {
      slot: 17,
      window: {startFrame: 0, endFrame: 1_000, bucketCount: 2},
    });

    expect(inspected).toEqual(inspect);
    expect(Object.isFrozen(inspected)).toBe(true);
    expect(envelope).toEqual(waveform);
    expect(Object.isFrozen(envelope.buckets)).toBe(true);
    expect(calls.map(({method}) => method)).toEqual([
      "inspectSample",
      "queryWaveform",
    ]);
  });

  test("rejects malformed inspect truth before it reaches Creator state", async () => {
    const invalid = [
      {...inspect, projectRevision: Number.MAX_SAFE_INTEGER + 1},
      {...inspect, playback: {...playback, triggerMode: "invalid"}},
      {...inspect, waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/3`},
      {...inspect, projectPath: "/private/project.lmdj"},
      {...inspect, sourceFileName: "kick.wav"},
      {...inspect, sampleBytes: new Uint8Array([1, 2, 3])},
    ];
    for (const response of invalid) {
      const {session} = fixture();
      session.inspectSample = async () => response as never;
      await expectProtocolMismatch(inspectSampleJourney(session, 17));
    }
  });

  test("rejects noncanonical and privacy-bearing waveform responses", async () => {
    const invalid = [
      {...waveform, algorithmVersion: 2},
      {...waveform, buckets: [
        {startFrame: 0, endFrame: 499, peakMagnitude: 1},
        {startFrame: 499, endFrame: 1_000, peakMagnitude: 2},
      ]},
      {...waveform, buckets: [
        {startFrame: 0, endFrame: 500, peakMagnitude: 32_769},
        {startFrame: 500, endFrame: 1_000, peakMagnitude: 2},
      ]},
      {...waveform, fileName: "private.wav"},
    ];
    for (const response of invalid) {
      const {session} = fixture();
      session.queryWaveform = async () => response as never;
      await expectProtocolMismatch(queryWaveformJourney(session, {
        slot: 17,
        window: {startFrame: 0, endFrame: 1_000, bucketCount: 2},
      }));
    }
  });

  test("accepts the canonical 512-bucket waveform contract maximum", async () => {
    const {session} = fixture();
    const sourceFrames = 512;
    session.queryWaveform = async () => ({
      metadata: {...inspect.metadata!, sourceFrames},
      algorithmVersion: 1,
      buckets: Array.from({length: 512}, (_, startFrame) => ({
        startFrame,
        endFrame: startFrame + 1,
        peakMagnitude: startFrame % 32_769,
      })),
      projectRevision: 42,
    });
    const result = await queryWaveformJourney(session, {
      slot: 17,
      window: {startFrame: 0, endFrame: sourceFrames, bucketCount: 512},
    });
    expect(result.buckets).toHaveLength(512);
  });

  test("previews a complete draft and cancellation creates no Authoring mutation", async () => {
    const {calls, session} = fixture();
    const draft = updateSampleDraft(beginSampleDraft(playback, 42), {
      trimStartFrame: 120,
    });

    expect(await previewSampleDraftJourney(session, 17, draft)).toBe(true);
    expect(await cancelSamplePreviewJourney(session, 17)).toBe(true);
    expect(calls).toEqual([
      {method: "setSamplePreview", arguments: [17, draft.proposed]},
      {method: "clearSamplePreview", arguments: [17]},
    ]);
  });

  test("fails closed and clears preview when Runtime rejects preview admission", async () => {
    const {calls, session} = fixture();
    session.setSamplePreview = async (slot, value) => {
      calls.push({method: "setSamplePreview", arguments: [slot, value]});
      return false;
    };
    const draft = updateSampleDraft(beginSampleDraft(playback, 42), {
      trimStartFrame: 120,
    });

    await expect(previewSampleDraftJourney(session, 17, draft)).rejects.toMatchObject({
      code: "HOST_STATE_INVALID",
      message: "Runtime preview failed",
    });
    expect(calls).toEqual([
      {method: "setSamplePreview", arguments: [17, draft.proposed]},
      {method: "clearSamplePreview", arguments: [17]},
    ]);
  });

  test("rejects missing complete playback in preview and update inputs", async () => {
    const {session} = fixture();
    const draft = beginSampleDraft(playback, 42);
    await expect(previewSampleDraftJourney(session, 17, {
      ...draft,
      proposed: undefined,
    } as never)).rejects.toThrow("Sample playback is invalid");
    expect(() => updateSampleJourney(session, {
      slot: 17,
      expectedRevision: 42,
      playback: undefined,
    } as never)).toThrow("Sample playback is invalid");
  });

  test("commits exactly one complete playback on release and clears preview", async () => {
    const {calls, session} = fixture();
    const draft = updateSampleDraft(beginSampleDraft(playback, 42), {
      trimStartFrame: 120,
    });
    const refreshed = {
      ...inspect,
      projectRevision: 43,
      playback: draft.proposed,
    };
    session.inspectSample = async (slot) => {
      calls.push({method: "inspectSample", arguments: [slot]});
      return refreshed;
    };

    const result = await commitSampleDraft(session, 17, draft);
    expect(result).toEqual({kind: "committed", commit: published, inspect: refreshed});
    expect(calls).toEqual([
      {
        method: "updatePad",
        arguments: [{
          slot: 17,
          expectedRevision: 42,
          playback: {...playback, trimStartFrame: 120},
        }],
      },
      {method: "clearSamplePreview", arguments: [17]},
      {method: "inspectSample", arguments: [17]},
    ]);
  });

  test.each(["preview-clear", "inspect"] as const)(
    "preserves the committed receipt when %s settlement fails",
    async (failure) => {
      const {calls, session} = fixture();
      if (failure === "preview-clear") {
        session.clearSamplePreview = async (slot) => {
          calls.push({method: "clearSamplePreview", arguments: [slot]});
          throw Object.assign(new Error("late cleanup"), {code: "HOST_TIMEOUT"});
        };
      } else {
        session.inspectSample = async (slot) => {
          calls.push({method: "inspectSample", arguments: [slot]});
          throw Object.assign(new Error("late refresh"), {code: "HOST_TIMEOUT"});
        };
      }

      await expect(updateSampleJourney(session, {
        slot: 17,
        expectedRevision: 42,
        playback,
      })).resolves.toEqual({
        kind: "committed",
        commit: published,
        inspect: null,
      });
      expect(calls.at(0)?.method).toBe("updatePad");
    },
  );

  test("never retries a revision conflict and refreshes after clearing preview", async () => {
    const {calls, session} = fixture();
    session.updatePad = async (request) => {
      calls.push({method: "updatePad", arguments: [request]});
      throw Object.assign(new Error("stale"), {code: "REVISION_CONFLICT"});
    };
    session.inspectSample = async (slot) => {
      calls.push({method: "inspectSample", arguments: [slot]});
      return {...inspect, projectRevision: 44};
    };
    const draft = updateSampleDraft(beginSampleDraft(playback, 42), {
      muted: true,
    });

    const result = await commitSampleDraft(session, 17, draft);
    expect(result).toEqual({
      kind: "conflict",
      inspect: {...inspect, projectRevision: 44},
      message: "Project changed; review and try again",
    });
    expect(calls.map(({method}) => method)).toEqual([
      "updatePad",
      "clearSamplePreview",
      "inspectSample",
    ]);
  });

  test("preserves valid Cook-failed publication truth and rejects impossible results", async () => {
    const {session} = fixture();
    const cookFailed = {
      committedRevision: 43,
      runtimeRevision: 42,
      runtimePublished: false,
      snapshotError: {
        code: "COOK_FAILED",
        message: "Sample runtime preparation failed",
        details: {},
      },
    };
    session.updatePad = async () => cookFailed;
    const refreshed = {...inspect, projectRevision: 43};
    session.inspectSample = async () => refreshed;
    expect(await updateSampleJourney(session, {
      slot: 17,
      expectedRevision: 42,
      playback,
    })).toEqual({kind: "committed", commit: cookFailed, inspect: refreshed});

    const invalid = [
      {...published, committedRevision: Number.MAX_SAFE_INTEGER + 1},
      {...published, runtimeRevision: null},
      {...published, runtimeRevision: 42},
      {...published, snapshotError: cookFailed.snapshotError},
      {...published, projectPath: "/private/project.lmdj"},
      {
        ...cookFailed,
        snapshotError: {...cookFailed.snapshotError, details: {path: "/private"}},
      },
      {
        ...cookFailed,
        snapshotError: {
          ...cookFailed.snapshotError,
          details: {payload: new ArrayBuffer(8)},
        },
      },
      {
        ...cookFailed,
        snapshotError: {
          ...cookFailed.snapshotError,
          details: {payload: [new Uint8Array([1])]},
        },
      },
      {
        ...cookFailed,
        snapshotError: {
          ...cookFailed.snapshotError,
          details: {payload: new File(["private"], "secret.wav")},
        },
      },
      {
        ...cookFailed,
        snapshotError: {
          ...cookFailed.snapshotError,
          details: {payload: new Date(0)},
        },
      },
      {
        ...cookFailed,
        snapshotError: {
          ...cookFailed.snapshotError,
          details: {
            nested: {
              AbsolutePath: "/private/project",
              projectJSON: {revision: 42},
              audioBytes: [82, 73, 70, 70],
              OPFSHandle: "private-handle",
            },
          },
        },
      },
      {
        ...cookFailed,
        snapshotError: {
          ...cookFailed.snapshotError,
          details: {
            payload: {
              contract: "lmdj.project.v2",
              revision: 1,
              banks: [],
              assets: {},
            },
          },
        },
      },
    ];
    for (const response of invalid) {
      const value = fixture();
      value.session.resetPad = async () => response as never;
      value.session.inspectSample = async () => ({...inspect, projectRevision: 43});
      await expectProtocolMismatch(resetSampleJourney(value.session, {
        slot: 17,
        expectedRevision: 42,
      }));
    }
  });

  test("accepts only exact public snapshot detail shapes and normalizes Host messages", async () => {
    const publicDetails: readonly Readonly<Record<string, unknown>>[] = [
      {},
      {actual_revision: 43, expected_revision: 42},
      ...[
        "artifact_bytes",
        "decoded_frames_per_pad",
        "prepared_bank_bytes",
        "live_bank_bytes",
      ].map((resource) => ({resource, observed: 1_048_576, limit: 524_288})),
      ...[
        "project_busy",
        "already_exists",
        "atomic_publish_unsupported",
      ].map((storage_condition) => ({storage_condition})),
      {transfer_condition: "resource_limit"},
    ];

    for (const details of publicDetails) {
      const {session} = fixture();
      session.resetPad = async () => ({
        committedRevision: 43,
        runtimeRevision: 42,
        runtimePublished: false,
        snapshotError: {
          code: "COOK_FAILED",
          message: "opaque Host wording",
          details,
        },
      });
      session.inspectSample = async () => ({...inspect, projectRevision: 43});

      const result = await resetSampleJourney(session, {
        slot: 17,
        expectedRevision: 42,
      });
      expect(result.kind).toBe("committed");
      if (result.kind === "committed") {
        expect(result.commit.snapshotError).toEqual({
          code: "COOK_FAILED",
          message: "Sample runtime preparation failed",
          details,
        });
        expect(Object.isFrozen(result.commit.snapshotError?.details)).toBe(true);
      }
    }
  });

  test("rejects private Host messages and every non-allowlisted snapshot detail shape", async () => {
    const privateDetails = [
      {actual_revision: Number.MAX_SAFE_INTEGER + 1, expected_revision: 42},
      {actual_revision: 43, expected_revision: 42, note: "extra"},
      {resource: "unknown_resource", observed: 2, limit: 1},
      {resource: "artifact_bytes", observed: -1, limit: 1},
      {storage_condition: "unknown_condition"},
      {transfer_condition: "unknown_condition"},
      {note: "/private/projects/session.lmdj"},
      {payload: [82, 73, 70, 70]},
      Object.assign(Object.create({inherited: true}), {
        actual_revision: 43,
        expected_revision: 42,
      }),
      {
        contract: "lmdj.project.v2",
        revision: 43,
        banks: [],
        assets: {},
      },
    ];
    const privateMessages = [
      "failed at /private/projects/session.lmdj",
      "OPFS:/projects/secret",
      "could not decode private-kick.wav",
      "failed at C:\\Users\\private\\kick.wav",
    ];

    for (const details of privateDetails) {
      const {session} = fixture();
      session.resetPad = async () => ({
        committedRevision: 43,
        runtimeRevision: 42,
        runtimePublished: false,
        snapshotError: {
          code: "COOK_FAILED",
          message: "Sample runtime preparation failed",
          details,
        },
      });
      session.inspectSample = async () => ({...inspect, projectRevision: 43});
      await expectProtocolMismatch(resetSampleJourney(session, {
        slot: 17,
        expectedRevision: 42,
      }));
    }
    for (const message of privateMessages) {
      const {session} = fixture();
      session.resetPad = async () => ({
        committedRevision: 43,
        runtimeRevision: 42,
        runtimePublished: false,
        snapshotError: {code: "COOK_FAILED", message, details: {}},
      });
      session.inspectSample = async () => ({...inspect, projectRevision: 43});
      await expectProtocolMismatch(resetSampleJourney(session, {
        slot: 17,
        expectedRevision: 42,
      }));
    }
  });

  test("validates import, reset, and retry results without retaining a File name", async () => {
    const {calls, session} = fixture();
    const file = new File(["RIFF"], "private-kick.wav", {type: "audio/wav"});
    const refreshed = {...inspect, projectRevision: 43};
    session.inspectSample = async (slot) => {
      calls.push({method: "inspectSample", arguments: [slot]});
      return refreshed;
    };
    const imported = await importAssignSampleJourney(session, file, {
      slot: 17,
      expectedRevision: 42,
      signal: new AbortController().signal,
      onProgress: () => {},
    });
    const reset = await resetSampleJourney(session, {
      slot: 17,
      expectedRevision: 43,
    });
    const retry = await retryPrepareJourney(
      session,
      "33333333-3333-4333-8333-333333333333",
    );

    expect(imported).toEqual({kind: "committed", commit: published, inspect: refreshed});
    expect(JSON.stringify(imported)).not.toContain(file.name);
    expect(reset).toEqual({kind: "committed", commit: published, inspect: refreshed});
    expect(retry).toEqual(retried);
    expect(calls.map(({method}) => method)).toEqual([
      "importAssignSample",
      "clearSamplePreview",
      "inspectSample",
      "resetPad",
      "clearSamplePreview",
      "inspectSample",
      "retryPrepare",
    ]);
  });

  test("passes a frozen normalized import options copy into the mutation lane", async () => {
    const {session} = fixture();
    const signal = new AbortController().signal;
    const onProgress = (_progress: TransferProgress) => {};
    const options = {slot: 17, expectedRevision: 42, signal, onProgress};
    let observed: typeof options | null = null;
    let receivedOptions: unknown = null;
    session.importAssignSample = async (_file, received) => {
      receivedOptions = received;
      await Promise.resolve();
      observed = {
        slot: received.slot,
        expectedRevision: received.expectedRevision,
        signal: received.signal!,
        onProgress: received.onProgress!,
      };
      return published;
    };
    session.inspectSample = async () => ({...inspect, projectRevision: 43});
    const pending = importAssignSampleJourney(
      session,
      new File(["RIFF"], "private.wav"),
      options,
    );
    options.slot = 3;
    options.expectedRevision = 99;
    await pending;
    expect(receivedOptions).not.toBe(options);
    expect(Object.isFrozen(receivedOptions)).toBe(true);
    expect(observed).toEqual({slot: 17, expectedRevision: 42, signal, onProgress});
  });

  test.each([
    [
      "published",
      {
        committedRevision: 43,
        runtimeRevision: 45,
        runtimePublished: true,
        snapshotError: null,
      },
    ],
    [
      "Cook-failed",
      {
        committedRevision: 43,
        runtimeRevision: 45,
        runtimePublished: false,
        snapshotError: {
          code: "COOK_FAILED",
          message: "Sample runtime preparation failed",
          details: {},
        },
      },
    ],
  ] as const)(
    "refreshes authoritative inspect after a delayed %s replay",
    async (_label, commit) => {
      const {calls, session} = fixture();
      const refreshed = {
        ...inspect,
        projectRevision: 45,
        playback: {...playback, muted: true},
      };
      session.updatePad = async (request) => {
        calls.push({method: "updatePad", arguments: [request]});
        return commit;
      };
      session.inspectSample = async (slot) => {
        calls.push({method: "inspectSample", arguments: [slot]});
        return refreshed;
      };
      expect(await updateSampleJourney(session, {
        slot: 17,
        expectedRevision: 42,
        playback,
      })).toEqual({kind: "committed", commit, inspect: refreshed});
      expect(calls.map(({method}) => method)).toEqual([
        "updatePad",
        "clearSamplePreview",
        "inspectSample",
      ]);
    },
  );

  test("rejects a mutation refresh older than delayed Runtime truth", async () => {
    const {session} = fixture();
    session.updatePad = async () => ({
      committedRevision: 43,
      runtimeRevision: 45,
      runtimePublished: true,
      snapshotError: null,
    });
    session.inspectSample = async () => ({...inspect, projectRevision: 44});
    await expectProtocolMismatch(updateSampleJourney(session, {
      slot: 17,
      expectedRevision: 42,
      playback,
    }));
  });

  test("keeps cancellation authoritative and rejects malformed retry publication", async () => {
    const cancelled = fixture();
    cancelled.session.importAssignSample = async () => {
      cancelled.calls.push({method: "importAssignSample", arguments: []});
      throw new DOMException("cancelled", "AbortError");
    };
    await expect(importAssignSampleJourney(
      cancelled.session,
      new File(["RIFF"], "cancelled.wav"),
      {slot: 17, expectedRevision: 42},
    )).rejects.toMatchObject({name: "AbortError"});
    expect(cancelled.calls.map(({method}) => method)).toEqual([
      "importAssignSample",
    ]);

    const malformed = fixture();
    malformed.session.retryPrepare = async () => ({
      ...retried,
      generation: 0,
      fileName: "private.wav",
    }) as never;
    await expectProtocolMismatch(retryPrepareJourney(
      malformed.session,
      retried.patternId,
    ));
  });
});

describe("captureCommitJourney", () => {
  function captureBuffer(frames: number): CaptureBuffer {
    const buffer = new CaptureBuffer(1);
    buffer.append([Float32Array.from({length: frames}, (_, i) => ((i % 8) + 1) / 8)]);
    return buffer;
  }

  test("encodes the selection and delegates to the unchanged import journey", async () => {
    const {calls, session} = fixture();
    const buffer = captureBuffer(64);
    const refreshed = {...inspect, projectRevision: 43};
    session.inspectSample = async (slot) => {
      calls.push({method: "inspectSample", arguments: [slot]});
      return refreshed;
    };
    const resolution = await captureCommitJourney(
      session,
      buffer,
      {startFrame: 8, frameCount: 16},
      {slot: 17, expectedRevision: 42},
    );

    expect(resolution).toEqual({kind: "committed", commit: published, inspect: refreshed});
    const call = calls.find(({method}) => method === "importAssignSample");
    const [file, options] = (call?.arguments ?? []) as [File, {slot: number; expectedRevision: number}];
    expect(file).toBeInstanceOf(File);
    expect(file.name).toBe(CAPTURE_FILE_NAME);
    expect(file.type).toBe("audio/wav");
    expect(options).toMatchObject({slot: 17, expectedRevision: 42});
    // The delegated bytes are exactly the deterministic encoding of the
    // selected frames — not the whole take.
    const expected = encodePcm16Wav(buffer.slice(8, 16));
    expect(new Uint8Array(await file.arrayBuffer())).toEqual(expected);
  });

  test("reads expectedRevision from the caller at commit time (S8B-D6)", async () => {
    const {calls, session} = fixture();
    // Two commits of the same buffer with different fresh revisions must reach
    // the import session with those exact revisions; nothing is captured at
    // recording time.
    await captureCommitJourney(session, captureBuffer(32), {startFrame: 0, frameCount: 8},
      {slot: 3, expectedRevision: 7});
    await captureCommitJourney(session, captureBuffer(32), {startFrame: 0, frameCount: 8},
      {slot: 3, expectedRevision: 9});
    const revisions = calls
      .filter(({method}) => method === "importAssignSample")
      .map(({arguments: args}) => (args[1] as {expectedRevision: number}).expectedRevision);
    expect(revisions).toEqual([7, 9]);
  });

  test("a conflict retry re-encodes identical bytes under a fresh revision", async () => {
    const {calls, session} = fixture();
    const buffer = captureBuffer(64);
    const selection = {startFrame: 4, frameCount: 24};
    await captureCommitJourney(session, buffer, selection, {slot: 5, expectedRevision: 11});
    await captureCommitJourney(session, buffer, selection, {slot: 5, expectedRevision: 12});
    const files = calls
      .filter(({method}) => method === "importAssignSample")
      .map(({arguments: args}) => args[0] as File);
    const [first, second] = files;
    if (first === undefined || second === undefined) {
      throw new Error("expected two delegated import calls");
    }
    expect(new Uint8Array(await first.arrayBuffer()))
      .toEqual(new Uint8Array(await second.arrayBuffer()));
  });

  test("rejects a selection over COMMIT_MAX_FRAMES or otherwise malformed", async () => {
    const {calls, session} = fixture();
    const buffer = captureBuffer(64);
    await expect(captureCommitJourney(session, buffer,
      {startFrame: 0, frameCount: COMMIT_MAX_FRAMES + 1}, {slot: 1, expectedRevision: 1},
    )).rejects.toThrow(TypeError);
    await expect(captureCommitJourney(session, buffer,
      {startFrame: 0, frameCount: 0}, {slot: 1, expectedRevision: 1},
    )).rejects.toThrow(TypeError);
    await expect(captureCommitJourney(session, buffer,
      {startFrame: -1, frameCount: 8} as never, {slot: 1, expectedRevision: 1},
    )).rejects.toThrow(TypeError);
    await expect(captureCommitJourney(session, buffer,
      {startFrame: 0, frameCount: 8, extra: 1} as never, {slot: 1, expectedRevision: 1},
    )).rejects.toThrow(TypeError);
    // A selection outside the recorded frames is the buffer's RangeError, and
    // it must never reach the Runtime as a half-formed import.
    await expect(captureCommitJourney(session, buffer,
      {startFrame: 60, frameCount: 16}, {slot: 1, expectedRevision: 1},
    )).rejects.toThrow(RangeError);
    expect(calls.some(({method}) => method === "importAssignSample")).toBe(false);
  });
});
