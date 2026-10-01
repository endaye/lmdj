// Cooperative hand-over of an open Project between Creator tabs (#1679).
//
// The writer lease is an exclusive OPFS sync access handle that no other
// context can take away, so a second tab cannot steal it. Instead it asks the
// tab that holds the Project to release it through that tab's normal close
// path, then opens the Project itself. The exchange is Creator-internal and is
// not a Contract: request -> accepted | refused, then released {clean}.

export const PROJECT_TAKEOVER_CHANNEL = "lmdj.creator.project-takeover.v1";

// A holder answers at once when it is alive and listening; releasing runs its
// shutdown barriers and a bounded host.close, so it gets a longer bound.
export const TAKEOVER_ANSWER_TIMEOUT_MS = 2_000;
export const TAKEOVER_RELEASE_TIMEOUT_MS = 20_000;

export type TakeoverOutcome =
  | "released"
  | "release-failed"
  | "refused"
  | "unanswered"
  | "cancelled";

// What a holder decides when asked. Accepting commits it to releasing; the
// promise resolves to whether its Runtime closed cleanly.
export type TakeoverDecision =
  | {readonly accepted: false}
  | {readonly accepted: true; readonly released: Promise<boolean>};

export interface TakeoverPort {
  postMessage(message: unknown): void;
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  removeEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  close(): void;
}

export interface ProjectTakeoverCoordinator {
  // Answer requests for this Project until the returned function is called.
  // A release already accepted still reports its result afterwards.
  serve(projectId: string, decide: () => TakeoverDecision): () => void;
  request(projectId: string, options?: {signal?: AbortSignal}): Promise<TakeoverOutcome>;
  close(): void;
}

interface CoordinatorOptions {
  port: TakeoverPort;
  randomId?: () => string;
  setTimeout?: (callback: () => void, ms: number) => unknown;
  clearTimeout?: (handle: unknown) => void;
  answerTimeoutMs?: number;
  releaseTimeoutMs?: number;
}

type TakeoverMessage =
  | {kind: "request"; requestId: string; projectId: string}
  | {kind: "accepted" | "refused"; requestId: string}
  | {kind: "released"; requestId: string; clean: boolean};

const ID = /^[A-Za-z0-9._:-]{1,128}$/;

function parseMessage(value: unknown): TakeoverMessage | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  const message = value as Record<string, unknown>;
  if (message.schema !== PROJECT_TAKEOVER_CHANNEL) return null;
  const {kind, requestId} = message;
  if (typeof requestId !== "string" || !ID.test(requestId)) return null;
  const keys = Object.keys(message).sort().join(",");
  switch (kind) {
    case "request":
      return keys === "kind,projectId,requestId,schema" &&
        typeof message.projectId === "string" && ID.test(message.projectId)
        ? {kind, requestId, projectId: message.projectId}
        : null;
    case "accepted":
    case "refused":
      return keys === "kind,requestId,schema" ? {kind, requestId} : null;
    case "released":
      return keys === "clean,kind,requestId,schema" && typeof message.clean === "boolean"
        ? {kind, requestId, clean: message.clean}
        : null;
    default:
      return null;
  }
}

export function createProjectTakeoverCoordinator({
  port,
  randomId = () => crypto.randomUUID(),
  setTimeout: schedule = (callback, ms) => globalThis.setTimeout(callback, ms),
  clearTimeout: cancel = (handle) => globalThis.clearTimeout(handle as number),
  answerTimeoutMs = TAKEOVER_ANSWER_TIMEOUT_MS,
  releaseTimeoutMs = TAKEOVER_RELEASE_TIMEOUT_MS,
}: CoordinatorOptions): ProjectTakeoverCoordinator {
  const listeners = new Set<(message: TakeoverMessage) => void>();
  let closed = false;
  const onMessage = (event: MessageEvent) => {
    const message = parseMessage(event.data);
    if (message === null) return;
    for (const listener of [...listeners]) listener(message);
  };
  port.addEventListener("message", onMessage);
  const post = (message: TakeoverMessage) => {
    if (!closed) port.postMessage({schema: PROJECT_TAKEOVER_CHANNEL, ...message});
  };

  return {
    serve(projectId, decide) {
      // One hand-over per registration: once accepted, this tab is no longer
      // the holder, so later requests are refused rather than answered twice.
      let handling = false;
      const listener = (message: TakeoverMessage) => {
        if (message.kind !== "request" || message.projectId !== projectId) return;
        if (handling) {
          post({kind: "refused", requestId: message.requestId});
          return;
        }
        let decision: TakeoverDecision;
        try {
          decision = decide();
        } catch {
          decision = {accepted: false};
        }
        if (!decision.accepted) {
          post({kind: "refused", requestId: message.requestId});
          return;
        }
        handling = true;
        post({kind: "accepted", requestId: message.requestId});
        void decision.released.then(
          (clean) => post({kind: "released", requestId: message.requestId, clean}),
          () => post({kind: "released", requestId: message.requestId, clean: false}),
        );
      };
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },

    request(projectId, {signal} = {}) {
      if (signal?.aborted) return Promise.resolve("cancelled");
      const requestId = randomId();
      return new Promise<TakeoverOutcome>((resolve) => {
        let timer: unknown = null;
        let settled = false;
        const finish = (outcome: TakeoverOutcome) => {
          if (settled) return;
          settled = true;
          if (timer !== null) cancel(timer);
          listeners.delete(listener);
          signal?.removeEventListener("abort", onAbort);
          resolve(outcome);
        };
        const wait = (ms: number, outcome: TakeoverOutcome) => {
          if (timer !== null) cancel(timer);
          timer = schedule(() => finish(outcome), ms);
        };
        const listener = (message: TakeoverMessage) => {
          if (message.requestId !== requestId) return;
          if (message.kind === "accepted") {
            wait(releaseTimeoutMs, "release-failed");
          } else if (message.kind === "refused") {
            finish("refused");
          } else if (message.kind === "released") {
            finish(message.clean ? "released" : "release-failed");
          }
        };
        const onAbort = () => finish("cancelled");
        listeners.add(listener);
        signal?.addEventListener("abort", onAbort);
        wait(answerTimeoutMs, "unanswered");
        post({kind: "request", requestId, projectId});
      });
    },

    close() {
      if (closed) return;
      closed = true;
      listeners.clear();
      port.removeEventListener("message", onMessage);
      port.close();
    },
  };
}

// The browser coordinator, or null where BroadcastChannel is unavailable; a
// Creator without it keeps the plain busy refusal and Retry.
export function createBrowserProjectTakeover(): ProjectTakeoverCoordinator | null {
  if (typeof BroadcastChannel !== "function") return null;
  return createProjectTakeoverCoordinator({
    port: new BroadcastChannel(PROJECT_TAKEOVER_CHANNEL),
  });
}
