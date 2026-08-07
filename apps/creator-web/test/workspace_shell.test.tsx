import {render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test} from "vitest";

import {App} from "../src/app";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";

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
