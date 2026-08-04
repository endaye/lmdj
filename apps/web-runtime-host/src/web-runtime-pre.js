if (typeof window !== "undefined") {
  globalThis.Module = Module;

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
  async function waitForUnsupportedFailure(deadline) {
    while (
      Module["_lmdj_web_audio_control_failure_committed"]() !== 1 &&
      performance.now() < deadline
    ) await delay(2);
    return Module["_lmdj_web_audio_control_failure_committed"]() === 1
      ? unsupportedResult()
      : {ok: false, fatal: "control_failure_timeout"};
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
        return waitForUnsupportedFailure(deadline);
      }
      if (result !== 1 && result !== 2 && result !== 3) {
        const fatalCode = Module["_lmdj_web_audio_fatal"]();
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
          const fatalCode = Module["_lmdj_web_audio_fatal"]();
          return {ok: false, fatal: fatalNames[fatalCode] ?? "unknown"};
        }
        await delay(5);
      }
      return {ok: false, fatal: "worklet_start_timeout"};
    })();
    startRecord = {handle, promise};
    return promise;
  }

  const host = {
    runtimeInitialized: false,
    registerAudioContext,
    startAudioWorklet,
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
          ["array", "number", "array", "number"],
          [envelope, envelope.byteLength, sidecar, sidecar.byteLength],
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

    async function waitForRenderProof(expected) {
      const deadline = performance.now() + 30_000;
      let status = null;
      while (performance.now() < deadline) {
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
      Module["_lmdj_web_audio_test_clear_outcomes"]();
      if (Module["_lmdj_web_audio_test_request_outcomes"]() !== 1) {
        throw new Error("outcome drain request was rejected");
      }
      while (
        Module["_lmdj_web_audio_test_outcome_state"]() === 1 &&
        performance.now() < deadline
      ) await delay(2);
      const count = Module["_lmdj_web_audio_test_outcome_count"]();
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
        };
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
        const activation = await waitForUnsupportedFailure(
          performance.now() + 30_000);
        return {activation, hostStatus: await submit("host.status", {})};
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
    host.runtimeInitialized = true;
    /* LMDJ_WEB_AUDIO_CONFORMANCE_INSTALL_BEGIN */
    if (typeof Module["_lmdj_web_audio_test_poll"] === "function") {
      window.lmdjWebRuntimeHostTest = createConformanceApi();
    }
    /* LMDJ_WEB_AUDIO_CONFORMANCE_INSTALL_END */
  };
}
