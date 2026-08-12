import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test} from "vitest";

import {App} from "../src/app";
import {activateCreatorAudio} from "../src/runtime/runtime_context";
import type {
  CreatorRuntimeSession,
  CreatorSampleRuntimeSession,
  LocalProjectSummary,
  RuntimeDiagnostics,
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
  const diagnosticListeners = new Set<(value: RuntimeDiagnostics) => void>();
  const outcomeListeners = new Set<(outcome: RuntimeOutcome) => void>();
  let hostState = "audio-suspended";
  let errorCode: string | null = null;
  let errorDetails: Readonly<Record<string, unknown>> = {};
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
    subscribeDiagnostics(listener) {
      diagnosticListeners.add(listener);
      return () => diagnosticListeners.delete(listener);
    },
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
      error_details: errorDetails,
      product_build: "1.0.20.0",
      host_id: "creator-web",
      host_version: "1.1.2",
      platform_version: "0.2.1",
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
  function emit(value: Omit<RuntimeHostState, "errorDetails"> & {
    errorDetails?: Readonly<Record<string, unknown>>;
  }) {
    const normalized = {...value, errorDetails: value.errorDetails ?? {}};
    hostState = value.state;
    errorCode = value.errorCode;
    errorDetails = normalized.errorDetails;
    if (value.state !== "recovering") recoveryProbeReady = false;
    for (const listener of hostListeners) listener(normalized);
  }
  function outcome(value: RuntimeOutcome) {
    for (const listener of outcomeListeners) listener(value);
  }
  return {
    session,
    calls,
    emit,
    outcome,
    setRecoveryProbeReady(value: boolean) {
      recoveryProbeReady = value;
      const diagnostic = session.diagnostics();
      for (const listener of diagnosticListeners) listener(diagnostic);
    },
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

test("automatic reopen owns the same Project action lane until completion", async () => {
  const user = userEvent.setup();
  const first = sessionFixture("lane-first");
  const second = sessionFixture("lane-second");
  let finishReopen: (() => void) | undefined;
  const reopen = new Promise<void>((resolve) => { finishReopen = resolve; });
  second.session.openProject = async () => {
    second.calls.push("lane-second:open");
    await reopen;
    return {};
  };
  const sessions = [first, second];
  let creations = 0;
  render(<App runtimeFactory={() => sessions[creations++]!.session} />);

  await user.click(await screen.findByRole("button", {
    name: "Open Project 11111111",
  }));
  await screen.findByRole("heading", {name: "Project 11111111"});
  first.emit({
    state: "restart-required",
    errorCode: "HOST_RESTART_REQUIRED",
  });
  await waitFor(() => expect(second.calls).toContain("lane-second:open"));
  expect(screen.getByRole("button", {name: "Open local"}).hasAttribute("disabled"))
    .toBe(true);
  expect(screen.getByRole("button", {name: "Import .lmdj"}).hasAttribute("disabled"))
    .toBe(true);

  finishReopen?.();
  await waitFor(() => expect(second.calls).toContain("lane-second:reload"));
  expect(screen.getByRole("button", {name: "Open local"}).hasAttribute("disabled"))
    .toBe(false);
});

test("Runtime replacement cannot leave an aborted import permanently visible", async () => {
  const first = sessionFixture("import-first");
  const second = sessionFixture("import-second");
  first.session.importProject = async (_file, {signal}) =>
    new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => {
        reject(new DOMException("cancelled", "AbortError"));
      }, {once: true});
    });
  const sessions = [first, second];
  let creations = 0;
  const {container} = render(
    <App runtimeFactory={() => sessions[creations++]!.session} />,
  );

  await screen.findByRole("button", {name: "Open Project 11111111"});
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  await userEvent.upload(input!, new File(["bundle"], "stage7.lmdj"));
  await screen.findByText("importing");

  first.emit({
    state: "restart-required",
    errorCode: "HOST_RESTART_REQUIRED",
  });
  await waitFor(() => expect(creations).toBe(2));
  await waitFor(() => expect(second.calls).toEqual([
    "import-second:start",
    "import-second:list",
  ]));

  expect(screen.getByTestId("creator-phase").textContent).toBe("ready");
  expect(screen.getByRole("button", {name: "Open local"}).hasAttribute("disabled"))
    .toBe(false);
  expect(screen.getByRole("button", {name: "Import .lmdj"}).hasAttribute("disabled"))
    .toBe(false);
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
  const pad = screen.getByRole("button", {name: "Pad A1 — assigned — Key Q"});
  expect(pad.hasAttribute("disabled")).toBe(true);

  value.emit({state: "recovering", errorCode: null});
  expect(screen.getByTestId("audio-state").textContent).toBe("Audio suspended");
  value.setRecoveryProbeReady(true);
  await screen.findByText("Audio recovering");
  expect(pad.hasAttribute("disabled")).toBe(false);
  window.dispatchEvent(new KeyboardEvent("keydown", {code: "KeyQ"}));
  await waitFor(() => expect(value.calls).toContain(
    "recovery:trigger:0:100:keyboard",
  ));

  value.emit({state: "running", errorCode: null});
  await screen.findByText("Audio running");
});

test("an admitted recovery probe stays owned after readiness is consumed", async () => {
  const value = sessionFixture("probe-owner");
  let resolveTrigger: ((admission: {
    sequence: number;
    slot: number;
    velocity: number;
    source: "keyboard";
  }) => void) | null = null;
  value.session.trigger = (slot, velocity, source) => {
    value.calls.push(`probe-owner:trigger:${slot}:${velocity}:${source}`);
    return new Promise((resolve) => {
      resolveTrigger = (admission) => resolve(admission);
    });
  };
  render(<App runtimeFactory={() => value.session} />);

  await userEvent.click(await screen.findByRole("button", {
    name: "Open Project 11111111",
  }));
  await screen.findByRole("heading", {name: "Project 11111111"});
  await act(async () => value.emit({state: "running", errorCode: null}));
  await screen.findByText("Audio running");
  await act(async () => value.emit({state: "interrupted", errorCode: null}));
  await screen.findByText("Audio suspended");
  await act(async () => value.emit({state: "recovering", errorCode: null}));
  value.setRecoveryProbeReady(true);
  await screen.findByText("Audio recovering");

  const pad = screen.getByRole("button", {name: "Pad A1 — assigned"});
  fireEvent.keyDown(window, {code: "KeyA", repeat: false});
  await waitFor(() => expect(value.calls).toContain(
    "probe-owner:trigger:0:100:keyboard",
  ));
  await act(async () => {
    value.setRecoveryProbeReady(false);
    await new Promise((resolve) => window.setTimeout(resolve, 40));
  });
  expect(screen.getByTestId("audio-state").textContent).toBe("Audio recovering");

  await act(async () => resolveTrigger?.({
    sequence: 1,
    slot: 0,
    velocity: 100,
    source: "keyboard",
  }));
  await waitFor(() => expect(pad.dataset.outcome).toBe("admitted"));
  await act(async () => value.outcome({
    sequence: 1,
    outcome: "voice_started",
    runtimeFrame: 128,
  }));
  await waitFor(() => expect(pad.dataset.outcome).toBe("started"));
  fireEvent.keyUp(window, {code: "KeyA"});
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

test("gives an assigned Project Pad keyboard press semantics", async () => {
  const value = sessionFixture("project-keyboard");
  let triggerCount = 0;
  value.session.trigger = async (slot, velocity, source) => {
    triggerCount += 1;
    return {sequence: triggerCount, slot, velocity, source};
  };
  render(<App runtimeFactory={() => value.session} />);
  await userEvent.click(await screen.findByRole("button", {
    name: "Open Project 11111111",
  }));
  await screen.findByRole("heading", {name: "Project 11111111"});
  await act(async () => value.emit({state: "running", errorCode: null}));

  const pad = screen.getByRole("button", {name: "Pad A1 — assigned — Key Q"});
  fireEvent.keyDown(pad, {key: "Enter", code: "Enter", repeat: false});
  fireEvent.keyDown(pad, {key: "Enter", code: "Enter", repeat: true});
  await waitFor(() => {
    expect(triggerCount).toBe(1);
    expect(pad.dataset.outcome).toBe("admitted");
  });
  fireEvent.keyUp(pad, {key: "Enter", code: "Enter"});
  await waitFor(() => expect(pad.dataset.outcome).toBe("idle"));
});

test("lifecycle matrix clears fresh loop toggles without duplicate Session stop ownership", async () => {
  const value = sessionFixture("sample");
  let triggerCount = 0;
  let stopPadCount = 0;
  let stopAllCount = 0;
  let voiceSubscriptions = 0;
  let voiceUnsubscriptions = 0;
  const sampleSession: CreatorSampleRuntimeSession = {
    ...value.session,
    inspectSample: async (slot) => ({
      projectRevision: 3,
      slot,
      assetId: slot === 0 ? "33333333-3333-4333-8333-333333333333" : null,
      playback: {
        trimStartFrame: 0,
        trimEndFrame: slot === 0 ? 8 : null,
        triggerMode: "loop_toggle",
        gainMillidb: 0,
        muted: false,
      },
      metadata: slot === 0
        ? {sampleRate: 48_000, channels: 1, sourceFrames: 8}
        : null,
      waveformCacheIdentity: slot === 0
        ? `${"a".repeat(64)}/1/max-abs-mirror/1`
        : null,
    }),
    queryWaveform: async () => { throw new Error("unused"); },
    importAssignSample: async () => { throw new Error("unused"); },
    updatePad: async () => { throw new Error("unused"); },
    resetPad: async () => { throw new Error("unused"); },
    setSamplePreview: async () => true,
    clearSamplePreview: async () => true,
    release: async () => true,
    stopPad: async () => { stopPadCount += 1; return true; },
    stopAll: async () => { stopAllCount += 1; return true; },
    retryPrepare: async () => { throw new Error("unused"); },
    subscribeVoiceState: () => {
      voiceSubscriptions += 1;
      return () => { voiceUnsubscriptions += 1; };
    },
    trigger: async (slot, velocity, source) => {
      triggerCount += 1;
      return {sequence: triggerCount, slot, velocity, source};
    },
  };
  const replacementSession: CreatorSampleRuntimeSession = {...sampleSession};
  const sessions = [sampleSession, replacementSession];
  let sessionIndex = 0;
  render(<App runtimeFactory={() => sessions[Math.min(sessionIndex++, 1)]!} />);

  await userEvent.click(await screen.findByRole("button", {
    name: "Open Project 11111111",
  }));
  await screen.findByRole("heading", {name: "Project 11111111"});
  await act(async () => value.emit({state: "running", errorCode: null}));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByText("Asset 33333333");
  const pad = screen.getByRole("button", {name: "Pad A1 — assigned"});
  const volume = screen.getByRole("slider", {name: "Pad A1 Volume"});
  fireEvent.change(volume, {target: {value: "-6"}});
  await waitFor(() => expect((volume as HTMLInputElement).value).toBe("-6"));
  await act(async () => value.emit({state: "interrupted", errorCode: null}));
  await waitFor(() => expect((volume as HTMLInputElement).value).toBe("0"));
  await act(async () => value.emit({state: "running", errorCode: null}));
  const latch = async (expectedCount: number) => {
    fireEvent.keyDown(window, {code: "KeyQ", repeat: false});
    await waitFor(() => expect(triggerCount).toBe(expectedCount));
    await act(async () => value.outcome({
      sequence: expectedCount,
      outcome: "voice_started",
      runtimeFrame: expectedCount * 128,
    }));
    fireEvent.keyUp(window, {code: "KeyQ"});
    await waitFor(() => expect(pad.dataset.outcome).toBe("started"));
  };

  await latch(1);
  fireEvent(window, new Event("blur"));
  await waitFor(() => expect(pad.dataset.outcome).toBe("idle"));

  await latch(2);
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "hidden",
  });
  fireEvent(document, new Event("visibilitychange"));
  delete (document as {visibilityState?: string}).visibilityState;
  await waitFor(() => expect(pad.dataset.outcome).toBe("idle"));

  await latch(3);
  await userEvent.click(screen.getByRole("button", {name: "Suspend audio"}));
  await waitFor(() => expect(pad.dataset.outcome).toBe("idle"));

  await act(async () => value.emit({state: "running", errorCode: null}));
  await latch(4);
  await act(async () => value.emit({state: "recovering", errorCode: null}));
  await waitFor(() => expect(pad.dataset.outcome).toBe("idle"));
  const subscriptionsBeforeDuplicate = voiceSubscriptions;
  const unsubscriptionsBeforeDuplicate = voiceUnsubscriptions;
  await act(async () => value.emit({state: "recovering", errorCode: null}));
  expect(voiceSubscriptions).toBe(subscriptionsBeforeDuplicate);
  expect(voiceUnsubscriptions).toBe(unsubscriptionsBeforeDuplicate);
  await act(async () => value.emit({state: "running", errorCode: null}));
  await latch(5);

  await act(async () => value.emit({state: "audio-suspended", errorCode: null}));
  await waitFor(() => expect(pad.dataset.outcome).toBe("idle"));
  await act(async () => value.emit({state: "running", errorCode: null}));
  await latch(6);
  await act(async () => value.emit({state: "audio-suspended", errorCode: null}));
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  await userEvent.click(screen.getByRole("button", {name: "Open local"}));
  await userEvent.click(screen.getByRole("button", {name: "Open Project 11111111"}));
  await screen.findByRole("heading", {name: "Project 11111111"});
  await act(async () => value.emit({state: "running", errorCode: null}));
  fireEvent.keyDown(window, {code: "KeyQ", repeat: false});
  await waitFor(() => expect(triggerCount).toBe(7));
  await act(async () => value.outcome({
    sequence: 7,
    outcome: "voice_started",
    runtimeFrame: 896,
  }));
  fireEvent.keyUp(window, {code: "KeyQ"});

  await act(async () => value.emit({
    state: "restart-required",
    errorCode: "HOST_RESTART_REQUIRED",
  }));
  await waitFor(() => expect(
    value.calls.filter((call) => call === "sample:start"),
  ).toHaveLength(2));
  await waitFor(() => expect(
    value.calls.filter((call) => call === "sample:open"),
  ).toHaveLength(3));
  fireEvent.keyDown(window, {code: "KeyQ", repeat: false});
  await waitFor(() => expect(triggerCount).toBe(8));

  expect(voiceSubscriptions - voiceUnsubscriptions).toBe(1);
  expect(stopPadCount).toBe(0);
  expect(stopAllCount).toBe(0);
});
