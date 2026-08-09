const diagnosticTransports = new WeakMap();


export function registerDiagnosticTransport(session, send) {
  if (
    session === null ||
    typeof session !== "object" ||
    typeof send !== "function" ||
    diagnosticTransports.has(session)
  ) {
    throw new TypeError("Diagnostic transport binding is invalid");
  }
  diagnosticTransports.set(session, send);
}

export function createDiagnosticClient(session) {
  const send = diagnosticTransports.get(session);
  if (typeof send !== "function") {
    throw new TypeError("Diagnostic client requires a bound Runtime Session");
  }
  return Object.freeze({
    createProject(payload) {
      return send("project.create", payload, {});
    },
    importAsset(payload, sidecar) {
      return send("asset.import", payload, {sidecar});
    },
    assignPad(payload) {
      return send("pad.assign", payload, {});
    },
  });
}
