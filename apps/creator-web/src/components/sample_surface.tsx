import {useCallback, useEffect, useRef, useState} from "react";

import {BankSelector} from "./bank_selector";
import {ConfirmationDialog, SampleControls} from "./sample_controls";
import {WaveformEditor} from "./waveform_editor";
import type {createCreatorInputController} from "../runtime/input_controller";
import {
  cancelSamplePreviewJourney,
  captureCommitJourney,
  importAssignSampleJourney,
  inspectSampleJourney,
  previewSampleDraftJourney,
  queryWaveformJourney,
  resetSampleJourney,
  updateSampleJourney,
  type SampleMutationResolution,
} from "../runtime/sample_actions";
import {CapturePanel} from "./capture_panel";
import {LongSourceEditor, type LongSourceCommitOutcome} from "./long_source_editor";
import type {CaptureBuffer} from "../capture/capture_buffer";
import {
  DecodedLongSource,
  LongSourceIngestError,
  openLongSource,
} from "../ingest/long_source_ingest";
import {refreshProjectProjectionJourney} from "../runtime/project_actions";
import type {
  CreatorSampleRuntimeSession,
  PadPlayback,
  SampleQuota,
  TypedRuntimeError,
} from "../runtime/runtime_types";
import {
  beginSampleDraft,
  fitSampleViewport,
  updateSampleDraft,
  waveformWindowForViewport,
  type SamplePendingAction,
} from "../state/sample_state";
import type {CapturePhase} from "../state/capture_state";
import {
  selectVisiblePads,
  type CreatorAction,
  type CreatorState,
} from "../state/creator_state";
import {padAddress} from "../state/view_model";

interface SampleSurfaceProps {
  state: CreatorState;
  session?: CreatorSampleRuntimeSession;
  controller?: ReturnType<typeof createCreatorInputController>;
  filePickIntent: {current: (slot: number) => void};
  dispatch: (action: CreatorAction) => void;
  captureStopRequest?: number;
  onCaptureSlotChange?(slot: number | null): void;
  onCapturePhaseChange?(phase: CapturePhase): void;
  onContinueCaptureInSequence?(): void;
  closeCaptureAfterResolution?: boolean;
}

interface PendingFile {
  readonly slot: number;
  readonly file: File;
}

interface LongSourceDraft {
  readonly slot: number;
  readonly source: DecodedLongSource;
  readonly quota: Readonly<SampleQuota>;
}

interface CaptureTarget {
  readonly slot: number;
  readonly quota: Readonly<SampleQuota>;
}

// What the Sample surface reports back to a byte source about one import
// journey. CapturePanel consumes exactly this shape.
type ImportOutcome =
  | {readonly kind: "committed"}
  | {readonly kind: "conflict"; readonly message: string}
  | {readonly kind: "failed"; readonly message: string};

const COMMITTED_OUTCOME: ImportOutcome = Object.freeze({kind: "committed"});
const BUSY_OUTCOME: ImportOutcome = Object.freeze({
  kind: "failed",
  message: "Another Sample operation is still running.",
});
// The journey was replaced by a newer operation; its own result is no longer
// this caller's to report, and the surface already reflects the newer one.
const SUPERSEDED_OUTCOME: ImportOutcome = Object.freeze({
  kind: "failed",
  message: "Superseded by a newer Sample operation.",
});
const CANCELLED_OUTCOME: ImportOutcome = Object.freeze({
  kind: "failed",
  message: "Sample import was cancelled.",
});

interface PreviewOwner {
  readonly session: CreatorSampleRuntimeSession;
  readonly slot: number;
}

const SAMPLE_ERROR_CODES = new Set([
  "INVALID_ARGUMENT",
  "NOT_FOUND",
  "REVISION_CONFLICT",
  "DUPLICATE_ID",
  "UNSUPPORTED_AUDIO",
  "MISSING_ASSET",
  "INVALID_PROJECT",
  "COOK_FAILED",
  "BANK_QUOTA_EXHAUSTED",
  "PROJECT_QUOTA_EXHAUSTED",
  "PROVIDER_NOT_FOUND",
  "PROVIDER_FAILED",
  "PERMISSION_DENIED",
  "IO_ERROR",
  "INTERNAL_ERROR",
  "UNSUPPORTED_WEB_RUNTIME",
  "PROJECT_BUSY",
  "WEB_RUNTIME_RESOURCE_LIMIT",
  "HOST_STATE_INVALID",
  "HOST_TIMEOUT",
  "HOST_RESTART_REQUIRED",
  "HOST_PROTOCOL_MISMATCH",
]);
const PAD_KEY_CODES = Object.freeze([
  "KeyQ", "KeyW", "KeyE", "KeyR", "KeyT", "KeyY", "KeyU", "KeyI",
  "KeyA", "KeyS", "KeyD", "KeyF", "KeyG", "KeyH", "KeyJ", "KeyK",
]);

function publicOperationError(
  error: unknown,
): Readonly<{code: string; message: string; details?: Readonly<Record<string, unknown>>}> {
  const candidate = (error as TypedRuntimeError | null)?.code;
  const code = candidate !== undefined && SAMPLE_ERROR_CODES.has(candidate)
    ? candidate
    : "INTERNAL_ERROR";
  const details = (error as TypedRuntimeError | null)?.details;
  return Object.freeze({
    code,
    message: code === "BANK_QUOTA_EXHAUSTED"
      ? "Selection exceeds this Bank quota; shorten it, free another Pad, or use another Bank"
      : code === "PROJECT_QUOTA_EXHAUSTED"
        ? "Selection exceeds the Project quota; shorten it or free prepared Samples"
        : "Sample operation failed",
    ...(details === undefined ? {} : {details}),
  });
}

function metadataCopy(state: CreatorState): string {
  const metadata = state.sample.inspect?.metadata;
  if (metadata === null || metadata === undefined) return "No Sample assigned";
  const rate = metadata.sampleRate === 44_100 ? "44.1 kHz" : "48 kHz";
  const channels = metadata.channels === 1 ? "Mono" : "Stereo";
  return `${rate} · ${channels} · ${metadata.sourceFrames.toLocaleString()} frames`;
}

function displayFileName(name: string): string {
  const characters = Array.from(name);
  return characters.length <= 96 ? name : `${characters.slice(0, 95).join("")}…`;
}

function quotaErrorCopy(
  error: CreatorState["sample"]["lastError"],
): string | null {
  if (error === null || error.details === undefined) return null;
  if (error.code === "BANK_QUOTA_EXHAUSTED") {
    const bank = error.details.bank;
    const remaining = error.details.remaining_frames;
    const consumed = error.details.consumed;
    if (typeof bank !== "number" || typeof remaining !== "number" || !Array.isArray(consumed)) {
      return null;
    }
    const usage = consumed.map((entry) => {
      if (entry === null || typeof entry !== "object") return null;
      const pad = (entry as Record<string, unknown>).pad;
      const frames = (entry as Record<string, unknown>).prepared_frames;
      return typeof pad === "number" && typeof frames === "number"
        ? `${String.fromCharCode(65 + bank)}${pad + 1}: ${(frames / 48_000).toFixed(2)} s`
        : null;
    }).filter((entry): entry is string => entry !== null);
    return `Bank ${String.fromCharCode(65 + bank)} remaining ${(remaining / 48_000).toFixed(2)} s; Pad usage ${usage.length === 0 ? "none" : usage.join(", ")}.`;
  }
  if (error.code === "PROJECT_QUOTA_EXHAUSTED") {
    const remaining = error.details.project_remaining_bytes;
    return typeof remaining === "number"
      ? `Project remaining ${(remaining / 4 / 48_000).toFixed(2)} s prepared mono PCM.`
      : null;
  }
  return null;
}

export function SampleSurface({
  state,
  session,
  controller,
  filePickIntent,
  dispatch,
  captureStopRequest = 0,
  onCaptureSlotChange,
  onCapturePhaseChange,
  onContinueCaptureInSequence,
  closeCaptureAfterResolution = false,
}: SampleSurfaceProps) {
  const input = useRef<HTMLInputElement | null>(null);
  const fileSlot = useRef<number | null>(null);
  const replaceReturnFocus = useRef<HTMLElement | null>(null);
  const importController = useRef<AbortController | null>(null);
  const operationPending = useRef<Readonly<SamplePendingAction> | null>(null);
  const importPending = useRef<Readonly<SamplePendingAction> | null>(null);
  const previousSession = useRef(session);
  const previewEpoch = useRef(0);
  const previewOwner = useRef<PreviewOwner | null>(null);
  const ingestEpoch = useRef(0);
  const ingestOwner = useRef<DecodedLongSource | null>(null);
  const [pendingFile, setPendingFile] = useState<PendingFile | null>(null);
  const [longSourceDraft, setLongSourceDraft] = useState<LongSourceDraft | null>(null);
  const [ingestPending, setIngestPending] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);
  // Slot whose Replace confirmation is pending before the capture panel opens
  // (S8-D12), and the slot the open panel records into.
  const [pendingCaptureSlot, setPendingCaptureSlot] = useState<number | null>(null);
  const [captureTarget, setCaptureTarget] = useState<CaptureTarget | null>(null);
  const sample = state.sample;
  const audioSuspended = state.audio.phase !== "running" &&
    state.audio.phase !== "recovering";
  const previousAudioSuspended = useRef(audioSuspended);
  const inspect = sample.inspect;
  const selectedSlot = sample.selectedSlot;

  useEffect(() => {
    onCaptureSlotChange?.(captureTarget?.slot ?? null);
  }, [captureTarget, onCaptureSlotChange]);

  const releaseLongSource = useCallback(() => {
    ingestEpoch.current += 1;
    const source = ingestOwner.current;
    ingestOwner.current = null;
    source?.release();
    setLongSourceDraft(null);
  }, []);

  const clearOwnedPreview = useCallback(() => {
    const owner = previewOwner.current;
    if (owner === null) return;
    previewOwner.current = null;
    previewEpoch.current += 1;
    void cancelSamplePreviewJourney(owner.session, owner.slot).then(
      () => dispatch({type: "sample-action", action: {type: "preview-cleared"}}),
      () => {},
    );
  }, [dispatch]);

  useEffect(() => {
    filePickIntent.current = (slot) => {
      replaceReturnFocus.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      fileSlot.current = slot;
      input.current?.click();
    };
    return () => { filePickIntent.current = () => {}; };
  }, [filePickIntent]);

  useEffect(() => () => {
    clearOwnedPreview();
    releaseLongSource();
    const pending = importPending.current;
    importPending.current = null;
    if (pending !== null) {
      if (operationPending.current === pending) operationPending.current = null;
      dispatch({
        type: "sample-action",
        action: {type: "operation-cancelled", pending},
      });
    }
    importController.current?.abort();
    importController.current = null;
  }, [clearOwnedPreview, dispatch, releaseLongSource]);

  useEffect(() => {
    if (session !== undefined && selectedSlot !== null &&
      sample.auditionPlayback !== null && previewOwner.current === null) {
      previewOwner.current = {session, slot: selectedSlot};
    }
  }, [sample.auditionPlayback, selectedSlot, session]);

  useEffect(() => {
    const wasSuspended = previousAudioSuspended.current;
    previousAudioSuspended.current = audioSuspended;
    if (!audioSuspended || wasSuspended) return;
    previewEpoch.current += 1;
    previewOwner.current = null;
  }, [audioSuspended]);

  useEffect(() => {
    if (previousSession.current === session) return;
    clearOwnedPreview();
    releaseLongSource();
    previousSession.current = session;
    const pending = operationPending.current;
    operationPending.current = null;
    importPending.current = null;
    importController.current?.abort();
    importController.current = null;
    if (pending !== null) {
      dispatch({
        type: "sample-action",
        action: {type: "operation-cancelled", pending},
      });
    }
  }, [clearOwnedPreview, dispatch, releaseLongSource, session]);

  const projectIdentity = state.project.current?.projectId ?? null;
  const previousProjectIdentity = useRef(projectIdentity);
  useEffect(() => {
    if (previousProjectIdentity.current === projectIdentity) return;
    previousProjectIdentity.current = projectIdentity;
    releaseLongSource();
    setCaptureTarget(null);
  }, [projectIdentity, releaseLongSource]);

  useEffect(() => {
    if (state.audio.phase !== "recovering") return;
    releaseLongSource();
    setCaptureTarget(null);
  }, [releaseLongSource, state.audio.phase]);

  useEffect(() => {
    if (selectedSlot !== null || state.project.current === null) return;
    dispatch({
      type: "sample-action",
      action: {type: "slot-selected", slot: state.activeBank * 16},
    });
  }, [dispatch, selectedSlot, state.activeBank, state.project.current]);

  useEffect(() => {
    if (session === undefined || selectedSlot === null ||
      state.project.current === null) return;
    let current = true;
    void inspectSampleJourney(session, selectedSlot).then(
      (value) => {
        if (current) {
          dispatch({
            type: "sample-action",
            action: {type: "inspect-stored", inspect: value},
          });
        }
      },
      () => {
        // Input-controller and mutation paths own typed public failures.
      },
    );
    return () => { current = false; };
  }, [
    dispatch,
    sample.savedRevision,
    selectedSlot,
    session,
    state.project.current,
  ]);

  useEffect(() => {
    if (session === undefined || inspect === null || inspect.metadata === null ||
      inspect.waveformCacheIdentity === null) return;
    let current = true;
    const viewport = fitSampleViewport(inspect.metadata.sourceFrames);
    const window = waveformWindowForViewport(
      viewport,
      Math.min(256, inspect.metadata.sourceFrames),
    );
    const request = Object.freeze({
      slot: inspect.slot,
      window,
      waveformCacheIdentity: inspect.waveformCacheIdentity,
    });
    void queryWaveformJourney(session, {slot: inspect.slot, window}).then(
      (envelope) => {
        if (current) {
          dispatch({
            type: "sample-action",
            action: {type: "waveform-stored", envelope, request},
          });
        }
      },
      () => {
        // Inspect remains usable when the derived waveform query is unavailable.
      },
    );
    return () => { current = false; };
  }, [dispatch, inspect, session]);

  useEffect(() => {
    const refresh = state.sampleProjectionRefresh;
    const currentProject = state.project.current;
    if (refresh === null || session === undefined || currentProject === null) return;
    let active = true;
    let retryTimer: number | null = null;
    const waitForRetry = (milliseconds: number) => new Promise<void>((resolve) => {
      retryTimer = window.setTimeout(() => {
        retryTimer = null;
        resolve();
      }, milliseconds);
    });
    const failRefresh = (errorCode: string) => {
      if (active) dispatch({type: "sample-projection-refresh-failed", errorCode});
    };
    void (async () => {
      let currentInspect = refresh.inspect;
      for (let attempt = 0; attempt < 4; ++attempt) {
        if (attempt > 0) await waitForRetry(attempt * 25);
        if (!active) return;
        let project;
        try {
          project = await refreshProjectProjectionJourney(session, currentProject);
        } catch (error) {
          const code = publicOperationError(error).code;
          if (code === "PROJECT_BUSY") continue;
          failRefresh(code);
          return;
        }
        if (!active) return;
        if (project === null) continue;
        if (currentInspect === null ||
          project.revision !== currentInspect.projectRevision) {
          try {
            currentInspect = await inspectSampleJourney(session, refresh.pending.slot);
          } catch (error) {
            const code = publicOperationError(error).code;
            if (code === "PROJECT_BUSY") continue;
            failRefresh(code);
            return;
          }
          if (project.revision !== currentInspect.projectRevision) continue;
        }
        if (!active || currentInspect === null) return;
        dispatch({
          type: "sample-project-refreshed",
          project,
          action: {...refresh, inspect: currentInspect},
        });
        return;
      }
      failRefresh("HOST_TIMEOUT");
    })();
    return () => {
      active = false;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
    };
  }, [dispatch, session, state.project.current, state.sampleProjectionRefresh]);

  const dispatchResolution = (
    pending: Readonly<SamplePendingAction>,
    resolution: SampleMutationResolution,
  ): void => {
    if (operationPending.current !== pending) return;
    operationPending.current = null;
    if (importPending.current === pending) importPending.current = null;
    dispatch({
      type: "sample-projection-refresh-started",
      action: resolution.kind === "committed"
        ? {
            type: "mutation-committed",
            pending,
            inspect: resolution.inspect,
            commit: resolution.commit,
          }
        : {
            type: "mutation-conflicted",
            pending,
            inspect: resolution.inspect,
          },
    });
  };

  const isAssigned = (slot: number): boolean =>
    (state.project.current?.pads[slot]?.assetId !== null &&
      state.project.current?.pads[slot]?.assetId !== undefined) ||
    (inspect?.slot === slot && inspect.assetId !== null);

  const stopBeforeMutation = async (slot: number) => {
    if (session === undefined) return;
    if (await session.stopPad(slot) !== true) {
      throw Object.assign(new Error("Sample stop failed"), {code: "HOST_STATE_INVALID"});
    }
  };

  const performUpdate = async (playback: Readonly<PadPlayback>) => {
    if (session === undefined || inspect === null || sample.pendingAction !== null ||
      operationPending.current !== null) return;
    previewEpoch.current += 1;
    const pending = Object.freeze({
      kind: "update" as const,
      slot: inspect.slot,
      expectedRevision: inspect.projectRevision,
    });
    operationPending.current = pending;
    dispatch({type: "sample-action", action: {type: "pending-began", pending}});
    let mutationStarted = false;
    try {
      if (playback.muted !== inspect.playback.muted) {
        await stopBeforeMutation(inspect.slot);
      }
      mutationStarted = true;
      const resolution = await updateSampleJourney(session, {
        slot: inspect.slot,
        expectedRevision: inspect.projectRevision,
        playback,
      });
      previewOwner.current = null;
      if (operationPending.current !== pending) return;
      dispatchResolution(pending, resolution);
    } catch (error) {
      if (mutationStarted) previewOwner.current = null;
      else clearOwnedPreview();
      if (operationPending.current !== pending) return;
      operationPending.current = null;
      dispatch({type: "sample-action", action: {type: "draft-cancelled"}});
      dispatch({type: "sample-action", action: {type: "preview-cleared"}});
      dispatch({
        type: "sample-action",
        action: {type: "operation-failed", pending, error: publicOperationError(error)},
      });
    }
  };

  const preview = (playback: Readonly<PadPlayback>) => {
    if (session === undefined || inspect === null || sample.pendingAction !== null ||
      operationPending.current !== null) return;
    const epoch = ++previewEpoch.current;
    previewOwner.current = {session, slot: inspect.slot};
    const draft = updateSampleDraft(
      beginSampleDraft(inspect.playback, inspect.projectRevision),
      playback,
    );
    if (sample.draft === null) {
      dispatch({type: "sample-action", action: {type: "draft-began"}});
    }
    dispatch({
      type: "sample-action",
      action: {type: "draft-updated", changes: playback},
    });
    void previewSampleDraftJourney(session, inspect.slot, draft).then(
      () => {
        if (previewEpoch.current === epoch) {
          dispatch({
            type: "sample-action",
            action: {type: "preview-applied", playback},
          });
        }
      },
      () => {
        if (previewEpoch.current === epoch) {
          previewOwner.current = null;
          dispatch({type: "sample-action", action: {type: "preview-failed"}});
        }
      },
    );
  };

  const cancelPreview = () => {
    dispatch({type: "sample-action", action: {type: "draft-cancelled"}});
    clearOwnedPreview();
  };

  const reset = async () => {
    if (session === undefined || inspect === null || sample.pendingAction !== null ||
      operationPending.current !== null) return;
    const pending = Object.freeze({
      kind: "reset" as const,
      slot: inspect.slot,
      expectedRevision: inspect.projectRevision,
    });
    operationPending.current = pending;
    dispatch({type: "sample-action", action: {type: "pending-began", pending}});
    let mutationStarted = false;
    try {
      await stopBeforeMutation(inspect.slot);
      mutationStarted = true;
      const resolution = await resetSampleJourney(session, {
        slot: inspect.slot,
        expectedRevision: inspect.projectRevision,
      });
      previewOwner.current = null;
      if (operationPending.current !== pending) return;
      dispatchResolution(pending, resolution);
    } catch (error) {
      if (mutationStarted) previewOwner.current = null;
      else clearOwnedPreview();
      if (operationPending.current !== pending) return;
      operationPending.current = null;
      dispatch({
        type: "sample-action",
        action: {type: "operation-failed", pending, error: publicOperationError(error)},
      });
    }
  };

  // One journey runner for every byte source that assigns a Sample to a Pad.
  // A file pick and a committed capture differ only in how the bytes are
  // produced, so they must share the Replace confirmation, the pre-mutation
  // stop, the pending/abort bookkeeping, conflict classification and the
  // post-import selection and waveform behaviour. `invoke` is the only seam.
  const runImportJourney = async (
    slot: number,
    invoke: (
      active: CreatorSampleRuntimeSession,
      options: {slot: number; expectedRevision: number; signal: AbortSignal},
    ) => Promise<SampleMutationResolution>,
    expectedRevisionOverride?: number,
  ): Promise<ImportOutcome> => {
    if (session === undefined || sample.pendingAction !== null ||
      operationPending.current !== null) return BUSY_OUTCOME;
    const expectedRevision = expectedRevisionOverride ??
      sample.savedRevision ?? state.project.current?.revision;
    if (expectedRevision === null || expectedRevision === undefined) return BUSY_OUTCOME;
    const assigned = isAssigned(slot);
    const pending = Object.freeze({
      kind: assigned ? "replace" as const : "import" as const,
      slot,
      expectedRevision,
    });
    dispatch({type: "sample-action", action: {type: "pending-began", pending}});
    const controller = new AbortController();
    importController.current = controller;
    operationPending.current = pending;
    importPending.current = pending;
    try {
      if (assigned) await stopBeforeMutation(slot);
      const resolution = await invoke(session, {
        slot,
        expectedRevision,
        signal: controller.signal,
      });
      previewOwner.current = null;
      if (operationPending.current !== pending) return SUPERSEDED_OUTCOME;
      dispatchResolution(pending, resolution);
      return resolution.kind === "conflict"
        ? {kind: "conflict", message: resolution.message}
        : COMMITTED_OUTCOME;
    } catch (error) {
      clearOwnedPreview();
      if (operationPending.current !== pending) return SUPERSEDED_OUTCOME;
      operationPending.current = null;
      importPending.current = null;
      if (error instanceof DOMException && error.name === "AbortError") {
        dispatch({
          type: "sample-action",
          action: {type: "operation-cancelled", pending},
        });
        return CANCELLED_OUTCOME;
      }
      const failure = publicOperationError(error);
      dispatch({
        type: "sample-action",
        action: {type: "operation-failed", pending, error: failure},
      });
      return {kind: "failed", message: failure.message};
    } finally {
      if (importController.current === controller) importController.current = null;
    }
  };

  const startLongImport = async ({slot, file}: PendingFile): Promise<void> => {
    if (session === undefined || ingestPending || sample.pendingAction !== null ||
      operationPending.current !== null) return;
    releaseLongSource();
    setIngestPending(true);
    setIngestError(null);
    const epoch = ++ingestEpoch.current;
    try {
      const quota = await session.querySampleQuota(slot);
      const source = await openLongSource(file, session.sampleIngestLimits());
      if (ingestEpoch.current !== epoch) {
        source.release();
        return;
      }
      ingestOwner.current = source;
      setLongSourceDraft({slot, source, quota});
    } catch (error) {
      if (ingestEpoch.current !== epoch) return;
      if (error instanceof LongSourceIngestError) {
        setIngestError(`${error.message} (${error.details.resource}: ${String(error.details.observed)} / ${String(error.details.limit)})`);
      } else {
        setIngestError(publicOperationError(error).message);
      }
    } finally {
      if (ingestEpoch.current === epoch) setIngestPending(false);
    }
  };

  const commitLongSource = async (
    draft: LongSourceDraft,
    selection: {startFrame: number; frameCount: number},
  ): Promise<LongSourceCommitOutcome> => {
    let file: File;
    try {
      file = draft.source.encodeSelection(selection, draft.quota.effectiveRemainingFrames);
    } catch (error) {
      return {kind: "failed", message: error instanceof Error ? error.message : "Selection encode failed"};
    }
    const outcome = await runImportJourney(
      draft.slot,
      (active, options) => importAssignSampleJourney(active, file, options),
      draft.quota.projectRevision,
    );
    if (outcome.kind === "committed") releaseLongSource();
    return outcome;
  };

  const performCaptureCommit = (
    target: CaptureTarget,
    buffer: CaptureBuffer,
    selection: {startFrame: number; frameCount: number},
  ) => runImportJourney(
    target.slot,
    (active, options) => captureCommitJourney(active, buffer, selection, options),
    target.quota.projectRevision,
  );

  const openCapture = async (slot: number): Promise<void> => {
    if (session === undefined) return;
    setIngestError(null);
    try {
      const quota = await session.querySampleQuota(slot);
      if (quota.effectiveRemainingFrames < 1) {
        setIngestError("why: no prepared-PCM quota remains; remedy: free a Pad or choose another Bank.");
        return;
      }
      setCaptureTarget({slot, quota});
    } catch (error) {
      setIngestError(publicOperationError(error).message);
    }
  };

  const chooseFile = (slot: number) => {
    replaceReturnFocus.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    fileSlot.current = slot;
    input.current?.click();
  };
  const selectedAddress = selectedSlot === null
    ? "No Pad selected"
    : `Pad ${padAddress({slot: selectedSlot, assetId: inspect?.assetId ?? null})}`;
  const editablePlayback = sample.auditionPlayback ?? sample.draft?.proposed ?? inspect?.playback;
  const selectedAssigned = inspect?.assetId !== null && inspect?.assetId !== undefined;
  const projectUnavailable = state.project.phase !== "ready" ||
    state.project.current === null;
  const actionsDisabled = session === undefined || projectUnavailable || inspect === null ||
    !selectedAssigned || sample.pendingAction !== null;
  const inspectedMetadata = inspect?.metadata;
  const queryViewportWaveform = session === undefined || inspect === null ||
      inspectedMetadata === null || inspectedMetadata === undefined ||
      inspect.waveformCacheIdentity === null
    ? undefined
    : async (viewport: Readonly<ReturnType<typeof fitSampleViewport>>) => {
        const span = viewport.endFrame - viewport.startFrame;
        const window = waveformWindowForViewport(viewport, Math.min(256, span));
        const envelope = await queryWaveformJourney(session, {slot: inspect.slot, window});
        if (envelope.projectRevision !== inspect.projectRevision ||
          envelope.metadata.sourceFrames !== inspectedMetadata.sourceFrames ||
          envelope.metadata.sampleRate !== inspectedMetadata.sampleRate ||
          envelope.metadata.channels !== inspectedMetadata.channels) {
          return null;
        }
        return envelope;
      };

  return (
    <main className="sample-surface">
      <header className="sample-heading">
        <div>
          <p className="eyebrow">Sample surface</p>
          <h1>Sample editor</h1>
        </div>
        <div className="selected-sample" aria-live="polite">
          <strong>{selectedAddress}</strong>
          <span>{inspect?.assetId === null || inspect?.assetId === undefined
            ? "Empty"
            : `Asset ${inspect.assetId.slice(0, 8)}`}</span>
          <span>{metadataCopy(state)}</span>
          {selectedAssigned && selectedSlot !== null ? (
            <button
              type="button"
              disabled={session === undefined || projectUnavailable ||
                sample.pendingAction !== null}
              onClick={() => chooseFile(selectedSlot)}
            >
              Replace Sample
            </button>
          ) : null}
          {selectedSlot !== null ? (
            <button
              type="button"
              disabled={session === undefined || projectUnavailable ||
                sample.pendingAction !== null || captureTarget !== null}
              onClick={() => {
                replaceReturnFocus.current = document.activeElement instanceof HTMLElement
                  ? document.activeElement
                  : null;
                // Recording onto an assigned Pad is a replacement, so it takes
                // the existing confirmation before the microphone is ever
                // requested (S8-D12, S8B-D2).
                if (selectedAssigned) setPendingCaptureSlot(selectedSlot);
                else void openCapture(selectedSlot);
              }}
            >
              Record Sample
            </button>
          ) : null}
        </div>
      </header>

      {inspect !== null && inspect.metadata !== null && editablePlayback !== undefined ? (
        <>
          <WaveformEditor
            key={`${inspect.slot}:${inspect.waveformCacheIdentity ?? "none"}`}
            padLabel={selectedAddress}
            envelope={sample.waveform}
            metadata={inspect.metadata}
            projectRevision={inspect.projectRevision}
            playback={editablePlayback}
            playheadFrame={sample.playhead?.sourceFrame ?? null}
            disabled={actionsDisabled}
            onPreview={preview}
            onCommit={(playback) => { void performUpdate(playback); }}
            onCancel={cancelPreview}
            {...(queryViewportWaveform === undefined
              ? {}
              : {onQueryWaveform: queryViewportWaveform})}
          />
          <SampleControls
            padLabel={selectedAddress}
            playback={editablePlayback}
            audioSuspended={audioSuspended}
            disabled={actionsDisabled}
            onPreview={preview}
            onCommit={(playback) => { void performUpdate(playback); }}
            onCancel={cancelPreview}
            onReset={() => { void reset(); }}
          />
        </>
      ) : (
        <section className="empty-sample" aria-label="Selected Pad Sample">
          <p>Select an assigned Pad to edit its waveform and playback.</p>
          {selectedSlot === null ? null : (
            <button
              type="button"
              disabled={session === undefined || projectUnavailable ||
                sample.pendingAction !== null}
              onClick={() => chooseFile(selectedSlot)}
            >
              Add Sample to {selectedAddress}
            </button>
          )}
        </section>
      )}

      {sample.lastError === null ? null : (
        <div className="sample-error" role="alert">
          <p>{sample.lastError.message}</p>
          {quotaErrorCopy(sample.lastError) === null
            ? null
            : <p>{quotaErrorCopy(sample.lastError)}</p>}
        </div>
      )}

      <section className="sample-pads" aria-label="Sample Pads">
        <BankSelector
          activeBank={state.activeBank}
          onSelect={(bank) => {
            controller?.clearPressed();
            dispatch({type: "bank-selected", bank});
          }}
        />
        <div className="pad-grid" aria-label="Playable Pads">
          {selectVisiblePads(state).map((pad) => {
            const address = padAddress(pad);
            const selected = sample.selectedSlot === pad.slot;
            const assigned = pad.assetId !== null ||
              (selected && inspect?.assetId !== null && inspect?.assetId !== undefined);
            const outcome = state.pressed.get(pad.slot);
            return (
              <button
                type="button"
                className={`pad${selected ? " is-selected" : ""}`}
                data-outcome={outcome ?? "idle"}
                aria-pressed={selected}
                aria-label={`Pad ${address} — ${assigned ? "assigned" : "empty"}`}
                key={pad.slot}
                disabled={projectUnavailable}
                onPointerDown={(event) => controller?.pointerDown(event, pad.slot)}
                onMouseDown={(event) => controller?.pointerDown(event, pad.slot)}
                onPointerUp={(event) => controller?.pointerUp(event, pad.slot)}
                onMouseUp={(event) => controller?.pointerUp(event, pad.slot)}
                onPointerCancel={(event) => controller?.pointerCancel(event, pad.slot)}
                onKeyDown={(event) => {
                  if (!assigned || controller === undefined ||
                    (event.key !== "Enter" && event.key !== " ")) return;
                  event.preventDefault();
                  if (event.repeat) return;
                  const code = PAD_KEY_CODES[pad.slot - state.activeBank * 16];
                  if (code !== undefined) {
                    controller.keyDown({code, repeat: false, target: document.body});
                  }
                }}
                onKeyUp={(event) => {
                  if (!assigned || controller === undefined ||
                    (event.key !== "Enter" && event.key !== " ")) return;
                  event.preventDefault();
                  const code = PAD_KEY_CODES[pad.slot - state.activeBank * 16];
                  if (code !== undefined) {
                    controller.keyUp({code, repeat: false, target: document.body});
                  }
                }}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  const file = event.dataTransfer.files[0];
                  if (file === undefined) return;
                  if (!selected) {
                    dispatch({
                      type: "sample-action",
                      action: {type: "slot-selected", slot: pad.slot},
                    });
                  }
                  if (assigned) {
                    replaceReturnFocus.current = event.currentTarget;
                    setPendingFile({slot: pad.slot, file});
                  }
                  else void startLongImport({slot: pad.slot, file});
                }}
                onClick={(event) => {
                  if (!selected) {
                    dispatch({
                      type: "sample-action",
                      action: {type: "slot-selected", slot: pad.slot},
                    });
                  }
                  if (!assigned && (controller === undefined || event.detail === 0)) {
                    chooseFile(pad.slot);
                  }
                }}
              >
                <strong>{address}</strong>
                <span>{assigned ? "Assigned" : "Empty"}</span>
              </button>
            );
          })}
        </div>
      </section>

      <input
        ref={input}
        className="sample-file-input"
        type="file"
        accept=".wav,.mp3,.m4a,.aac,.flac,audio/wav,audio/wave,audio/mpeg,audio/mp4,audio/aac,audio/flac"
        aria-hidden="true"
        tabIndex={-1}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          const slot = fileSlot.current;
          event.currentTarget.value = "";
          if (file === undefined || slot === null) return;
          const assigned = isAssigned(slot);
          if (assigned) setPendingFile({slot, file});
          else void startLongImport({slot, file});
        }}
      />
      {ingestPending ? <p role="status">Decoding long source…</p> : null}
      {ingestError === null ? null : <p className="sample-error" role="alert">{ingestError}</p>}
      {longSourceDraft === null ? null : (
        <LongSourceEditor
          source={longSourceDraft.source}
          quota={longSourceDraft.quota}
          returnFocus={replaceReturnFocus.current}
          onCommit={(selection) => commitLongSource(longSourceDraft, selection)}
          onCancel={releaseLongSource}
        />
      )}
      {captureTarget === null ? null : (
        <CapturePanel
          padLabel={`Pad ${padAddress({slot: captureTarget.slot, assetId: null})}`}
          onCommit={(buffer, selection) =>
            performCaptureCommit(captureTarget, buffer, selection)}
          // The panel's modal dialog owns focus restore on close (P2-D2), so
          // onClose only clears state — a second .focus() here would race the
          // dialog's own restore.
          returnFocus={replaceReturnFocus.current}
          stopRequest={captureStopRequest}
          maxCommitFrames={captureTarget.quota.effectiveRemainingFrames}
          closeAfterResolution={closeCaptureAfterResolution}
          {...(onCapturePhaseChange === undefined
            ? {}
            : {onPhaseChange: onCapturePhaseChange})}
          {...(onContinueCaptureInSequence === undefined
            ? {}
            : {onContinueInSequence: onContinueCaptureInSequence})}
          onClose={() => setCaptureTarget(null)}
        />
      )}
      {pendingCaptureSlot === null ? null : (
        <ConfirmationDialog
          labelledBy="record-replace-heading"
          returnFocus={replaceReturnFocus.current}
          onCancel={() => setPendingCaptureSlot(null)}
        >
          <h2 id="record-replace-heading">
            Replace Pad {padAddress({slot: pendingCaptureSlot, assetId: null})}?
          </h2>
          <p>Committing a recording replaces this Pad&apos;s Sample.</p>
          <p>Replacing the Sample resets Start, End, trigger, Loop, Volume, and Mute.</p>
          <div className="confirmation-actions">
            <button type="button" onClick={() => setPendingCaptureSlot(null)}>
              Cancel replace
            </button>
            <button
              type="button"
              onClick={() => {
                const slot = pendingCaptureSlot;
                setPendingCaptureSlot(null);
                void openCapture(slot);
              }}
            >
              Confirm replace
            </button>
          </div>
        </ConfirmationDialog>
      )}
      {pendingFile === null ? null : (
        <ConfirmationDialog
          labelledBy="replace-heading"
          returnFocus={replaceReturnFocus.current}
          onCancel={() => setPendingFile(null)}
        >
          <h2 id="replace-heading">
            Replace Pad {padAddress({slot: pendingFile.slot, assetId: null})}?
          </h2>
          <p>{displayFileName(pendingFile.file.name)}</p>
          <p>Replacing the Sample resets Start, End, trigger, Loop, Volume, and Mute.</p>
          <div className="confirmation-actions">
            <button type="button" onClick={() => setPendingFile(null)}>Cancel replace</button>
            <button
              type="button"
              onClick={() => {
                const replacement = pendingFile;
                setPendingFile(null);
                void startLongImport(replacement);
              }}
            >
              Confirm replace
            </button>
          </div>
        </ConfirmationDialog>
      )}
    </main>
  );
}
