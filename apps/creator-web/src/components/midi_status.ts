export interface MidiStatus {
  readonly permission: string;
  readonly connectedInputCount: number;
}

export function midiLabel(midi: MidiStatus | null | undefined): string {
  if (!midi) return "—";
  switch (midi.permission) {
    case "granted":
      return midi.connectedInputCount === 1
        ? "1 input"
        : `${midi.connectedInputCount} inputs`;
    case "requesting":
      return "requesting";
    case "denied":
      return "denied";
    default:
      return "off";
  }
}
