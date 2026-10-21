import type {RecordingAudioProgress} from "../state/perform_state";

function audioTime(frames: number, sampleRate: number): string {
  if (!Number.isSafeInteger(frames) || frames < 0 ||
      !Number.isSafeInteger(sampleRate) || sampleRate <= 0) return "Unavailable";
  const milliseconds = Math.floor(frames / sampleRate * 1000);
  const minutes = String(Math.floor(milliseconds / 60_000)).padStart(2, "0");
  const seconds = String(Math.floor(milliseconds / 1000) % 60).padStart(2, "0");
  const fraction = String(milliseconds % 1000).padStart(3, "0");
  return `${minutes}:${seconds}.${fraction}`;
}

export function RecordingAudioReadout({progress}: {
  readonly progress: RecordingAudioProgress | null;
}) {
  if (progress === null) return null;
  const capture = progress.capture;
  const wav = progress.wav;
  const prefix = wav !== null && (wav.snapshot.droppedFrames > 0 ||
    (wav.snapshot.reason !== null && wav.snapshot.reason !== "stopped" &&
      wav.snapshot.reason !== "frame-limit"));
  const unknownLoss = progress.tapLoss === null && (prefix ||
    (capture.state === "available" && capture.phase === "failed"));
  return <section className="perform-audio-readout" aria-label="Recording audio readout"
    data-session-id={progress.sessionId} data-performance-id={progress.performanceId}>
    <dl>
      <div><dt>Captured audio</dt><dd>
        <output role="status" aria-live="off" aria-label="Captured audio"
          data-capture-id={capture.state === "available" ? capture.captureId : undefined}
          data-frames={capture.state === "available" ? capture.receivedFrames : undefined}
          data-rate={capture.state === "available" ? capture.sampleRate : undefined}
          data-phase={capture.state === "available" ? capture.phase : "unavailable"}>
          {capture.state === "available"
            ? audioTime(capture.receivedFrames, capture.sampleRate) : "Unavailable"}
        </output>
      </dd></div>
      <div><dt>{prefix ? "Local WAV prefix" : "Local WAV"}</dt><dd>
        <output role="status" aria-live="off" aria-label="Local WAV audio"
          data-frames={wav?.snapshot.durableFrames} data-rate={wav?.format?.sampleRate}
          data-settled={wav?.settled ?? false} data-reason={wav?.snapshot.reason ?? undefined}
          data-dropped-frames={wav?.snapshot.droppedFrames}>
          {wav?.format ? audioTime(wav.snapshot.durableFrames, wav.format.sampleRate) : "Unavailable"}
        </output>
      </dd></div>
      {wav !== null && wav.snapshot.droppedFrames > 0 ? <div>
        <dt>Dropped frames</dt><dd>{wav.snapshot.droppedFrames}</dd>
      </div> : null}
    </dl>
    {unknownLoss ? <p>Additional audio loss unknown</p> : null}
  </section>;
}
