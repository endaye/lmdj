import {useState} from "react";

import {fireEvent, render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test} from "vitest";

import {App} from "../src/app";
import {ErrorPanel} from "../src/components/error_panel";
import {ModeRail} from "../src/components/mode_rail";
import {ProjectSurface, formatBytes} from "../src/components/project_surface";
import {SequenceSurface} from "../src/components/sequence_surface";
import {SequenceTransport} from "../src/components/sequence_transport";
import {StatusBar, midiLabel} from "../src/components/status_bar";
import type {CreatorBuildIdentity} from "../src/runtime/build_identity";
import type {ProjectView} from "../src/runtime/runtime_types";
import {
  creatorReducer,
  initialCreatorState,
  isCreatorActionAllowed,
  type CreatorState,
} from "../src/state/creator_state";
import {initialSequenceState} from "../src/state/sequence_state";

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
    {patternId: "pattern-1", bars: 1},
    {patternId: "pattern-2", bars: 4},
  ],
  patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
  sequenceSettings: {quantizeEnabled: false, swingPercent: 62},
};

const ready: CreatorState = {
  ...initialCreatorState,
  project: {phase: "ready", projects: [], current: project},
  runtime: {phase: "ready", errorCode: null, errorDetails: {}},
};

test("status bar shows the build identity, the Project revision and the MIDI state", () => {
  render(
    <StatusBar
      state={ready}
      buildIdentity={BUILD}
      midi={{permission: "granted", connectedInputCount: 2}}
    />,
  );
  const identity = screen.getByTestId("build-identity");
  expect(identity.textContent).toBe("v9.8.7.6 · creator-web 1.5.0");
  expect(identity.getAttribute("title")).toBe(
    "Product Build 9.8.7.6 · creator-web 1.5.0 · web-runtime-platform 0.3.6 · protocol 1",
  );
  expect(screen.getByText("Rev").nextElementSibling?.textContent).toBe("7");
  expect(screen.getByTestId("midi-state").textContent).toBe("2 inputs");
  expect(screen.getByRole("button", {name: "Enable MIDI"}).hasAttribute("disabled"))
    .toBe(true);
});

test("status bar omits the build identity when none is supplied", () => {
  render(<StatusBar state={ready} />);
  expect(screen.queryByTestId("build-identity")).toBeNull();
  expect(screen.getByTestId("midi-state").textContent).toBe("—");
});

test("MIDI label covers every permission state", () => {
  expect(midiLabel(null)).toBe("—");
  expect(midiLabel({permission: "prompt", connectedInputCount: 0})).toBe("off");
  expect(midiLabel({permission: "requesting", connectedInputCount: 0})).toBe("requesting");
  expect(midiLabel({permission: "denied", connectedInputCount: 0})).toBe("denied");
  expect(midiLabel({permission: "granted", connectedInputCount: 1})).toBe("1 input");
});

test("App threads the build identity into the status bar", () => {
  render(<App initialState={ready} buildIdentity={BUILD} />);
  expect(screen.getByTestId("build-identity").textContent)
    .toBe("v9.8.7.6 · creator-web 1.5.0");
});

test("mode rail glyphs never reuse Pad keyboard letters", () => {
  render(<ModeRail activeMode="project" onSelect={() => {}} />);
  const glyphs = Array.from(
    document.querySelectorAll(".mode-glyph"),
    (glyph) => glyph.textContent ?? "",
  );
  expect(glyphs).toHaveLength(5);
  for (const glyph of glyphs) expect(glyph).not.toMatch(/^[A-Za-z]$/);
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

test("sequence transport explains why Record is unavailable", () => {
  const {rerender} = render(
    <SequenceTransport state={initialSequenceState} ready={false}
      onRecord={() => {}} onStop={() => {}} onRefresh={() => {}} />,
  );
  expect(screen.getByText("Activate audio to record")).toBeTruthy();
  rerender(
    <SequenceTransport state={initialSequenceState} ready
      onRecord={() => {}} onStop={() => {}} onRefresh={() => {}} />,
  );
  expect(screen.queryByText("Activate audio to record")).toBeNull();
});

test("sequence settings follow committed Project values and pluralise bars", () => {
  const noop = () => {};
  const props = {
    state: initialSequenceState,
    ready: true,
    onRecord: noop, onStop: noop, onRefresh: noop, onSwitch: noop,
    onCreatePattern: noop, onSettingsChange: noop, onRecover: noop, onDiscard: noop,
  };
  const {rerender} = render(<SequenceSurface project={project} {...props} />);
  expect(screen.getByText("Project revision 7 · 2 Patterns")).toBeTruthy();
  expect(screen.getByRole("option", {name: "pattern- · 1 bar"})).toBeTruthy();
  expect(screen.getByRole("option", {name: "pattern- · 4 bars"})).toBeTruthy();
  const bpm = screen.getByLabelText("BPM") as HTMLInputElement;
  expect(bpm.value).toBe("96");
  fireEvent.change(bpm, {target: {value: "120"}});
  expect(bpm.value).toBe("120");
  rerender(<SequenceSurface project={{...project, revision: 8, bpm: 104}} {...props} />);
  expect(bpm.value).toBe("104");
});
