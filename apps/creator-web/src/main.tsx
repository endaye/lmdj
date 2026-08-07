import {createRoot} from "react-dom/client";
import {createRuntimeSession} from
  "@lmdj/web-runtime-platform/runtime_session.mjs";

import {App} from "./app";
import type {CreatorRuntimeSession} from "./runtime/runtime_types";
import "./styles.css";

const root = document.getElementById("root");
if (root === null) throw new Error("Creator root is missing");

const ASSEMBLY_IDENTITY = Object.freeze({
  distributionContract: "lmdj.creator-web.distribution.v1",
  hostId: "creator-web",
  hostVersion: "1.0.0",
  platformVersion: "0.1.0",
  productBuild: "1.0.16.0",
  protocolVersion: 1,
});
const MANIFEST_SOURCE = Object.freeze({
  heapBytes: 536_870_912,
  resourceLimits: Object.freeze({
    imported_wav_bytes: 1_048_576,
    decoded_frames_per_pad: 240_000,
    decoded_float_pcm_bytes_per_bank: 67_108_864,
    decoded_float_pcm_bytes_total: 134_217_728,
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
  compatibleHosts: Object.freeze([
    Object.freeze({host_id: "web-runtime-host", host_version: "1.2.0"}),
  ]),
  expectedAssets: Object.freeze([
    Object.freeze({prefix: "assets/main.", suffix: ".js", role: "host_main"}),
    Object.freeze({
      prefix: "assets/runtime.", suffix: ".js", role: "runtime_script",
    }),
    Object.freeze({
      prefix: "assets/runtime.", suffix: ".wasm", role: "runtime_wasm",
    }),
    Object.freeze({
      prefix: "assets/styles.", suffix: ".css", role: "host_style",
    }),
  ]),
});

function createCreatorRuntimeSession(): CreatorRuntimeSession {
  return createRuntimeSession({
    document,
    window,
    navigator,
    crypto,
    assemblyIdentity: ASSEMBLY_IDENTITY,
    manifestSource: MANIFEST_SOURCE,
    inputConfiguration: {
      keyboardMapping: {},
      padBindings: [],
    },
  }) as CreatorRuntimeSession;
}

createRoot(root).render(
  <App runtimeFactory={createCreatorRuntimeSession} />,
);
