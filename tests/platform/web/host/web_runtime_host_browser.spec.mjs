import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";


const fixtureRoot = process.env.LMDJ_WEB_HOST_FIXTURE_ROOT;
if (!fixtureRoot) {
  throw new Error("LMDJ_WEB_HOST_FIXTURE_ROOT is required");
}
const fixtureMetadata = JSON.parse(await readFile(
  resolve(fixtureRoot, "web-runtime-host-fixture.json"),
  "utf8",
));
const fixtureBytes = await readFile(
  resolve(fixtureRoot, fixtureMetadata.wav.path),
);
const rejectedFixtureBytes = Buffer.from(fixtureBytes);
rejectedFixtureBytes.writeUInt32LE(44_100, 24);
rejectedFixtureBytes.writeUInt32LE(88_200, 28);
const deadlineFixtureBytes = Buffer.alloc(32_768);
fixtureBytes.copy(deadlineFixtureBytes);
const deadlineFixtureSha256 = createHash("sha256")
  .update(deadlineFixtureBytes)
  .digest("hex");

const FULL_TRIGGER_COUNT = 500;
const PROTOCOL_VERSION = 1;


function clone(value) {
  return JSON.parse(JSON.stringify(value));
}


async function installTransportObservability(page) {
  await page.addInitScript(() => {
    const observations = {
      admittedSequences: [],
      notifications: [],
      responses: [],
      suppressTriggerOutcomes: false,
    };
    window.__lmdjTask11 = observations;
    const existing = window.__LMDJ_WEB_HOST_SEAMS__ ?? {};
    const observedTransport = {
      async send(request, options) {
        const response = await window.lmdjWebRuntimeHost.transport.send(
          request,
          options,
        );
        observations.responses.push({
          operation: request.operation,
          response: structuredClone(response),
        });
        if (request.operation === "trigger" && response?.ok === true) {
          observations.admittedSequences.push(response.result.sequence);
        }
        return response;
      },
      subscribe(listener) {
        return window.lmdjWebRuntimeHost.transport.subscribe((notification) => {
          observations.notifications.push(structuredClone(notification));
          if (
            observations.suppressTriggerOutcomes === true &&
            notification?.event === "runtime.trigger_outcomes"
          ) {
            return;
          }
          listener(notification);
        });
      },
      subscribeFailure(listener) {
        return window.lmdjWebRuntimeHost.transport.subscribeFailure(listener);
      },
    };
    window.__LMDJ_WEB_HOST_SEAMS__ = {
      ...existing,
      transport: observedTransport,
    };
  });
}


async function openPackagedHost(page) {
  await installTransportObservability(page);
  await page.goto("/index.html");
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  expect(await page.evaluate(() => ({
    crossOriginIsolated,
    manifestReady: window.lmdjWebRuntimeHost.manifestReady,
    runtimeInitialized: window.lmdjWebRuntimeHost.runtimeInitialized,
    sharedMemory: window.Module.wasmMemory.buffer instanceof SharedArrayBuffer,
  }))).toEqual({
    crossOriginIsolated: true,
    manifestReady: true,
    runtimeInitialized: true,
    sharedMemory: true,
  });
}


async function enableDeadlineProof(page, settlementWatchdogMs = 1_000) {
  await page.addInitScript((watchdogMs) => {
    window.__LMDJ_WEB_HOST_DEADLINE_PROOF__ = Object.freeze({
      settlementWatchdogMs: watchdogMs,
    });
  }, settlementWatchdogMs);
}


async function installTerminalAckAttack(page) {
  await page.evaluate(() => {
    const channel = new BroadcastChannel("lmdj.web-runtime-host.terminal.v1");
    const evidence = {
      capturedToken: null,
      forgedAcksSent: 0,
      duplicateReleaseRequestsSent: 0,
      observedWorkerAcks: 0,
      consumeResults: [],
    };
    const originalCcall = window.Module.ccall;
    window.Module.ccall = function observedTerminalConsume(
      identifier,
      ...arguments_
    ) {
      const result = originalCcall.call(this, identifier, ...arguments_);
      if (identifier === "lmdj_web_host_consume_terminal_release") {
        evidence.consumeResults.push(result);
      }
      return result;
    };
    channel.addEventListener("message", (event) => {
      if (
        event.data?.type === "release-and-close" &&
        typeof event.data.token === "string" &&
        evidence.capturedToken === null
      ) {
        evidence.capturedToken = event.data.token;
        for (let index = 0; index < 2; ++index) {
          channel.postMessage({
            type: "released-and-closed",
            token: event.data.token,
            released: true,
          });
          evidence.forgedAcksSent += 1;
          channel.postMessage({
            type: "release-and-close",
            token: event.data.token,
          });
          evidence.duplicateReleaseRequestsSent += 1;
        }
      } else if (
        event.data?.type === "released-and-closed" &&
        event.data?.token === evidence.capturedToken
      ) {
        evidence.observedWorkerAcks += 1;
      }
    });
    window.__lmdjTerminalAckAttack = {channel, evidence};
  });
}


async function terminalAckAttackEvidence(page) {
  return page.evaluate(() => {
    const evidence = structuredClone(
      window.__lmdjTerminalAckAttack.evidence);
    return {
      ...evidence,
      acceptedConsumes:
        evidence.consumeResults.filter((result) => result === 1).length,
      rejectedConsumes:
        evidence.consumeResults.filter((result) => result === -1).length,
    };
  });
}


async function replayConsumedTerminalAck(page) {
  return page.evaluate(() => {
    const token = window.__lmdjTerminalAckAttack.evidence.capturedToken;
    try {
      return window.Module.ccall(
        "lmdj_web_host_consume_terminal_release",
        "number",
        ["string", "number"],
        [token, token.length],
      );
    } catch {
      return "missing";
    }
  });
}


async function beginDeadlineMutation(
  page,
  operation,
  payload,
  sidecar,
  {
    deadlineMs,
    gate,
    forcePublicationError = false,
    synchronousSubmitBlockMs = 0,
  },
) {
  return page.evaluate(({
    selectedOperation,
    selectedPayload,
    bytes,
    timeout,
    selectedGate,
    forceError,
    submitBlockMs,
  }) => {
    const requestId = crypto.randomUUID();
    window.lmdjWebRuntimeHost.deadlineProof.arm({
      requestId,
      gate: selectedGate,
      forcePublicationError: forceError,
    });
    window.__lmdjDeadlineMutations ??= new Map();
    if (submitBlockMs > 0) {
      const originalCcall = window.Module.ccall;
      window.Module.ccall = function blockedSubmit(identifier, ...arguments_) {
        if (identifier === "lmdj_web_host_submit") {
          window.Module.ccall = originalCcall;
          let blockedUntil = performance.now() + submitBlockMs;
          while (performance.now() < blockedUntil) {
            // Deterministically model the synchronous ccall array marshal/copy
            // path preventing the main-thread deadline timer from running.
          }
          const submitted = originalCcall.call(
            this, identifier, ...arguments_);
          blockedUntil = performance.now() + submitBlockMs;
          while (performance.now() < blockedUntil) {
            // Keep the same synchronous submit frame occupied after native
            // admission so the Control owner can expose a shifted cutoff.
          }
          return submitted;
        }
        return originalCcall.call(this, identifier, ...arguments_);
      };
    }
    const outcome = window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: requestId,
      operation: selectedOperation,
      payload: selectedPayload,
    }, {
      deadlineMs: timeout,
      sidecar: new Uint8Array(bytes),
    }).then(
      (response) => ({ response }),
      (error) => ({
        error: {
          code: error?.code,
          message: error?.message,
          details: structuredClone(error?.details ?? {}),
        },
      }),
    );
    window.__lmdjDeadlineMutations.set(requestId, outcome);
    return requestId;
  }, {
    selectedOperation: operation,
    selectedPayload: payload,
    bytes: [...sidecar],
    timeout: deadlineMs,
    selectedGate: gate,
    forceError: forcePublicationError,
    submitBlockMs: synchronousSubmitBlockMs,
  });
}


async function deadlineProofState(page, requestId) {
  return page.evaluate((id) =>
    window.lmdjWebRuntimeHost.deadlineProof.state(id), requestId);
}


async function releaseDeadlineProof(page) {
  return page.evaluate(() => window.lmdjWebRuntimeHost.deadlineProof.release());
}


async function deadlineMutationOutcome(page, requestId) {
  return page.evaluate((id) => window.__lmdjDeadlineMutations.get(id), requestId);
}


async function hostRequest(
  page,
  operation,
  payload,
  { sidecar = [], deadlineMs = 30_000 } = {},
) {
  return page.evaluate(async ({ selectedOperation, selectedPayload, bytes, timeout }) => {
    return window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: selectedOperation,
      payload: selectedPayload,
    }, {
      deadlineMs: timeout,
      sidecar: new Uint8Array(bytes),
    });
  }, {
    selectedOperation: operation,
    selectedPayload: payload,
    bytes: [...sidecar],
    timeout: deadlineMs,
  });
}


function success(response, label) {
  expect(response, label).toMatchObject({ ok: true });
  return response.result;
}


async function activateWithGesture(page) {
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  await page.locator("#audio-activate").click();
  await expect.poll(async () => page.locator("#host-state").textContent())
    .not.toBe("audio-suspended");
  const activation = await page.evaluate(() => ({
    audio: {
      fatal: window.Module?._lmdj_web_audio_fatal?.(),
      observedFrames: window.Module?._lmdj_web_audio_observed_render_quantum?.(),
      observedSampleRate: window.Module?._lmdj_web_audio_observed_sample_rate?.(),
      state: window.Module?._lmdj_web_audio_state?.(),
    },
    diagnostics: window.lmdjWebRuntimeController.diagnostics(),
    state: document.querySelector("#host-state")?.textContent,
  }));
  expect(activation, JSON.stringify(activation)).toMatchObject({ state: "running" });
}


async function createPreparedProject(page, identity) {
  const created = success(await hostRequest(page, "project.create", {
    project_id: identity.projectId,
    bpm: 120,
    initial_pattern: {
      pattern_id: identity.patternId,
      bars: 1,
      events: [],
    },
  }), "project.create");
  expect(created.project_revision).toBe(0);

  const imported = success(await hostRequest(page, "asset.import", {
    command_id: crypto.randomUUID(),
    expected_revision: 0,
    asset_id: identity.assetId,
    media_type: "audio/wav",
    sidecar: {
      sidecar_bytes: fixtureBytes.byteLength,
      sidecar_sha256: fixtureMetadata.wav.sha256,
    },
  }, { sidecar: fixtureBytes }), "asset.import");
  expect(imported.project_revision).toBe(1);

  const assigned = success(await hostRequest(page, "pad.assign", {
    command_id: crypto.randomUUID(),
    expected_revision: 1,
    slot: { bank: 0, pad: 0 },
    asset_id: identity.assetId,
  }), "pad.assign");
  expect(assigned.project_revision).toBe(2);

  const snapshot = success(await hostRequest(page, "snapshot.reload", {
    pattern_id: identity.patternId,
  }), "snapshot.reload");
  expect(snapshot.runtime_ready).toBe(true);
  expect(snapshot.generation).toBeGreaterThan(0);
  return snapshot;
}


async function observationMarker(page) {
  return page.evaluate(() => ({
    admissions: window.__lmdjTask11.admittedSequences.length,
    notifications: window.__lmdjTask11.notifications.length,
    responses: window.__lmdjTask11.responses.length,
  }));
}


async function triggerThroughController(page, count, pacingMs, velocity = 100) {
  return page.evaluate(async ({ triggerCount, pacing, selectedVelocity }) => {
    const start = window.__lmdjTask11.admittedSequences.length;
    for (let index = 0; index < triggerCount; index += 1) {
      const admitted = await window.lmdjWebRuntimeController.trigger(
        0,
        selectedVelocity,
      );
      if (!admitted) {
        throw new Error(`Trigger ${index} was rejected`);
      }
      if (pacing > 0) {
        await new Promise((resolvePromise) => {
          window.setTimeout(resolvePromise, pacing);
        });
      }
    }
    return window.__lmdjTask11.admittedSequences.slice(start);
  }, {
    triggerCount: count,
    pacing: pacingMs,
    selectedVelocity: velocity,
  });
}


async function outcomesSince(page, notificationMarker) {
  return page.evaluate((start) => {
    return window.__lmdjTask11.notifications
      .slice(start)
      .filter(({ event }) => event === "runtime.trigger_outcomes")
      .flatMap(({ payload }) => payload.events);
  }, notificationMarker);
}


async function proveExactOutcomes(page, admittedSequences, notificationMarker) {
  await expect.poll(
    async () => (await outcomesSince(page, notificationMarker)).length,
    { timeout: 30_000 },
  ).toBe(admittedSequences.length);
  const outcomes = await outcomesSince(page, notificationMarker);
  const admitted = new Set(admittedSequences);
  const outcomeSequences = outcomes.map(({ sequence }) => sequence);
  expect(admittedSequences).toHaveLength(admitted.size);
  expect(outcomeSequences).toHaveLength(new Set(outcomeSequences).size);
  expect([...outcomeSequences].sort((left, right) => left - right)).toEqual(
    [...admittedSequences].sort((left, right) => left - right),
  );
  expect(outcomes.filter(({ sequence }) => !admitted.has(sequence))).toEqual([]);
  expect(outcomes.filter(({ outcome }) => outcome !== "voice_started")).toEqual([]);
  expect(outcomes.every(({ runtime_frame }) =>
    Number.isSafeInteger(runtime_frame) && runtime_frame >= 0)).toBe(true);
  return outcomes;
}


async function waitForCaptureState(page, expected) {
  await expect.poll(async () => {
    const response = await hostRequest(page, "host.status", {});
    return response.ok ? response.result.capture_state : response.error.code;
  }, { timeout: 10_000 }).toBe(expected);
}


async function reopenProject(
  page,
  identity,
  patternId,
  { overallDeadlineMs = 10_000, retryDelayMs = 25 } = {},
) {
  if (!Number.isFinite(overallDeadlineMs) || overallDeadlineMs <= 0) {
    throw new TypeError("overallDeadlineMs must be positive");
  }
  if (!Number.isFinite(retryDelayMs) || retryDelayMs < 0) {
    throw new TypeError("retryDelayMs must be non-negative");
  }
  const deadline = performance.now() + overallDeadlineMs;
  const deadlineToken = Symbol("project.open deadline");
  let response;
  async function closePendingPage() {
    if (!page.isClosed()) {
      await page.close({ runBeforeUnload: false }).catch(() => {});
    }
  }
  async function failDeadline(cause) {
    await closePendingPage();
    throw new Error("project.open overall deadline elapsed", { cause });
  }
  while (performance.now() < deadline) {
    const remaining = Math.max(1, Math.ceil(deadline - performance.now()));
    let timer;
    let boundedResponse;
    try {
      boundedResponse = await Promise.race([
        hostRequest(page, "project.open", {
          project_id: identity.projectId,
          pattern_id: patternId,
        }, { deadlineMs: remaining }),
        new Promise((resolvePromise) => {
          timer = setTimeout(() => resolvePromise(deadlineToken), remaining);
        }),
      ]);
    } catch (error) {
      await closePendingPage();
      if (performance.now() >= deadline) {
        throw new Error("project.open overall deadline elapsed", { cause: error });
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
    if (boundedResponse === deadlineToken || performance.now() >= deadline) {
      return failDeadline();
    }
    response = boundedResponse;
    if (response.ok || response.error?.code !== "PROJECT_BUSY") {
      return response;
    }
    const retryBudget = deadline - performance.now();
    if (retryBudget <= 0) {
      break;
    }
    await new Promise((resolvePromise) => setTimeout(
      resolvePromise,
      Math.min(retryDelayMs, retryBudget),
    ));
  }
  return failDeadline();
}


async function opfsInventory(page) {
  return page.evaluate(async () => {
    async function visit(directory, prefix = "") {
      const entries = [];
      for await (const [name, handle] of directory.entries()) {
        const relative = `${prefix}${name}`;
        entries.push(`${handle.kind}:${relative}`);
        if (handle.kind === "directory") {
          entries.push(...await visit(handle, `${relative}/`));
        }
      }
      return entries;
    }
    return (await visit(await navigator.storage.getDirectory())).sort();
  });
}


async function deadlineOutcome(
  page,
  operation,
  payload,
  sidecar = [],
  deadlineMs = 10,
) {
  return page.evaluate(async ({
    selectedOperation,
    selectedPayload,
    bytes,
    timeout,
  }) => {
    try {
      const response = await window.lmdjWebRuntimeHost.transport.send({
        protocol_version: 1,
        request_id: crypto.randomUUID(),
        operation: selectedOperation,
        payload: selectedPayload,
      }, {
        deadlineMs: timeout,
        sidecar: new Uint8Array(bytes),
      });
      return { response };
    } catch (error) {
      return { error: { code: error?.code, message: error?.message } };
    }
  }, {
    selectedOperation: operation,
    selectedPayload: payload,
    bytes: [...sidecar],
    timeout: deadlineMs,
  });
}


async function terminalTransportEvidence(page) {
  return page.evaluate(async () => {
    let newSubmitCode = null;
    try {
      await window.lmdjWebRuntimeHost.transport.send({
        protocol_version: 1,
        request_id: crypto.randomUUID(),
        operation: "host.status",
        payload: {},
      }, { deadlineMs: 1_000 });
    } catch (error) {
      newSubmitCode = error?.code ?? null;
    }
    return {
      controller: window.lmdjWebRuntimeController.diagnostics(),
      newSubmitCode,
      terminated: window.lmdjWebRuntimeHost.transport.terminated,
      terminalOwnerReleased:
        window.lmdjWebRuntimeHost.transport.terminalOwnerReleased,
    };
  });
}


async function webKitCapabilities(page) {
  return page.evaluate(async () => {
    const result = {
      secureContext: isSecureContext === true,
      crossOriginIsolated: crossOriginIsolated === true,
      sharedArrayBuffer: typeof SharedArrayBuffer === "function",
      webAssembly: typeof WebAssembly === "object",
      audioWorklet:
        typeof AudioContext === "function" &&
        "audioWorklet" in AudioContext.prototype,
      opfs: typeof navigator.storage?.getDirectory === "function",
      opfsSyncAccessHandle: null,
      opfsWritableReplace: null,
      worker_reason: null,
    };
    if (!result.opfs || typeof Worker !== "function") {
      return result;
    }
    const source = `
      self.onmessage = async ({data}) => {
        const observed = {
          opfsSyncAccessHandle: false,
          opfsWritableReplace: false,
          worker_reason: null,
        };
        let root;
        let sync;
        let writable;
        try {
          root = await navigator.storage.getDirectory();
          const file = await root.getFileHandle(data, {create: true});
          observed.opfsSyncAccessHandle =
            typeof file.createSyncAccessHandle === "function";
          if (observed.opfsSyncAccessHandle) {
            sync = await file.createSyncAccessHandle();
            sync.close();
            sync = null;
          }
          observed.opfsWritableReplace =
            typeof file.createWritable === "function";
          if (observed.opfsWritableReplace) {
            writable = await file.createWritable({keepExistingData: false});
            await writable.close();
            writable = null;
          }
        } catch (error) {
          observed.worker_reason = error?.name ?? "worker_probe_failed";
        }
        try { sync?.close(); } catch {}
        try { await writable?.abort(); } catch {}
        try { await root?.removeEntry(data); } catch {}
        self.postMessage(observed);
      };
    `;
    const url = URL.createObjectURL(new Blob([source], { type: "text/javascript" }));
    const worker = new Worker(url);
    try {
      const workerResult = await new Promise((resolvePromise) => {
        const timeout = setTimeout(() => resolvePromise({
          opfsSyncAccessHandle: false,
          opfsWritableReplace: false,
          worker_reason: "worker_probe_timeout",
        }), 2_000);
        worker.addEventListener("message", ({ data }) => {
          clearTimeout(timeout);
          resolvePromise(data);
        }, { once: true });
        worker.addEventListener("error", () => {
          clearTimeout(timeout);
          resolvePromise({
            opfsSyncAccessHandle: false,
            opfsWritableReplace: false,
            worker_reason: "worker_probe_error",
          });
        }, { once: true });
        worker.postMessage(`.lmdj-task11-webkit-${crypto.randomUUID()}`);
      });
      return { ...result, ...workerResult };
    } finally {
      worker.terminate();
      URL.revokeObjectURL(url);
    }
  });
}


test.describe.configure({ mode: "serial" });


test("Chromium binds the verified packaged runtime to the real AudioWorklet", async ({
  browserName,
  page,
}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(60_000);
  const runtimeModuleRequests = [];
  page.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.endsWith(".js")) {
      runtimeModuleRequests.push(pathname);
    }
  });

  await openPackagedHost(page);
  expect(await opfsInventory(page)).toEqual([]);
  const runtimeScriptPath = await page.evaluate(async () => {
    const manifest = await fetch("./host-manifest.json").then((response) =>
      response.json());
    return manifest.assets.find(({ role }) => role === "runtime_script").path;
  });
  const runtimeScriptPathname = new URL(runtimeScriptPath, page.url()).pathname;
  const identity = {
    projectId: crypto.randomUUID(),
    patternId: crypto.randomUUID(),
    assetId: crypto.randomUUID(),
  };
  await createPreparedProject(page, identity);
  await activateWithGesture(page);

  expect(runtimeModuleRequests).not.toContain("/lmdj-web-runtime-host.js");
  expect(runtimeModuleRequests.filter(
    (pathname) => pathname === runtimeScriptPathname,
  ).length).toBeGreaterThanOrEqual(2);
  const closeMarker = await observationMarker(page);
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(true);
  const closeResponses = await page.evaluate((start) =>
    window.__lmdjTask11.responses.slice(start)
      .filter(({ operation }) => operation === "host.close"),
  closeMarker.responses);
  expect(closeResponses).toHaveLength(1);
  expect(success(closeResponses[0].response, "host.close").state).toBe("closed");
  await expect(page.locator("#host-state")).toHaveText("closed");
  expect(await page.evaluate(() => window.lmdjWebRuntimeHost.transport.terminated))
    .toBe(true);
});


test("Chromium completes the exact twelve-step packaged runtime journey", async ({
  browserName,
  context,
  page,
}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  const runtimeModuleRequests = [];
  page.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.endsWith(".js")) {
      runtimeModuleRequests.push(pathname);
    }
  });

  expect(fixtureMetadata).toMatchObject({
    contract: "lmdj.web-runtime-host.browser-fixture.v1",
    wav: {
      channels: 1,
      frame_count: expect.any(Number),
      sample_rate: 48_000,
      sample_width_bytes: 2,
    },
    trigger_proof: {
      admission_count: FULL_TRIGGER_COUNT,
      pacing_ms: expect.any(Number),
      capacities: {
        queue: expect.any(Number),
        trigger_outcome: expect.any(Number),
        voice: expect.any(Number),
      },
      maximum_concurrent_voices: expect.any(Number),
    },
  });
  expect(createHash("sha256").update(fixtureBytes).digest("hex")).toBe(
    fixtureMetadata.wav.sha256,
  );
  expect(FULL_TRIGGER_COUNT).toBeLessThan(
    fixtureMetadata.trigger_proof.capacities.queue,
  );
  expect(FULL_TRIGGER_COUNT).toBeLessThan(
    fixtureMetadata.trigger_proof.capacities.trigger_outcome,
  );
  expect(fixtureMetadata.trigger_proof.maximum_concurrent_voices).toBeLessThan(
    fixtureMetadata.trigger_proof.capacities.voice,
  );

  await openPackagedHost(page);
  const runtimeScriptPath = await page.evaluate(async () => {
    const manifest = await fetch("./host-manifest.json").then((response) =>
      response.json());
    return manifest.assets.find(({ role }) => role === "runtime_script").path;
  });
  const runtimeScriptPathname = new URL(runtimeScriptPath, page.url()).pathname;
  const identity = {
    projectId: crypto.randomUUID(),
    patternId: crypto.randomUUID(),
    committedPatternId: crypto.randomUUID(),
    assetId: crypto.randomUUID(),
    rejectedAssetId: crypto.randomUUID(),
    takeId: crypto.randomUUID(),
  };
  const initialSnapshot = await createPreparedProject(page, identity);
  await activateWithGesture(page);
  expect(runtimeModuleRequests).not.toContain("/lmdj-web-runtime-host.js");
  expect(runtimeModuleRequests.filter(
    (pathname) => pathname === runtimeScriptPathname,
  ).length).toBeGreaterThanOrEqual(2);

  const fullMarker = await observationMarker(page);
  const admitted = await triggerThroughController(
    page,
    fixtureMetadata.trigger_proof.admission_count,
    fixtureMetadata.trigger_proof.pacing_ms,
  );
  expect(admitted).toHaveLength(FULL_TRIGGER_COUNT);
  const fullOutcomes = await proveExactOutcomes(
    page,
    admitted,
    fullMarker.notifications,
  );
  expect(fullOutcomes).toHaveLength(FULL_TRIGGER_COUNT);
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.diagnostics()))
    .toMatchObject({
      state: "running",
      trigger_admitted_count: FULL_TRIGGER_COUNT,
      trigger_outcome_count: FULL_TRIGGER_COUNT,
      trigger_rejected_count: 0,
    });
  const fullTriggerResponses = await page.evaluate((start) =>
    window.__lmdjTask11.responses.slice(start)
      .filter(({ operation }) => operation === "trigger"),
  fullMarker.responses);
  expect(fullTriggerResponses).toHaveLength(FULL_TRIGGER_COUNT);
  expect(fullTriggerResponses.filter(({ response }) => response.ok !== true))
    .toEqual([]);
  expect(fullTriggerResponses.every(({ response }) =>
    response.result.status === "enqueued")).toBe(true);
  expect(fullOutcomes.filter(({ outcome }) => outcome === "voice_capacity"))
    .toEqual([]);
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.diagnostics()))
    .toMatchObject({ state: "running" });

  expect(await page.evaluate(({ takeId }) =>
    window.lmdjWebRuntimeController.beginTake(takeId, 2), identity)).toBe(true);
  await waitForCaptureState(page, "active");
  const takeMarker = await observationMarker(page);
  const takeAdmissions = await triggerThroughController(
    page,
    20,
    fixtureMetadata.trigger_proof.pacing_ms,
    101,
  );
  const stopped = success(await hostRequest(page, "take.stop", {}), "take.stop");
  expect(stopped).toMatchObject({ take_id: identity.takeId, status: "committable" });
  await proveExactOutcomes(page, takeAdmissions, takeMarker.notifications);

  const afterStopMarker = await observationMarker(page);
  const afterStopAdmissions = await triggerThroughController(
    page,
    1,
    fixtureMetadata.trigger_proof.pacing_ms,
    102,
  );
  await proveExactOutcomes(
    page,
    afterStopAdmissions,
    afterStopMarker.notifications,
  );
  const committedPattern = {
    pattern_id: identity.committedPatternId,
    bars: 2,
    events: Array.from({ length: 20 }, (_, step) => ({
      slot: { bank: 0, pad: 0 },
      step,
      velocity: 101,
    })),
  };
  const committed = success(await hostRequest(page, "take.commit", {
    command_id: crypto.randomUUID(),
    expected_revision: 2,
    pattern: committedPattern,
  }), "take.commit");
  expect(committed).toMatchObject({
    take_id: identity.takeId,
    pattern_id: identity.committedPatternId,
    project_revision: 3,
  });
  const inspectedAfterCommit = success(
    await hostRequest(page, "project.inspect", {}),
    "project.inspect after commit",
  );
  expect(inspectedAfterCommit.project_revision).toBe(3);
  expect(inspectedAfterCommit.project.takes[identity.takeId].events).toHaveLength(20);
  expect(inspectedAfterCommit.project.takes[identity.takeId].events
    .every(({ velocity }) => velocity === 101)).toBe(true);
  expect(inspectedAfterCommit.project.patterns[identity.committedPatternId].events)
    .toHaveLength(20);
  expect(success(await hostRequest(page, "take.recoverable.list", {}),
    "take.recoverable.list").candidates).toEqual([]);

  await page.reload();
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  const reopened = success(
    await reopenProject(page, identity, identity.committedPatternId),
    "project.open after page and Worker reload",
  );
  expect(reopened).toMatchObject({
    project_revision: 3,
    runtime_ready: true,
    pattern_id: identity.committedPatternId,
  });
  const inspectedAfterRestart = success(
    await hostRequest(page, "project.inspect", {}),
    "project.inspect after restart",
  );
  expect(inspectedAfterRestart.project_revision).toBe(3);
  expect(inspectedAfterRestart.project.takes[identity.takeId].events).toHaveLength(20);
  expect(success(await hostRequest(page, "take.recoverable.list", {}),
    "recoverable after restart").candidates).toEqual([]);
  await activateWithGesture(page);
  const restartMarker = await observationMarker(page);
  const restartedAdmission = await triggerThroughController(
    page,
    1,
    fixtureMetadata.trigger_proof.pacing_ms,
  );
  await proveExactOutcomes(page, restartedAdmission, restartMarker.notifications);

  const priorStatus = success(await hostRequest(page, "host.status", {}),
    "status before rejected Snapshot");
  expect(priorStatus.control_generation).toBe(reopened.generation);
  const importedRejected = success(await hostRequest(page, "asset.import", {
    command_id: crypto.randomUUID(),
    expected_revision: 3,
    asset_id: identity.rejectedAssetId,
    media_type: "audio/wav",
    sidecar: {
      sidecar_bytes: rejectedFixtureBytes.byteLength,
      sidecar_sha256: createHash("sha256").update(rejectedFixtureBytes).digest("hex"),
    },
  }, { sidecar: rejectedFixtureBytes }), "rejected fixture import");
  expect(importedRejected.project_revision).toBe(4);
  expect(success(await hostRequest(page, "pad.assign", {
    command_id: crypto.randomUUID(),
    expected_revision: 4,
    slot: { bank: 0, pad: 0 },
    asset_id: identity.rejectedAssetId,
  }), "assign rejected fixture").project_revision).toBe(5);
  const rejectionMarker = await observationMarker(page);
  const rejectedSnapshot = await hostRequest(page, "snapshot.reload", {
    pattern_id: identity.committedPatternId,
  });
  expect(rejectedSnapshot.ok).toBe(false);
  expect(rejectedSnapshot.error.code).toBe("UNSUPPORTED_AUDIO");
  const retainedStatus = success(await hostRequest(page, "host.status", {}),
    "status after rejected Snapshot");
  expect(await page.evaluate((start) =>
    window.__lmdjTask11.notifications.slice(start)
      .filter(({ event }) => event === "snapshot.rejected"),
  rejectionMarker.notifications)).toEqual([]);
  expect(retainedStatus.control_generation).toBe(priorStatus.control_generation);
  expect(retainedStatus.acknowledged_generation).toBe(
    priorStatus.acknowledged_generation,
  );
  expect(success(await hostRequest(page, "pad.assign", {
    command_id: crypto.randomUUID(),
    expected_revision: 5,
    slot: { bank: 0, pad: 0 },
    asset_id: identity.assetId,
  }), "restore accepted fixture").project_revision).toBe(6);
  const republished = success(await hostRequest(page, "snapshot.reload", {
    pattern_id: identity.committedPatternId,
  }), "republish after rejected Snapshot");
  expect(republished.generation).toBeGreaterThan(priorStatus.control_generation);

  await page.locator("#audio-suspend").click();
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  await activateWithGesture(page);
  await page.evaluate(() => window.lmdjWebRuntimeController.observeVisibility(true));
  await expect(page.locator("#host-state")).toHaveText("recovering");
  const recoveryMarker = await observationMarker(page);
  await page.locator("#pad-0").click();
  await expect.poll(() => page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.length - start,
  recoveryMarker.admissions)).toBe(1);
  await expect(page.locator("#host-state")).toHaveText("running");
  const recoverySequence = await page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.slice(start),
  recoveryMarker.admissions);
  await proveExactOutcomes(page, recoverySequence, recoveryMarker.notifications);
  await page.evaluate(() => window.lmdjWebRuntimeController.observeVisibility(false));

  const finalStatus = success(await hostRequest(page, "host.status", {}),
    "status before clean close");
  expect(finalStatus).toMatchObject({
    state: "running",
    capture_state: "idle",
  });

  const contender = await context.newPage();
  await openPackagedHost(contender);
  const busy = await hostRequest(contender, "project.open", {
    project_id: identity.projectId,
    pattern_id: identity.committedPatternId,
  });
  expect(busy).toMatchObject({
    ok: false,
    error: { code: "PROJECT_BUSY" },
  });
  expect(await contender.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(true);
  await contender.close();

  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(true);
  await expect(page.locator("#host-state")).toHaveText("closed");
  expect(initialSnapshot.generation).toBeGreaterThan(0);
});


test("Chromium rejects protocol mismatch before OPFS mutation", async ({
  browserName,
  page,
}) => {
  test.skip(browserName !== "chromium");
  await openPackagedHost(page);
  const before = await opfsInventory(page);
  const mismatch = await page.evaluate(() => {
    return window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 2,
      request_id: crypto.randomUUID(),
      operation: "project.create",
      payload: {
        project_id: crypto.randomUUID(),
        bpm: 120,
        initial_pattern: {
          pattern_id: crypto.randomUUID(),
          bars: 1,
          events: [],
        },
      },
    }, { deadlineMs: 30_000 });
  });
  expect(mismatch).toMatchObject({
    ok: false,
    error: { code: "HOST_PROTOCOL_MISMATCH" },
  });
  expect(await opfsInventory(page)).toEqual(before);
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(true);
});


test("Chromium reopen helper enforces its overall deadline and closes late work", async ({
  browserName,
  page,
}) => {
  test.skip(browserName !== "chromium");
  await page.goto("/__task11-reopen-deadline__");
  await page.evaluate(() => {
    window.lmdjWebRuntimeHost = {
      transport: {
        send(_request, { deadlineMs }) {
          window.__task11ReopenDeadlineMs = deadlineMs;
          return new Promise((resolvePromise) => {
            window.setTimeout(() => {
              resolvePromise({
                ok: true,
                result: { project_revision: 2 },
              });
            }, 150);
          });
        },
      },
    };
  });
  const startedAt = Date.now();
  await expect(reopenProject(
    page,
    { projectId: crypto.randomUUID() },
    crypto.randomUUID(),
    { overallDeadlineMs: 40, retryDelayMs: 1 },
  )).rejects.toThrow("project.open overall deadline elapsed");
  expect(Date.now() - startedAt).toBeLessThan(500);
  expect(page.isClosed()).toBe(true);
});


test("Chromium recovery outcome timeout is terminal and releases the lease", async ({
  browserName,
  context,
  page,
}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(60_000);
  await openPackagedHost(page);
  const identity = {
    projectId: crypto.randomUUID(),
    patternId: crypto.randomUUID(),
    assetId: crypto.randomUUID(),
  };
  await createPreparedProject(page, identity);
  await activateWithGesture(page);
  await page.evaluate(() => window.lmdjWebRuntimeController.observeVisibility(true));
  await expect(page.locator("#host-state")).toHaveText("recovering");
  await page.evaluate(() => {
    window.__lmdjTask11.suppressTriggerOutcomes = true;
  });
  const marker = await observationMarker(page);
  await page.locator("#pad-0").click();
  await expect.poll(() => page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.length - start,
  marker.admissions)).toBe(1);
  await expect(page.locator("#host-state")).toHaveText("failed", {
    timeout: 3_000,
  });
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.diagnostics()))
    .toMatchObject({ state: "failed", error_code: "HOST_TIMEOUT" });
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(false);

  const reopenedPage = await context.newPage();
  await openPackagedHost(reopenedPage);
  const reopenResponse = await reopenProject(
    reopenedPage,
    identity,
    identity.patternId,
  );
  const reopened = success(
    reopenResponse,
    `reopen after timeout cleanup: ${JSON.stringify(reopenResponse)}`,
  );
  expect(reopened.project_revision).toBe(2);
  expect(await reopenedPage.evaluate(() =>
    window.lmdjWebRuntimeController.close())).toBe(true);
  await reopenedPage.close();
});


test("Chromium synchronous submit copy cannot move the caller publication cutoff", async ({
  browserName,
  context,
  page,
}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(60_000);
  await enableDeadlineProof(page);
  await openPackagedHost(page);
  const identity = {
    projectId: crypto.randomUUID(),
    patternId: crypto.randomUUID(),
    assetId: crypto.randomUUID(),
  };
  success(await hostRequest(page, "project.create", {
    project_id: identity.projectId,
    bpm: 120,
    initial_pattern: {
      pattern_id: identity.patternId,
      bars: 1,
      events: [],
    },
  }), "blocked submit project.create");
  const before = success(await hostRequest(page, "project.inspect", {}),
    "blocked submit inspect before deadline");
  const inventoryBefore = await opfsInventory(page);

  const requestId = await beginDeadlineMutation(
    page,
    "asset.import",
    {
      command_id: crypto.randomUUID(),
      expected_revision: 0,
      asset_id: identity.assetId,
      media_type: "audio/wav",
      sidecar: {
        sidecar_bytes: deadlineFixtureBytes.byteLength,
        sidecar_sha256: deadlineFixtureSha256,
      },
    },
    deadlineFixtureBytes,
    {
      deadlineMs: 250,
      gate: "after-claim",
      synchronousSubmitBlockMs: 300,
    },
  );
  await expect.poll(() => deadlineProofState(page, requestId), {
    message: "expired send-time cutoff cancels before publication claim",
  }).toMatchObject({
    gate: "after-claim",
    publication: "cancelled",
    last_cancel_result: "cancelled",
  });
  expect(await deadlineMutationOutcome(page, requestId)).toMatchObject({
    error: { code: "HOST_TIMEOUT" },
  });
  await expect(page.locator("#host-state")).toHaveText("failed");
  await expect.poll(() => terminalTransportEvidence(page)).toMatchObject({
    controller: { state: "failed", error_code: "HOST_TIMEOUT" },
    newSubmitCode: "HOST_TIMEOUT",
    terminated: true,
    terminalOwnerReleased: true,
  });
  expect(await opfsInventory(page)).toEqual(inventoryBefore);

  const reopened = await context.newPage();
  await openPackagedHost(reopened);
  expect(success(await reopenProject(
    reopened,
    identity,
    identity.patternId,
  ), "blocked submit first reopen").project_revision).toBe(0);
  expect(success(await hostRequest(reopened, "project.inspect", {})))
    .toEqual(before);
  expect(await opfsInventory(reopened)).toEqual(inventoryBefore);
  expect(await reopened.evaluate(() =>
    window.lmdjWebRuntimeController.close())).toBe(true);
  await reopened.close();
});


test("Chromium packaged responsive cancellation wins before mutation publication", async ({
  browserName,
  context,
  page,
}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(60_000);

  const cases = [
    {
      name: "late-success asset.import",
      expectedRevision: 0,
      claimAttempted: true,
    },
    {
      name: "late-error asset.import revision conflict",
      expectedRevision: 99,
      claimAttempted: false,
    },
  ];

  for (const [index, selected] of cases.entries()) {
    const owner = index === 0 ? page : await context.newPage();
    await enableDeadlineProof(owner);
    await openPackagedHost(owner);
    if (index === 0) {
      await installTerminalAckAttack(owner);
    }
    const identity = {
      projectId: crypto.randomUUID(),
      patternId: crypto.randomUUID(),
      assetId: crypto.randomUUID(),
    };
    success(await hostRequest(owner, "project.create", {
      project_id: identity.projectId,
      bpm: 120,
      initial_pattern: {
        pattern_id: identity.patternId,
        bars: 1,
        events: [],
      },
    }), `${selected.name} project.create`);
    const before = success(
      await hostRequest(owner, "project.inspect", {}),
      `${selected.name} project.inspect before deadline`,
    );
    const inventoryBefore = await opfsInventory(owner);
    const observationsBefore = await owner.evaluate(() => ({
      notifications: window.__lmdjTask11.notifications.length,
      responses: window.__lmdjTask11.responses.length,
    }));

    const requestId = await beginDeadlineMutation(
      owner,
      "asset.import",
      {
        command_id: crypto.randomUUID(),
        expected_revision: selected.expectedRevision,
        asset_id: identity.assetId,
        media_type: "audio/wav",
        sidecar: {
          sidecar_bytes: deadlineFixtureBytes.byteLength,
          sidecar_sha256: deadlineFixtureSha256,
        },
      },
      deadlineFixtureBytes,
      {
        deadlineMs: 250,
        gate: "responsive-cancellation",
      },
    );
    await expect.poll(() => deadlineProofState(owner, requestId), {
      message: `${selected.name} entered Facade with publication still open`,
    }).toMatchObject({
      entered_facade: true,
      claim_attempted: false,
      gate: "responsive-cancellation",
      publication: "open",
    });
    await expect.poll(() => deadlineProofState(owner, requestId), {
      message: `${selected.name} deadline cancellation won open -> cancelled`,
    }).toMatchObject({
      publication: "cancelled",
      cancel_calls: 2,
      last_cancel_result: "cancelled",
    });
    const outcome = await deadlineMutationOutcome(owner, requestId);
    expect(outcome, `${selected.name}: ${JSON.stringify(outcome)}`).toMatchObject({
      error: { code: "HOST_TIMEOUT" },
    });
    await expect(owner.locator("#host-state"), selected.name).toHaveText("failed");
    await expect.poll(() => terminalTransportEvidence(owner), {
      message: `${selected.name} responsive owner release`,
    }).toMatchObject({
      controller: { state: "failed", error_code: "HOST_TIMEOUT" },
      newSubmitCode: "HOST_TIMEOUT",
      terminated: true,
      terminalOwnerReleased: true,
    });
    if (index === 0) {
      await expect.poll(() => terminalAckAttackEvidence(owner)).toMatchObject({
        forgedAcksSent: 2,
        duplicateReleaseRequestsSent: 2,
        observedWorkerAcks: 1,
        acceptedConsumes: 1,
        rejectedConsumes: 2,
      });
      expect(await replayConsumedTerminalAck(owner)).toBe(-1);
      expect(await terminalAckAttackEvidence(owner)).toMatchObject({
        acceptedConsumes: 1,
        rejectedConsumes: 3,
      });
      expect(await terminalTransportEvidence(owner)).toMatchObject({
        terminalOwnerReleased: true,
      });
    }
    expect(await deadlineProofState(owner, requestId), selected.name)
      .toMatchObject({ claim_attempted: selected.claimAttempted });
    expect(await opfsInventory(owner), `${selected.name} direct cleanup`)
      .toEqual(inventoryBefore);
    await owner.waitForTimeout(100);
    expect(await owner.evaluate(() => ({
      notifications: window.__lmdjTask11.notifications.length,
      responses: window.__lmdjTask11.responses.length,
    })), `${selected.name} late messages`).toEqual(observationsBefore);

    const reopened = await context.newPage();
    await openPackagedHost(reopened);
    const reopenResponse = await hostRequest(reopened, "project.open", {
      project_id: identity.projectId,
      pattern_id: identity.patternId,
    });
    const reopenedProject = success(
      reopenResponse,
      `${selected.name} immediate writer reacquire: ${JSON.stringify(reopenResponse)}`,
    );
    expect(reopenedProject.project_revision, selected.name).toBe(0);
    const after = success(
      await hostRequest(reopened, "project.inspect", {}),
      `${selected.name} project.inspect after deadline`,
    );
    expect(after, selected.name).toEqual(before);
    expect(await opfsInventory(reopened), selected.name).toEqual(inventoryBefore);
    expect(success(await hostRequest(reopened, "asset.import", {
      command_id: crypto.randomUUID(),
      expected_revision: 0,
      asset_id: identity.assetId,
      media_type: "audio/wav",
      sidecar: {
        sidecar_bytes: deadlineFixtureBytes.byteLength,
        sidecar_sha256: deadlineFixtureSha256,
      },
    }, { sidecar: deadlineFixtureBytes }), `${selected.name} explicit retry`)
      .project_revision).toBe(1);
    expect(await reopened.evaluate(() =>
      window.lmdjWebRuntimeController.close()), selected.name).toBe(true);
    await reopened.close();
    if (owner !== page) {
      await owner.close();
    }
  }
});


test("Chromium packaged unresponsive cancellation force-terminates and recovers", async ({
  browserName,
  context,
  page,
}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(60_000);
  await enableDeadlineProof(page);
  await openPackagedHost(page);
  await installTerminalAckAttack(page);
  const identity = {
    projectId: crypto.randomUUID(),
    patternId: crypto.randomUUID(),
    assetId: crypto.randomUUID(),
  };
  success(await hostRequest(page, "project.create", {
    project_id: identity.projectId,
    bpm: 120,
    initial_pattern: {
      pattern_id: identity.patternId,
      bars: 1,
      events: [],
    },
  }), "unresponsive cancellation project.create");
  const before = success(await hostRequest(page, "project.inspect", {}),
    "unresponsive cancellation inspect before deadline");
  const inventoryBefore = await opfsInventory(page);
  const observationsBefore = await page.evaluate(() => ({
    notifications: window.__lmdjTask11.notifications.length,
    responses: window.__lmdjTask11.responses.length,
  }));
  const requestId = await beginDeadlineMutation(
    page,
    "asset.import",
    {
      command_id: crypto.randomUUID(),
      expected_revision: 0,
      asset_id: identity.assetId,
      media_type: "audio/wav",
      sidecar: {
        sidecar_bytes: deadlineFixtureBytes.byteLength,
        sidecar_sha256: deadlineFixtureSha256,
      },
    },
    deadlineFixtureBytes,
    { deadlineMs: 250, gate: "unresponsive-cancellation" },
  );
  await expect.poll(() => deadlineProofState(page, requestId)).toMatchObject({
    entered_facade: true,
    claim_attempted: true,
    gate: "unresponsive-cancellation",
    publication: "open",
  });
  await expect.poll(() => deadlineProofState(page, requestId)).toMatchObject({
    publication: "cancelled",
    cancel_calls: 2,
    last_cancel_result: "cancelled",
  });
  expect(await releaseDeadlineProof(page), "release unresponsive proof gate")
    .toBe(true);
  expect(await deadlineMutationOutcome(page, requestId)).toMatchObject({
    error: { code: "HOST_TIMEOUT" },
  });
  await expect(page.locator("#host-state")).toHaveText("failed");
  await page.waitForTimeout(150);
  expect(await terminalTransportEvidence(page)).toMatchObject({
    controller: { state: "failed", error_code: "HOST_TIMEOUT" },
    newSubmitCode: "HOST_TIMEOUT",
    terminated: true,
    terminalOwnerReleased: false,
  });
  expect(await terminalAckAttackEvidence(page)).toMatchObject({
    forgedAcksSent: 2,
    duplicateReleaseRequestsSent: 2,
    observedWorkerAcks: 0,
    acceptedConsumes: 0,
    rejectedConsumes: 2,
  });
  const directInventory = await opfsInventory(page);
  expect(directInventory, "unresponsive non-Truth staging residue")
    .not.toEqual(inventoryBefore);
  expect(await page.evaluate(() => ({
    notifications: window.__lmdjTask11.notifications.length,
    responses: window.__lmdjTask11.responses.length,
  })), "unresponsive cancellation late messages").toEqual(observationsBefore);

  const reopened = await context.newPage();
  await openPackagedHost(reopened);
  const reopenResponse = await hostRequest(reopened, "project.open", {
    project_id: identity.projectId,
    pattern_id: identity.patternId,
  });
  const reopenedProject = success(
    reopenResponse,
    `unresponsive cancellation first reopen: ${JSON.stringify(reopenResponse)}`,
  );
  expect(reopenedProject.project_revision).toBe(0);
  expect(success(await hostRequest(reopened, "project.inspect", {})),
    "unresponsive cancellation recovered truth").toEqual(before);
  expect(await opfsInventory(reopened), "unresponsive recovery cleanup")
    .toEqual(inventoryBefore);
  expect(success(await hostRequest(reopened, "asset.import", {
    command_id: crypto.randomUUID(),
    expected_revision: 0,
    asset_id: identity.assetId,
    media_type: "audio/wav",
    sidecar: {
      sidecar_bytes: deadlineFixtureBytes.byteLength,
      sidecar_sha256: deadlineFixtureSha256,
    },
  }, { sidecar: deadlineFixtureBytes }), "unresponsive explicit retry")
    .project_revision).toBe(1);
  expect(await reopened.evaluate(() =>
    window.lmdjWebRuntimeController.close())).toBe(true);
  await reopened.close();
});


test("Chromium packaged asset.import claim wins before deadline and settles after it", async ({
  browserName,
  context,
}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(60_000);
  for (const selected of [
    { name: "committed success", forcePublicationError: false },
    { name: "aborted IO error", forcePublicationError: true },
  ]) {
    const owner = await context.newPage();
    await enableDeadlineProof(owner);
    await openPackagedHost(owner);
    const identity = {
      projectId: crypto.randomUUID(),
      patternId: crypto.randomUUID(),
      assetId: crypto.randomUUID(),
    };
    success(await hostRequest(owner, "project.create", {
      project_id: identity.projectId,
      bpm: 120,
      initial_pattern: {
        pattern_id: identity.patternId,
        bars: 1,
        events: [],
      },
    }), `${selected.name} project.create`);
    const inventoryBefore = await opfsInventory(owner);
    const requestId = await beginDeadlineMutation(
      owner,
      "asset.import",
      {
        command_id: crypto.randomUUID(),
        expected_revision: 0,
        asset_id: identity.assetId,
        media_type: "audio/wav",
        sidecar: {
          sidecar_bytes: deadlineFixtureBytes.byteLength,
          sidecar_sha256: deadlineFixtureSha256,
        },
      },
      deadlineFixtureBytes,
      {
        deadlineMs: 250,
        gate: "after-claim",
        forcePublicationError: selected.forcePublicationError,
      },
    );
    await expect.poll(() => deadlineProofState(owner, requestId), {
      message: `${selected.name} entered Facade and won publication claim`,
    }).toMatchObject({
      entered_facade: true,
      claim_attempted: true,
      gate: "after-claim",
      publication: "publish-claimed",
    });
    await owner.waitForTimeout(300);
    expect(await deadlineProofState(owner, requestId), selected.name)
      .toMatchObject({
        publication: "publish-claimed",
        cancel_calls: 1,
        last_cancel_result: "publish-claimed",
      });
    expect(await releaseDeadlineProof(owner), selected.name).toBe(true);
    const outcome = await deadlineMutationOutcome(owner, requestId);
    const settledProof = await deadlineProofState(owner, requestId);
    if (selected.forcePublicationError) {
      expect(outcome, `${selected.name}: ${JSON.stringify(settledProof)}`)
        .toMatchObject({
        response: { ok: false, error: { code: "IO_ERROR" } },
      });
      expect(settledProof, selected.name)
        .toMatchObject({ publication: "aborted" });
      expect(success(await hostRequest(owner, "project.inspect", {}),
        `${selected.name} inspect`).project_revision).toBe(0);
      expect(await opfsInventory(owner), `${selected.name} residue`)
        .toEqual(inventoryBefore);
    } else {
      expect(outcome, `${selected.name}: ${JSON.stringify(settledProof)}`)
        .toMatchObject({
        response: { ok: true, result: { project_revision: 1 } },
      });
      expect(settledProof, selected.name)
        .toMatchObject({ publication: "committed" });
      expect(success(await hostRequest(owner, "project.inspect", {}),
        `${selected.name} inspect`).project_revision).toBe(1);
    }
    expect(await owner.locator("#host-state").textContent(), selected.name)
      .toBe("audio-suspended");
    expect(await owner.evaluate(() =>
      window.lmdjWebRuntimeController.close()), selected.name).toBe(true);
    await owner.close();
  }
});


test("Chromium claimed asset.import publication hang becomes restart-required and recovers", async ({
  browserName,
  context,
  page,
}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(60_000);
  await enableDeadlineProof(page, 200);
  await openPackagedHost(page);
  const identity = {
    projectId: crypto.randomUUID(),
    patternId: crypto.randomUUID(),
    assetId: crypto.randomUUID(),
  };
  success(await hostRequest(page, "project.create", {
    project_id: identity.projectId,
    bpm: 120,
    initial_pattern: {
      pattern_id: identity.patternId,
      bars: 1,
      events: [],
    },
  }), "publication hang project.create");
  const inventoryBefore = await opfsInventory(page);
  const observationsBefore = await page.evaluate(() => ({
    notifications: window.__lmdjTask11.notifications.length,
    responses: window.__lmdjTask11.responses.length,
  }));
  const requestId = await beginDeadlineMutation(
    page,
    "asset.import",
    {
      command_id: crypto.randomUUID(),
      expected_revision: 0,
      asset_id: identity.assetId,
      media_type: "audio/wav",
      sidecar: {
        sidecar_bytes: deadlineFixtureBytes.byteLength,
        sidecar_sha256: deadlineFixtureSha256,
      },
    },
    deadlineFixtureBytes,
    { deadlineMs: 100, gate: "after-claim" },
  );
  await expect.poll(() => deadlineProofState(page, requestId)).toMatchObject({
    entered_facade: true,
    claim_attempted: true,
    gate: "after-claim",
    publication: "publish-claimed",
  });
  await expect.poll(() => deadlineProofState(page, requestId), {
    message: "claimed publication rejected deadline cancellation exactly once",
    intervals: [5, 10, 20],
  }).toMatchObject({
    publication: "publish-claimed",
    cancel_calls: 1,
    last_cancel_result: "publish-claimed",
  });
  const startedAt = Date.now();
  const outcome = await deadlineMutationOutcome(page, requestId);
  expect(outcome).toMatchObject({
    error: {
      code: "HOST_RESTART_REQUIRED",
      details: {
        terminal_state: "restart-required",
        mutation_outcome: "unknown",
      },
    },
  });
  expect(Date.now() - startedAt).toBeLessThan(1_000);
  expect(await deadlineProofState(page, requestId)).toMatchObject({
    publication: "publish-claimed",
    cancel_calls: 2,
    last_cancel_result: "publish-claimed",
  });
  await expect(page.locator("#host-state")).toHaveText("failed");
  expect(await terminalTransportEvidence(page)).toMatchObject({
    controller: { state: "failed", error_code: "HOST_RESTART_REQUIRED" },
    newSubmitCode: "HOST_RESTART_REQUIRED",
    terminated: true,
    terminalOwnerReleased: false,
  });
  const directInventory = await opfsInventory(page);
  expect(directInventory).not.toEqual(inventoryBefore);
  await page.waitForTimeout(100);
  expect(await page.evaluate(() => ({
    notifications: window.__lmdjTask11.notifications.length,
    responses: window.__lmdjTask11.responses.length,
  })), "publication hang late messages").toEqual(observationsBefore);

  const reopened = await context.newPage();
  await openPackagedHost(reopened);
  const recovered = success(await reopenProject(
    reopened,
    identity,
    identity.patternId,
    { overallDeadlineMs: 5_000, retryDelayMs: 10 },
  ), "reopen after publication settlement watchdog");
  expect([0, 1]).toContain(recovered.project_revision);
  const inspected = success(await hostRequest(reopened, "project.inspect", {}),
    "inspect old-or-new truth after publication settlement watchdog");
  expect(inspected.project_revision).toBe(recovered.project_revision);
  if (inspected.project_revision === 0) {
    expect(success(await hostRequest(reopened, "asset.import", {
      command_id: crypto.randomUUID(),
      expected_revision: 0,
      asset_id: identity.assetId,
      media_type: "audio/wav",
      sidecar: {
        sidecar_bytes: deadlineFixtureBytes.byteLength,
        sidecar_sha256: deadlineFixtureSha256,
      },
    }, { sidecar: deadlineFixtureBytes }), "explicit retry after old truth")
      .project_revision).toBe(1);
  }
  const recoveredInventory = await opfsInventory(reopened);
  expect(recoveredInventory.filter((entry) =>
    entry.includes(".lmdj-host/storage-intents/") && entry.startsWith("file:")))
    .toEqual([]);
  expect(recoveredInventory).not.toEqual(directInventory);
  expect(await reopened.evaluate(() =>
    window.lmdjWebRuntimeController.close())).toBe(true);
  await reopened.close();
});


test("WebKit records capability limitation or completes protocol OPFS restart lifecycle smoke", async ({
  browserName,
  page,
}, testInfo) => {
  test.skip(browserName !== "webkit");
  test.setTimeout(120_000);
  await installTransportObservability(page);
  await page.goto("/index.html");
  await expect.poll(() => page.locator("#host-state").textContent(), {
    timeout: 30_000,
  }).toMatch(/^(?:audio-suspended|failed)$/);
  const capabilities = await webKitCapabilities(page);
  const missing = Object.entries(capabilities)
    .filter(([name, value]) => name !== "worker_reason" && value !== true)
    .map(([name]) => name);
  const state = await page.locator("#host-state").textContent();
  if (state === "failed") {
    const diagnostics = JSON.parse(await page.locator("#diagnostics").textContent());
    expect(diagnostics.error_code).toBe("UNSUPPORTED_WEB_RUNTIME");
    expect(missing.length).toBeGreaterThan(0);
    const limitation = {
      browser: "webkit",
      code: "UNSUPPORTED_WEB_RUNTIME",
      missing,
      worker_reason: capabilities.worker_reason,
    };
    console.log(`LMDJ_WEBKIT_LIMITATION ${JSON.stringify(limitation)}`);
    await testInfo.attach("webkit-limitation.json", {
      body: JSON.stringify(limitation),
      contentType: "application/json",
    });
    return;
  }

  expect(missing).toEqual([]);
  const identity = {
    projectId: crypto.randomUUID(),
    patternId: crypto.randomUUID(),
  };
  expect(success(await hostRequest(page, "host.status", {}), "WebKit status"))
    .toMatchObject({ state: "core-ready" });
  expect(success(await hostRequest(page, "project.create", {
    project_id: identity.projectId,
    bpm: 120,
    initial_pattern: {
      pattern_id: identity.patternId,
      bars: 1,
      events: [],
    },
  }), "WebKit project.create").project_revision).toBe(0);
  expect(success(await hostRequest(page, "snapshot.reload", {
    pattern_id: identity.patternId,
  }), "WebKit snapshot.reload").runtime_ready).toBe(true);
  const beforeMismatch = await hostRequest(page, "project.inspect", {});
  const mismatch = await page.evaluate(() =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 2,
      request_id: crypto.randomUUID(),
      operation: "project.inspect",
      payload: {},
    }, { deadlineMs: 30_000 }));
  expect(mismatch).toMatchObject({
    ok: false,
    error: { code: "HOST_PROTOCOL_MISMATCH" },
  });
  expect(await hostRequest(page, "project.inspect", {})).toEqual(beforeMismatch);
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(true);

  await page.reload();
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  expect(success(await reopenProject(page, identity, identity.patternId),
    "WebKit reopen").project_revision).toBe(0);
  await activateWithGesture(page);
  await page.locator("#audio-suspend").click();
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  await activateWithGesture(page);
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(true);
  await expect(page.locator("#host-state")).toHaveText("closed");
  console.log("LMDJ_WEBKIT_SMOKE {\"status\":\"pass\",\"scope\":\"capability-protocol-opfs-restart-lifecycle\"}");
});
