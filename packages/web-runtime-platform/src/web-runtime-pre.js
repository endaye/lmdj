if (typeof globalThis.window !== "undefined") {
  globalThis.Module = Module;
  // Capture this invocation's configuration before any publication or
  // external callback can change the shared browser Module reference.
  const runtimeOwnerCreated = Module["lmdjRuntimeOwnerCreated"];
  delete Module["lmdjRuntimeOwnerCreated"];
  const PUBLICATION_SETTLEMENT_WATCHDOG_MS = 1_000;
  const TRANSPORT_POLL_INTERVAL_MS = 16;
  const deadlineProofConfig = window.__LMDJ_WEB_HOST_DEADLINE_PROOF__;
  const publicationSettlementWatchdogMs =
    Number.isInteger(deadlineProofConfig?.settlementWatchdogMs) &&
    deadlineProofConfig.settlementWatchdogMs > 0 &&
    deadlineProofConfig.settlementWatchdogMs <=
      PUBLICATION_SETTLEMENT_WATCHDOG_MS
      ? deadlineProofConfig.settlementWatchdogMs
      : PUBLICATION_SETTLEMENT_WATCHDOG_MS;
  const NativeWorker = window.Worker;
  const runtimeWorkers = new Set();
  window.Worker = class LmdjWebRuntimeWorker extends NativeWorker {
    constructor(...arguments_) {
      super(...arguments_);
      runtimeWorkers.add(this);
      window.Worker = NativeWorker;
    }
  };
  /* LMDJ_WEB_AUDIO_CONFORMANCE_MANIFEST */

  const injectedManifestBytes = Module["lmdjHostManifestBytes"];
  const injectedManifestSha256 = Module["lmdjHostManifestSha256"];
  const manifestPreRun = () => {
    if (
      !(injectedManifestBytes instanceof Uint8Array) ||
      injectedManifestBytes.byteLength < 1 ||
      injectedManifestBytes.byteLength > 65_536 ||
      !/^[0-9a-f]{64}$/.test(injectedManifestSha256)
    ) {
      throw new Error("HOST_PROTOCOL_MISMATCH");
    }
    const initialized = Module.ccall(
      "lmdj_web_host_initialize_manifest",
      "number",
      ["array", "number", "string", "number"],
      [
        injectedManifestBytes,
        injectedManifestBytes.byteLength,
        injectedManifestSha256,
        injectedManifestSha256.length,
      ],
    );
    delete Module["lmdjHostManifestBytes"];
    delete Module["lmdjHostManifestSha256"];
    if (initialized !== 0) {
      throw new Error("HOST_PROTOCOL_MISMATCH");
    }
    host.manifestReady = true;
  };
  const previousPreRun = Module["preRun"];
  Module["preRun"] = Array.isArray(previousPreRun)
    ? [...previousPreRun, manifestPreRun]
    : typeof previousPreRun === "function"
      ? [previousPreRun, manifestPreRun]
      : [manifestPreRun];

  const contexts = new Map();
  const audioNodes = new Map();
  const fatalNames = Object.freeze({
    0: "none",
    1: "wrong_browser_thread",
    2: "invalid_audio_context",
    3: "unsupported_sample_rate",
    4: "unsupported_render_quantum",
    5: "worklet_thread_start_failed",
    6: "processor_create_failed",
    7: "node_create_failed",
    8: "invalid_callback_shape",
    9: "callback_reentry",
    10: "coordinator_install_failed",
    11: "processor_error",
    12: "quiescence_timeout",
    13: "bootstrap_timeout",
  });
  const gateNames = Object.freeze({
    0: "paused",
    1: "open",
    2: "final-quantum-requested",
    3: "terminal",
  });
  const delay = (milliseconds) =>
    new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  const unsupportedResult = () => ({
    ok: false,
    error: {
      code: "UNSUPPORTED_WEB_RUNTIME",
      message: "realized Web Audio configuration is unsupported",
      details: {
        expected_sample_rate: 48_000,
        observed_sample_rate:
          Module["_lmdj_web_audio_observed_sample_rate"](),
        expected_render_quantum: 128,
        observed_render_quantum:
          Module["_lmdj_web_audio_observed_render_quantum"](),
      },
    },
  });
  async function ensureControlFailureCommitted() {
    while (Module["_lmdj_web_audio_control_failure_committed"]() !== 1) {
      Module["_lmdj_web_audio_commit_failure"]();
      await delay(2);
    }
  }
  async function waitForUnsupportedFailure() {
    await ensureControlFailureCommitted();
    return unsupportedResult();
  }
  async function committedFatalResult() {
    const fatalCode = Module["_lmdj_web_audio_fatal"]();
    await ensureControlFailureCommitted();
    return {ok: false, fatal: fatalNames[fatalCode] ?? "unknown"};
  }

  function registerAudioContext(audioContext) {
    if (!(audioContext instanceof AudioContext)) {
      throw new TypeError("an AudioContext is required");
    }
    const handle = emscriptenRegisterAudioObject(audioContext);
    if (!Number.isInteger(handle) || handle <= 0) {
      throw new Error("AudioContext registration failed");
    }
    contexts.set(handle, audioContext);
    return handle;
  }

  function registerAudioNode(node) {
    if (!(node instanceof AudioNode)) {
      throw new TypeError("an AudioNode is required");
    }
    const contextHandle = [...contexts.entries()]
      .find(([, context]) => context === node.context)?.[0];
    if (!Number.isInteger(contextHandle) || contextHandle <= 0) {
      throw new TypeError("the AudioNode context must be registered");
    }
    const handle = emscriptenRegisterAudioObject(node);
    if (!Number.isInteger(handle) || handle <= 0) {
      throw new Error("AudioNode registration failed");
    }
    audioNodes.set(handle, {node, contextHandle});
    return handle;
  }

  function audioCallbackHeartbeat() {
    return Module["_lmdj_web_audio_callback_heartbeat"]() >>> 0;
  }

  function audioEngineEpochHeartbeat() {
    const sample = Module["_lmdj_web_audio_engine_epoch_heartbeat"];
    return typeof sample === "function" ? sample() >>> 0 : null;
  }

  let startRecord = null;
  function startAudioWorklet(
    contextHandle,
    outputDestinationHandle = contextHandle,
  ) {
    return startAudioWorkletOutputs(
      contextHandle, outputDestinationHandle, 0);
  }

  function startAudioWorkletWithCountIn(
    contextHandle, outputDestinationHandle, cueDestinationHandle,
  ) {
    if (!Number.isInteger(cueDestinationHandle) || cueDestinationHandle <= 0 ||
        cueDestinationHandle === outputDestinationHandle ||
        audioNodes.get(cueDestinationHandle)?.contextHandle !== contextHandle) {
      return Promise.reject(
        new TypeError("a distinct registered cue monitor handle is required"));
    }
    return startAudioWorkletOutputs(
      contextHandle, outputDestinationHandle, cueDestinationHandle);
  }

  function setCountInMetronome(enabled) {
    if (typeof enabled !== "boolean") throw new TypeError("Count-in metronome must be boolean");
    if (!host.runtimeInitialized || !host.manifestReady || transport.terminated ||
        typeof Module["_lmdj_web_audio_set_count_in_metronome"] !== "function") return false;
    return Module["_lmdj_web_audio_set_count_in_metronome"](enabled ? 1 : 0) === 1;
  }

  function startAudioWorkletOutputs(
    contextHandle, outputDestinationHandle, cueDestinationHandle,
  ) {
    if (
      !Number.isInteger(contextHandle) ||
      contextHandle <= 0 ||
      !contexts.has(contextHandle)
    ) {
      return Promise.reject(
        new TypeError("a registered AudioContext handle is required"));
    }
    const destination = audioNodes.get(outputDestinationHandle);
    if (
      !Number.isInteger(outputDestinationHandle) ||
      outputDestinationHandle <= 0 ||
      (
        outputDestinationHandle !== contextHandle &&
        destination?.contextHandle !== contextHandle
      )
    ) {
      return Promise.reject(
        new TypeError("a registered output destination handle is required"));
    }
    if (startRecord !== null) {
      if (
        startRecord.contextHandle !== contextHandle ||
        startRecord.outputDestinationHandle !== outputDestinationHandle ||
        startRecord.cueDestinationHandle !== cueDestinationHandle
      ) {
        return Promise.reject(
          new TypeError("the AudioWorklet is bound to another output graph"));
      }
      return startRecord.promise;
    }
    const context = contexts.get(contextHandle);
    const promise = (async () => {
      const deadline = performance.now() + 30_000;
      while (!host.runtimeInitialized && performance.now() < deadline) {
        await delay(2);
      }
      const result = cueDestinationHandle === 0
        ? Module["_lmdj_web_audio_start"](contextHandle, outputDestinationHandle)
        : Module["_lmdj_web_audio_start_with_count_in"](
            contextHandle, outputDestinationHandle, cueDestinationHandle);
      if (result === -4 || result === -5) {
        return waitForUnsupportedFailure();
      }
      if (result !== 1 && result !== 2 && result !== 3) {
        const fatalCode = Module["_lmdj_web_audio_fatal"]();
        if (fatalCode !== 0) return committedFatalResult();
        return {ok: false, fatal: fatalNames[fatalCode] ?? "unknown"};
      }
      while (performance.now() < deadline) {
        const state = Module["_lmdj_web_audio_state"]();
        if (state === 3) {
          return {
            ok: true,
            sampleRate: context.sampleRate,
            inputs: 0,
            outputs: cueDestinationHandle === 0 ? 1 : 2,
            channels: 2,
            frames: 128,
          };
        }
        if (state === -1) {
          return committedFatalResult();
        }
        await delay(5);
      }
      const finalState = Module["_lmdj_web_audio_state"]();
      if (finalState === 3) {
        return {
          ok: true,
          sampleRate: context.sampleRate,
          inputs: 0,
          outputs: cueDestinationHandle === 0 ? 1 : 2,
          channels: 2,
          frames: 128,
        };
      }
      if (finalState === -1) return committedFatalResult();
      Module["_lmdj_web_audio_bootstrap_timeout"]();
      return committedFatalResult();
    })();
    startRecord = {
      contextHandle, outputDestinationHandle, cueDestinationHandle, promise,
    };
    return promise;
  }

  function connectAudioWorkletDirect(contextHandle, outputDestinationHandle = contextHandle) {
    if (
      !Number.isInteger(contextHandle) ||
      contextHandle <= 0 ||
      !contexts.has(contextHandle) ||
      startRecord?.contextHandle !== contextHandle ||
      !Number.isInteger(outputDestinationHandle) ||
      outputDestinationHandle <= 0 ||
      (outputDestinationHandle !== contextHandle &&
        audioNodes.get(outputDestinationHandle)?.contextHandle !== contextHandle)
    ) {
      return false;
    }
    return Module["_lmdj_web_audio_connect_direct"](
      contextHandle, outputDestinationHandle) === 1;
  }

  const transportEncoder = new TextEncoder();
  const transportDecoder = new TextDecoder("utf-8", {fatal: true});
  const pendingRequests = new Map();
  // Accepted RPCs whose public observer failed still have a real Bridge
  // response consumer. Draining that response never consumes a Native ticket.
  const abandonedRequestIds = new Set();
  // Abandoned RPCs whose Native cancel already returned a receipt (0 or 1).
  // Reaping retries only an unreceipted cancel; it never re-cancels.
  const receiptedAbandonedIds = new Set();
  // Same finite request owner budget as ControlBridge's existing 16 slots.
  const RETAINED_RPC_OWNER_LIMIT = 16;
  const notificationSubscribers = new Set();
  const failureSubscribers = new Set();
  const TERMINAL_OWNER_RELEASE_GRACE_MS = 5_000;
  const terminalToken = crypto.randomUUID();
  const terminalChannel = new BroadcastChannel(
    "lmdj.web-runtime-host.terminal.v1");
  let pollScheduled = false;
  let transportTerminated = false;
  let terminalTransportError = null;
  let terminalOwnerBlocked = false;
  let terminalOwnerReleased = false;
  let terminalFailureDelivered = false;
  let terminalAckTimeout = 0;
  let terminalCleanupCompleted = false;
  let resolveTerminalCleanup;
  const terminalCleanupPromise = new Promise((resolve) => {
    resolveTerminalCleanup = resolve;
  });
  let host;

  function transportFailure(code, message, details = {}) {
    const error = new Error(message);
    error.code = code;
    error.details = Object.freeze({...details});
    return error;
  }

  function requestDeadlineDetails(pending) {
    return {...pending.deadlineProvenance, cancel_return: pending.cancelReturn};
  }

  function restartRequiredFailure(pending) {
    return transportFailure(
      "HOST_RESTART_REQUIRED",
      "Project publication settlement did not complete; restart and inspect before retrying",
      {
        ...requestDeadlineDetails(pending),
        terminal_state: "restart-required",
        mutation_outcome: "unknown",
      },
    );
  }

  function cancelControlRequest(requestId) {
    if (!host.runtimeInitialized) return -1;
    try {
      return Module.ccall(
        "lmdj_web_host_cancel_request",
        "number",
        ["string", "number"],
        [requestId, requestId.length],
      );
    } catch {
      return -1;
    }
  }

  function cancelQueryRequest(requestId) {
    if (!host.runtimeInitialized) return -1;
    try {
      return Module.ccall(
        "lmdj_web_host_cancel_query",
        "number",
        ["string", "number"],
        [requestId, requestId.length],
      );
    } catch {
      return -1;
    }
  }

  function transportAbortError() {
    const error = new Error("formal Web Host request was cancelled");
    error.name = "AbortError";
    return error;
  }

  function detachPendingAbort(pending) {
    if (pending.abortSignal && pending.abortListener) {
      pending.abortSignal.removeEventListener("abort", pending.abortListener);
    }
    pending.abortSignal = null;
    pending.abortListener = null;
  }

  function abortPendingRequest(requestId, pending) {
    if (
      (transportTerminated && !pending.retained) ||
      pendingRequests.get(requestId) !== pending ||
      pending.abortError !== null
    ) {
      return;
    }
    pending.abortError = transportAbortError();
    const cancellation = cancelQueryRequest(requestId);
    pending.cancelReturn ??= cancellation;
    if (cancellation < -1 || cancellation > 1) {
      failClosed(transportFailure(
        "HOST_TIMEOUT", "formal Web Host request cancellation failed"));
      return;
    }
    window.clearTimeout(pending.timeout);
    pending.deadlineAt = performance.now();
    pending.deadlineLinearized = true;
    pending.settlementDeadlineAt =
      performance.now() + publicationSettlementWatchdogMs;
    linearizeRequestDeadline(requestId, pending);
    scheduleTransportPoll();
  }

  function deliverTerminalFailure() {
    if (terminalFailureDelivered) return;
    terminalFailureDelivered = true;
    for (const subscriber of [...failureSubscribers]) {
      try {
        subscriber(terminalTransportError);
      } catch {
        // One observer cannot prevent terminal cleanup.
      }
    }
    notificationSubscribers.clear();
    failureSubscribers.clear();
  }

  function completeTerminalCleanup() {
    if (terminalCleanupCompleted || !terminalOwnerReleased ||
        pendingRequests.size !== 0) return;
    finishTerminalCleanup();
  }

  // As on main, a Native owner that has not confirmed its release within the
  // grace period is ended by force: a worker blocked inside a claimed
  // publication can never authorize it, and only terminating the workers
  // frees their storage locks for the next owner. A released owner whose
  // retained requests are still draining has a live control thread, so it
  // keeps waiting instead. A forced end resolves terminate() without a
  // release receipt; callers keep checking terminalOwnerReleased.
  function forceTerminalCleanup() {
    if (terminalCleanupCompleted || terminalOwnerReleased) return;
    for (const [requestId, pending] of [...pendingRequests.entries()]) {
      rejectRetainedRequest(requestId, pending, transportFailure(
        "HOST_RESTART_REQUIRED",
        "retained Web Host owner was ended before its release",
        {
          ...requestDeadlineDetails(pending),
          terminal_state: "restart-required",
          mutation_outcome: "unknown",
        }));
    }
    finishTerminalCleanup();
  }

  function finishTerminalCleanup() {
    terminalCleanupCompleted = true;
    window.clearTimeout(terminalAckTimeout);
    abandonedRequestIds.clear();
    receiptedAbandonedIds.clear();
    terminateRuntimeWorkers();
    try {
      terminalChannel.close();
    } catch {
      // The release attempt is terminal even if the browser channel is gone.
    }
    deliverTerminalFailure();
    resolveTerminalCleanup();
  }

  function releaseTerminalOwner() {
    if (terminalCleanupCompleted) return;
    window.clearTimeout(terminalAckTimeout);
    if (terminalReleaseCompleted() && consumeTerminalOwnerRelease()) {
      completeTerminalCleanup();
      if (terminalCleanupCompleted) return;
    }
    try {
      terminalChannel.postMessage({
        type: "release-and-close",
        token: terminalToken,
      });
    } catch {
      // A lost channel is not a physical/caller/IO release receipt. Keep the
      // actual owner and retry its existing authenticated retirement request.
    }
    if (terminalOwnerBlocked) {
      terminalAckTimeout = window.setTimeout(
        forceTerminalCleanup, TRANSPORT_POLL_INTERVAL_MS);
      scheduleTransportPoll();
      return;
    }
    terminalAckTimeout = window.setTimeout(() => {
      if (terminalOwnerReleased ||
          (terminalReleaseCompleted() && consumeTerminalOwnerRelease())) {
        // The control worker has already closed. Polling finishes cleanup once
        // retained requests drain; asking it to release again does nothing.
        completeTerminalCleanup();
      } else {
        forceTerminalCleanup();
      }
    }, TERMINAL_OWNER_RELEASE_GRACE_MS);
    scheduleTransportPoll();
  }

  function terminalReleaseCompleted() {
    try {
      return Module.ccall(
        "lmdj_web_host_terminal_release_completed", "number", [], []) === 1;
    } catch {
      return false;
    }
  }

  function consumeTerminalOwnerRelease() {
    if (terminalOwnerReleased) return true;
    let released;
    try {
      released = Module.ccall(
        "lmdj_web_host_consume_terminal_release",
        "number",
        ["string", "number"],
        [terminalToken, terminalToken.length],
      );
    } catch {
      return false;
    }
    if (released !== 1) return false;
    terminalOwnerReleased = true;
    return true;
  }

  function terminateRuntimeWorkers() {
    for (const worker of runtimeWorkers) {
      try {
        worker.terminate();
      } catch {
        // The transport has already sealed every external operation.
      }
    }
    runtimeWorkers.clear();
  }

  function failClosed(error) {
    if (transportTerminated) return false;
    transportTerminated = true;
    terminalTransportError = error;
    // Preserve the first deadline origin even when no System surface/React
    // diagnostic is mounted. Console failure cannot affect settlement.
    if (["HOST_TIMEOUT", "HOST_RESTART_REQUIRED"].includes(error.code)) {
      try {
        const source = error.details ?? {};
        const capsule = {code: error.code};
        if (typeof source.operation === "string" && /^[a-z][a-z0-9._-]{0,63}$/.test(source.operation)) {
          capsule.operation = source.operation;
        }
        if (typeof source.request_id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(source.request_id)) {
          capsule.request_id = source.request_id;
        }
        if (Number.isFinite(source.deadline_ms) && source.deadline_ms >= 0 && source.deadline_ms <= 0xffff_ffff) {
          capsule.deadline_ms = source.deadline_ms;
        }
        if (Number.isFinite(source.deadline_at_ms) && source.deadline_at_ms >= 0) {
          capsule.deadline_at_ms = source.deadline_at_ms;
        }
        if (Number.isSafeInteger(source.cancel_return)) capsule.cancel_return = source.cancel_return;
        console.warn("lmdj-web-host-deadline-diagnostic " + JSON.stringify(capsule));
      } catch {
        // Neither absent logging nor a throwing observer can alter the fault.
      }
    }
    const entries = [...pendingRequests.entries()];
    pendingRequests.clear();
    for (const [requestId, pending] of entries) {
      abandonedRequestIds.add(requestId);
      noteAbandonedCancel(requestId, cancelControlRequest(requestId));
      window.clearTimeout(pending.timeout);
      detachPendingAbort(pending);
      pending.reject(error);
    }
    // Existing consumers must see the original failure while the real Host
    // remains alive to service their exact retained inspect/release/consume.
    deliverTerminalFailure();
    releaseTerminalOwner();
    return true;
  }

  terminalChannel.addEventListener("message", (event) => {
    if (
      event.data?.type !== "released-and-closed" ||
      event.data?.token !== terminalToken
    ) {
      return;
    }
    if (!consumeTerminalOwnerRelease()) return;
    completeTerminalCleanup();
  });

  function rejectRetainedRequest(requestId, pending, error) {
    if (pendingRequests.get(requestId) !== pending) return;
    pendingRequests.delete(requestId);
    abandonedRequestIds.add(requestId);
    noteAbandonedCancel(requestId, cancelControlRequest(requestId));
    window.clearTimeout(pending.timeout);
    detachPendingAbort(pending);
    // This RPC was submitted. Neither its deadline nor cancellation proves
    // that an existing input or count-in consumer acknowledged its ticket.
    error.details = Object.freeze({...error.details, pending: true});
    pending.reject(error);
    scheduleTransportPoll();
  }

  function noteAbandonedCancel(requestId, status) {
    if (status === 0 || status === 1) receiptedAbandonedIds.add(requestId);
  }

  function reapAbandonedControlRequests() {
    if (!host.runtimeInitialized) return;
    for (const requestId of receiptedAbandonedIds)
      if (!abandonedRequestIds.has(requestId)) receiptedAbandonedIds.delete(requestId);
    for (const requestId of abandonedRequestIds) {
      if (receiptedAbandonedIds.has(requestId)) continue;
      try {
        const status = Module.ccall(
          "lmdj_web_host_cancel_request", "number", ["string", "number"],
          [requestId, requestId.length]);
        if (status === -1) abandonedRequestIds.delete(requestId);
        else noteAbandonedCancel(requestId, status);
        // A real not-found receipt retires only this RPC lookup. Native and
        // SDK consumer identities remain retained independently. An exception
        // is not a receipt and cannot free any budget.
      } catch {}
    }
  }

  function linearizeRequestDeadline(requestId, pending) {
    const remaining = pending.deadlineAt - performance.now();
    if (remaining > 0) {
      pending.timeout = window.setTimeout(
        () => onRequestDeadline(requestId), remaining);
      return true;
    }
    let cancellation;
    if (pending.deadlineLinearized !== true) {
      cancellation = cancelControlRequest(requestId);
      pending.cancelReturn ??= cancellation;
    }
    if (pending.deadlineLinearized === true || cancellation === 0) {
      pending.deadlineLinearized = true;
      if (pending.settlementDeadlineAt === null) {
        pending.settlementDeadlineAt =
          performance.now() + publicationSettlementWatchdogMs;
      }
      const settlementRemaining =
        pending.settlementDeadlineAt - performance.now();
      if (settlementRemaining <= 0) {
        // A claimed publication that never settled keeps the control thread,
        // so the owner can never authorize its release. Do not wait out the
        // grace period for a receipt that cannot arrive.
        terminalOwnerBlocked = true;
        if (pending.retained) {
          rejectRetainedRequest(requestId, pending, restartRequiredFailure(pending));
          if (transportTerminated && !terminalCleanupCompleted) {
            window.clearTimeout(terminalAckTimeout);
            terminalAckTimeout = window.setTimeout(
              forceTerminalCleanup, TRANSPORT_POLL_INTERVAL_MS);
          }
        } else {
          failClosed(restartRequiredFailure(pending));
        }
        return false;
      }
      pending.timeout = window.setTimeout(
        () => onRequestDeadline(requestId),
        Math.min(2, settlementRemaining),
      );
      return true;
    }
    const error = transportFailure(
      "HOST_TIMEOUT", "formal Web Host request timed out", requestDeadlineDetails(pending));
    if (pending.retained) rejectRetainedRequest(requestId, pending, error);
    else failClosed(error);
    return false;
  }

  function onRequestDeadline(requestId) {
    const pending = pendingRequests.get(requestId);
    if (!pending || (transportTerminated && !pending.retained)) return;
    linearizeRequestDeadline(requestId, pending);
  }

  function scheduleTransportPoll() {
    if (
      terminalCleanupCompleted ||
      pollScheduled ||
      (!transportTerminated && !pendingRequests.size &&
       !notificationSubscribers.size)
    ) {
      return;
    }
    pollScheduled = true;
    window.setTimeout(pollTransport, TRANSPORT_POLL_INTERVAL_MS);
  }

  function pollTransport() {
    pollScheduled = false;
    if (terminalCleanupCompleted) return;
    if (!host.runtimeInitialized) {
      scheduleTransportPoll();
      return;
    }
    for (const [requestId, pending] of pendingRequests) {
      if (
        performance.now() >= pending.deadlineAt &&
        pending.deadlineLinearized !== true &&
        !linearizeRequestDeadline(requestId, pending)
      ) {
        return;
      }
    }
    const output = _malloc(65_536);
    const requiredPointer = _malloc(4);
    try {
      const status = _lmdj_web_host_poll(output, 65_536, requiredPointer);
      const required = HEAPU32[requiredPointer >> 2];
      if (status === 1) {
        const bytes = HEAPU8.slice(output, output + required);
        const message = JSON.parse(transportDecoder.decode(bytes));
        if (typeof message.request_id === "string") {
          const pending = pendingRequests.get(message.request_id);
          if (pending) {
            pendingRequests.delete(message.request_id);
            window.clearTimeout(pending.timeout);
            detachPendingAbort(pending);
            if (pending.abortError !== null) {
              pending.reject(pending.abortError);
            } else {
              pending.resolve(message);
            }
          } else if (abandonedRequestIds.delete(message.request_id)) {
            // Consume only the actual Bridge response envelope. The SDK's
            // independently retained Native/input/count-in owner remains.
          } else {
            failClosed(transportFailure(
              "HOST_PROTOCOL_MISMATCH",
              "formal Web Host response request ID is not pending",
            ));
            if (!transportTerminated) return;
          }
        } else {
          for (const subscriber of notificationSubscribers) {
            subscriber(message);
          }
        }
      } else if (status === 2 || status === 3) {
        failClosed(transportFailure(
          status === 2 ? "HOST_PROTOCOL_MISMATCH" : "HOST_STATE_INVALID",
          "formal Web Host transport failed",
        ));
      }
    } catch {
      failClosed(transportFailure(
        "HOST_PROTOCOL_MISMATCH",
        "formal Web Host transport message is invalid",
      ));
    } finally {
      _free(requiredPointer);
      _free(output);
    }
    if (transportTerminated) reapAbandonedControlRequests();
    // Native completes the terminal release asynchronously, possibly after the
    // worker acknowledgement. Consume it once it is observably complete, so a
    // poll never spends a rejected consume, then finish once requests drain.
    if (transportTerminated && !terminalOwnerReleased &&
        terminalReleaseCompleted()) consumeTerminalOwnerRelease();
    if (transportTerminated && terminalOwnerReleased) completeTerminalCleanup();
    scheduleTransportPoll();
  }

  function retainedOwnerRequest(request) {
    const exactKeys = (value, keys) => value !== null &&
      typeof value === "object" && !Array.isArray(value) &&
      Object.keys(value).length === keys.length &&
      keys.every((key) => Object.hasOwn(value, key));
    if (!exactKeys(request, ["protocol_version", "request_id", "operation", "payload"]) ||
        request.protocol_version !== 1 || typeof request.request_id !== "string" ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(request.request_id)) {
      return false;
    }
    const payload = request.payload;
    switch (request.operation) {
      case "pattern.tempo.preview.status":
      case "pattern.tempo.preview.cancel":
        return exactKeys(payload, ["ticket"]);
      case "pattern.tempo.preview.commit":
        // Core still requires this exact ticket's already-frozen command.
        // Neither begin nor set can enter the sealed transport.
        return exactKeys(payload, ["ticket", "command_id"]);
      case "pattern.transport.input.inspect":
        return exactKeys(payload,
          ["command_id", "runtime_generation", "frame_epoch", "ticket", "consume"]);
      case "pattern.transport.count-in.inspect":
        return exactKeys(payload, ["session_id", "command_id", "runtime_generation",
          "frame_epoch", "schedule_serial", "consume"]);
      case "pattern.transport.count-in.cancel":
        return exactKeys(payload, ["session_id", "project_id", "command_id",
          "start_command_id", "runtime_generation", "frame_epoch", "schedule_serial",
          "expected_epoch", "intent"]);
      case "pattern.transport.inspect":
        return exactKeys(payload, ["session_id"]);
      case "pattern.transport.input.request":
        return exactKeys(payload, ["command_id", "runtime_generation", "frame_epoch",
          "input_serial", "slot", "velocity", "kind", "held", "held_press_sequence"]) &&
          payload.kind === "release" && typeof payload.held_press_sequence === "string";
      default:
        return false;
    }
  }

  function sendTransportRequest(request, options = {}, retained = false) {
    if (!retained && transportTerminated) {
      return Promise.reject(terminalTransportError);
    }
    const notAdmitted = retained ? {pending: false} : {};
    if (retained && (!transportTerminated || terminalCleanupCompleted ||
        terminalOwnerReleased || !retainedOwnerRequest(request) ||
        pendingRequests.size + abandonedRequestIds.size >= RETAINED_RPC_OWNER_LIMIT ||
        (options.sidecar !== undefined && options.sidecar.byteLength !== 0))) {
      return Promise.reject(transportFailure(
        "HOST_STATE_INVALID", "retained Web Host owner request is unavailable",
        notAdmitted));
    }
    if (!host.runtimeInitialized || pendingRequests.has(request.request_id) ||
        abandonedRequestIds.has(request.request_id)) {
      return Promise.reject(transportFailure(
        "HOST_STATE_INVALID",
        "formal Web Host transport is unavailable", notAdmitted,
      ));
    }
    if (options.sidecar !== undefined &&
        !(options.sidecar instanceof Uint8Array)) {
      return Promise.reject(transportFailure(
        "HOST_PROTOCOL_MISMATCH",
        "formal Web Host sidecar is invalid", notAdmitted,
      ));
    }
    if (options.cancelQuery === true && options.signal?.aborted === true) {
      const error = transportAbortError();
      if (retained) error.details = Object.freeze(notAdmitted);
      return Promise.reject(error);
    }
    const envelope = transportEncoder.encode(JSON.stringify(request));
    const sidecar = options.sidecar ?? new Uint8Array();
    const deadlineMs = Number.isFinite(options.deadlineMs)
      ? Math.min(0xffff_ffff, Math.max(0, options.deadlineMs))
      : 30_000;
    const deadlineAt = performance.now() + deadlineMs;
    // Local scalars only: never retain the Project payload or sidecar. Capture
    // before submit; query abort may later change the active cutoff.
    const deadlineProvenance = Object.freeze({
      operation: request.operation,
      request_id: request.request_id,
      deadline_ms: deadlineMs,
      deadline_at_ms: deadlineAt,
    });
    const envelopePointer = envelope.byteLength === 0
      ? 0
      : _malloc(envelope.byteLength);
    const sidecarPointer = sidecar.byteLength === 0
      ? 0
      : _malloc(sidecar.byteLength);
    if ((envelope.byteLength !== 0 && envelopePointer === 0) ||
        (sidecar.byteLength !== 0 && sidecarPointer === 0)) {
      if (sidecarPointer !== 0) _free(sidecarPointer);
      if (envelopePointer !== 0) _free(envelopePointer);
      return Promise.reject(transportFailure(
        "HOST_STATE_INVALID",
        "formal Web Host transport is unavailable", notAdmitted,
      ));
    }
    let submitted;
    try {
      if (envelope.byteLength !== 0) {
        HEAPU8.set(envelope, envelopePointer);
      }
      if (sidecar.byteLength !== 0) {
        HEAPU8.set(sidecar, sidecarPointer);
      }
      submitted = Module.ccall(
        "lmdj_web_host_submit",
        "number",
        ["number", "number", "number", "number", "number"],
        [
          envelopePointer,
          envelope.byteLength,
          sidecarPointer,
          sidecar.byteLength,
          performance.timeOrigin + deadlineAt,
        ],
      );
    } catch (error) {
      if (!retained) throw error;
      abandonedRequestIds.add(request.request_id);
      scheduleTransportPoll();
      return Promise.reject(transportFailure(
        "HOST_STATE_INVALID", "retained Web Host submit outcome is unknown",
        {pending: true}));
    } finally {
      if (sidecarPointer !== 0) _free(sidecarPointer);
      if (envelopePointer !== 0) _free(envelopePointer);
    }
    if (submitted !== 0) {
      return Promise.reject(transportFailure(
        submitted === 1 || submitted === 2
          ? "HOST_PROTOCOL_MISMATCH"
          : "HOST_STATE_INVALID",
        "formal Web Host request was rejected", notAdmitted,
      ));
    }
    return new Promise((resolve, reject) => {
      const pending = {
        resolve,
        reject,
        retained,
        timeout: 0,
        deadlineAt,
        deadlineProvenance,
        cancelReturn: null,
        deadlineLinearized: false,
        settlementDeadlineAt: null,
        abortError: null,
        abortSignal: null,
        abortListener: null,
      };
      pendingRequests.set(request.request_id, pending);
      if (options.cancelQuery === true && options.signal !== undefined) {
        pending.abortSignal = options.signal;
        pending.abortListener = () =>
          abortPendingRequest(request.request_id, pending);
        options.signal.addEventListener("abort", pending.abortListener, {
          once: true,
        });
        if (options.signal.aborted === true) pending.abortListener();
      }
      if (pending.abortError === null) {
        linearizeRequestDeadline(request.request_id, pending);
      }
      scheduleTransportPoll();
    });
  }

  const transport = Object.freeze({
    send(request, options = {}) {
      return sendTransportRequest(request, options);
    },
    sendRetained(request, options = {}) {
      return sendTransportRequest(request, options, true);
    },
    subscribe(listener) {
      if (typeof listener !== "function") {
        throw new TypeError("a transport notification listener is required");
      }
      notificationSubscribers.add(listener);
      scheduleTransportPoll();
      return () => notificationSubscribers.delete(listener);
    },
    subscribeFailure(listener) {
      if (typeof listener !== "function") {
        throw new TypeError("a transport failure listener is required");
      }
      if (transportTerminated) {
        if (terminalFailureDelivered) {
          listener(terminalTransportError);
          return () => {};
        }
        failureSubscribers.add(listener);
        return () => failureSubscribers.delete(listener);
      }
      failureSubscribers.add(listener);
      return () => failureSubscribers.delete(listener);
    },
    terminate() {
      failClosed(transportFailure(
        "HOST_STATE_INVALID", "formal Web Host transport is terminated"));
      return terminalCleanupPromise;
    },
    get terminated() {
      return transportTerminated;
    },
    get terminalOwnerReleased() {
      return terminalOwnerReleased;
    },
    get terminalOwnerEnded() {
      // True once terminal cleanup finished, whether the owner released or was
      // ended by force; terminalOwnerReleased alone reports a release receipt.
      return terminalCleanupCompleted;
    },
  });

  const deadlineProof = deadlineProofConfig === undefined
    ? undefined
    : Object.freeze({
        arm({requestId, gate, forcePublicationError = false}) {
          const gates = Object.freeze({
            "responsive-cancellation": 1,
            "after-claim": 2,
            "unresponsive-cancellation": 3,
          });
          const selectedGate = gates[gate];
          if (
            typeof requestId !== "string" ||
            !Number.isInteger(selectedGate) ||
            Module.ccall(
              "lmdj_web_host_deadline_proof_configure",
              "number",
              ["string", "number", "number", "number"],
              [
                requestId,
                requestId.length,
                selectedGate,
                forcePublicationError === true ? 1 : 0,
              ],
            ) !== 1
          ) {
            throw new TypeError("deadline proof configuration is invalid");
          }
        },
        release() {
          return Module.ccall(
            "lmdj_web_host_deadline_proof_release", "number", [], []) === 1;
        },
        state(requestId) {
          const packed = Module.ccall(
            "lmdj_web_host_deadline_proof_state",
            "number",
            ["string", "number"],
            [requestId, requestId.length],
          );
          if (packed < 0) return null;
          return Object.freeze({
            entered_facade: (packed & (1 << 8)) !== 0,
            claim_attempted: (packed & (1 << 9)) !== 0,
            claim_started_open: (packed & (1 << 10)) !== 0,
            last_cancel_result: Object.freeze({
              0: "none",
              1: "publish-claimed",
              2: "cancelled",
              3: "not-found",
            })[(packed >> 16) & 0x3] ?? "unknown",
            cancel_calls: (packed >> 20) & 0xff,
            gate: Object.freeze({
              1: "responsive-cancellation",
              2: "after-claim",
              3: "unresponsive-cancellation",
            })[
              (packed >> 12) & 0xf
            ] ?? "none",
            publication: Object.freeze({
              0: "open",
              1: "cancelled",
              2: "publish-claimed",
              3: "committed",
              4: "aborted",
            })[packed & 0xff] ?? "unknown",
          });
        },
      });

  host = {
    runtimeInitialized: false,
    manifestReady: false,
    registerAudioContext,
    registerAudioNode,
    audioCallbackHeartbeat,
    audioEngineEpochHeartbeat,
    startAudioWorklet,
    startAudioWorkletWithCountIn,
    setCountInMetronome,
    connectAudioWorkletDirect,
    transport,
    ...(deadlineProof === undefined ? {} : {deadlineProof}),
  };
  if (typeof runtimeOwnerCreated === "function") runtimeOwnerCreated(host, Module);
  window.lmdjWebRuntimeHost = host;

  /* LMDJ_WEB_AUDIO_CONFORMANCE_API_BEGIN */
  function createConformanceApi() {
    const encoder = new TextEncoder();

    async function submitUntrackedHostStatus(requestId) {
      const envelope = encoder.encode(JSON.stringify({
        protocol_version: 1,
        request_id: requestId,
        operation: "host.status",
        payload: {},
      }));
      const deadline = performance.now() + 30_000;
      while (performance.now() < deadline) {
        const submitted = Module.ccall(
          "lmdj_web_host_submit",
          "number",
          ["array", "number", "array", "number", "number"],
          [
            envelope,
            envelope.byteLength,
            new Uint8Array(),
            0,
            performance.timeOrigin + deadline,
          ],
        );
        if (submitted === 0) {
          scheduleTransportPoll();
          return;
        }
        if (submitted !== -1) {
          throw new Error(`Host submit failed: host.status: ${submitted}`);
        }
        await delay(5);
      }
      throw new Error("Host submit timed out: host.status");
    }

    async function submit(operation, payload, sidecar = new Uint8Array()) {
      const requestId = crypto.randomUUID();
      const envelope = encoder.encode(JSON.stringify({
        protocol_version: 1,
        request_id: requestId,
        operation,
        payload,
      }));
      const deadline = performance.now() + 30_000;
      let accepted = false;
      while (performance.now() < deadline) {
        const submitted = Module.ccall(
          "lmdj_web_host_submit",
          "number",
          ["array", "number", "array", "number", "number"],
          [
            envelope,
            envelope.byteLength,
            sidecar,
            sidecar.byteLength,
            performance.timeOrigin + deadline,
          ],
        );
        if (submitted === 0) {
          accepted = true;
          break;
        }
        if (submitted !== -1) {
          throw new Error(`Host submit failed: ${submitted}`);
        }
        await delay(5);
      }
      if (!accepted) throw new Error(`Host submit timed out: ${operation}`);
      while (performance.now() < deadline) {
        const serialized = Module.ccall(
          "lmdj_web_audio_test_poll", "string", [], []);
        if (serialized) {
          const message = JSON.parse(serialized);
          if (message.request_id === requestId) return message;
        }
        await delay(2);
      }
      throw new Error(`Host response timed out: ${operation}`);
    }

    function writeU16(view, offset, value) {
      view.setUint16(offset, value, true);
    }

    function writeU32(view, offset, value) {
      view.setUint32(offset, value, true);
    }

    function writeTag(bytes, offset, tag) {
      for (let index = 0; index < tag.length; ++index) {
        bytes[offset + index] = tag.charCodeAt(index);
      }
    }

    function sineWav(frames) {
      const bytes = new Uint8Array(44 + frames * 2);
      const view = new DataView(bytes.buffer);
      writeTag(bytes, 0, "RIFF");
      writeU32(view, 4, 36 + frames * 2);
      writeTag(bytes, 8, "WAVE");
      writeTag(bytes, 12, "fmt ");
      writeU32(view, 16, 16);
      writeU16(view, 20, 1);
      writeU16(view, 22, 1);
      writeU32(view, 24, 48_000);
      writeU32(view, 28, 96_000);
      writeU16(view, 32, 2);
      writeU16(view, 34, 16);
      writeTag(bytes, 36, "data");
      writeU32(view, 40, frames * 2);
      for (let frame = 0; frame < frames; ++frame) {
        const sample = Math.round(
          Math.sin((2 * Math.PI * 440 * frame) / 48_000) * 24_000);
        view.setInt16(44 + frame * 2, sample, true);
      }
      return bytes;
    }

    async function sha256(bytes) {
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      return [...new Uint8Array(digest)]
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
    }

    async function prepareProject() {
      const projectId = crypto.randomUUID();
      const patternId = crypto.randomUUID();
      const assetId = crypto.randomUUID();
      const create = await submit("project.create", {
        project_id: projectId,
        bpm: 120,
        initial_pattern: {pattern_id: patternId, bars: 1, events: []},
      });
      if (!create.ok) throw new Error(JSON.stringify(create));
      const wav = sineWav(4_800);
      const imported = await submit("asset.import", {
        command_id: crypto.randomUUID(),
        expected_revision: 0,
        asset_id: assetId,
        media_type: "audio/wav",
        sidecar: {
          sidecar_bytes: wav.byteLength,
          sidecar_sha256: await sha256(wav),
        },
      }, wav);
      if (!imported.ok) throw new Error(JSON.stringify(imported));
      const assigned = await submit("pad.assign", {
        command_id: crypto.randomUUID(),
        expected_revision: 1,
        slot: {bank: 0, pad: 0},
        asset_id: assetId,
      });
      if (!assigned.ok) throw new Error(JSON.stringify(assigned));
      const snapshot = await submit(
        "snapshot.reload", {pattern_id: patternId});
      if (!snapshot.ok) throw new Error(JSON.stringify(snapshot));
      return {
        controlGeneration: snapshot.result.generation,
        patternId,
      };
    }

    async function prepareAndTrigger() {
      const prepared = await prepareProject();
      const activated = await submit("audio.activate", {});
      if (!activated.ok) throw new Error(JSON.stringify(activated));
      const trigger = await submit("trigger", {slot: 0, velocity: 127});
      if (!trigger.ok) throw new Error(JSON.stringify(trigger));
      return {
        ...prepared,
        admittedSequence: trigger.result.sequence,
      };
    }

    let lastRenderProofDeadlines = null;

    function readDiagnosticOutcome() {
      const count = Module["_lmdj_web_audio_test_outcome_count"]();
      return count === 0
        ? {count: 0}
        : {
            count,
            sequence: Module["_lmdj_web_audio_test_outcome_sequence"](0),
            outcome:
              Module["_lmdj_web_audio_test_outcome_code"](0) === 0
                ? "voice_started"
                : "voice_capacity",
            runtime_frame:
              Module["_lmdj_web_audio_test_outcome_frame"](0),
          };
    }

    async function requestAndDrainOutcomes({
      budgetMs = 30_000,
      onRequested = null,
    } = {}) {
      Module["_lmdj_web_audio_test_clear_outcomes"]();
      if (Module["_lmdj_web_audio_test_request_outcomes"]() !== 1) {
        throw new Error("outcome drain request was rejected");
      }
      const outcomeStartedAt = performance.now();
      const outcomeDeadline = outcomeStartedAt + budgetMs;
      if (onRequested !== null) {
        onRequested({outcomeStartedAt, outcomeDeadline});
      }
      while (
        Module["_lmdj_web_audio_test_outcome_state"]() === 1 &&
        performance.now() < outcomeDeadline
      ) await delay(2);
      return {
        outcomeStartedAt,
        outcomeDeadline,
        outcomeReadyAt: performance.now(),
        state: Module["_lmdj_web_audio_test_outcome_state"](),
        outcome: readDiagnosticOutcome(),
      };
    }

    async function queueSyntheticOutcomeWriter(
      sequence,
      outcome = 0,
      runtimeFrame = 256,
    ) {
      if (Module[
        "_lmdj_web_audio_test_queue_outcome_mirror_write"
      ](sequence, outcome, runtimeFrame) !== 1) {
        throw new Error("outcome mirror writer was rejected");
      }
      const writerDeadline = performance.now() + 3_000;
      while (
        Module["_lmdj_web_audio_test_outcome_mirror_state"]() !== 1 &&
        Module[
          "_lmdj_web_audio_test_outcome_mirror_writer_timed_out"
        ]() === 0 &&
        performance.now() < writerDeadline
      ) await delay(2);
      if (Module["_lmdj_web_audio_test_outcome_mirror_state"]() !== 1) {
        throw new Error("outcome mirror writer did not enter writing state");
      }
    }

    function releaseSyntheticOutcomeWriter() {
      if (Module[
        "_lmdj_web_audio_test_release_outcome_mirror_write"
      ]() !== 1) {
        throw new Error("outcome mirror writer release was rejected");
      }
    }

    async function waitForRenderProof(expected) {
      const renderStartedAt = performance.now();
      const renderDeadline = renderStartedAt + 30_000;
      let status = null;
      while (performance.now() < renderDeadline) {
        status = await submit("host.status", {});
        if (
          status.ok &&
          status.result.acknowledged_generation === expected &&
          Module["_lmdj_web_audio_test_output_energy"]() > 0
        ) break;
        await delay(5);
      }
      if (!status?.ok || status.result.acknowledged_generation !== expected) {
        throw new Error("Worklet generation acknowledgement timed out");
      }
      const drained = await requestAndDrainOutcomes();
      lastRenderProofDeadlines = Object.freeze({
        renderStartedAt,
        renderDeadline,
        outcomeStartedAt: drained.outcomeStartedAt,
        outcomeDeadline: drained.outcomeDeadline,
      });
      const count = drained.outcome.count;
      if (count < 1) throw new Error("no realtime outcome was drained");
      return {status, count};
    }

    return Object.freeze({
      submitUntrackedHostStatus,
      pendingRequestIds() {
        return Object.freeze([...pendingRequests.keys()]);
      },

      async runSharedEngineProof() {
        const memory = Module.wasmMemory;
        const initialBuffer = memory.buffer;
        const prepared = await prepareAndTrigger();
        await waitForRenderProof(prepared.controlGeneration);
        const sequence = Module["_lmdj_web_audio_test_outcome_sequence"](0);
        const code = Module["_lmdj_web_audio_test_outcome_code"](0);
        const runtimeFrame = Module["_lmdj_web_audio_test_outcome_frame"](0);
        return {
          ...prepared,
          acknowledgedGeneration:
            Module["_lmdj_web_audio_test_ack_generation"](),
          outcome: {
            sequence,
            outcome: code === 0 ? "voice_started" : "voice_capacity",
            runtime_frame: runtimeFrame,
          },
          outputEnergy: Module["_lmdj_web_audio_test_output_energy"](),
          memory: {
            bufferShared: initialBuffer instanceof SharedArrayBuffer,
            allowGrowth: memory.buffer !== initialBuffer,
            initialBytes: initialBuffer.byteLength,
          },
          callback: {
            inputs: 0,
            outputs: 1,
            channels: 2,
            frames: Module["_lmdj_web_audio_test_observed_frames"](),
          },
          deadlines: lastRenderProofDeadlines,
        };
      },

      async runFreshOutcomeDeadlineProof() {
        const expectedSequence = 51_515;
        const renderStartedAt = performance.now();
        const renderDeadline = renderStartedAt + 20;
        let writerQueued = false;
        let writerReleased = false;
        let releasePromise = null;
        try {
          await queueSyntheticOutcomeWriter(expectedSequence);
          writerQueued = true;
          while (performance.now() <= renderDeadline) await delay(2);
          const drained = await requestAndDrainOutcomes({
            budgetMs: 1_000,
            onRequested: () => {
              releasePromise = (async () => {
                await delay(25);
                releaseSyntheticOutcomeWriter();
                writerReleased = true;
              })();
            },
          });
          await releasePromise;
          if (drained.outcome.count < 1) {
            throw new Error("no outcome arrived within its fresh budget");
          }
          if (Module[
            "_lmdj_web_audio_test_outcome_mirror_writer_timed_out"
          ]() !== 0) {
            throw new Error("outcome mirror writer timed out");
          }
          return {
            expectedSequence,
            renderStartedAt,
            renderDeadline,
            outcomeStartedAt: drained.outcomeStartedAt,
            outcomeDeadline: drained.outcomeDeadline,
            outcomeReadyAt: drained.outcomeReadyAt,
            outcome: drained.outcome,
          };
        } finally {
          if (releasePromise !== null) {
            await releasePromise;
          } else if (writerQueued && !writerReleased) {
            releaseSyntheticOutcomeWriter();
          }
        }
      },

      async runOutcomeMirrorRaceProof() {
        const expectedSequence = 42_424;
        let writerQueued = false;
        let writerReleased = false;
        try {
          await queueSyntheticOutcomeWriter(expectedSequence);
          writerQueued = true;
          const firstDrain = await requestAndDrainOutcomes({
            budgetMs: 1_000,
            onRequested: () => {
              releaseSyntheticOutcomeWriter();
              writerReleased = true;
            },
          });
          const secondDrain = await requestAndDrainOutcomes({budgetMs: 1_000});
          if (Module[
            "_lmdj_web_audio_test_outcome_mirror_writer_timed_out"
          ]() !== 0) {
            throw new Error("outcome mirror writer timed out");
          }
          return {
            expectedSequence,
            writerTimedOut: false,
            first: firstDrain.outcome,
            second: {
              state: secondDrain.state,
              count: secondDrain.outcome.count,
            },
          };
        } finally {
          if (writerQueued && !writerReleased) {
            releaseSyntheticOutcomeWriter();
          }
        }
      },

      async runOutcomeMirrorWriterTimeoutProof() {
        const expectedSequence = 61_616;
        let writerMayNeedRelease = false;
        try {
          await queueSyntheticOutcomeWriter(expectedSequence);
          writerMayNeedRelease = true;
          const firstDrain = await requestAndDrainOutcomes({budgetMs: 7_000});
          const writerTimedOut = Module[
            "_lmdj_web_audio_test_outcome_mirror_writer_timed_out"
          ]() === 1;
          if (writerTimedOut) writerMayNeedRelease = false;
          const followupDrain = await requestAndDrainOutcomes({
            budgetMs: 1_000,
          });
          return {
            writerTimedOut,
            writerElapsedMs:
              firstDrain.outcomeReadyAt - firstDrain.outcomeStartedAt,
            mirrorState:
              Module["_lmdj_web_audio_test_outcome_mirror_state"](),
            first: {
              state: firstDrain.state,
              count: firstDrain.outcome.count,
            },
            followup: {
              state: followupDrain.state,
              count: followupDrain.outcome.count,
            },
            followupElapsedMs:
              followupDrain.outcomeReadyAt - followupDrain.outcomeStartedAt,
          };
        } finally {
          if (
            writerMayNeedRelease &&
            Module["_lmdj_web_audio_test_outcome_mirror_state"]() === 1
          ) {
            releaseSyntheticOutcomeWriter();
          }
        }
      },

      engineRenderCalls() {
        return Module["_lmdj_web_audio_test_render_calls"]();
      },

      armPhysicalFenceBarrier(stages) {
        return Module["_lmdj_web_audio_test_physical_fence_arm"](stages) === 1;
      },

      releasePhysicalFenceBarrier(stages) {
        return Module["_lmdj_web_audio_test_physical_fence_release"](stages) === 1;
      },

      physicalFenceState() {
        const cueBatch = Module["_lmdj_web_audio_test_physical_fence_cue_batch"]();
        const cuePendingBatch = Module["_lmdj_web_audio_test_physical_fence_pending_cue_batch"]();
        if (!Number.isSafeInteger(cueBatch) || cueBatch < 0 ||
            !Number.isSafeInteger(cuePendingBatch) || cuePendingBatch < 0)
          throw new Error("physical fence batch identity exceeds the guarded numeric observation");
        return {
          stage: Module["_lmdj_web_audio_test_physical_fence_stage"]() >>> 0,
          cueBatch, cuePendingBatch,
          borrows: Module["_lmdj_web_audio_test_physical_fence_borrows"]() >>> 0,
          physicalQuiescent: Module["_lmdj_web_audio_test_physically_quiescent"]() === 1,
          gate: gateNames[Module["_lmdj_web_audio_test_gate_state"]()],
          callbackInFlight: Module["_lmdj_web_audio_test_in_flight"](),
          fatal: fatalNames[Module["_lmdj_web_audio_fatal"]()] ?? null,
        };
      },

      requestPhysicalTerminalDrain() {
        return Module["_lmdj_web_audio_test_request_physical_terminal_drain"]() === 1;
      },

      async runPhysicalFenceQuiescenceWait(timeoutMs) {
        const startedAt = performance.now();
        if (Module["_lmdj_web_audio_test_physical_quiescence_wait"](timeoutMs) !== 1)
          throw new Error("actual physical fence wait was rejected");
        // Same finite watchdog as the existing operational diagnostic. The
        // real control wait retains its original two equal timeout budgets.
        while (performance.now() < startedAt + 500) {
          const serialized = Module.ccall(
            "lmdj_web_audio_test_quiescence_timeout_result", "string", [], []);
          if (serialized) return {...JSON.parse(serialized),
            observed_wall_ms: performance.now() - startedAt};
          await delay(2);
        }
        return {completed: false, observed_wall_ms: performance.now() - startedAt};
      },

      preactivationState() {
        return {
          gate:
            gateNames[Module["_lmdj_web_audio_test_gate_state"]()],
          callbackInFlight:
            Module["_lmdj_web_audio_test_in_flight"](),
          renderCalls: Module["_lmdj_web_audio_test_render_calls"](),
          acknowledgedGeneration:
            Module["_lmdj_web_audio_test_ack_generation"](),
        };
      },

      startCalls() {
        return Module["_lmdj_web_audio_test_start_calls"]();
      },

      directOutputConnections() {
        return Module[
          "_lmdj_web_audio_test_direct_output_connections"
        ]();
      },

      async runDirectOutputContinuationProof() {
        if (Module["_lmdj_web_audio_test_reset_output_energy"]() !== 1) {
          throw new Error("output energy reset failed");
        }
        const renderCallsBefore =
          Module["_lmdj_web_audio_test_render_calls"]();
        const trigger = await submit("trigger", {slot: 0, velocity: 127});
        if (!trigger.ok) throw new Error(JSON.stringify(trigger));
        const deadline = performance.now() + 3_000;
        let renderCallsAfter = renderCallsBefore;
        let outputEnergy = 0;
        while (performance.now() < deadline) {
          renderCallsAfter = Module["_lmdj_web_audio_test_render_calls"]();
          outputEnergy = Module["_lmdj_web_audio_test_output_energy"]();
          if (renderCallsAfter > renderCallsBefore && outputEnergy > 0) break;
          await delay(2);
        }
        return {renderCallsBefore, renderCallsAfter, outputEnergy};
      },

      hostStatus() {
        return submit("host.status", {});
      },

      async validateUnsupportedConfiguration({sampleRate, renderQuantum}) {
        const result = Module[
          "_lmdj_web_audio_test_validate_configuration"
        ](sampleRate, renderQuantum);
        if (result !== -4 && result !== -5) {
          throw new Error(`configuration validator returned ${result}`);
        }
        const activation = await waitForUnsupportedFailure();
        return {activation, hostStatus: await submit("host.status", {})};
      },

      async runBootstrapFailureProof(selectedFatal) {
        const codes = {
          worklet_thread_start_failed: 5,
          processor_create_failed: 6,
          node_create_failed: 7,
          coordinator_install_failed: 10,
        };
        if (selectedFatal === "bootstrap_timeout") {
          if (Module["_lmdj_web_audio_bootstrap_timeout"]() !== 1) {
            throw new Error("bootstrap timeout injection failed");
          }
        } else {
          const code = codes[selectedFatal];
          if (!code || Module[
            "_lmdj_web_audio_test_bootstrap_failure"
          ](code) !== 1) {
            throw new Error(`bootstrap failure injection failed: ${selectedFatal}`);
          }
        }
        const context = new AudioContext({sampleRate: 48_000});
        await context.resume();
        const handle = host.registerAudioContext(context);
        const activation = await host.startAudioWorklet(handle);
        return {
          activation,
          controlFailureCommitted:
            Module["_lmdj_web_audio_control_failure_committed"](),
          hostStatus: await submit("host.status", {}),
          snapshotReload: await submit(
            "snapshot.reload", {pattern_id: crypto.randomUUID()}),
          trigger: await submit("trigger", {slot: 0, velocity: 127}),
        };
      },

      invokeAdapterShape({inputs, outputs, channels, frames}) {
        if (inputs !== 0 || outputs !== 1 || channels !== 2) {
          throw new TypeError("the conformance seam varies frames only");
        }
        const before = Module["_lmdj_web_audio_test_render_calls"]();
        const returned = Module["_lmdj_web_audio_test_invalid_shape"](frames);
        return {
          returned: returned === 1,
          fatal: fatalNames[Module["_lmdj_web_audio_fatal"]()],
          gate: gateNames[Module["_lmdj_web_audio_test_gate_state"]()],
          expectedFrames: 128,
          observedFrames: Module["_lmdj_web_audio_test_observed_frames"](),
          engineRenderCalls:
            Module["_lmdj_web_audio_test_render_calls"]() - before,
        };
      },

      dispatchProcessorError() {
        if (Module["_lmdj_web_audio_test_processor_error"]() !== 1) {
          throw new Error("processor error injection failed");
        }
      },

      async waitForFatal() {
        const deadline = performance.now() + 30_000;
        while (performance.now() < deadline) {
          const gateClosed =
            Module["_lmdj_web_audio_test_gate_closed"]() === 1;
          const callbackInFlight =
            Module["_lmdj_web_audio_test_in_flight"]() === 1;
          const fatalCode = Module["_lmdj_web_audio_fatal"]();
          const controlFailureCommitted =
            Module["_lmdj_web_audio_control_failure_committed"]() === 1;
          if (
            gateClosed &&
            !callbackInFlight &&
            fatalCode === 11 &&
            controlFailureCommitted
          ) {
            const callsAtFatal =
              Module["_lmdj_web_audio_test_render_calls"]();
            await delay(20);
            return {
              fatal: fatalNames[fatalCode],
              callbackGate: "closed",
              callbackInFlight: 0,
              controlFailureCommitted,
              renderCallsAtFatal: callsAtFatal,
              renderCallsAfterFatal:
                Module["_lmdj_web_audio_test_render_calls"](),
            };
          }
          await delay(2);
        }
        throw new Error("processor fatal state timed out");
      },

      async runGenerationMismatchProof() {
        const prepared = await prepareAndTrigger();
        await waitForRenderProof(prepared.controlGeneration);
        const acknowledgedGeneration =
          Module["_lmdj_web_audio_test_ack_generation"]();
        const expectedGeneration = acknowledgedGeneration + 1;
        return {
          expectedGeneration,
          acknowledgedGeneration,
          accepted:
            Module["_lmdj_web_audio_test_generation_matches"](
              expectedGeneration) === 1,
          reason: "generation_mismatch",
        };
      },

      async runQuiescenceTimeoutProof(timeoutMs) {
        const startedAt = performance.now();
        if (Module.ccall(
          "lmdj_web_audio_test_quiescence_timeout",
          "number",
          ["number"],
          [timeoutMs],
        ) !== 1) {
          throw new Error("quiescence timeout proof was rejected");
        }
        const watchdogDeadline = startedAt + 500;
        let serialized = null;
        while (performance.now() < watchdogDeadline) {
          serialized = Module.ccall(
            "lmdj_web_audio_test_quiescence_timeout_result",
            "string",
            [],
            [],
          );
          if (serialized) break;
          await delay(2);
        }
        return {
          ...(!serialized
            ? {completed: false}
            : JSON.parse(serialized)),
          observed_wall_ms: performance.now() - startedAt,
          fatal: fatalNames[Module["_lmdj_web_audio_fatal"]()],
          gate: gateNames[Module["_lmdj_web_audio_test_gate_state"]()],
          callback_in_flight:
            Module["_lmdj_web_audio_test_in_flight"](),
        };
      },

      async runSuspendReactivateProof() {
        const prepared = await prepareProject();
        const context = contexts.get(startRecord?.contextHandle);
        if (!(context instanceof AudioContext)) {
          throw new Error("registered AudioContext is unavailable");
        }
        const firstActivation = await submit("audio.activate", {});
        if (!firstActivation.ok) throw new Error(JSON.stringify(firstActivation));
        const firstAcknowledgement =
          Module["_lmdj_web_audio_test_ack_generation"]();
        const liveReload = await submit(
          "snapshot.reload", {pattern_id: prepared.patternId});
        if (!liveReload.ok) throw new Error(JSON.stringify(liveReload));
        const latestGeneration = liveReload.result.generation;
        const liveAcknowledgement =
          Module["_lmdj_web_audio_test_ack_generation"]();
        const suspended = await submit("audio.suspend", {});
        const paused = {
          gate: gateNames[Module["_lmdj_web_audio_test_gate_state"]()],
          callbackInFlight: Module["_lmdj_web_audio_test_in_flight"](),
        };
        await context.suspend();
        const heartbeatBeforeResume =
          Module["_lmdj_web_audio_callback_heartbeat"]();
        await context.resume();
        const heartbeatDeadline = performance.now() + 1_000;
        let heartbeatAfterResume =
          Module["_lmdj_web_audio_callback_heartbeat"]();
        while (
          heartbeatAfterResume === heartbeatBeforeResume &&
          performance.now() < heartbeatDeadline
        ) {
          await delay(0);
          heartbeatAfterResume =
            Module["_lmdj_web_audio_callback_heartbeat"]();
        }
        if (heartbeatAfterResume === heartbeatBeforeResume) {
          throw new Error("AudioWorklet callback did not resume");
        }
        const secondActivation = await submit("audio.activate", {});
        if (!secondActivation.ok) {
          throw new Error(JSON.stringify(secondActivation));
        }
        const secondAcknowledgement =
          Module["_lmdj_web_audio_test_ack_generation"]();
        return {
          ...prepared,
          firstAcknowledgement,
          latestGeneration,
          liveAcknowledgement,
          suspended,
          paused,
          heartbeatBeforeResume,
          heartbeatAfterResume,
          secondActivation,
          secondAcknowledgement,
        };
      },

      // #2345: a running context keeps admitting paused callbacks. Hold one,
      // borrow included, and prove activation waits for it instead of
      // refusing while it is in flight.
      async runPausedBorrowActivationProof() {
        await prepareProject();
        if (Module["_lmdj_web_audio_test_physical_fence_arm"](4) !== 1) {
          throw new Error("paused callback fence could not be armed");
        }
        const heldDeadline = performance.now() + 5_000;
        while ((Module["_lmdj_web_audio_test_physical_fence_stage"]() & 4) === 0) {
          if (performance.now() >= heldDeadline) {
            throw new Error("no paused callback was held");
          }
          await delay(1);
        }
        const held = {
          gate: gateNames[Module["_lmdj_web_audio_test_gate_state"]()],
          callbackInFlight: Module["_lmdj_web_audio_test_in_flight"](),
        };
        const waitsBefore =
          Module["_lmdj_web_audio_test_begin_rendering_borrow_waits"]() >>> 0;
        let settledWhileHeld = false;
        let released = false;
        const activation = submit("audio.activate", {}).finally(() => {
          if (!released) settledWhileHeld = true;
        });
        // Release only once begin_rendering has met the held borrow, so the
        // proof covers its wait and not merely the readiness precheck.
        const waitDeadline = performance.now() + 2_000;
        let beginMetHeldBorrow = false;
        while (!settledWhileHeld && performance.now() < waitDeadline) {
          if ((Module["_lmdj_web_audio_test_begin_rendering_borrow_waits"]() >>> 0) !==
              waitsBefore) {
            beginMetHeldBorrow = true;
            break;
          }
          await delay(1);
        }
        released = true;
        Module["_lmdj_web_audio_test_physical_fence_release"](4);
        return {held, beginMetHeldBorrow, settledWhileHeld,
          activation: await activation};
      },
    });
  }
  /* LMDJ_WEB_AUDIO_CONFORMANCE_API_END */

  const previousInitialized = Module["onRuntimeInitialized"];
  Module["onRuntimeInitialized"] = async () => {
    if (typeof previousInitialized === "function") previousInitialized();
    Module.wasmMemory = wasmMemory;
    const deadline = performance.now() + 30_000;
    while (
      Module["_lmdj_web_audio_state"]() === -2 &&
      performance.now() < deadline
    ) await delay(2);
    if (Module["_lmdj_web_audio_state"]() === -2) {
      throw new Error("formal Web Runtime Host initialization timed out");
    }
    const terminalTokenAccepted = Module.ccall(
      "lmdj_web_host_set_terminal_token",
      "number",
      ["string", "number"],
      [terminalToken, terminalToken.length],
    );
    if (terminalTokenAccepted !== 0) {
      throw new Error("formal Web Runtime Host terminal token was rejected");
    }
    host.runtimeInitialized = true;
    /* LMDJ_WEB_AUDIO_CONFORMANCE_INSTALL_BEGIN */
    if (typeof Module["_lmdj_web_audio_test_poll"] === "function") {
      window.lmdjWebRuntimeHostTest = createConformanceApi();
    }
    /* LMDJ_WEB_AUDIO_CONFORMANCE_INSTALL_END */
  };
}

if (ENVIRONMENT_IS_PTHREAD && typeof BroadcastChannel === "function") {
  const terminalChannel = new BroadcastChannel(
    "lmdj.web-runtime-host.terminal.v1");
  let terminalReleaseToken = null;
  terminalChannel.addEventListener("message", (event) => {
    const token = event.data?.token;
    if (
      event.data?.type !== "release-and-close" ||
      typeof token !== "string"
    ) {
      return;
    }
    if (terminalReleaseToken !== null) {
      if (token !== terminalReleaseToken) {
        // Other tokens still require the original native authorization.
        Module.ccall(
          "lmdj_web_host_authorize_terminal_release",
          "number",
          ["string", "number"],
          [token, token.length],
        );
      }
      return;
    }
    terminalReleaseToken = token;
    let authorized = false;
    let writersReleased = false;
    const releaseWhenReady = () => {
      if (!authorized) {
        const authorization = Module.ccall(
          "lmdj_web_host_authorize_terminal_release",
          "number",
          ["string", "number"],
          [token, token.length],
        );
        if (authorization === 2) {
          setTimeout(releaseWhenReady, 2);
          return;
        }
        if (authorization !== 1) {
          terminalReleaseToken = null;
          return;
        }
        // Native authorization is a one-shot ready -> authorized transition.
        authorized = true;
      }
      if (!writersReleased) {
        try {
          writersReleased = LmdjOpfs.releaseAllWriters() === true;
        } catch (_) {
          // An unknown drain outcome retains its owners and authorization.
        }
      }
      if (!writersReleased) {
        setTimeout(releaseWhenReady, 2);
        return;
      }
      let completed;
      try {
        completed = Module.ccall(
          "lmdj_web_host_complete_terminal_release",
          "number",
          ["string", "number", "number"],
          [token, token.length, 1],
        );
      } catch (_) {
        // Physical release alone cannot stand in for a native completion ACK.
      }
      if (completed !== 1) {
        setTimeout(releaseWhenReady, 2);
        return;
      }
      terminalChannel.postMessage({
        type: "released-and-closed",
        token,
      });
      terminalChannel.close();
      globalThis.close();
    };
    releaseWhenReady();
  });
}
