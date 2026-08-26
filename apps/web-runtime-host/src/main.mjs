import {createDiagnosticClient} from
  "../../../packages/web-runtime-platform/web/diagnostic_client.mjs";
import {createUserGestureToken} from
  "../../../packages/web-runtime-platform/web/input_adapters.mjs";
import {createRuntimeSession} from
  "../../../packages/web-runtime-platform/web/runtime_session.mjs";
import {WEB_RUNTIME_IDENTITY} from
  "../../../products/lmdj/generated/web-runtime-identity.mjs";
import {createDiagnosticProjectCoordinator} from "./diagnostic_project.mjs";

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

  const hostIdentity = WEB_RUNTIME_IDENTITY.hosts["web-runtime-host"];
  const generatedAssemblyIdentity = {
    distributionContract: hostIdentity.distribution_contract,
    hostId: hostIdentity.id,
    hostVersion: hostIdentity.version,
    platformVersion: WEB_RUNTIME_IDENTITY.platform.version,
    productBuild: WEB_RUNTIME_IDENTITY.product_build,
    protocolVersion: WEB_RUNTIME_IDENTITY.protocol_version,
  };
  const generatedManifestSource = {
    heapBytes: WEB_RUNTIME_IDENTITY.heap_bytes,
    resourceLimits: WEB_RUNTIME_IDENTITY.resource_limits,
    emscripten: {
      emcc_version: WEB_RUNTIME_IDENTITY.emscripten.emcc_version,
      emscripten_releases_revision:
        WEB_RUNTIME_IDENTITY.emscripten.emscripten_releases_revision,
      emsdk_revision: WEB_RUNTIME_IDENTITY.emscripten.emsdk_revision,
      emsdk_tag: WEB_RUNTIME_IDENTITY.emscripten.emsdk_tag,
    },
    expectedAssets: hostIdentity.expected_assets,
  };
  session = options.session ?? createRuntimeSession({
    document,
    window,
    navigator: options.navigator ?? window?.navigator,
    crypto,
    manifestSource: options.manifestSource ?? generatedManifestSource,
    assemblyIdentity: options.assemblyIdentity ?? generatedAssemblyIdentity,
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
    beginSequence: session.beginSequence,
    recordSequenceEvent: session.recordSequenceEvent,
    flushSequence: session.flushSequence,
    stopSequence: session.stopSequence,
    requestPatternSwitch: session.requestPatternSwitch,
    createPattern: session.createPattern,
    updateSequenceSettings: session.updateSequenceSettings,
    querySequenceStatus: session.querySequenceStatus,
    listSequenceRecovery: session.listSequenceRecovery,
    applySequenceRecovery: session.applySequenceRecovery,
    discardSequenceRecovery: session.discardSequenceRecovery,
    subscribeSequenceBarBoundary: session.subscribeSequenceBarBoundary,
    refreshSequenceDiagnostics: diagnosticProject.refreshSequenceAuthority,
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
