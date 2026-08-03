export const HOST_STATES = Object.freeze([
  "cold",
  "preflight",
  "storage-ready",
  "core-ready",
  "audio-suspended",
  "running",
  "interrupted",
  "recovering",
  "closed",
  "failed",
]);

const STATE_SET = new Set(HOST_STATES);
const TERMINAL_STATES = new Set(["closed", "failed"]);
const NONTERMINAL_STATES = new Set(
  HOST_STATES.filter((state) => !TERMINAL_STATES.has(state)),
);
const NEXT_STATES = Object.freeze({
  cold: Object.freeze(["preflight"]),
  preflight: Object.freeze(["storage-ready"]),
  "storage-ready": Object.freeze(["core-ready"]),
  "core-ready": Object.freeze(["audio-suspended"]),
  "audio-suspended": Object.freeze(["running"]),
  running: Object.freeze(["audio-suspended", "interrupted"]),
  interrupted: Object.freeze(["recovering"]),
  recovering: Object.freeze(["running", "audio-suspended"]),
});

export class HostStateError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "HostStateError";
    this.code = "HOST_STATE_INVALID";
    this.details = details;
  }
}

export function createHostStateMachine({
  initialState = "cold",
  notify = () => {},
  sealTake = () => {},
  cleanup = () => {},
} = {}) {
  if (!STATE_SET.has(initialState)) {
    throw new TypeError("Unknown initial Host state");
  }
  if (
    typeof notify !== "function" ||
    typeof sealTake !== "function" ||
    typeof cleanup !== "function"
  ) {
    throw new TypeError("Host state side effects must be injected functions");
  }

  let state = initialState;
  let activeTakeId = null;
  let transitionInProgress = false;

  function invalid(message, details = {}) {
    throw new HostStateError(message, { state, ...details });
  }

  function rejectMutationDuringTransition(operation) {
    if (transitionInProgress) {
      invalid("Host operation is blocked during a state transition", {
        operation,
        transition_in_progress: true,
      });
    }
  }

  function isAllowedTransition(nextState) {
    if (!STATE_SET.has(nextState) || TERMINAL_STATES.has(state)) {
      return false;
    }
    if (nextState === "closed" || nextState === "failed") {
      return NONTERMINAL_STATES.has(state);
    }
    return NEXT_STATES[state]?.includes(nextState) ?? false;
  }

  function sealActiveTake(reason) {
    if (activeTakeId === null) {
      return null;
    }
    const sealed = Object.freeze({
      take_id: activeTakeId,
      outcome: "capture_incomplete",
      reason,
    });
    activeTakeId = null;
    sealTake(sealed);
    return sealed;
  }

  function transition(nextState, { reason = "host_lifecycle" } = {}) {
    if (transitionInProgress) {
      invalid("Reentrant Host state transitions are not allowed", {
        next_state: nextState,
        transition_in_progress: true,
      });
    }
    if (!isAllowedTransition(nextState)) {
      invalid("Transition is not present in the locked Host state table", {
        next_state: nextState,
      });
    }
    transitionInProgress = true;
    try {
      const previousState = state;
      const requiresCleanup =
        nextState === "interrupted" ||
        nextState === "failed" ||
        nextState === "closed";
      const requiresCaptureSeal =
        requiresCleanup ||
        (previousState === "running" && nextState === "audio-suspended");
      const sealed = requiresCaptureSeal ? sealActiveTake(reason) : null;
      if (requiresCleanup) {
        cleanup(nextState, { reason });
      }

      state = nextState;
      if (sealed !== null) {
        notify("capture.sealed", sealed);
      }
      notify("host.state_changed", {
        previous_state: previousState,
        state: nextState,
      });
      if (nextState === "interrupted") {
        notify("audio.interrupted", { reason });
      }
      if (previousState === "recovering" && nextState === "running") {
        notify("audio.recovered", {});
      }
      return state;
    } finally {
      transitionInProgress = false;
    }
  }

  function allowsOperation(operation) {
    if (transitionInProgress) {
      return false;
    }
    if (operation === "trigger" || operation === "take.begin") {
      return state === "running";
    }
    if (operation === "audio.suspend") {
      return state === "running" || state === "audio-suspended";
    }
    return !TERMINAL_STATES.has(state);
  }

  function handleOperation(operation) {
    rejectMutationDuringTransition(operation);
    if (operation !== "audio.suspend") {
      invalid("State machine does not directly complete this operation", {
        operation,
      });
    }
    if (state === "audio-suspended") {
      return Object.freeze({ state, changed: false });
    }
    if (state !== "running") {
      invalid("audio.suspend is invalid in the current Host state", {
        operation,
      });
    }
    transition("audio-suspended", { reason: "audio.suspend" });
    return Object.freeze({ state, changed: true });
  }

  function beginTake(takeId) {
    rejectMutationDuringTransition("take.begin");
    if (state !== "running") {
      invalid("take.begin requires the running Host state", {
        operation: "take.begin",
      });
    }
    if (typeof takeId !== "string" || takeId.length === 0) {
      throw new TypeError("take_id must be a non-empty string");
    }
    if (activeTakeId !== null) {
      invalid("A Take is already active", { operation: "take.begin" });
    }
    activeTakeId = takeId;
    return Object.freeze({ take_id: activeTakeId });
  }

  function stopTake() {
    rejectMutationDuringTransition("take.stop");
    if (state !== "running" || activeTakeId === null) {
      invalid("take.stop requires an active Take in running state", {
        operation: "take.stop",
      });
    }
    const stopped = Object.freeze({ take_id: activeTakeId });
    activeTakeId = null;
    return stopped;
  }

  return Object.freeze({
    transition,
    allowsOperation,
    handleOperation,
    beginTake,
    stopTake,
    get state() {
      return state;
    },
    get activeTake() {
      return activeTakeId;
    },
  });
}
