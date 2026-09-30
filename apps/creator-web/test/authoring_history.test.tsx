import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";
import {AuthoringHistoryControls} from "../src/components/authoring_history";
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

test("one action undoes and redoes through the same session across modes", async () => {
  const {props, history} = fixture();
  const view = render(<AuthoringHistoryControls {...props} />);
  await waitFor(() => expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", false));
  await userEvent.click(screen.getByRole("button", {name: "Undo"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Redo"})).toHaveProperty("disabled", false));
  expect(history.undoAuthoring).toHaveBeenCalledWith({sessionId, expectedRevision: 1, commandId: expect.any(String)});
  expect(props.onChanged).toHaveBeenCalledWith(mutation);
  expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", true);
  view.rerender(<AuthoringHistoryControls {...props} revision={2} refreshKey="sequence" />);
  await waitFor(() => expect(screen.getByRole("button", {name: "Redo"})).toHaveProperty("disabled", false));
  await userEvent.click(screen.getByRole("button", {name: "Redo"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", false));
  expect(history.redoAuthoring).toHaveBeenCalledWith({sessionId, expectedRevision: 2, commandId: expect.any(String)});
});

test("a refused operation retains its command for an explicit retry and never retries itself", async () => {
  const {props, history} = fixture();
  vi.mocked(history.undoAuthoring).mockRejectedValueOnce(new Error("Writer busy"));
  render(<AuthoringHistoryControls {...props} />);
  await waitFor(() => expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", false));
  await userEvent.click(screen.getByRole("button", {name: "Undo"}));
  await screen.findByText("Writer busy");
  await waitFor(() => expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", false));
  expect(history.undoAuthoring).toHaveBeenCalledTimes(1);
  expect(props.onChanged).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name: "Undo"}));
  await waitFor(() => expect(history.undoAuthoring).toHaveBeenCalledTimes(2));
  expect(vi.mocked(history.undoAuthoring).mock.calls[0]).toEqual(vi.mocked(history.undoAuthoring).mock.calls[1]);
});

test("recording and recovery show the Core reason without submitting history commands", async () => {
  for (const [reason, message] of [["sequence_session_active", "Finish Pattern recording to undo or redo."],
      ["sequence_recovery_pending", "Resolve the pending recording recovery first."]]) {
    const {props, history} = fixture({...status, disabledReason: reason!, canUndo: false});
    const view = render(<AuthoringHistoryControls {...props} />);
    await screen.findByText(message!);
    expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", {name: "Undo"}));
    expect(history.undoAuthoring).not.toHaveBeenCalled();
    view.unmount();
  }
});

test("a pending request admits no second action and waits for the refreshed projection", async () => {
  const {props, history} = fixture();
  let release!: () => void;
  props.onChanged.mockImplementation(() => new Promise<void>((resolve) => {release = resolve;}));
  render(<AuthoringHistoryControls {...props} />);
  await waitFor(() => expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", false));
  fireEvent.click(screen.getByRole("button", {name: "Undo"}));
  fireEvent.click(screen.getByRole("button", {name: "Undo"}));
  await waitFor(() => expect(props.onChanged).toHaveBeenCalledTimes(1));
  expect(history.undoAuthoring).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", {name: "Redo"})).toHaveProperty("disabled", true);
  await act(async () => release());
  await waitFor(() => expect(screen.getByRole("button", {name: "Redo"})).toHaveProperty("disabled", false));
  expect(props.onBusy.mock.calls).toEqual([[true], [false]]);
});

test("reopening shows an empty history and a committed sound publication failure stays visible", async () => {
  const {props, history} = fixture();
  vi.mocked(history.undoAuthoring).mockResolvedValue({...mutation, runtimePublished: false,
    runtimeRevision: 1, snapshotError: {code: "COOK_FAILED", message: "Audio unavailable", details: {}}});
  const view = render(<AuthoringHistoryControls {...props} />);
  await waitFor(() => expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", false));
  await userEvent.click(screen.getByRole("button", {name: "Undo"}));
  await screen.findByText("Change saved; sound update failed: Audio unavailable");
  const reopened = fixture({...status, sessionId: "20000000-0000-4000-8000-000000000002", undoCount: 0, undoLabel: "", canUndo: false});
  view.rerender(<AuthoringHistoryControls {...reopened.props} />);
  await screen.findByText("No changes in this session");
  expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", true);
  expect(screen.getByRole("button", {name: "Redo"})).toHaveProperty("disabled", true);
});

test("lost acknowledgement replays the original command after the source stack becomes empty", async () => {
  const {props, history} = fixture();
  vi.mocked(history.undoAuthoring).mockImplementationOnce(async () => {
    vi.mocked(history.inspectAuthoringHistory).mockResolvedValue({...status,
      projectRevision: 2, undoCount: 0, redoCount: 1, undoLabel: "", redoLabel: "Edit Pad",
      canUndo: false, canRedo: true});
    throw new Error("Response lost");
  });
  const view = render(<AuthoringHistoryControls {...props} />);
  await waitFor(() => expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", false));
  await userEvent.click(screen.getByRole("button", {name: "Undo"}));
  await screen.findByText("Response lost");
  await waitFor(() => expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", false));
  view.rerender(<AuthoringHistoryControls {...props} revision={2} refreshKey="sequence" />);
  await waitFor(() => expect(screen.getByRole("button", {name: "Undo"})).toHaveProperty("disabled", false));
  await userEvent.click(screen.getByRole("button", {name: "Undo"}));
  await waitFor(() => expect(props.onChanged).toHaveBeenCalledWith(mutation));
  expect(vi.mocked(history.undoAuthoring).mock.calls[1]).toEqual(vi.mocked(history.undoAuthoring).mock.calls[0]);
  expect(vi.mocked(history.undoAuthoring).mock.calls[1]![0].expectedRevision).toBe(1);
});
