export const HOST_STATES = Object.freeze([
  "cold",
  "preflight",
  "storage-ready",
  "core-ready",
  "audio-suspended",
  "running",
  "interrupted",
  "recovering",
  "restart-required",
  "closed",
  "failed",
]);

const STATE_SET = new Set(HOST_STATES);
const TERMINAL_STATES = new Set(["restart-required", "closed", "failed"]);
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
  recovering: Object.freeze(["running", "audio-suspended", "interrupted"]),
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
  cleanup = () => {},
} = {}) {
  if (!STATE_SET.has(initialState)) {
    throw new TypeError("Unknown initial Host state");
  }
  if (
    typeof notify !== "function" ||
    typeof cleanup !== "function"
  ) {
    throw new TypeError("Host state side effects must be injected functions");
  }

  let state = initialState;
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

  function isAllowedTransition(nextState, recoveryEpoch) {
    if (!STATE_SET.has(nextState) || TERMINAL_STATES.has(state)) {
      return false;
    }
    if (TERMINAL_STATES.has(nextState)) {
      return NONTERMINAL_STATES.has(state);
    }
    if (
      state === "audio-suspended" &&
      nextState === "recovering"
    ) {
      return recoveryEpoch === true;
    }
    return NEXT_STATES[state]?.includes(nextState) ?? false;
  }

  function transition(
    nextState,
    { reason = "host_lifecycle", recoveryEpoch = false } = {},
  ) {
    if (transitionInProgress) {
      invalid("Reentrant Host state transitions are not allowed", {
        next_state: nextState,
        transition_in_progress: true,
      });
    }
    if (!isAllowedTransition(nextState, recoveryEpoch)) {
      invalid("Transition is not present in the locked Host state table", {
        next_state: nextState,
      });
    }
    transitionInProgress = true;
    try {
      const previousState = state;
      const requiresCleanup =
        nextState === "interrupted" ||
        nextState === "restart-required" ||
        nextState === "failed" ||
        nextState === "closed";
      if (requiresCleanup) {
        cleanup(nextState, { reason });
      }

      state = nextState;
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

  return Object.freeze({
    transition,
    handleOperation,
    get state() {
      return state;
    },
  });
}
