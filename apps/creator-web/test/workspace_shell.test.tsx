import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test} from "vitest";

import {App} from "../src/app";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import type {
  CreatorRuntimeSession,
  LocalProjectSummary,
} from "../src/runtime/runtime_types";

const ready: CreatorState = {
  ...initialCreatorState,
  project: {
    phase: "ready",
    projects: [],
    current: {
      projectId: "11111111-1111-4111-8111-111111111111",
      patternId: "22222222-2222-4222-8222-222222222222",
      revision: 4,
      bpm: 120,
      assetCount: 0,
      assignedPadCount: 0,
      bundleDigest: "a".repeat(64),
      key: "—",
      pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null})),
    },
  },
  runtime: {phase: "ready", errorCode: null},
};

test("renders the approved workspace without inventing future modes or Project truth", async () => {
  const user = userEvent.setup();
  render(<App initialState={ready} />);

  const projectMode = screen.getByRole("button", {name: "Project"});
  expect(projectMode.hasAttribute("disabled")).toBe(false);
  for (const [mode, stage] of [
    ["Sample", 8],
    ["Sequence", 9],
    ["Perform", 10],
  ] as const) {
    const button = screen.getByRole("button", {
      name: `${mode} — available in Stage ${stage}`,
    });
    expect(button.hasAttribute("disabled")).toBe(true);
    expect(button.tabIndex).toBe(-1);
  }

  expect(screen.getByText("Key").nextElementSibling?.textContent).toBe("—");
  expect(screen.queryByText(/untitled/i)).toBeNull();
  expect(screen.queryByText(/beat\.lmdj/i)).toBeNull();
  expect(screen.getAllByRole("button", {
    name: /^Pad [A-D](?:[1-9]|1[0-6]) — empty$/,
  })).toHaveLength(16);

  await user.tab();
  expect(document.activeElement).toBe(
    screen.getByRole("button", {name: "Activate audio"}),
  );
  await user.tab();
  expect(document.activeElement).toBe(projectMode);
  await user.tab();
  expect(document.activeElement).toBe(
    screen.getByRole("button", {name: "Open local"}),
  );
});

const listedSummary: LocalProjectSummary = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 3,
  bpm: 120,
  assetCount: 1,
  assignedPadCount: 1,
  bundleDigest: "a".repeat(64),
};

function runtimeFixture(overrides: Partial<CreatorRuntimeSession> = {}) {
  const calls: string[] = [];
  const session: CreatorRuntimeSession = {
    start: async () => { calls.push("start"); return true; },
    close: async () => { calls.push("close"); return true; },
    listLocalProjects: async () => {
      calls.push("listLocalProjects");
      return [listedSummary];
    },
    importProject: async (_file, {onProgress}) => {
      calls.push("importProject");
      onProgress({completedBytes: 6, totalBytes: 6});
      return listedSummary;
    },
    openProject: async () => { calls.push("openProject"); return {}; },
    inspectProject: async () => {
      calls.push("inspectProject");
      return {
        project_revision: 3,
        project: {
          contract: "lmdj.project.v1",
          project_id: listedSummary.projectId,
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
    },
    reloadSnapshot: async () => { calls.push("reloadSnapshot"); return {}; },
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
      host_version: "1.0.0",
      protocol_version: 1,
      trigger_admitted_count: 0,
      trigger_outcome_count: 0,
      trigger_rejected_count: 0,
    }),
    ...overrides,
  };
  return {calls, session};
}

test("lists, opens, and imports through the injected Runtime Session", async () => {
  const user = userEvent.setup();
  const fixture = runtimeFixture();
  const {container} = render(
    <App runtimeFactory={() => fixture.session} />,
  );
  const open = await screen.findByRole("button", {
    name: "Open Project 11111111",
  });
  expect(screen.getByText("Revision 3")).toBeTruthy();
  expect(screen.getByText("120 BPM")).toBeTruthy();
  expect(screen.getByText("1 assigned Pad")).toBeTruthy();
  expect(screen.getByText("1 Asset")).toBeTruthy();
  await user.click(screen.getByRole("button", {
    name: "Sample — available in Stage 8",
  }));
  expect(fixture.calls).toEqual(["start", "listLocalProjects"]);
  await user.click(open);
  await screen.findByRole("heading", {name: "Project 11111111"});
  expect(fixture.calls).toEqual([
    "start",
    "listLocalProjects",
    "openProject",
    "inspectProject",
    "reloadSnapshot",
  ]);

  await user.click(screen.getByRole("button", {name: "Import .lmdj"}));
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  expect(input).not.toBeNull();
  await user.upload(input!, new File(["bundle"], "beat.lmdj", {
    type: "application/vnd.lmdj.project-bundle",
  }));
  await waitFor(() => expect(fixture.calls.filter((call) =>
    call === "reloadSnapshot")).toHaveLength(2));
  expect(screen.queryByText("beat.lmdj")).toBeNull();
});

test("presents Project busy with an explicit retry", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  const fixture = runtimeFixture({
    listLocalProjects: async () => {
      attempts += 1;
      if (attempts === 1) {
        throw Object.assign(new Error("busy"), {code: "PROJECT_BUSY"});
      }
      return [];
    },
  });
  render(<App runtimeFactory={() => fixture.session} />);
  expect((await screen.findByRole("alert")).textContent).toContain("PROJECT_BUSY");
  await user.click(screen.getByRole("button", {name: "Retry"}));
  await screen.findByText("No local Project is open.");
  expect(attempts).toBe(2);
});

test.each([
  "INVALID_PROJECT",
  "DUPLICATE_ID",
  "WEB_RUNTIME_RESOURCE_LIMIT",
  "HOST_RESTART_REQUIRED",
])("presents a safe typed %s import failure without exposing the filename", async (code) => {
  const user = userEvent.setup();
  const fixture = runtimeFixture({
    importProject: async () => {
      throw Object.assign(new Error("private implementation detail"), {code});
    },
  });
  const {container} = render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByRole("button", {name: "Open Project 11111111"});
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  await user.upload(input!, new File(["bundle"], "private-name.lmdj"));

  expect((await screen.findByRole("alert")).textContent).toContain(code);
  expect(screen.queryByText("private-name.lmdj")).toBeNull();
  if (code === "HOST_RESTART_REQUIRED") {
    expect(screen.getByTestId("creator-phase").textContent).toBe("restart-required");
  }
});
