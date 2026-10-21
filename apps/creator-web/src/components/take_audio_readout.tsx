import type {ProjectView} from "../runtime/runtime_types";
import {sameRecordingArtifact, type PerformanceSummary, type TakeAudioState} from "../state/perform_state";
import {audioTime} from "./recording_audio_readout";

export function TakeAudioReadout({project, performance, value, onRetry}: {
  readonly project: ProjectView;
  readonly performance: PerformanceSummary;
  readonly value: TakeAudioState | null;
  readonly onRetry: () => void;
}) {
  // Render guards run before effects: a same-ID reopen or ref/revision change
  // must never flash an old time while the next query is being scheduled.
  const current = value?.owner === project && value.performanceId === performance.performanceId &&
    sameRecordingArtifact(value.artifact, performance.recordingArtifact) &&
    (value.metadata === null || (value.metadata.projectId === project.projectId &&
      value.metadata.performanceId === performance.performanceId &&
      value.metadata.projectRevision === project.revision &&
      sameRecordingArtifact(value.metadata.recordingArtifact, performance.recordingArtifact))) ? value : null;
  const audio = current?.state === "verified" ? current.metadata.audioMetadata : null;
  const label = performance.recordingArtifact === null ? "No WAV attached"
    : current?.state === "reading" ? "Checking WAV…"
    : current?.state === "unsupported" ? "WAV format unsupported"
    : current?.state === "damaged" ? "WAV integrity check failed"
    : audio !== null ? audioTime(audio.sourceFrames, audio.sampleRate)
    : "Audio duration unavailable";
  return <section className="perform-audio-readout perform-take-audio" aria-label="Saved Take audio">
    <dl><div><dt>WAV audio</dt><dd>
      <output role="status" aria-live="polite" aria-label="Take WAV audio"
        data-performance-id={performance.performanceId}
        data-state={current?.state ?? "unavailable"}
        data-project-revision={current?.metadata?.projectRevision}
        data-recording-revision={current?.metadata?.recordingRevision}
        data-sha256={current?.metadata?.recordingArtifact.sha256}
        data-byte-length={current?.metadata?.recordingArtifact.byteLength}
        data-frames={audio?.sourceFrames} data-rate={audio?.sampleRate} data-channels={audio?.channels}>
        {label}
      </output>
    </dd></div></dl>
    {audio !== null ? <p>Recording completeness unknown</p> : null}
    {current?.state === "damaged" ? <p>The WAV no longer matches this saved Take.</p> : null}
    {(current === null && performance.recordingArtifact !== null) ||
        current?.state === "unavailable" || current?.state === "damaged" ?
      <button type="button" onClick={onRetry}>Retry audio check</button> : null}
  </section>;
}
