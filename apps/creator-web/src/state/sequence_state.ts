import type {SequenceRecoveryCandidate, SequenceStatus} from "../runtime/runtime_types";

export type SequencePhase =
  | "stopped"
  | "recording"
  | "switch-pending"
  | "flushing"
  | "recovery"
  | "trim-overlay";

export interface SequenceState {
  phase: SequencePhase;
  status: SequenceStatus | null;
  recovery: readonly SequenceRecoveryCandidate[];
  selectedPatternId: string | null;
  sessionId: string | null;
  lastCommandId: string | null;
  errorCode: string | null;
}

export const initialSequenceState: SequenceState = Object.freeze({
  phase: "stopped",
  status: null,
  recovery: Object.freeze([]),
  selectedPatternId: null,
  sessionId: null,
  lastCommandId: null,
  errorCode: null,
});

export type SequenceAction =
  | {type: "selected"; patternId: string}
  | {type: "authority"; status: SequenceStatus}
  | {type: "recording"; status: SequenceStatus; sessionId: string}
  | {type: "flushing"; commandId: string}
  | {type: "switch-pending"; status: SequenceStatus}
  | {type: "boundary"; status: SequenceStatus; patternId: string}
  | {type: "stopped"; status: SequenceStatus; commandId: string}
  | {type: "recovery"; candidates: readonly SequenceRecoveryCandidate[]}
  | {type: "trim-overlay"}
  | {type: "trim-closed"}
  | {type: "failed"; errorCode: string};

export function reduceSequence(
  state: SequenceState,
  action: SequenceAction,
): SequenceState {
  switch (action.type) {
    case "selected":
      return state.phase === "stopped"
        ? {...state, selectedPatternId: action.patternId}
        : state;
    case "authority":
      return {
        ...state,
        phase: state.phase === "trim-overlay" &&
          (action.status.state === "active" || action.status.state === "switching")
          ? "trim-overlay" :
          action.status.state === "recoverable" ? "recovery" :
          action.status.state === "switching" ? "switch-pending" :
          action.status.state === "active" ? "recording" : "stopped",
        status: action.status,
        selectedPatternId: action.status.patternId ?? state.selectedPatternId,
        sessionId: action.status.sessionId,
        errorCode: null,
      };
    case "recording":
      if (state.phase !== "stopped" && state.phase !== "recovery") return state;
      return {...state, phase: "recording", status: action.status,
        selectedPatternId: action.status.patternId, sessionId: action.sessionId,
        errorCode: null};
    case "flushing":
      if (!["recording", "switch-pending"].includes(state.phase)) return state;
      return {...state, phase: "flushing", lastCommandId: action.commandId};
    case "switch-pending":
      if (state.phase !== "recording") return state;
      return {...state, phase: "switch-pending", status: action.status};
    case "boundary":
      if (
        (state.phase !== "switch-pending" && state.phase !== "trim-overlay") ||
        state.status?.pendingPatternId !== action.patternId ||
        action.status.state !== "active" ||
        action.status.sessionId !== state.sessionId ||
        action.status.patternId !== action.patternId ||
        action.status.pendingPatternId !== null ||
        action.status.effectiveRuntimeFrame !== null
      ) return state;
      return {...state,
        phase: state.phase === "trim-overlay" ? "trim-overlay" : "recording",
        status: action.status,
        selectedPatternId: action.patternId};
    case "stopped":
      if (!["recording", "switch-pending", "flushing"].includes(state.phase)) return state;
      return {...state, phase: "stopped", status: action.status,
        sessionId: null, lastCommandId: action.commandId, errorCode: null};
    case "recovery":
      if (state.phase === "recording" || state.phase === "flushing" ||
          state.phase === "switch-pending" || state.phase === "trim-overlay") {
        return state;
      }
      return {...state, phase: action.candidates.length === 0 ? "stopped" : "recovery",
        recovery: Object.freeze([...action.candidates])};
    case "trim-overlay":
      return ["recording", "switch-pending"].includes(state.phase) &&
        state.sessionId !== null
        ? {...state, phase: "trim-overlay"}
        : state;
    case "trim-closed":
      if (state.phase !== "trim-overlay") return state;
      return {
        ...state,
        phase: state.status?.state === "active" ? "recording" :
          state.status?.state === "switching" ? "switch-pending" : "stopped",
      };
    case "failed":
      return {...state, errorCode: action.errorCode};
  }
}
