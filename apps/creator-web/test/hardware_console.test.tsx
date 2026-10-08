import {readFileSync} from "node:fs";

import {render, screen, within} from "@testing-library/react";
import {fireEvent} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";

import {HardwareConsole, fitConsoleToStage} from "../src/components/hardware_console";
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
  // The −/+ placeholder row is gone; SHIFT holds its row as one full-width key.
  expect(screen.queryByRole("button", {name: /^Decrease/})).toBeNull();
  expect(screen.queryByRole("button", {name: /^Increase/})).toBeNull();
  expect(screen.getByRole("button", {name: "SHIFT — history layer unavailable"})
    .classList.contains("is-shift")).toBe(true);
  expect(screen.getByRole("group", {name: "Encoders"})).toBeTruthy();
  expect(screen.getAllByRole("button", {
    name: /Encoder \d — unassigned until hardware mapping is approved/,
  })).toHaveLength(4);
});

test("the rail SHIFT chord gates Undo/Redo behind the modifier with lamp availability", () => {
  const onUndo = vi.fn();
  const onRedo = vi.fn();
  const onToggleShift = vi.fn();
  const history = {
    shifted: false,
    onToggleShift,
    undoAvailable: true,
    redoAvailable: false,
    onUndo,
    onRedo,
    undoTitle: "Undo Edit Pad",
    redoTitle: "Nothing to redo",
  };
  const view = render(<PhysicalControls
    activeMode="sample"
    activeBank={0}
    onSelectMode={() => {}}
    onSelectBank={() => {}}
    history={history}
  />);
  const shift = screen.getByRole("button", {name: "SHIFT — engage the Undo/Redo layer"});
  const undo = screen.getByRole("button", {name: "Undo — SHIFT + ←"});
  const redo = screen.getByRole("button", {name: "Redo — SHIFT + →"});
  // Lamps report availability even before the modifier engages; both
  // direction keys stay inert until SHIFT is held.
  expect(undo.classList.contains("is-lit")).toBe(true);
  expect(redo.classList.contains("is-lit")).toBe(false);
  expect(shift.getAttribute("aria-pressed")).toBe("false");
  expect(undo).toHaveProperty("disabled", true);
  expect(redo).toHaveProperty("disabled", true);
  fireEvent.click(shift);
  expect(onToggleShift).toHaveBeenCalledTimes(1);

  view.rerender(<PhysicalControls
    activeMode="sample"
    activeBank={0}
    onSelectMode={() => {}}
    onSelectBank={() => {}}
    history={{...history, shifted: true}}
  />);
  expect(shift.getAttribute("aria-pressed")).toBe("true");
  expect(undo).toHaveProperty("disabled", false);
  // Redo is not available, so its chord stays inert even while shifted.
  expect(redo).toHaveProperty("disabled", true);
  fireEvent.click(undo);
  expect(onUndo).toHaveBeenCalledTimes(1);
  fireEvent.click(redo);
  expect(onRedo).not.toHaveBeenCalled();
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

// jsdom leaves var() unsubstituted in computed values while a browser
// substitutes it; resolve one level so an assertion reads the token's value.
function resolved(style: CSSStyleDeclaration, property: string): string {
  const value = style.getPropertyValue(property);
  const reference = /^var\((--[\w-]+)\)$/.exec(value);
  return reference === null ? value : style.getPropertyValue(reference[1]!);
}

test("console body takes the Desktop Final mono stack and surfaces", () => {
  const style = document.createElement("style");
  style.textContent = readFileSync("src/styles.css", "utf8");
  document.head.append(style);
  try {
    render(<HardwareConsole
      physicalControls={<span>keys</span>}
      overview={<output>Ready</output>}
      pads={<span>pads</span>}
      touchWorkspace={<span>touch</span>}
    />);
    const shell = getComputedStyle(screen.getByTestId("hardware-console"));
    const display = getComputedStyle(screen.getByRole("region", {name: "Overview display"}));
    expect(resolved(shell, "font-family")).toMatch(/^"IBM Plex Mono",/);
    expect(resolved(shell, "background")).toBe("#202321");
    expect(resolved(display, "background")).toBe("#292d29");
  } finally {
    style.remove();
  }
});

function railWith(props: Partial<Parameters<typeof PhysicalControls>[0]> = {}) {
  return render(<PhysicalControls activeMode="sequence" activeBank={0}
    onSelectMode={() => {}} onSelectBank={() => {}} {...props} />);
}

test("an unbound encoder stays unavailable and a bound one turns by key, wheel and drag", () => {
  const onTurn = vi.fn();
  railWith({encoders: {3: {label: "Tempo", onTurn}}});
  expect(screen.getByRole("button", {name: /^Encoder 1 — unassigned/}).hasAttribute("disabled"))
    .toBe(true);
  const tempo = screen.getByRole("button", {name: "Encoder 3 — Tempo"});
  fireEvent.keyDown(tempo, {key: "ArrowUp"});
  fireEvent.keyDown(tempo, {key: "ArrowLeft"});
  fireEvent.wheel(tempo, {deltaY: -60});
  fireEvent.wheel(tempo, {deltaY: 60});
  expect(onTurn.mock.calls.map(([detents]) => detents)).toEqual([1, -1, 1, -1]);
  onTurn.mockClear();
  // A trackpad burst of small deltas accumulates: twenty 5 px events are
  // 100 px, two detents, not twenty.
  for (let index = 0; index < 20; index += 1) fireEvent.wheel(tempo, {deltaY: -5});
  expect(onTurn.mock.calls.map(([detents]) => detents)).toEqual([1, 1]);
  onTurn.mockClear();
  // Sixteen pixels up is two clockwise detents; the remainder carries over.
  fireEvent.pointerDown(tempo, {pointerId: 7, clientY: 100});
  fireEvent.pointerMove(tempo, {pointerId: 7, clientY: 84});
  fireEvent.pointerMove(tempo, {pointerId: 7, clientY: 80});
  fireEvent.pointerMove(tempo, {pointerId: 7, clientY: 76});
  fireEvent.pointerUp(tempo, {pointerId: 7});
  expect(onTurn.mock.calls.map(([detents]) => detents)).toEqual([2, 1]);
});

test("a disabled encoder binding ignores turns", () => {
  const onTurn = vi.fn();
  railWith({encoders: {4: {label: "Swing", disabled: true, onTurn}}});
  const swing = screen.getByRole("button", {name: "Encoder 4 — Swing"});
  expect(swing.hasAttribute("disabled")).toBe(true);
  fireEvent.keyDown(swing, {key: "ArrowUp"});
  expect(onTurn).not.toHaveBeenCalled();
});

test("without SHIFT the arrows take the page's step; with SHIFT they are Undo / Redo", () => {
  const onBack = vi.fn();
  const onForward = vi.fn();
  const history = {
    shifted: false, onToggleShift: () => {}, undoAvailable: true, redoAvailable: false,
    onUndo: vi.fn(), onRedo: vi.fn(), undoTitle: "Undo", redoTitle: "Redo",
  };
  const directionStep = {
    backLabel: "Pattern back — ←", forwardLabel: "Pattern forward — →",
    backAvailable: false, forwardAvailable: true, onBack, onForward,
  };
  const view = railWith({history, directionStep});
  expect(screen.getByRole("button", {name: "Pattern back — ←"}).hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", {name: "Pattern forward — →"}));
  expect(onForward).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("button", {name: "Undo — SHIFT + ←"})).toBeNull();
  view.rerender(<PhysicalControls activeMode="sequence" activeBank={0}
    onSelectMode={() => {}} onSelectBank={() => {}}
    history={{...history, shifted: true}} directionStep={directionStep} />);
  fireEvent.click(screen.getByRole("button", {name: "Undo — SHIFT + ←"}));
  expect(history.onUndo).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("button", {name: "Pattern forward — →"})).toBeNull();
  expect(onBack).not.toHaveBeenCalled();
});

test("the console scales proportionally to fit the stage and centres itself", () => {
  const console = {width: 880, height: 640};
  // A tall stage is limited by width, a wide one by height; both centre.
  expect(fitConsoleToStage({width: 1440, height: 1280}, console, false))
    .toEqual({scale: 1440 / 880, dx: 0, dy: (1280 - 640 * 1440 / 880) / 2, rotate: false});
  expect(fitConsoleToStage({width: 1440, height: 800}, console, false))
    .toEqual({scale: 1.25, dx: (1440 - 1100) / 2, dy: 0, rotate: false});
  // A short window shrinks the console instead of scrolling it.
  expect(fitConsoleToStage({width: 768, height: 512}, console, false))
    .toEqual({scale: 0.8, dx: (768 - 704) / 2, dy: 0, rotate: false});
});

test("a narrow portrait stage turns the console and never enlarges it", () => {
  const console = {width: 880, height: 640};
  expect(fitConsoleToStage({width: 390, height: 700}, console, true))
    .toEqual({scale: 390 / 640, dx: 0, dy: (700 + 880 * 390 / 640) / 2, rotate: true});
  expect(fitConsoleToStage({width: 900, height: 2000}, console, true)?.scale).toBe(1);
});

test("an unmeasured stage or console is not fitted", () => {
  expect(fitConsoleToStage({width: 0, height: 600}, {width: 880, height: 640}, false)).toBeNull();
  expect(fitConsoleToStage({width: 800, height: 600}, {width: 0, height: 0}, false)).toBeNull();
});
