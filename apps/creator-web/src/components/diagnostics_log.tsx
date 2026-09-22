export const DIAGNOSTICS_LIMIT = 100;

export interface DiagnosticRecord {
  readonly timestamp: string;
  readonly operation: string;
  readonly code: string;
  readonly message: string;
  readonly details: Readonly<Record<string, unknown>>;
}

// Retain only the error envelope, never the request, Project or Error stack.
export function diagnosticRecord(operation: string, error: unknown): DiagnosticRecord {
  const envelope = error as {code?: unknown; message?: unknown; details?: unknown} | null;
  let details: Readonly<Record<string, unknown>> = {};
  if (envelope?.details !== null && typeof envelope?.details === "object" &&
      !Array.isArray(envelope.details)) {
    // Protocol details are JSON. Snapshot them so later mutation cannot rewrite
    // history; malformed non-protocol exceptions must not break error handling.
    try { details = JSON.parse(JSON.stringify(envelope.details)); } catch { /* empty */ }
  }
  return {
    timestamp: new Date().toISOString(),
    operation,
    code: error instanceof DOMException && error.name === "AbortError"
      ? "ABORTED"
      : typeof envelope?.code === "string" ? envelope.code : "INTERNAL_ERROR",
    message: typeof envelope?.message === "string" ? envelope.message : "Unknown error",
    details,
  };
}

export function appendDiagnostic(
  records: readonly DiagnosticRecord[], record: DiagnosticRecord,
): readonly DiagnosticRecord[] {
  return [...records.slice(-(DIAGNOSTICS_LIMIT - 1)), record];
}

export function DiagnosticsLog({records}: {records: readonly DiagnosticRecord[]}) {
  return (
    <details className="diagnostics-log">
      <summary>Developer diagnostics ({records.length})</summary>
      <section aria-label="Developer diagnostics">
        <p>Session errors · latest {DIAGNOSTICS_LIMIT} records · kept in memory only.</p>
        {records.length === 0 ? <p>No errors recorded.</p> : (
          <ol>{records.map((record, index) => (
            <li key={index}>
              <time dateTime={record.timestamp}>{record.timestamp}</time>
              <strong>{record.operation}</strong>
              <code>{record.code}</code>
              <p>{record.message}</p>
              <pre>{JSON.stringify(record.details, null, 2)}</pre>
            </li>
          ))}</ol>
        )}
      </section>
    </details>
  );
}
