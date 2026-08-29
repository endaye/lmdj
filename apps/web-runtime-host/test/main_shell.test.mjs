import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

import {createUserGestureToken} from
  "../../../packages/web-runtime-platform/web/input_adapters.mjs";
import {createWebRuntimeHostController} from "../src/main.mjs";


const APP_ROOT = new URL("../", import.meta.url);
const TEST_PRODUCT_BUILD = "9.8.7.6";

class Element extends EventTarget {
  constructor(id, {bank, pad} = {}) {
    super();
    this.id = id;
    this.dataset = {};
    this.attributes = new Map();
    this.disabled = false;
    this.textContent = "";
    if (bank !== undefined) {
      this.dataset.bank = String(bank);
      this.dataset.pad = String(pad);
    }
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }
}

function dom() {
  const elements = new Map([
    "host-state",
    "diagnostics",
    "diagnostic-project-state",
    "diagnostic-project-load",
    "audio-activate",
    "audio-suspend",
    "midi-enable",
  ].map((id) => [id, new Element(id)]));
  const pads = Array.from({length: 64}, (_, slot) =>
    new Element(`pad-${slot}`, {
      bank: Math.floor(slot / 16),
      pad: slot % 16,
    }));
  return {
    elements,
    document: {
      getElementById(id) {
        return elements.get(id) ?? null;
      },
      querySelectorAll(selector) {
        return selector === "button[data-bank][data-pad]" ? pads : [];
      },
    },
  };
}

function fixture() {
  const view = dom();
  let state = "cold";
  let diagnosticState = "idle";
  let closed = 0;
  const hostListeners = new Set();
  const session = Object.freeze({
    async start() {
      state = "audio-suspended";
      for (const listener of hostListeners) {
        listener({state, errorCode: null});
      }
      return true;
    },
    async activateAudio(token) {
      assert.equal(token.kind, "lmdj.web-runtime.user-gesture");
      state = "running";
      for (const listener of hostListeners) {
        listener({state, errorCode: null});
      }
      return true;
    },
    async suspendAudio() {
      state = "audio-suspended";
      return true;
    },
    async requestMidi() {
      return true;
    },
    async trigger() {
      return {sequence: 1, slot: 0, velocity: 100, source: "pointer"};
    },
    async beginSequence(request) {
      return {state: "active", sessionId: request.sessionId};
    },
    async recordSequenceEvent(request) {
      return {state: "active", sessionId: request.sessionId};
    },
    async flushSequence(request) {
      return {state: "active", sessionId: request.sessionId};
    },
    async stopSequence(request) {
      return {state: "inactive", sessionId: request.sessionId};
    },
    async requestPatternSwitch(request) {
      return {state: "switching", sessionId: request.sessionId};
    },
    async querySequenceStatus() {
      return {state: "inactive"};
    },
    async listSequenceRecovery() {
      return [];
    },
    async applySequenceRecovery(request) {
      return {state: "inactive", sessionId: request.sessionId};
    },
    async discardSequenceRecovery() {
      return true;
    },
    subscribeSequenceBarBoundary() {
      return () => true;
    },
    async close() {
      state = "closed";
      closed += 1;
      for (const listener of hostListeners) {
        listener({state, errorCode: null});
      }
      return true;
    },
    subscribeHostState(listener) {
      hostListeners.add(listener);
      return () => hostListeners.delete(listener);
    },
    subscribeRuntimeOutcome() {
      return () => {};
    },
    diagnostics() {
      return Object.freeze({
        state,
        error_code: null,
        product_build: TEST_PRODUCT_BUILD,
        host_version: "2.1.1",
        protocol_version: 1,
      });
    },
  });
  const diagnosticProject = {
    async load() {
      diagnosticState = "ready";
      return {state: "ready", generation: 7};
    },
    invalidate() {
      diagnosticState = "idle";
    },
    diagnostics() {
      return diagnosticState === "ready"
        ? {
          diagnostic_project_state: "ready",
          diagnostic_project_generation: 7,
        }
        : {diagnostic_project_state: diagnosticState};
    },
    async refreshSequenceAuthority() {
      return {state: "inactive", switch_pending: false, recovery_count: 0};
    },
  };
  const controller = createWebRuntimeHostController({
    document: view.document,
    window: new EventTarget(),
    session,
    diagnosticClient: {},
    diagnosticProject,
  });
  return {closed: () => closed, controller, view};
}

test("static shell has local assets and 64 stable Pad identities", async () => {
  const index = await readFile(new URL("index.html", APP_ROOT), "utf8");
  assert.doesNotMatch(index, /https?:\/\//);
  const padIds = [...index.matchAll(/id="pad-(\d+)"/g)]
    .map((match) => Number.parseInt(match[1], 10));
  assert.deepEqual(padIds, Array.from({length: 64}, (_, index) => index));
});

test("thin diagnostic controller delegates lifecycle and renders merged state", async () => {
  const {closed, controller, view} = fixture();
  assert.equal(await controller.start(), true);
  assert.equal(controller.state, "audio-suspended");
  assert.equal(view.elements.get("host-state").textContent, "audio-suspended");
  assert.equal(view.elements.get("audio-activate").disabled, true);

  assert.equal(await controller.loadDiagnosticProject(), true);
  assert.equal(view.elements.get("audio-activate").disabled, false);
  assert.equal(
    await controller.activateAudio(createUserGestureToken({isTrusted: true})),
    true,
  );
  assert.equal(controller.state, "running");
  assert.deepEqual(await controller.trigger(0, 100, "pointer"), {
    sequence: 1,
    slot: 0,
    velocity: 100,
    source: "pointer",
  });
  const sessionId = "00000000-0000-4000-8000-000000000201";
  assert.deepEqual(await controller.beginSequence({sessionId}), {
    state: "active",
    sessionId,
  });
  assert.equal((await controller.querySequenceStatus()).state, "inactive");
  assert.deepEqual(await controller.refreshSequenceDiagnostics(), {
    state: "inactive",
    switch_pending: false,
    recovery_count: 0,
  });
  assert.equal(await controller.close(), true);
  assert.equal(closed(), 1);
  assert.equal(controller.state, "closed");
});

test("duplicate start is rejected and diagnostic identities stay private", async () => {
  const {controller} = fixture();
  assert.equal(await controller.start(), true);
  assert.equal(await controller.start(), false);
  const serialized = JSON.stringify(controller.diagnostics());
  assert.equal(serialized.includes("project_id"), false);
  assert.equal(serialized.includes("asset_id"), false);
});
