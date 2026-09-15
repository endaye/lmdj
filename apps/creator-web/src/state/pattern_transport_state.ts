import type {
  PatternTransportIntent,
  PatternTransportStatus,
} from "@lmdj/web-runtime-platform/runtime_types";

// One command this Host submitted to the global Pattern transport. The
// identity is retained across failures so a retry can reconcile the original
// operation instead of issuing a new inverse toggle.
export interface PatternTransportCommand {
  readonly commandId: string;
  readonly intent: PatternTransportIntent;
  readonly epoch: number;
  readonly expectedRevision: number | null;
}

export interface PatternTransportState {
  // Identity of the engagement for the current Project session; regenerated
  // per Project open because the runtime engagement dies with it.
  readonly sessionId: string | null;
  readonly projectId: string | null;
  // Last authoritative projection accepted from the runtime; null until the
  // first ticket or inspection lands.
  readonly status: PatternTransportStatus | null;
  // The single in-flight operation; the runtime refuses a second one, so the
  // reducer refuses it locally first.
  readonly pending: PatternTransportCommand | null;
  // Identity of the last command whose submit failed or whose outcome stayed
  // unknown; retained until an authority observation proves it settled.
  readonly lastFailed: PatternTransportCommand | null;
  readonly lastCommandId: string | null;
  // Authoring revision authority for record intents; never lowered by an
  // absent or stale observation.
  readonly expectedRevision: number | null;
  readonly errorCode: string | null;
}

export const initialPatternTransportState: PatternTransportState = Object.freeze({
  sessionId: null,
  projectId: null,
  status: null,
  pending: null,
  lastFailed: null,
  lastCommandId: null,
  expectedRevision: null,
  errorCode: null,
});

export type PatternTransportAction =
  | {type: "engaged"; sessionId: string; projectId: string; revision: number | null}
  | {type: "disengaged"}
  | {type: "requested"; command: PatternTransportCommand}
  | {type: "submitted"; commandId: string; status: PatternTransportStatus}
  | {type: "observed"; status: PatternTransportStatus}
  | {type: "failed"; command: PatternTransportCommand; errorCode: string}
  | {type: "observe-failed"; errorCode: string}
  | {type: "revision"; revision: number | null};

const BUSY_PHASES: readonly string[] = [
  "preparing",
  "awaiting_audio",
  "flushing",
  "reconciling",
];

export function selectTransportBusy(state: PatternTransportState): boolean {
  return state.pending !== null ||
    (state.status !== null && BUSY_PHASES.includes(state.status.phase));
}

export function selectTransportPlaying(state: PatternTransportState): boolean {
  return state.status?.playing === true;
}

export function selectTransportRecording(state: PatternTransportState): boolean {
  return state.status?.recording === true;
}

// An observation is stale when it predates the accepted projection or the
// in-flight command: epochs are monotone per runtime generation, and an older
// generation can never describe a newer one.
function isStale(
  state: PatternTransportState,
  status: PatternTransportStatus,
): boolean {
  const current = state.status;
  if (current !== null) {
    if (status.runtimeGeneration < current.runtimeGeneration) return true;
    if (status.runtimeGeneration === current.runtimeGeneration &&
        status.transportEpoch < current.transportEpoch) return true;
  }
  return state.pending !== null && status.transportEpoch < state.pending.epoch;
}

function applyStatus(
  state: PatternTransportState,
  status: PatternTransportStatus,
): PatternTransportState {
  if (!status.engaged) {
    // engaged: false answers the inspection of this session's own identity,
    // so it is current ownership authority, never a stale projection. It is
    // the clean state before the first command, but with an operation in
    // flight it means the owning engagement is gone: retain the command
    // identity as failed and say so.
    if (state.pending !== null || state.lastFailed !== null) {
      return {
        ...state,
        status,
        pending: null,
        lastFailed: state.pending ?? state.lastFailed,
        errorCode: "HOST_STATE_INVALID",
      };
    }
    return {...state, status};
  }
  if (isStale(state, status)) return state;
  const settlesPending = state.pending !== null &&
    status.transportEpoch >= state.pending.epoch &&
    (status.phase === "idle" || status.phase === "error");
  const clearsFailure = state.lastFailed !== null &&
    status.transportEpoch >= state.lastFailed.epoch &&
    status.phase === "idle";
  return {
    ...state,
    status,
    pending: settlesPending ? null : state.pending,
    lastFailed: clearsFailure ? null : state.lastFailed,
    errorCode: status.phase === "error"
      ? status.error?.code ?? "INTERNAL_ERROR"
      : (settlesPending || clearsFailure ? null : state.errorCode),
  };
}

export function reducePatternTransport(
  state: PatternTransportState,
  action: PatternTransportAction,
): PatternTransportState {
  switch (action.type) {
    case "engaged":
      return {
        ...initialPatternTransportState,
        sessionId: action.sessionId,
        projectId: action.projectId,
        expectedRevision: action.revision,
      };
    case "disengaged":
      return initialPatternTransportState;
    case "requested":
      if (state.pending !== null || state.sessionId === null) return state;
      return {
        ...state,
        pending: action.command,
        lastCommandId: action.command.commandId,
        errorCode: null,
      };
    case "submitted":
      if (state.pending?.commandId !== action.commandId) return state;
      return applyStatus(state, action.status);
    case "observed":
      return applyStatus(state, action.status);
    case "failed":
      return {
        ...state,
        pending: null,
        lastFailed: action.command,
        lastCommandId: action.command.commandId,
        errorCode: action.errorCode,
      };
    case "observe-failed":
      return {...state, errorCode: action.errorCode};
    case "revision":
      if (action.revision === null) return state;
      return {
        ...state,
        expectedRevision: Math.max(state.expectedRevision ?? 0, action.revision),
      };
  }
}
