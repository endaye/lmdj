import { useCallback, useEffect, useRef, useState } from "react";
import { MidiInput, type MidiSnapshot } from "../midi/MidiInput";
import {
  loadMidiMapping,
  MidiLearnSession,
  padIndexForNote,
  saveMidiMapping,
  type MidiBank,
  type MidiMapping,
} from "../midi/mapping";

const INITIAL_SNAPSHOT: MidiSnapshot = {
  support: "unknown",
  connection: "idle",
  devices: [],
};

interface LearnState {
  notes: Set<number>;
  target: number;
  session: MidiLearnSession;
}

const CONNECTION_LABELS: Record<MidiSnapshot["connection"], string> = {
  idle: "Not connected",
  requesting: "Requesting",
  connected: "Connected",
  denied: "Permission denied",
  disconnected: "Disconnected",
};

export function MidiPanel({
  onTrigger,
  bank,
  onBankChange,
  onMappingModeChange,
}: {
  onTrigger: (index: number) => void;
  bank: MidiBank;
  onBankChange: (bank: MidiBank) => void;
  onMappingModeChange?: (mode: MidiMapping["mode"]) => void;
}) {
  const [mapping, setMapping] = useState<MidiMapping>(() =>
    loadMidiMapping(localStorage),
  );
  const [snapshot, setSnapshot] = useState(INITIAL_SNAPSHOT);
  const [learnProgress, setLearnProgress] = useState<{
    captured: number;
    target: number;
  } | null>(null);
  const mappingRef = useRef(mapping);
  const bankRef = useRef(bank);
  const triggerRef = useRef(onTrigger);
  const learnRef = useRef<LearnState | null>(null);
  mappingRef.current = mapping;
  bankRef.current = bank;
  triggerRef.current = onTrigger;

  const handleNote = useCallback((note: number) => {
    const learn = learnRef.current;
    if (learn) {
      const completed = learn.session.capture(note);
      if (Number.isInteger(note) && note >= 0 && note <= 127) {
        learn.notes.add(note);
      }
      setLearnProgress({
        captured: learn.notes.size,
        target: learn.target,
      });
      if (completed) {
        saveMidiMapping(localStorage, completed);
        mappingRef.current = completed;
        setMapping(completed);
        learnRef.current = null;
        setLearnProgress(null);
      }
      return;
    }

    const index = padIndexForNote(mappingRef.current, note, bankRef.current);
    if (index !== null) triggerRef.current(index);
  }, []);

  const [midi] = useState(() => new MidiInput(handleNote));

  useEffect(() => {
    setSnapshot(midi.snapshot);
    return midi.subscribe(setSnapshot);
  }, [midi]);

  useEffect(() => () => midi.dispose(), [midi]);

  useEffect(() => {
    onMappingModeChange?.(mapping.mode);
  }, [mapping.mode, onMappingModeChange]);

  const beginLearn = (mode: MidiMapping["mode"]) => {
    const target = mode === "direct-16" ? 16 : 8;
    learnRef.current = {
      notes: new Set(),
      target,
      session: new MidiLearnSession(mode),
    };
    setLearnProgress({ captured: 0, target });
  };

  const direct = mapping.mode === "direct-16";
  const supportLabel =
    snapshot.support === "unsupported"
      ? "Web MIDI unsupported"
      : CONNECTION_LABELS[snapshot.connection];

  return (
    <section className="midi-panel" aria-label="MIDI controller">
      <div className="midi-panel__connection">
        <strong>MIDI</strong>
        <span data-testid="midi-connection">{supportLabel}</span>
        <button
          type="button"
          aria-label="Connect MIDI"
          onClick={() => void midi.connect()}
          disabled={
            snapshot.connection === "requesting" ||
            snapshot.connection === "connected" ||
            snapshot.support === "unsupported"
          }
        >
          Connect
        </button>
      </div>

      <span data-testid="midi-devices">
        {snapshot.devices.length > 0
          ? snapshot.devices.join(", ")
          : "No MIDI input"}
      </span>

      <div className="midi-panel__mapping">
        <span data-testid="midi-mapping-mode">
          {direct ? "Direct 16" : "8-pad Controller"}
        </span>
        <button
          type="button"
          aria-label="Learn Direct 16"
          onClick={() => beginLearn("direct-16")}
        >
          Learn 16
        </button>
        <button
          type="button"
          aria-label="Learn 8-pad"
          onClick={() => beginLearn("banked-8")}
        >
          Learn 8
        </button>
      </div>

      {learnProgress && (
        <span data-testid="midi-learn-progress">
          Learn {learnProgress.captured} / {learnProgress.target}
        </span>
      )}

      <div className="midi-panel__bank" data-testid="midi-bank-status">
        {direct ? (
          <span>Bank 不适用（Direct 16）</span>
        ) : (
          <>
            <span>Hardware Bank</span>
            {(["A", "B"] as const).map((candidate) => (
              <button
                key={candidate}
                type="button"
                aria-label={`Bank ${candidate}`}
                aria-pressed={bank === candidate}
                onClick={() => onBankChange(candidate)}
              >
                {candidate}
              </button>
            ))}
          </>
        )}
      </div>
    </section>
  );
}
