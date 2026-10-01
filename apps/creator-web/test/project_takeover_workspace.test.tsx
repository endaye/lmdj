import {act, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, beforeEach, expect, test, vi} from "vitest";

import {App} from "../src/app";
import type {
  ProjectTakeoverCoordinator,
  TakeoverDecision,
  TakeoverOutcome,
} from "../src/runtime/project_takeover";
import type {
  CreatorRuntimeSession,
  LocalProjectSummary,
  RuntimeHostState,
} from "../src/runtime/runtime_types";

const LISTED: LocalProjectSummary = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 0,
  bpm: 120,
  assetCount: 0,
  assignedPadCount: 0,
  bundleDigest: "a".repeat(64),
};
const LAST_PROJECT_KEY = "lmdj.creator.last-project.v1";
const BUSY = "The local Project is busy in another tab or process.";

function memoryStorage(initial: Record<string, string>) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
    clear: () => { values.clear(); },
  };
}

beforeEach(() => {
  vi.stubGlobal("localStorage", memoryStorage({[LAST_PROJECT_KEY]: LISTED.projectId}));
});
afterEach(() => { vi.unstubAllGlobals(); });

function refusal(code: string): Error & {code: string} {
  return Object.assign(new Error(code), {code});
}

// One tab's Runtime Session over a store holding LISTED. `opens` decides each
// openProject call in turn; a missing entry opens.
function sessionFixture(opens: Array<"busy" | "open"> = []) {
  const calls: string[] = [];
  const hostListeners = new Set<(state: RuntimeHostState) => void>();
  let openAttempt = 0;
  const session: CreatorRuntimeSession = {
    start: async () => true,
    close: async () => { calls.push("close"); return true; },
    listLocalProjects: async () => [LISTED],
    importProject: async () => { throw new Error("import is not expected"); },
    duplicateProject: async () => { throw new Error("duplicate is not expected"); },
    createProject: async () => { throw new Error("create is not expected"); },
    openProject: async (projectId) => {
      calls.push(`openProject:${projectId}`);
      if (opens[openAttempt++] === "busy") throw refusal("PROJECT_BUSY");
      return {};
    },
    inspectProject: async () => ({
      project_revision: 0,
      project: {
        contract: "lmdj.project.v3",
        project_id: LISTED.projectId,
        revision: 0,
        bpm: 120,
        assets: {},
        banks: Array.from({length: 4}, (_, bank) => ({
          bank,
          pads: Array.from({length: 16}, (_, pad) => ({pad, asset_id: null})),
        })),
        patterns: {[LISTED.patternId]: {bars: 1, events: []}},
        sequence_settings: {quantize_enabled: true, swing_percent: 50},
      },
    }),
    reloadSnapshot: async () => ({}),
    activateAudio: async () => true,
    suspendAudio: async () => true,
    trigger: async () => false,
    requestMidi: async () => true,
    subscribeDiagnostics: () => () => {},
    subscribeHostState: (listener) => {
      hostListeners.add(listener);
      return () => { hostListeners.delete(listener); };
    },
    subscribeRuntimeOutcome: () => () => {},
    diagnostics: () => ({
      state: "audio-suspended",
      error_code: null,
      error_details: {},
      product_build: "9.8.7.6",
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
    }),
  };
  const emit = (state: RuntimeHostState) => {
    for (const listener of hostListeners) listener(state);
  };
  return {calls, emit, session};
}

// A coordinator whose holder registrations and requests the test drives.
function fakeTakeover() {
  const served: Array<{projectId: string; decide: () => TakeoverDecision; active: boolean}> = [];
  const requests: Array<{projectId: string; resolve: (outcome: TakeoverOutcome) => void}> = [];
  const coordinator: ProjectTakeoverCoordinator = {
    serve(projectId, decide) {
      const entry = {projectId, decide, active: true};
      served.push(entry);
      return () => { entry.active = false; };
    },
    request(projectId, {signal} = {}) {
      return new Promise((resolve) => {
        requests.push({projectId, resolve});
        signal?.addEventListener("abort", () => resolve("cancelled"));
      });
    },
    close() {},
  };
  const holder = () => {
    const active = served.filter((entry) => entry.active);
    expect(active).toHaveLength(1);
    return active[0]!;
  };
  return {coordinator, served, requests, holder};
}

async function bootHolder(secondOpens: Array<"busy" | "open"> = []) {
  const first = sessionFixture();
  const second = sessionFixture(secondOpens);
  const sessions = [first.session, second.session];
  let created = 0;
  const takeover = fakeTakeover();
  render(<App
    runtimeFactory={() => sessions[created++]!}
    projectTakeover={takeover.coordinator}
  />);
  await waitFor(() => expect(takeover.served.some((entry) => entry.active)).toBe(true));
  return {first, second, takeover, created: () => created};
}

test("the open Project is served for takeover under its own identity", async () => {
  const {takeover} = await bootHolder();
  expect(takeover.holder().projectId).toBe(LISTED.projectId);
});

test("an accepted takeover closes this Runtime and shows the Project continued elsewhere", async () => {
  const {first, takeover} = await bootHolder();
  let decision: TakeoverDecision | undefined;
  act(() => { decision = takeover.holder().decide(); });
  expect(decision?.accepted).toBe(true);
  await expect(decision?.accepted ? decision.released : null).resolves.toBe(true);
  expect(first.calls.filter((call) => call === "close")).toHaveLength(1);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Project open in another tab");
  expect(screen.getByRole("button", {name: "Continue here"})).toBeTruthy();
});

test("a holder playing audio refuses and keeps its Runtime", async () => {
  const {first, takeover} = await bootHolder();
  act(() => { first.emit({state: "running", errorCode: null, errorDetails: {}}); });
  await screen.findByText("running");
  let decision: TakeoverDecision | undefined;
  act(() => { decision = takeover.holder().decide(); });
  expect(decision).toEqual({accepted: false});
  expect(first.calls).not.toContain("close");
  expect(screen.queryByText("Project open in another tab")).toBeNull();
});

test("a closed holder's Continue here waits for release, then reopens on a fresh Runtime", async () => {
  const {second, takeover, created} = await bootHolder();
  act(() => { takeover.holder().decide(); });
  await userEvent.click(await screen.findByRole("button", {name: "Continue here"}));
  expect(takeover.requests.map(({projectId}) => projectId)).toEqual([LISTED.projectId]);
  expect(created()).toBe(1);
  expect(screen.getByText("Asking the other tab to hand over this Project…")).toBeTruthy();

  act(() => takeover.requests[0]!.resolve("released"));
  await waitFor(() => expect(second.calls).toContain(`openProject:${LISTED.projectId}`));
  expect(created()).toBe(2);
  await waitFor(() => expect(screen.queryByText("Project open in another tab")).toBeNull());
});

test("a take-back whose fresh reopen is still busy offers Continue here again", async () => {
  const {second, takeover} = await bootHolder(["busy"]);
  act(() => { takeover.holder().decide(); });
  await userEvent.click(await screen.findByRole("button", {name: "Continue here"}));
  act(() => takeover.requests[0]!.resolve("unanswered"));
  await waitFor(() => expect(second.calls).toContain(`openProject:${LISTED.projectId}`));
  // The taken-over panel gives way to the busy refusal, which keeps the
  // affordance and names why the take-back did not land.
  const busy = await screen.findByText(BUSY);
  expect(busy.closest("[role=alert]")?.textContent).toMatch(/did not respond/);
  expect(screen.getByRole("button", {name: "Continue here"})).toBeTruthy();
  expect(screen.queryByText("Project open in another tab")).toBeNull();
});

test("a refused take-back keeps this Runtime closed and says why", async () => {
  const {takeover, created} = await bootHolder();
  act(() => { takeover.holder().decide(); });
  await userEvent.click(await screen.findByRole("button", {name: "Continue here"}));
  act(() => takeover.requests[0]!.resolve("refused"));
  await screen.findByText(/The other tab is playing, recording or saving/);
  expect(created()).toBe(1);
  expect(screen.getByRole("button", {name: "Continue here"})).toBeTruthy();
});

async function bootRequester(opens: Array<"busy" | "open">) {
  const fixture = sessionFixture(opens);
  const takeover = fakeTakeover();
  render(<App runtimeFactory={() => fixture.session} projectTakeover={takeover.coordinator} />);
  await screen.findByText(BUSY);
  return {fixture, takeover};
}

const openCalls = (calls: string[]) =>
  calls.filter((call) => call === `openProject:${LISTED.projectId}`);

test("a busy open offers Continue here and opens once the holder releases", async () => {
  const {fixture, takeover} = await bootRequester(["busy", "open"]);
  await userEvent.click(screen.getByRole("button", {name: "Continue here"}));
  expect(takeover.requests.map(({projectId}) => projectId)).toEqual([LISTED.projectId]);
  expect(openCalls(fixture.calls)).toHaveLength(1);

  act(() => takeover.requests[0]!.resolve("released"));
  await waitFor(() => expect(openCalls(fixture.calls)).toHaveLength(2));
  await waitFor(() => expect(screen.queryByText(BUSY)).toBeNull());
  expect(screen.queryByRole("alert")).toBeNull();
});

test.each([
  ["unanswered", /did not respond/],
  ["release-failed", /still closing/],
  ["released", /let go, but the Project is still busy/],
] as const)("an open still busy after %s names that outcome", async (outcome, note) => {
  const {fixture, takeover} = await bootRequester(["busy", "busy"]);
  await userEvent.click(screen.getByRole("button", {name: "Continue here"}));
  act(() => takeover.requests[0]!.resolve(outcome));
  await waitFor(() => expect(openCalls(fixture.calls)).toHaveLength(2));
  await screen.findByText(note);
  expect(screen.getByText(BUSY)).toBeTruthy();
});

test("a refused Continue here does not open and says why", async () => {
  const {fixture, takeover} = await bootRequester(["busy"]);
  await userEvent.click(screen.getByRole("button", {name: "Continue here"}));
  act(() => takeover.requests[0]!.resolve("refused"));
  await screen.findByText(/The other tab is playing, recording or saving/);
  expect(openCalls(fixture.calls)).toHaveLength(1);
});

test("cancelling a waiting Continue here opens nothing and offers it again", async () => {
  const {fixture} = await bootRequester(["busy"]);
  await userEvent.click(screen.getByRole("button", {name: "Continue here"}));
  expect(screen.queryByRole("button", {name: "Retry project"})).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Cancel"}));
  await screen.findByRole("button", {name: "Continue here"});
  expect(screen.queryByText("Asking the other tab to hand over this Project…")).toBeNull();
  expect(openCalls(fixture.calls)).toHaveLength(1);
});

test("without a takeover channel a busy open offers only Retry", async () => {
  const fixture = sessionFixture(["busy"]);
  render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByText(BUSY);
  expect(screen.getByRole("button", {name: "Retry project"})).toBeTruthy();
  expect(screen.queryByRole("button", {name: "Continue here"})).toBeNull();
});
