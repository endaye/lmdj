import {createDiagnosticClient} from
  "../../../packages/web-runtime-platform/web/diagnostic_client.mjs";
import {createUserGestureToken} from
  "../../../packages/web-runtime-platform/web/input_adapters.mjs";
import {createRuntimeSession} from
  "../../../packages/web-runtime-platform/web/runtime_session.mjs";
import {createDiagnosticProjectCoordinator} from "./diagnostic_project.mjs";


const ASSEMBLY_IDENTITY = Object.freeze({
  distributionContract: "lmdj.web-runtime-host.distribution.v1",
  hostId: "web-runtime-host",
  hostVersion: "1.2.0",
  platformVersion: "0.1.0",
  productBuild: "1.0.16.0",
  protocolVersion: 1,
});
const MANIFEST_SOURCE = Object.freeze({
  heapBytes: 536_870_912,
  resourceLimits: Object.freeze({
    decoded_float_pcm_bytes_per_bank: 67_108_864,
    decoded_float_pcm_bytes_total: 134_217_728,
    decoded_frames_per_pad: 240_000,
    imported_wav_bytes: 1_048_576,
  }),
  emscripten: Object.freeze({
    emcc_version:
      "emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) " +
      "6.0.5 (1db513782be24469589d7cb8a1f1834e9a33f271)",
    emscripten_releases_revision:
      "dbd755b5da399329c2576f6e3dfa7f419f5d8409",
    emsdk_revision: "dfb9d1a46c3bb8f52e1e6324be23123b9d73c190",
    emsdk_tag: "6.0.5",
  }),
  expectedAssets: Object.freeze([
    Object.freeze({
      prefix: "assets/diagnostic-client.",
      suffix: ".mjs",
      role: "platform_module",
    }),
    Object.freeze({
      prefix: "assets/diagnostic-project.",
      suffix: ".mjs",
      role: "host_module",
    }),
    Object.freeze({
      prefix: "assets/input-adapters.",
      suffix: ".mjs",
      role: "platform_module",
    }),
    Object.freeze({prefix: "assets/main.", suffix: ".mjs", role: "host_main"}),
    Object.freeze({
      prefix: "assets/preflight.",
      suffix: ".mjs",
      role: "platform_module",
    }),
    Object.freeze({
      prefix: "assets/project-bundle-reader.",
      suffix: ".mjs",
      role: "platform_module",
    }),
    Object.freeze({
      prefix: "assets/protocol.",
      suffix: ".mjs",
      role: "platform_module",
    }),
    Object.freeze({
      prefix: "assets/runtime.",
      suffix: ".js",
      role: "runtime_script",
    }),
    Object.freeze({
      prefix: "assets/runtime.",
      suffix: ".wasm",
      role: "runtime_wasm",
    }),
    Object.freeze({
      prefix: "assets/runtime-loader.",
      suffix: ".mjs",
      role: "platform_module",
    }),
    Object.freeze({
      prefix: "assets/runtime-session.",
      suffix: ".mjs",
      role: "platform_module",
    }),
    Object.freeze({
      prefix: "assets/state-machine.",
      suffix: ".mjs",
      role: "platform_module",
    }),
    Object.freeze({prefix: "assets/styles.", suffix: ".css", role: "host_style"}),
  ]),
});

function isPositiveInteger(value) {
  return Number.isInteger(value) && value > 0;
}

export function createWebRuntimeHostController(options = {}) {
  const document = options.document;
  const window = options.window;
  const crypto = options.crypto ?? window?.crypto;
  const pads = [
    ...(document?.querySelectorAll?.("button[data-bank][data-pad]") ?? []),
  ];
  const listeners = [];
  let started = false;
  let closing = false;
  let session;

  function element(id) {
    return document?.getElementById?.(id) ?? null;
  }

  function listen(target, type, listener) {
    if (typeof target?.addEventListener !== "function") {
      return;
    }
    target.addEventListener(type, listener);
    listeners.push(() => target.removeEventListener(type, listener));
  }

  function renderPressed(slots) {
    if (!Array.isArray(slots)) {
      return;
    }
    const active = new Set(slots);
    for (const pad of pads) {
      const slot = Number.parseInt(pad.id.slice(4), 10);
      pad.setAttribute("aria-pressed", active.has(slot) ? "true" : "false");
    }
  }

  session = options.session ?? createRuntimeSession({
    document,
    window,
    navigator: options.navigator ?? window?.navigator,
    crypto,
    manifestSource: options.manifestSource ?? MANIFEST_SOURCE,
    assemblyIdentity: options.assemblyIdentity ?? ASSEMBLY_IDENTITY,
    inputConfiguration: {
      padBindings: pads.map((pad) => Object.freeze({
        element: pad,
        slot: Object.freeze({
          bank: Number.parseInt(pad.dataset.bank, 10),
          pad: Number.parseInt(pad.dataset.pad, 10),
        }),
      })),
      onPressedChange: renderPressed,
    },
    seams: options.seams ?? options,
  });
  const diagnosticClient =
    options.diagnosticClient ?? createDiagnosticClient(session);
  const diagnosticProject = options.diagnosticProject ??
    createDiagnosticProjectCoordinator({
      storage: options.storage ?? window?.localStorage,
      crypto,
      session,
      diagnosticClient,
    });

  function diagnostics() {
    return Object.freeze({
      ...session.diagnostics(),
      ...diagnosticProject.diagnostics(),
    });
  }

  function render() {
    const value = diagnostics();
    const state = element("host-state");
    if (state) {
      state.textContent = value.state;
    }
    const output = element("diagnostics");
    if (output) {
      output.textContent = JSON.stringify(value, null, 2);
    }
    const diagnosticState = element("diagnostic-project-state");
    if (diagnosticState) {
      diagnosticState.textContent = value.diagnostic_project_state;
    }
    const load = element("diagnostic-project-load");
    if (load) {
      const loading = value.diagnostic_project_state === "loading";
      load.disabled = loading || closing;
      load.setAttribute("aria-busy", loading ? "true" : "false");
    }
    const activate = element("audio-activate");
    if (activate) {
      activate.disabled = !(
        value.diagnostic_project_state === "ready" &&
        isPositiveInteger(value.diagnostic_project_generation) &&
        !closing
      );
    }
  }

  async function loadDiagnosticProject() {
    if (closing || session.diagnostics().state !== "audio-suspended") {
      return false;
    }
    const pending = diagnosticProject.load();
    render();
    const result = await pending;
    render();
    return result.state === "ready";
  }

  async function activateAudio(token) {
    const value = diagnosticProject.diagnostics();
    if (
      value.diagnostic_project_state !== "ready" ||
      !isPositiveInteger(value.diagnostic_project_generation)
    ) {
      return false;
    }
    const activated = await session.activateAudio(token);
    render();
    return activated;
  }

  async function start() {
    if (started) {
      return false;
    }
    started = true;
    session.subscribeHostState(render);
    session.subscribeRuntimeOutcome(render);
    listen(window, "pagehide", () => diagnosticProject.invalidate());
    listen(element("diagnostic-project-load"), "click", loadDiagnosticProject);
    listen(element("audio-activate"), "click", (event) => {
      try {
        activateAudio(createUserGestureToken(event));
      } catch {
        render();
      }
    });
    listen(element("audio-suspend"), "click", () => session.suspendAudio());
    listen(element("midi-enable"), "click", () => session.requestMidi());
    const result = await session.start();
    render();
    return result;
  }

  async function close() {
    closing = true;
    diagnosticProject.invalidate();
    const result = await session.close();
    for (const dispose of listeners.splice(0)) {
      dispose();
    }
    render();
    return result;
  }

  return Object.freeze({
    start,
    loadDiagnosticProject,
    activateAudio,
    suspendAudio: session.suspendAudio,
    enableMidi: session.requestMidi,
    trigger: session.trigger,
    close,
    diagnostics,
    get state() {
      return session.diagnostics().state;
    },
  });
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  const controller = createWebRuntimeHostController({
    document,
    window,
    seams: window.__LMDJ_WEB_HOST_SEAMS__,
  });
  window.lmdjWebRuntimeController = controller;
  controller.start();
}
