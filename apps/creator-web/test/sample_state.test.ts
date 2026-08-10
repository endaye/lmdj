import {describe, expect, test} from "vitest";

import {
  SAMPLE_VOICE_RENDER_LIMIT,
  applyRuntimeVoiceState,
  applySampleCommit,
  applySampleConflict,
  applySampleRetryPublication,
  beginSamplePending,
  beginSampleDraft,
  cancelSampleDraft,
  fitSampleViewport,
  initialSampleState,
  panSampleViewport,
  projectSamplePlayback,
  reduceSampleState,
  selectSampleSlot,
  storeSampleInspect,
  storeSampleWaveform,
  updateSampleDraft,
  waveformWindowForViewport,
  zoomSampleViewport,
} from "../src/state/sample_state";
import {
  creatorReducer,
  initialCreatorState,
} from "../src/state/creator_state";

const saved = Object.freeze({
  trimStartFrame: 10,
  trimEndFrame: 480,
  triggerMode: "gate" as const,
  gainMillidb: -1_200,
  muted: false,
});

const metadata = Object.freeze({
  sampleRate: 48_000,
  channels: 2,
  sourceFrames: 1_000,
});

const inspect = Object.freeze({
  projectRevision: 42,
  slot: 17,
  assetId: "11111111-1111-4111-8111-111111111111",
  playback: saved,
  metadata,
  waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/2`,
});

function inspectedState() {
  return storeSampleInspect(selectSampleSlot(initialSampleState, 17), inspect);
}

describe("Creator Sample state", () => {
  test("keeps one complete gesture draft on its captured Project revision", () => {
    const draft = beginSampleDraft(saved, 42);
    const moved = updateSampleDraft(draft, {trimStartFrame: 120});

    expect(moved.baseRevision).toBe(42);
    expect(moved.proposed).toEqual({...saved, trimStartFrame: 120});
    expect(moved.dirty).toBe(true);
  });

  test("projects missing v2 playback to the complete v1 defaults", () => {
    expect(projectSamplePlayback(undefined)).toEqual({
      trimStartFrame: 0,
      trimEndFrame: null,
      triggerMode: "one_shot",
      gainMillidb: 0,
      muted: false,
    });
    expect(projectSamplePlayback(saved)).toEqual(saved);
  });

  test("preserves complete nondefault v2 playback on an unassigned Pad", () => {
    const selected = selectSampleSlot(initialSampleState, 17);
    const empty = {
      ...inspect,
      assetId: null,
      playback: saved,
      metadata: null,
      waveformCacheIdentity: null,
    };
    expect(storeSampleInspect(selected, empty).inspect?.playback).toEqual(saved);
  });

  test("stores selected v2 inspect truth and delegates selection through Creator state", () => {
    const selected = selectSampleSlot(initialSampleState, 17);
    expect(selected.selectedSlot).toBe(17);
    expect(selected.inspect).toBeNull();

    const state = storeSampleInspect(selected, inspect);
    expect(state.inspect).toEqual(inspect);
    expect(state.savedRevision).toBe(42);
    expect(state.viewport).toEqual({
      sourceFrames: 1_000,
      startFrame: 0,
      endFrame: 1_000,
    });

    const creator = creatorReducer(initialCreatorState, {
      type: "sample-action",
      action: {type: "slot-selected", slot: 17},
    });
    expect(creator.sample.selectedSlot).toBe(17);
  });

  test("initializes saved and Runtime revision from a prepared Project reopen", () => {
    const prepared = creatorReducer(initialCreatorState, {
      type: "project-ready",
      project: {
        projectId: "11111111-1111-4111-8111-111111111111",
        patternId: "22222222-2222-4222-8222-222222222222",
        revision: 42,
        bpm: 120,
        assetCount: 0,
        assignedPadCount: 0,
        bundleDigest: "a".repeat(64),
        key: "—",
        pads: [],
      },
    });

    expect(prepared.sample.savedRevision).toBe(42);
    expect(prepared.sample.runtimeRevision).toBe(42);
  });

  test("stores one canonical waveform window without duplicating its cache identity", () => {
    const viewport = zoomSampleViewport(fitSampleViewport(1_000), 2, 500);
    const window = waveformWindowForViewport(viewport, 2);
    const envelope = {
      metadata,
      algorithmVersion: 1,
      buckets: [
        {startFrame: 250, endFrame: 500, peakMagnitude: 32_768},
        {startFrame: 500, endFrame: 750, peakMagnitude: 12},
      ],
      projectRevision: 42,
    };

    const state = storeSampleWaveform(
      {...inspectedState(), viewport},
      envelope,
      {
        slot: 17,
        window,
        waveformCacheIdentity: inspect.waveformCacheIdentity,
      },
    );
    expect(state.waveform).toEqual(envelope);
    expect(state.inspect?.waveformCacheIdentity).toBe(
      `${"a".repeat(64)}/1/max-abs-mirror/2`,
    );
    expect(Object.keys(state)).not.toContain("waveformCache");
  });

  test("rejects a waveform response issued for a previously selected Pad", () => {
    const window = waveformWindowForViewport(fitSampleViewport(1_000), 2);
    const envelope = {
      metadata,
      algorithmVersion: 1,
      buckets: [
        {startFrame: 0, endFrame: 500, peakMagnitude: 100},
        {startFrame: 500, endFrame: 1_000, peakMagnitude: 200},
      ],
      projectRevision: 42,
    };
    const nextInspect = {
      ...inspect,
      slot: 18,
      assetId: "22222222-2222-4222-8222-222222222222",
      waveformCacheIdentity: `${"b".repeat(64)}/1/max-abs-mirror/2`,
    };
    const nextSelection = storeSampleInspect(
      selectSampleSlot(inspectedState(), 18),
      nextInspect,
    );

    expect(() => storeSampleWaveform(nextSelection, envelope, {
      slot: 17,
      window,
      waveformCacheIdentity: inspect.waveformCacheIdentity,
    })).toThrow(
      "Sample waveform truth does not match selection",
    );
  });

  test("accepts the canonical 512-bucket waveform contract maximum", () => {
    const sourceFrames = 512;
    const largeMetadata = {...metadata, sourceFrames};
    const largeInspect = {
      ...inspect,
      metadata: largeMetadata,
      waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/1`,
    };
    const state = storeSampleInspect(
      selectSampleSlot(initialSampleState, 17),
      largeInspect,
    );
    const window = {startFrame: 0, endFrame: sourceFrames, bucketCount: 512};
    const envelope = {
      metadata: largeMetadata,
      algorithmVersion: 1,
      buckets: Array.from({length: 512}, (_, startFrame) => ({
        startFrame,
        endFrame: startFrame + 1,
        peakMagnitude: startFrame % 32_769,
      })),
      projectRevision: 42,
    };
    expect(storeSampleWaveform(state, envelope, {
      slot: 17,
      window,
      waveformCacheIdentity: largeInspect.waveformCacheIdentity,
    }).waveform?.buckets).toHaveLength(512);
  });

  test("fits, zooms, and pans only within source-frame bounds", () => {
    const fit = fitSampleViewport(1_000);
    expect(fit).toEqual({sourceFrames: 1_000, startFrame: 0, endFrame: 1_000});
    const zoomed = zoomSampleViewport(fit, 2, 500);
    expect(zoomed).toEqual({sourceFrames: 1_000, startFrame: 250, endFrame: 750});
    expect(panSampleViewport(zoomed, 400)).toEqual({
      sourceFrames: 1_000,
      startFrame: 500,
      endFrame: 1_000,
    });
    expect(panSampleViewport(zoomed, -1_000)).toEqual({
      sourceFrames: 1_000,
      startFrame: 0,
      endFrame: 500,
    });
    expect(zoomSampleViewport(zoomed, 0.01, 500)).toEqual(fit);
    expect(() => fitSampleViewport(Number.MAX_SAFE_INTEGER + 1)).toThrow();
    expect(() => waveformWindowForViewport(fit, 513)).toThrow();
  });

  test("keeps discrete pending state separate from a gesture draft", () => {
    const draft = beginSampleDraft(saved, 42);
    const state = beginSamplePending(
      {...inspectedState(), draft},
      {kind: "update", slot: 17, expectedRevision: 42},
    );
    expect(state.draft).toBe(draft);
    expect(state.pendingAction).toEqual({
      kind: "update",
      slot: 17,
      expectedRevision: 42,
    });

    const cancelled = cancelSampleDraft(state);
    expect(cancelled.draft).toBeNull();
    expect(cancelled.pendingAction).toEqual(state.pendingAction);
    expect(cancelled.savedRevision).toBe(42);
  });

  test("keeps project-wide pending and Cook retry truth across Pad selection", () => {
    const pending = beginSamplePending(inspectedState(), {
      kind: "update",
      slot: 17,
      expectedRevision: 42,
    });
    expect(selectSampleSlot(pending, 18).pendingAction).toEqual(
      pending.pendingAction,
    );

    const committing = beginSamplePending(
      {...inspectedState(), runtimeRevision: 42},
      {kind: "update", slot: 17, expectedRevision: 42},
    );
    const failed = applySampleCommit(
      committing,
      committing.pendingAction,
      {...inspect, projectRevision: 43},
      {
        committedRevision: 43,
        runtimeRevision: 42,
        runtimePublished: false,
        snapshotError: {
          code: "COOK_FAILED",
          message: "Sample runtime preparation failed",
          details: {},
        },
      },
    );
    const selected = selectSampleSlot(failed, 18);
    expect(selected.lastError).toEqual(failed.lastError);
    const reInspected = storeSampleInspect(selected, {
      ...inspect,
      projectRevision: 43,
      slot: 18,
      assetId: "22222222-2222-4222-8222-222222222222",
    });
    expect(reInspected.lastError).toEqual(failed.lastError);
    expect(reInspected.savedRevision).toBe(43);
    expect(reInspected.runtimeRevision).toBe(42);
  });

  test("preserves saved truth and the older Runtime revision on Cook failure", () => {
    const draft = updateSampleDraft(beginSampleDraft(saved, 42), {
      trimStartFrame: 120,
    });
    const pending = beginSamplePending(
      {...inspectedState(), draft, runtimeRevision: 42},
      {kind: "update", slot: 17, expectedRevision: 42},
    );
    const state = applySampleCommit(pending, pending.pendingAction, {
      ...inspect,
      projectRevision: 43,
      playback: draft.proposed,
    }, {
      committedRevision: 43,
      runtimeRevision: 42,
      runtimePublished: false,
      snapshotError: {
        code: "COOK_FAILED",
        message: "Sample runtime preparation failed",
        details: {},
      },
    });

    expect(state.inspect?.playback.trimStartFrame).toBe(120);
    expect(state.savedRevision).toBe(43);
    expect(state.runtimeRevision).toBe(42);
    expect(state.draft).toBeNull();
    expect(state.pendingAction).toBeNull();
    expect(state.lastError).toEqual({
      code: "COOK_FAILED",
      message: "Sample runtime preparation failed",
      retryPrepare: true,
    });

    const retrying = beginSamplePending(state, {
      kind: "retry-prepare",
      slot: 17,
      expectedRevision: 43,
    });
    const recovered = applySampleRetryPublication(
      retrying,
      retrying.pendingAction,
      {
      projectId: "22222222-2222-4222-8222-222222222222",
      projectRevision: 43,
      patternId: "33333333-3333-4333-8333-333333333333",
      runtimeReady: true,
      generation: 8,
      snapshotError: null,
      runtimeRevision: 43,
      },
    );
    expect(recovered.savedRevision).toBe(43);
    expect(recovered.runtimeRevision).toBe(43);
    expect(recovered.pendingAction).toBeNull();
    expect(recovered.lastError).toBeNull();
  });

  test("refreshes authoritative truth after a delayed Runtime replay", () => {
    const refreshed = {
      ...inspect,
      projectRevision: 45,
      playback: {...saved, muted: true},
    };
    const pending = beginSamplePending(inspectedState(), {
      kind: "update",
      slot: 17,
      expectedRevision: 42,
    });
    const state = applySampleCommit(pending, pending.pendingAction, refreshed, {
      committedRevision: 43,
      runtimeRevision: 45,
      runtimePublished: true,
      snapshotError: null,
    });
    expect(state.inspect).toEqual(refreshed);
    expect(state.savedRevision).toBe(45);
    expect(state.runtimeRevision).toBe(45);
    expect(state.lastError).toBeNull();
  });

  test("refreshes authoritative truth on conflict without retaining the draft", () => {
    const draft = updateSampleDraft(beginSampleDraft(saved, 42), {
      gainMillidb: -2_400,
    });
    const pending = beginSamplePending(
      {...inspectedState(), draft, runtimeRevision: 41},
      {kind: "update", slot: 17, expectedRevision: 42},
    );
    const refreshed = applySampleConflict(pending, pending.pendingAction, {
      ...inspect,
      projectRevision: 44,
      playback: {...saved, muted: true},
    });
    expect(refreshed.savedRevision).toBe(44);
    expect(refreshed.runtimeRevision).toBe(41);
    expect(refreshed.draft).toBeNull();
    expect(refreshed.pendingAction).toBeNull();
    expect(refreshed.lastError).toEqual({
      code: "REVISION_CONFLICT",
      message: "Project changed; review and try again",
      retryPrepare: false,
    });
  });

  test("reduces bounded inspect, waveform, draft, and Voice actions", () => {
    let state = reduceSampleState(initialSampleState, {
      type: "slot-selected",
      slot: 17,
    });
    state = reduceSampleState(state, {type: "inspect-stored", inspect});
    state = reduceSampleState(state, {
      type: "waveform-stored",
      envelope: {
        metadata,
        algorithmVersion: 1,
        buckets: [{startFrame: 0, endFrame: 1_000, peakMagnitude: 12}],
        projectRevision: 42,
      },
      request: {
        slot: 17,
        window: {startFrame: 0, endFrame: 1_000, bucketCount: 1},
        waveformCacheIdentity: inspect.waveformCacheIdentity,
      },
    });
    state = reduceSampleState(state, {type: "draft-began"});
    state = reduceSampleState(state, {
      type: "draft-updated",
      changes: {trimStartFrame: 120},
    });
    state = reduceSampleState(state, {
      type: "preview-applied",
      playback: state.draft?.proposed,
    } as never);
    state = reduceSampleState(state, {
      type: "voice-changed",
      event: {
        sequence: 1,
        slot: 17,
        state: "started",
        runtimeFrame: 128,
        sourceFrame: 50,
      },
    });
    expect(state.waveform?.buckets).toHaveLength(1);
    expect(state.draft?.proposed.trimStartFrame).toBe(120);
    expect(state.playhead?.sourceFrame).toBe(120);
    state = reduceSampleState(state, {type: "draft-cancelled"});
    expect(state.draft).toBeNull();
    expect(state.auditionPlayback).toBeNull();
    expect(() => reduceSampleState(state, {
      type: "draft-cancelled",
      extra: true,
    } as never)).toThrow("Sample state action is invalid");

    const creator = creatorReducer(initialCreatorState, {
      type: "sample-action",
      action: {type: "slot-selected", slot: 17},
    } as never);
    expect(creator.sample.selectedSlot).toBe(17);
  });

  test("stores only accepted preview playback and clears it at exact boundaries", () => {
    let state = reduceSampleState(inspectedState(), {type: "draft-began"});
    state = reduceSampleState(state, {
      type: "draft-updated",
      changes: {triggerMode: "loop_toggle"},
    });
    const accepted = state.draft?.proposed;
    state = reduceSampleState(state, {
      type: "preview-applied",
      playback: accepted,
    } as never);
    expect(state.auditionPlayback).toEqual(accepted);

    state = reduceSampleState(state, {
      type: "draft-updated",
      changes: {triggerMode: "one_shot"},
    });
    expect(state.auditionPlayback).toEqual(accepted);
    expect(() => reduceSampleState(state, {
      type: "preview-applied",
      playback: state.draft?.proposed,
      stale: true,
    } as never)).toThrow("Sample state action is invalid");

    state = reduceSampleState(state, {type: "preview-cleared"} as never);
    expect(state.auditionPlayback).toBeNull();
    expect(state.draft?.proposed.triggerMode).toBe("one_shot");
    state = reduceSampleState(state, {
      type: "preview-applied",
      playback: state.draft?.proposed,
    } as never);
    state = reduceSampleState(state, {type: "preview-failed"});
    expect(state.auditionPlayback).toBeNull();
    expect(state.draft).toBeNull();
  });

  test("reduces pending success, conflict, retry, failure, and cancellation", () => {
    let state = inspectedState();
    state = reduceSampleState(state, {
      type: "pending-began",
      pending: {kind: "import", slot: 17, expectedRevision: 42},
    });
    state = reduceSampleState(state, {
      type: "operation-failed",
      pending: state.pendingAction,
      error: {
        code: "IO_ERROR",
        message: "file:///private/Creator/samples/secret.wav",
        details: {storage_condition: "already_exists"},
      },
    });
    expect(state.pendingAction).toBeNull();
    expect(state.lastError).toEqual({
      code: "IO_ERROR",
      message: "Sample storage operation failed",
      retryPrepare: false,
      details: {storage_condition: "already_exists"},
    });
    expect(state.savedRevision).toBe(42);
    expect(state.runtimeRevision).toBeNull();
    state = reduceSampleState(state, {type: "error-cleared"});
    expect(state.lastError).toBeNull();

    state = reduceSampleState(state, {
      type: "pending-began",
      pending: {kind: "import", slot: 17, expectedRevision: 42},
    });
    state = reduceSampleState(state, {
      type: "operation-cancelled",
      pending: state.pendingAction,
    });
    expect(state.pendingAction).toBeNull();
    expect(state.lastError).toBeNull();

    state = reduceSampleState(state, {
      type: "pending-began",
      pending: {kind: "update", slot: 17, expectedRevision: 42},
    });
    state = {
      ...state,
      auditionPlayback: saved,
    } as never;
    state = reduceSampleState(state, {
      type: "mutation-committed",
      pending: state.pendingAction,
      inspect: {...inspect, projectRevision: 43, playback: {...saved, muted: true}},
      commit: {
        committedRevision: 43,
        runtimeRevision: 42,
        runtimePublished: false,
        snapshotError: {
          code: "COOK_FAILED",
          message: "Sample runtime preparation failed",
          details: {},
        },
      },
    });
    expect(state.savedRevision).toBe(43);
    expect(state.runtimeRevision).toBe(42);
    expect(state.lastError?.retryPrepare).toBe(true);
    expect(state.auditionPlayback).toBeNull();

    state = reduceSampleState(state, {
      type: "pending-began",
      pending: {kind: "retry-prepare", slot: 17, expectedRevision: 43},
    });
    state = reduceSampleState(state, {
      type: "retry-published",
      pending: state.pendingAction,
      publication: {
        projectId: "22222222-2222-4222-8222-222222222222",
        projectRevision: 43,
        patternId: "33333333-3333-4333-8333-333333333333",
        runtimeReady: true,
        generation: 8,
        snapshotError: null,
        runtimeRevision: 43,
      },
    });
    expect(state.runtimeRevision).toBe(43);
    expect(state.lastError).toBeNull();

    state = reduceSampleState(state, {
      type: "pending-began",
      pending: {kind: "update", slot: 17, expectedRevision: 43},
    });
    state = {
      ...state,
      auditionPlayback: saved,
    } as never;
    state = reduceSampleState(state, {
      type: "mutation-conflicted",
      pending: state.pendingAction,
      inspect: {...inspect, projectRevision: 44},
    });
    expect(state.savedRevision).toBe(44);
    expect(state.lastError?.code).toBe("REVISION_CONFLICT");
    expect(state.auditionPlayback).toBeNull();
  });

  test("discards a private operation-failure message when no safe details are supplied", () => {
    let state = beginSamplePending(inspectedState(), {
      kind: "import",
      slot: 17,
      expectedRevision: 42,
    });
    state = reduceSampleState(state, {
      type: "operation-failed",
      pending: state.pendingAction,
      error: {
        code: "IO_ERROR",
        message: "file:///private/Creator/samples/secret.wav",
      },
    });

    expect(state.lastError).toEqual({
      code: "IO_ERROR",
      message: "Sample storage operation failed",
      retryPrepare: false,
      details: {},
    });
  });

  test("fails a rejected preview without requiring or changing mutation pending truth", () => {
    const draft = updateSampleDraft(beginSampleDraft(saved, 42), {
      trimStartFrame: 120,
    });
    const pendingAction = Object.freeze({
      kind: "update" as const,
      slot: 17,
      expectedRevision: 42,
    });
    const state = reduceSampleState({
      ...inspectedState(),
      draft,
      pendingAction,
    }, {type: "preview-failed"} as never);
    expect(state.draft).toBeNull();
    expect(state.pendingAction).toEqual(pendingAction);
    expect(state.lastError).toEqual({
      code: "HOST_STATE_INVALID",
      message: "Runtime preview failed",
      retryPrepare: false,
    });
    expect(() => reduceSampleState(state, {
      type: "preview-failed",
      error: "raw",
    } as never)).toThrow("Sample state action is invalid");
  });

  test("rejects overlapping or stale pending resolutions and requires selection", () => {
    const active = beginSamplePending(inspectedState(), {
      kind: "update",
      slot: 17,
      expectedRevision: 42,
    });
    expect(() => beginSamplePending(active, {
      kind: "reset",
      slot: 17,
      expectedRevision: 42,
    })).toThrow("Sample action is already pending");
    expect(() => reduceSampleState(active, {
      type: "operation-failed",
      pending: {kind: "update", slot: 17, expectedRevision: 41},
      error: {code: "IO_ERROR", message: "late failure"},
    })).toThrow("Sample pending action does not match");
    expect(active.pendingAction?.expectedRevision).toBe(42);
    expect(active.lastError).toBeNull();

    const pending = {kind: "update" as const, slot: 17, expectedRevision: 42};
    expect(() => applySampleCommit(
      {...initialSampleState, pendingAction: pending},
      pending,
      {...inspect, projectRevision: 43},
      {
        committedRevision: 43,
        runtimeRevision: 43,
        runtimePublished: true,
        snapshotError: null,
      },
    )).toThrow("Sample mutation has no matching selection");
  });

  test("preserves Cook retry truth when a later operation is cancelled", () => {
    const committing = beginSamplePending(
      {...inspectedState(), runtimeRevision: 42},
      {kind: "update", slot: 17, expectedRevision: 42},
    );
    let state = applySampleCommit(
      committing,
      committing.pendingAction,
      {...inspect, projectRevision: 43},
      {
        committedRevision: 43,
        runtimeRevision: 42,
        runtimePublished: false,
        snapshotError: {
          code: "COOK_FAILED",
          message: "Sample runtime preparation failed",
          details: {},
        },
      },
    );
    state = reduceSampleState(state, {
      type: "pending-began",
      pending: {kind: "import", slot: 17, expectedRevision: 43},
    });
    const retryError = state.lastError;
    state = reduceSampleState(state, {
      type: "operation-cancelled",
      pending: state.pendingAction,
    });
    expect(state.pendingAction).toBeNull();
    expect(state.lastError).toEqual(retryError);
    expect(state.savedRevision).toBe(43);
    expect(state.runtimeRevision).toBe(42);
  });

  test("bounds active Voice and selected playhead render state", () => {
    let state = inspectedState();
    for (let sequence = 1; sequence <= SAMPLE_VOICE_RENDER_LIMIT + 1; sequence += 1) {
      state = applyRuntimeVoiceState(state, {
        sequence,
        slot: 17,
        state: "started",
        runtimeFrame: sequence * 128,
        sourceFrame: 100 + sequence,
      });
    }
    expect(state.voices).toHaveLength(SAMPLE_VOICE_RENDER_LIMIT);
    expect(state.voices.some(({sequence}) => sequence === 1)).toBe(false);
    expect(state.playhead).toEqual({
      sequence: SAMPLE_VOICE_RENDER_LIMIT + 1,
      slot: 17,
      runtimeFrame: (SAMPLE_VOICE_RENDER_LIMIT + 1) * 128,
      sourceFrame: 100 + SAMPLE_VOICE_RENDER_LIMIT + 1,
      sampleRate: 48_000,
      trimStartFrame: 10,
      trimEndFrame: 480,
    });

    state = applyRuntimeVoiceState(state, {
      sequence: SAMPLE_VOICE_RENDER_LIMIT + 1,
      slot: 17,
      state: "completed",
      runtimeFrame: 9_999,
      sourceFrame: 900,
    });
    expect(state.voices.some(
      ({sequence}) => sequence === SAMPLE_VOICE_RENDER_LIMIT + 1,
    )).toBe(false);
    expect(state.playhead).toBeNull();
  });

  test("bounds an audition playhead against the active draft preview", () => {
    const draft = updateSampleDraft(beginSampleDraft(saved, 42), {
      trimStartFrame: 120,
      trimEndFrame: 300,
    });
    const previewed = reduceSampleState({...inspectedState(), draft}, {
      type: "preview-applied",
      playback: draft.proposed,
    });
    const state = applyRuntimeVoiceState(previewed, {
      sequence: 1,
      slot: 17,
      state: "started",
      runtimeFrame: 128,
      sourceFrame: 50,
    });
    expect(state.playhead?.sourceFrame).toBe(120);
  });

  test("snapshots Voice render bounds when preview playback starts", () => {
    const draft = updateSampleDraft(beginSampleDraft(saved, 42), {
      trimStartFrame: 120,
      trimEndFrame: 300,
    });
    let state = reduceSampleState({...inspectedState(), draft}, {
      type: "preview-applied",
      playback: draft.proposed,
    } as never);
    state = applyRuntimeVoiceState(state, {
      sequence: 9,
      slot: 17,
      state: "started",
      runtimeFrame: 128,
      sourceFrame: 140,
    });
    expect(state.voices.at(-1)).toMatchObject({
      sampleRate: 48_000,
      trimStartFrame: 120,
      trimEndFrame: 300,
    });
    expect(state.playhead).toMatchObject({
      sampleRate: 48_000,
      trimStartFrame: 120,
      trimEndFrame: 300,
    });

    state = reduceSampleState(state, {type: "draft-cancelled"});
    expect(state.voices.at(-1)).toMatchObject({
      sampleRate: 48_000,
      trimStartFrame: 120,
      trimEndFrame: 300,
    });
    expect(state.playhead).toMatchObject({
      sampleRate: 48_000,
      trimStartFrame: 120,
      trimEndFrame: 300,
    });
  });

  test("rejects unsafe, noncanonical, extra-key, and private state inputs", () => {
    expect(() => projectSamplePlayback({...saved, fileName: "kick.wav"})).toThrow();
    expect(() => storeSampleInspect(initialSampleState, {
      ...inspect,
      projectRevision: Number.MAX_SAFE_INTEGER + 1,
    })).toThrow();
    expect(() => storeSampleInspect(selectSampleSlot(initialSampleState, 17), {
      ...inspect,
      projectPath: "/private/project.lmdj",
    })).toThrow();
    expect(() => storeSampleInspect(selectSampleSlot(initialSampleState, 17), {
      ...inspect,
      waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/3`,
    })).toThrow();
    expect(() => storeSampleWaveform(inspectedState(), {
      metadata,
      algorithmVersion: 1,
      buckets: [{
        startFrame: 0,
        endFrame: 1_000,
        peakMagnitude: 32_769,
        sampleBytes: new Uint8Array([1]),
      }],
      projectRevision: 42,
    }, {
      slot: 17,
      window: {startFrame: 0, endFrame: 1_000, bucketCount: 1},
      waveformCacheIdentity: inspect.waveformCacheIdentity,
    })).toThrow();
    expect(() => applyRuntimeVoiceState(inspectedState(), {
      sequence: Number.MAX_SAFE_INTEGER + 1,
      slot: 17,
      state: "started",
      runtimeFrame: 0,
      sourceFrame: 10,
    })).toThrow();
    for (const payload of [
      new ArrayBuffer(8),
      [new Uint8Array([1])],
      new File(["private"], "secret.wav"),
      new Date(0),
      {absolutePath: "/private/project"},
      {projectJson: {revision: 42}},
      {audioBytes: [82, 73, 70, 70]},
      {OPFSHandle: "private-handle"},
      {
        contract: "lmdj.project.v2",
        revision: 1,
        banks: [],
        assets: {},
      },
    ]) {
      const pending = beginSamplePending(inspectedState(), {
        kind: "update",
        slot: 17,
        expectedRevision: 42,
      });
      expect(() => applySampleCommit(pending, pending.pendingAction, {
        ...inspect,
        projectRevision: 43,
      }, {
        committedRevision: 43,
        runtimeRevision: 42,
        runtimePublished: false,
        snapshotError: {
          code: "COOK_FAILED",
          message: "Sample runtime preparation failed",
          details: {payload},
        },
      })).toThrow();
    }
  });

  test("accepts only exact public snapshot details and stores fixed Creator messages", () => {
    const publicDetails: readonly Readonly<Record<string, unknown>>[] = [
      {},
      {actual_revision: 43, expected_revision: 42},
      ...[
        "artifact_bytes",
        "decoded_frames_per_pad",
        "prepared_bank_bytes",
        "live_bank_bytes",
      ].map((resource) => ({resource, observed: 2_000, limit: 1_000})),
      ...[
        "project_busy",
        "already_exists",
        "atomic_publish_unsupported",
      ].map((storage_condition) => ({storage_condition})),
      {transfer_condition: "resource_limit"},
    ];

    for (const details of publicDetails) {
      const pending = beginSamplePending(inspectedState(), {
        kind: "update",
        slot: 17,
        expectedRevision: 42,
      });
      const applied = applySampleCommit(pending, pending.pendingAction, {
        ...inspect,
        projectRevision: 43,
      }, {
        committedRevision: 43,
        runtimeRevision: 42,
        runtimePublished: false,
        snapshotError: {
          code: "COOK_FAILED",
          message: "opaque Host wording",
          details,
        },
      });
      expect(applied.lastError).toEqual({
        code: "COOK_FAILED",
        message: "Sample runtime preparation failed",
        retryPrepare: true,
      });
    }
  });

  test("rejects private Host messages and non-allowlisted details at the state boundary", () => {
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
      const pending = beginSamplePending(inspectedState(), {
        kind: "update",
        slot: 17,
        expectedRevision: 42,
      });
      expect(() => applySampleCommit(pending, pending.pendingAction, {
        ...inspect,
        projectRevision: 43,
      }, {
        committedRevision: 43,
        runtimeRevision: 42,
        runtimePublished: false,
        snapshotError: {
          code: "COOK_FAILED",
          message: "Sample runtime preparation failed",
          details,
        },
      })).toThrow();
    }
    for (const message of privateMessages) {
      const pending = beginSamplePending(inspectedState(), {
        kind: "update",
        slot: 17,
        expectedRevision: 42,
      });
      expect(() => applySampleCommit(pending, pending.pendingAction, {
        ...inspect,
        projectRevision: 43,
      }, {
        committedRevision: 43,
        runtimeRevision: 42,
        runtimePublished: false,
        snapshotError: {code: "COOK_FAILED", message, details: {}},
      })).toThrow();
    }
  });
});
