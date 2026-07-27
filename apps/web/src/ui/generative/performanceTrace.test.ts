import { describe, expect, it } from "vitest";
import {
  appendPerformanceTrace,
  beatDurationMs,
  prunePerformanceTraces,
  type PerformanceTrace,
} from "./performanceTrace";

describe("performanceTrace", () => {
  it("uses exactly one quarter-note beat", () => {
    expect(beatDurationMs(120)).toBe(500);
    expect(beatDurationMs(90)).toBeCloseTo(666.666, 2);
  });

  it("creates a stable event and expires it after one beat", () => {
    const traces = appendPerformanceTrace(
      [],
      { sequence: 1, padIndex: 3 },
      "lead",
      "patch-a",
      120,
      1_000,
    );
    expect(traces).toEqual([
      {
        id: "patch-a:1:3",
        padIndex: 3,
        role: "lead",
        signatureSeed: "patch-a:3:1",
        expiresAt: 1_500,
      },
    ]);
    expect(prunePerformanceTraces(traces, 1_499)).toHaveLength(1);
    expect(prunePerformanceTraces(traces, 1_500)).toHaveLength(0);
  });

  it("keeps only the newest eight direct gestures", () => {
    const traces = Array.from({ length: 10 }, (_, index) => index).reduce<
      PerformanceTrace[]
    >(
      (current, sequence) =>
        appendPerformanceTrace(
          current,
          { sequence, padIndex: sequence % 16 },
          "action",
          "patch-a",
          100,
          sequence,
        ),
      [],
    );
    expect(traces).toHaveLength(8);
    expect(traces[0].id).toBe("patch-a:2:2");
    expect(traces[7].id).toBe("patch-a:9:9");
  });
});
