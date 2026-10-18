import type {
  PatternCountInCancel,
  PatternCountInRequest,
  PatternCountInStatus,
  PatternCountInTicket,
  PatternTransportIntent,
  PatternTransportRuntimeSession,
  PatternTransportStatus,
} from "@lmdj/web-runtime-platform/runtime_types";

export type CreatorCountInSession = Pick<PatternTransportRuntimeSession,
  "queryPatternCountInCapabilities" | "setCountInMetronome" |
  "requestPatternCountIn" | "inspectPatternCountIn" | "cancelPatternCountIn" |
  "inspectPatternTransport"
> & {diagnostics(): {state: string}};

export function isCountInSession(value: unknown): value is CreatorCountInSession {
  if (value === null || typeof value !== "object") return false;
  return ["queryPatternCountInCapabilities", "setCountInMetronome",
    "requestPatternCountIn", "inspectPatternCountIn", "cancelPatternCountIn",
    "inspectPatternTransport", "diagnostics"].every((key) =>
    typeof (value as Record<string, unknown>)[key] === "function");
}

export interface CountInState {
  readonly active: boolean;
  readonly phase: "idle" | "preparing" | "counting" | "recording" | "cancelling" | "settling";
  readonly recording: boolean;
  readonly ticket: PatternCountInTicket | null;
  readonly status: PatternCountInStatus | null;
  // Retained after Record-off: JS must never replay Native's original S beat.
  readonly nativeDownbeatFrame: number | null;
  readonly errorCode: string | null;
  readonly errorMessage: string | null;
}

export const initialCountInState: CountInState = Object.freeze({
  active: false, phase: "idle", recording: false, ticket: null, status: null,
  nativeDownbeatFrame: null, errorCode: null, errorMessage: null,
});

// Selection can join an opened recording without retiring its original caller.
// Applied changes the lamp before durable opening completes, so phase alone is
// insufficient. A cancellation/error closes this gate synchronously.
export function countInLocksPatternSelection(state: CountInState): boolean {
  if (!state.active) return false;
  const status = state.status;
  return state.phase !== "recording" || !state.recording || state.errorCode !== null ||
    status === null || status.error !== null || status.openingPending ||
    !status.openingComplete || status.startReceipt?.result !== "applied" ||
    status.cancelReceipt !== null;
}

const ticketMatches = (a: PatternCountInTicket | null, b: PatternCountInTicket) =>
  a !== null && a.sessionId === b.sessionId && a.commandId === b.commandId &&
  a.runtimeGeneration === b.runtimeGeneration && a.frameEpoch === b.frameEpoch &&
  a.scheduleSerial === b.scheduleSerial;

const failure = (code: string, message: string) => Object.assign(new Error(message), {code});
const errorCode = (error: unknown): string =>
  error !== null && typeof error === "object" && "code" in error &&
    typeof error.code === "string" ? error.code : "INTERNAL_ERROR";

interface Owner {
  ticket: PatternCountInTicket | null;
  request: PatternCountInRequest | null;
  cancel: PatternCountInCancel | null;
  cancelIntent: PatternTransportIntent | null;
  cancelInFlight: boolean;
  capabilityReady: boolean;
  observing: boolean;
  projecting: boolean;
  consuming: boolean;
}

// The public SDK owns native schedules, durable input and lifecycle retirement.
// This Host controller owns only the exact original caller and its readout.
export function createCountInController(options: Readonly<{
  session: CreatorCountInSession;
  sessionId: string;
  projectId: string;
  metronomeEnabled(): boolean;
  onTransport(status: PatternTransportStatus): void;
  onError(error: unknown): void;
}>) {
  const {session} = options;
  let state = initialCountInState;
  let owner: Owner | null = null;
  let disposed = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const listeners = new Set<() => void>();
  const owns = (candidate: Owner) => !disposed && owner === candidate;
  const publish = (change: Partial<CountInState>) => {
    if (disposed) return;
    state = Object.freeze({...state, ...change});
    for (const listener of listeners) listener();
  };
  const report = (error: unknown) => {
    if (disposed) return;
    const code = errorCode(error);
    const message = error instanceof Error ? error.message :
      error !== null && typeof error === "object" && "message" in error &&
        typeof error.message === "string" ? error.message : "Count-in could not finish.";
    if (state.errorCode !== code || state.errorMessage !== message) {
      publish({errorCode: code, errorMessage: message});
      options.onError(error);
    }
  };
  const finish = (candidate: Owner) => {
    if (!owns(candidate)) return;
    owner = null;
    if (timer !== null) clearTimeout(timer);
    timer = null;
    publish({active: false, phase: "idle", recording: false, ticket: null});
  };
  const accept = (candidate: Owner, status: PatternCountInStatus) => {
    if (!owns(candidate) || candidate.ticket === null) return;
    if (!ticketMatches(status.ticket, candidate.ticket)) {
      throw failure("HOST_PROTOCOL_MISMATCH", "Count-in observation belongs to another request.");
    }
    const applied = status.startReceipt?.result === "applied";
    const closed = status.cancelReceipt !== null && status.cancelReceipt.result !== "refused";
    publish({status, recording: applied && !closed,
      nativeDownbeatFrame: applied ? status.startReceipt!.effectiveFrame : state.nativeDownbeatFrame,
      phase: closed || (status.startReceipt !== null && !applied) ? "settling"
        : candidate.cancelIntent !== null ? "cancelling"
        : applied ? "recording" : status.countIn?.startFrame != null ? "counting" : "preparing",
    });
    if (status.error !== null) report(status.error);
  };
  const refreshTransport = async (candidate: Owner) => {
    const status = await session.inspectPatternTransport(options.sessionId);
    if (owns(candidate)) options.onTransport(status);
  };
  const refreshProjection = (candidate: Owner) => {
    if (!owns(candidate) || candidate.projecting || state.status?.error != null ||
        session.diagnostics().state !== "running") return;
    candidate.projecting = true;
    // Ordinary SDK queries can wait behind lifecycle work that itself needs
    // this caller's consume. Keep that queue outside the retained ticket lane.
    void refreshTransport(candidate).catch((error) => {
      if (owns(candidate)) report(error);
    }).finally(() => {candidate.projecting = false;});
  };
  const consumeIfReady = async (candidate: Owner) => {
    if (!owns(candidate) || candidate.ticket === null || candidate.consuming) return;
    const status = state.status;
    if (status === null || status.openingPending) return;
    if (status.error === null) {
      if (status.startReceipt === null ||
          (candidate.cancelIntent !== null && status.cancelReceipt === null)) return;
      if (status.startReceipt.result === "applied" &&
          (status.cancelReceipt?.result !== "applied" || !status.openingComplete)) return;
    }
    // A failed owner may have no genuine e2 F. Error permits an attempt, not
    // retirement: the Host still gates on its actual physical/I/O failure ACK.
    candidate.consuming = true;
    try {
      // A terminal-looking DTO is not a physical/input consumer ACK. The Host
      // may still refuse while a Pad release or durable closure is retained.
      const consumed = await session.inspectPatternCountIn(candidate.ticket, true);
      if (!owns(candidate)) return;
      accept(candidate, consumed);
      try {
        await refreshTransport(candidate);
      } catch (error) {
        if (owns(candidate) && consumed.error === null) report(error);
      } finally {
        // The positive consumer ACK already retired this caller. An unrelated
        // projection failure cannot resurrect it or submit a second consume.
        finish(candidate);
      }
    } catch (error) {
      if (owns(candidate) && errorCode(error) !== "HOST_STATE_INVALID") report(error);
    } finally {
      candidate.consuming = false;
    }
  };
  const schedule = () => {
    if (disposed || owner === null || timer !== null) return;
    timer = setTimeout(() => {
      timer = null;
      void observe();
    }, 250);
  };
  const observe = async () => {
    const candidate = owner;
    if (disposed || candidate === null || candidate.ticket === null || candidate.observing) return;
    candidate.observing = true;
    try {
      const status = await session.inspectPatternCountIn(candidate.ticket);
      if (!owns(candidate)) return;
      accept(candidate, status);
      await consumeIfReady(candidate);
      refreshProjection(candidate);
    } catch (error) {
      if (owns(candidate)) report(error);
    } finally {
      candidate.observing = false;
      if (owns(candidate)) schedule();
    }
  };
  const sendCancel = async (candidate: Owner) => {
    if (!owns(candidate) || candidate.ticket === null || candidate.request === null ||
        candidate.cancelIntent === null || candidate.cancelInFlight) return;
    candidate.cancel ??= Object.freeze({
      ticket: candidate.ticket, projectId: options.projectId,
      commandId: crypto.randomUUID(), intent: candidate.cancelIntent,
      expectedEpoch: (BigInt(candidate.request.expectedEpoch) + 1n).toString(),
    });
    candidate.cancelInFlight = true;
    try {
      const admission = await session.cancelPatternCountIn(candidate.cancel);
      if (!owns(candidate)) return;
      if (!ticketMatches(admission.ticket, candidate.ticket)) {
        throw failure("HOST_PROTOCOL_MISMATCH", "Count-in cancellation belongs to another request.");
      }
      accept(candidate, admission.status);
      await consumeIfReady(candidate);
      refreshProjection(candidate);
    } catch (error) {
      if (owns(candidate)) report(error);
    } finally {
      candidate.cancelInFlight = false;
      if (owns(candidate)) schedule();
    }
  };

  return Object.freeze({
    getState: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {listeners.delete(listener);};
    },
    async start(bars: 1 | 2, expectedRevision: number) {
      if (disposed || owner !== null) return;
      const candidate: Owner = {ticket: null, request: null, cancel: null,
        cancelIntent: null, cancelInFlight: false, capabilityReady: false,
        observing: false, projecting: false, consuming: false};
      owner = candidate;
      publish({...initialCountInState, active: true, phase: "preparing"});
      try {
        const capability = await session.queryPatternCountInCapabilities();
        if (!owns(candidate)) return;
        if (!capability.supported || !capability.negotiated || !capability.outputReady ||
            capability.runtimeGeneration === null || capability.frameEpoch === null ||
            capability.nextSerial === null) {
          throw failure("UNSUPPORTED_AUDIO", "Count-in is unavailable on this audio output. Your setting is kept.");
        }
        const transport = await session.inspectPatternTransport(options.sessionId);
        if (!owns(candidate)) return;
        if (transport.playing || transport.recording ||
            (transport.engaged && transport.phase !== "idle") ||
            !Number.isSafeInteger(transport.transportEpoch)) {
          throw failure("HOST_STATE_INVALID", "Wait for the Pattern transport to stop before count-in.");
        }
        options.onTransport(transport);
        candidate.capabilityReady = true;
        session.setCountInMetronome(options.metronomeEnabled());
        const request: PatternCountInRequest = Object.freeze({
          sessionId: options.sessionId, projectId: options.projectId,
          commandId: crypto.randomUUID(), runtimeGeneration: capability.runtimeGeneration,
          frameEpoch: capability.frameEpoch, scheduleSerial: capability.nextSerial,
          expectedEpoch: (BigInt(transport.transportEpoch) + 1n).toString(), bars, expectedRevision,
        });
        candidate.request = request;
        candidate.ticket = Object.freeze({sessionId: request.sessionId,
          commandId: request.commandId, runtimeGeneration: request.runtimeGeneration,
          frameEpoch: request.frameEpoch, scheduleSerial: request.scheduleSerial});
        publish({ticket: candidate.ticket});
      } catch (error) {
        if (owns(candidate)) {report(error); finish(candidate);}
        return;
      }
      try {
        const admission = await session.requestPatternCountIn(candidate.request!);
        if (!owns(candidate)) return;
        if (!ticketMatches(admission.ticket, candidate.ticket!)) {
          throw failure("HOST_PROTOCOL_MISMATCH", "Count-in admission belongs to another request.");
        }
        accept(candidate, admission.status);
      } catch (error) {
        if (!owns(candidate)) return;
        report(error);
        // SDK unknown-submission failures seal the Session before rejection
        // and retain their original caller privately. A known pre-effect
        // refusal leaves it running (covered by the SDK's pending:false test).
        // Never infer never-accepted from HOST_STATE_INVALID or elapsed time.
        if (session.diagnostics().state === "running" && state.status === null &&
            errorCode(error) !== "HOST_PROTOCOL_MISMATCH") finish(candidate);
        else schedule();
        return;
      }
      if (candidate.cancelIntent !== null) await sendCancel(candidate);
      else await observe();
    },
    async cancel(intent: PatternTransportIntent) {
      const candidate = owner;
      // A terminal receipt can already have been consumed while the final
      // ordinary projection is still in flight. Its original cancel identity
      // cannot be submitted again or turned into another musical command.
      if (disposed || candidate === null || state.phase === "settling") return;
      candidate.cancelIntent ??= intent;
      publish({phase: "cancelling"});
      // A press before capability/admission settles is retained and sent once
      // the original request has actually returned; it cannot become a start.
      if (candidate.ticket !== null && state.status !== null) await sendCancel(candidate);
    },
    setMetronome(enabled: boolean) {
      if (!disposed && owner?.capabilityReady) {
        try {session.setCountInMetronome(enabled);}
        catch (error) {report(error); throw error;}
      }
    },
    clearHandoff() {
      if (owner === null && state.nativeDownbeatFrame !== null) publish({nativeDownbeatFrame: null});
    },
    observe,
    dispose() {
      disposed = true;
      if (timer !== null) clearTimeout(timer);
      timer = null;
      listeners.clear();
      // Do not manufacture a consume or release. Session.close/replacement
      // already owns its retained SDK callers and positive physical receipts.
    },
  });
}

export type CountInController = ReturnType<typeof createCountInController>;

// Display the current beat until the next actual marker. Native places cues
// at rounded quarter-Bar offsets, which can differ from the ordinary PPQ grid.
export function countInBeatsRemaining(status: PatternCountInStatus | null, frame: number): number | null {
  const count = status?.countIn;
  if (count?.countInFrame == null || count.startFrame === null ||
      count.barFrames === null || count.bpm === null || !Number.isFinite(frame)) return null;
  if (frame >= count.startFrame) return 0; // Still not an Applied receipt.
  let currentBeat = 0;
  for (let bar = 0; bar < count.bars; bar += 1) {
    for (let beat = 0; beat < 4; beat += 1) {
      const marker = count.countInFrame + bar * count.barFrames + Math.floor((beat * count.barFrames + 2) / 4);
      if (frame >= marker) currentBeat = bar * 4 + beat;
    }
  }
  return count.bars * 4 - currentBeat;
}
