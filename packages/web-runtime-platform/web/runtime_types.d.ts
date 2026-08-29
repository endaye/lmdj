export type SequenceRecordState =
  | "inactive"
  | "active"
  | "switching"
  | "recoverable";

export interface SequenceStatus {
  readonly state: SequenceRecordState;
  readonly sessionId: string | null;
  readonly patternId: string | null;
  readonly pendingPatternId: string | null;
  readonly expectedRevision: number;
  readonly nextFlushSequence: number;
  readonly pendingEventCount: number;
  readonly effectiveRuntimeFrame: number | null;
}

export interface SequenceMutation extends SequenceStatus {
  readonly committedRevision: number | null;
  readonly replayed: boolean;
  readonly projectRevision: number | null;
}

export interface SequenceTransportAnchor {
  readonly runtimeFrame: number;
  readonly tickNumerator: number;
  readonly bpm: number;
}

export interface SequenceBeginResult extends SequenceMutation {
  readonly transportAnchor: SequenceTransportAnchor;
}

export interface SequenceEventResult extends SequenceMutation {
  readonly runtimeFrame: number;
  readonly inputSequence: number;
}

export interface SequencePatternPublication {
  readonly generation: number;
  readonly activationFrame: number;
}

export interface SequenceFlushResult extends SequenceMutation {
  readonly runtimeFrame: number;
  readonly patternPublication: SequencePatternPublication | null;
}

export interface SequenceSwitchResult extends SequenceMutation {
  readonly patternPublication: SequencePatternPublication;
}

export interface SequenceRecoveryCandidate {
  readonly sessionId: string;
  readonly patternId: string;
  readonly bars: 1 | 2 | 4 | 8;
  readonly reason: string;
  readonly eventCount: number;
}

export interface SequenceRuntimeSession {
  createPattern(request: {
    readonly patternId: string;
    readonly bars: 1 | 2 | 4 | 8;
    readonly expectedRevision: number;
  }): Promise<Readonly<{
    committedRevision: number;
    patternId: string;
    bars: 1 | 2 | 4 | 8;
    replayed: boolean;
    projectRevision: number;
  }>>;
  updateSequenceSettings(request: {
    readonly expectedRevision: number;
    readonly sessionId: string | null;
    readonly bpm: number | null;
    readonly quantizeEnabled: boolean | null;
    readonly swingPercent: number | null;
  }): Promise<Readonly<{
    committedRevision: number;
    bpm: number;
    quantizeEnabled: boolean;
    swingPercent: number;
    replayed: boolean;
    patternPublication: SequencePatternPublication | null;
    projectRevision: number;
  }>>;
  subscribeSequenceBarBoundary(
    listener: (event: Readonly<{
      sessionId: string;
      patternId: string;
      runtimeFrame: number;
      generation: number;
    }>) => void,
  ): () => boolean;
  beginSequence(request: {
    readonly sessionId: string;
    readonly patternId: string;
    readonly expectedRevision: number;
    readonly armedCaptureSlot?: number | null;
  }): Promise<SequenceBeginResult>;
  disarmSequenceCapture(request: {
    readonly sessionId: string;
    readonly slot: number;
  }): Promise<boolean>;
  recordSequenceEvent(request: {
    readonly sessionId: string;
    readonly slot: number;
    readonly velocity: number;
    readonly pressed: boolean;
  }): Promise<SequenceEventResult>;
  flushSequence(request: {
    readonly sessionId: string;
    readonly commandId: string;
  }): Promise<SequenceFlushResult>;
  stopSequence(request: {
    readonly sessionId: string;
    readonly commandId: string;
  }): Promise<SequenceFlushResult>;
  requestPatternSwitch(request: {
    readonly sessionId: string;
    readonly nextPatternId: string;
  }): Promise<SequenceSwitchResult>;
  querySequenceStatus(projectId?: string | null): Promise<SequenceStatus>;
  listSequenceRecovery(
    projectId?: string | null,
  ): Promise<readonly SequenceRecoveryCandidate[]>;
  applySequenceRecovery(request: {
    readonly sessionId: string;
    readonly destinationPatternId: string | null;
  }): Promise<SequenceMutation>;
  discardSequenceRecovery(sessionId: string): Promise<boolean>;
}
