import {
  createRequestEnvelope,
  deadlineForOperation,
} from "./protocol.mjs";


export function createPackagedRuntimeLocator({
  baseURI,
  runtimeScriptURL,
  runtimeWasmURL,
}) {
  const scriptURL = new URL(runtimeScriptURL, baseURI);
  const wasmURL = new URL(runtimeWasmURL, baseURI);
  const wasmRequestName = wasmURL.pathname.split("/").at(-1);
  return (path) => {
    if (path === "lmdj-web-runtime.js") {
      return scriptURL.href;
    }
    if (path === wasmRequestName) {
      return wasmURL.href;
    }
    return new URL(path, baseURI).href;
  };
}

export async function defaultRuntimeTerminator({
  runtime,
  audioContext,
  window,
}) {
  let transportTerminated = false;
  let transportTermination = null;
  try {
    if (typeof runtime?.transport?.terminate === "function") {
      transportTermination = Promise.resolve(runtime.transport.terminate());
      transportTerminated = true;
    }
  } catch {
    // Fall through to direct Worker termination.
  }
  if (!transportTerminated) {
    const workers = new Set(runtime?.workers ?? []);
    for (const worker of workers) {
      try {
        worker?.terminate?.();
      } catch {
        // Terminal cleanup is best effort and continues through every resource.
      }
    }
  }

  try {
    const deadlineMs = deadlineForOperation("host.close");
    const request = createRequestEnvelope({
      operation: "host.close",
      payload: {},
      crypto: window.crypto,
    });
    Promise.resolve(runtime?.transport?.send?.(request, {deadlineMs}))
      .catch(() => null);
  } catch {
    // A clean close attempt cannot delay terminal Worker termination.
  }

  if (transportTermination !== null) {
    await transportTermination.catch(() => {});
  }

  await Promise.resolve()
    .then(() => runtime?.worklet?.disconnect?.())
    .catch(() => {});
  await Promise.resolve()
    .then(() => runtime?.worklet?.port?.close?.())
    .catch(() => {});
  if (audioContext && audioContext.state !== "closed") {
    await Promise.resolve()
      .then(() => audioContext.close())
      .catch(() => {});
  }
}
