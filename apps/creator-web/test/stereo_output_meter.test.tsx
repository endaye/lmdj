import {act, render, screen} from "@testing-library/react";
import {afterEach, expect, test, vi} from "vitest";
import type {StereoOutputMeter as Measurement} from "@lmdj/web-runtime-platform/runtime_types";
import {StereoOutputMeter} from "../src/components/stereo_output_meter";

const owner = "11111111-1111-4111-8111-111111111111";
const measured = (change: Partial<Extract<Measurement, {state: "available"}>> = {}):
  Extract<Measurement, {state: "available"}> => ({
  state: "available", owner, sampleRate: 48_000, renderQuantumFrames: 128,
  windowStartFrame: "48000", windowEndFrame: "50400", leftPeakFrame: "48000",
  rightPeakFrame: "49000", leftPeak: 0.5, rightPeak: 0.25, contextTimeSeconds: 1.05, ...change,
});
const readout = () => screen.getByLabelText("Stereo output readout");
afterEach(() => vi.restoreAllMocks());
function frames() {
  const pending = new Map<number, FrameRequestCallback>();
  let next = 0;
  const request = vi.spyOn(window, "requestAnimationFrame").mockImplementation(callback => {
    pending.set(++next, callback); return next;
  });
  const cancel = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(id => {pending.delete(id);});
  return {pending, request, cancel, advance() {
    const entry = pending.entries().next().value;
    if (entry === undefined) throw new Error("No live meter frame");
    pending.delete(entry[0]); act(() => entry[1](999_999));
  }};
}

test("read-only rails and text expose independent actual L/R measurements", () => {
  frames();
  const outputMeter = vi.fn(() => measured());
  render(<StereoOutputMeter source={{outputMeter}} projectId="project-a" running />);
  expect(readout().textContent).toBe("L −6.0  R −12.0 dBFS");
  expect(screen.getByRole("meter", {name: "Left output level"}).getAttribute("aria-valuenow"))
    .toBe("-6.020599913279624");
  expect(screen.getByRole("meter", {name: "Right output level"}).getAttribute("aria-valuetext"))
    .toBe("−12.0 dBFS; peak −12.0 dBFS");
  expect(screen.getByRole("group").getAttribute("data-owner")).toBe(owner);
  expect(readout().closest("[role='group']")?.querySelector("button,input,select,[tabindex]")).toBeNull();
});

test("actual zero is a silent empty rail, not an unavailable or0dBFS reading", () => {
  frames();
  const outputMeter = () => measured({leftPeak: 0, rightPeak: 0});
  render(<StereoOutputMeter source={{outputMeter}} projectId="project-a" running />);
  expect(readout().textContent).toBe("L −∞  R −∞ dBFS");
  expect(screen.getByRole("group").getAttribute("data-state")).toBe("available");
  expect(readout().closest("[role='group']")?.querySelectorAll(".perform-output-meter-hold")).toHaveLength(0);
});

test("unavailable removes all numeric meter claims and held markers", () => {
  const clock = frames(); let value: Measurement = measured();
  render(<StereoOutputMeter source={{outputMeter: () => value}} projectId="project-a" running />);
  value = {state: "unavailable", reason: "stale"}; clock.advance();
  expect(readout().textContent).toBe("UNAVAILABLE");
  expect(screen.queryAllByRole("meter")).toHaveLength(0);
  expect(screen.getByRole("group").getAttribute("data-owner")).toBeNull();
  expect(screen.getByRole("group").querySelector(".perform-output-meter-hold")).toBeNull();
});

test("rendered hold expires using real measured frame age, not the RAF timestamp", () => {
  const clock = frames(); let value = measured();
  render(<StereoOutputMeter source={{outputMeter: () => value}} projectId="project-a" running />);
  value = measured({windowStartFrame: "93600", windowEndFrame: "96000", leftPeakFrame: "95000",
    rightPeakFrame: "95000", leftPeak: 0.1, rightPeak: 0.01, contextTimeSeconds: 95_999 / 48_000});
  clock.advance();
  expect(screen.getByRole("meter", {name: "Left output level"}).getAttribute("data-held-peak")).toBe("0.5");
  value = {...value, contextTimeSeconds: 2}; clock.advance();
  expect(screen.getByRole("meter", {name: "Left output level"}).getAttribute("data-held-peak")).toBe("0.1");
});

test("a replacement Session first renders unavailable and cannot inherit a held peak", () => {
  frames();
  const view = render(<StereoOutputMeter source={{outputMeter: () => measured()}} projectId="project-a" running />);
  const replacement = {outputMeter: vi.fn(() => {
    expect(readout().textContent).toBe("UNAVAILABLE");
    return measured({leftPeak: 0.01});
  })};
  view.rerender(<StereoOutputMeter source={replacement} projectId="project-a" running />);
  expect(screen.getByRole("meter", {name: "Left output level"}).getAttribute("data-held-peak")).toBe("0.01");
});

test("Project replacement resets hold even when the Session and meter owner stay the same", () => {
  frames(); let value = measured();
  const source = {outputMeter: () => value};
  const view = render(<StereoOutputMeter source={source} projectId="project-a" running />);
  value = measured({leftPeak: 0.01});
  view.rerender(<StereoOutputMeter source={source} projectId="project-b" running />);
  expect(screen.getByRole("meter", {name: "Left output level"}).getAttribute("data-held-peak")).toBe("0.01");
});

test("suspend cancels the reader, and same-Session recovery cannot borrow the old hold", () => {
  const clock = frames(); let value = measured();
  const source = {outputMeter: vi.fn(() => value)};
  const view = render(<StereoOutputMeter source={source} projectId="project-a" running />);
  view.rerender(<StereoOutputMeter source={source} projectId="project-a" running={false} />);
  expect(readout().textContent).toBe("UNAVAILABLE");
  expect(clock.pending.size).toBe(0);
  value = measured({leftPeak: 0.01});
  view.rerender(<StereoOutputMeter source={source} projectId="project-a" running />);
  expect(screen.getByRole("meter", {name: "Left output level"}).getAttribute("data-held-peak")).toBe("0.01");
});

test("a queued frame after unmount neither reads nor reschedules", () => {
  const clock = frames(); const outputMeter = vi.fn(() => measured());
  const view = render(<StereoOutputMeter source={{outputMeter}} projectId="project-a" running />);
  const queued = [...clock.pending.values()][0]!;
  const reads = outputMeter.mock.calls.length, requests = clock.request.mock.calls.length;
  view.unmount(); act(() => queued(123));
  expect(clock.cancel).toHaveBeenCalled();
  expect(outputMeter).toHaveBeenCalledTimes(reads);
  expect(clock.request).toHaveBeenCalledTimes(requests);
});

test("a getter exception shows unavailable and loses its old hold", () => {
  const clock = frames(); const outputMeter = vi.fn<() => Measurement>().mockReturnValue(measured());
  render(<StereoOutputMeter source={{outputMeter}} projectId="project-a" running />);
  outputMeter.mockImplementation(() => {throw new Error("source unavailable");}); clock.advance();
  expect(readout().textContent).toBe("UNAVAILABLE");
  outputMeter.mockReturnValue(measured({leftPeak: 0.01})); clock.advance();
  expect(screen.getByRole("meter", {name: "Left output level"}).getAttribute("data-held-peak")).toBe("0.01");
});

test.each([null, {}])("a missing measurement capability %s has no numeric fallback or reader", source => {
  const clock = frames();
  render(<StereoOutputMeter source={source} projectId="project-a" running />);
  expect(readout().textContent).toBe("UNAVAILABLE");
  expect(clock.request).not.toHaveBeenCalled();
});

test("a closed Project never reads the previous Project's measurement", () => {
  const clock = frames(); const outputMeter = vi.fn(() => measured());
  render(<StereoOutputMeter source={{outputMeter}} projectId={null} running />);
  expect(outputMeter).not.toHaveBeenCalled(); expect(clock.request).not.toHaveBeenCalled();
  expect(readout().textContent).toBe("UNAVAILABLE");
});

test("visible reads never issue commands or change monitor, FX or Project state", () => {
  const clock = frames(); const source = {outputMeter: vi.fn(() => measured()),
    send: vi.fn(), trigger: vi.fn(), setMonitorVolume: vi.fn(), updatePad: vi.fn()};
  render(<StereoOutputMeter source={source} projectId="project-a" running />);
  clock.advance(); clock.advance();
  expect(source.outputMeter).toHaveBeenCalledTimes(3);
  for (const method of [source.send, source.trigger, source.setMonitorVolume, source.updatePad])
    expect(method).not.toHaveBeenCalled();
});
