import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deriveChameleonVisualState } from "./adapter";
import { useChameleonController } from "./useChameleonController";

describe("useChameleonController", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("keeps the Gallery Stage visible", () => {
    const visual = deriveChameleonVisualState({ appPhase: "source" });
    const { result } = renderHook(() => useChameleonController(visual));
    expect(result.current.expanded).toBe(true);
    expect(result.current.visualState.placement).toBe("stage");
  });

  it("reveals ready once, closes after 4000ms, and does not replay the same key", () => {
    const visual = deriveChameleonVisualState({
      appPhase: "loaded",
      patchId: "patch-1",
    });
    const { result, rerender } = renderHook(
      ({ state }) => useChameleonController(state),
      { initialProps: { state: visual } },
    );
    expect(result.current.expanded).toBe(true);
    expect(result.current.visualState.placement).toBe("floating");

    act(() => vi.advanceTimersByTime(4000));
    expect(result.current.expanded).toBe(false);
    rerender({ state: { ...visual } });
    expect(result.current.expanded).toBe(false);
  });

  it("keeps error open until dismissed", () => {
    const visual = deriveChameleonVisualState({
      appPhase: "failed",
      errorKey: "submission-1:upload",
    });
    const { result } = renderHook(() => useChameleonController(visual));
    act(() => vi.advanceTimersByTime(10000));
    expect(result.current.expanded).toBe(true);
    act(() => result.current.dismiss());
    expect(result.current.expanded).toBe(false);
  });

  it("never auto-closes a manual reveal", () => {
    const visual = deriveChameleonVisualState({
      appPhase: "processing",
      jobState: "separating",
    });
    const { result } = renderHook(() => useChameleonController(visual));
    act(() => result.current.reveal());
    act(() => vi.advanceTimersByTime(10000));
    expect(result.current.expanded).toBe(true);
  });
});
