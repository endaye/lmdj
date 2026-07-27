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
  onPress,
  onRelease,
  bank,
  onBankChange,
  onMappingModeChange,
}: {
  onPress: (index: number) => void;
  onRelease: (index: number) => void;
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
  const pressRef = useRef(onPress);
  const releaseRef = useRef(onRelease);
  const activeNotesRef = useRef(new Map<number, number>());
  const learnRef = useRef<LearnState | null>(null);
  mappingRef.current = mapping;
  bankRef.current = bank;
  pressRef.current = onPress;
  releaseRef.current = onRelease;

  const handleNote = useCallback((note: number, pressed: boolean) => {
    const learn = learnRef.current;
    if (learn) {
      if (!pressed) return;
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

    if (!pressed) {
      const activeIndex = activeNotesRef.current.get(note);
      if (activeIndex === undefined) return;
      activeNotesRef.current.delete(note);
      releaseRef.current(activeIndex);
      return;
    }

    const index = padIndexForNote(mappingRef.current, note, bankRef.current);
    if (index !== null) {
      activeNotesRef.current.set(note, index);
      pressRef.current(index);
    }
  }, []);

  const [midi] = useState(() => new MidiInput(handleNote));

  const releaseActiveNotes = useCallback(() => {
    const activeIndexes = new Set(activeNotesRef.current.values());
    activeNotesRef.current.clear();
    for (const index of activeIndexes) releaseRef.current(index);
  }, []);

  useEffect(() => {
    setSnapshot(midi.snapshot);
    return midi.subscribe(setSnapshot);
  }, [midi]);

  useEffect(
    () => () => {
      releaseActiveNotes();
      midi.dispose();
    },
    [midi, releaseActiveNotes],
  );

  useEffect(() => {
    if (snapshot.connection !== "connected") releaseActiveNotes();
  }, [releaseActiveNotes, snapshot.connection]);

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
          onClick={() => void midi.connect()}
          disabled={
            snapshot.connection === "requesting" ||
            snapshot.connection === "connected" ||
            snapshot.support === "unsupported"
          }
        >
          Connect MIDI
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
        <button type="button" onClick={() => beginLearn("direct-16")}>
          Learn Direct 16
        </button>
        <button type="button" onClick={() => beginLearn("banked-8")}>
          Learn 8-pad
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
