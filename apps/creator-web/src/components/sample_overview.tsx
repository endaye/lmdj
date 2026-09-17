import type {CreatorState} from "../state/creator_state";
import {padAddress} from "../state/view_model";

interface SampleOverviewProps {
  state: CreatorState;
}

export function SampleOverview({state}: SampleOverviewProps) {
  const slot = state.sample.selectedSlot;
  const metadata = state.sample.inspect?.metadata ?? null;
  return (
    <div className="sample-overview" data-testid="sample-overview">
      <dl className="overview-facts">
        <div>
          <dt>Pad</dt>
          <dd>{slot === null ? "—" : padAddress({slot, assetId: null})}</dd>
        </div>
        <div>
          <dt>Format</dt>
          <dd>
            {metadata === null
              ? "—"
              : `${metadata.channels === 1 ? "mono" : "stereo"} ${metadata.sampleRate} Hz`}
          </dd>
        </div>
        <div>
          <dt>Frames</dt>
          <dd>{metadata?.sourceFrames ?? "—"}</dd>
        </div>
      </dl>
      <p className="overview-grid-caption">
        Overview waveform is not an editor. Trim, audition, assign and capture
        stay in the touch workspace.
      </p>
    </div>
  );
}
