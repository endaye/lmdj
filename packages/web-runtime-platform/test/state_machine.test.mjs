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

test("audio.suspend seals an active Take before audio-suspended is observable", () => {
  const observations = [];
  let machine;
  machine = createHostStateMachine({
    initialState: "running",
    sealTake: (take) => {
      observations.push({
        step: "seal",
        state: machine.state,
        activeTake: machine.activeTake,
        take,
      });
    },
    notify: (event, payload) => {
      observations.push({
        step: `notify:${event}`,
        state: machine.state,
        activeTake: machine.activeTake,
        payload,
      });
    },
  });
  machine.beginTake("take-suspend");

  assert.deepEqual(machine.handleOperation("audio.suspend"), {
    state: "audio-suspended",
    changed: true,
  });

  assert.equal(machine.activeTake, null);
  assert.deepEqual(observations[0], {
    step: "seal",
    state: "running",
    activeTake: null,
    take: {
      take_id: "take-suspend",
      outcome: "capture_incomplete",
      reason: "audio.suspend",
    },
  });
  assert.deepEqual(
    observations.slice(1).map(({ step }) => step),
    ["notify:capture.sealed", "notify:host.state_changed"],
  );
  for (const observation of observations.slice(1)) {
    assert.equal(observation.state, "audio-suspended", observation.step);
    assert.equal(observation.activeTake, null, observation.step);
  }
});

test("Trigger and take.begin are accepted only while running", () => {
  for (const state of HOST_STATES) {
    const machine = createHostStateMachine({ initialState: state });
    assert.equal(machine.allowsOperation("trigger"), state === "running", state);
    assert.equal(machine.allowsOperation("take.begin"), state === "running", state);
  }
});

test("interruption seals an active Take and emits exact notifications", () => {
  const notifications = [];
  const sealed = [];
  const machine = createHostStateMachine({
    initialState: "running",
    notify: (event, payload) => notifications.push({ event, payload }),
    sealTake: (take) => sealed.push(take),
  });
  machine.beginTake("take-1");
  machine.transition("interrupted", { reason: "audio_statechange" });

  assert.equal(machine.activeTake, null);
  assert.deepEqual(sealed, [
    {
      take_id: "take-1",
      outcome: "capture_incomplete",
      reason: "audio_statechange",
    },
  ]);
  assert.deepEqual(
    notifications.map(({ event }) => event),
    ["capture.sealed", "host.state_changed", "audio.interrupted"],
  );
});

test("seals and cleans before terminal or interrupted state becomes observable", () => {
  for (const nextState of ["interrupted", "restart-required", "failed", "closed"]) {
    const observations = [];
    let machine;
    machine = createHostStateMachine({
      initialState: "running",
      sealTake: () => {
        observations.push({
          step: "seal",
          state: machine.state,
          activeTake: machine.activeTake,
        });
      },
      cleanup: (targetState) => {
        observations.push({
          step: `cleanup:${targetState}`,
          state: machine.state,
          activeTake: machine.activeTake,
        });
      },
      notify: (event) => {
        observations.push({
          step: `notify:${event}`,
          state: machine.state,
          activeTake: machine.activeTake,
        });
      },
    });
    machine.beginTake(`take-${nextState}`);
    machine.transition(nextState);

    assert.deepEqual(observations[0], {
      step: "seal",
      state: "running",
      activeTake: null,
    });
    assert.deepEqual(observations[1], {
      step: `cleanup:${nextState}`,
      state: "running",
      activeTake: null,
    });
    for (const observation of observations.slice(2)) {
      assert.equal(observation.state, nextState, observation.step);
      assert.equal(observation.activeTake, null, observation.step);
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
        assert.equal(machine.activeTake, null);
        try {
          machine.transition("recovering");
        } catch (error) {
          reentrantErrors.push(error);
        }
      }
    },
  });
  machine.beginTake("take-reentrant");
  machine.transition("interrupted");
  assert.equal(machine.state, "interrupted");
  assert.equal(reentrantErrors.length, 1);
  assert.equal(reentrantErrors[0].code, "HOST_STATE_INVALID");
});

function exerciseAdmissionBarrier(callbackName, nextState) {
  const sideEffects = {
    trigger: 0,
    beginTake: 0,
    stopTake: 0,
  };
  const admissions = [];
  const rejected = [];
  let machine;

  function probeAdmission() {
    const triggerAllowed = machine.allowsOperation("trigger");
    admissions.push({
      trigger: triggerAllowed,
      beginTake: machine.allowsOperation("take.begin"),
      hostStatus: machine.allowsOperation("host.status"),
    });
    if (triggerAllowed) {
      sideEffects.trigger += 1;
    }
    for (const [operation, mutate] of [
      ["take.begin", () => machine.beginTake("take-reentrant")],
      ["take.stop", () => machine.stopTake()],
      ["audio.suspend", () => machine.handleOperation("audio.suspend")],
    ]) {
      try {
        mutate();
        if (operation === "take.begin") {
          sideEffects.beginTake += 1;
        } else if (operation === "take.stop") {
          sideEffects.stopTake += 1;
        }
      } catch (error) {
        rejected.push({ operation, error });
      }
    }
  }

  machine = createHostStateMachine({
    initialState: "running",
    sealTake: callbackName === "sealTake" ? probeAdmission : () => {},
    cleanup: callbackName === "cleanup" ? probeAdmission : () => {},
  });
  machine.beginTake("take-active");
  machine.transition(nextState);

  assert.equal(machine.state, nextState);
  assert.equal(machine.activeTake, null);
  assert.deepEqual(admissions, [
    { trigger: false, beginTake: false, hostStatus: false },
  ]);
  assert.deepEqual(sideEffects, {
    trigger: 0,
    beginTake: 0,
    stopTake: 0,
  });
  assert.deepEqual(
    rejected.map(({ operation }) => operation),
    ["take.begin", "take.stop", "audio.suspend"],
  );
  for (const { error } of rejected) {
    assert.equal(error instanceof HostStateError, true);
    assert.equal(error.code, "HOST_STATE_INVALID");
    assert.equal(error.details.transition_in_progress, true);
  }
}

test("sealTake callback cannot admit Trigger or mutate Take state", () => {
  for (const nextState of ["interrupted", "failed", "closed"]) {
    exerciseAdmissionBarrier("sealTake", nextState);
  }
});

test("cleanup callback cannot admit Trigger or mutate Take state", () => {
  for (const nextState of ["interrupted", "failed", "closed"]) {
    exerciseAdmissionBarrier("cleanup", nextState);
  }
});

test("fatal failure seals an active Take and terminal states are immutable", () => {
  const sealed = [];
  const failed = createHostStateMachine({
    initialState: "running",
    sealTake: (take) => sealed.push(take),
  });
  failed.beginTake("take-2");
  failed.transition("failed", { reason: "WORKLET_PROCESSOR_ERROR" });
  assert.deepEqual(sealed, [
    {
      take_id: "take-2",
      outcome: "capture_incomplete",
      reason: "WORKLET_PROCESSOR_ERROR",
    },
  ]);
  assert.throws(() => failed.transition("closed"), HostStateError);
  assert.equal(failed.state, "failed");

  const closed = createHostStateMachine({ initialState: "closed" });
  assert.throws(() => closed.transition("failed"), HostStateError);
  assert.equal(closed.state, "closed");
});

test("supports repeated interruption and both recovery paths without reviving a sealed Take", () => {
  const sealed = [];
  const machine = createHostStateMachine({
    initialState: "running",
    sealTake: (take) => sealed.push(take),
  });
  machine.beginTake("take-first");
  machine.transition("interrupted");
  machine.transition("recovering");
  machine.transition("running");
  assert.equal(machine.activeTake, null);

  machine.beginTake("take-second");
  machine.transition("interrupted");
  machine.transition("recovering");
  machine.transition("audio-suspended");
  machine.transition("running");
  assert.equal(machine.activeTake, null);
  assert.deepEqual(
    sealed.map(({ take_id }) => take_id),
    ["take-first", "take-second"],
  );
});

test("take.stop ends the active Take without incomplete sealing", () => {
  const sealed = [];
  const machine = createHostStateMachine({
    initialState: "running",
    sealTake: (take) => sealed.push(take),
  });
  machine.beginTake("take-clean");
  assert.deepEqual(machine.stopTake(), { take_id: "take-clean" });
  assert.equal(machine.activeTake, null);
  assert.deepEqual(sealed, []);
});
