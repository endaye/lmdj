import type {
  PatternTransportRequest,
  PatternTransportStatus,
  PatternTransportTicket,
  TransportPatternSwitchRequest,
  TransportPatternSwitchResult,
} from "@lmdj/web-runtime-platform/runtime_types";
import {
  reducePatternTransport,
  type PatternTransportState,
} from "../state/pattern_transport_state";

// The Creator consumes only the global Pattern transport surface: intents go
// in, projections come out. The runtime coordinator owns the journal, the
// audio effect and every retry of the same operation.
export interface CreatorPatternTransportSession {
  requestPatternTransport(
    request: PatternTransportRequest,
  ): Promise<PatternTransportTicket>;
  inspectPatternTransport(sessionId: string): Promise<PatternTransportStatus>;
  // #1958 S1: switches the playing transport's Pattern at the engine's next
  // Bar. Every session with this transport surface carries it.
  requestTransportPatternSwitch(
    request: TransportPatternSwitchRequest,
  ): Promise<TransportPatternSwitchResult>;
}

// The request and inspection journeys below use only these two members, so
// they accept any session that carries them.
export type PatternTransportJourneySession = Pick<
  CreatorPatternTransportSession,
  "requestPatternTransport" | "inspectPatternTransport"
>;

export function isPatternTransportSession(
  value: unknown,
): value is CreatorPatternTransportSession {
  const session = value as Partial<CreatorPatternTransportSession> | null;
  return session !== null && typeof session === "object" &&
    typeof session.requestPatternTransport === "function" &&
    typeof session.inspectPatternTransport === "function";
}

export async function requestPatternTransportJourney(
  session: PatternTransportJourneySession,
  request: PatternTransportRequest,
): Promise<PatternTransportTicket> {
  return session.requestPatternTransport(request);
}

export async function inspectPatternTransportJourney(
  session: PatternTransportJourneySession,
  sessionId: string,
): Promise<PatternTransportStatus> {
  return session.inspectPatternTransport(sessionId);
}

export async function observePatternTransportJourney(
  session: PatternTransportJourneySession,
  readCurrent: () => PatternTransportState,
): Promise<{status: PatternTransportStatus; state: PatternTransportState} | null> {
  const owner = readCurrent();
  if (owner.sessionId === null) return null;
  const owns = (state: PatternTransportState) =>
    state.sessionId === owner.sessionId && state.projectId === owner.projectId;
  let status: PatternTransportStatus;
  try {
    status = await inspectPatternTransportJourney(session, owner.sessionId);
  } catch (error) {
    if (!owns(readCurrent())) return null;
    throw error;
  }
  const current = readCurrent();
  if (!owns(current)) return null;
  // A different inspection may have settled a command during this await.
  // Projecting onto the captured state would resurrect its retired identity.
  return {status, state: reducePatternTransport(current, {type: "observed", status})};
}

// The only retry the Creator may perform: the retained command goes out
// verbatim (the runtime replays a same-identity request instead of applying a
// second effect) and authority is re-inspected afterwards. A retry is never a
// new command and never the inverse toggle.
export async function reconcilePatternTransportJourney(
  session: PatternTransportJourneySession,
  retained: PatternTransportRequest,
  readCurrent: () => PatternTransportState,
): Promise<{ticket: PatternTransportTicket; status: PatternTransportStatus} | null> {
  const owns = () => {
    const current = readCurrent();
    return current.sessionId === retained.sessionId &&
      current.projectId === retained.projectId;
  };
  if (!owns()) return null;
  try {
    const ticket = await session.requestPatternTransport(retained);
    if (!owns()) return null;
    const status = await session.inspectPatternTransport(retained.sessionId);
    if (!owns()) return null;
    return Object.freeze({ticket, status});
  } catch (error) {
    if (!owns()) return null;
    throw error;
  }
}
