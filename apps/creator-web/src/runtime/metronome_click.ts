// Metronome click playback. A timer only tops up a queue — it never times a
// click: on each tick the loop asks the Host-supplied `supply` for the beats
// whose context time falls inside the lookahead horizon and schedules every
// one it has not scheduled yet, directly on the AudioContext clock.
//
// Every click connects straight to `audioContext.destination` and NEVER
// through the Perform master tap: the tap node is the only capture point for
// Perform recordings and main-output resamples, so bypassing it keeps clicks
// out of every recording while staying audible alongside them
// (2026-10-02 tempo/metronome decision, item 7).
//
// Each scheduled click dispatches `lmdj:metronome-click` with
// {contextTime, beat, accent} — the documented observability seam for the
// metronome journeys and diagnostics. Stop (toggle-off, transport stop, grid
// change) cancels every queued click that has not sounded yet.

export interface MetronomeClickBeat {
  readonly contextTime: number;
  readonly beat: number;
  readonly accent: boolean;
}

export interface MetronomeClickLoop {
  start(contextSeconds: number): void;
  stop(): void;
  isRunning(): boolean;
}

const LOOKAHEAD_SECONDS = 0.120;
const TOP_UP_MS = 40;
const ACCENT_FREQUENCY_HZ = 1_800;
const NORMAL_FREQUENCY_HZ = 1_200;
const CLICK_GAIN = 0.2;
const CLICK_DECAY_SECONDS = 0.04;

interface ScheduledClick {
  readonly contextTime: number;
  readonly oscillator: OscillatorNode;
  readonly envelope: GainNode;
}

export function createMetronomeClickLoop(options: {
  readonly context: AudioContext;
  // Beats wanted inside [fromSeconds, untilSeconds), in context seconds.
  readonly supply: (
    fromSeconds: number,
    untilSeconds: number,
  ) => readonly MetronomeClickBeat[];
  readonly eventTarget?: Pick<Window, "dispatchEvent">;
  readonly setTimer?: (tick: () => void, ms: number) => unknown;
  readonly clearTimer?: (timer: unknown) => void;
}): MetronomeClickLoop {
  const eventTarget = options.eventTarget ?? window;
  const setTimer = options.setTimer ??
    ((tick: () => void, ms: number) => setInterval(tick, ms));
  const clearTimer = options.clearTimer ??
    ((timer: unknown) => clearInterval(timer as ReturnType<typeof setInterval>));
  let timer: unknown = null;
  const scheduled = new Map<string, ScheduledClick>();

  function scheduleClick(beat: MetronomeClickBeat): void {
    const oscillator = options.context.createOscillator();
    const envelope = options.context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = beat.accent
      ? ACCENT_FREQUENCY_HZ
      : NORMAL_FREQUENCY_HZ;
    envelope.gain.setValueAtTime(CLICK_GAIN, beat.contextTime);
    envelope.gain.exponentialRampToValueAtTime(
      0.0001, beat.contextTime + CLICK_DECAY_SECONDS);
    oscillator.connect(envelope);
    envelope.connect(options.context.destination);
    oscillator.start(beat.contextTime);
    oscillator.stop(beat.contextTime + CLICK_DECAY_SECONDS);
    scheduled.set(`${beat.contextTime}:${beat.beat}`, {
      contextTime: beat.contextTime,
      oscillator,
      envelope,
    });
    eventTarget.dispatchEvent(new CustomEvent("lmdj:metronome-click", {
      detail: {
        contextTime: beat.contextTime,
        beat: beat.beat,
        accent: beat.accent,
      },
    }));
  }

  function topUp(fromSeconds: number): void {
    const untilSeconds = fromSeconds + LOOKAHEAD_SECONDS;
    // Retire clicks whose decay has finished; the map is the de-dupe record
    // for the overlapping windows successive ticks produce.
    for (const [key, click] of scheduled) {
      if (click.contextTime + CLICK_DECAY_SECONDS < fromSeconds) {
        scheduled.delete(key);
      }
    }
    for (const beat of options.supply(fromSeconds, untilSeconds)) {
      if (scheduled.has(`${beat.contextTime}:${beat.beat}`)) continue;
      scheduleClick(beat);
    }
  }

  return {
    start(contextSeconds: number): void {
      if (timer !== null) return;
      topUp(contextSeconds);
      timer = setTimer(() => topUp(options.context.currentTime), TOP_UP_MS);
    },
    stop(): void {
      if (timer !== null) {
        clearTimer(timer);
        timer = null;
      }
      const nowSeconds = options.context.currentTime;
      for (const click of scheduled.values()) {
        if (click.contextTime <= nowSeconds) continue;
        try {
          click.oscillator.stop();
        } catch {
          // An oscillator that reached its own stop time refuses a second.
        }
        click.oscillator.disconnect();
        click.envelope.disconnect();
      }
      scheduled.clear();
    },
    isRunning(): boolean {
      return timer !== null;
    },
  };
}
