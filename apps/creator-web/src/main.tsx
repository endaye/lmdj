import {createRoot} from "react-dom/client";
import {createRuntimeSession} from
  "@lmdj/web-runtime-platform/runtime_session.mjs";
import {createPerformanceMasterTap} from
  "@lmdj/web-runtime-platform/performance_master_capture.mjs";
import {createFetchCatalogClient} from
  "@lmdj/web-runtime-platform/soundset_catalog.mjs";
import performanceMasterTapUrl from
  "@lmdj/web-runtime-platform/performance_master_tap_worklet.js?url&no-inline";
import {WEB_RUNTIME_IDENTITY} from
  "../../../products/lmdj/generated/web-runtime-identity.mjs";
import {CREATOR_SOUND_SET_CATALOG_PATH} from
  "../../../products/lmdj/creator-defaults.mjs";

import {App} from "./app";
import {fitConsoleToStage} from "./components/hardware_console";
import {createRetainedAudioContext} from "./runtime/audio_clock";
import {registerOfflineShell} from "./runtime/offline_shell";
import {
  announceBuildIdentity,
  creatorBuildIdentity,
} from "./runtime/build_identity";
import {createBrowserProjectTakeover} from "./runtime/project_takeover";
import type {CreatorRuntimeSession} from "./runtime/runtime_types";
import "./styles.css";

const root = document.getElementById("root");
if (root === null) throw new Error("Creator root is missing");

const buildIdentity = creatorBuildIdentity(WEB_RUNTIME_IDENTITY);
announceBuildIdentity(buildIdentity);
Object.defineProperty(window, "__LMDJ_CREATOR_BUILD__", {
  value: buildIdentity,
  configurable: false,
  enumerable: false,
  writable: false,
});

// Product Assembly supplies the same-origin default proxy. Workspace/Host
// overrides stay outside Project Truth.
function soundSetCatalogEndpoint(): string | null {
  const injected = (
    window as Window & {__LMDJ_SOUNDSET_CATALOG__?: unknown}
  ).__LMDJ_SOUNDSET_CATALOG__;
  if (typeof injected === "string" && injected.length > 0) {
    return injected;
  }
  const configured = document
    .querySelector('meta[name="lmdj-soundset-catalog"]')
    ?.getAttribute("content");
  return configured !== null && configured !== undefined && configured !== ""
    ? configured
    : new URL(CREATOR_SOUND_SET_CATALOG_PATH, document.baseURI).href;
}

function createSoundSetCatalog(): ReturnType<
  typeof createFetchCatalogClient
> | null {
  const endpoint = soundSetCatalogEndpoint();
  if (endpoint === null) {
    return null;
  }
  try {
    return createFetchCatalogClient({
      endpoint,
      fetch: window.fetch.bind(window),
    });
  } catch {
    // A malformed endpoint is a Host configuration fault, not a reason to
    // refuse to start: the Workspace Set Store is still browsable.
    return null;
  }
}

function createCreatorRuntimeSession(): CreatorRuntimeSession {
  const host = WEB_RUNTIME_IDENTITY.hosts["creator-web"];
  const seams = (
    window as Window & {__LMDJ_WEB_HOST_SEAMS__?: Record<string, unknown>}
  ).__LMDJ_WEB_HOST_SEAMS__;
  return createRuntimeSession({
    document,
    window,
    navigator,
    crypto,
    assemblyIdentity: {
      distributionContract: host.distribution_contract,
      hostId: host.id,
      hostVersion: host.version,
      platformVersion: WEB_RUNTIME_IDENTITY.platform.version,
      productBuild: WEB_RUNTIME_IDENTITY.product_build,
      protocolVersion: WEB_RUNTIME_IDENTITY.protocol_version,
    },
    manifestSource: {
      heapBytes: WEB_RUNTIME_IDENTITY.heap_bytes,
      resourceLimits: WEB_RUNTIME_IDENTITY.resource_limits,
      performanceMasterTapUrl,
      emscripten: {
        emcc_version: WEB_RUNTIME_IDENTITY.emscripten.emcc_version,
        emscripten_releases_revision:
          WEB_RUNTIME_IDENTITY.emscripten.emscripten_releases_revision,
        emsdk_revision: WEB_RUNTIME_IDENTITY.emscripten.emsdk_revision,
        emsdk_tag: WEB_RUNTIME_IDENTITY.emscripten.emsdk_tag,
      },
      compatibleHosts: host.compatible_hosts,
      expectedAssets: host.expected_assets,
    },
    inputOwnership: "host",
    // The Creator's single session owner opts in to the global Pattern
    // transport; Project open/create then carry the negotiation marker.
    patternTransport: true,
    soundsetCatalog: createSoundSetCatalog(),
    seams: {
      // The session owns the AudioContext; the factory retains a reference
      // so the Host audio clock converts engine frames on the same device
      // clock the engine renders to.
      createAudioContext: createRetainedAudioContext,
      createPerformanceMasterTap,
      ...seams,
    },
  });
}

createRoot(root).render(
  <App
    runtimeFactory={createCreatorRuntimeSession}
    buildIdentity={buildIdentity}
    projectTakeover={createBrowserProjectTakeover()}
  />,
);

void registerOfflineShell(document, navigator, crypto, window.fetch.bind(window), phase => {
  Object.defineProperty(window, "__LMDJ_OFFLINE_SHELL__", {value: phase, configurable: true});
  window.dispatchEvent(new CustomEvent("lmdj-offline-shell", {detail: phase}));
});

// Static shell dressing: the header/footer live in index.html so unit tests
// that render <App/> never see them; both slots no-op when absent.
const identitySlot = document.querySelector("[data-build-identity]");
if (identitySlot !== null) {
  identitySlot.textContent =
    `v${buildIdentity.productBuild} · creator-web ${buildIdentity.hostVersion}`;
}

// Stage fit (Desktop Final T2). The console scales proportionally to fill
// the stage (#root, the flex item between header and footer) and centres
// itself; under (max-width: 959px) and (orientation: portrait) it is also
// turned 90° so the device reads as landscape. styles.css pins the workspace
// to the stage's top-left corner; CSS cannot divide two lengths, so the
// scale is computed here and applied about that corner.
const stagePortrait = window.matchMedia(
  "(max-width: 959px) and (orientation: portrait)",
);
let fittedWorkspace: HTMLElement | null = null;
function fitStage(): void {
  const workspace = document.querySelector<HTMLElement>(".hardware-workspace");
  if (workspace === null) return;
  fittedWorkspace = workspace;
  workspace.style.width = "";
  workspace.style.height = "";
  workspace.style.transform = "";
  workspace.style.transformOrigin = "";
  const stage = workspace.parentElement;
  if (stage === null) return;
  const naturalWidth = workspace.scrollWidth;
  const naturalHeight = workspace.scrollHeight;
  const fit = fitConsoleToStage(
    {width: stage.clientWidth, height: stage.clientHeight},
    {width: naturalWidth, height: naturalHeight},
    stagePortrait.matches,
  );
  if (fit === null) return;
  workspace.style.width = `${naturalWidth}px`;
  workspace.style.height = `${naturalHeight}px`;
  workspace.style.transformOrigin = "0 0";
  workspace.style.transform = `translate(${fit.dx}px, ${fit.dy}px)${
    fit.rotate ? " rotate(-90deg)" : ""} scale(${fit.scale})`;
}
stagePortrait.addEventListener("change", fitStage);
window.addEventListener("resize", fitStage);
window.addEventListener("load", fitStage);
requestAnimationFrame(fitStage);
// The App commits .hardware-workspace only after the Runtime session attempt
// resolves, later than any of the events above, and a later remount produces
// a fresh element without these inline styles. Keep watching and refit
// whenever the mounted element changes; the identity check keeps steady-state
// mutations free of refits, and the childList-only filter keeps our own
// inline-style writes from retriggering.
const stageMount = new MutationObserver(() => {
  const workspace = document.querySelector<HTMLElement>(".hardware-workspace");
  if (workspace === null || workspace === fittedWorkspace) return;
  fittedWorkspace = workspace;
  fitStage();
});
stageMount.observe(root, {childList: true, subtree: true});
