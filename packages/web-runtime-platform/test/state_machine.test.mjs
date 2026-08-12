import assert from "node:assert/strict";
import test from "node:test";

import {
  HOST_STATES,
  HostStateError,
  createHostStateMachine,
} from "../web/state_machine.mjs";

const NONTERMINAL_STATES = [
  "cold",
  "preflight",
  "storage-ready",
  "core-ready",
  "audio-suspended",
  "running",
  "interrupted",
  "recovering",
];

function advanceToRunning(machine) {
  for (const nextState of [
    "preflight",
    "storage-ready",
    "core-ready",
    "audio-suspended",
    "running",
  ]) {
    machine.transition(nextState);
  }
}

test("exports exactly the externally visible Host states", () => {
  assert.deepEqual(HOST_STATES, [
    ...NONTERMINAL_STATES,
    "restart-required",
    "closed",
    "failed",
  ]);
});

test("exposes only the active Stage 7 state-machine surface", () => {
  assert.deepEqual(Object.keys(createHostStateMachine()).sort(), [
    "handleOperation",
    "state",
    "transition",
  ]);
});

test("exercises every locked nonterminal state-table row", () => {
  const startup = createHostStateMachine();
  advanceToRunning(startup);
  startup.transition("audio-suspended");
  assert.equal(startup.state, "audio-suspended");

  const recoveryWithoutGesture = createHostStateMachine({
    initialState: "running",
  });
  recoveryWithoutGesture.transition("interrupted");
  recoveryWithoutGesture.transition("recovering");
  recoveryWithoutGesture.transition("running");
  assert.equal(recoveryWithoutGesture.state, "running");

  const recoveryWithGesture = createHostStateMachine({ initialState: "running" });
  recoveryWithGesture.transition("interrupted");
  recoveryWithGesture.transition("recovering");
  recoveryWithGesture.transition("audio-suspended");
  assert.equal(recoveryWithGesture.state, "audio-suspended");
});

test("allows clean close from every nonterminal state", () => {
  for (const state of NONTERMINAL_STATES) {
    const machine = createHostStateMachine({ initialState: state });
    machine.transition("closed");
    assert.equal(machine.state, "closed", state);
  }
});

test("allows fatal failure from every nonterminal state", () => {
  for (const state of NONTERMINAL_STATES) {
    const machine = createHostStateMachine({ initialState: state });
    machine.transition("failed", { reason: "WORKER_CRASH" });
    assert.equal(machine.state, "failed", state);
  }
});

test("allows restart-required from every nonterminal state and seals terminally", () => {
  for (const state of NONTERMINAL_STATES) {
    const machine = createHostStateMachine({initialState: state});
    machine.transition("restart-required", {reason: "HOST_TIMEOUT"});
    assert.equal(machine.state, "restart-required", state);
    assert.throws(() => machine.transition("closed"), HostStateError);
  }
});

test("rejects transitions absent from the locked state table", () => {
  const machine = createHostStateMachine();
  assert.throws(
    () => machine.transition("running"),
    (error) =>
      error instanceof HostStateError && error.code === "HOST_STATE_INVALID",
  );
  assert.equal(machine.state, "cold");
});

test("audio.suspend is idempotent only in audio-suspended", () => {
  const machine = createHostStateMachine({ initialState: "audio-suspended" });
  assert.deepEqual(machine.handleOperation("audio.suspend"), {
    state: "audio-suspended",
    changed: false,
  });

  const running = createHostStateMachine({ initialState: "running" });
  assert.deepEqual(running.handleOperation("audio.suspend"), {
    state: "audio-suspended",
    changed: true,
  });

  for (const state of ["cold", "preflight", "storage-ready", "core-ready", "interrupted", "recovering", "restart-required", "closed", "failed"]) {
    const invalid = createHostStateMachine({ initialState: state });
    assert.throws(
      () => invalid.handleOperation("audio.suspend"),
      (error) => error.code === "HOST_STATE_INVALID",
      state,
    );
  }
});

test("audio.suspend publishes the new state after the transition", () => {
  const observations = [];
  let machine;
  machine = createHostStateMachine({
    initialState: "running",
    notify: (event, payload) => observations.push({
      event,
      payload,
      state: machine.state,
    }),
  });

  assert.deepEqual(machine.handleOperation("audio.suspend"), {
    state: "audio-suspended",
    changed: true,
  });
  assert.deepEqual(observations, [{
    event: "host.state_changed",
    payload: {previous_state: "running", state: "audio-suspended"},
    state: "audio-suspended",
  }]);
});

test("interruption emits exact notifications", () => {
  const notifications = [];
  const machine = createHostStateMachine({
    initialState: "running",
    notify: (event, payload) => notifications.push({ event, payload }),
  });
  machine.transition("interrupted", { reason: "audio_statechange" });

  assert.deepEqual(
    notifications.map(({ event }) => event),
    ["host.state_changed", "audio.interrupted"],
  );
});

test("cleans before terminal or interrupted state becomes observable", () => {
  for (const nextState of ["interrupted", "restart-required", "failed", "closed"]) {
    const observations = [];
    let machine;
    machine = createHostStateMachine({
      initialState: "running",
      cleanup: (targetState) => {
        observations.push({
          step: `cleanup:${targetState}`,
          state: machine.state,
        });
      },
      notify: (event) => {
        observations.push({
          step: `notify:${event}`,
          state: machine.state,
        });
      },
    });
    machine.transition(nextState);

    assert.deepEqual(observations[0], {
      step: `cleanup:${nextState}`,
      state: "running",
    });
    for (const observation of observations.slice(1)) {
      assert.equal(observation.state, nextState, observation.step);
    }
  }
});

test("reentrant notification cannot recover during an interrupted transition", () => {
  const reentrantErrors = [];
  let machine;
  machine = createHostStateMachine({
    initialState: "running",
    notify: (event) => {
      if (event === "host.state_changed") {
        assert.equal(machine.state, "interrupted");
        try {
          machine.transition("recovering");
        } catch (error) {
          reentrantErrors.push(error);
        }
      }
    },
  });
  machine.transition("interrupted");
  assert.equal(machine.state, "interrupted");
  assert.equal(reentrantErrors.length, 1);
  assert.equal(reentrantErrors[0].code, "HOST_STATE_INVALID");
});

function exerciseAdmissionBarrier(nextState) {
  const rejected = [];
  let machine;

  function probeAdmission() {
    for (const [operation, mutate] of [
      ["transition", () => machine.transition("audio-suspended")],
      ["audio.suspend", () => machine.handleOperation("audio.suspend")],
    ]) {
      try {
        mutate();
      } catch (error) {
        rejected.push({ operation, error });
      }
    }
  }

  machine = createHostStateMachine({
    initialState: "running",
    cleanup: probeAdmission,
  });
  machine.transition(nextState);

  assert.equal(machine.state, nextState);
  assert.deepEqual(
    rejected.map(({ operation }) => operation),
    ["transition", "audio.suspend"],
  );
  for (const { error } of rejected) {
    assert.equal(error instanceof HostStateError, true);
    assert.equal(error.code, "HOST_STATE_INVALID");
    assert.equal(error.details.transition_in_progress, true);
  }
}

test("cleanup callback cannot mutate Host state", () => {
  for (const nextState of ["interrupted", "failed", "closed"]) {
    exerciseAdmissionBarrier(nextState);
  }
});

test("terminal states are immutable", () => {
  const failed = createHostStateMachine({
    initialState: "running",
  });
  failed.transition("failed", { reason: "WORKLET_PROCESSOR_ERROR" });
  assert.throws(() => failed.transition("closed"), HostStateError);
  assert.equal(failed.state, "failed");

  const closed = createHostStateMachine({ initialState: "closed" });
  assert.throws(() => closed.transition("failed"), HostStateError);
  assert.equal(closed.state, "closed");
});

test("supports repeated interruption and both recovery paths", () => {
  const machine = createHostStateMachine({initialState: "running"});
  machine.transition("interrupted");
  machine.transition("recovering");
  machine.transition("running");

  machine.transition("interrupted");
  machine.transition("recovering");
  machine.transition("audio-suspended");
  machine.transition("running");
  assert.equal(machine.state, "running");
});
