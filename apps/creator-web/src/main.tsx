import {createRoot} from "react-dom/client";
import {createRuntimeSession} from
  "@lmdj/web-runtime-platform/runtime_session.mjs";
import {WEB_RUNTIME_IDENTITY} from
  "../../../products/lmdj/generated/web-runtime-identity.mjs";

import {App} from "./app";
import type {CreatorRuntimeSession} from "./runtime/runtime_types";
import "./styles.css";

const root = document.getElementById("root");
if (root === null) throw new Error("Creator root is missing");

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
    seams,
  }) as CreatorRuntimeSession;
}

createRoot(root).render(
  <App runtimeFactory={createCreatorRuntimeSession} />,
);
