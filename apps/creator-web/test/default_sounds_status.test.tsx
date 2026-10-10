import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {expect, test, vi} from "vitest";
import {DefaultSoundsStatus} from "../src/components/default_sounds_status";
import type {DefaultSeed, SeedPhase} from "../src/state/default_seed";

const seed = (...phases: SeedPhase[]): DefaultSeed => ({
  projectId: "project", setId: "set", version: "1.0.0", manifestSha256: "a".repeat(64),
  slots: phases.map(phase => ({phase, request: null, committedRevision: null})),
});
const actions = () => ({onRetry: vi.fn(), onPrepare: vi.fn(async () => {}), onDetails: vi.fn()});

test("mixed default-sound outcomes have one summary and keep recovery actions reachable", () => {
  const callbacks = actions();
  const view = render(<DefaultSoundsStatus seed={seed("ready", "loading", "failed", "saved-unavailable")}
    error={null} {...callbacks} />);
  expect(screen.getByRole("status").textContent)
    .toBe("Default sounds · 1 ready · 1 loading · 1 unavailable · 1 saved · playback pending");
  fireEvent.click(screen.getByRole("button", {name: "Retry default sounds"}));
  expect(callbacks.onRetry).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", {name: "System details"}));
  expect(callbacks.onDetails).toHaveBeenCalledTimes(1);
  view.rerender(<DefaultSoundsStatus seed={seed("ready", "ready", "ready", "retired")}
    error={null} {...callbacks} />);
  expect(screen.queryByRole("region", {name: "Default sounds"})).toBeNull();
  expect(screen.getByRole("status").textContent).toBe("Default sounds · 3 ready");
  expect(screen.queryByRole("button", {name: "Retry default sounds"})).toBeNull();
});

test("failed playback preparation settles its busy state and permits a successful retry", async () => {
  const callbacks = actions();
  let reject!: (reason: Error) => void;
  callbacks.onPrepare.mockImplementationOnce(() => new Promise<void>((_, fail) => {reject = fail;}));
  const view = render(<DefaultSoundsStatus seed={seed("saved-unavailable")}
    error={null} {...callbacks} />);
  fireEvent.click(screen.getByRole("button", {name: "Prepare default sounds"}));
  expect((screen.getByRole("button", {name: "Preparing playback…"}) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => reject(new Error("publication failed")));
  expect(screen.getByText(/Playback is still unavailable/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", {name: "Prepare default sounds"}));
  await waitFor(() => expect(callbacks.onPrepare).toHaveBeenCalledTimes(2));
  view.rerender(<DefaultSoundsStatus seed={seed("ready")} error={null} {...callbacks} />);
  expect(screen.getByRole("status").textContent).toBe("Default sounds · 1 ready");
  expect(screen.queryByText(/Playback is still unavailable/)).toBeNull();
});

test("an unreadable seed journal offers diagnostics without inventing retryable slots", () => {
  render(<DefaultSoundsStatus seed={null} error="Default sounds unavailable; existing content is preserved" {...actions()} />);
  expect(screen.getByRole("status").textContent).toContain("existing content is preserved");
  expect(screen.getAllByRole("button").map(button => button.textContent)).toEqual(["System details"]);
});


test("a recovered publication does not reuse a previous preparation failure", async () => {
  const callbacks = actions();
  callbacks.onPrepare.mockRejectedValueOnce(new Error("publication failed"));
  const view = render(<DefaultSoundsStatus seed={seed("saved-unavailable")} error={null} {...callbacks} />);
  fireEvent.click(screen.getByRole("button", {name: "Prepare default sounds"}));
  await screen.findByText(/Playback is still unavailable/);
  view.rerender(<DefaultSoundsStatus seed={seed("ready")} error={null} {...callbacks} />);
  view.rerender(<DefaultSoundsStatus seed={seed("saved-unavailable")} error={null} {...callbacks} />);
  expect(screen.queryByText(/Playback is still unavailable/)).toBeNull();
  expect((screen.getByRole("button", {name: "Prepare default sounds"}) as HTMLButtonElement).disabled).toBe(false);
});

test("a late failure from before publication cannot poison a new preparation", async () => {
  const callbacks = actions();
  let reject!: (reason: Error) => void;
  callbacks.onPrepare.mockImplementationOnce(() => new Promise<void>((_, fail) => {reject = fail;}));
  const view = render(<DefaultSoundsStatus seed={seed("saved-unavailable")} error={null} {...callbacks} />);
  fireEvent.click(screen.getByRole("button", {name: "Prepare default sounds"}));
  view.rerender(<DefaultSoundsStatus seed={seed("ready")} error={null} {...callbacks} />);
  view.rerender(<DefaultSoundsStatus seed={seed("saved-unavailable")} error={null} {...callbacks} />);
  let resolve!: () => void;
  callbacks.onPrepare.mockImplementationOnce(() => new Promise<void>(done => {resolve = done;}));
  fireEvent.click(screen.getByRole("button", {name: "Prepare default sounds"}));
  await act(async () => reject(new Error("old attempt failed")));
  expect(screen.queryByText(/Playback is still unavailable/)).toBeNull();
  expect((screen.getByRole("button", {name: "Preparing playback…"}) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => resolve());
  expect((screen.getByRole("button", {name: "Prepare default sounds"}) as HTMLButtonElement).disabled).toBe(false);
});
