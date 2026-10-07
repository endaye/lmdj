import {useState} from "react";

import {fireEvent, render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";

import {App} from "../src/app";
import {ErrorPanel} from "../src/components/error_panel";
import {ProjectSurface, formatBytes} from "../src/components/project_surface";
import {midiLabel} from "../src/components/midi_status";
import type {CreatorBuildIdentity} from "../src/runtime/build_identity";
import type {ProjectView} from "../src/runtime/runtime_types";
import {
  creatorReducer,
  initialCreatorState,
  isCreatorActionAllowed,
  type CreatorState,
} from "../src/state/creator_state";
import {initialSequenceState} from "../src/state/sequence_state";
import {initialPatternTransportState} from "../src/state/pattern_transport_state";

const BUILD: CreatorBuildIdentity = {
  productBuild: "9.8.7.6",
  hostId: "creator-web",
  hostVersion: "1.5.0",
  platformVersion: "0.3.6",
  protocolVersion: 1,
};

const project: ProjectView = {
  projectId: "0123456789abcdef",
  patternId: "pattern-1",
  revision: 7,
  bpm: 96,
  assetCount: 3,
  assignedPadCount: 5,
  bundleDigest: "digest",
  key: "—",
  pads: [],
  patterns: [
    {patternId: "pattern-1", bars: 1, events: []},
    {patternId: "pattern-2", bars: 4, events: []},
  ],
  patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
  sequenceSettings: {quantizeEnabled: false, swingPercent: 62},
};

const ready: CreatorState = {
  ...initialCreatorState,
  project: {phase: "ready", projects: [], current: project},
  runtime: {phase: "ready", errorCode: null, errorDetails: {}},
};

test("MIDI label covers every permission state", () => {
  expect(midiLabel(null)).toBe("—");
  expect(midiLabel({permission: "prompt", connectedInputCount: 0})).toBe("off");
  expect(midiLabel({permission: "requesting", connectedInputCount: 0})).toBe("requesting");
  expect(midiLabel({permission: "denied", connectedInputCount: 0})).toBe("denied");
  expect(midiLabel({permission: "granted", connectedInputCount: 1})).toBe("1 input");
});

test("App threads the build identity into the shell", () => {
  render(<App initialState={ready} buildIdentity={BUILD} />);
  expect(screen.getByTestId("build-identity").textContent)
    .toBe("v9.8.7.6 · creator-web 1.5.0");
});

test("Project summary lists Pattern and Sequence settings and drops the stale stage note", () => {
  render(<ProjectSurface state={ready} />);
  expect(screen.getByText("Patterns").nextElementSibling?.textContent).toBe("2");
  expect(screen.getByText("Quantize").nextElementSibling?.textContent).toBe("Off");
  expect(screen.getByText("Swing").nextElementSibling?.textContent).toBe("62%");
  expect(screen.queryByText(/Stages 8–10/)).toBeNull();
  expect(screen.getByText("Perform mode arrives in Stage 10.")).toBeTruthy();
});

test("Project surface shows import progress while a transfer is running", () => {
  const importing: CreatorState = {
    ...ready,
    transfer: {phase: "importing", completedBytes: 512 * 1024, totalBytes: 2 * 1024 * 1024},
  };
  render(<ProjectSurface state={importing} />);
  expect(screen.getByRole("status").textContent).toBe("Importing… 512.0 KiB of 2.0 MiB");
  const progress = screen.getByRole("progressbar") as HTMLProgressElement;
  expect(progress.max).toBe(2 * 1024 * 1024);
  expect(progress.value).toBe(512 * 1024);
});

test("formatBytes renders human units", () => {
  expect(formatBytes(0)).toBe("0 B");
  expect(formatBytes(900)).toBe("900 B");
  expect(formatBytes(1536)).toBe("1.5 KiB");
  expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MiB");
  expect(formatBytes(-1)).toBe("0 B");
});

test("D01 Project cards keep Open, offer New Project and omit Save", () => {
  const onOpen = vi.fn();
  const withList: CreatorState = {
    ...ready,
    project: {
      ...ready.project,
      projects: [{
        projectId: project.projectId,
        patternId: project.patternId,
        revision: 7,
        bpm: 96,
        assetCount: 3,
        assignedPadCount: 5,
        bundleDigest: "digest",
      }],
    },
  };
  render(<ProjectSurface state={withList} canOpen hideSummary onOpen={onOpen} />);
  expect(screen.getByText("01 LOCAL")).toBeTruthy();
  expect(screen.getByText("01", {selector: ".project-card-index"})).toBeTruthy();
  fireEvent.click(screen.getByRole("button", {name: "Open Project 01234567"}));
  expect(onOpen).toHaveBeenCalledWith(withList.project.projects[0]);
  expect(screen.queryByRole("button", {name: /^SAVE$/i})).toBeNull();
  expect(screen.getByRole("button", {name: "New Project"})).toBeTruthy();
  expect(screen.queryByRole("button", {name: /SAVE AS/i})).toBeNull();
});

function listed(projectId: string, revision: number) {
  return {projectId, patternId: project.patternId, revision, bpm: 96, assetCount: 1,
    assignedPadCount: 1, bundleDigest: "digest"};
}

test("a selected Project that leaves the list is not selected when it returns", () => {
  const other = "f".repeat(32);
  const withList = (projects: CreatorState["project"]["projects"]): CreatorState => ({
    ...ready, project: {...ready.project, projects}});
  const current = listed(project.projectId, 7);
  const both = [current, listed(other, 1)];
  const {rerender} = render(<ProjectSurface state={withList(both)} canOpen hideSummary />);
  fireEvent.click(screen.getByRole("button", {name: "Select Project ffffffff"}));
  expect(screen.getByRole("button", {name: "Open Project ffffffff"})).toBeTruthy();
  rerender(<ProjectSurface state={withList([current])} canOpen hideSummary />);
  rerender(<ProjectSurface state={withList(both)} canOpen hideSummary />);
  expect(screen.getByRole("button", {name: "Open Project 01234567"})).toBeTruthy();
});

test("the summary view draws no OPEN PROJECT row", () => {
  const withList: CreatorState = {
    ...ready, project: {...ready.project, projects: [listed(project.projectId, 7)]}};
  render(<ProjectSurface state={withList} canOpen />);
  expect(screen.getByText("Project ID")).toBeTruthy();
  expect(screen.queryByRole("button", {name: /^Open Project/})).toBeNull();
});

test("the local Project chooser can return to the open Project", async () => {
  const user = userEvent.setup();
  const withList: CreatorState = {
    ...ready,
    project: {
      ...ready.project,
      projects: [{
        projectId: project.projectId,
        patternId: project.patternId,
        revision: 7,
        bpm: 96,
        assetCount: 3,
        assignedPadCount: 5,
        bundleDigest: "digest",
      }],
    },
  };
  function Chooser() {
    const [showLocal, setShowLocal] = useState(false);
    return (
      <ProjectSurface state={withList} canOpen showLocalProjects={showLocal}
        onShowLocal={() => setShowLocal(true)} onHideLocal={() => setShowLocal(false)} />
    );
  }
  render(<Chooser />);
  expect(screen.queryByRole("button", {name: "Back to Project"})).toBeNull();
  await user.click(screen.getByRole("button", {name: "Open local"}));
  expect(screen.getByRole("heading", {level: 1}).textContent).toBe("Local Projects");
  expect(screen.getByText("Open now")).toBeTruthy();
  expect(screen.getByRole("listitem").getAttribute("aria-current")).toBe("true");
  await user.click(screen.getByRole("button", {name: "Back to Project"}));
  expect(screen.getByRole("heading", {level: 1}).textContent).toBe("Project 01234567");
});

test("an advisory error can be dismissed but a Runtime fault cannot", async () => {
  const user = userEvent.setup();
  const advisory: CreatorState = {
    ...ready,
    project: {...ready.project, phase: "error"},
    runtime: {phase: "ready", errorCode: "INVALID_PROJECT", errorDetails: {}},
  };
  render(<App initialState={advisory} />);
  expect(screen.getByRole("alert")).toBeTruthy();
  await user.click(screen.getByRole("button", {name: "Dismiss"}));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByTestId("creator-phase").textContent).toBe("ready");

  const fatal: CreatorState = {
    ...ready,
    runtime: {phase: "restart-required", errorCode: "HOST_RESTART_REQUIRED", errorDetails: {}},
  };
  expect(isCreatorActionAllowed(fatal, {type: "runtime-error-dismissed"})).toBe(false);
  expect(creatorReducer(fatal, {type: "runtime-error-dismissed"})).toBe(fatal);
  expect(isCreatorActionAllowed(ready, {type: "runtime-error-dismissed"})).toBe(false);
});

test("dismissing an error with no open Project returns the inventory to empty", () => {
  const errored: CreatorState = {
    ...initialCreatorState,
    project: {phase: "error", projects: [], current: null},
    runtime: {phase: "ready", errorCode: "INVALID_PROJECT", errorDetails: {}},
  };
  const next = creatorReducer(errored, {type: "runtime-error-dismissed"});
  expect(next.project.phase).toBe("empty");
  expect(next.runtime.errorCode).toBeNull();
});

test("error panel renders Dismiss only when a handler is offered", () => {
  const {rerender} = render(<ErrorPanel code="INVALID_PROJECT" />);
  expect(screen.queryByRole("button", {name: "Dismiss"})).toBeNull();
  rerender(<ErrorPanel code="INVALID_PROJECT" onDismiss={() => {}} />);
  expect(screen.getByRole("button", {name: "Dismiss"})).toBeTruthy();
});

test("an unreadable local copy is not reported as an invalid bundle", () => {
  render(<ErrorPanel code="LOCAL_PROJECT_UNREADABLE" />);
  const message = screen.getByRole("alert").textContent ?? "";
  expect(message).toContain("local copy");
  expect(message).not.toContain("Bundle is invalid");
});

test("D01: a card tap only selects; OPEN PROJECT opens the selection", () => {
  const onOpen = vi.fn();
  const summary = (projectId: string) => ({
    projectId, patternId: project.patternId, revision: 7, bpm: 96,
    assetCount: 3, assignedPadCount: 5, bundleDigest: "digest",
  });
  const withTwo: CreatorState = {
    ...ready,
    project: {...ready.project, projects: [summary(project.projectId), summary("89abcdef00000000")]},
  };
  render(<ProjectSurface state={withTwo} canOpen hideSummary onOpen={onOpen} />);
  // The open Project is selected by default.
  expect(screen.getByRole("button", {name: "Select Project 01234567"}).getAttribute("aria-pressed"))
    .toBe("true");
  fireEvent.click(screen.getByRole("button", {name: "Select Project 89abcdef"}));
  expect(onOpen).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", {name: "Open Project 01234567"})).toBeNull();
  fireEvent.click(screen.getByRole("button", {name: "Open Project 89abcdef"}));
  expect(onOpen).toHaveBeenCalledWith(withTwo.project.projects[1]);
});
