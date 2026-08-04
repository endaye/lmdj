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


async function reopenProject(page, identity, patternId) {
  const deadline = Date.now() + 10_000;
  let response;
  do {
    response = await hostRequest(page, "project.open", {
      project_id: identity.projectId,
      pattern_id: patternId,
    });
    if (response.ok || response.error?.code !== "PROJECT_BUSY") {
      return response;
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 25));
  } while (Date.now() < deadline);
  return response;
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
  expect(success(await hostRequest(page, "host.close", {}), "host.close").state)
    .toBe("closed");
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
