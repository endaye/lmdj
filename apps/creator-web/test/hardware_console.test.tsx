import {render, screen, within} from "@testing-library/react";
import {fireEvent} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";

import {HardwareConsole} from "../src/components/hardware_console";
import {PhysicalControls} from "../src/components/physical_controls";

test("overview contains no action while touch workspace remains actionable", () => {
  render(<HardwareConsole
    physicalControls={<button type="button">Play</button>}
    overview={<output>Stopped</output>}
    pads={<button type="button">Pad A01</button>}
    touchWorkspace={<button type="button">Activate audio</button>}
  />);
  const display = screen.getByRole("region", {name: "Overview display"});
  expect(within(display).queryAllByRole("button")).toHaveLength(0);
  expect(within(screen.getByRole("region", {name: "Touch workspace"}))
    .getByRole("button", {name: "Activate audio"})).toBeDefined();
});

test("names the four hardware regions for the console shell", () => {
  render(<HardwareConsole
    physicalControls={<span>keys</span>}
    overview={<output>Ready</output>}
    pads={<span>pads</span>}
    touchWorkspace={<span>touch</span>}
  />);
  expect(screen.getByTestId("hardware-console")).toBeTruthy();
  expect(screen.getByRole("complementary", {name: "Physical controls"})).toBeTruthy();
  expect(screen.getByRole("region", {name: "Overview display"})).toBeTruthy();
  expect(screen.getByRole("region", {name: "Pad matrix"})).toBeTruthy();
  expect(screen.getByRole("region", {name: "Touch workspace"})).toBeTruthy();
});

test("names D01–D04 physical keys by accessible name and exported icons", () => {
  render(<PhysicalControls
    activeMode="project"
    activeBank={0}
    sequenceEnabled
    performEnabled
    onSelectMode={() => {}}
    onSelectBank={() => {}}
    onRecord={() => {}}
    recordEnabled
  />);
  for (const name of [
    "Project", "Sample", "Sequence", "Perform",
    "Bank A", "Bank B", "Bank C", "Bank D",
  ]) {
    const key = screen.getByRole("button", {name});
    if (name.startsWith("Bank ")) {
      expect(key.textContent).toBe(name.slice(-1));
    } else {
      expect(key.querySelector("svg")).toBeTruthy();
      expect(key.textContent).toBe("");
    }
  }
  expect(screen.getByRole("button", {name: "Record"}).querySelector("svg")).toBeTruthy();
  expect(screen.getByRole("button", {
    name: "Play/Stop — needs a playable Project and running audio",
  }).querySelector("svg")).toBeTruthy();
  expect(screen.getByRole("group", {name: "Encoders"})).toBeTruthy();
  expect(screen.getAllByRole("button", {
    name: /Encoder \d — unassigned until hardware mapping is approved/,
  })).toHaveLength(4);
});

test("physical icons are inline SVG so the img-src 'self' CSP cannot blank them", () => {
  // The packaged Host ships under `img-src 'self'`; an `<img>` fed a Vite
  // `data:` URL renders as a broken image there, which is how the D01–D04
  // icons vanished on device without a journey noticing.
  const {container} = render(<PhysicalControls
    activeMode="sequence"
    activeBank={0}
    sequenceEnabled
    performEnabled
    onSelectMode={() => {}}
    onSelectBank={() => {}}
    onRecord={() => {}}
    recordEnabled
    onPlayStop={() => {}}
    playEnabled
  />);
  expect(container.querySelectorAll("img")).toHaveLength(0);
  expect(container.querySelectorAll("[src]")).toHaveLength(0);
  const svgs = container.querySelectorAll("svg");
  // Brand mark, four encoders, four mode keys, Record, Play/Stop.
  expect(svgs).toHaveLength(11);
  for (const svg of svgs) {
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.querySelector("path")).toBeTruthy();
  }
});

test("physical Play/Stop and Record drive the global Pattern transport", () => {
  const onRecord = vi.fn();
  const onPlayStop = vi.fn();
  render(<PhysicalControls
    activeMode="sequence"
    activeBank={0}
    sequenceEnabled
    performEnabled
    onSelectMode={() => {}}
    onSelectBank={() => {}}
    onRecord={onRecord}
    recordEnabled
    recording
    onPlayStop={onPlayStop}
    playEnabled
    playing
  />);
  // Record stays enabled while recording: the same key is Record-off, never a
  // Sample capture or master recording control.
  fireEvent.click(screen.getByRole("button", {
    name: "Record — stop recording Pad events into the current Pattern",
  }));
  expect(onRecord).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", {
    name: "Play/Stop — Pattern is playing",
  }));
  expect(onPlayStop).toHaveBeenCalledTimes(1);
});
