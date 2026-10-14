import {useState} from "react";
import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, expect, test, vi} from "vitest";

import {LongSourceEditor} from "../src/components/long_source_editor";
import {DecodedLongSource} from "../src/ingest/long_source_ingest";
import type {SampleQuota} from "../src/runtime/runtime_types";

function source(): DecodedLongSource {
  const samples = Float32Array.from({length: 100}, (_, index) => index / 100);
  return new DecodedLongSource("flac", "whole-song.flac", {
    length: samples.length,
    numberOfChannels: 1,
    sampleRate: 48_000,
    getChannelData: () => samples,
  });
}

const quota: Readonly<SampleQuota> = Object.freeze({
  projectRevision: 7,
  slot: 1,
  bankQuotaBytes: 400,
  bankUsedBytes: 240,
  bankRemainingBytes: 160,
  projectQuotaBytes: 800,
  projectUsedBytes: 240,
  projectRemainingBytes: 560,
  effectiveRemainingBytes: 160,
  effectiveRemainingFrames: 40,
  consumed: Object.freeze([
    Object.freeze({slot: 0, preparedBytes: 240, preparedFrames: 60}),
  ]),
});

test("bounds selection by effective quota and retains it after a failed commit", async () => {
  const decoded = source();
  const commit = vi.fn()
    .mockResolvedValueOnce({kind: "failed", message: "quota changed; choose a shorter range"})
    .mockResolvedValueOnce({kind: "committed"});
  render(
    <LongSourceEditor
      source={decoded}
      quota={quota}
      onCommit={commit}
      onCancel={() => {}}
    />,
  );

  expect(screen.getByText(/Bank A: 0.00 s remaining/)).toBeTruthy();
  expect(screen.getByText(/Pad usage: A01: 0.00 s/)).toBeTruthy();
  const length = screen.getByRole("slider", {name: "Long source selection length"});
  expect(length.getAttribute("max")).toBe("40");
  fireEvent.change(length, {target: {value: "25"}});
  fireEvent.click(screen.getByRole("button", {name: "Commit selection"}));

  expect((await screen.findByRole("alert")).textContent).toContain("quota changed");
  expect((length as HTMLInputElement).value).toBe("25");
  expect(commit).toHaveBeenLastCalledWith({startFrame: 0, frameCount: 25});

  fireEvent.click(screen.getByRole("button", {name: "Commit selection"}));
  await waitFor(() => expect(commit).toHaveBeenCalledTimes(2));
});


// Keep the real DecodedLongSource owner/range validation and observe its Web
// Audio boundary. jsdom supplies no audio engine: actual starts, natural ended,
// native focus and pointer geometry belong to the packaged Import journeys.
function observePreviewAudio() {
  const contexts: Array<{
    node: EventTarget & {buffer: AudioBuffer | null; connect: ReturnType<typeof vi.fn>;
      start: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn>};
    close: ReturnType<typeof vi.fn>;
  }> = [];
  class Context {
    state = "running";
    destination = {};
    close = vi.fn(async () => {});
    node = Object.assign(new EventTarget(), {
      buffer: null as AudioBuffer | null,
      connect: vi.fn(), start: vi.fn(), stop: vi.fn(), disconnect: vi.fn(),
    });
    constructor() { contexts.push(this); }
    createBufferSource() { return this.node; }
  }
  vi.stubGlobal("AudioContext", Context);
  return contexts;
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

test("names the captured target, bounds the source label and keeps both preview exits visible", () => {
  const longName = "<source>".repeat(40) + ".wav";
  const decoded = new DecodedLongSource("wav", longName, {
    length: 100, numberOfChannels: 1, sampleRate: 48_000,
    getChannelData: () => new Float32Array(100),
  });
  render(<LongSourceEditor source={decoded} quota={{...quota, slot: 18}}
    onCommit={vi.fn()} onCancel={vi.fn()} onDelete={vi.fn()} />);
  expect(screen.getByRole("heading", {name: "IMPORT AUDIO"})).toBeTruthy();
  expect(screen.getByText("TARGET B03")).toBeTruthy();
  expect(screen.getByText(`${Array.from(longName).slice(0, 95).join("")}…`)).toBeTruthy();
  expect(screen.getByText(/WAV · Mono/)).toBeTruthy();
  expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual([
    "Preview selection", "Stop preview", "Commit selection", "Cancel", "Delete Pad",
  ]);
  expect(screen.getByRole("button", {name: "Delete Pad B03"})).toBeTruthy();
  expect(document.activeElement).toBe(screen.getByRole("slider", {name: "Long source selection start"}));
});

test("Preview restarts the current exact selection and repeated Stop is harmless", async () => {
  const audio = observePreviewAudio();
  const commit = vi.fn();
  render(<LongSourceEditor source={source()} quota={quota} onCommit={commit} onCancel={vi.fn()} />);
  const preview = screen.getByRole("button", {name: "Preview selection"});
  const stop = screen.getByRole("button", {name: "Stop preview"});
  await act(async () => { fireEvent.click(preview); });
  expect(audio[0]!.node.start).toHaveBeenCalledWith(0, 0, 40 / 48_000);
  fireEvent.change(screen.getByRole("slider", {name: "Long source selection length"}), {target: {value: "10"}});
  fireEvent.change(screen.getByRole("slider", {name: "Long source selection start"}), {target: {value: "20"}});
  await act(async () => { fireEvent.click(preview); });
  expect(audio).toHaveLength(2);
  expect(audio[0]!.node.stop).toHaveBeenCalledTimes(1);
  expect(audio[0]!.node.disconnect).toHaveBeenCalledTimes(1);
  expect(audio[0]!.close).toHaveBeenCalledTimes(1);
  expect(audio[1]!.node.start).toHaveBeenCalledWith(0, 20 / 48_000, 10 / 48_000);
  fireEvent.click(stop);
  expect(audio[1]!.node.stop).toHaveBeenCalledTimes(1);
  expect(audio[1]!.close).toHaveBeenCalledTimes(1);
  fireEvent.click(stop);
  expect(audio[1]!.node.stop).toHaveBeenCalledTimes(1);
  expect(commit).not.toHaveBeenCalled();
});

test("natural preview completion can be followed by another Preview without a stale toggle", async () => {
  const audio = observePreviewAudio();
  render(<LongSourceEditor source={source()} quota={quota} onCommit={vi.fn()} onCancel={vi.fn()} />);
  const preview = screen.getByRole("button", {name: "Preview selection"});
  await act(async () => { fireEvent.click(preview); });
  await act(async () => { audio[0]!.node.dispatchEvent(new Event("ended")); });
  expect(audio[0]!.close).toHaveBeenCalledTimes(1);
  await act(async () => { fireEvent.click(preview); });
  expect(audio).toHaveLength(2);
  expect(audio[1]!.node.start).toHaveBeenCalledWith(0, 0, 40 / 48_000);
  expect(audio[0]!.node.stop).not.toHaveBeenCalled();
  expect(screen.queryByText(/Playing/)).toBeNull();
});

test("preview failure retains the selection and a real subsequent start clears its error", async () => {
  const decoded = source();
  vi.stubGlobal("AudioContext", class { constructor() { throw new Error("Audio preview unavailable"); } });
  render(<LongSourceEditor source={decoded} quota={quota} onCommit={vi.fn()} onCancel={vi.fn()} />);
  const length = screen.getByRole("slider", {name: "Long source selection length"});
  fireEvent.change(length, {target: {value: "19"}});
  await act(async () => { fireEvent.click(screen.getByRole("button", {name: "Preview selection"})); });
  expect(screen.getByRole("alert").textContent).toBe("Audio preview unavailable");
  expect((length as HTMLInputElement).value).toBe("19");
  const audio = observePreviewAudio();
  await act(async () => { fireEvent.click(screen.getByRole("button", {name: "Preview selection"})); });
  expect(audio[0]!.node.start).toHaveBeenCalledWith(0, 0, 19 / 48_000);
  expect(screen.queryByRole("alert")).toBeNull();
});

test("no room preserves quota details and Cancel/Delete without an invalid selection action", () => {
  render(<LongSourceEditor source={source()} quota={{...quota, effectiveRemainingFrames: 0,
    effectiveRemainingBytes: 0}} onCommit={vi.fn()} onCancel={vi.fn()} onDelete={vi.fn()} />);
  expect(screen.getByRole("alert").textContent).toContain("room");
  expect(screen.queryAllByRole("slider")).toHaveLength(0);
  expect((screen.getByRole("button", {name: "Preview selection"}) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", {name: "Commit selection"}) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", {name: "Cancel"}) as HTMLButtonElement).disabled).toBe(false);
  expect((screen.getByRole("button", {name: "Delete Pad A02"}) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.getByText(/Pad usage: A01/)).toBeTruthy();
});

test("committing stops preview and keeps the existing Delete and Escape cancellation boundaries", async () => {
  const audio = observePreviewAudio();
  let finish!: (value: {kind: "failed"; message: string}) => void;
  const commit = vi.fn(() => new Promise<{kind: "failed"; message: string}>((resolve) => { finish = resolve; }));
  const cancel = vi.fn(); const remove = vi.fn();
  render(<LongSourceEditor source={source()} quota={quota} onCommit={commit} onCancel={cancel} onDelete={remove} />);
  await act(async () => { fireEvent.click(screen.getByRole("button", {name: "Preview selection"})); });
  fireEvent.click(screen.getByRole("button", {name: "Commit selection"}));
  expect(audio[0]!.node.stop).toHaveBeenCalledTimes(1);
  expect(commit).toHaveBeenCalledWith({startFrame: 0, frameCount: 40});
  for (const control of [...screen.getAllByRole("slider"), ...["Preview selection", "Stop preview", "Committing…", "Cancel"].map((name) => screen.getByRole("button", {name}))]) {
    expect((control as HTMLInputElement).disabled).toBe(true);
  }
  fireEvent.click(screen.getByRole("button", {name: "Delete Pad A02"}));
  expect(remove).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(screen.getByRole("dialog"), {key: "Escape"});
  expect(cancel).toHaveBeenCalledTimes(1);
  await act(async () => { finish({kind: "failed", message: "Commit failed"}); });
  expect(screen.getByRole("alert").textContent).toBe("Commit failed");
  expect((screen.getByRole("button", {name: "Commit selection"}) as HTMLButtonElement).disabled).toBe(false);
});

test("revision conflict keeps exact selection available for retry", async () => {
  const commit = vi.fn().mockResolvedValueOnce({kind: "conflict", message: "Project revision changed"})
    .mockResolvedValueOnce({kind: "committed"});
  render(<LongSourceEditor source={source()} quota={quota} onCommit={commit} onCancel={vi.fn()} />);
  const start = screen.getByRole("slider", {name: "Long source selection start"});
  const length = screen.getByRole("slider", {name: "Long source selection length"});
  fireEvent.change(length, {target: {value: "15"}});
  fireEvent.change(start, {target: {value: "21"}});
  await act(async () => { fireEvent.click(screen.getByRole("button", {name: "Commit selection"})); });
  expect(screen.getByRole("alert").textContent).toBe("Project revision changed");
  expect((start as HTMLInputElement).value).toBe("21");
  expect((length as HTMLInputElement).value).toBe("15");
  await act(async () => { fireEvent.click(screen.getByRole("button", {name: "Commit selection"})); });
  expect(commit.mock.calls).toEqual([[{startFrame: 21, frameCount: 15}], [{startFrame: 21, frameCount: 15}]]);
});

test("Cancel unmounts the preview owner, restores focus and releases the background", async () => {
  const audio = observePreviewAudio();
  function Fixture() {
    const [open, setOpen] = useState(false);
    const [opener, setOpener] = useState<HTMLElement | null>(null);
    return <section><button onClick={(event) => { setOpener(event.currentTarget); setOpen(true); }}>Import fixture</button>
      {open ? <LongSourceEditor source={decoded} quota={quota} onCommit={vi.fn()}
        returnFocus={opener} onCancel={() => setOpen(false)} /> : null}</section>;
  }
  const decoded = source();
  render(<Fixture />);
  const opener = screen.getByRole("button", {name: "Import fixture"});
  fireEvent.click(opener);
  expect(opener.hasAttribute("inert")).toBe(true);
  await act(async () => { fireEvent.click(screen.getByRole("button", {name: "Preview selection"})); });
  fireEvent.click(screen.getByRole("button", {name: "Cancel"}));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(audio[0]!.node.stop).toHaveBeenCalledTimes(1);
  expect(audio[0]!.close).toHaveBeenCalledTimes(1);
  expect(opener.hasAttribute("inert")).toBe(false);
  expect(document.activeElement).toBe(opener);
});

test("a selection starting inside a waveform bin highlights that bin", () => {
  // 100 frames over 192 bins: bin 1 covers frames [0.52, 1.04), so frame 1
  // starts inside it. Bin 0 lies wholly before the selection.
  render(<LongSourceEditor source={source()} quota={quota} onCommit={vi.fn()} onCancel={vi.fn()} />);
  fireEvent.change(screen.getByRole("slider", {name: "Long source selection start"}), {target: {value: "1"}});
  const bins = document.querySelectorAll(".long-source-waveform rect");
  expect(bins[0]?.getAttribute("data-selected")).toBe("false");
  expect(bins[1]?.getAttribute("data-selected")).toBe("true");
});

test("Import opts into the existing touch anchor without replacing its native dialog", () => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    x: 300, y: 200, left: 300, top: 200, width: 368, height: 368,
    right: 668, bottom: 568, toJSON: () => ({}),
  });
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(368);
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(368);
  render(<section data-testid="touch-workspace"><LongSourceEditor source={source()} quota={quota}
    onCommit={vi.fn()} onCancel={vi.fn()} /></section>);
  const dialog = screen.getByRole("dialog");
  expect(dialog.style.left).toBe("300px");
  expect(dialog.style.top).toBe("200px");
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  const start = screen.getByRole("slider", {name: "Long source selection start"});
  const cancel = screen.getByRole("button", {name: "Cancel"});
  start.focus(); fireEvent.keyDown(start, {key: "Tab", shiftKey: true});
  expect(document.activeElement).toBe(cancel);
  fireEvent.keyDown(cancel, {key: "Tab"});
  expect(document.activeElement).toBe(start);
});
