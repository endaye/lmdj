import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {
  RuntimeProvider,
  useRuntime,
} from "../src/runtime/runtime_context";
import type {
  CreatorRuntimeSession,
  RuntimeDiagnostics,
  RuntimeHostState,
} from "../src/runtime/runtime_types";

function Probe() {
  const runtime = useRuntime();
  return <>
    <output aria-label="phase">{runtime.phase}</output>
    <output aria-label="host-state">{runtime.hostState}</output>
    <output aria-label="recovery-probe">{String(runtime.recoveryProbeReady)}</output>
    <button type="button" onClick={runtime.retryRuntime}>Retry runtime</button>
  </>;
}

function defaultDiagnostics(): RuntimeDiagnostics {
  return {
    state: "audio-suspended",
    error_code: null,
    error_details: {},
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
  };
}

function sessionFixture({
  startError,
  startResult = true,
  initialDiagnostics = defaultDiagnostics(),
}: {
  startError?: Error;
  startResult?: boolean;
  initialDiagnostics?: RuntimeDiagnostics;
} = {}) {
  let starts = 0;
  let closes = 0;
  let diagnostics = initialDiagnostics;
  const hostListeners = new Set<(value: RuntimeHostState) => void>();
  const diagnosticListeners = new Set<(value: RuntimeDiagnostics) => void>();
  const capturedHostListeners: Array<(value: RuntimeHostState) => void> = [];
  const session: CreatorRuntimeSession = {
    async start() {
      starts += 1;
      if (startError) throw startError;
      return startResult;
    },
    async close() {
      closes += 1;
      return true;
    },
    listLocalProjects: async () => [],
    importProject: async () => { throw new Error("unused"); },
    openProject: async () => ({}),
    inspectProject: async () => ({}),
    reloadSnapshot: async () => ({}),
    activateAudio: async () => true,
    suspendAudio: async () => true,
    trigger: async () => false,
    requestMidi: async () => true,
    subscribeDiagnostics(listener) {
      diagnosticListeners.add(listener);
      return () => diagnosticListeners.delete(listener);
    },
    subscribeHostState(listener) {
      hostListeners.add(listener);
      capturedHostListeners.push(listener);
      return () => hostListeners.delete(listener);
    },
    subscribeRuntimeOutcome: () => () => {},
    diagnostics: () => diagnostics,
  };
  return {
    session,
    starts: () => starts,
    closes: () => closes,
    diagnosticListenerCount: () => diagnosticListeners.size,
    emitDiagnostics(value: RuntimeDiagnostics) {
      diagnostics = value;
      for (const listener of [...diagnosticListeners]) listener(value);
    },
    emitHost(value: RuntimeHostState) {
      diagnostics = {
        ...diagnostics,
        state: value.state,
        error_code: value.errorCode,
        error_details: value.errorDetails,
      };
      for (const listener of [...hostListeners]) listener(value);
    },
    emitCapturedHost(value: RuntimeHostState) {
      capturedHostListeners[0]?.(value);
    },
  };
}

test("creates and starts one Runtime Session and closes it once", async () => {
  const fixture = sessionFixture();
  let creations = 0;
  const factory = () => {
    creations += 1;
    return fixture.session;
  };
  const rendered = render(
    <RuntimeProvider factory={factory}><Probe /></RuntimeProvider>,
  );
  await screen.findByText("ready");
  rendered.rerender(
    <RuntimeProvider factory={factory}><Probe /></RuntimeProvider>,
  );
  expect(creations).toBe(1);
  expect(fixture.starts()).toBe(1);

  window.dispatchEvent(new Event("pagehide"));
  await waitFor(() => expect(fixture.closes()).toBe(1));
  rendered.unmount();
  await Promise.resolve();
  expect(fixture.closes()).toBe(1);
});

test("keeps the Runtime Session alive across persisted page lifecycle", async () => {
  const fixture = sessionFixture();
  const rendered = render(
    <RuntimeProvider factory={() => fixture.session}><Probe /></RuntimeProvider>,
  );
  await screen.findByText("ready");

  window.dispatchEvent(new PageTransitionEvent("pagehide", {persisted: true}));
  window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted: true}));
  await Promise.resolve();

  expect(fixture.closes()).toBe(0);
  expect(screen.getByText("ready")).toBeTruthy();
  rendered.unmount();
  await waitFor(() => expect(fixture.closes()).toBe(1));
});

test("exposes a typed terminal startup failure", async () => {
  const failure = Object.assign(new Error("unsupported"), {
    code: "UNSUPPORTED_WEB_RUNTIME",
    details: {},
  });
  const fixture = sessionFixture({startError: failure});
  render(
    <RuntimeProvider factory={() => fixture.session}><Probe /></RuntimeProvider>,
  );
  await screen.findByText("unsupported");
});

test("preserves unsupported when startup returns a failed Host state", async () => {
  const fixture = sessionFixture({
    startResult: false,
    initialDiagnostics: {
      ...defaultDiagnostics(),
      state: "failed",
      error_code: "UNSUPPORTED_WEB_RUNTIME",
    },
  });
  render(
    <RuntimeProvider factory={() => fixture.session}><Probe /></RuntimeProvider>,
  );
  await screen.findByText("unsupported");
});

test("uses push diagnostics for recovery without a 16 ms polling timer", async () => {
  const fixture = sessionFixture();
  const rendered = render(
    <RuntimeProvider factory={() => fixture.session}><Probe /></RuntimeProvider>,
  );
  await screen.findByText("ready");
  const timeout = vi.spyOn(window, "setTimeout");
  timeout.mockClear();

  act(() => {
    fixture.emitHost({state: "recovering", errorCode: null, errorDetails: {}});
    fixture.emitDiagnostics({
      ...defaultDiagnostics(),
      state: "recovering",
      recovery_probe_ready: true,
    });
  });

  expect(screen.getByLabelText("recovery-probe").textContent).toBe("true");
  expect(timeout).not.toHaveBeenCalled();
  timeout.mockRestore();
  rendered.unmount();
  expect(fixture.diagnosticListenerCount()).toBe(0);
});

test("automatically replaces once, ignores stale callbacks, and allows manual retry", async () => {
  const first = sessionFixture();
  const second = sessionFixture();
  const third = sessionFixture();
  const sessions = [first, second, third];
  let creations = 0;
  render(
    <RuntimeProvider factory={() => sessions[creations++]!.session}>
      <Probe />
    </RuntimeProvider>,
  );
  await screen.findByText("ready");

  act(() => first.emitHost({
    state: "restart-required",
    errorCode: "HOST_TIMEOUT",
    errorDetails: {},
  }));
  await waitFor(() => expect(second.starts()).toBe(1));
  await screen.findByText("ready");
  act(() => first.emitCapturedHost({
    state: "failed",
    errorCode: "INTERNAL_ERROR",
    errorDetails: {},
  }));
  expect(screen.getByLabelText("phase").textContent).toBe("ready");

  act(() => second.emitHost({
    state: "restart-required",
    errorCode: "HOST_RESTART_REQUIRED",
    errorDetails: {terminal_state: "restart-required"},
  }));
  await waitFor(() => expect(
    screen.getByLabelText("phase").textContent,
  ).toBe("restart-required"));
  expect(creations).toBe(2);

  fireEvent.click(screen.getByRole("button", {name: "Retry runtime"}));
  await waitFor(() => expect(third.starts()).toBe(1));
  await screen.findByText("ready");
  expect(second.closes()).toBe(1);
});

test("stable running resets the automatic replacement allowance", async () => {
  const first = sessionFixture();
  const second = sessionFixture();
  const third = sessionFixture();
  const sessions = [first, second, third];
  let creations = 0;
  render(
    <RuntimeProvider factory={() => sessions[creations++]!.session}>
      <Probe />
    </RuntimeProvider>,
  );
  await screen.findByText("ready");
  act(() => first.emitHost({
    state: "restart-required",
    errorCode: "HOST_TIMEOUT",
    errorDetails: {},
  }));
  await waitFor(() => expect(second.starts()).toBe(1));

  act(() => second.emitHost({state: "running", errorCode: null, errorDetails: {}}));
  act(() => second.emitHost({
    state: "restart-required",
    errorCode: "HOST_TIMEOUT",
    errorDetails: {},
  }));
  await waitFor(() => expect(third.starts()).toBe(1));
  expect(creations).toBe(3);
});
