import {describe, expect, test} from "vitest";

import * as projectActions from "../src/runtime/project_actions";
import {
  createProjectActionLane,
  createProjectJourney,
  duplicateProjectJourney,
  importProjectJourney,
  listLocalProjectsJourney,
  openProjectJourney,
  refreshProjectProjectionJourney,
} from "../src/runtime/project_actions";
import type {
  CreatorRuntimeSession,
  LocalProjectSummary,
} from "../src/runtime/runtime_types";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
const PATTERN_ID = "22222222-2222-4222-8222-222222222222";
const SECOND_PATTERN_ID = "44444444-4444-4444-8444-444444444444";
const UNKNOWN_PATTERN_ID = "55555555-5555-4555-8555-555555555555";
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

function inspectV3(projectId = PROJECT_ID): {
  project_revision: number;
  project: Record<string, unknown>;
} {
  return {
    project_revision: 3,
    project: {
      contract: "lmdj.project.v3",
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
          category: null,
          colour_override: null,
          colour: null,
        })),
      })),
      patterns: {[PATTERN_ID]: {bars: 1, events: []}},
      sequence_settings: {quantize_enabled: true, swing_percent: 50},
    },
  };
}

function inspectV4(patternSlots: readonly (string | null)[]) {
  const inspected = inspectV3();
  inspected.project.contract = "lmdj.project.v4";
  inspected.project.patterns = {
    [PATTERN_ID]: {bars: 1, events: []},
    [SECOND_PATTERN_ID]: {bars: 4, events: []},
  };
  inspected.project.pattern_slots = [...patternSlots];
  inspected.project.performances = {};
  return inspected;
}

function sessionFor(inspected: ReturnType<typeof inspectV3>) {
  return sessionFixture({inspectProject: async () => inspected}).session;
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
    duplicateProject: async () => { throw new Error("duplicate is not expected"); },
    createProject: async () => {
      calls.push("createProject");
      return {};
    },
    openProject: async () => {
      calls.push("openProject");
      return {};
    },
    inspectProject: async () => {
      calls.push("inspectProject");
      return inspectV3();
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

  test("creates a Project with the default tempo and a one-Bar Pattern under fresh identities", async () => {
    const requests: unknown[] = [];
    const ids = [PROJECT_ID, PATTERN_ID];
    const {session} = sessionFixture({
      createProject: async (request) => { requests.push(request); return {}; },
      listLocalProjects: async () => [summary],
    });
    await createProjectJourney(session, () => ids.shift()!);
    expect(requests).toEqual([{
      projectId: PROJECT_ID,
      patternId: PATTERN_ID,
      bpm: 120,
      bars: 1,
    }]);
  });

  test("reads the created Project without reopening it", async () => {
    const ids = [PROJECT_ID, PATTERN_ID];
    const {session, calls} = sessionFixture({
      listLocalProjects: async () => [summary],
    });
    const view = await createProjectJourney(session, () => ids.shift()!);
    expect(calls).toEqual(["createProject", "inspectProject", "reloadSnapshot"]);
    expect(view.projectId).toBe(PROJECT_ID);
  });

  test("refuses a created Project that the inventory does not list", async () => {
    const ids = [PROJECT_ID, PATTERN_ID];
    const {session} = sessionFixture({listLocalProjects: async () => []});
    await expect(createProjectJourney(session, () => ids.shift()!))
      .rejects.toMatchObject({code: "HOST_PROTOCOL_MISMATCH"});
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

  test("projects v3 to sixteen immutable empty Pattern slots", async () => {
    const inspected = inspectV3();
    const view = await openProjectJourney(sessionFor(inspected), summary);
    expect(view.patternSlots).toEqual(Array(16).fill(null));
    expect(Object.isFrozen(view.patternSlots)).toBe(true);
    expect(view.patternSlots).not.toBe(inspected.project.pattern_slots);
  });

  test.each([
    {field: "pattern_slots", shape: "undefined", value: undefined},
    {field: "pattern_slots", shape: "an empty array", value: []},
    {field: "performances", shape: "undefined", value: undefined},
    {field: "performances", shape: "an empty object", value: {}},
  ])("rejects v3 when $field is present as $shape", async ({field, value}) => {
    const inspected = inspectV3();
    inspected.project[field] = value;
    await expect(openProjectJourney(sessionFor(inspected), summary))
      .rejects.toMatchObject({code: "HOST_PROTOCOL_MISMATCH"});
  });

  test.each(["lmdj.project.v4", "lmdj.project.v5"])("preserves sixteen ordered %s Pattern slots in a new immutable projection", async (contract) => {
    const slots = Array<string | null>(16).fill(null);
    slots[1] = SECOND_PATTERN_ID;
    slots[7] = PATTERN_ID;
    const inspected = inspectV4(slots);
    inspected.project.contract = contract;
    const transportedSlots = inspected.project.pattern_slots;
    const view = await openProjectJourney(sessionFor(inspected), summary);
    expect(view.patternSlots).toEqual(slots);
    expect(Object.isFrozen(view.patternSlots)).toBe(true);
    expect(view.patternSlots).not.toBe(transportedSlots);
  });

  test.each([
    {name: "wrong length", slots: Array<string | null>(15).fill(null)},
    {
      name: "duplicate Pattern",
      slots: [PATTERN_ID, PATTERN_ID, ...Array<string | null>(14).fill(null)],
    },
    {
      name: "dangling Pattern",
      slots: [UNKNOWN_PATTERN_ID, ...Array<string | null>(15).fill(null)],
    },
  ])("rejects v4/v5 $name without returning stale slot truth", async ({slots}) => {
    for (const contract of ["lmdj.project.v4", "lmdj.project.v5"]) {
      const inspected = inspectV4(slots);
      inspected.project.contract = contract;
      await expect(openProjectJourney(sessionFor(inspected), summary))
        .rejects.toMatchObject({code: "HOST_PROTOCOL_MISMATCH"});
    }
  });

  test("rejects an unknown Project contract", async () => {
    const inspected = inspectV3();
    inspected.project.contract = "lmdj.project.v6";
    await expect(openProjectJourney(sessionFor(inspected), summary))
      .rejects.toMatchObject({code: "HOST_PROTOCOL_MISMATCH"});
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

test("Project action module has no New, Save As, or Project export journey", () => {
  expect(projectActions).not.toHaveProperty("createEmptyProject");
  expect(projectActions).not.toHaveProperty("saveAsProject");
  expect(projectActions).not.toHaveProperty("exportProject");
});

 test("refreshes the same Project when history changes its first Pattern anchor", async () => {
  const inspected = inspectV4(Array(16).fill(null));
  const changedSummary = {...summary, patternId: SECOND_PATTERN_ID};
  const {session, calls} = sessionFixture({
    inspectProject: async () => inspected,
    listLocalProjects: async () => [changedSummary],
  });
  const view = await refreshProjectProjectionJourney(session, summary);
  expect(view?.projectId).toBe(PROJECT_ID);
  expect(view?.patternId).toBe(SECOND_PATTERN_ID);
  expect(view?.revision).toBe(3);
  expect(calls).not.toContain("openProject");
});

// A one-bar Pattern is 3840 ticks: the inspection boundary admits exactly the
// Contract's events — no note past the seam, velocity 1..127 — and keeps them.
test("Pattern events outside the Contract's per-bar bounds are a protocol mismatch", async () => {
  const withEvent = (event: Record<string, unknown>) => {
    const inspected = inspectV3();
    inspected.project.patterns = {[PATTERN_ID]: {bars: 1, events: [event]}};
    return sessionFor(inspected);
  };
  const valid = {slot: {bank: 3, pad: 15}, onset_tick: 3600, duration_tick: 240, velocity: 127};
  const view = await openProjectJourney(withEvent(valid), summary);
  expect(view.patterns[0]!.events).toEqual([
    {slot: {bank: 3, pad: 15}, onsetTick: 3600, durationTick: 240, velocity: 127},
  ]);
  for (const invalid of [
    {...valid, onset_tick: 3840, duration_tick: 1},
    {...valid, duration_tick: 241},
    {...valid, duration_tick: 0},
    {...valid, velocity: 128},
    {...valid, velocity: 0},
    {...valid, slot: {bank: 4, pad: 0}},
    {...valid, slot: {bank: 0, pad: 16}},
  ]) {
    await expect(openProjectJourney(withEvent(invalid), summary), JSON.stringify(invalid))
      .rejects.toMatchObject({code: "HOST_PROTOCOL_MISMATCH"});
  }
});

const COPY_ID = "66666666-6666-4666-8666-666666666666";

test("duplicateProjectJourney copies under a new identity and does not open the copy", async () => {
  const requests: unknown[] = [];
  const {session, calls} = sessionFixture({
    duplicateProject: async (request) => {
      requests.push(request);
      return {...summary, projectId: COPY_ID, revision: 0};
    },
  });
  const copy = await duplicateProjectJourney(session, PROJECT_ID, () => COPY_ID);
  expect(requests).toEqual([{sourceProjectId: PROJECT_ID, projectId: COPY_ID}]);
  expect(copy.projectId).toBe(COPY_ID);
  expect(calls).not.toContain("openProject");
});

test("a duplicate summary for another identity or a later revision is a protocol mismatch", async () => {
  for (const returned of [
    {...summary, projectId: PROJECT_ID, revision: 0},
    {...summary, projectId: COPY_ID, revision: 1},
  ]) {
    const {session} = sessionFixture({duplicateProject: async () => returned});
    await expect(duplicateProjectJourney(session, PROJECT_ID, () => COPY_ID))
      .rejects.toMatchObject({code: "HOST_PROTOCOL_MISMATCH"});
  }
});

function padInspection(
  inspected: ReturnType<typeof inspectV3>,
  bank: number,
  pad: number,
): Record<string, unknown> {
  const banks = inspected.project.banks as {pads: Record<string, unknown>[]}[];
  return banks[bank]!.pads[pad]!;
}

test("projectView maps each Pad's category, override and effective colour from inspection", async () => {
  const inspected = inspectV3();
  Object.assign(padInspection(inspected, 2, 3), {
    category: "bass", colour_override: 2, colour: 2,
  });
  const view = await openProjectJourney(sessionFor(inspected), summary);
  expect(view.pads[35]).toEqual({
    slot: 35,
    assetId: "33333333-3333-4333-8333-333333333333",
    category: "bass",
    colourOverride: 2,
    colour: 2,
  });
  expect(view.pads[0]).toEqual({
    slot: 0, assetId: null, category: null, colourOverride: null, colour: null,
  });
});

test.each([
  ["an index outside the palette", {colour: 5}],
  ["a non-integer index", {colour_override: "1"}],
  ["an unknown category", {category: "other"}],
  ["a missing effective colour", {colour: undefined}],
])("a Pad colour inspection with %s is a protocol mismatch", async (_, fields) => {
  const inspected = inspectV3();
  const pad = padInspection(inspected, 2, 3);
  Object.assign(pad, fields);
  for (const [key, value] of Object.entries(fields)) {
    if (value === undefined) delete pad[key];
  }
  await expect(openProjectJourney(sessionFor(inspected), summary)).rejects.toMatchObject({
    code: "HOST_PROTOCOL_MISMATCH",
  });
});
