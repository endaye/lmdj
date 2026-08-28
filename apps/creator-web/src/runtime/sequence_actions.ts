import type {
  CreatorSequenceRuntimeSession,
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
