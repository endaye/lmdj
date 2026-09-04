const MAX_BATCH_FRAMES = 4_800;
const STOP_ACK_TIMEOUT_MS = 30_000;

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
}) {
  let generation = 0;
  let active = null;
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
    const record = active;
    if (record === null) return;
    if (!validMasterTapEvent(data)) {
      if (record.terminalFailure === null) failActiveTraffic(record);
      return;
    }
    if (data.generation !== record.generation) return;
    if (record.terminalFailure !== null) return;
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
    if (active !== null) settle(active, {droppedFrames: 0});
    return true;
  }

  async function start(sink) {
    requireSink(sink);
    if (closed || processorFailed) {
      throw new Error("Performance master capture is unavailable");
    }
    if (active !== null) {
      throw new Error("Performance master capture is already active");
    }
    generation = nextGeneration(generation);
    let resolveStop;
    const stopPromise = new Promise((resolve) => { resolveStop = resolve; });
    const record = {
      generation,
      sequence: 0,
      sink,
      stopRequested: false,
      stopTimer: null,
      terminalFailure: null,
      settled: false,
      resolve: resolveStop,
      stopPromise,
    };
    active = record;
    try {
      node.port.postMessage({type: "start", generation});
    } catch {
      settle(record, {droppedFrames: 0});
      throw new Error("Performance master capture could not start");
    }
    return Object.freeze({
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
  }

  async function close() {
    if (closed) return;
    closed = true;
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
  {context, processorUrl},
  internal = {},
) {
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
  node.connect(context.destination);
  return createPerformanceMasterCaptureController({
    node,
    destination: context.destination,
    timers: internal.timers ?? globalThis,
    stopAckTimeoutMs:
      internal.stopAckTimeoutMs ?? STOP_ACK_TIMEOUT_MS,
  });
}
