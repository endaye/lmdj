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

import {App} from "./app";
import {
  announceBuildIdentity,
  creatorBuildIdentity,
} from "./runtime/build_identity";
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

// S11-D6: the Catalog endpoint is Workspace/Host settings and never Project
// Truth, so it is configured on the Host page and nowhere else. A Host that
// configures none browses whatever its Workspace Set Store already holds; the
// Creator invents no default endpoint of its own.
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
    : null;
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
      createPerformanceMasterTap,
      ...seams,
    },
  });
}

createRoot(root).render(
  <App
    runtimeFactory={createCreatorRuntimeSession}
    buildIdentity={buildIdentity}
  />,
);
