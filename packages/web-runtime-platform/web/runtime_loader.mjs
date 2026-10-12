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
  if (typeof runtime?.transport?.terminate === "function") {
    // A failed formal retirement cannot authorize a direct kill or detach.
    transportTermination = Promise.resolve(runtime.transport.terminate());
    transportTerminated = true;
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
    await transportTermination;
    if (runtime.transport.terminalOwnerReleased === false) {
      const error = new Error("formal Runtime owner is still retained");
      error.code = "HOST_STATE_INVALID";
      error.details = Object.freeze({pending: true});
      throw error;
    }
  }

  await runtime?.worklet?.disconnect?.();
  await runtime?.worklet?.port?.close?.();
  if (audioContext && audioContext.state !== "closed") {
    await audioContext.close();
    if (audioContext.state !== "closed") {
      const error = new Error("AudioContext did not confirm backend closure");
      error.code = "HOST_STATE_INVALID";
      error.details = Object.freeze({pending: true});
      throw error;
    }
  }
}
