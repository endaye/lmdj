// The Creator-side anchor between the engine frame clock and the AudioContext
// clock. The runtime session owns the AudioContext; the Host injects
// createRetainedAudioContext as the session's context factory so this module
// keeps a reference to the exact device clock the engine renders to.
//
// Within one engine epoch the engine frame counter and the AudioContext clock
// advance 1:1 at 48 000 frames per second (128 frames per audio callback, the
// gate open from audio.activate until engine stop). sampleAnchor() pairs one
// session clock sample with the engine frame derived from it; every later
// conversion is pure arithmetic against that anchor. The anchor carries a
// constant error of at most a couple of render quanta — the callbacks that
// ran between the gate opening and the epoch sample — and no per-beat drift.
// It must be re-sampled on every new epoch (any return of the audio phase to
// running) and invalidated when audio leaves running.
import type {CreatorRuntimeSession} from "./runtime_types";

export const ENGINE_FRAMES_PER_SECOND = 48_000;
const HEARTBEAT_MODULUS = 0x1_0000_0000;

let retainedContext: AudioContext | null = null;

export interface AudioClockAnchor {
  readonly contextTimeSeconds: number;
  readonly engineFrameAtSample: number;
}

let anchor: AudioClockAnchor | null = null;

// The session calls this once per context it creates and owns the context
// lifecycle; this module only retains the reference.
export function createRetainedAudioContext(
  options?: AudioContextOptions,
): AudioContext {
  retainedContext = new AudioContext(options);
  return retainedContext;
}

export function retainedAudioContext(): AudioContext | null {
  return retainedContext;
}

// The callback heartbeat is a uint32 counter; the delta within one epoch is
// small, so one modulus correction covers a wrap. A session without the
// accessor (only test fakes) is refused the same way as audio not running.
export function sampleAnchor(
  session: Pick<CreatorRuntimeSession, "sampleAudioClock">,
): AudioClockAnchor {
  if (typeof session.sampleAudioClock !== "function") {
    throw new Error("Audio clock is unavailable on this session");
  }
  const sample = session.sampleAudioClock();
  const callbacks =
    (sample.callbackHeartbeat - sample.engineEpochHeartbeat +
      HEARTBEAT_MODULUS) % HEARTBEAT_MODULUS;
  anchor = {
    contextTimeSeconds: sample.contextTimeSeconds,
    engineFrameAtSample: callbacks * 128,
  };
  return anchor;
}

export function hasAnchor(): boolean {
  return anchor !== null;
}

export function invalidate(): void {
  anchor = null;
}

function requireAnchor(): AudioClockAnchor {
  if (anchor === null) {
    throw new Error("Audio clock anchor is not sampled");
  }
  return anchor;
}

export function engineFrameToContextSeconds(engineFrame: number): number {
  const current = requireAnchor();
  return (
    current.contextTimeSeconds +
    (engineFrame - current.engineFrameAtSample) / ENGINE_FRAMES_PER_SECOND
  );
}

export function contextSecondsToEngineFrame(contextSeconds: number): number {
  const current = requireAnchor();
  return (
    current.engineFrameAtSample +
    (contextSeconds - current.contextTimeSeconds) * ENGINE_FRAMES_PER_SECOND
  );
}
