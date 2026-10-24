import {
  NO_ROOM_MESSAGE,
  PUBLIC_ERROR_CODES,
  sampleMessage,
  sampleNextStep,
} from "../state/error_messages";
import {useReportFailure} from "../runtime/diagnostics_context";
import {useCallback, useEffect, useMemo, useRef, useState, type ReactNode} from "react";
import {createSampleEncoderTurn, type SampleEncoderParameter} from "../state/sample_encoder";
import type {ContextualEncoders, ContextualNavigation} from "./physical_controls";

import {ConfirmationDialog, SampleControls} from "./sample_controls";
import {WaveformEditor} from "./waveform_editor";
import {
  cancelSamplePreviewJourney,
  captureCommitJourney,
  importAssignSampleJourney,
  inspectSampleJourney,
  previewSampleDraftJourney,
  queryWaveformJourney,
  resetSampleJourney,
  deleteSampleJourney,
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
  samplePlayheadFrameAt,
  selectSampleEditingPlayback,
  updateSampleDraft,
  waveformWindowForViewport,
  type SamplePendingAction,
} from "../state/sample_state";
import type {CapturePhase} from "../state/capture_state";
import {
  type CreatorAction,
  type CreatorState,
} from "../state/creator_state";
import {padAddress, slotAddress} from "../state/view_model";
import {candidateSources, type CandidateSource} from "../state/candidate_state";
import "./sample_pad_layout.css";
import type {CreatorPadAssignmentRuntimeSession, PadAssignmentRequest} from "../runtime/runtime_types";

export interface SampleAssignmentControls {
  readonly session: CreatorPadAssignmentRuntimeSession;
  readonly busy: boolean;
  // A retired session's unknown request remains visible and is never replaced
  // with a new assignment command; it does not fence fresh Project recovery.
  readonly unresolved?: boolean;
  readonly reconfirmationRequired?: boolean;
  onAssign(request: Readonly<PadAssignmentRequest>): Promise<void>;
}

interface AssignmentDraft {
  readonly context: object;
  readonly projectId: string;
  readonly revision: number;
  readonly session: CreatorPadAssignmentRuntimeSession;
  readonly sources: readonly CandidateSource[];
  readonly assetId: string;
  readonly slot: number;
  readonly destinationConfirmed: boolean;
  readonly occupiedAssetId: string | null;
  readonly phase: "loading" | "choose" | "checking" | "confirm";
  readonly error: string | null;
}

const SAMPLE_PAGES = [
  ["trim", "Trim"], ["playback", "Playback"], ["tone", "Tone / EQ"], ["pad", "Pad"],
] as const;
type SamplePage = typeof SAMPLE_PAGES[number][0];

interface SampleSurfaceProps {
  assignment?: SampleAssignmentControls;
  renderPadColourControls?: ((actions: ReactNode) => ReactNode) | null;
  padAction?: ReactNode;
  state: CreatorState;
  externalCaptureBusy?: boolean;
  session?: CreatorSampleRuntimeSession;
  padDropIntent?: {current: (slot: number, file: File, target: HTMLElement) => void};
  filePickIntent: {current: (slot: number) => void};
  dispatch: (action: CreatorAction) => void;
  captureStopRequest?: number;
  onCaptureSlotChange?(slot: number | null): void;
  onCapturePhaseChange?(phase: CapturePhase): void;
  onCaptureGesture?(event: {isTrusted: boolean}): void;
  onContinueCaptureInSequence?(): void;
  closeCaptureAfterResolution?: boolean;
  captureBackgrounded?: boolean;
  encodersActive?: boolean;
  onEncodersReady?: (encoders: ContextualEncoders | null) => void;
  onNavigationReady?: (navigation: ContextualNavigation | null) => void;
  onUpdatePendingChange?: (owner: Readonly<SampleUpdateOwner> | null) => void;
  sequenceCapture?: Readonly<{
    sessionId: string;
    expectedRevision: number;
  }>;
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

// Consumer journey ownership, not evidence that a transport sent a command.
export interface SampleUpdateOwner {
  readonly projectId: string;
  readonly pending: Readonly<SamplePendingAction>;
  readonly session: CreatorSampleRuntimeSession;
}

interface PendingSampleUpdate {
  readonly owner: Readonly<SampleUpdateOwner>;
  result: Readonly<{kind: "resolution"; resolution: SampleMutationResolution}> |
    Readonly<{kind: "failure"; error: ReturnType<typeof publicOperationError>}> | null;
  phase: "waiting" | "projecting" | "failed";
  projectionSession: CreatorSampleRuntimeSession | null;
}


function publicOperationError(
  error: unknown,
): Readonly<{code: string; message: string; details?: Readonly<Record<string, unknown>>}> {
  const candidate = (error as TypedRuntimeError | null)?.code;
  const code = candidate !== undefined && PUBLIC_ERROR_CODES.has(candidate)
    ? candidate
    : "INTERNAL_ERROR";
  const details = (error as TypedRuntimeError | null)?.details;
  return Object.freeze({
    code,
    message: sampleMessage(code).message,
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
        ? `${slotAddress(bank * 16 + pad)}: ${(frames / 48_000).toFixed(2)} s`
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
  assignment,
  renderPadColourControls,
  padAction,
  state,
  session,
  padDropIntent,
  filePickIntent,
  dispatch,
  captureStopRequest = 0,
  externalCaptureBusy = false,
  onCaptureSlotChange,
  onCapturePhaseChange,
  onCaptureGesture,
  onContinueCaptureInSequence,
  closeCaptureAfterResolution = false,
  captureBackgrounded = false,
  encodersActive = true,
  onEncodersReady,
  onNavigationReady,
  onUpdatePendingChange,
  sequenceCapture,
}: SampleSurfaceProps) {
  // #1680: every Sample failure keeps its code and details in Developer
  // diagnostics; the surface shows only the user-language message.
  const reportFailure = useReportFailure();
  const recordedFailure = (operation: string, error: unknown) => {
    reportFailure(operation, error);
    return publicOperationError(error);
  };
  const [page, setPage] = useState<SamplePage>("trim");
  const input = useRef<HTMLInputElement | null>(null);
  const fileSlot = useRef<number | null>(null);
  const replaceReturnFocus = useRef<HTMLElement | null>(null);
  const importController = useRef<AbortController | null>(null);
  const operationPending = useRef<Readonly<SamplePendingAction> | null>(null);
  const pendingUpdate = useRef<PendingSampleUpdate | null>(null);
  const renderedPendingUpdate = pendingUpdate.current;
  const [updateSettlementVersion, setUpdateSettlementVersion] = useState(0);
  const previousProjectionActive = useRef(encodersActive);
  const [projectionReentryVersion, setProjectionReentryVersion] = useState(0);
  const importPending = useRef<Readonly<SamplePendingAction> | null>(null);
  const previousSession = useRef(session);
  const previewEpoch = useRef(0);
  const previewOwner = useRef<PreviewOwner | null>(null);
  const ingestEpoch = useRef(0);
  const ingestOwner = useRef<DecodedLongSource | null>(null);
  const ingestSlot = useRef<number | null>(null);
  const [pendingFile, setPendingFile] = useState<PendingFile | null>(null);
  const [longSourceDraft, setLongSourceDraft] = useState<LongSourceDraft | null>(null);
  const [ingestPending, setIngestPending] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);
  // Slot whose Replace confirmation is pending before the capture panel opens
  // (S8-D12), and the slot the open panel records into.
  const [pendingCaptureSlot, setPendingCaptureSlot] = useState<number | null>(null);
  const [captureTarget, setCaptureTarget] = useState<CaptureTarget | null>(null);
  const sample = state.sample;
  const projectIdentity = state.project.current?.projectId ?? null;
  const updateContext = useRef({projectIdentity, session});
  updateContext.current = {projectIdentity, session};
  const audioSuspended = state.audio.phase !== "running" &&
    state.audio.phase !== "recovering";
  const previousAudioSuspended = useRef(audioSuspended);
  const inspect = sample.inspect;
  const selectedSlot = sample.selectedSlot;
  const assignmentContext = useMemo(() => ({}), [assignment?.session, assignment?.reconfirmationRequired,
    projectIdentity, state.project.current?.revision, selectedSlot, page, encodersActive]);
  const assignmentContextRef = useRef(assignmentContext);
  assignmentContextRef.current = assignmentContext;
  const assignmentDraftRef = useRef<AssignmentDraft | null>(null);
  const [assignmentDraft, setAssignmentDraft] = useState<AssignmentDraft | null>(null);
  const assignmentReturnFocus = useRef<HTMLElement | null>(null);
  const assignmentView = useRef({assignment, project: state.project.current});
  assignmentView.current = {assignment, project: state.project.current};
  const storeAssignmentDraft = (draft: AssignmentDraft | null) => {
    assignmentDraftRef.current = draft;
    setAssignmentDraft(draft);
  };
  const ownsAssignmentDraft = (draft: AssignmentDraft) =>
    assignmentDraftRef.current === draft && assignmentContextRef.current === draft.context &&
    assignmentView.current.assignment?.session === draft.session &&
    assignmentView.current.project?.projectId === draft.projectId &&
    assignmentView.current.project?.revision === draft.revision;
  useEffect(() => {
    assignmentDraftRef.current = null;
    setAssignmentDraft(null);
    return () => {assignmentDraftRef.current = null;};
  }, [assignmentContext]);
  const [encoderGroup, setEncoderGroup] = useState<"trim" | "sound">("trim");
  const encoderCallbacks = useRef({preview: (_playback: Readonly<PadPlayback>) => {},
    commit: (_playback: Readonly<PadPlayback>) => {}, cancel: () => {}});
  const encoderTurn = useRef<ReturnType<typeof createSampleEncoderTurn> | null>(null);
  encoderTurn.current ??= createSampleEncoderTurn({
    schedule: (callback, delay) => window.setTimeout(callback, delay),
    clear: (handle) => window.clearTimeout(handle as number),
    preview: (playback) => encoderCallbacks.current.preview(playback),
    commit: (playback) => encoderCallbacks.current.commit(playback),
    cancel: () => encoderCallbacks.current.cancel(),
  });
  const encoderTarget = useRef<string | null>(null);
  const numericEditorCancel = useRef<(() => void) | null>(null);
  const [numericEditorOpen, setNumericEditorOpen] = useState(false);
  const bindNumericEditorCancel = useCallback((cancel: (() => void) | null) => {
    numericEditorCancel.current = cancel;
    setNumericEditorOpen(cancel !== null);
  }, []);
  const [animatedPlayhead, setAnimatedPlayhead] = useState<Readonly<{
    sequence: number;
    sourceFrame: number;
  }> | null>(null);
  const playheadFrame = sample.playhead === null
    ? null
    : animatedPlayhead?.sequence === sample.playhead.sequence
      ? animatedPlayhead.sourceFrame
      : samplePlayheadFrameAt(sample.playhead, sample.playhead.runtimeFrame);

  useEffect(() => {
    const playhead = sample.playhead;
    if (playhead === null) {
      setAnimatedPlayhead(null);
      return;
    }
    setAnimatedPlayhead({
      sequence: playhead.sequence,
      sourceFrame: samplePlayheadFrameAt(playhead, playhead.runtimeFrame),
    });
    let animationFrame = window.requestAnimationFrame(function advance(now) {
      const elapsedMilliseconds = Math.max(0, now - playhead.observedAtMilliseconds);
      const runtimeFrame = playhead.runtimeFrame + Math.floor(
        elapsedMilliseconds * 48_000 / 1_000,
      );
      setAnimatedPlayhead({
        sequence: playhead.sequence,
        sourceFrame: samplePlayheadFrameAt(playhead, runtimeFrame),
      });
      animationFrame = window.requestAnimationFrame(advance);
    });
    return () => { window.cancelAnimationFrame(animationFrame); };
  }, [sample.playhead]);

  useEffect(() => {
    onCaptureSlotChange?.(captureTarget?.slot ?? null);
  }, [captureTarget, onCaptureSlotChange]);

  const releaseLongSource = useCallback(() => {
    ingestEpoch.current += 1;
    const source = ingestOwner.current;
    ingestOwner.current = null;
    source?.release();
    setLongSourceDraft(null);
    ingestSlot.current = null;
    setIngestPending(false);
  }, []);

  const clearOwnedPreview = useCallback(() => {
    const owner = previewOwner.current;
    if (owner === null) return;
    previewOwner.current = null;
    const epoch = ++previewEpoch.current;
    void cancelSamplePreviewJourney(owner.session, owner.slot).then(
      () => {
        if (previewEpoch.current === epoch) {
          dispatch({type: "sample-action", action: {type: "preview-cleared"}});
        }
      },
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
    const retainedUpdate = pendingUpdate.current?.owner.pending === pending;
    if (!retainedUpdate) operationPending.current = null;
    importPending.current = null;
    importController.current?.abort();
    importController.current = null;
    if (pending !== null && !retainedUpdate) {
      dispatch({
        type: "sample-action",
        action: {type: "operation-cancelled", pending},
      });
    }
  }, [clearOwnedPreview, dispatch, releaseLongSource, session]);

  useEffect(() => {
    // Pair this render's reducer state with its own operation. An older
    // passive closure must not restore or settle a later update from the ref.
    const update = renderedPendingUpdate;
    if (update === null || pendingUpdate.current !== update) return;
    const {owner, result} = update;
    const finish = () => {
      if (pendingUpdate.current !== update) return;
      if (operationPending.current === owner.pending) operationPending.current = null;
      pendingUpdate.current = null;
      onUpdatePendingChange?.(null);
      setUpdateSettlementVersion((value) => value + 1);
    };
    if (update.projectionSession !== null && update.projectionSession !== session) {
      // Project reopen can replace the reducer's pending/projection state. The
      // original receipt remains available; only its readback is resumed.
      update.phase = "waiting";
      update.projectionSession = null;
    }
    if (projectIdentity !== owner.projectId) {
      // No result from the old Project is dispatched into a replacement.
      // Ordinary App Project changes stay fenced while this journey is owned.
      if (result !== null) finish();
      return;
    }
    if (session === undefined || state.runtime.phase !== "ready" ||
        state.project.phase !== "ready") return;
    if (update.phase !== "waiting") {
      if (state.sampleProjectionRefresh === null && sample.pendingAction === null) finish();
      return;
    }
    if (sample.pendingAction === null) {
      // This effect precedes the default selection effect. A same-Project
      // Runtime reopen resets selection and pending together; reinstall the
      // original pending identity before selecting the current bank's Pad.
      if (pendingUpdate.current !== update ||
          (selectedSlot !== null && selectedSlot !== owner.pending.slot)) return;
      operationPending.current = owner.pending;
      dispatch({type: "sample-action", action: {type: "pending-began", pending: owner.pending}});
      return;
    }
    if (pendingUpdate.current !== update ||
        sample.pendingAction.kind !== owner.pending.kind ||
        sample.pendingAction.slot !== owner.pending.slot ||
        sample.pendingAction.expectedRevision !== owner.pending.expectedRevision ||
        state.sampleProjectionRefresh !== null || result === null) return;
    update.projectionSession = session;
    operationPending.current = null;
    if (result.kind === "failure") {
      update.phase = "failed";
      dispatch({type: "sample-action", action: {type: "draft-cancelled"}});
      dispatch({type: "sample-action", action: {type: "preview-cleared"}});
      dispatch({type: "sample-action", action: {
        type: "operation-failed", pending: owner.pending, error: result.error,
      }});
    } else {
      update.phase = "projecting";
      const resolution = result.resolution;
      dispatch({type: "sample-projection-refresh-started", action: resolution.kind === "committed"
        ? {type: "mutation-committed", pending: owner.pending,
            inspect: resolution.inspect, commit: resolution.commit}
        : {type: "mutation-conflicted", pending: owner.pending, inspect: resolution.inspect}});
    }
  }, [dispatch, onUpdatePendingChange, projectIdentity, renderedPendingUpdate,
    sample.pendingAction, selectedSlot, session, state, updateSettlementVersion]);

  const previousProjectIdentity = useRef(projectIdentity);
  useEffect(() => {
    if (previousProjectIdentity.current === projectIdentity) return;
    previousProjectIdentity.current = projectIdentity;
    releaseLongSource();
    setCaptureTarget(null);
  }, [projectIdentity, releaseLongSource]);

  // Audio recovery owns decoded long-source memory only. It must not close an
  // open capture panel: a real focus loss on macOS Safari interrupts the
  // AudioContext, so recovery arrives in the same moment the panel's own blur
  // listener stops the recording and retains the take. Clearing the target
  // here unmounted the panel and discarded that take with no way to commit or
  // discard it (#738). The panel closes through its own Close/Commit/Discard
  // controls, exactly as it already does across a Runtime session replacement.
  useEffect(() => {
    if (state.audio.phase !== "recovering") return;
    releaseLongSource();
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
    const wasActive = previousProjectionActive.current;
    previousProjectionActive.current = encodersActive;
    // A retained hidden surface still settles in the background. Reentry
    // restarts only its existing readback, as a fresh Sample mount used to.
    if (encodersActive && !wasActive && state.sampleProjectionRefresh !== null) {
      setProjectionReentryVersion((value) => value + 1);
    }
  }, [encodersActive, state.sampleProjectionRefresh]);

  useEffect(() => {
    const refresh = state.sampleProjectionRefresh;
    const currentProject = state.project.current;
    if (refresh === null || session === undefined || currentProject === null ||
        state.runtime.phase !== "ready" || state.project.phase !== "ready") return;
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
  }, [dispatch, session, state.project.current, state.project.phase,
    state.runtime.phase, state.sampleProjectionRefresh, projectionReentryVersion]);

  const dispatchResolution = (
    pending: Readonly<SamplePendingAction>,
    resolution: SampleMutationResolution,
  ): void => {
    if (operationPending.current !== pending) return;
    operationPending.current = null;
    if (importPending.current === pending) importPending.current = null;
    if (resolution.kind === "committed" && resolution.commit.snapshotError !== null) {
      reportFailure("Prepare saved Sample", resolution.commit.snapshotError);
    }
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

  // A voice can sound only while audio runs, and the Runtime refuses
  // `sample.stop` otherwise (#1724). The Host's own mutation also stops the
  // voice when audio runs, so with audio stopped there is nothing to stop.
  const stopBeforeMutation = async (slot: number) => {
    if (session === undefined || audioSuspended) return;
    if (await session.stopPad(slot) !== true) {
      throw Object.assign(new Error("Sample stop failed"), {code: "HOST_STATE_INVALID"});
    }
  };

  const performUpdate = async (playback: Readonly<PadPlayback>) => {
    if (session === undefined || inspect === null || projectIdentity === null || sample.pendingAction !== null ||
        assignmentView.current.assignment?.busy === true ||
      operationPending.current !== null) return;
    previewEpoch.current += 1;
    const pending = Object.freeze({
      kind: "update" as const,
      slot: inspect.slot,
      expectedRevision: inspect.projectRevision,
    });
    operationPending.current = pending;
    dispatch({type: "sample-action", action: {type: "pending-began", pending}});
    let update: PendingSampleUpdate | null = null;
    try {
      if (playback.muted !== inspect.playback.muted) {
        await stopBeforeMutation(inspect.slot);
      }
      if (operationPending.current !== pending ||
          updateContext.current.session !== session ||
          updateContext.current.projectIdentity !== projectIdentity) return;
      update = {owner: Object.freeze({projectId: projectIdentity, pending, session}),
        result: null, phase: "waiting", projectionSession: null};
      pendingUpdate.current = update;
      onUpdatePendingChange?.(update.owner);
      setUpdateSettlementVersion((value) => value + 1);
      const resolution = await updateSampleJourney(session, {
        slot: inspect.slot,
        expectedRevision: inspect.projectRevision,
        playback,
      });
      if (previewOwner.current?.session === session) previewOwner.current = null;
      if (pendingUpdate.current !== update) return;
      if (resolution.kind === "committed" && resolution.commit.snapshotError !== null) {
        reportFailure("Prepare saved Sample", resolution.commit.snapshotError);
      }
      update.result = {kind: "resolution", resolution};
      setUpdateSettlementVersion((value) => value + 1);
    } catch (error) {
      if (update !== null) {
        if (previewOwner.current?.session === session) previewOwner.current = null;
        if (pendingUpdate.current !== update) return;
        update.result = {kind: "failure", error: recordedFailure("Update Pad", error)};
        setUpdateSettlementVersion((value) => value + 1);
        return;
      }
      clearOwnedPreview();
      if (operationPending.current !== pending) return;
      operationPending.current = null;
      dispatch({type: "sample-action", action: {type: "draft-cancelled"}});
      dispatch({type: "sample-action", action: {type: "preview-cleared"}});
      dispatch({
        type: "sample-action",
        action: {type: "operation-failed", pending, error: recordedFailure("Update Pad", error)},
      });
    }
  };

  const preview = (playback: Readonly<PadPlayback>) => {
    if (session === undefined || inspect === null || sample.pendingAction !== null ||
      operationPending.current !== null) return;
    const epoch = ++previewEpoch.current;
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
    // Editing is available before audio activation. The visual draft still
    // previews, but the stopped Host cannot accept an audible preview.
    if (audioSuspended) return;
    previewOwner.current = {session, slot: inspect.slot};
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

  const cancelPreview = useCallback(() => {
    dispatch({type: "sample-action", action: {type: "draft-cancelled"}});
    clearOwnedPreview();
  }, [dispatch, clearOwnedPreview]);
  const selectPage = useCallback((target: SamplePage) => {
    if (!encodersActive || page === target) return;
    encoderTurn.current?.cancel();
    numericEditorCancel.current?.();
    cancelPreview();
    setPage(target);
  }, [encodersActive, page, cancelPreview]);
  const navigation = useMemo<ContextualNavigation>(() => {
    const index = SAMPLE_PAGES.findIndex(([target]) => target === page);
    return {directionStep: {
      backLabel: "Previous Sample page — ←", forwardLabel: "Next Sample page — →",
      backAvailable: index > 0, forwardAvailable: index < SAMPLE_PAGES.length - 1,
      onBack: () => {
        const target = SAMPLE_PAGES[index - 1]?.[0];
        if (target !== undefined) selectPage(target);
      },
      onForward: () => {
        const target = SAMPLE_PAGES[index + 1]?.[0];
        if (target !== undefined) selectPage(target);
      },
    }};
  }, [page, selectPage]);
  useEffect(() => {
    onNavigationReady?.(encodersActive ? navigation : null);
    return () => onNavigationReady?.(null);
  }, [onNavigationReady, encodersActive, navigation]);

  const reset = async () => {
    if (assignmentView.current.assignment?.busy === true) return;
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
        action: {type: "operation-failed", pending, error: recordedFailure("Reset Pad", error)},
      });
    }
  };

  const deleteSelectedPad = async () => {
    if (assignmentView.current.assignment?.busy === true) return;
    if (session === undefined || inspect === null || selectedSlot !== inspect.slot ||
        state.project.phase !== "ready" ||
        inspect.projectRevision !== state.project.current?.revision || captureTarget !== null) return;
    const previous = operationPending.current ?? sample.pendingAction;
    if (previous !== null && (previous.slot !== inspect.slot ||
        (previous.kind !== "import" && previous.kind !== "replace"))) return;
    if (previous !== null) {
      importController.current?.abort();
      importController.current = null;
      importPending.current = null;
      operationPending.current = null;
      dispatch({type: "sample-action", action: {type: "operation-cancelled", pending: previous}});
    }
    if (ingestSlot.current === inspect.slot || longSourceDraft?.slot === inspect.slot) {
      releaseLongSource();
    }
    if (pendingFile?.slot === inspect.slot) setPendingFile(null);
    if (pendingCaptureSlot === inspect.slot) setPendingCaptureSlot(null);
    setIngestError(null);
    const pending = Object.freeze({
      kind: "delete" as const, slot: inspect.slot, expectedRevision: inspect.projectRevision,
    });
    operationPending.current = pending;
    dispatch({type: "sample-action", action: {type: "pending-began", pending}});
    try {
      await stopBeforeMutation(inspect.slot);
      if (operationPending.current !== pending) return;
      const resolution = await deleteSampleJourney(session, {
        slot: inspect.slot, expectedRevision: inspect.projectRevision,
      });
      if (operationPending.current !== pending) return;
      previewOwner.current = null;
      dispatchResolution(pending, resolution);
    } catch (error) {
      if (operationPending.current !== pending) return;
      operationPending.current = null;
      dispatch({type: "sample-action", action: {
        type: "operation-failed", pending, error: recordedFailure("Delete Pad", error),
      }});
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
      options: {
        slot: number;
        expectedRevision: number;
        sequenceSessionId?: string;
        signal: AbortSignal;
      },
    ) => Promise<SampleMutationResolution>,
    context?: Readonly<{expectedRevision: number; sequenceSessionId?: string}>,
  ): Promise<ImportOutcome> => {
    if (assignmentView.current.assignment?.busy === true) return BUSY_OUTCOME;
    if (session === undefined || sample.pendingAction !== null ||
      operationPending.current !== null) return BUSY_OUTCOME;
    const expectedRevision = context?.expectedRevision ??
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
        ...(context?.sequenceSessionId === undefined
          ? {}
          : {sequenceSessionId: context.sequenceSessionId}),
        signal: controller.signal,
      });
      previewOwner.current = null;
      if (operationPending.current !== pending) return SUPERSEDED_OUTCOME;
      dispatchResolution(pending, resolution);
      return resolution.kind === "conflict"
        ? {kind: "conflict", message: resolution.message}
        : COMMITTED_OUTCOME;
    } catch (error) {
      if (operationPending.current !== pending) return SUPERSEDED_OUTCOME;
      clearOwnedPreview();
      operationPending.current = null;
      importPending.current = null;
      if (error instanceof DOMException && error.name === "AbortError") {
        dispatch({
          type: "sample-action",
          action: {type: "operation-cancelled", pending},
        });
        return CANCELLED_OUTCOME;
      }
      const failure = recordedFailure("Import Sample", error);
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
    ingestSlot.current = slot;
    setIngestPending(true);
    setIngestError(null);
    const epoch = ++ingestEpoch.current;
    try {
      const quota = await session.querySampleQuota(slot);
      if (ingestEpoch.current !== epoch) return;
      const source = await openLongSource(file, session.sampleIngestLimits());
      if (ingestEpoch.current !== epoch) {
        source.release();
        return;
      }
      ingestOwner.current = source;
      setLongSourceDraft({slot, source, quota});
    } catch (error) {
      if (ingestEpoch.current !== epoch) return;
      // The resource token, observed value and limit go to diagnostics only.
      const failure = recordedFailure("Read Sample source", error);
      setIngestError(error instanceof LongSourceIngestError ? error.message : failure.message);
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
      {expectedRevision: draft.quota.projectRevision},
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
    {
      expectedRevision: sequenceCapture?.expectedRevision ?? target.quota.projectRevision,
      ...(sequenceCapture === undefined
        ? {}
        : {sequenceSessionId: sequenceCapture.sessionId}),
    },
  );

  const openCapture = async (slot: number): Promise<void> => {
    if (session === undefined || externalCaptureBusy) return;
    setIngestError(null);
    try {
      const quota = await session.querySampleQuota(slot);
      if (quota.effectiveRemainingFrames < 1) {
        setIngestError(NO_ROOM_MESSAGE);
        return;
      }
      setCaptureTarget({slot, quota});
    } catch (error) {
      setIngestError(recordedFailure("Check Sample room", error).message);
    }
  };

  const chooseFile = (slot: number) => {
    if (assignmentView.current.assignment?.busy === true) return;
    replaceReturnFocus.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    fileSlot.current = slot;
    input.current?.click();
  };

  const readAssignmentCatalog = async (draft: AssignmentDraft) => {
    const catalog = candidateSources(await draft.session.inspectProject(), draft.projectId);
    if (!ownsAssignmentDraft(draft)) return null;
    const project = assignmentView.current.project;
    if (catalog.revision !== draft.revision || project === null ||
        project.pads.length !== 64 || project.pads.some((pad, slot) => pad.slot !== slot) ||
        project.pads[draft.slot]?.assetId !== draft.occupiedAssetId ||
        (draft.assetId !== "" && !catalog.sources.some(source => source.assetId === draft.assetId))) {
      throw new Error("Project changed; close ASSIGN and refresh before choosing again.");
    }
    return catalog;
  };
  const openAssignment = () => {
    const project = state.project.current;
    if (assignment === undefined || assignment.busy || assignment.unresolved === true || project === null ||
        projectUnavailable || selectedSlot === null || sample.pendingAction !== null) return;
    encoderTurn.current?.cancel();
    numericEditorCancel.current?.();
    cancelPreview();
    assignmentReturnFocus.current = document.activeElement instanceof HTMLElement
      ? document.activeElement : null;
    const draft: AssignmentDraft = {context: assignmentContext, projectId: project.projectId,
      revision: project.revision, session: assignment.session, sources: [], assetId: "",
      slot: selectedSlot, occupiedAssetId: project.pads[selectedSlot]?.assetId ?? null,
      destinationConfirmed: assignment.reconfirmationRequired !== true,
      phase: "loading", error: null};
    storeAssignmentDraft(draft);
    void readAssignmentCatalog(draft).then(catalog => {
      if (catalog !== null && ownsAssignmentDraft(draft)) {
        storeAssignmentDraft({...draft, sources: catalog.sources, phase: "choose"});
      }
    }, () => {
      if (ownsAssignmentDraft(draft)) storeAssignmentDraft({...draft, phase: "choose",
        error: "The retained source list could not be read. Close ASSIGN and refresh the Project."});
    });
  };
  const changeAssignment = (expected: AssignmentDraft, change: {assetId?: string; slot?: number}) => {
    const draft = assignmentDraftRef.current;
    if (draft === null || draft !== expected || !ownsAssignmentDraft(draft) || draft.phase === "loading") return;
    const slot = change.slot ?? draft.slot;
    storeAssignmentDraft({...draft, ...change, slot,
      destinationConfirmed: change.slot !== undefined || draft.destinationConfirmed,
      occupiedAssetId: assignmentView.current.project?.pads[slot]?.assetId ?? null,
      phase: "choose", error: null});
  };
  const submitAssignment = async (expected: AssignmentDraft) => {
    const previous = assignmentDraftRef.current;
    const controls = assignmentView.current.assignment;
    if (previous === null || previous !== expected || !ownsAssignmentDraft(previous) || controls === undefined ||
        controls.busy || controls.unresolved === true || previous.assetId === "" || !previous.destinationConfirmed ||
        !["choose", "confirm"].includes(previous.phase)) return;
    const draft: AssignmentDraft = {...previous, phase: "checking", error: null};
    storeAssignmentDraft(draft);
    try {
      const catalog = await readAssignmentCatalog(draft);
      if (catalog === null || !ownsAssignmentDraft(draft)) return;
      if (draft.occupiedAssetId !== null && previous.phase !== "confirm") {
        storeAssignmentDraft({...draft, sources: catalog.sources, phase: "confirm"});
        return;
      }
      const request = Object.freeze({commandId: crypto.randomUUID(), expectedRevision: draft.revision,
        slot: draft.slot, assetId: draft.assetId});
      // Only the unsent presentation is retired here. App owns the immutable
      // request from invocation onward, even if this surface unmounts.
      storeAssignmentDraft(null);
      await controls.onAssign(request);
    } catch {
      if (ownsAssignmentDraft(draft)) storeAssignmentDraft({...draft, phase: "choose",
        error: "Project changed or the source is unavailable. Close ASSIGN and refresh before trying again."});
    }
  };
  useEffect(() => {
    if (padDropIntent === undefined) return;
    padDropIntent.current = (slot, file, target) => {
      if (assignmentView.current.assignment?.busy === true) return;
      if (state.project.phase !== "ready" || state.project.current === null ||
          captureTarget !== null) return;
      if (selectedSlot !== slot) {
        dispatch({type: "sample-action", action: {type: "slot-selected", slot}});
      }
      replaceReturnFocus.current = target;
      if (isAssigned(slot)) setPendingFile({slot, file});
      else void startLongImport({slot, file});
    };
    return () => { padDropIntent.current = () => {}; };
  });

  const selectedAddress = selectedSlot === null
    ? "No Pad selected"
    : `Pad ${padAddress({slot: selectedSlot, assetId: inspect?.assetId ?? null})}`;
  const editablePlayback = selectSampleEditingPlayback(sample);
  const selectedAssigned = inspect?.assetId !== null && inspect?.assetId !== undefined;
  const projectUnavailable = state.project.phase !== "ready" ||
    state.project.current === null;
  const actionsDisabled = session === undefined || projectUnavailable || inspect === null ||
    !selectedAssigned || sample.pendingAction !== null || pendingUpdate.current !== null || assignment?.busy === true;
  const encoderDisabled = actionsDisabled || !encodersActive || externalCaptureBusy ||
    captureTarget !== null || state.projectProjectionRefresh !== null ||
    inspect?.slot !== selectedSlot || inspect?.projectRevision !== state.project.current?.revision;
  const encoderKey = `${state.project.current?.projectId}:${inspect?.slot}:${inspect?.assetId}:${inspect?.projectRevision}`;
  const numericEditingContext = useMemo(() => ({key: encoderKey, session}),
    [encoderKey, session]);
  const encoderContext = useRef({key: encoderKey, disabled: encoderDisabled});
  encoderContext.current = {key: encoderKey, disabled: encoderDisabled};
  encoderCallbacks.current = {
    preview,
    commit: (playback) => {
      if (encoderContext.current.disabled || encoderTarget.current !== encoderContext.current.key) {
        cancelPreview();
        return;
      }
      void performUpdate(playback);
    },
    cancel: cancelPreview,
  };
  useEffect(() => {
    if (encoderDisabled) encoderTurn.current?.cancel();
    return () => encoderTurn.current?.cancel();
  }, [encoderKey, encoderDisabled]);
  const encoders = useMemo<ContextualEncoders>(() => {
    const group: readonly SampleEncoderParameter[] = encoderGroup === "trim"
      ? ["start", "end", "pitch"] : ["gain", "pan", "tone"];
    const labels = {start: "Start", end: "End", pitch: "Pitch", gain: "Pad Volume", pan: "Pan", tone: "Tone"};
    const playback = editablePlayback;
    const metadata = inspect?.metadata;
    const value = (parameter: SampleEncoderParameter): string => {
      if (playback === undefined || metadata == null) return "—";
      switch (parameter) {
        case "start": return `${(playback.trimStartFrame / metadata.sampleRate).toFixed(5)} s`;
        case "end": return `${((playback.trimEndFrame ?? metadata.sourceFrames) / metadata.sampleRate).toFixed(5)} s`;
        case "pitch": return `${(playback.pitchCents / 100).toFixed(1)} st`;
        case "gain": return `${(playback.gainMillidb / 1000).toFixed(1)} dB`;
        case "pan": return playback.pan === 0 ? "C" : `${playback.pan < 0 ? "L" : "R"}${Math.abs(playback.pan)}`;
        case "tone": return Math.abs(playback.tone) <= 2 ? "Off" : `${playback.tone < 0 ? "LP" : "HP"} ${Math.abs(playback.tone)}`;
      }
    };
    return {pending: encoderTurn.current?.pending() === true || numericEditorOpen,
      cancel: () => {
        encoderTurn.current?.cancel();
        numericEditorCancel.current?.();
      },
      bindings: Object.fromEntries(group.map((parameter, index) => [index + 1, {
        label: labels[parameter], value: value(parameter), disabled: encoderDisabled || metadata == null,
        onTurn: (detents: number, fine = false) => {
          if (encoderContext.current.key !== encoderKey || encoderContext.current.disabled ||
            inspect === null || metadata == null || operationPending.current !== null) return;
          encoderTarget.current = encoderKey;
          encoderTurn.current?.turn(parameter, detents, fine, inspect.playback, metadata);
        },
      }]))};
  }, [encoderGroup, editablePlayback, inspect, encoderKey, encoderDisabled, numericEditorOpen]);
  useEffect(() => {
    onEncodersReady?.(encodersActive ? encoders : null);
    return () => onEncodersReady?.(null);
  }, [onEncodersReady, encodersActive, encoders]);
  const pendingDeleteAllowed = sample.pendingAction === null ||
    (sample.pendingAction.slot === selectedSlot &&
      (sample.pendingAction.kind === "import" || sample.pendingAction.kind === "replace"));
  const deleteDisabledReason = session === undefined || projectUnavailable || inspect === null
    ? "Open a Project and select a Pad to delete."
    : inspect.slot !== selectedSlot || inspect.projectRevision !== state.project.current?.revision
      ? "Refreshing the selected Pad…"
    : captureTarget !== null ? "Finish or cancel Capture before deleting a Pad."
    : assignment?.busy === true ? "Wait for the current Project change to finish."
    : !pendingDeleteAllowed ? "Wait for the current edit to finish."
    : !selectedAssigned && sample.pendingAction === null &&
      ingestSlot.current !== selectedSlot && longSourceDraft?.slot !== selectedSlot &&
      sample.lastError === null && ingestError === null ? "This Pad is already empty."
    : null;
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

  const sampleControls = inspect?.metadata != null && editablePlayback !== undefined &&
    page !== "trim" ? (
    <SampleControls
      key={selectedSlot}
      page={page}
      padLabel={selectedAddress}
      playback={editablePlayback}
      savedPlayback={inspect.playback}
      numericEditingContext={numericEditingContext}
      numericEditingDisabled={encoderDisabled}
      onBeginNumericEdit={() => {encoderTurn.current?.cancel(); cancelPreview();}}
      onNumericEditorReady={bindNumericEditorCancel}
      audioSuspended={audioSuspended}
      disabled={actionsDisabled}
      onPreview={(playback) => {encoderTurn.current?.cancel(); preview(playback);}}
      onCommit={(playback) => {encoderTurn.current?.cancel(); void performUpdate(playback);}}
      onCancel={() => {encoderTurn.current?.cancel(); cancelPreview();}}
      onReset={() => { void reset(); }}
      padAction={padAction}
    />
  ) : null;

  const fileAction = selectedSlot === null ? null : (
    <button type="button"
      className={`touch-control${selectedAssigned ? "" : " is-primary"}`}
      aria-label={selectedAssigned ? undefined : `Add Sample to ${selectedAddress}`}
      disabled={session === undefined || projectUnavailable ||
        sample.pendingAction !== null || assignment?.busy === true}
      onClick={() => chooseFile(selectedSlot)}>
      {selectedAssigned ? "Replace Sample" : "Add Sample"}
    </button>
  );
  const recordAction = selectedSlot === null ? null : (
    <button type="button" className="touch-control"
      disabled={session === undefined || projectUnavailable ||
        sample.pendingAction !== null || captureTarget !== null || externalCaptureBusy}
      onClick={() => {
        replaceReturnFocus.current = document.activeElement instanceof HTMLElement
          ? document.activeElement : null;
        // Assigned Pad recording keeps the original replacement confirmation
        // before microphone permission. Empty Pad uses the same capture owner.
        if (selectedAssigned) setPendingCaptureSlot(selectedSlot);
        else void openCapture(selectedSlot);
      }}>
      Record Sample
    </button>
  );
  const padActions = <>
    <div className="sample-pad-file-actions">{fileAction}{recordAction}</div>
    {sampleControls ?? (padAction == null ? null :
      <div className="sample-pad-edit-actions">{padAction}</div>)}
    {selectedSlot === null ? null : <div className="selected-pad-actions">
      <button type="button" className="touch-control is-danger"
        aria-label={`Delete ${selectedAddress}`}
        disabled={deleteDisabledReason !== null}
        aria-describedby={deleteDisabledReason === null ? undefined : "pad-delete-reason"}
        onClick={() => { void deleteSelectedPad(); }}>Delete Pad</button>
      {deleteDisabledReason === null ? null : <small id="pad-delete-reason">{deleteDisabledReason}</small>}
    </div>}
  </>;
  // Only an actual matching empty inspection can claim that no sound exists.
  // An assigned sound whose metadata/prepare is unavailable keeps its error path.
  const confirmedEmpty = selectedSlot !== null && inspect?.slot === selectedSlot &&
    inspect.assetId === null && inspect.projectRevision === state.project.current?.revision;

  return (
    <main className="sample-surface">
      <div className="sample-encoder-groups" role="group" aria-label="Sample encoder group">
        <button type="button" aria-pressed={encoderGroup === "trim"} onClick={() => setEncoderGroup("trim")}>Trim / Pitch</button>
        <button type="button" aria-pressed={encoderGroup === "sound"} onClick={() => setEncoderGroup("sound")}>Pad Sound</button>
      </div>
      <header className="sample-heading">
        <div>
          <p className="eyebrow">Sample surface</p>
          <h1>Sample editor</h1>
        </div>
        <div className="selected-sample" aria-live="polite">
          <strong>{selectedAddress}</strong>
        </div>
      </header>

      <button type="button" disabled={assignment === undefined || assignment.busy || assignment.unresolved === true ||
        projectUnavailable || selectedSlot === null || sample.pendingAction !== null ||
        captureTarget !== null || ingestPending}
        title={assignment === undefined ? "Retained Asset assignment is unavailable in this audio session." : undefined}
        onClick={openAssignment}>ASSIGN</button>

      {assignmentDraft === null || assignmentDraft.context !== assignmentContext ? null : (
        <ConfirmationDialog labelledBy="sample-assign-title" returnFocus={assignmentReturnFocus.current}
          onCancel={() => storeAssignmentDraft(null)}>
          <h2 id="sample-assign-title">Assign retained Asset</h2>
          <p>Choose a source retained by this Project. Its material and source Pad stay unchanged.</p>
          {assignment?.reconfirmationRequired === true ? <p>
            The previous assignment is still unresolved. Choose the source and destination for a new assignment.
          </p> : null}
          <label>Retained source
            <select aria-label="Retained source" tabIndex={assignmentDraft.phase === "loading" ? -1 : 0} value={assignmentDraft.assetId}
              disabled={assignmentDraft.phase === "loading"}
              onChange={event => changeAssignment(assignmentDraft, {assetId: event.target.value})}>
              <option value="">Choose a retained Asset</option>
              {assignmentDraft.sources.map(source => <option key={source.assetId} value={source.assetId}>
                {source.label}</option>)}
            </select>
          </label>
          <label>Destination Pad
            <select aria-label="Destination Pad" tabIndex={assignmentDraft.phase === "loading" ? -1 : 0}
              value={assignmentDraft.destinationConfirmed ? assignmentDraft.slot : ""}
              disabled={assignmentDraft.phase === "loading"}
              onChange={event => changeAssignment(assignmentDraft, {slot: Number(event.target.value)})}>
              {assignment?.reconfirmationRequired === true ? <option value="" disabled>Choose a destination</option> : null}
              {[0, 1, 2, 3].map(bank => <optgroup key={bank} label={`Bank ${String.fromCharCode(65 + bank)}`}>
                {state.project.current?.pads.slice(bank * 16, bank * 16 + 16).map(pad => (
                  <option key={pad.slot} value={pad.slot}>{slotAddress(pad.slot)}</option>
                ))}
              </optgroup>)}
            </select>
          </label>
          <p>Asset {assignmentDraft.assetId || "—"} → {assignmentDraft.destinationConfirmed
            ? slotAddress(assignmentDraft.slot) : "Choose a destination"}</p>
          {assignmentDraft.phase === "confirm" ? <p>
            Replace {slotAddress(assignmentDraft.slot)} assignment {assignmentDraft.occupiedAssetId}?
            The prior material remains retained.
          </p> : null}
          {assignmentDraft.error === null ? null : <p role="alert">{assignmentDraft.error}</p>}
          {assignmentDraft.phase === "loading" ? <p role="status">Reading retained Assets…</p> : null}
          <div className="sample-confirmation-actions">
            <button type="button" onClick={() => storeAssignmentDraft(null)}>Cancel assignment</button>
            <button key={`${assignmentDraft.assetId}:${assignmentDraft.slot}`} type="button" disabled={assignmentDraft.assetId === "" || !assignmentDraft.destinationConfirmed || assignment?.busy ||
              assignmentDraft.error !== null || !["choose", "confirm"].includes(assignmentDraft.phase)}
              onClick={() => {void submitAssignment(assignmentDraft);}}>
              {assignmentDraft.phase === "confirm" ? "Confirm replacement" : "Assign Asset"}
            </button>
          </div>
        </ConfirmationDialog>
      )}

      <nav className="sample-page-nav" aria-label="Sample pages">
        {SAMPLE_PAGES.map(([target, label]) => (
          <button key={target} type="button"
            aria-current={page === target ? "page" : undefined}
            onClick={() => selectPage(target)}>
            {label}
          </button>
        ))}
      </nav>

      {page === "pad" ? (
        <section className="sample-pad-management" aria-label={`${selectedAddress} management`}>
          {renderPadColourControls?.(padActions) ?? padActions}
          <details className="sample-details">
            <summary className="touch-control">Sample details</summary>
            <dl>
              <div><dt>Asset ID</dt><dd>{inspect?.assetId ?? "No Sample assigned"}</dd></div>
              <div><dt>Source</dt><dd>{metadataCopy(state)}</dd></div>
              <div><dt>Revision</dt><dd>{inspect?.projectRevision ?? "—"}</dd></div>
            </dl>
          </details>
        </section>
      ) : null}

      {inspect !== null && inspect.metadata !== null && editablePlayback !== undefined ? (
        <>
          {page === "trim" ? <WaveformEditor
            key={`${inspect.slot}:${inspect.waveformCacheIdentity ?? "none"}`}
            padLabel={selectedAddress}
            envelope={sample.waveform}
            metadata={inspect.metadata}
            projectRevision={inspect.projectRevision}
            playback={editablePlayback}
            playheadFrame={playheadFrame}
            disabled={actionsDisabled}
            previewActive={sample.draft !== null}
            onPreview={(playback) => {encoderTurn.current?.cancel(); preview(playback);}}
            onCommit={(playback) => {encoderTurn.current?.cancel(); void performUpdate(playback);}}
            onCancel={() => {encoderTurn.current?.cancel(); cancelPreview();}}
            {...(queryViewportWaveform === undefined
              ? {}
              : {onQueryWaveform: queryViewportWaveform})}
          /> : null}
          {page !== "pad" ? sampleControls : null}
        </>
      ) : page !== "pad" ? (
        <section className="empty-sample" aria-label="Selected Pad Sample">
          {confirmedEmpty ? <div className="empty-sample-card">
            <h2>Make room for a new sound.</h2>
            <p>Hold {selectedAddress} to record. Or choose an audio file below.</p>
          </div> : <p>Select an assigned Pad to edit its waveform and playback.</p>}
          {fileAction}
          {confirmedEmpty ? <>
            {recordAction}
            <p className="empty-sample-permission">First microphone use asks for permission.
              After allowing it, hold the Pad again.</p>
          </> : null}
        </section>
      ) : null}

      {sample.lastError === null ? null : (
        <div className="sample-error" role="alert">
          <p>{sample.lastError.message}</p>
          {sampleNextStep(sample.lastError) === "" ? null
            : <p className="sample-next-step">{sampleNextStep(sample.lastError)}</p>}
          {quotaErrorCopy(sample.lastError) === null
            ? null
            : <p>{quotaErrorCopy(sample.lastError)}</p>}
        </div>
      )}

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
          onDelete={() => { void deleteSelectedPad(); }}
        />
      )}
      {captureTarget === null ? null : (
        <CapturePanel
          recordingBusy={externalCaptureBusy}
          {...(onCaptureGesture === undefined ? {} : {onRecordGesture: onCaptureGesture})}
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
          backgrounded={captureBackgrounded}
          {...(onCapturePhaseChange === undefined
            ? {}
            : {onPhaseChange: onCapturePhaseChange})}
          {...(onContinueCaptureInSequence === undefined
            ? {}
            : {onContinueInSequence: onContinueCaptureInSequence})}
          onClose={() => {
            onCapturePhaseChange?.("idle");
            setCaptureTarget(null);
          }}
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
