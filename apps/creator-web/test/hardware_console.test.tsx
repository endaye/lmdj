import {render, screen, within} from "@testing-library/react";
import {expect, test} from "vitest";

import {HardwareConsole} from "../src/components/hardware_console";

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
