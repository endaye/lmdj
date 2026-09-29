import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test} from "vitest";

import {App} from "../src/app";
import type {
  CreatorRuntimeSession,
  LocalProjectSummary,
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

// An empty Project truth for whichever identity the session last opened or
// created, so opening and creating run through the real journeys.
function projectFixture(
  initial: LocalProjectSummary[],
  overrides: Partial<CreatorRuntimeSession> = {},
) {
  const calls: string[] = [];
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
    subscribeHostState: () => () => {},
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
  return {calls, session};
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
