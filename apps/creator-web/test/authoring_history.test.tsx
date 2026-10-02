import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {DiagnosticsProvider} from "../src/runtime/diagnostics_context";
import userEvent from "@testing-library/user-event";
import {useState} from "react";
import {expect, test, vi} from "vitest";
import {useAuthoringHistory} from "../src/components/authoring_history";
import {PhysicalControls} from "../src/components/physical_controls";
import type {AuthoringHistoryRuntimeSession, AuthoringHistoryStatus} from "@lmdj/web-runtime-platform/runtime_types";
import type {CreatorRuntimeSession} from "../src/runtime/runtime_types";

const sessionId = "20000000-0000-4000-8000-000000000001";
const status: AuthoringHistoryStatus = {sessionId, projectRevision: 1, undoCount: 1, redoCount: 0,
  undoLabel: "Edit Pad", redoLabel: "", disabledReason: "", canUndo: true, canRedo: false};
const mutation = {committedRevision: 2, runtimeRevision: 2, runtimePublished: true, snapshotError: null};
function fixture(initial = status) {
  let current = initial;
  const history: AuthoringHistoryRuntimeSession = {
    inspectAuthoringHistory: vi.fn(async () => current),
    undoAuthoring: vi.fn(async () => {
      current = {...current, projectRevision: 2, undoCount: 0, redoCount: 1,
        undoLabel: "", redoLabel: "Edit Pad", canUndo: false, canRedo: true};
      return mutation;
    }),
    redoAuthoring: vi.fn(async () => {current = {...status, projectRevision: 3}; return {...mutation, committedRevision: 3, runtimeRevision: 3};}),
  };
  const props = {session: history as CreatorRuntimeSession & AuthoringHistoryRuntimeSession,
    projectId: "project", revision: 1, refreshKey: "sample", disabledReason: "",
    onChanged: vi.fn(async () => {}), onBusy: vi.fn()};
  return {history, props};
}

const UNDO_NAME = "Undo — SHIFT + ←";
const REDO_NAME = "Redo — SHIFT + →";
const SHIFT_NAME = "SHIFT — engage the Undo/Redo layer";

// The rail chord exactly as app.tsx wires it: SHIFT toggles, ← / → consume it.
function Harness(props: Parameters<typeof useAuthoringHistory>[0]) {
  const history = useAuthoringHistory(props);
  const [shifted, setShifted] = useState(false);
  return (
    <>
      <PhysicalControls
        activeMode="sample"
        activeBank={0}
        onSelectMode={() => setShifted(false)}
        onSelectBank={() => setShifted(false)}
        onRecord={() => setShifted(false)}
        recordEnabled
        onPlayStop={() => setShifted(false)}
        playEnabled
        history={{
          shifted,
          onToggleShift: () => setShifted((value) => !value),
          undoAvailable: history.undoAvailable,
          redoAvailable: history.redoAvailable,
          onUndo: () => { setShifted(false); history.undo(); },
          onRedo: () => { setShifted(false); history.redo(); },
          undoTitle: history.undoTitle,
          redoTitle: history.redoTitle,
        }}
      />
      <div role="status">{history.statusText}</div>
    </>
  );
}

const undoKey = () => screen.getByRole("button", {name: UNDO_NAME});
const redoKey = () => screen.getByRole("button", {name: REDO_NAME});
const shiftKey = () => screen.getByRole("button", {name: SHIFT_NAME});
const lit = (key: HTMLElement) => key.classList.contains("is-lit");

async function pressUndo() {
  await userEvent.click(shiftKey());
  await userEvent.click(undoKey());
}
async function pressRedo() {
  await userEvent.click(shiftKey());
  await userEvent.click(redoKey());
}

test("the lamp carries availability and the chord needs SHIFT first", async () => {
  const {props, history} = fixture();
  render(<Harness {...props} />);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  // The lamp says undo is possible; the key stays inert until SHIFT engages,
  // so a bare tap on the direction row never rewrites history.
  expect(undoKey()).toHaveProperty("disabled", true);
  await userEvent.click(undoKey());
  expect(history.undoAuthoring).not.toHaveBeenCalled();
  expect(shiftKey().getAttribute("aria-pressed")).toBe("false");
  await pressUndo();
  await waitFor(() => expect(history.undoAuthoring).toHaveBeenCalledTimes(1));
  // One chord, one action: SHIFT falls back off after the direction key.
  expect(shiftKey().getAttribute("aria-pressed")).toBe("false");
  await waitFor(() => expect(lit(redoKey())).toBe(true));
});

test("any other rail action consumes an engaged SHIFT", async () => {
  const {props} = fixture();
  render(<Harness {...props} />);
  await userEvent.click(shiftKey());
  expect(shiftKey().getAttribute("aria-pressed")).toBe("true");
  await userEvent.click(screen.getByRole("button", {name: "Record"}));
  expect(shiftKey().getAttribute("aria-pressed")).toBe("false");
  await userEvent.click(shiftKey());
  await userEvent.click(screen.getByRole("button", {name: "Play/Stop"}));
  expect(shiftKey().getAttribute("aria-pressed")).toBe("false");
});

test("one action undoes and redoes through the same session across modes", async () => {
  const {props, history} = fixture();
  const view = render(<Harness {...props} />);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  await pressUndo();
  await waitFor(() => expect(lit(redoKey())).toBe(true));
  expect(history.undoAuthoring).toHaveBeenCalledWith({sessionId, expectedRevision: 1, commandId: expect.any(String)});
  expect(props.onChanged).toHaveBeenCalledWith(mutation);
  expect(lit(undoKey())).toBe(false);
  view.rerender(<Harness {...props} revision={2} refreshKey="sequence" />);
  await waitFor(() => expect(lit(redoKey())).toBe(true));
  await pressRedo();
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  expect(history.redoAuthoring).toHaveBeenCalledWith({sessionId, expectedRevision: 2, commandId: expect.any(String)});
});

test("Cmd/Ctrl+Z and Cmd/Ctrl+Shift+Z drive the same history without the rail", async () => {
  const {props, history} = fixture();
  render(<Harness {...props} />);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  const undoEvent = new KeyboardEvent("keydown",
    {code: "KeyZ", key: "z", ctrlKey: true, bubbles: true, cancelable: true});
  fireEvent(window, undoEvent);
  expect(undoEvent.defaultPrevented).toBe(true);
  await waitFor(() => expect(history.undoAuthoring).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(lit(redoKey())).toBe(true));
  fireEvent.keyDown(window, {code: "KeyZ", key: "z", metaKey: true, shiftKey: true});
  await waitFor(() => expect(history.redoAuthoring).toHaveBeenCalledTimes(1));
});

test("the keyboard shortcut leaves the key alone when no history action can run", async () => {
  const {props, history} = fixture({...status, undoCount: 0, undoLabel: "", canUndo: false});
  render(<Harness {...props} />);
  await screen.findByText("No changes in this session");
  const event = new KeyboardEvent("keydown",
    {code: "KeyZ", key: "z", ctrlKey: true, bubbles: true, cancelable: true});
  fireEvent(window, event);
  expect(event.defaultPrevented).toBe(false);
  expect(history.undoAuthoring).not.toHaveBeenCalled();
});

test("the keyboard shortcut leaves native text undo inside editable fields", async () => {
  const {props, history} = fixture();
  render(<><Harness {...props} /><input aria-label="Project note" />
    <div aria-label="Rich note" ref={(el) => el?.setAttribute("contenteditable", "")} />
    <div aria-label="Plain note" contentEditable="plaintext-only" suppressContentEditableWarning /></>);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  for (const name of ["Project note", "Rich note", "Plain note"]) {
    fireEvent.keyDown(screen.getByLabelText(name), {code: "KeyZ", key: "z", ctrlKey: true});
  }
  expect(history.undoAuthoring).not.toHaveBeenCalled();
  // A widget that already handled the chord keeps precedence over history.
  const handled = new KeyboardEvent("keydown",
    {code: "KeyZ", key: "z", ctrlKey: true, bubbles: true, cancelable: true});
  handled.preventDefault();
  fireEvent(shiftKey(), handled);
  expect(history.undoAuthoring).not.toHaveBeenCalled();
});

test("a refused operation retains its command for an explicit retry and never retries itself", async () => {
  const {props, history} = fixture();
  vi.mocked(history.undoAuthoring).mockRejectedValueOnce(new Error("Writer busy"));
  render(<Harness {...props} />);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  await pressUndo();
  // #1680: the raw message stays in diagnostics; the user sees the catalogue.
  await screen.findByText("Something went wrong in Creator. Try again. Details are in Developer diagnostics.");
  expect(screen.queryByText(/Writer busy/)).toBeNull();
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  expect(history.undoAuthoring).toHaveBeenCalledTimes(1);
  expect(props.onChanged).not.toHaveBeenCalled();
  await pressUndo();
  await waitFor(() => expect(history.undoAuthoring).toHaveBeenCalledTimes(2));
  expect(vi.mocked(history.undoAuthoring).mock.calls[0]).toEqual(vi.mocked(history.undoAuthoring).mock.calls[1]);
});

test("recording and recovery show the Core reason without submitting history commands", async () => {
  for (const [reason, message] of [["sequence_session_active", "Finish Pattern recording to undo or redo."],
      ["sequence_recovery_pending", "Resolve the pending recording recovery first."]]) {
    const {props, history} = fixture({...status, disabledReason: reason!, canUndo: false});
    const view = render(<Harness {...props} />);
    await screen.findByText(message!);
    expect(lit(undoKey())).toBe(false);
    fireEvent.click(shiftKey());
    fireEvent.click(undoKey());
    expect(history.undoAuthoring).not.toHaveBeenCalled();
    view.unmount();
  }
});

test("a pending request admits no second action and waits for the refreshed projection", async () => {
  const {props, history} = fixture();
  let release!: () => void;
  props.onChanged.mockImplementation(() => new Promise<void>((resolve) => {release = resolve;}));
  render(<Harness {...props} />);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  fireEvent.click(shiftKey());
  fireEvent.click(undoKey());
  fireEvent.click(shiftKey());
  fireEvent.click(undoKey());
  await waitFor(() => expect(props.onChanged).toHaveBeenCalledTimes(1));
  expect(history.undoAuthoring).toHaveBeenCalledTimes(1);
  expect(lit(redoKey())).toBe(false);
  await act(async () => release());
  await waitFor(() => expect(lit(redoKey())).toBe(true));
  expect(props.onBusy.mock.calls).toEqual([[true], [false]]);
});

test("reopening shows an empty history and a committed sound publication failure stays visible", async () => {
  const {props, history} = fixture();
  vi.mocked(history.undoAuthoring).mockResolvedValue({...mutation, runtimePublished: false,
    runtimeRevision: 1, snapshotError: {code: "COOK_FAILED", message: "Audio unavailable", details: {}}});
  const view = render(<Harness {...props} />);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  await pressUndo();
  await screen.findByText("The change was saved, but the sound is not ready to play yet. Try preparing the audio again.");
  expect(screen.queryByText(/Audio unavailable/)).toBeNull();
  const reopened = fixture({...status, sessionId: "20000000-0000-4000-8000-000000000002", undoCount: 0, undoLabel: "", canUndo: false});
  view.rerender(<Harness {...reopened.props} />);
  await screen.findByText("No changes in this session");
  expect(lit(undoKey())).toBe(false);
  expect(lit(redoKey())).toBe(false);
});

test("lost acknowledgement replays the original command after the source stack becomes empty", async () => {
  const {props, history} = fixture();
  vi.mocked(history.undoAuthoring).mockImplementationOnce(async () => {
    vi.mocked(history.inspectAuthoringHistory).mockResolvedValue({...status,
      projectRevision: 2, undoCount: 0, redoCount: 1, undoLabel: "", redoLabel: "Edit Pad",
      canUndo: false, canRedo: true});
    throw new Error("Response lost");
  });
  const view = render(<Harness {...props} />);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  await pressUndo();
  await screen.findByText("Something went wrong in Creator. Try again. Details are in Developer diagnostics.");
  expect(screen.queryByText(/Response lost/)).toBeNull();
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  view.rerender(<Harness {...props} revision={2} refreshKey="sequence" />);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  await pressUndo();
  await waitFor(() => expect(props.onChanged).toHaveBeenCalledWith(mutation));
  expect(vi.mocked(history.undoAuthoring).mock.calls[1]).toEqual(vi.mocked(history.undoAuthoring).mock.calls[0]);
  expect(vi.mocked(history.undoAuthoring).mock.calls[1]![0].expectedRevision).toBe(1);
});

test("a definite revision refusal allows a new Undo at the observed revision", async () => {
  const {props, history} = fixture();
  vi.mocked(history.undoAuthoring).mockImplementationOnce(async () => {
    vi.mocked(history.inspectAuthoringHistory).mockResolvedValue({...status, projectRevision: 2});
    throw Object.assign(new Error("Project changed before Undo"), {code: "REVISION_CONFLICT"});
  });
  render(<Harness {...props} />);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  await pressUndo();
  await screen.findByText("The Project changed while this was in progress. Review the change, then try again.");
  expect(screen.queryByText(/Project changed before Undo/)).toBeNull();
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  expect(props.onChanged).not.toHaveBeenCalled();
  await pressUndo();
  await waitFor(() => expect(history.undoAuthoring).toHaveBeenCalledTimes(2));
  const [first, second] = vi.mocked(history.undoAuthoring).mock.calls;
  expect(second![0].expectedRevision).toBe(2);
  expect(second![0].commandId).not.toBe(first![0].commandId);
});

test("a failed Undo records its raw failure in Developer diagnostics (#1680)", async () => {
  const {props, history} = fixture();
  const raw = Object.assign(new Error("history journal locked"), {code: "HOST_STATE_INVALID"});
  vi.mocked(history.undoAuthoring).mockRejectedValueOnce(raw);
  const reportFailure = vi.fn(() => "HOST_STATE_INVALID");
  render(<DiagnosticsProvider value={reportFailure}><Harness {...props} /></DiagnosticsProvider>);
  await waitFor(() => expect(lit(undoKey())).toBe(true));
  await pressUndo();
  await screen.findByText(
    "That can't be done right now. Stop playback and finish any recording or import, then try again.");
  expect(screen.queryByText(/history journal locked/)).toBeNull();
  expect(reportFailure).toHaveBeenCalledWith("Undo", raw);
});
