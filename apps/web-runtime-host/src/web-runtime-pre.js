if (typeof window !== "undefined") {
  globalThis.Module = Module;
  const PUBLICATION_SETTLEMENT_WATCHDOG_MS = 1_000;
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

  let startRecord = null;
  function startAudioWorklet(handle) {
    if (!Number.isInteger(handle) || handle <= 0 || !contexts.has(handle)) {
      return Promise.reject(
        new TypeError("a registered AudioContext handle is required"));
    }
    if (startRecord !== null) {
      if (startRecord.handle !== handle) {
        return Promise.reject(
          new TypeError("the AudioWorklet is bound to another context"));
      }
      return startRecord.promise;
    }
    const context = contexts.get(handle);
    const promise = (async () => {
      const deadline = performance.now() + 30_000;
      while (!host.runtimeInitialized && performance.now() < deadline) {
        await delay(2);
      }
      const result = Module["_lmdj_web_audio_start"](handle);
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
            outputs: 1,
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
          outputs: 1,
          channels: 2,
          frames: 128,
        };
      }
      if (finalState === -1) return committedFatalResult();
      Module["_lmdj_web_audio_bootstrap_timeout"]();
      return committedFatalResult();
    })();
    startRecord = {handle, promise};
    return promise;
  }

  const transportEncoder = new TextEncoder();
  const transportDecoder = new TextDecoder("utf-8", {fatal: true});
  const pendingRequests = new Map();
  const notificationSubscribers = new Set();
  const failureSubscribers = new Set();
  const terminalToken = crypto.randomUUID();
  const terminalChannel = new BroadcastChannel(
    "lmdj.web-runtime-host.terminal.v1");
  let pollScheduled = false;
  let transportTerminated = false;
  let terminalTransportError = null;
  let terminalOwnerReleased = false;
  let terminalFailureDelivered = false;
  let terminalAckTimeout = 0;
  let host;

  function transportFailure(code, message, details = {}) {
    const error = new Error(message);
    error.code = code;
    error.details = Object.freeze({...details});
    return error;
  }

  function restartRequiredFailure() {
    return transportFailure(
      "HOST_RESTART_REQUIRED",
      "Project publication settlement did not complete; restart and inspect before retrying",
      {
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

  function releaseTerminalOwner() {
    terminalChannel.postMessage({
      type: "release-and-close",
      token: terminalToken,
    });
    terminalAckTimeout = window.setTimeout(() => {
      terminateRuntimeWorkers();
      terminalChannel.close();
      deliverTerminalFailure();
    }, 100);
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
    const entries = [...pendingRequests.entries()];
    pendingRequests.clear();
    for (const [requestId, pending] of entries) {
      cancelControlRequest(requestId);
      window.clearTimeout(pending.timeout);
      pending.reject(error);
    }
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
    let released;
    try {
      released = Module.ccall(
        "lmdj_web_host_consume_terminal_release",
        "number",
        ["string", "number"],
        [terminalToken, terminalToken.length],
      );
    } catch {
      return;
    }
    if (released !== 0 && released !== 1) return;
    terminalOwnerReleased = released === 1;
    window.clearTimeout(terminalAckTimeout);
    terminateRuntimeWorkers();
    terminalChannel.close();
    deliverTerminalFailure();
  });

  function linearizeRequestDeadline(requestId, pending) {
    const remaining = pending.deadlineAt - performance.now();
    if (remaining > 0) {
      pending.timeout = window.setTimeout(
        () => onRequestDeadline(requestId), remaining);
      return true;
    }
    if (
      pending.deadlineLinearized === true ||
      cancelControlRequest(requestId) === 0
    ) {
      pending.deadlineLinearized = true;
      if (pending.settlementDeadlineAt === null) {
        pending.settlementDeadlineAt =
          performance.now() + publicationSettlementWatchdogMs;
      }
      const settlementRemaining =
        pending.settlementDeadlineAt - performance.now();
      if (settlementRemaining <= 0) {
        failClosed(restartRequiredFailure());
        return false;
      }
      pending.timeout = window.setTimeout(
        () => onRequestDeadline(requestId),
        Math.min(2, settlementRemaining),
      );
      return true;
    }
    failClosed(transportFailure(
      "HOST_TIMEOUT", "formal Web Host request timed out"));
    return false;
  }

  function onRequestDeadline(requestId) {
    const pending = pendingRequests.get(requestId);
    if (!pending || transportTerminated) return;
    linearizeRequestDeadline(requestId, pending);
  }

  function scheduleTransportPoll() {
    if (
      transportTerminated ||
      pollScheduled ||
      (!pendingRequests.size && !notificationSubscribers.size)
    ) {
      return;
    }
    pollScheduled = true;
    window.setTimeout(pollTransport, 2);
  }

  function pollTransport() {
    pollScheduled = false;
    if (transportTerminated) return;
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
            pending.resolve(message);
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
    scheduleTransportPoll();
  }

  const transport = Object.freeze({
    send(request, options = {}) {
      if (transportTerminated) {
        return Promise.reject(terminalTransportError);
      }
      if (!host.runtimeInitialized || pendingRequests.has(request.request_id)) {
        return Promise.reject(transportFailure(
          "HOST_STATE_INVALID",
          "formal Web Host transport is unavailable",
        ));
      }
      const envelope = transportEncoder.encode(JSON.stringify(request));
      const sidecar = options.sidecar instanceof Uint8Array
        ? options.sidecar
        : new Uint8Array();
      const deadlineMs = Number.isFinite(options.deadlineMs)
        ? Math.min(0xffff_ffff, Math.max(0, options.deadlineMs))
        : 30_000;
      const deadlineAt = performance.now() + deadlineMs;
      const submitted = Module.ccall(
        "lmdj_web_host_submit",
        "number",
        ["array", "number", "array", "number", "number"],
        [
          envelope,
          envelope.byteLength,
          sidecar,
          sidecar.byteLength,
          performance.timeOrigin + deadlineAt,
        ],
      );
      if (submitted !== 0) {
        return Promise.reject(transportFailure(
          submitted === 1 || submitted === 2
            ? "HOST_PROTOCOL_MISMATCH"
            : "HOST_STATE_INVALID",
          "formal Web Host request was rejected",
        ));
      }
      return new Promise((resolve, reject) => {
        const pending = {
          resolve,
          reject,
          timeout: 0,
          deadlineAt,
          deadlineLinearized: false,
          settlementDeadlineAt: null,
        };
        pendingRequests.set(request.request_id, pending);
        linearizeRequestDeadline(request.request_id, pending);
        scheduleTransportPoll();
      });
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
    },
    get terminated() {
      return transportTerminated;
    },
    get terminalOwnerReleased() {
      return terminalOwnerReleased;
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
    startAudioWorklet,
    transport,
    ...(deadlineProof === undefined ? {} : {deadlineProof}),
  };
  window.lmdjWebRuntimeHost = host;

  /* LMDJ_WEB_AUDIO_CONFORMANCE_API_BEGIN */
  function createConformanceApi() {
    const encoder = new TextEncoder();

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
      return {controlGeneration: snapshot.result.generation};
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
          if (gateClosed && !callbackInFlight && fatalCode === 11) {
            const callsAtFatal =
              Module["_lmdj_web_audio_test_render_calls"]();
            let hostStatus = null;
            while (performance.now() < deadline) {
              hostStatus = await submit("host.status", {});
              if (
                !hostStatus.ok &&
                hostStatus.error?.code === "HOST_STATE_INVALID"
              ) break;
              await delay(2);
            }
            await delay(20);
            return {
              fatal: fatalNames[fatalCode],
              callbackGate: "closed",
              callbackInFlight: 0,
              hostStatus,
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

      async runSuspendReactivateProof() {
        const prepared = await prepareProject();
        const firstActivation = await submit("audio.activate", {});
        if (!firstActivation.ok) throw new Error(JSON.stringify(firstActivation));
        const firstAcknowledgement =
          Module["_lmdj_web_audio_test_ack_generation"]();
        const suspended = await submit("audio.suspend", {});
        const paused = {
          gate: gateNames[Module["_lmdj_web_audio_test_gate_state"]()],
          callbackInFlight: Module["_lmdj_web_audio_test_in_flight"](),
        };
        const secondActivation = await submit("audio.activate", {});
        if (!secondActivation.ok) {
          throw new Error(JSON.stringify(secondActivation));
        }
        const secondAcknowledgement =
          Module["_lmdj_web_audio_test_ack_generation"]();
        return {
          ...prepared,
          firstAcknowledgement,
          suspended,
          paused,
          secondActivation,
          secondAcknowledgement,
        };
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
  terminalChannel.addEventListener("message", (event) => {
    const token = event.data?.token;
    if (
      event.data?.type !== "release-and-close" ||
      typeof token !== "string"
    ) {
      return;
    }
    const releaseWhenReady = () => {
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
      if (authorization !== 1) return;
      let released = false;
      try {
        LmdjOpfs.releaseAllWriters();
        released = true;
      } finally {
        const completed = Module.ccall(
          "lmdj_web_host_complete_terminal_release",
          "number",
          ["string", "number", "number"],
          [token, token.length, released ? 1 : 0],
        );
        if (completed === 1) {
          terminalChannel.postMessage({
            type: "released-and-closed",
            token,
          });
        }
        terminalChannel.close();
        globalThis.close();
      }
    };
    releaseWhenReady();
  });
}
