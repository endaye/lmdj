export const DIAGNOSTIC_PROJECT_CONTRACT =
  "lmdj.web-runtime-host.diagnostic-project.v1";
export const DIAGNOSTIC_PROJECT_STORAGE_KEY =
  "lmdj.web-runtime-host.diagnostic-project.v1";

const PROJECT_DEADLINE_MS = 30_000;
const PROJECT_OPEN_RETRY_DEADLINE_MS = 60_000;
const PROJECT_OPEN_RETRY_DELAY_MS = 25;
const PAD_COUNT = 64;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const DESCRIPTOR_KEYS = ["asset_id", "contract", "pattern_id", "project_id"].sort();
const SAMPLE_RATE = 48_000;
const SAMPLE_COUNT = 4_800;
const ATTACK_RELEASE_SAMPLES = 240;
const TONE_HERTZ = 440;
const TONE_AMPLITUDE = 12_000;
const STALE_ADMISSION = Object.freeze({ stale_admission: true });
const ALLOWED_TYPED_ERROR_CODES = new Set([
  "INVALID_ARGUMENT",
  "NOT_FOUND",
  "REVISION_CONFLICT",
  "DUPLICATE_ID",
  "UNSUPPORTED_AUDIO",
  "MISSING_ASSET",
  "INVALID_PROJECT",
  "COOK_FAILED",
  "PROVIDER_NOT_FOUND",
  "PROVIDER_FAILED",
  "PERMISSION_DENIED",
  "IO_ERROR",
  "INTERNAL_ERROR",
  "UNSUPPORTED_WEB_RUNTIME",
  "PROJECT_BUSY",
  "WEB_RUNTIME_RESOURCE_LIMIT",
  "HOST_STATE_INVALID",
  "HOST_TIMEOUT",
  "HOST_RESTART_REQUIRED",
  "HOST_PROTOCOL_MISMATCH",
]);

function exactKeys(value, expected) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const actual = Object.keys(value).sort();
  return (
    actual.length === expected.length &&
    actual.every((key, index) => key === expected[index])
  );
}

function validDescriptor(value) {
  return (
    exactKeys(value, DESCRIPTOR_KEYS) &&
    value.contract === DIAGNOSTIC_PROJECT_CONTRACT &&
    [value.project_id, value.pattern_id, value.asset_id].every(
      (id) => typeof id === "string" && UUID_PATTERN.test(id),
    )
  );
}

function generatedDescriptor(crypto) {
  if (typeof crypto?.randomUUID !== "function") {
    throw new TypeError("Diagnostic project requires an injected UUID source");
  }
  return {
    contract: DIAGNOSTIC_PROJECT_CONTRACT,
    project_id: crypto.randomUUID(),
    pattern_id: crypto.randomUUID(),
    asset_id: crypto.randomUUID(),
  };
}

export function loadOrCreateDiagnosticDescriptor({ storage, crypto }) {
  if (
    typeof storage?.getItem !== "function" ||
    typeof storage?.setItem !== "function"
  ) {
    throw new TypeError("Diagnostic project requires browser-local storage");
  }

  let parsed = null;
  const stored = storage.getItem(DIAGNOSTIC_PROJECT_STORAGE_KEY);
  if (typeof stored === "string") {
    try {
      parsed = JSON.parse(stored);
    } catch {
      parsed = null;
    }
  }
  if (validDescriptor(parsed)) {
    return parsed;
  }

  const descriptor = generatedDescriptor(crypto);
  storage.setItem(DIAGNOSTIC_PROJECT_STORAGE_KEY, JSON.stringify(descriptor));
  return descriptor;
}

function writeTag(view, offset, value) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

export function createDiagnosticWav() {
  const dataBytes = SAMPLE_COUNT * 2;
  const bytes = new Uint8Array(44 + dataBytes);
  const view = new DataView(bytes.buffer);
  writeTag(view, 0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeTag(view, 8, "WAVE");
  writeTag(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeTag(view, 36, "data");
  view.setUint32(40, dataBytes, true);

  for (let sample = 0; sample < SAMPLE_COUNT; sample += 1) {
    const attack = Math.min(1, sample / ATTACK_RELEASE_SAMPLES);
    const release = Math.min(1, (SAMPLE_COUNT - 1 - sample) / ATTACK_RELEASE_SAMPLES);
    const envelope = Math.min(attack, release);
    const value = Math.round(
      TONE_AMPLITUDE * envelope * Math.sin((2 * Math.PI * TONE_HERTZ * sample) / SAMPLE_RATE),
    );
    view.setInt16(44 + sample * 2, value, true);
  }
  return bytes;
}

function typedError(code) {
  const error = new Error(code);
  error.code = code;
  return error;
}

function errorCode(error) {
  return ALLOWED_TYPED_ERROR_CODES.has(error?.code)
    ? error.code
    : "HOST_PROTOCOL_MISMATCH";
}

function projectRevision(result) {
  if (!Number.isSafeInteger(result?.project_revision) || result.project_revision < 0) {
    throw typedError("HOST_PROTOCOL_MISMATCH");
  }
  return result.project_revision;
}

function projectFromInspection(result) {
  if (result?.project === null || typeof result?.project !== "object") {
    throw typedError("HOST_PROTOCOL_MISMATCH");
  }
  projectRevision(result);
  return result.project;
}

function assetExists(project, assetId) {
  return (
    project.assets !== null &&
    typeof project.assets === "object" &&
    Object.prototype.hasOwnProperty.call(project.assets, assetId)
  );
}

function assignedAsset(project, flatSlot) {
  const bank = Math.floor(flatSlot / 16);
  const pad = flatSlot % 16;
  const record = project?.banks?.[bank]?.pads?.[pad];
  if (record?.bank !== undefined && record.bank !== bank) {
    throw typedError("HOST_PROTOCOL_MISMATCH");
  }
  if (record?.pad !== pad || !("asset_id" in record)) {
    throw typedError("HOST_PROTOCOL_MISMATCH");
  }
  return record.asset_id;
}

async function sha256Hex(bytes, crypto) {
  if (typeof crypto?.subtle?.digest !== "function") {
    throw new TypeError("Diagnostic project requires an injected SHA-256 implementation");
  }
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

function diagnosticResult(state, { errorCode: code, generation } = {}) {
  if (state === "ready") {
    return Object.freeze({ state, generation });
  }
  if (state === "restart-required") {
    return Object.freeze({ state, outcome: "unknown" });
  }
  return Object.freeze(code === undefined ? { state } : { state, error_code: code });
}

export function createDiagnosticProjectCoordinator({ storage, crypto, transport }) {
  if (typeof transport?.send !== "function") {
    throw new TypeError("Diagnostic project requires a transport send seam");
  }

  let state = "idle";
  let code;
  let generation;
  let pending = null;
  let pendingAdmission = null;
  let queuedLoad = null;
  let admission = 0;
  let terminalResult = null;

  function diagnostics() {
    const result = { diagnostic_project_state: state };
    if (code !== undefined) {
      result.diagnostic_project_error_code = code;
    }
    if (state === "ready" && generation !== undefined) {
      result.diagnostic_project_generation = generation;
    }
    return Object.freeze(result);
  }

  async function send(
    token,
    operation,
    payload,
    sidecar = undefined,
    deadlineMs = PROJECT_DEADLINE_MS,
  ) {
    if (token !== admission) {
      throw STALE_ADMISSION;
    }
    const response = await transport.send(
      { operation, payload },
      { deadlineMs, sidecar },
    );
    if (response?.ok === false) {
      throw typedError(response.error?.code ?? "HOST_PROTOCOL_MISMATCH");
    }
    if (token !== admission) {
      throw STALE_ADMISSION;
    }
    return response?.ok === true ? response.result : response;
  }

  async function openOrCreate(descriptor, token) {
    async function openExisting() {
      const deadline = globalThis.performance.now() +
        PROJECT_OPEN_RETRY_DEADLINE_MS;
      let busyError = typedError("PROJECT_BUSY");
      while (true) {
        const remainingMs = deadline - globalThis.performance.now();
        if (remainingMs <= 0) {
          throw busyError;
        }
        try {
          await send(
            token,
            "project.open",
            {
              project_id: descriptor.project_id,
              pattern_id: descriptor.pattern_id,
            },
            undefined,
            remainingMs,
          );
          return;
        } catch (error) {
          if (errorCode(error) !== "PROJECT_BUSY") {
            throw error;
          }
          busyError = error;
        }
        const retryBudgetMs = deadline - globalThis.performance.now();
        if (retryBudgetMs <= 0) {
          throw busyError;
        }
        await new Promise((resolvePromise) => globalThis.setTimeout(
          resolvePromise,
          Math.min(PROJECT_OPEN_RETRY_DELAY_MS, retryBudgetMs),
        ));
      }
    }

    try {
      await openExisting();
      return;
    } catch (error) {
      if (!["NOT_FOUND", "INVALID_PROJECT"].includes(errorCode(error))) {
        throw error;
      }
    }

    try {
      await send(token, "project.create", {
        project_id: descriptor.project_id,
        bpm: 120,
        initial_pattern: {
          pattern_id: descriptor.pattern_id,
          bars: 1,
          events: [],
        },
      });
    } catch (error) {
      if (errorCode(error) !== "DUPLICATE_ID") {
        throw error;
      }
      await openExisting();
    }
  }

  async function prepare(token) {
    const descriptor = loadOrCreateDiagnosticDescriptor({ storage, crypto });
    await openOrCreate(descriptor, token);
    const inspected = await send(token, "project.inspect", {});
    const project = projectFromInspection(inspected);
    let revision = projectRevision(inspected);

    if (!assetExists(project, descriptor.asset_id)) {
      const wav = createDiagnosticWav();
      const imported = await send(
        token,
        "asset.import",
        {
          command_id: crypto.randomUUID(),
          expected_revision: revision,
          asset_id: descriptor.asset_id,
          media_type: "audio/wav",
          sidecar: {
            sidecar_bytes: wav.byteLength,
            sidecar_sha256: await sha256Hex(wav, crypto),
          },
        },
        wav,
      );
      revision = projectRevision(imported);
    }

    for (let flatSlot = 0; flatSlot < PAD_COUNT; flatSlot += 1) {
      if (assignedAsset(project, flatSlot) === descriptor.asset_id) {
        continue;
      }
      const assigned = await send(token, "pad.assign", {
        command_id: crypto.randomUUID(),
        expected_revision: revision,
        slot: { bank: Math.floor(flatSlot / 16), pad: flatSlot % 16 },
        asset_id: descriptor.asset_id,
      });
      revision = projectRevision(assigned);
    }

    const finalInspection = await send(token, "project.inspect", {});
    const finalProject = projectFromInspection(finalInspection);
    if (
      projectRevision(finalInspection) !== revision ||
      !assetExists(finalProject, descriptor.asset_id)
    ) {
      throw typedError("HOST_PROTOCOL_MISMATCH");
    }
    for (let flatSlot = 0; flatSlot < PAD_COUNT; flatSlot += 1) {
      if (assignedAsset(finalProject, flatSlot) !== descriptor.asset_id) {
        throw typedError("HOST_PROTOCOL_MISMATCH");
      }
    }

    const snapshot = await send(token, "snapshot.reload", {
      pattern_id: descriptor.pattern_id,
    });
    if (
      snapshot?.runtime_ready !== true ||
      !Number.isSafeInteger(snapshot.generation) ||
      snapshot.generation <= 0
    ) {
      throw typedError("HOST_STATE_INVALID");
    }
    state = "ready";
    code = undefined;
    generation = snapshot.generation;
    return diagnosticResult("ready", { generation });
  }

  function load() {
    if (terminalResult !== null) {
      return Promise.resolve(terminalResult);
    }
    if (pending !== null) {
      if (pendingAdmission !== admission) {
        if (queuedLoad === null) {
          const staleLoad = pending;
          queuedLoad = staleLoad.then((result) => {
            queuedLoad = null;
            if (terminalResult !== null) {
              return terminalResult;
            }
            if (result.state === "restart-required") {
              return result;
            }
            return load();
          });
        }
        return queuedLoad;
      }
      return pending;
    }
    const token = admission;
    pendingAdmission = token;
    state = "loading";
    code = undefined;
    generation = undefined;
    pending = prepare(token)
      .catch((error) => {
        if (error === STALE_ADMISSION) {
          state = "error";
          code = undefined;
          generation = undefined;
          return diagnosticResult("error");
        }
        const failureCode = errorCode(error);
        code = failureCode;
        generation = undefined;
        if (failureCode === "HOST_RESTART_REQUIRED") {
          state = "restart-required";
          terminalResult = diagnosticResult("restart-required");
          return terminalResult;
        }
        if (failureCode === "HOST_PROTOCOL_MISMATCH") {
          state = "error";
          terminalResult = diagnosticResult("error", {
            errorCode: failureCode,
          });
          return terminalResult;
        }
        if (token !== admission) {
          state = "error";
          code = undefined;
          return diagnosticResult("error");
        }
        state = "error";
        return diagnosticResult("error", { errorCode: failureCode });
      })
      .finally(() => {
        pending = null;
        pendingAdmission = null;
      });
    return pending;
  }

  function invalidate() {
    admission += 1;
    if (state === "loading" || state === "ready") {
      state = "error";
      code = undefined;
      generation = undefined;
    }
  }

  return Object.freeze({ load, invalidate, diagnostics });
}
