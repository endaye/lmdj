export const PREFLIGHT_CAPABILITIES = Object.freeze([
  "secureContext",
  "crossOriginIsolated",
  "sharedArrayBuffer",
  "webAssembly",
  "audioWorklet",
  "opfs",
  "opfsSyncAccessHandle",
  "opfsWritableReplace",
]);

export class PreflightError extends Error {
  constructor(missing) {
    super("The Web Runtime is missing mandatory capabilities");
    this.name = "PreflightError";
    this.code = "UNSUPPORTED_WEB_RUNTIME";
    this.details = Object.freeze({ missing: Object.freeze([...missing]) });
  }
}

export async function runPreflight(capabilities) {
  if (capabilities === null || typeof capabilities !== "object") {
    throw new TypeError("Preflight capabilities must be injected");
  }
  const missing = [];
  for (const capability of PREFLIGHT_CAPABILITIES) {
    const value = capabilities[capability];
    try {
      const available =
        typeof value === "function" ? await value() : await value;
      if (available !== true) {
        missing.push(capability);
      }
    } catch {
      missing.push(capability);
    }
  }
  if (missing.length > 0) {
    throw new PreflightError(missing);
  }
  return Object.freeze({
    ok: true,
    capabilities: PREFLIGHT_CAPABILITIES,
  });
}
