import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, expect, test, vi} from "vitest";

import {App} from "../src/app";
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

const OTHER: LocalProjectSummary = {
  ...LISTED,
  projectId: "66666666-6666-4666-8666-666666666666",
  patternId: "77777777-7777-4777-8777-777777777777",
};
const LAST_PROJECT_KEY = "lmdj.creator.last-project.v1";

function memoryStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
    clear: () => { values.clear(); },
  };
}

afterEach(() => { vi.unstubAllGlobals(); });

// An empty Project truth for whichever identity the session last opened or
// created, so opening and creating run through the real journeys.
function projectFixture(
  initial: LocalProjectSummary[],
  overrides: Partial<CreatorRuntimeSession> = {},
) {
  const calls: string[] = [];
  const hostListeners = new Set<(state: RuntimeHostState) => void>();
  let inventory = [...initial];
  let current: LocalProjectSummary | null = null;
  const session: CreatorRuntimeSession = {
    start: async () => true,
    close: async () => true,
    listLocalProjects: async () => { calls.push("listLocalProjects"); return inventory; },
    importProject: async () => { throw new Error("import is not expected"); },
    createProject: async (request) => {
      calls.push("createProject");
      current = {...LISTED, projectId: request.projectId, patternId: request.patternId};
      inventory = [...inventory, current];
      return {};
    },
    openProject: async (projectId) => {
      calls.push(`openProject:${projectId}`);
      current = inventory.find((summary) => summary.projectId === projectId) ?? null;
      return {};
    },
    inspectProject: async () => ({
      project_revision: 0,
      project: {
        contract: "lmdj.project.v3",
        project_id: current?.projectId,
        revision: 0,
        bpm: 120,
        assets: {},
        banks: Array.from({length: 4}, (_, bank) => ({
          bank,
          pads: Array.from({length: 16}, (_, pad) => ({pad, asset_id: null})),
        })),
        patterns: {[current?.patternId ?? ""]: {bars: 1, events: []}},
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
    ...overrides,
  };
  const emit = (state: RuntimeHostState) => {
    for (const listener of hostListeners) listener(state);
  };
  return {calls, emit, session};
}

function refusal(code: string): Error & {code: string} {
  return Object.assign(new Error(code), {code});
}

function sampleKeyIsCurrent(): boolean {
  return screen.getByRole("button", {name: "Sample"}).getAttribute("aria-current") === "page";
}

test("New Project creates a Project, lists it and lands on Sample", async () => {
  const fixture = projectFixture([LISTED]);
  render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByRole("button", {name: "Open Project 11111111"});
  await userEvent.click(screen.getByRole("button", {name: "New Project"}));
  await waitFor(() => expect(sampleKeyIsCurrent()).toBe(true));
  expect(fixture.calls.filter((call) => call === "createProject")).toHaveLength(1);
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  await userEvent.click(screen.getByRole("button", {name: "Open local"}));
  expect(screen.getAllByRole("button", {name: /^Open Project /})).toHaveLength(2);
});

test("a create whose read fails keeps the error and lists the stored Project", async () => {
  const fixture = projectFixture([LISTED], {
    inspectProject: async () => {
      throw Object.assign(new Error("read failed"), {code: "IO_ERROR"});
    },
  });
  render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByRole("button", {name: "Open Project 11111111"});
  await userEvent.click(screen.getByRole("button", {name: "New Project"}));
  await screen.findByRole("alert");
  await waitFor(() =>
    expect(screen.getAllByRole("button", {name: /^Open Project /})).toHaveLength(2));
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(fixture.calls.filter((call) => call === "createProject")).toHaveLength(1);
});

test("boot on a device with no Project creates one and lands on Sample", async () => {
  vi.stubGlobal("localStorage", memoryStorage());
  const fixture = projectFixture([]);
  render(<App runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(sampleKeyIsCurrent()).toBe(true));
  expect(fixture.calls.filter((call) => call === "createProject")).toHaveLength(1);
  expect(fixture.calls.some((call) => call.startsWith("openProject"))).toBe(false);
});

test("boot reopens the remembered Project", async () => {
  vi.stubGlobal("localStorage", memoryStorage({[LAST_PROJECT_KEY]: OTHER.projectId}));
  const fixture = projectFixture([LISTED, OTHER]);
  render(<App runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain(`openProject:${OTHER.projectId}`));
  expect(fixture.calls).not.toContain("createProject");
});

test("boot with stored Projects but none remembered stays in the library", async () => {
  vi.stubGlobal("localStorage", memoryStorage());
  const fixture = projectFixture([LISTED]);
  render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByRole("button", {name: "Open Project 11111111"});
  expect(fixture.calls).not.toContain("createProject");
  expect(fixture.calls.some((call) => call.startsWith("openProject"))).toBe(false);
});

test("an opened Project is remembered for the next boot", async () => {
  const storage = memoryStorage();
  vi.stubGlobal("localStorage", storage);
  const fixture = projectFixture([LISTED]);
  render(<App runtimeFactory={() => fixture.session} />);
  await userEvent.click(await screen.findByRole("button", {name: "Open Project 11111111"}));
  await waitFor(() => expect(storage.values.get(LAST_PROJECT_KEY)).toBe(LISTED.projectId));
});

test("boot shows a busy remembered Project as retryable and creates nothing", async () => {
  vi.stubGlobal("localStorage", memoryStorage({[LAST_PROJECT_KEY]: LISTED.projectId}));
  const fixture = projectFixture([LISTED], {
    openProject: async () => { throw refusal("PROJECT_BUSY"); },
  });
  render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByText("The local Project is busy in another tab or process.");
  expect(screen.getByRole("button", {name: "Retry project"})).toBeTruthy();
  expect(fixture.calls).not.toContain("createProject");
});

test("a failed boot reopen reports the error instead of creating a Project", async () => {
  vi.stubGlobal("localStorage", memoryStorage({[LAST_PROJECT_KEY]: LISTED.projectId}));
  const fixture = projectFixture([LISTED], {
    openProject: async () => { throw refusal("LOCAL_PROJECT_UNREADABLE"); },
  });
  render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByText(/could not be read/);
  expect(fixture.calls).not.toContain("createProject");
});

test("a failed first-run create reports the error and remembers no Project", async () => {
  const storage = memoryStorage();
  vi.stubGlobal("localStorage", storage);
  let creates = 0;
  const fixture = projectFixture([], {
    createProject: async () => { creates += 1; throw refusal("IO_ERROR"); },
  });
  render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByRole("alert");
  expect(creates).toBe(1);
  expect(sampleKeyIsCurrent()).toBe(false);
  expect(storage.values.has(LAST_PROJECT_KEY)).toBe(false);
});

test("a first-run create whose read fails keeps the error and lists the stored Project", async () => {
  vi.stubGlobal("localStorage", memoryStorage());
  const fixture = projectFixture([], {
    inspectProject: async () => { throw refusal("IO_ERROR"); },
  });
  render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByRole("alert");
  await waitFor(() =>
    expect(screen.getAllByRole("button", {name: /^Open Project /})).toHaveLength(1));
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(fixture.calls.filter((call) => call === "createProject")).toHaveLength(1);
});

test("a Runtime replaced during boot discards the retired session's late reopen", async () => {
  vi.stubGlobal("localStorage", memoryStorage({[LAST_PROJECT_KEY]: LISTED.projectId}));
  let release: (() => void) | undefined;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  const retired = projectFixture([LISTED], {
    openProject: async () => { await pending; return {}; },
  });
  // The retired session reports a later revision, so its reopen landing
  // would be visible in the overview.
  const inspect = retired.session.inspectProject;
  retired.session.inspectProject = async () => {
    retired.calls.push("inspectProject");
    const result = await inspect() as {project: Record<string, unknown>};
    return {
      ...result,
      project_revision: 9,
      project: {
        ...result.project,
        project_id: LISTED.projectId,
        revision: 9,
        patterns: {[LISTED.patternId]: {bars: 1, events: []}},
      },
    };
  };
  const replacement = projectFixture([LISTED]);
  const sessions = [retired, replacement];
  let creations = 0;
  render(<App runtimeFactory={() => sessions[creations++]!.session} />);
  await waitFor(() => expect(creations).toBe(1));
  retired.emit({state: "restart-required", errorCode: "HOST_RESTART_REQUIRED", errorDetails: {}});
  await waitFor(() => expect(overviewRevision()).toBe("0"));
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  release?.();
  await waitFor(() => expect(retired.calls).toContain("inspectProject"));
  await new Promise((resolve) => setTimeout(resolve, 50));
  // Neither the retired Project nor its landing navigation reaches the page.
  expect(overviewRevision()).toBe("0");
  expect(screen.getByRole("button", {name: "Project"}).getAttribute("aria-current"))
    .toBe("page");
});

function overviewRevision(): string | null {
  const facts = screen.getByRole("region", {name: "Overview display"})
    .querySelectorAll(".overview-facts div");
  const rev = [...facts].find((fact) => fact.querySelector("dt")?.textContent === "Rev");
  return rev?.querySelector("dd")?.textContent ?? null;
}
