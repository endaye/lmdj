import {describe, expect, test} from "vitest";

import {
  createProjectActionLane,
  importProjectJourney,
  listLocalProjectsJourney,
  openProjectJourney,
} from "../src/runtime/project_actions";
import type {
  CreatorRuntimeSession,
  LocalProjectSummary,
} from "../src/runtime/runtime_types";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
const PATTERN_ID = "22222222-2222-4222-8222-222222222222";
const TEST_PRODUCT_BUILD = "9.8.7.6";

const summary: LocalProjectSummary = {
  projectId: PROJECT_ID,
  patternId: PATTERN_ID,
  revision: 3,
  bpm: 120,
  assetCount: 1,
  assignedPadCount: 1,
  bundleDigest: "a".repeat(64),
};

function inspectResult(projectId = PROJECT_ID) {
  return {
    project_revision: 3,
    project: {
      contract: "lmdj.project.v1",
      project_id: projectId,
      revision: 3,
      bpm: 120,
      assets: {["33333333-3333-4333-8333-333333333333"]: {artifact: {}}},
      banks: Array.from({length: 4}, (_, bank) => ({
        bank,
        pads: Array.from({length: 16}, (_, pad) => ({
          pad,
          asset_id: bank === 2 && pad === 3
            ? "33333333-3333-4333-8333-333333333333"
            : null,
        })),
      })),
      patterns: {},
      takes: {},
    },
  };
}

function sessionFixture(overrides: Partial<CreatorRuntimeSession> = {}) {
  const calls: string[] = [];
  const session: CreatorRuntimeSession = {
    start: async () => true,
    close: async () => true,
    listLocalProjects: async () => [],
    importProject: async () => {
      calls.push("importProject");
      return summary;
    },
    openProject: async () => {
      calls.push("openProject");
      return {};
    },
    inspectProject: async () => {
      calls.push("inspectProject");
      return inspectResult();
    },
    reloadSnapshot: async () => {
      calls.push("reloadSnapshot");
      return {};
    },
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
      product_build: TEST_PRODUCT_BUILD,
      host_id: "creator-web",
      host_version: "1.3.3",
      platform_version: "0.3.3",
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

describe("Project journeys", () => {
  test("serializes one generation-scoped Project action and rejects stale owners", () => {
    const first = sessionFixture().session;
    const second = sessionFixture().session;
    const lane = createProjectActionLane();
    const token = lane.claim(first);
    expect(token).not.toBeNull();
    expect(lane.claim(first)).toBeNull();
    expect(lane.owns(token!, first)).toBe(true);
    expect(lane.owns(token!, second)).toBe(false);
    lane.invalidate();
    expect(lane.owns(token!, first)).toBe(false);
    const replacement = lane.claim(second);
    expect(lane.owns(replacement!, second)).toBe(true);
    lane.finish(replacement!);
    expect(lane.busy).toBe(false);
  });

  test("sorts the local inventory and preserves an empty inventory", async () => {
    const second = {...summary, projectId: "00000000-0000-4000-8000-000000000002"};
    const first = {...summary, projectId: "00000000-0000-4000-8000-000000000001"};
    const {session} = sessionFixture({
      listLocalProjects: async () => [second, first],
    });
    expect((await listLocalProjectsJourney(session)).map(({projectId}) => projectId))
      .toEqual([first.projectId, second.projectId]);
    session.listLocalProjects = async () => [];
    expect(await listLocalProjectsJourney(session)).toEqual([]);
  });

  test("opens, inspects, reloads, and emits one authoritative View Model", async () => {
    const {calls, session} = sessionFixture();
    const view = await openProjectJourney(session, summary);
    expect(calls).toEqual(["openProject", "inspectProject", "reloadSnapshot"]);
    expect(view.projectId).toBe(PROJECT_ID);
    expect(view.key).toBe("—");
    expect(view.pads).toHaveLength(64);
    expect(view.pads[35]?.assetId).toBe(
      "33333333-3333-4333-8333-333333333333",
    );
  });

  test("imports then uses the same open journey and forwards progress", async () => {
    const {calls, session} = sessionFixture();
    const progress: {completedBytes: number; totalBytes: number}[] = [];
    const signal = new AbortController().signal;
    const file = new File(["bundle"], "beat.lmdj");
    const view = await importProjectJourney(
      session,
      file,
      signal,
      (value) => progress.push(value),
    );
    expect(calls).toEqual([
      "importProject", "openProject", "inspectProject", "reloadSnapshot",
    ]);
    expect(view.projectId).toBe(PROJECT_ID);
    expect(view.key).toBe("—");
  });

  test.each([
    "INVALID_PROJECT",
    "DUPLICATE_ID",
    "PROJECT_BUSY",
    "WEB_RUNTIME_RESOURCE_LIMIT",
    "HOST_RESTART_REQUIRED",
  ])("keeps typed %s rejection authoritative", async (code) => {
    const primary = Object.assign(new Error("safe"), {code});
    const {calls, session} = sessionFixture({
      importProject: async () => {
        calls.push("importProject");
        throw primary;
      },
    });
    await expect(importProjectJourney(
      session,
      new File(["bundle"], "beat.lmdj"),
      new AbortController().signal,
      () => {},
    )).rejects.toBe(primary);
    expect(calls).toEqual(["importProject"]);
  });

  test("keeps AbortError authoritative", async () => {
    const primary = new DOMException("cancelled", "AbortError");
    const {session} = sessionFixture({
      importProject: async () => { throw primary; },
    });
    await expect(importProjectJourney(
      session,
      new File(["bundle"], "beat.lmdj"),
      new AbortController().signal,
      () => {},
    )).rejects.toBe(primary);
  });
});
