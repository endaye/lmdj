import type {PatternTransportState} from "../state/pattern_transport_state";

// One reading of the global Pattern transport for every read-only surface.
export function transportStatusLabel(transport: PatternTransportState): string {
  const status = transport.status;
  if (status === null || !status.engaged) return "stopped";
  if (status.phase === "error") return "error";
  if (status.phase !== "idle") return status.phase;
  if (status.recording) return "recording";
  if (status.playing) return "playing";
  return "stopped";
}
