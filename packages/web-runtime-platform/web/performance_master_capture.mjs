const MAX_BATCH_FRAMES = 4_800;
const STOP_ACK_TIMEOUT_MS = 30_000;
// D0/W1: the start ACK failure timer reuses the 30s stop budget as an
// independent budget; it never extends the stop timer.
const START_ACK_TIMEOUT_MS = 30_000;

// D0/W1: the begin binding binds a capture start to one Core epoch, session
// and begin command; null only for a legacy non-D04 caller.
function validTapBinding(binding) {
  if (binding === null) return true;
  if (binding === undefined || typeof binding !== "object" ||
      Array.isArray(binding)) return false;
  const keys = Object.keys(binding).sort();
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  return keys.length === 3 &&
    keys[0] === "begin_command_id" && keys[1] === "control_epoch" &&
    keys[2] === "session_id" &&
    uuid.test(binding.begin_command_id) &&
    uuid.test(binding.control_epoch) && uuid.test(binding.session_id);
}

function tapBindingEqual(left, right) {
  if (left === null || right === null) return left === right;
  return left.control_epoch === right.control_epoch &&
    left.session_id === right.session_id &&
    left.begin_command_id === right.begin_command_id;
}

function requireSink(sink) {
  if (
    sink === null ||
    typeof sink !== "object" ||
    typeof sink.onBatch !== "function" ||
    typeof sink.onStopped !== "function" ||
    typeof sink.onFailure !== "function"
  ) {
    throw new TypeError("A Performance master capture sink is required");
  }
  return sink;
}

function validChannels(value) {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    value[0] instanceof Float32Array &&
    value[1] instanceof Float32Array &&
    value[0].length > 0 &&
    value[0].length <= MAX_BATCH_FRAMES &&
    value[1].length === value[0].length
  );
}

function validMasterTapEvent(message) {
  if (
    message === null ||
    typeof message !== "object" ||
    !Number.isSafeInteger(message.generation) ||
    message.generation < 0
  ) return false;
  if (message.type === "started") {
    return (
      exactKeys(message, ["binding", "generation", "type"]) &&
      validTapBinding(message.binding)
    );
  }
  if (message.type === "batch") {
    return (
      exactKeys(message, ["channels", "generation", "sequence", "type"]) &&
      Number.isSafeInteger(message.sequence) &&
      message.sequence >= 0 &&
      validChannels(message.channels)
    );
  }
  if (message.type === "stopped") {
    return (
      exactKeys(message, ["finalSequence", "generation", "type"]) &&
      Number.isSafeInteger(message.finalSequence) &&
      message.finalSequence >= 0
    );
  }
  if (message.type === "failed") {
    return (
      exactKeys(message, [
        "droppedFrames", "generation", "reason", "type",
      ]) &&
      message.reason === "post-message-failed" &&
      Number.isSafeInteger(message.droppedFrames) &&
      message.droppedFrames >= 0
    );
  }
  return false;
}

function exactKeys(value, expected) {
  const keys = Object.keys(value).sort();
  return keys.length === expected.length &&
    keys.every((key, index) => key === expected[index]);
}

function nextGeneration(value) {
  return value === Number.MAX_SAFE_INTEGER ? 0 : value + 1;
}

function createPerformanceMasterCaptureController({
  node,
  destination,
  timers,
  stopAckTimeoutMs,
  startAckTimeoutMs,
}) {
  let generation = 0;
  let active = null;
  // D0/W1: the controller owns the single pending start before the message
  // is posted, so a second start can never slip through the active=null
  // window, and a late ACK is never inherited by a later begin.
  let pendingStart = null;
  let closed = false;
  let processorFailed = false;

  function callSink(callback) {
    try {
      callback();
    } catch {
      // Sink failures belong to the Host control path and never escape into
      // the platform port handler or influence render continuation.
    }
  }

  function settle(record, notification) {
    if (active !== record || record.settled) return;
    record.settled = true;
    if (record.stopTimer !== null) {
      timers.clearTimeout(record.stopTimer);
      record.stopTimer = null;
    }
    active = null;
    if (notification === "stopped") {
      callSink(() => record.sink.onStopped());
    } else if (notification !== null) {
      callSink(() => record.sink.onFailure(
        "tap-failure", notification.droppedFrames));
      callSink(() => record.sink.onStopped());
    }
    record.resolve();
  }

  function requestProcessorStop(record) {
    if (record.stopRequested) return true;
    record.stopRequested = true;
    try {
      node.port.postMessage({
        type: "stop",
        generation: record.generation,
      });
      return true;
    } catch {
      return false;
    }
  }

  function failActiveTraffic(record, droppedFrames = 0) {
    if (active !== record || record.settled) return;
    record.terminalFailure = {droppedFrames};
    requestProcessorStop(record);
    settle(record, record.terminalFailure);
  }

  node.port.onmessage = ({data}) => {
    if (pendingStart !== null) {
      const pending = pendingStart;
      if (!validMasterTapEvent(data)) {
        rejectPendingStart(pending, "tap-protocol-failure");
        return;
      }
      // An ACK from an old generation or node is ignored, never inherited.
      if (data.generation !== pending.record.generation) return;
      // Only the exact started ACK for this binding arms the capture; a
      // batch before it, a duplicate, or a binding mismatch all fail the
      // pending start as protocol failures.
      if (data.type !== "started" ||
          !tapBindingEqual(data.binding, pending.record.binding)) {
        rejectPendingStart(pending, "tap-protocol-failure");
        return;
      }
      completePendingStart(pending);
      return;
    }
    const record = active;
    if (record === null) return;
    if (!validMasterTapEvent(data)) {
      if (record.terminalFailure === null) failActiveTraffic(record);
      return;
    }
    if (data.generation !== record.generation) return;
    if (record.terminalFailure !== null) return;
    if (data.type === "started") {
      // A started ACK with no pending start is a protocol failure: a closed
      // target must not be able to reuse it.
      failActiveTraffic(record);
      return;
    }
    if (
      data.type === "batch" &&
      data.sequence === record.sequence + 1
    ) {
      record.sequence = data.sequence;
      callSink(() => record.sink.onBatch(data.channels));
      return;
    }
    if (
      data.type === "stopped" &&
      record.stopRequested &&
      data.finalSequence === record.sequence
    ) {
      settle(record, "stopped");
      return;
    }
    if (data.type === "failed") {
      settle(record, {droppedFrames: data.droppedFrames});
      return;
    }
    failActiveTraffic(record);
  };

  function failProcessor() {
    if (processorFailed) return false;
    processorFailed = true;
    if (pendingStart !== null) {
      rejectPendingStart(pendingStart, "tap-processor-failed");
    }
    if (active !== null) settle(active, {droppedFrames: 0});
    return true;
  }

  // A rejected pending start releases the ownership slot and reports the
  // failure through the promise, never through sink callbacks (nothing was
  // ever armed). The record settles through the ordinary failure path so the
  // bounded stop cleanup still runs if the processor state is unknown.
  function rejectPendingStart(pending, reason) {
    if (pendingStart !== pending) return;
    pendingStart = null;
    if (pending.timer !== null) {
      timers.clearTimeout(pending.timer);
      pending.timer = null;
    }
    if (pending.posted) {
      // The processor may have received the start; run the bounded stop
      // cleanup before declaring the record settled.
      requestProcessorStop(pending.record);
    }
    settle(pending.record, {droppedFrames: 0});
    pending.reject(
      Object.assign(
        new Error("Performance master capture start was not acknowledged"),
        {code: reason},
      ));
  }

  function completePendingStart(pending) {
    if (pendingStart !== pending) return;
    pendingStart = null;
    if (pending.timer !== null) {
      timers.clearTimeout(pending.timer);
      pending.timer = null;
    }
    active = pending.record;
    pending.resolve(pending.handle);
  }

  async function start(sink, binding = null) {
    requireSink(sink);
    if (!validTapBinding(binding)) {
      throw new TypeError("Performance master capture binding is invalid");
    }
    if (closed || processorFailed) {
      throw new Error("Performance master capture is unavailable");
    }
    if (active !== null || pendingStart !== null) {
      throw new Error("Performance master capture is already active");
    }
    generation = nextGeneration(generation);
    let resolveStop;
    const stopPromise = new Promise((resolve) => { resolveStop = resolve; });
    const record = {
      generation,
      sequence: 0,
      binding,
      sink,
      stopRequested: false,
      stopTimer: null,
      terminalFailure: null,
      settled: false,
      resolve: resolveStop,
      stopPromise,
    };
    let resolveStart;
    let rejectStart;
    const startPromise = new Promise((resolve, reject) => {
      resolveStart = resolve;
      rejectStart = reject;
    });
    const pending = {
      record,
      posted: false,
      timer: null,
      resolve: resolveStart,
      reject: rejectStart,
      handle: null,
    };
    // The pending owner is registered before the message is posted.
    pendingStart = pending;
    let stopping = null;
    pending.handle = Object.freeze({
      // The immutable started receipt: proof this tap armed this binding.
      generation: record.generation,
      binding,
      stop() {
        if (record.settled || record.stopRequested) return record.stopPromise;
        if (!requestProcessorStop(record)) {
          settle(record, {droppedFrames: 0});
        }
        if (!record.settled) {
          record.stopTimer = timers.setTimeout(() => {
            settle(record, {droppedFrames: 0});
          }, stopAckTimeoutMs);
        }
        return record.stopPromise;
      },
    });
    // The start failure timer exists before the post: a synchronous ACK or a
    // synchronous post failure both settle it exactly once.
    pending.timer = timers.setTimeout(() => {
      rejectPendingStart(pending, "tap-start-timeout");
    }, startAckTimeoutMs);
    try {
      node.port.postMessage({type: "start", generation, binding});
      pending.posted = true;
    } catch {
      rejectPendingStart(pending, "tap-post-failed");
      throw new Error("Performance master capture could not start");
    }
    return startPromise;
  }

  async function close() {
    if (closed) return;
    closed = true;
    if (pendingStart !== null) {
      rejectPendingStart(pendingStart, "tap-closed");
    }
    if (active !== null) settle(active, {droppedFrames: 0});
    node.port.onmessage = null;
    try {
      node.disconnect(destination);
    } catch {}
  }

  return Object.freeze({
    destinationNode: node,
    start,
    failProcessor,
    close,
  });
}

export async function createPerformanceMasterTap(
  {context, processorUrl, destination = context.destination},
  internal = {},
) {
  if (destination !== context.destination && destination?.context !== context) {
    throw new TypeError("Perform master tap destination must share its context");
  }
  const url = new URL(processorUrl, globalThis.location?.href);
  if (globalThis.location && url.origin !== globalThis.location.origin) {
    throw new TypeError("Perform master tap URL must be same-origin");
  }
  await context.audioWorklet.addModule(url.href);
  const node = new AudioWorkletNode(context, "lmdj-perform-master-tap", {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [2],
    channelCount: 2,
    channelCountMode: "explicit",
    channelInterpretation: "discrete",
  });
  node.connect(destination);
  return createPerformanceMasterCaptureController({
    node,
    destination,
    timers: internal.timers ?? globalThis,
    stopAckTimeoutMs:
      internal.stopAckTimeoutMs ?? STOP_ACK_TIMEOUT_MS,
    startAckTimeoutMs:
      internal.startAckTimeoutMs ?? START_ACK_TIMEOUT_MS,
  });
}
