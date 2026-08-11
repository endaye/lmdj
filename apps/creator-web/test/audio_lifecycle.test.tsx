import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test} from "vitest";

import {App} from "../src/app";
import {activateCreatorAudio} from "../src/runtime/runtime_context";
import type {
  CreatorRuntimeSession,
  LocalProjectSummary,
  RuntimeHostState,
  RuntimeOutcome,
} from "../src/runtime/runtime_types";

const summary: LocalProjectSummary = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 3,
  bpm: 120,
  assetCount: 1,
  assignedPadCount: 1,
  bundleDigest: "a".repeat(64),
};

function inspectResult() {
  return {
    project_revision: 3,
    project: {
      contract: "lmdj.project.v1",
      project_id: summary.projectId,
      revision: 3,
      bpm: 120,
      assets: {"33333333-3333-4333-8333-333333333333": {artifact: {}}},
      banks: Array.from({length: 4}, (_, bank) => ({
        bank,
        pads: Array.from({length: 16}, (_, pad) => ({
          pad,
          asset_id: bank === 0 && pad === 0
            ? "33333333-3333-4333-8333-333333333333"
            : null,
        })),
      })),
      patterns: {},
      takes: {},
    },
  };
}

function sessionFixture(name: string) {
  const calls: string[] = [];
  const hostListeners = new Set<(state: RuntimeHostState) => void>();
  const outcomeListeners = new Set<(outcome: RuntimeOutcome) => void>();
  let hostState = "audio-suspended";
  let errorCode: string | null = null;
  let recoveryProbeReady = false;
  const session: CreatorRuntimeSession = {
    start: async () => { calls.push(`${name}:start`); return true; },
    close: async () => { calls.push(`${name}:close`); return true; },
    listLocalProjects: async () => {
      calls.push(`${name}:list`);
      return [summary];
    },
    importProject: async () => { throw new Error("unused"); },
    openProject: async () => { calls.push(`${name}:open`); return {}; },
    inspectProject: async () => { calls.push(`${name}:inspect`); return inspectResult(); },
    reloadSnapshot: async () => { calls.push(`${name}:reload`); return {}; },
    activateAudio: async () => { calls.push(`${name}:activate`); return true; },
    suspendAudio: async () => {
      calls.push(`${name}:suspend`);
      emit({state: "audio-suspended", errorCode: null});
      return true;
    },
    trigger: async () => false,
    requestMidi: async () => true,
    subscribeHostState(listener) {
      hostListeners.add(listener);
      return () => hostListeners.delete(listener);
    },
    subscribeRuntimeOutcome(listener) {
      outcomeListeners.add(listener);
      return () => outcomeListeners.delete(listener);
    },
    diagnostics: () => ({
      state: hostState,
      error_code: errorCode,
      product_build: "1.0.16.6",
      host_id: "creator-web",
      host_version: "1.0.3",
      platform_version: "0.1.3",
      protocol_version: 1,
      capabilities: {
        secureContext: true, crossOriginIsolated: true, sharedArrayBuffer: true,
        webAssembly: true, audioWorklet: true, opfs: true,
        opfsSyncAccessHandle: true, opfsWritableReplace: true, webMidi: false,
      },
      trigger_admitted_count: 0,
      trigger_outcome_count: 0,
      trigger_rejected_count: 0,
      recovery_probe_ready: recoveryProbeReady,
    }),
  };
  function emit(value: RuntimeHostState) {
    hostState = value.state;
    errorCode = value.errorCode;
    if (value.state !== "recovering") recoveryProbeReady = false;
    for (const listener of hostListeners) listener(value);
  }
  return {
    session,
    calls,
    emit,
    setRecoveryProbeReady(value: boolean) { recoveryProbeReady = value; },
  };
}

test("suspend stays explicit and restart rebuilds, lists, and reopens without autoplay", async () => {
  const user = userEvent.setup();
  const first = sessionFixture("first");
  const second = sessionFixture("second");
  const sessions = [first, second];
  let creations = 0;
  render(<App runtimeFactory={() => sessions[creations++]!.session} />);

  await user.click(await screen.findByRole("button", {
    name: "Open Project 11111111",
  }));
  await screen.findByRole("heading", {name: "Project 11111111"});
  expect(first.calls).not.toContain("first:activate");

  first.emit({state: "running", errorCode: null});
  await screen.findByText("Audio running");
  await user.click(screen.getByRole("button", {name: "Suspend audio"}));
  await screen.findByText("Audio suspended");

  first.emit({state: "restart-required", errorCode: "HOST_RESTART_REQUIRED"});
  await waitFor(() => expect(creations).toBe(2));
  await waitFor(() => expect(second.calls).toEqual([
    "second:start",
    "second:list",
    "second:open",
    "second:inspect",
    "second:reload",
  ]));
  expect(first.calls.filter((call) => call === "first:close")).toHaveLength(1);
  expect(second.calls).not.toContain("second:activate");
  expect(screen.getByTestId("creator-phase").textContent).toBe("ready");
  expect(screen.getByTestId("audio-state").textContent).toBe("Audio inactive");
});

test("a failed Runtime Session start never becomes ready", async () => {
  const failed = sessionFixture("failed");
  failed.session.start = async () => false;
  failed.emit({state: "failed", errorCode: "HOST_STATE_INVALID"});
  render(<App runtimeFactory={() => failed.session} />);
  expect((await screen.findByRole("alert")).textContent).toContain("HOST_STATE_INVALID");
  expect(screen.getByTestId("creator-phase").textContent).toBe("failed");
});

test("recovery keeps the Project playable for the required probe Trigger", async () => {
  const user = userEvent.setup();
  const value = sessionFixture("recovery");
  value.session.trigger = async (slot, velocity, source) => {
    value.calls.push(`recovery:trigger:${slot}:${velocity}:${source}`);
    return {sequence: 1, slot, velocity, source};
  };
  render(<App runtimeFactory={() => value.session} />);

  await user.click(await screen.findByRole("button", {
    name: "Open Project 11111111",
  }));
  await screen.findByRole("heading", {name: "Project 11111111"});
  value.emit({state: "running", errorCode: null});
  await screen.findByText("Audio running");

  value.emit({state: "interrupted", errorCode: null});
  await screen.findByText("Audio suspended");
  const pad = screen.getByRole("button", {name: "Pad A1 — assigned"});
  expect(pad.hasAttribute("disabled")).toBe(true);

  value.emit({state: "recovering", errorCode: null});
  expect(screen.getByTestId("audio-state").textContent).toBe("Audio suspended");
  value.setRecoveryProbeReady(true);
  await screen.findByText("Audio recovering");
  expect(pad.hasAttribute("disabled")).toBe(false);
  window.dispatchEvent(new KeyboardEvent("keydown", {code: "KeyA"}));
  await waitFor(() => expect(value.calls).toContain(
    "recovery:trigger:0:100:keyboard",
  ));

  value.emit({state: "running", errorCode: null});
  await screen.findByText("Audio running");
});

test("audio activation consumes only an explicit trusted gesture", async () => {
  const value = sessionFixture("gesture");
  let token: unknown = null;
  value.session.activateAudio = async (received) => {
    token = received;
    return true;
  };
  expect(() => activateCreatorAudio(value.session, {isTrusted: false}))
    .toThrow(TypeError);
  expect(token).toBeNull();
  await expect(activateCreatorAudio(value.session, {isTrusted: true}))
    .resolves.toBe(true);
  expect(token).toEqual({kind: "lmdj.web-runtime.user-gesture"});
});
