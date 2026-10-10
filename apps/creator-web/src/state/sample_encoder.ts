import type {PadPlayback, SampleMetadata} from "../runtime/runtime_types";
import {fitPlaybackLoop, playbackEquals} from "./sample_state";
import {ENCODER_IDLE_COMMIT_MS} from "./encoder_input";

export type SampleEncoderParameter = "start" | "end" | "pitch" | "gain" | "pan" | "tone";

export function adjustSampleEncoder(
  playback: Readonly<PadPlayback>, metadata: Readonly<SampleMetadata>,
  parameter: SampleEncoderParameter, detents: number, fine: boolean,
): Readonly<PadPlayback> {
  const delta = Math.trunc(detents);
  if (!Number.isFinite(delta) || delta === 0) return playback;
  const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
  const frameStep = fine ? 1 : Math.round(metadata.sampleRate / 100);
  switch (parameter) {
    case "start": return fitPlaybackLoop({...playback,
      trimStartFrame: clamp(playback.trimStartFrame + delta * frameStep, 0,
        (playback.trimEndFrame ?? metadata.sourceFrames) - 1)}, metadata.sourceFrames);
    case "end": {
      const end = clamp((playback.trimEndFrame ?? metadata.sourceFrames) + delta * frameStep,
        playback.trimStartFrame + 1, metadata.sourceFrames);
      return fitPlaybackLoop({...playback, trimEndFrame: end === metadata.sourceFrames ? null : end}, metadata.sourceFrames);
    }
    case "pitch": return {...playback, pitchCents: clamp(playback.pitchCents + delta * (fine ? 10 : 100), -2400, 2400)};
    case "gain": return {...playback, gainMillidb: clamp(playback.gainMillidb + delta * (fine ? 100 : 1000), -60000, 6000)};
    case "pan": return {...playback, pan: clamp(playback.pan + delta * (fine ? 1 : 10), -100, 100)};
    case "tone": return {...playback, tone: clamp(playback.tone + delta * (fine ? 1 : 10), -100, 100)};
  }
}

export function createSampleEncoderTurn(options: {
  schedule(callback: () => void, delay: number): unknown;
  clear(handle: unknown): void;
  preview(playback: Readonly<PadPlayback>): void;
  commit(playback: Readonly<PadPlayback>): void;
  cancel(): void;
}) {
  let timer: unknown = null;
  let current: {base: Readonly<PadPlayback>; value: Readonly<PadPlayback>} | null = null;
  const clear = () => {if (timer !== null) options.clear(timer); timer = null;};
  return {
    pending: () => current !== null,
    turn(parameter: SampleEncoderParameter, detents: number, fine: boolean,
      saved: Readonly<PadPlayback>, metadata: Readonly<SampleMetadata>) {
      if (!Number.isFinite(detents) || Math.trunc(detents) === 0) return;
      const previous = current?.value ?? saved;
      const next = adjustSampleEncoder(previous, metadata, parameter, detents, fine);
      if (current === null && playbackEquals(previous, next)) return;
      current ??= {base: saved, value: saved};
      current.value = next;
      options.preview(next);
      clear();
      timer = options.schedule(() => {
        timer = null;
        const settled = current;
        current = null;
        if (settled === null || playbackEquals(settled.base, settled.value)) options.cancel();
        else options.commit(settled.value);
      }, ENCODER_IDLE_COMMIT_MS);
    },
    cancel() {
      clear();
      if (current === null) return;
      current = null;
      options.cancel();
    },
  };
}
