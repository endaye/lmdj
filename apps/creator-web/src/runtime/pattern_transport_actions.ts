import type {
  PatternTransportRequest,
  PatternTransportStatus,
  PatternTransportTicket,
} from "@lmdj/web-runtime-platform/runtime_types";

// The Creator consumes only the global Pattern transport surface: intents go
// in, projections come out. The runtime coordinator owns the journal, the
// audio effect and every retry of the same operation.
export interface CreatorPatternTransportSession {
  requestPatternTransport(
    request: PatternTransportRequest,
  ): Promise<PatternTransportTicket>;
  inspectPatternTransport(sessionId: string): Promise<PatternTransportStatus>;
}

export function isPatternTransportSession(
  value: unknown,
): value is CreatorPatternTransportSession {
  const session = value as Partial<CreatorPatternTransportSession> | null;
  return session !== null && typeof session === "object" &&
    typeof session.requestPatternTransport === "function" &&
    typeof session.inspectPatternTransport === "function";
}

export async function requestPatternTransportJourney(
  session: CreatorPatternTransportSession,
  request: PatternTransportRequest,
): Promise<PatternTransportTicket> {
  return session.requestPatternTransport(request);
}

export async function inspectPatternTransportJourney(
  session: CreatorPatternTransportSession,
  sessionId: string,
): Promise<PatternTransportStatus> {
  return session.inspectPatternTransport(sessionId);
}

// The only retry the Creator may perform: the retained command goes out
// verbatim (the runtime replays a same-identity request instead of applying a
// second effect) and authority is re-inspected afterwards. A retry is never a
// new command and never the inverse toggle.
export async function reconcilePatternTransportJourney(
  session: CreatorPatternTransportSession,
  retained: PatternTransportRequest,
): Promise<{ticket: PatternTransportTicket; status: PatternTransportStatus}> {
  const ticket = await session.requestPatternTransport(retained);
  const status = await session.inspectPatternTransport(retained.sessionId);
  return Object.freeze({ticket, status});
}
