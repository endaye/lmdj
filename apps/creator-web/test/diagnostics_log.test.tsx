import {render, screen} from "@testing-library/react";
import {expect, test} from "vitest";
import {
  appendDiagnostic, diagnosticRecord, DiagnosticsLog, DIAGNOSTICS_LIMIT,
  type DiagnosticRecord,
} from "../src/components/diagnostics_log";

test("records only timestamp, operation and the full error envelope", () => {
  const error = Object.assign(new Error("Explicitly discard the recording"), {
    code: "INVALID_ARGUMENT",
    details: {reason: "sequence_admission_unresolved", journal_retained: true},
    request: {secret: "not part of the envelope"},
  });
  const record = diagnosticRecord("Recover Sequence Pattern", error);
  expect(record).toEqual({
    timestamp: expect.stringMatching(/^\d{4}-\d\d-\d\dT.*Z$/),
    operation: "Recover Sequence Pattern", code: error.code,
    message: error.message, details: error.details,
  });
  render(<DiagnosticsLog records={[record]} />);
  expect(screen.getByText(error.message)).toBeTruthy();
  expect(screen.getByText(error.code)).toBeTruthy();
  expect(screen.getByText(/"journal_retained": true/).textContent)
    .toContain('"reason": "sequence_admission_unresolved"');
});

test("snapshots details instead of retaining a mutable error reference", () => {
  const details = {nested: {reason: "original"}};
  const record = diagnosticRecord("Test", {details});
  details.nested.reason = "changed";
  expect(record.details).toEqual({nested: {reason: "original"}});
});

test("evicts only the oldest records at the declared bound", () => {
  let records: readonly DiagnosticRecord[] = [];
  for (let i = 0; i < DIAGNOSTICS_LIMIT * 3; i += 1) {
    const previous = records;
    records = appendDiagnostic(records, diagnosticRecord(`Operation ${i}`, null));
    expect(records).not.toBe(previous);
    expect(records.length).toBe(Math.min(i + 1, DIAGNOSTICS_LIMIT));
  }
  expect(records.map(({operation}) => operation)).toEqual(
    Array.from({length: DIAGNOSTICS_LIMIT}, (_, i) => `Operation ${i + 200}`),
  );
});

test("non-protocol exceptions keep normal error handling usable", () => {
  expect(diagnosticRecord("Test", null)).toMatchObject({
    code: "INTERNAL_ERROR", message: "Unknown error", details: {},
  });
  expect(diagnosticRecord("Test", new DOMException("Cancelled", "AbortError")))
    .toMatchObject({code: "ABORTED", message: "Cancelled", details: {}});
  const details: Record<string, unknown> = {};
  details.self = details;
  expect(diagnosticRecord("Test", {details}).details).toEqual({});
});
