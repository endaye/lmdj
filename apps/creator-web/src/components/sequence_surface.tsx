import type {ProjectView, SequenceRecoveryCandidate} from "../runtime/runtime_types";
import type {SequenceState} from "../state/sequence_state";
import type {PatternTransportState} from "../state/pattern_transport_state";
import {SequenceTouchWorkspace} from "./sequence_touch_workspace";
import {SequenceTransport} from "./sequence_transport";

interface SequenceSurfaceProps {
  project: ProjectView;
  state: SequenceState;
  transport: PatternTransportState;
  ready: boolean;
  onPlayStop(): void;
  onRecord(): void;
  onRefresh(): void;
  onSwitch(patternId: string): void;
  onCreatePattern(bars: 1 | 2 | 4 | 8): void;
  onSettingsChange(changes: Readonly<{
    bpm?: number;
    quantizeEnabled?: boolean;
    swingPercent?: number;
  }>): void;
  onRecover(candidate: SequenceRecoveryCandidate, destinationPatternId: string | null): void;
  onDiscard(candidate: SequenceRecoveryCandidate): void;
}

export function SequenceSurface(props: SequenceSurfaceProps) {
  return (
    <main className="sequence-surface" aria-label="Sequence">
      <SequenceTransport transport={props.transport} ready={props.ready}
        onPlayStop={props.onPlayStop} onRecord={props.onRecord} onRefresh={props.onRefresh} />
      <SequenceTouchWorkspace
        project={props.project}
        state={props.state}
        transport={props.transport}
        showRefresh={false}
        onRefresh={props.onRefresh}
        onSwitch={props.onSwitch}
        onCreatePattern={props.onCreatePattern}
        onSettingsChange={props.onSettingsChange}
        onRecover={props.onRecover}
        onDiscard={props.onDiscard}
      />
    </main>
  );
}
