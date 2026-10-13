import {useRef, useState} from "react";
import {act, fireEvent, render, screen} from "@testing-library/react";
import {afterEach, expect, test, vi} from "vitest";
import {ModalDialog} from "../src/components/modal_dialog";

const originalShowModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "close");
afterEach(() => {
  vi.restoreAllMocks();
  for (const [name, descriptor] of [["showModal", originalShowModal], ["close", originalClose]] as const) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name);
  }
});

function anchorRect({left = 496, top = 208, width = 368, height = 368} = {}) {
  return {x: left, y: top, left, top, width, height,
    right: left + width, bottom: top + height, toJSON() { return {}; }};
}

function mountAtTouchArea(placement: "touch-workspace" | "center" = "touch-workspace") {
  let rect = anchorRect();
  const read = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return this.getAttribute("data-testid") === "touch-workspace" ? rect : anchorRect({width: 0, height: 0});
  });
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(368);
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(368);
  const view = render(<div className="hardware-workspace"><section data-testid="touch-workspace">
    <ModalDialog {...(placement === "center" ? {} : {placement})} label="Placement fixture" returnFocus={null}
      onCancel={() => {}} dialogClassName="fixture-dialog">
      <button type="button">First</button><button type="button">Last</button>
    </ModalDialog>
  </section></div>);
  const dialog = screen.getByRole("dialog") as HTMLDialogElement;
  return {...view, dialog, read, setRect(value: typeof rect) { rect = value; }};
}

test("default placement retains centered consumer styles without observing an anchor", () => {
  const {dialog, read} = mountAtTouchArea("center");
  expect(dialog.style.left).toBe("");
  expect(dialog.style.transform).toBe("");
  expect(read).not.toHaveBeenCalled();
});

test("touch placement follows actual viewport geometry without remounting or taking focus", () => {
  const {dialog, setRect} = mountAtTouchArea();
  expect(dialog.style.left).toBe("496px");
  expect(dialog.style.top).toBe("208px");
  expect(dialog.style.width).toBe("368px");
  expect(dialog.style.height).toBe("368px");
  const last = screen.getByRole("button", {name: "Last"});
  last.focus();
  setRect(anchorRect({left: 360, top: 184}));
  fireEvent(window, new Event("resize"));
  expect(screen.getByRole("dialog")).toBe(dialog);
  expect(dialog.style.left).toBe("360px");
  expect(dialog.style.top).toBe("184px");
  expect(document.activeElement).toBe(last);
});

test("a rotated console still gets an upright modal and targets never scale below one", () => {
  const {dialog, setRect} = mountAtTouchArea();
  setRect(anchorRect({left: 200, top: 250, width: 340, height: 340}));
  fireEvent(window, new Event("scroll"));
  expect(dialog.style.transform).toBe("scale(1)");
  expect(dialog.style.left).toBe("200px");
  expect(dialog.style.top).toBe("250px");
});

test("touch placement reproduces a larger scale and clamps the whole panel inside viewport margins", () => {
  const {dialog, setRect} = mountAtTouchArea();
  setRect(anchorRect({left: 496, top: 208, width: 460, height: 460}));
  fireEvent(window, new Event("resize"));
  expect(dialog.style.transform).toBe("scale(1.25)");
  setRect(anchorRect({left: 950, top: 700, width: 460, height: 460}));
  fireEvent(window, new Event("scroll"));
  expect(Number.parseFloat(dialog.style.left) + 460).toBe(window.innerWidth - 8);
  expect(Number.parseFloat(dialog.style.top) + 460).toBe(window.innerHeight - 8);
});

test("a stage transform update repositions the existing dialog even without a natural resize", async () => {
  const {container, dialog, setRect} = mountAtTouchArea();
  setRect(anchorRect({left: 160, top: 240}));
  await act(async () => {
    container.querySelector<HTMLElement>(".hardware-workspace")!.style.transform = "rotate(-90deg)";
  });
  expect(dialog.style.left).toBe("160px");
  expect(dialog.style.top).toBe("240px");
  expect(dialog.style.transform).toBe("scale(1)");
});

test("touch placement follows ResizeObserver then releases its observer on unmount", () => {
  let changed: ResizeObserverCallback | undefined;
  const disconnect = vi.fn();
  vi.stubGlobal("ResizeObserver", class {
    observe = vi.fn();
    disconnect = disconnect;
    constructor(callback: ResizeObserverCallback) { changed = callback; }
  });
  try {
    const {dialog, setRect, unmount} = mountAtTouchArea();
    setRect(anchorRect({left: 88, top: 160}));
    act(() => changed?.([], {} as ResizeObserver));
    expect(dialog.style.left).toBe("88px");
    expect(dialog.style.top).toBe("160px");
    unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  } finally {
    vi.unstubAllGlobals();
  }
});

test("missing touch anchor retains the existing centered dialog", () => {
  render(<ModalDialog placement="touch-workspace" label="No anchor"
    returnFocus={null} onCancel={() => {}} dialogClassName="fixture-dialog">
    <button type="button">Close</button>
  </ModalDialog>);
  expect((screen.getByRole("dialog") as HTMLElement).style.left).toBe("");
});

test("placement preserves native ownership, background lock, Tab trap, Escape and return focus", () => {
  const showModal = vi.fn(function (this: HTMLDialogElement) { this.open = true; });
  const close = vi.fn(function (this: HTMLDialogElement) { this.open = false; });
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {configurable: true, value: showModal});
  Object.defineProperty(HTMLDialogElement.prototype, "close", {configurable: true, value: close});
  function Harness() {
    const [open, setOpen] = useState(false);
    const trigger = useRef<HTMLButtonElement>(null);
    return <section data-testid="touch-workspace">
      <button ref={trigger} type="button" onClick={() => setOpen(true)}>Open</button>
      {open && <ModalDialog placement="touch-workspace" label="Native fixture"
        returnFocus={trigger.current} onCancel={() => setOpen(false)} dialogClassName="fixture-dialog">
        <button type="button">First</button><button type="button">Last</button>
      </ModalDialog>}
    </section>;
  }
  const {container} = render(<Harness />);
  const trigger = screen.getByRole("button", {name: "Open"});
  fireEvent.click(trigger);
  expect(showModal).toHaveBeenCalledOnce();
  expect(trigger.hasAttribute("inert")).toBe(true);
  const dialog = screen.getByRole("dialog");
  const first = screen.getByRole("button", {name: "First"});
  const last = screen.getByRole("button", {name: "Last"});
  last.focus();
  fireEvent.keyDown(dialog, {key: "Tab"});
  expect(document.activeElement).toBe(first);
  fireEvent.keyDown(dialog, {key: "Tab", shiftKey: true});
  expect(document.activeElement).toBe(last);
  fireEvent.pointerDown(container.querySelector(".sample-modal-backdrop")!);
  expect(screen.getByRole("dialog")).toBe(dialog);
  fireEvent.keyDown(dialog, {key: "Escape"});
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(trigger.hasAttribute("inert")).toBe(false);
  expect(document.activeElement).toBe(trigger);
});
