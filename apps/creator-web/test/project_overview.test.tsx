import {render, screen, within} from "@testing-library/react";
import {expect, test} from "vitest";
import {ProjectOverview} from "../src/components/project_overview";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";

const state: CreatorState = {...initialCreatorState,
  project: {...initialCreatorState.project, phase: "ready", current: {
    projectId: "11111111-1111-4111-8111-111111111111",
    patternId: "22222222-2222-4222-8222-222222222222",
    revision: 123, bpm: 120, assetCount: 1, assignedPadCount: 64,
    bundleDigest: "a".repeat(64), key: "—", pads: [], patterns: [],
    patternSlots: Array<string | null>(16).fill(null),
    sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
  }},
};

test("a Runtime error replaces its status row without adding raw error text to the overview", () => {
  render(<ProjectOverview state={{...state,
    runtime: {...state.runtime, phase: "restart-required", errorCode: "INTERNAL_ERROR",
      errorDetails: {message: "Unbounded provider text ".repeat(100)}},
  }} />);
  const overview = screen.getByTestId("project-overview");
  const workspace = overview.querySelector('dl[aria-label="Workspace"]')!;
  expect(workspace.querySelectorAll("dd")).toHaveLength(3);
  expect(workspace.querySelector("[data-error-code]")?.textContent).toBe("Needs attention");
  expect(overview.textContent).not.toContain("Unbounded provider text");
  expect(overview.querySelector("button,input,select,a")).toBeNull();
});


test("a saved Sample with audio still pending remains a qualified storage status", () => {
  render(<ProjectOverview state={{...state, sample: {...state.sample,
    savedRevision: 124, runtimeRevision: 123}}} />);
  const overview = screen.getByTestId("project-overview");
  expect(within(overview).getByText("SAMPLE SAVED · AUDIO PENDING")).toBeDefined();
  expect(overview.textContent).not.toContain("123");
});

test("no open Project displays an explicit empty identity and state", () => {
  render(<ProjectOverview state={initialCreatorState} />);
  const overview = screen.getByTestId("project-overview");
  expect(overview.querySelector('dl[aria-label="Project"]')?.textContent)
    .toBe("PROJECTnone—NO PROJECT OPEN");
});
