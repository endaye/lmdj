import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {useEffect} from "react";
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

const TEST_PRODUCT_BUILD = "9.8.7.6";

function Probe() {
  const runtime = useRuntime();
  return <>
    <output aria-label="phase">{runtime.phase}</output>
    <output aria-label="host-state">{runtime.hostState}</output>
    <output aria-label="recovery-probe">{String(runtime.recoveryProbeReady)}</output>
    <output aria-label="error-code">{runtime.errorCode}</output>
    <output aria-label="issue-details">{JSON.stringify(runtime.issue?.details)}</output>
    <button type="button" onClick={runtime.retryRuntime}>Retry runtime</button>
  </>;
}

function YieldProbe() {
  const runtime = useRuntime();
  return <>
    <Probe />
    <button
      type="button"
      onClick={() => {
        void runtime.yieldRuntime().then((clean) => {
          document.title = `yield:${clean}`;
        });
      }}
    >Yield runtime</button>
  </>;
}

function ShutdownBarrierProbe({barrier}: {
  readonly barrier: () => Promise<void>;
}) {
  const runtime = useRuntime();
  useEffect(
    () => runtime.registerShutdownBarrier(barrier),
    [runtime.registerShutdownBarrier, barrier],
  );
  return <Probe />;
}

function defaultDiagnostics(): RuntimeDiagnostics {
  return {
    state: "audio-suspended",
    error_code: null,
    error_details: {},
    product_build: TEST_PRODUCT_BUILD,
    host_id: "creator-web",
    host_version: "1.5.0",
    platform_version: "0.3.6",
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
    duplicateProject: async () => { throw new Error("duplicate is not expected"); },
    createProject: async () => ({}),
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
    emit(state: string, errorCode: string | null) {
      const value = {state, errorCode, errorDetails: {}};
      diagnostics = {
        ...diagnostics,
        state,
        error_code: errorCode,
        error_details: {},
      };
      for (const listener of [...hostListeners]) listener(value);
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

test("pagehide awaits a registered shutdown barrier before closing the Session", async () => {
  const fixture = sessionFixture();
  const order: string[] = [];
  let finishBarrier: (() => void) | undefined;
  const barrierGate = new Promise<void>((resolve) => { finishBarrier = resolve; });
  fixture.session.close = async () => {
    order.push("session:close");
    return true;
  };
  const barrier = vi.fn(async () => {
    order.push("barrier:start");
    await barrierGate;
    order.push("barrier:end");
  });
  const rendered = render(
    <RuntimeProvider factory={() => fixture.session}>
      <ShutdownBarrierProbe barrier={barrier} />
    </RuntimeProvider>,
  );
  await screen.findByText("ready");

  window.dispatchEvent(new Event("pagehide"));
  await waitFor(() => expect(barrier).toHaveBeenCalledTimes(1));
  expect(order).toEqual(["barrier:start"]);

  finishBarrier?.();
  await waitFor(() => expect(order).toEqual([
    "barrier:start", "barrier:end", "session:close",
  ]));
  rendered.unmount();
  await Promise.resolve();
  expect(barrier).toHaveBeenCalledTimes(1);
});

test("automatic replacement awaits shutdown work before closing and creating", async () => {
  const first = sessionFixture();
  const second = sessionFixture();
  const order: string[] = [];
  let finishBarrier: (() => void) | undefined;
  const barrierGate = new Promise<void>((resolve) => { finishBarrier = resolve; });
  first.session.close = async () => {
    order.push("first:close");
    return true;
  };
  second.session.start = async () => {
    order.push("second:start");
    return true;
  };
  const barrier = vi.fn(async () => {
    order.push("barrier:start");
    await barrierGate;
    order.push("barrier:end");
  });
  const sessions = [first.session, second.session];
  let creations = 0;
  const rendered = render(
    <RuntimeProvider factory={() => {
      order.push(`create:${creations + 1}`);
      return sessions[creations++]!;
    }}>
      <ShutdownBarrierProbe barrier={barrier} />
    </RuntimeProvider>,
  );
  await screen.findByText("ready");
  order.splice(0);

  act(() => first.emitHost({
    state: "restart-required",
    errorCode: "HOST_RESTART_REQUIRED",
    errorDetails: {},
  }));
  await waitFor(() => expect(barrier).toHaveBeenCalledTimes(1));
  expect(order).toEqual(["barrier:start"]);
  expect(creations).toBe(1);

  finishBarrier?.();
  await waitFor(() => expect(creations).toBe(2));
  await screen.findByText("ready");
  expect(order).toEqual([
    "barrier:start", "barrier:end", "first:close", "create:2", "second:start",
  ]);
  rendered.unmount();
  await waitFor(() => expect(second.closes()).toBe(1));
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

test("keeps an unsupported startup classification after the terminal Host notification", async () => {
  const fixture = sessionFixture();
  const diagnostics = fixture.session.diagnostics();
  fixture.session.start = async () => false;
  fixture.session.diagnostics = () => ({
    ...diagnostics,
    state: "failed",
    error_code: "UNSUPPORTED_WEB_RUNTIME",
  });
  render(
    <RuntimeProvider factory={() => fixture.session}><Probe /></RuntimeProvider>,
  );
  await screen.findByText("unsupported");

  await act(async () => {
    fixture.emit("failed", "UNSUPPORTED_WEB_RUNTIME");
  });
  expect(screen.getByText("unsupported")).toBeTruthy();
});

test("closes a restart-required Session once before creating its replacement", async () => {
  const first = sessionFixture();
  const second = sessionFixture();
  let finishClose: (() => void) | undefined;
  const closeGate = new Promise<void>((resolve) => { finishClose = resolve; });
  let firstCloseCount = 0;
  const order: string[] = [];
  first.session.close = async () => {
    firstCloseCount += 1;
    order.push("first:close:start");
    await closeGate;
    order.push("first:close:end");
    return true;
  };
  second.session.start = async () => {
    order.push("second:start");
    return true;
  };
  const sessions = [first.session, second.session];
  let creations = 0;
  const rendered = render(
    <RuntimeProvider factory={() => {
      order.push(`create:${creations + 1}`);
      return sessions[creations++]!;
    }}><Probe /></RuntimeProvider>,
  );
  await screen.findByText("ready");

  first.emit("restart-required", "HOST_RESTART_REQUIRED");
  first.emit("restart-required", "HOST_RESTART_REQUIRED");
  await waitFor(() => expect(firstCloseCount).toBe(1));
  expect(creations).toBe(1);
  expect(order).toEqual(["create:1", "first:close:start"]);

  finishClose?.();
  await waitFor(() => expect(creations).toBe(2));
  await screen.findByText("ready");
  expect(order).toEqual([
    "create:1",
    "first:close:start",
    "first:close:end",
    "create:2",
    "second:start",
  ]);
  rendered.unmount();
  await waitFor(() => expect(second.closes()).toBe(1));
  expect(firstCloseCount).toBe(1);
});

test("yield awaits shutdown barriers, closes once and reports a clean close", async () => {
  const fixture = sessionFixture();
  const order: string[] = [];
  fixture.session.close = async () => {
    order.push("session:close");
    return true;
  };
  function YieldWithBarrier() {
    const runtime = useRuntime();
    useEffect(() => runtime.registerShutdownBarrier(async () => {
      order.push("barrier");
    }), [runtime.registerShutdownBarrier]);
    return <YieldProbe />;
  }
  document.title = "";
  render(<RuntimeProvider factory={() => fixture.session}><YieldWithBarrier /></RuntimeProvider>);
  await screen.findByText("ready");

  fireEvent.click(screen.getByRole("button", {name: "Yield runtime"}));
  await waitFor(() => expect(document.title).toBe("yield:true"));
  expect(order).toEqual(["barrier", "session:close"]);
  expect(screen.getByLabelText("phase").textContent).toBe("closed");
});

test("yield reports an unclean close when the Session refuses to close", async () => {
  const fixture = sessionFixture();
  fixture.session.close = async () => false;
  document.title = "";
  render(<RuntimeProvider factory={() => fixture.session}><YieldProbe /></RuntimeProvider>);
  await screen.findByText("ready");
  fireEvent.click(screen.getByRole("button", {name: "Yield runtime"}));
  await waitFor(() => expect(document.title).toBe("yield:false"));
});

test("yield reports an unclean close when closing throws", async () => {
  const fixture = sessionFixture();
  fixture.session.close = async () => { throw new Error("close failed"); };
  document.title = "";
  render(<RuntimeProvider factory={() => fixture.session}><YieldProbe /></RuntimeProvider>);
  await screen.findByText("ready");
  fireEvent.click(screen.getByRole("button", {name: "Yield runtime"}));
  await waitFor(() => expect(document.title).toBe("yield:false"));
});

test("a yielded Session's later failure neither relabels the phase nor replaces it", async () => {
  const fixture = sessionFixture();
  let creations = 0;
  render(<RuntimeProvider factory={() => { creations += 1; return fixture.session; }}>
    <YieldProbe />
  </RuntimeProvider>);
  await screen.findByText("ready");
  fireEvent.click(screen.getByRole("button", {name: "Yield runtime"}));
  await waitFor(() => expect(fixture.closes()).toBe(1));

  act(() => fixture.emit("restart-required", "HOST_RESTART_REQUIRED"));
  act(() => fixture.emit("failed", "INTERNAL_ERROR"));
  expect(screen.getByLabelText("phase").textContent).toBe("closed");
  expect(creations).toBe(1);
});

test("retry after a yield starts a fresh Session", async () => {
  const first = sessionFixture();
  const second = sessionFixture();
  const sessions = [first.session, second.session];
  let creations = 0;
  render(<RuntimeProvider factory={() => sessions[creations++]!}><YieldProbe /></RuntimeProvider>);
  await screen.findByText("ready");
  fireEvent.click(screen.getByRole("button", {name: "Yield runtime"}));
  await waitFor(() => expect(first.closes()).toBe(1));

  fireEvent.click(screen.getByRole("button", {name: "Retry runtime"}));
  await waitFor(() => expect(second.starts()).toBe(1));
  await screen.findByText("ready");
  expect(first.closes()).toBe(1);
});


function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((fulfill, refuse) => {
    resolve = fulfill;
    reject = refuse;
  });
  return {promise, resolve, reject};
}

type ReplacementMode = "automatic" | "manual";
const ORIGINAL_FAILURE_DETAILS = {reason: "original-owner-still-held"};

function requestReplacement(first: ReturnType<typeof sessionFixture>, mode: ReplacementMode) {
  act(() => first.emitHost({
    state: mode === "automatic" ? "restart-required" : "failed",
    errorCode: "HOST_TIMEOUT",
    errorDetails: ORIGINAL_FAILURE_DETAILS,
  }));
  if (mode === "manual") {
    fireEvent.click(screen.getByRole("button", {name: "Retry runtime"}));
  }
}

function expectOriginalFailure(mode: ReplacementMode) {
  expect(screen.getByLabelText("phase").textContent).toBe(
    mode === "automatic" ? "restart-required" : "failed",
  );
  expect(screen.getByLabelText("error-code").textContent).toBe("HOST_TIMEOUT");
  expect(screen.getByLabelText("issue-details").textContent).toBe(
    JSON.stringify(ORIGINAL_FAILURE_DETAILS),
  );
}

for (const mode of ["automatic", "manual"] as const) {
  test(`${mode} replacement awaits the original application barrier, close and positive cleanup`, async () => {
    const first = sessionFixture();
    const second = sessionFixture();
    const barrierGate = deferred<void>();
    const closeGate = deferred<boolean>();
    const cleanupGate = deferred<boolean>();
    const order: string[] = [];
    const barrier = vi.fn(async () => {
      order.push("barrier:start");
      await barrierGate.promise;
      order.push("barrier:end");
    });
    first.session.close = vi.fn(async () => {
      order.push("close:start");
      const result = await closeGate.promise;
      order.push("close:end");
      // A cleanup notification must not erase the first fatal UI.
      first.emit("closed", null);
      return result;
    });
    const waiter = vi.fn(() => {
      order.push("cleanup:wait");
      return cleanupGate.promise;
    });
    first.session.waitForTerminalCleanup = waiter;
    const sessions = [first.session, second.session];
    let creations = 0;
    const factory = vi.fn(() => {
      order.push(`create:${++creations}`);
      return sessions[creations - 1]!;
    });
    const rendered = render(<RuntimeProvider factory={factory}>
      <ShutdownBarrierProbe barrier={barrier} />
    </RuntimeProvider>);
    await screen.findByText("ready");
    order.splice(0);
    requestReplacement(first, mode);
    await waitFor(() => expect(barrier).toHaveBeenCalledTimes(1));
    expect(order).toEqual(["barrier:start"]);
    expect(first.session.close).not.toHaveBeenCalled();
    expect(waiter).not.toHaveBeenCalled();
    expect(factory).toHaveBeenCalledTimes(1);
    expectOriginalFailure(mode);

    await act(async () => { barrierGate.resolve(undefined); await barrierGate.promise; });
    await waitFor(() => expect(first.session.close).toHaveBeenCalledTimes(1));
    expect(waiter).not.toHaveBeenCalled();
    expect(factory).toHaveBeenCalledTimes(1);
    expectOriginalFailure(mode);
    await act(async () => { closeGate.resolve(false); await closeGate.promise; });
    await waitFor(() => expect(waiter).toHaveBeenCalledTimes(1));
    expect(waiter.mock.contexts[0]).toBe(first.session);
    expect(factory).toHaveBeenCalledTimes(1);
    expectOriginalFailure(mode);
    await act(async () => { cleanupGate.resolve(true); await cleanupGate.promise; });
    await waitFor(() => expect(second.starts()).toBe(1));
    await screen.findByText("ready");
    expect(order).toEqual([
      "barrier:start", "barrier:end", "close:start", "close:end", "cleanup:wait", "create:2",
    ]);
    expect(factory).toHaveBeenCalledTimes(2);
    rendered.unmount();
    await waitFor(() => expect(second.closes()).toBe(1));
    expect(first.session.close).toHaveBeenCalledTimes(1);
    expect(waiter).toHaveBeenCalledTimes(1);
  });

  for (const result of ["false", "reject", "undefined"] as const) {
    test(`${mode} replacement refuses ${result} cleanup even after a true close`, async () => {
      const first = sessionFixture();
      const second = sessionFixture();
      const cleanupGate = deferred<boolean>();
      const close = vi.fn(async () => true);
      const waiter = vi.fn(() => cleanupGate.promise);
      first.session.close = close;
      first.session.waitForTerminalCleanup = waiter;
      const sessions = [first.session, second.session];
      let creations = 0;
      const factory = vi.fn(() => sessions[creations++]!);
      render(<RuntimeProvider factory={factory}><Probe /></RuntimeProvider>);
      await screen.findByText("ready");
      requestReplacement(first, mode);
      await waitFor(() => expect(waiter).toHaveBeenCalledTimes(1));
      expect(factory).toHaveBeenCalledTimes(1);
      expectOriginalFailure(mode);
      await act(async () => {
        if (result === "reject") cleanupGate.reject(new Error("actual cleanup rejected"));
        else cleanupGate.resolve(result === "false" ? false : undefined as unknown as boolean);
        await cleanupGate.promise.catch(() => {});
      });
      expect(factory).toHaveBeenCalledTimes(1);
      expect(second.starts()).toBe(0);
      expect(close).toHaveBeenCalledTimes(1);
      expectOriginalFailure(mode);
    });

    test(`${mode} legacy replacement refuses a ${result} close without a cleanup waiter`, async () => {
      const first = sessionFixture();
      const second = sessionFixture();
      const closeGate = deferred<boolean>();
      const close = vi.fn(() => closeGate.promise);
      first.session.close = close;
      expect(first.session.waitForTerminalCleanup).toBeUndefined();
      const sessions = [first.session, second.session];
      let creations = 0;
      const factory = vi.fn(() => sessions[creations++]!);
      render(<RuntimeProvider factory={factory}><Probe /></RuntimeProvider>);
      await screen.findByText("ready");
      requestReplacement(first, mode);
      await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
      await act(async () => {
        if (result === "reject") closeGate.reject(new Error("original close rejected"));
        else closeGate.resolve(result === "false" ? false : undefined as unknown as boolean);
        await closeGate.promise.catch(() => {});
      });
      expect(factory).toHaveBeenCalledTimes(1);
      expect(second.starts()).toBe(0);
      expectOriginalFailure(mode);
    });
  }
}

test("a rejected registered application barrier prevents automatic factory despite a positive SDK waiter", async () => {
  const first = sessionFixture();
  const second = sessionFixture();
  const gate = deferred<void>();
  const barrier = vi.fn(() => gate.promise);
  const close = vi.fn(async () => true);
  const waiter = vi.fn(async () => true);
  first.session.close = close;
  first.session.waitForTerminalCleanup = waiter;
  const sessions = [first.session, second.session];
  let creations = 0;
  const factory = vi.fn(() => sessions[creations++]!);
  render(<RuntimeProvider factory={factory}><ShutdownBarrierProbe barrier={barrier} /></RuntimeProvider>);
  await screen.findByText("ready");
  requestReplacement(first, "automatic");
  await waitFor(() => expect(barrier).toHaveBeenCalledTimes(1));
  await act(async () => {
    gate.reject(new Error("original persistence failed"));
    await gate.promise.catch(() => {});
  });
  expect(close).not.toHaveBeenCalled();
  expect(waiter).not.toHaveBeenCalled();
  expect(factory).toHaveBeenCalledTimes(1);
  expect(second.starts()).toBe(0);
  expectOriginalFailure("automatic");
});

test("unregister observes but retains the original rejected persistence barrier for manual retry", async () => {
  const first = sessionFixture();
  const second = sessionFixture();
  const gate = deferred<void>();
  const barrier = vi.fn(() => gate.promise);
  const close = vi.fn(async () => true);
  const waiter = vi.fn(async () => true);
  first.session.close = close;
  first.session.waitForTerminalCleanup = waiter;
  const sessions = [first.session, second.session];
  let creations = 0;
  const factory = vi.fn(() => sessions[creations++]!);
  const rendered = render(<RuntimeProvider factory={factory}>
    <ShutdownBarrierProbe barrier={barrier} />
  </RuntimeProvider>);
  await screen.findByText("ready");
  // Remove only the owner of this barrier, keeping the same RuntimeProvider.
  rendered.rerender(<RuntimeProvider factory={factory}><Probe /></RuntimeProvider>);
  await waitFor(() => expect(barrier).toHaveBeenCalledTimes(1));
  await act(async () => {
    gate.reject(new Error("original unregistered persistence failed"));
    await gate.promise.catch(() => {});
  });
  requestReplacement(first, "manual");
  await act(async () => {});
  expect(barrier).toHaveBeenCalledTimes(1);
  expect(close).not.toHaveBeenCalled();
  expect(waiter).not.toHaveBeenCalled();
  expect(factory).toHaveBeenCalledTimes(1);
  expect(second.starts()).toBe(0);
  expectOriginalFailure("manual");
});

test("a rejected original close cannot be overridden by a positive SDK waiter", async () => {
  const first = sessionFixture();
  const second = sessionFixture();
  const gate = deferred<boolean>();
  const close = vi.fn(() => gate.promise);
  const waiter = vi.fn(async () => true);
  first.session.close = close;
  first.session.waitForTerminalCleanup = waiter;
  const sessions = [first.session, second.session];
  let creations = 0;
  const factory = vi.fn(() => sessions[creations++]!);
  render(<RuntimeProvider factory={factory}><Probe /></RuntimeProvider>);
  await screen.findByText("ready");
  requestReplacement(first, "manual");
  await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
  await act(async () => {
    gate.reject(new Error("original close rejected"));
    await gate.promise.catch(() => {});
  });
  expect(waiter).not.toHaveBeenCalled();
  expect(factory).toHaveBeenCalledTimes(1);
  expectOriginalFailure("manual");
});

test("mixed automatic and duplicate manual retries share one close and one exact-session cleanup wait", async () => {
  const first = sessionFixture();
  const second = sessionFixture();
  const gate = deferred<boolean>();
  const close = vi.fn(async () => false);
  const waiter = vi.fn(() => gate.promise);
  first.session.close = close;
  first.session.waitForTerminalCleanup = waiter;
  const sessions = [first.session, second.session];
  let creations = 0;
  const factory = vi.fn(() => sessions[creations++]!);
  render(<RuntimeProvider factory={factory}><Probe /></RuntimeProvider>);
  await screen.findByText("ready");
  requestReplacement(first, "automatic");
  await waitFor(() => expect(waiter).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", {name: "Retry runtime"}));
  fireEvent.click(screen.getByRole("button", {name: "Retry runtime"}));
  act(() => first.emitCapturedHost({state: "closed", errorCode: null, errorDetails: {}}));
  expect(factory).toHaveBeenCalledTimes(1);
  expectOriginalFailure("automatic");
  await act(async () => { gate.resolve(true); await gate.promise; });
  await waitFor(() => expect(second.starts()).toBe(1));
  await screen.findByText("ready");
  expect(factory).toHaveBeenCalledTimes(2);
  expect(close).toHaveBeenCalledTimes(1);
  expect(waiter).toHaveBeenCalledTimes(1);
  act(() => first.emitCapturedHost({state: "failed", errorCode: "INTERNAL_ERROR", errorDetails: {}}));
  expect(screen.getByLabelText("phase").textContent).toBe("ready");
});

for (const retirement of ["yield", "pagehide", "unmount"] as const) {
  test(`${retirement} invalidates an in-flight positive replacement without a factory`, async () => {
    const first = sessionFixture();
    const second = sessionFixture();
    const gate = deferred<boolean>();
    const close = vi.fn(async () => false);
    const waiter = vi.fn(() => gate.promise);
    first.session.close = close;
    first.session.waitForTerminalCleanup = waiter;
    const sessions = [first.session, second.session];
    let creations = 0;
    const factory = vi.fn(() => sessions[creations++]!);
    const rendered = render(<RuntimeProvider factory={factory}><YieldProbe /></RuntimeProvider>);
    await screen.findByText("ready");
    requestReplacement(first, retirement === "pagehide" ? "manual" : "automatic");
    await waitFor(() => expect(waiter).toHaveBeenCalledTimes(1));
    if (retirement === "yield") {
      document.title = "";
      fireEvent.click(screen.getByRole("button", {name: "Yield runtime"}));
      await waitFor(() => expect(document.title).toBe("yield:false"));
    } else if (retirement === "pagehide") {
      act(() => window.dispatchEvent(new Event("pagehide")));
    } else {
      rendered.unmount();
    }
    await act(async () => { gate.resolve(true); await gate.promise; });
    expect(factory).toHaveBeenCalledTimes(1);
    expect(second.starts()).toBe(0);
    expect(close).toHaveBeenCalledTimes(1);
    expect(waiter).toHaveBeenCalledTimes(1);
    if (retirement !== "unmount") expect(screen.getByLabelText("phase").textContent).toBe("closed");
  });
}

test("a new Session's negative cleanup cannot reuse the previous Session's eligibility", async () => {
  const first = sessionFixture();
  const second = sessionFixture();
  const third = sessionFixture();
  const firstWait = vi.fn(async () => true);
  const secondGate = deferred<boolean>();
  const secondWait = vi.fn(() => secondGate.promise);
  first.session.close = vi.fn(async () => false);
  first.session.waitForTerminalCleanup = firstWait;
  second.session.close = vi.fn(async () => false);
  second.session.waitForTerminalCleanup = secondWait;
  const sessions = [first.session, second.session, third.session];
  let creations = 0;
  const factory = vi.fn(() => sessions[creations++]!);
  render(<RuntimeProvider factory={factory}><Probe /></RuntimeProvider>);
  await screen.findByText("ready");
  requestReplacement(first, "automatic");
  await waitFor(() => expect(second.starts()).toBe(1));
  await screen.findByText("ready");
  requestReplacement(second, "manual");
  await waitFor(() => expect(secondWait).toHaveBeenCalledTimes(1));
  await act(async () => { secondGate.resolve(false); await secondGate.promise; });
  expect(firstWait).toHaveBeenCalledTimes(1);
  expect(factory).toHaveBeenCalledTimes(2);
  expect(third.starts()).toBe(0);
  expectOriginalFailure("manual");
});
