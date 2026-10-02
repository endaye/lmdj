import type {
  PatternEventKeyRequest,
  PatternEventRequest,
} from "@lmdj/web-runtime-platform/runtime_types";
import type {
  CreatorSequenceRuntimeSession,
  PatternEventsEditMutation,
  SequenceMutation,
  SequenceRecoveryCandidate,
  SequenceStatus,
} from "./runtime_types";

export function isSequenceSession(value: unknown): value is CreatorSequenceRuntimeSession {
  const session = value as Partial<CreatorSequenceRuntimeSession> | null;
  return session !== null && typeof session === "object" &&
    typeof session.beginSequence === "function" &&
    typeof session.flushSequence === "function" &&
    typeof session.createPattern === "function" &&
    typeof session.updateSequenceSettings === "function" &&
    typeof session.editPatternEvents === "function" &&
    typeof session.disarmSequenceCapture === "function" &&
    typeof session.stopSequence === "function" &&
    typeof session.requestPatternSwitch === "function" &&
    typeof session.querySequenceStatus === "function" &&
    typeof session.listSequenceRecovery === "function" &&
    typeof session.applySequenceRecovery === "function" &&
    typeof session.discardSequenceRecovery === "function" &&
    typeof session.subscribeSequenceBarBoundary === "function";
}

export function reconcileSequenceAuthoringRevision(
  current: number,
  projectRevision: number,
  journalExpectedRevision: number,
): number {
  return Math.max(current, projectRevision, journalExpectedRevision);
}

export async function beginSequenceJourney(
  session: CreatorSequenceRuntimeSession,
  request: {
    sessionId: string;
    patternId: string;
    expectedRevision: number;
    armedCaptureSlot?: number | null;
  },
): Promise<SequenceMutation> {
  return session.beginSequence(request);
}

export async function stopSequenceJourney(
  session: CreatorSequenceRuntimeSession,
  sessionId: string,
  commandId: string,
): Promise<SequenceMutation> {
  return session.stopSequence({sessionId, commandId});
}

export async function disarmSequenceCaptureJourney(
  session: CreatorSequenceRuntimeSession,
  sessionId: string,
  slot: number,
): Promise<boolean> {
  return session.disarmSequenceCapture({sessionId, slot});
}

export async function refreshSequenceJourney(
  session: CreatorSequenceRuntimeSession,
  projectId: string,
): Promise<{status: SequenceStatus; recovery: readonly SequenceRecoveryCandidate[]}> {
  const [status, recovery] = await Promise.all([
    session.querySequenceStatus(projectId),
    session.listSequenceRecovery(projectId),
  ]);
  return Object.freeze({status, recovery});
}

// One grid gesture, committed at gesture end. Slots are flat 0..63, as for
// deletePad and trigger; the Session mints the command identity per call.
export async function editPatternEventsJourney(
  session: CreatorSequenceRuntimeSession,
  request: {
    patternId: string;
    expectedRevision: number;
    remove: readonly PatternEventKeyRequest[];
    put: readonly PatternEventRequest[];
  },
): Promise<Readonly<PatternEventsEditMutation>> {
  return session.editPatternEvents(request);
}
