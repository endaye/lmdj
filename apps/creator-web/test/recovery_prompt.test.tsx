import {render, screen, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";

import {RecoveryPrompt, type RecoveryCounts} from "../src/components/recovery_prompt";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return {promise, resolve, reject};
}

function renderPrompt(counts: RecoveryCounts, overrides: Partial<{
  onKeep: () => Promise<RecoveryCounts>;
  onDiscard: () => Promise<RecoveryCounts>;
}> = {}) {
  const handlers = {
    onKeep: vi.fn(overrides.onKeep ?? (async () => ({sequence: 0, performance: 0}))),
    onDiscard: vi.fn(overrides.onDiscard ?? (async () => ({sequence: 0, performance: 0}))),
    onOpen: vi.fn(),
    onClose: vi.fn(),
  };
  render(<RecoveryPrompt counts={counts} {...handlers} />);
  return handlers;
}

const region = () => screen.getByRole("region", {name: "Interrupted recording"});

test("names one recording and where it was made", () => {
  renderPrompt({sequence: 1, performance: 0});
  expect(region().textContent).toContain("A recording stopped before it was saved (1 in Sequence)");
  expect(region().textContent).toContain("Keep it in this Project?");
});

test("names several recordings across Sequence and Perform", () => {
  renderPrompt({sequence: 2, performance: 1});
  expect(region().textContent)
    .toContain("3 recordings stopped before they were saved (2 in Sequence and 1 in Perform)");
});

test("is a region, not an alert, and takes no focus", () => {
  const before = document.activeElement;
  renderPrompt({sequence: 1, performance: 0});
  expect(screen.queryByRole("alert")).toBeNull();
  expect(document.activeElement).toBe(before);
});

test("Keep reports progress, then that the recording is back", async () => {
  const kept = deferred<RecoveryCounts>();
  const handlers = renderPrompt({sequence: 1, performance: 0}, {onKeep: () => kept.promise});
  await userEvent.click(screen.getByRole("button", {name: "Keep recording"}));
  expect(handlers.onKeep).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("status").textContent).toBe("Keeping…");
  expect(screen.getByText("Keeping")).toBeTruthy();
  expect(screen.queryByRole("button")).toBeNull();
  kept.resolve({sequence: 0, performance: 0});
  expect((await screen.findByText("The interrupted recording is back in this Project.")).getAttribute("role"))
    .toBe("status");
  expect(screen.getByText("Complete")).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Close"}));
  expect(handlers.onClose).toHaveBeenCalledTimes(1);
});

test("a recording that could not be kept names where to finish it", async () => {
  const handlers = renderPrompt({sequence: 1, performance: 1}, {
    onKeep: async () => ({sequence: 1, performance: 0}),
  });
  await userEvent.click(screen.getByRole("button", {name: "Keep recording"}));
  expect((await screen.findByRole("status")).textContent).toMatch(/could not be kept here\s+\(1 in Sequence\)/);
  expect(screen.queryByRole("button", {name: "Open Perform"})).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Open Sequence"}));
  expect(handlers.onOpen).toHaveBeenCalledWith("sequence");
});

test("a Keep that throws leaves every recording to finish elsewhere", async () => {
  renderPrompt({sequence: 1, performance: 1}, {onKeep: async () => { throw new Error("x"); }});
  await userEvent.click(screen.getByRole("button", {name: "Keep recording"}));
  await screen.findByRole("button", {name: "Open Sequence"});
  expect(screen.getByRole("button", {name: "Open Perform"})).toBeTruthy();
});

test("Discard asks for confirmation and Cancel discards nothing", async () => {
  const handlers = renderPrompt({sequence: 1, performance: 0});
  await userEvent.click(screen.getByRole("button", {name: "Discard…"}));
  expect(handlers.onDiscard).not.toHaveBeenCalled();
  expect(region().textContent).toContain("This cannot be undone.");
  await userEvent.click(screen.getByRole("button", {name: "Cancel"}));
  expect(screen.getByRole("button", {name: "Keep recording"})).toBeTruthy();
  expect(handlers.onDiscard).not.toHaveBeenCalled();
});

test("a confirmed Discard discards and says so", async () => {
  const handlers = renderPrompt({sequence: 1, performance: 0});
  await userEvent.click(screen.getByRole("button", {name: "Discard…"}));
  await userEvent.click(screen.getByRole("button", {name: "Discard recording"}));
  expect(handlers.onDiscard).toHaveBeenCalledTimes(1);
  expect((await screen.findByRole("status")).textContent).toBe("The interrupted recording was discarded.");
  expect(screen.getByText("Complete")).toBeTruthy();
});

test("both destinations open independently without keeping or discarding", async () => {
  const handlers = renderPrompt({sequence: 1, performance: 1});
  await userEvent.click(screen.getByRole("button", {name: "Open Sequence"}));
  await userEvent.click(screen.getByRole("button", {name: "Open Perform"}));
  expect(handlers.onOpen.mock.calls).toEqual([["sequence"], ["perform"]]);
  expect(handlers.onKeep).not.toHaveBeenCalled();
  expect(handlers.onDiscard).not.toHaveBeenCalled();
});

test("offers only Perform when only Perform holds a recording", async () => {
  const handlers = renderPrompt({sequence: 0, performance: 1});
  expect(screen.queryByRole("button", {name: "Open Sequence"})).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Open Perform"}));
  expect(handlers.onOpen).toHaveBeenCalledWith("perform");
});

test("Decide later closes without keeping or discarding", async () => {
  const handlers = renderPrompt({sequence: 1, performance: 0});
  await userEvent.click(screen.getByRole("button", {name: "Decide later"}));
  expect(handlers.onClose).toHaveBeenCalledTimes(1);
  expect(handlers.onKeep).not.toHaveBeenCalled();
  expect(handlers.onDiscard).not.toHaveBeenCalled();
});

test("offers no destination when nothing is waiting", () => {
  renderPrompt({sequence: 0, performance: 0});
  expect(screen.queryByRole("button", {name: /^Open /})).toBeNull();
});

test("discarding several recordings names how many in the button and the result", async () => {
  renderPrompt({sequence: 2, performance: 1});
  await userEvent.click(screen.getByRole("button", {name: "Discard…"}));
  await userEvent.click(screen.getByRole("button", {name: "Discard 3 recordings"}));
  expect(await screen.findByText("The 3 interrupted recordings were discarded.")).toBeTruthy();
});

test("keeping several recordings names how many came back", async () => {
  renderPrompt({sequence: 1, performance: 1});
  await userEvent.click(screen.getByRole("button", {name: "Keep recording"}));
  expect(await screen.findByText("The 2 interrupted recordings are back in this Project.")).toBeTruthy();
});

test("presents the recovery card and direct actions in the design order", () => {
  renderPrompt({sequence: 2, performance: 1});
  expect(within(region()).getByRole("heading", {name: "Recording recovery"})).toBeTruthy();
  expect(within(region()).getByText("Action needed")).toBeTruthy();
  expect(within(region()).getByRole("heading", {name: "3 unfinished recordings are here"})).toBeTruthy();
  expect(within(region()).getAllByRole("button").map(button => button.textContent)).toEqual([
    "Keep recording", "Open Sequence", "Open Perform", "Decide later", "Discard…",
  ]);
});

test("offers only Sequence when only Sequence holds a recording", () => {
  renderPrompt({sequence: 1, performance: 0});
  expect(screen.getByRole("button", {name: "Open Sequence"})).toBeTruthy();
  expect(screen.queryByRole("button", {name: "Open Perform"})).toBeNull();
});

test("Discard progress has no actions and partial completion uses remaining destinations", async () => {
  const discarded = deferred<RecoveryCounts>();
  const handlers = renderPrompt({sequence: 2, performance: 1}, {onDiscard: () => discarded.promise});
  await userEvent.click(screen.getByRole("button", {name: "Discard…"}));
  expect(screen.getByText("Confirm discard")).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Discard 3 recordings"}));
  expect(screen.getByRole("status").textContent).toBe("Discarding…");
  expect(screen.queryByRole("button")).toBeNull();
  expect(handlers.onDiscard).toHaveBeenCalledTimes(1);
  discarded.resolve({sequence: 0, performance: 1});
  await screen.findByRole("button", {name: "Open Perform"});
  expect(screen.getByRole("status").textContent).toMatch(/could not be discarded here\s+\(1 in Perform\)/);
  expect(screen.getByText("Action needed")).toBeTruthy();
  expect(screen.queryByRole("button", {name: "Open Sequence"})).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Open Perform"}));
  expect(handlers.onOpen).toHaveBeenCalledWith("perform");
  expect(handlers.onKeep).not.toHaveBeenCalled();
});

test("a Discard that throws retains both destinations instead of declaring completion", async () => {
  renderPrompt({sequence: 1, performance: 1}, {onDiscard: async () => { throw new Error("x"); }});
  await userEvent.click(screen.getByRole("button", {name: "Discard…"}));
  await userEvent.click(screen.getByRole("button", {name: "Discard 2 recordings"}));
  await screen.findByRole("button", {name: "Open Sequence"});
  expect(screen.getByRole("button", {name: "Open Perform"})).toBeTruthy();
  expect(screen.getByText("Action needed")).toBeTruthy();
  expect(screen.queryByText("Complete")).toBeNull();
});
