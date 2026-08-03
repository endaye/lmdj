if (typeof window !== "undefined") {
  Module["lmdjMainThreadProbeCount"] = 0;
  Module["lmdjAudioContext"] = null;
  Module["lmdjAudioNode"] = null;
  Module["lmdjChannelSplitter"] = null;
  Module["lmdjAnalyser"] = null;
  Module["lmdjRuntimeInitialized"] = false;

  const capabilityOrder = Object.freeze([
    "secureContext",
    "crossOriginIsolated",
    "sharedArrayBuffer",
    "webAssembly",
    "audioWorklet",
    "opfs",
    "opfsSyncAccessHandle",
    "opfsWritableReplace",
  ]);

  function inspectWorkerStorageCapabilities() {
    const workerSource = `
      self.onmessage = async () => {
        const result = {
          opfs: false,
          opfsSyncAccessHandle: false,
          opfsWritableReplace: false,
        };
        try {
          result.opfs = typeof navigator.storage?.getDirectory === "function";
          if (result.opfs) {
            const root = await navigator.storage.getDirectory();
            const file = await root.getFileHandle(".lmdj-capability-probe", {create: true});
            result.opfsSyncAccessHandle = typeof file.createSyncAccessHandle === "function";
            result.opfsWritableReplace = typeof file.createWritable === "function";
            await root.removeEntry(".lmdj-capability-probe");
          }
        } catch (error) {
          result.error = String(error);
        }
        self.postMessage(result);
      };
    `;
    const url = URL.createObjectURL(new Blob([workerSource], { type: "text/javascript" }));
    const worker = new Worker(url);
    return new Promise((resolve) => {
      const timeout = window.setTimeout(() => {
        worker.terminate();
        URL.revokeObjectURL(url);
        resolve({
          opfs: false,
          opfsSyncAccessHandle: false,
          opfsWritableReplace: false,
          error: "storage capability worker timed out",
        });
      }, 5_000);
      worker.onmessage = (event) => {
        window.clearTimeout(timeout);
        worker.terminate();
        URL.revokeObjectURL(url);
        resolve(event.data);
      };
      worker.onerror = (event) => {
        window.clearTimeout(timeout);
        worker.terminate();
        URL.revokeObjectURL(url);
        resolve({
          opfs: false,
          opfsSyncAccessHandle: false,
          opfsWritableReplace: false,
          error: event.message || "storage capability worker failed",
        });
      };
      worker.postMessage(null);
    });
  }

  async function capabilities() {
    const storage = await inspectWorkerStorageCapabilities();
    const values = {
      secureContext: window.isSecureContext === true,
      crossOriginIsolated: window.crossOriginIsolated === true,
      sharedArrayBuffer: typeof SharedArrayBuffer === "function",
      webAssembly: typeof WebAssembly === "object",
      audioWorklet:
        typeof AudioContext === "function" &&
        typeof AudioWorkletNode === "function",
      opfs: storage.opfs === true,
      opfsSyncAccessHandle: storage.opfsSyncAccessHandle === true,
      opfsWritableReplace: storage.opfsWritableReplace === true,
    };
    const missing = capabilityOrder.filter((name) => values[name] !== true);
    if (missing.length > 0) {
      return {
        status: "unsupported",
        error: {
          code: "UNSUPPORTED_WEB_RUNTIME",
          missing,
        },
        capabilities: values,
      };
    }
    return { status: "supported", missing: [], capabilities: values };
  }

  function parseJsonPointer(getter) {
    const pointer = getter();
    if (!pointer) {
      return null;
    }
    const serialized = Module["UTF8ToString"](pointer);
    return serialized ? JSON.parse(serialized) : null;
  }

  function outputPeak() {
    const analyser = Module["lmdjAnalyser"];
    if (!analyser) {
      return 0;
    }
    const samples = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(samples);
    let peak = 0;
    for (const sample of samples) {
      peak = Math.max(peak, Math.abs(sample));
    }
    return peak;
  }

  function unsupportedAudioRuntime(details) {
    return {
      status: "unsupported",
      error: {
        code: "UNSUPPORTED_WEB_RUNTIME",
        ...details,
      },
    };
  }

  function classifyAudioRuntime({sampleRate, observedFrames, quantumMismatch}) {
    if (quantumMismatch) {
      return unsupportedAudioRuntime({
        expected_render_quantum_frames: 128,
        observed_render_quantum_frames: observedFrames,
      });
    }
    if (sampleRate !== 0 && sampleRate !== 48_000) {
      return unsupportedAudioRuntime({
        expected_sample_rate: 48_000,
        observed_sample_rate: sampleRate,
      });
    }
    if (sampleRate === 0 || observedFrames === 0) {
      return {status: "pending"};
    }
    return {status: "supported"};
  }

  function snapshot() {
    const context = Module["lmdjAudioContext"];
    const node = Module["lmdjAudioNode"];
    const sampleRate = Module["_lmdj_get_observed_sample_rate"]();
    const observedFrames = Module["_lmdj_get_observed_frames"]();
    const quantumMismatch = Module["_lmdj_get_quantum_mismatch"]() === 1;
    return {
      runtimeInitialized: Module["lmdjRuntimeInitialized"] === true,
      control: {
        browserMainThread: Module["_lmdj_get_control_browser_main"](),
        done: Module["_lmdj_get_control_done"](),
        probes: Module["_lmdj_get_control_probes"](),
        mainThreadProxyCount: Module["lmdjMainThreadProbeCount"],
      },
      wasmfs: Module["_lmdj_get_wasmfs_ok"](),
      lease: parseJsonPointer(Module["_lmdj_get_lease_json"]),
      iteration: parseJsonPointer(Module["_lmdj_get_iteration_json"]),
      replacement: parseJsonPointer(Module["_lmdj_get_replacement_json"]),
      audio: {
        state: Module["_lmdj_get_audio_state"](),
        ready: Module["_lmdj_get_audio_ready"](),
        configuredChannels: Module["_lmdj_get_configured_channels"](),
        nodeChannels: node ? node.channelCount : 0,
        numberOfOutputs: node ? node.numberOfOutputs : 0,
        sampleRate,
        observedFrames,
        quantumMismatch,
        sharedMarker: Module["_lmdj_get_shared_marker"](),
        contextTime: context ? context.currentTime : 0,
        outputPeak: outputPeak(),
        runtime: classifyAudioRuntime({
          sampleRate,
          observedFrames,
          quantumMismatch,
        }),
      },
    };
  }

  function activateAudioProbe() {
    const result = Module["_lmdj_start_audio_probe"]();
    const runtime = snapshot().audio.runtime;
    if (result === -3 && runtime.status === "unsupported") {
      return runtime;
    }
    if (result !== 1) {
      throw new Error(`audio probe activation failed: ${result}`);
    }
    return runtime;
  }

  function observeQuantumForTest(frames) {
    Module["_lmdj_observe_quantum_for_test"](frames);
    return snapshot().audio;
  }

  window["lmdjToolchainProbe"] = Object.freeze({
    capabilityOrder,
    capabilities,
    classifyAudioRuntime,
    snapshot,
    activateAudioProbe,
    observeQuantumForTest,
  });

  const previousInitialized = Module["onRuntimeInitialized"];
  Module["onRuntimeInitialized"] = () => {
    if (typeof previousInitialized === "function") {
      previousInitialized();
    }
    Module["lmdjRuntimeInitialized"] = true;
    const button = document.getElementById("activate");
    const status = document.getElementById("status");
    button.disabled = false;
    button.addEventListener("click", () => {
      try {
        status.value = JSON.stringify(activateAudioProbe());
      } catch (error) {
        status.value = String(error);
      }
    });
    status.value = "runtime initialized";
  };
}
