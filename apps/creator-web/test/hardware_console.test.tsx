import {render, screen, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test} from "vitest";

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

test("names Figma 15 physical keys on the control panel", () => {
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
    "Record",
  ]) {
    expect(screen.getByRole("button", {name}).textContent).toBe(
      name.startsWith("Bank ") ? name.slice(-1) : name,
    );
  }
  expect(screen.getByRole("button", {
    name: "Play — Pattern Play requires global Pattern transport",
  }).textContent).toBe("Play");
  expect(screen.getByRole("group", {name: "Encoders"})).toBeTruthy();
  expect(screen.getAllByRole("button", {
    name: /Encoder \d — unassigned until hardware mapping is approved/,
  })).toHaveLength(4);
});
