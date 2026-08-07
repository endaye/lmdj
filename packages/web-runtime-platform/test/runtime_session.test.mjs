import assert from "node:assert/strict";
import test from "node:test";

import {createDiagnosticClient} from "../web/diagnostic_client.mjs";
import {createUserGestureToken} from "../web/input_adapters.mjs";
import {createRuntimeSession} from "../web/runtime_session.mjs";


const API = [
  "activateAudio",
  "close",
  "diagnostics",
  "importProject",
  "inspectProject",
  "listLocalProjects",
  "openProject",
  "reloadSnapshot",
  "requestMidi",
  "start",
  "subscribeHostState",
  "subscribeRuntimeOutcome",
  "suspendAudio",
  "trigger",
].sort();

function fixture({send, browserWindow = {}, navigator = {}} = {}) {
  let request = 0;
  let terminated = 0;
  let notificationListener = null;
  const context = {
    state: "suspended",
    async resume() {
      this.state = "running";
    },
    async suspend() {
      this.state = "suspended";
    },
  };
  const transport = {
    async send(envelope) {
      if (send) {
        return send(envelope);
      }
      const results = {
        "audio.activate": {},
        "audio.suspend": {},
        "host.close": {},
        "host.status": {
          acknowledged_generation: 1,
          control_generation: 1,
        },
      };
      return {
        protocol_version: 1,
        request_id: envelope.request_id,
        ok: true,
        result: results[envelope.operation] ?? {},
      };
    },
    subscribe() {
      notificationListener = arguments[0];
      return () => {};
    },
    subscribeFailure() {
      return () => {};
    },
  };
  const session = createRuntimeSession({
    document: {},
    window: browserWindow,
    navigator,
    crypto: {
      randomUUID() {
        request += 1;
        return `00000000-0000-0000-0000-${String(request).padStart(12, "0")}`;
      },
    },
    manifestSource: {},
    assemblyIdentity: {
      distributionContract: "lmdj.web-runtime-host.distribution.v1",
      hostId: "web-runtime-host",
      hostVersion: "1.1.0",
      platformVersion: "0.1.0",
      productBuild: "1.0.15.0",
      protocolVersion: 1,
    },
    inputConfiguration: {},
    seams: {
      createAudioContext: () => context,
      loadRuntime: async () => ({
        registerAudioContext: () => 1,
        startAudioWorklet: async () => ({ok: true}),
        workers: [],
      }),
      preflight: async () => {},
      runtimeTerminator: async () => {
        terminated += 1;
      },
      transport,
      verifyManifest: async () => ({
        host_id: "web-runtime-host",
        host_version: "1.1.0",
        platform_version: "0.1.0",
        product_build: "1.0.15.0",
        protocol_version: 1,
      }),
    },
  });
  return {
    context,
    emitNotification(value) {
      notificationListener?.(value);
    },
    session,
    terminated: () => terminated,
  };
}

test("owns the exact Host-neutral surface and lifecycle", async () => {
  const {session, terminated} = fixture();
  assert.deepEqual(Object.keys(session).sort(), API);
  assert.equal(await session.start(), true);
  assert.equal(await session.start(), false);
  assert.equal(session.diagnostics().state, "audio-suspended");

  const states = [];
  const unsubscribe = session.subscribeHostState((value) => states.push(value));
  assert.throws(() => createUserGestureToken({isTrusted: false}), TypeError);
  assert.equal(await session.activateAudio({kind: "lmdj.web-runtime.user-gesture"}), false);
  const token = createUserGestureToken({isTrusted: true});
  assert.equal(await session.activateAudio(token), true);
  assert.equal(session.diagnostics().state, "running");
  assert.equal(await session.close(), true);
  unsubscribe();

  assert.deepEqual(states.at(-1), {state: "closed", errorCode: null});
  assert.equal(terminated(), 1);
});

test("returns typed admission and publishes normalized Runtime outcomes", async () => {
  const {emitNotification, session} = fixture({
    send: async (envelope) => ({
      protocol_version: 1,
      request_id: envelope.request_id,
      ok: true,
      result: envelope.operation === "trigger"
        ? {sequence: 9}
        : envelope.operation === "host.status"
          ? {acknowledged_generation: 1, control_generation: 1}
          : {},
    }),
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  const outcomes = [];
  session.subscribeRuntimeOutcome((value) => outcomes.push(value));
  assert.deepEqual(await session.trigger(3, 99, "keyboard"), {
    sequence: 9,
    slot: 3,
    velocity: 99,
    source: "keyboard",
  });
  emitNotification({
    protocol_version: 1,
    event: "runtime.trigger_outcomes",
    payload: {
      events: [{sequence: 9, outcome: "voice_started", runtime_frame: 42}],
    },
  });
  assert.deepEqual(outcomes, [
    {sequence: 9, outcome: "voice_started", runtimeFrame: 42},
  ]);
});

test("suppresses a late Trigger response after pagehide close", async () => {
  const browserWindow = new EventTarget();
  let settleTrigger;
  const triggerResponse = new Promise((resolvePromise) => {
    settleTrigger = resolvePromise;
  });
  const {session, terminated} = fixture({
    browserWindow,
    send: async (envelope) => {
      if (envelope.operation === "trigger") {
        return triggerResponse;
      }
      return {
        protocol_version: 1,
        request_id: envelope.request_id,
        ok: true,
        result: envelope.operation === "host.status"
          ? {acknowledged_generation: 1, control_generation: 1}
          : {},
      };
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  const pending = session.trigger(0, 100, "pointer");
  browserWindow.dispatchEvent(new Event("pagehide"));
  settleTrigger({
    protocol_version: 1,
    request_id: "00000000-0000-0000-0000-000000000003",
    ok: true,
    result: {sequence: 1},
  });
  assert.equal(await pending, false);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
  assert.equal(session.diagnostics().state, "closed");
  assert.equal(session.diagnostics().trigger_admitted_count, 0);
  assert.equal(terminated(), 1);
});

test("close disposes MIDI input listeners exactly once", async () => {
  let added = 0;
  let removed = 0;
  const input = {
    type: "input",
    state: "connected",
    addEventListener(type) {
      assert.equal(type, "midimessage");
      added += 1;
    },
    removeEventListener(type) {
      assert.equal(type, "midimessage");
      removed += 1;
    },
  };
  const access = new EventTarget();
  access.inputs = new Map([["private", input]]);
  const {session} = fixture({
    navigator: {
      async requestMIDIAccess(options) {
        assert.deepEqual(options, {sysex: false});
        return access;
      },
    },
  });
  await session.start();
  assert.equal(await session.requestMidi(), true);
  assert.equal(added, 1);
  await session.close();
  assert.equal(removed, 1);
});

test("timeout becomes one terminal restart-required notification", async () => {
  const failure = Object.assign(new Error("timeout"), {code: "HOST_TIMEOUT"});
  const {session, terminated} = fixture({
    send: async (envelope) => {
      if (envelope.operation === "project.create") {
        throw failure;
      }
      return {
        protocol_version: 1,
        request_id: envelope.request_id,
        ok: true,
        result: {},
      };
    },
  });
  await session.start();
  const states = [];
  session.subscribeHostState((value) => states.push(value));
  const diagnostic = createDiagnosticClient(session);

  await assert.rejects(diagnostic.createProject({}), failure);
  assert.equal(session.diagnostics().state, "restart-required");
  assert.equal(session.diagnostics().error_code, "HOST_TIMEOUT");
  assert.deepEqual(states, [
    {state: "restart-required", errorCode: "HOST_TIMEOUT"},
  ]);
  await Promise.resolve();
  assert.equal(terminated(), 1);
});
