import {
  selectTransportBusy,
  selectTransportPlaying,
  selectTransportRecording,
  type PatternTransportState,
} from "../state/pattern_transport_state";

interface SequenceTransportProps {
  transport: PatternTransportState;
  ready: boolean;
  onPlayStop(): void;
  onRecord(): void;
  onRefresh(): void;
}

// The surface renders only the acknowledged projection: busy phases, a
// durable-but-unpublished commit and a retained error are their own states,
// never decorated as successful steady states.
export function transportStatusLabel(transport: PatternTransportState): string {
  const status = transport.status;
  if (status === null || !status.engaged) return "stopped";
  if (status.phase === "error") return "error";
  if (status.phase !== "idle") return status.phase;
  if (status.recording) return "recording";
  if (status.playing) return "playing";
  return "stopped";
}

export function SequenceTransport({
  transport,
  ready,
  onPlayStop,
  onRecord,
  onRefresh,
}: SequenceTransportProps) {
  const busy = selectTransportBusy(transport);
  const playing = selectTransportPlaying(transport);
  const recording = selectTransportRecording(transport);
  const label = transportStatusLabel(transport);
  return (
    <section className="sequence-transport" aria-label="Sequence transport">
      <p role="status">
        {label}
        {transport.status?.publicationPending === true
          ? " · committed, publication pending"
          : ""}
      </p>
      <button type="button" disabled={!ready || busy} onClick={onPlayStop}>
        {playing ? "Stop" : "Play"}
      </button>
      <button type="button" disabled={!ready || busy} onClick={onRecord}>
        {recording ? "Record off" : "Record"}
      </button>
      <button type="button" onClick={onRefresh}>Refresh authority</button>
      {!ready ? (
        <p className="transport-hint">Activate audio to record</p>
      ) : null}
      {transport.lastFailed !== null ? (
        <p className="transport-hint">
          Last {transport.lastFailed.intent === "record" ? "Record" : "Play/Stop"}
          {" "}command failed; retry reconciles the same command.
        </p>
      ) : null}
      {transport.errorCode !== null ? (
        <p role="alert" className="sequence-error">{transport.errorCode}</p>
      ) : null}
    </section>
  );
}
