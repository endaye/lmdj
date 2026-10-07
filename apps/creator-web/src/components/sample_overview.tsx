import type {CreatorState} from "../state/creator_state";
import {padAddress} from "../state/view_model";

interface SampleOverviewProps {
  state: CreatorState;
}

const WIDTH = 720;
const HEIGHT = 96;

function seconds(frames: number, sampleRate: number): string {
  return (frames / sampleRate).toFixed(3);
}

// D03's read-only upper screen: the selected Pad, the Sample's format and
// trim selection, and the whole waveform with the selection marked. Trim,
// audition, assign and capture stay in the touch workspace.
export function SampleOverview({state}: SampleOverviewProps) {
  const slot = state.sample.selectedSlot;
  const inspect = state.sample.inspect;
  const metadata = inspect?.metadata ?? null;
  const playback = inspect?.playback ?? null;
  const envelope = state.sample.waveform;
  const frames = metadata?.sourceFrames ?? 0;
  const clamp = (frame: number) => Math.min(Math.max(frame, 0), frames);
  const selection = metadata === null || playback === null
    ? null
    : {start: clamp(playback.trimStartFrame), end: clamp(playback.trimEndFrame ?? frames)};
  const x = (frame: number) => frames === 0 ? 0 : Math.round(frame * WIDTH / frames);
  const bars = envelope === null || frames === 0 || envelope.metadata.sourceFrames !== frames
    ? []
    : envelope.buckets.map((bucket) => {
      const height = Math.max(1, Math.round(bucket.peakMagnitude * (HEIGHT - 8) / 32_768));
      return {x: x(bucket.startFrame), width: Math.max(1, x(bucket.endFrame) - x(bucket.startFrame)), height};
    });
  return (
    <div className="sample-overview" data-testid="sample-overview">
      <p className="sample-overview-pad">
        {slot === null ? "NO PAD" : `PAD ${padAddress({slot, assetId: null})}`}
      </p>
      <dl className="sample-overview-facts">
        <div>
          <dt>Format</dt>
          <dd>
            {metadata === null
              ? "—"
              : `${metadata.channels === 1 ? "mono" : "stereo"} ${metadata.sampleRate} Hz · ${
                seconds(metadata.sourceFrames, metadata.sampleRate)} s`}
          </dd>
        </div>
        <div>
          <dt>Selection</dt>
          <dd>
            {metadata === null || selection === null
              ? "—"
              : `${seconds(selection.start, metadata.sampleRate)} – ${
                seconds(selection.end, metadata.sampleRate)} s`}
          </dd>
        </div>
      </dl>
      <svg className="sample-overview-waveform" viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="none" role="img"
        aria-label={metadata === null ? "No Sample waveform" : "Whole Sample waveform with the trim selection"}>
        {bars.map((bar, index) => (
          <rect key={index} className="sample-overview-peak" x={bar.x} width={bar.width}
            y={(HEIGHT - bar.height) / 2} height={bar.height} />
        ))}
        {selection === null || frames === 0 ? null : (
          <>
            <rect className="sample-overview-outside" data-testid="sample-overview-outside"
              x={0} y={0} width={x(selection.start)} height={HEIGHT} />
            <rect className="sample-overview-outside" x={x(selection.end)} y={0}
              width={WIDTH - x(selection.end)} height={HEIGHT} />
            <line className="sample-overview-edge" x1={x(selection.start)} x2={x(selection.start)}
              y1={0} y2={HEIGHT} />
            <line className="sample-overview-edge" x1={x(selection.end)} x2={x(selection.end)}
              y1={0} y2={HEIGHT} />
          </>
        )}
      </svg>
    </div>
  );
}
