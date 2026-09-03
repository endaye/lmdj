import type {SequenceState} from "../state/sequence_state";

interface SequenceTransportProps {
  state: SequenceState;
  ready: boolean;
  onRecord(): void;
  onStop(): void;
  onRefresh(): void;
}

export function SequenceTransport({state, ready, onRecord, onStop, onRefresh}: SequenceTransportProps) {
  const recording = ["recording", "switch-pending", "flushing"].includes(state.phase);
  return (
    <section className="sequence-transport" aria-label="Sequence transport">
      <p role="status">{state.phase}</p>
      <button type="button" disabled={!ready || recording} onClick={onRecord}>Record</button>
      <button type="button" disabled={!recording || state.phase === "flushing"} onClick={onStop}>Stop</button>
      <button type="button" onClick={onRefresh}>Refresh authority</button>
      {!ready && !recording ? (
        <p className="transport-hint">Activate audio to record</p>
      ) : null}
      {state.status?.effectiveRuntimeFrame !== null &&
        state.status?.effectiveRuntimeFrame !== undefined ? (
          <p className="transport-frame">Next Bar frame: {state.status.effectiveRuntimeFrame}</p>
        ) : null}
    </section>
  );
}
