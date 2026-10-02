import {expect, test, vi} from "vitest";

import {
  PROJECT_TAKEOVER_CHANNEL,
  createProjectTakeoverCoordinator,
  type TakeoverDecision,
  type TakeoverPort,
} from "../src/runtime/project_takeover";

// An in-memory BroadcastChannel: a message reaches every other port on the
// bus, never the sender, asynchronously.
function bus() {
  const ports = new Set<FakePort>();
  class FakePort implements TakeoverPort {
    private readonly listeners = new Set<(event: MessageEvent) => void>();
    readonly sent: unknown[] = [];
    constructor() { ports.add(this); }
    postMessage(message: unknown) {
      this.sent.push(message);
      for (const port of ports) {
        if (port !== this) port.deliver(structuredClone(message));
      }
    }
    deliver(data: unknown) {
      queueMicrotask(() => {
        for (const listener of [...this.listeners]) {
          listener(new MessageEvent("message", {data}));
        }
      });
    }
    addEventListener(_type: "message", listener: (event: MessageEvent) => void) {
      this.listeners.add(listener);
    }
    removeEventListener(_type: "message", listener: (event: MessageEvent) => void) {
      this.listeners.delete(listener);
    }
    close() { ports.delete(this); }
  }
  return {port: () => new FakePort()};
}

function pair(options: {answerTimeoutMs?: number; releaseTimeoutMs?: number} = {}) {
  const channel = bus();
  let next = 0;
  const holderPort = channel.port();
  const requesterPort = channel.port();
  const holder = createProjectTakeoverCoordinator({port: holderPort, ...options});
  const requester = createProjectTakeoverCoordinator({
    port: requesterPort,
    randomId: () => `request-${++next}`,
    ...options,
  });
  return {channel, holder, requester, holderPort, requesterPort};
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return {promise, resolve, reject};
}

test("an accepting holder releases and the requester observes a clean release", async () => {
  const {holder, requester, holderPort} = pair();
  const released = deferred<boolean>();
  const decide = vi.fn((): TakeoverDecision => ({accepted: true, released: released.promise}));
  holder.serve("project-a", decide);

  const outcome = requester.request("project-a");
  await vi.waitFor(() => expect(decide).toHaveBeenCalledTimes(1));
  released.resolve(true);

  await expect(outcome).resolves.toBe("released");
  expect(holderPort.sent).toEqual([
    {schema: PROJECT_TAKEOVER_CHANNEL, kind: "accepted", requestId: "request-1"},
    {schema: PROJECT_TAKEOVER_CHANNEL, kind: "released", requestId: "request-1", clean: true},
  ]);
});

test("an unclean holder close is reported as release-failed", async () => {
  const {holder, requester} = pair();
  holder.serve("project-a", () => ({accepted: true, released: Promise.resolve(false)}));
  await expect(requester.request("project-a")).resolves.toBe("release-failed");
});

test("a rejected release promise is reported as an unclean release", async () => {
  const {holder, requester} = pair();
  holder.serve("project-a", () => ({accepted: true, released: Promise.reject(new Error("x"))}));
  await expect(requester.request("project-a")).resolves.toBe("release-failed");
});

test("a refusing holder answers refused and is asked to release nothing", async () => {
  const {holder, requester, holderPort} = pair();
  holder.serve("project-a", () => ({accepted: false}));
  await expect(requester.request("project-a")).resolves.toBe("refused");
  expect(holderPort.sent).toEqual([
    {schema: PROJECT_TAKEOVER_CHANNEL, kind: "refused", requestId: "request-1"},
  ]);
});

test("a throwing decision is a refusal", async () => {
  const {holder, requester} = pair();
  holder.serve("project-a", () => { throw new Error("guard failed"); });
  await expect(requester.request("project-a")).resolves.toBe("refused");
});

test("a holder of another Project does not answer", async () => {
  vi.useFakeTimers();
  try {
    const {holder, requester} = pair();
    const decide = vi.fn((): TakeoverDecision => ({accepted: false}));
    holder.serve("project-b", decide);
    const outcome = requester.request("project-a");
    await vi.advanceTimersByTimeAsync(2_000);
    await expect(outcome).resolves.toBe("unanswered");
    expect(decide).not.toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});

test("no holder is unanswered after the answer bound", async () => {
  vi.useFakeTimers();
  try {
    const {requester} = pair();
    let outcome: string | null = null;
    void requester.request("project-a").then((value) => { outcome = value; });
    await vi.advanceTimersByTimeAsync(1_999);
    expect(outcome).toBeNull();
    await vi.advanceTimersByTimeAsync(1);
    expect(outcome).toBe("unanswered");
  } finally {
    vi.useRealTimers();
  }
});

test("an accepted release that never finishes is release-failed after its bound", async () => {
  vi.useFakeTimers();
  try {
    const {holder, requester} = pair();
    holder.serve("project-a", () => ({accepted: true, released: new Promise<boolean>(() => {})}));
    let outcome: string | null = null;
    void requester.request("project-a").then((value) => { outcome = value; });
    // Acceptance replaces the short answer bound with the release bound.
    await vi.advanceTimersByTimeAsync(19_999);
    expect(outcome).toBeNull();
    await vi.advanceTimersByTimeAsync(1);
    expect(outcome).toBe("release-failed");
  } finally {
    vi.useRealTimers();
  }
});

test("cancelling before an answer resolves cancelled and ignores the late answer", async () => {
  const {holder, requester} = pair();
  const released = deferred<boolean>();
  const decided = deferred<void>();
  holder.serve("project-a", () => {
    decided.resolve();
    return {accepted: true, released: released.promise};
  });
  const abort = new AbortController();
  const outcome = requester.request("project-a", {signal: abort.signal});
  abort.abort();
  await expect(outcome).resolves.toBe("cancelled");
  // The holder still received the request and completes the release it accepted.
  await decided.promise;
  released.resolve(true);
});

test("an already aborted signal sends no request", async () => {
  const {requester, requesterPort} = pair();
  const abort = new AbortController();
  abort.abort();
  await expect(requester.request("project-a", {signal: abort.signal})).resolves.toBe("cancelled");
  expect(requesterPort.sent).toEqual([]);
});

test("a holder handles one hand-over and refuses a concurrent second request", async () => {
  const channel = bus();
  const holder = createProjectTakeoverCoordinator({port: channel.port()});
  const first = createProjectTakeoverCoordinator({port: channel.port(), randomId: () => "first"});
  const second = createProjectTakeoverCoordinator({port: channel.port(), randomId: () => "second"});
  const released = deferred<boolean>();
  const decide = vi.fn((): TakeoverDecision => ({accepted: true, released: released.promise}));
  holder.serve("project-a", decide);

  const firstOutcome = first.request("project-a");
  await vi.waitFor(() => expect(decide).toHaveBeenCalledTimes(1));
  await expect(second.request("project-a")).resolves.toBe("refused");
  released.resolve(true);
  await expect(firstOutcome).resolves.toBe("released");
  expect(decide).toHaveBeenCalledTimes(1);
});

test("an accepted release still reports after the holder stops serving", async () => {
  const {holder, requester} = pair();
  const released = deferred<boolean>();
  const decided = deferred<void>();
  const stop = holder.serve("project-a", () => {
    decided.resolve();
    return {accepted: true, released: released.promise};
  });
  const outcome = requester.request("project-a");
  await decided.promise;
  stop();
  released.resolve(true);
  await expect(outcome).resolves.toBe("released");
});

test("a stopped holder no longer answers", async () => {
  vi.useFakeTimers();
  try {
    const {holder, requester} = pair();
    const decide = vi.fn((): TakeoverDecision => ({accepted: false}));
    holder.serve("project-a", decide)();
    const outcome = requester.request("project-a");
    await vi.advanceTimersByTimeAsync(2_000);
    await expect(outcome).resolves.toBe("unanswered");
    expect(decide).not.toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});

test.each([
  ["another schema", {schema: "other.v1", kind: "released", requestId: "request-1", clean: true}],
  ["an extra field", {schema: PROJECT_TAKEOVER_CHANNEL, kind: "released", requestId: "request-1", clean: true, x: 1}],
  ["a non-boolean clean", {schema: PROJECT_TAKEOVER_CHANNEL, kind: "released", requestId: "request-1", clean: "yes"}],
  ["another request id", {schema: PROJECT_TAKEOVER_CHANNEL, kind: "released", requestId: "request-2", clean: true}],
  ["an unknown kind", {schema: PROJECT_TAKEOVER_CHANNEL, kind: "granted", requestId: "request-1"}],
  ["a non-object", "released"],
])("ignores %s", async (_name, message) => {
  vi.useFakeTimers();
  try {
    const {channel, requester} = pair();
    const stranger = channel.port();
    let outcome: string | null = null;
    void requester.request("project-a").then((value) => { outcome = value; });
    stranger.postMessage(message);
    await vi.advanceTimersByTimeAsync(1_999);
    expect(outcome).toBeNull();
    await vi.advanceTimersByTimeAsync(1);
    expect(outcome).toBe("unanswered");
  } finally {
    vi.useRealTimers();
  }
});

test("a malformed request reaches no holder decision", async () => {
  const {channel, holder} = pair();
  const decide = vi.fn((): TakeoverDecision => ({accepted: false}));
  holder.serve("project-a", decide);
  const stranger = channel.port();
  stranger.postMessage({schema: PROJECT_TAKEOVER_CHANNEL, kind: "request", requestId: "r", projectId: "project a/.."});
  stranger.postMessage({schema: PROJECT_TAKEOVER_CHANNEL, kind: "request", requestId: "r"});
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(decide).not.toHaveBeenCalled();
});

test("close stops answering and closes the port", async () => {
  vi.useFakeTimers();
  try {
    const {holder, requester} = pair();
    const decide = vi.fn((): TakeoverDecision => ({accepted: false}));
    holder.serve("project-a", decide);
    holder.close();
    const outcome = requester.request("project-a");
    await vi.advanceTimersByTimeAsync(2_000);
    await expect(outcome).resolves.toBe("unanswered");
    expect(decide).not.toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});
