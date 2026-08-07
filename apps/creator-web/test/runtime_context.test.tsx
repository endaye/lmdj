import {render, screen, waitFor} from "@testing-library/react";
import {expect, test} from "vitest";

import {
  RuntimeProvider,
  useRuntime,
} from "../src/runtime/runtime_context";
import type {CreatorRuntimeSession} from "../src/runtime/runtime_types";

function Probe() {
  const runtime = useRuntime();
  return <output>{runtime.phase}</output>;
}

function sessionFixture({startError}: {startError?: Error} = {}) {
  let starts = 0;
  let closes = 0;
  const session: CreatorRuntimeSession = {
    async start() {
      starts += 1;
      if (startError) throw startError;
      return true;
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
    subscribeHostState: () => () => {},
    subscribeRuntimeOutcome: () => () => {},
    diagnostics: () => ({
      state: "audio-suspended",
      error_code: null,
      product_build: "1.0.16.0",
      host_id: "creator-web",
      host_version: "1.0.0",
      platform_version: "0.1.0",
      protocol_version: 1,
      capabilities: {
        secureContext: true, crossOriginIsolated: true, sharedArrayBuffer: true,
        webAssembly: true, audioWorklet: true, opfs: true,
        opfsSyncAccessHandle: true, opfsWritableReplace: true, webMidi: false,
      },
      trigger_admitted_count: 0,
      trigger_outcome_count: 0,
      trigger_rejected_count: 0,
    }),
  };
  return {session, starts: () => starts, closes: () => closes};
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

test("exposes a typed terminal startup failure", async () => {
  const failure = Object.assign(new Error("unsupported"), {
    code: "UNSUPPORTED_WEB_RUNTIME",
  });
  const fixture = sessionFixture({startError: failure});
  render(
    <RuntimeProvider factory={() => fixture.session}><Probe /></RuntimeProvider>,
  );
  await screen.findByText("unsupported");
});
