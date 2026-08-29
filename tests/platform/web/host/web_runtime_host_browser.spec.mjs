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
const fixture44100Bytes = Buffer.from(fixtureBytes);
fixture44100Bytes.writeUInt32LE(44_100, 24);
fixture44100Bytes.writeUInt32LE(88_200, 28);
const deadlineFixtureBytes = Buffer.alloc(32_768);
fixtureBytes.copy(deadlineFixtureBytes);
const deadlineFixtureSha256 = createHash("sha256")
  .update(deadlineFixtureBytes)
  .digest("hex");

const FULL_TRIGGER_COUNT = 500;
const PROTOCOL_VERSION = 1;
const CLAIMED_PUBLICATION_PROOF_DEADLINE_MS = 5_000;
const TERMINAL_RELEASE_OBSERVATION_TIMEOUT_MS = 15_000;
const DIAGNOSTIC_PROJECT_OVERALL_TIMEOUT_MS = 300_000;
const DIAGNOSTIC_PROJECT_STALL_TIMEOUT_MS = 90_000;
const DIAGNOSTIC_PROJECT_POLL_INTERVAL_MS = 250;
const PROJECT_REOPEN_OVERALL_TIMEOUT_MS = 60_000;
const DIAGNOSTIC_PROJECT_CONTRACT =
  "lmdj.web-runtime-host.diagnostic-project.v1";
const DIAGNOSTIC_PROJECT_STORAGE_KEY = DIAGNOSTIC_PROJECT_CONTRACT;
const PREPARED_PROJECT_REVISION = 65;
const COMMITTED_PROJECT_REVISION = 66;


function clone(value) {
  return JSON.parse(JSON.stringify(value));
}


async function setDocumentVisibility(page, hidden) {
  await page.evaluate((nextHidden) => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: nextHidden ? "hidden" : "visible",
    });
    document.dispatchEvent(new Event("visibilitychange"));
  }, hidden);
}


async function installTransportObservability(page) {
  await page.addInitScript(() => {
    const NativeAudioContext = globalThis.AudioContext;
    const audioContexts = [];
    if (typeof NativeAudioContext === "function") {
      globalThis.AudioContext = class ObservableAudioContext
        extends NativeAudioContext {
        constructor(options) {
          super(options);
          audioContexts.push(this);
        }
      };
    }
    window.__lmdjAudioContexts = audioContexts;
    const observations = {
      admittedSequences: [],
      notifications: [],
      requests: [],
      responses: [],
      suppressTriggerOutcomes: false,
    };
    window.__lmdjTask11 = observations;
    const existing = window.__LMDJ_WEB_HOST_SEAMS__ ?? {};
    const observedTransport = {
      async send(request, options) {
        observations.requests.push(request.operation);
        const response = await window.lmdjWebRuntimeHost.transport.send(
          request,
          options,
        );
        observations.responses.push({
          operation: request.operation,
          payload: structuredClone(request.payload),
          response: structuredClone(response),
        });
        if (
          request.operation === "trigger" &&
          Object.hasOwn(request.payload, "velocity") &&
          response?.ok === true
        ) {
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


async function installCapabilityProbeScheduling(page, {
  delayMs,
  timeoutMs = null,
  workerErrorMs = null,
}) {
  await page.addInitScript(({ delayMs, timeoutMs, workerErrorMs }) => {
    const NativeWorker = globalThis.Worker;
    const nativeRevokeObjectURL = URL.revokeObjectURL.bind(URL);
    const observations = { revocations: 0, terminations: 0 };
    let capabilityProbeClaimed = false;
    let capabilityProbeUrl = null;
    globalThis.__lmdjCapabilityProbeScheduling = observations;
    globalThis.Worker = class ScheduledCapabilityWorker extends NativeWorker {
      constructor(url, options) {
        super(url, options);
        const candidateUrl = String(url);
        this.isCapabilityProbe =
          !capabilityProbeClaimed && candidateUrl.startsWith("blob:");
        if (this.isCapabilityProbe) {
          capabilityProbeClaimed = true;
          capabilityProbeUrl = candidateUrl;
        }
      }

      addEventListener(type, listener, options) {
        if (
          this.isCapabilityProbe &&
          type === "error" &&
          workerErrorMs !== null
        ) {
          setTimeout(() => listener.call(this, new Event("error")), workerErrorMs);
          return;
        }
        if (!this.isCapabilityProbe || type !== "message") {
          return super.addEventListener(type, listener, options);
        }
        return super.addEventListener(type, (event) => {
          setTimeout(() => listener.call(this, event), delayMs);
        }, options);
      }

      terminate() {
        if (this.isCapabilityProbe) observations.terminations += 1;
        return super.terminate();
      }
    };
    URL.revokeObjectURL = (url) => {
      if (String(url) === capabilityProbeUrl) observations.revocations += 1;
      return nativeRevokeObjectURL(url);
    };
    if (timeoutMs !== null) {
      globalThis.__LMDJ_WEB_HOST_SEAMS__ = {
        ...(globalThis.__LMDJ_WEB_HOST_SEAMS__ ?? {}),
        capabilityProbeTimeoutMs: timeoutMs,
      };
    }
  }, { delayMs, timeoutMs, workerErrorMs });
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


async function waitForDiagnosticProjectReady(page) {
  const startedAt = Date.now();
  let lastProgressAt = startedAt;
  let lastProgressKey = null;
  let observation = null;

  while (true) {
    observation = await page.evaluate(() => ({
      state: document.querySelector("#diagnostic-project-state")?.textContent ?? null,
      host_state: document.querySelector("#host-state")?.textContent ?? null,
      error_code:
        window.lmdjWebRuntimeController?.diagnostics?.()?.error_code ?? null,
      diagnostic_project_error_code:
        window.lmdjWebRuntimeController?.diagnostics?.()
          ?.diagnostic_project_error_code ?? null,
      request_count: window.__lmdjTask11?.requests?.length ?? 0,
      response_count: window.__lmdjTask11?.responses?.length ?? 0,
      last_request: window.__lmdjTask11?.requests?.at(-1) ?? null,
      last_response: window.__lmdjTask11?.responses?.at(-1)?.operation ?? null,
    }));
    if (observation.state === "ready") {
      return observation;
    }
    if (observation.state !== "loading") {
      throw new Error(
        `diagnostic project entered ${observation.state}: ${JSON.stringify(observation)}`,
      );
    }

    const progressKey = `${observation.request_count}:${observation.response_count}`;
    const now = Date.now();
    if (progressKey !== lastProgressKey) {
      lastProgressKey = progressKey;
      lastProgressAt = now;
    }
    if (
      now - startedAt >= DIAGNOSTIC_PROJECT_OVERALL_TIMEOUT_MS ||
      now - lastProgressAt >= DIAGNOSTIC_PROJECT_STALL_TIMEOUT_MS
    ) {
      throw new Error(
        `diagnostic project readiness deadline elapsed: ${JSON.stringify(observation)}`,
      );
    }
    await page.waitForTimeout(DIAGNOSTIC_PROJECT_POLL_INTERVAL_MS);
  }
}


async function recoverDiagnosticProjectAfterTimeout(page, originalError) {
  const observation = await page.evaluate(() => {
    const diagnostics = window.lmdjWebRuntimeController?.diagnostics?.() ?? {};
    return {
      host_state: document.querySelector("#host-state")?.textContent ?? null,
      error_code: diagnostics.error_code ?? null,
      diagnostic_project_error_code:
        diagnostics.diagnostic_project_error_code ?? null,
    };
  });
  if (
    observation.host_state !== "failed" ||
    observation.error_code !== "HOST_TIMEOUT" ||
    observation.diagnostic_project_error_code !== "HOST_TIMEOUT"
  ) {
    throw originalError;
  }
  console.log(
    `diagnostic project reload handoff recovery: ${JSON.stringify(observation)}`,
  );
  await page.reload();
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  await page.locator("#diagnostic-project-load").click();
  return waitForDiagnosticProjectReady(page);
}


async function enableDeadlineProof(page, settlementWatchdogMs = 1_000) {
  await page.addInitScript((watchdogMs) => {
    window.__LMDJ_WEB_HOST_DEADLINE_PROOF__ = Object.freeze({
      settlementWatchdogMs: watchdogMs,
    });
  }, settlementWatchdogMs);
}


async function delayTerminalAckDelivery(page, delayMs) {
  await page.addInitScript((selectedDelayMs) => {
    const NativeBroadcastChannel = globalThis.BroadcastChannel;
    let ownsHostTerminalChannel = false;
    globalThis.BroadcastChannel = class DelayedTerminalBroadcastChannel
      extends NativeBroadcastChannel {
      constructor(name) {
        super(name);
        this.delayTerminalAck =
          name === "lmdj.web-runtime-host.terminal.v1" &&
          ownsHostTerminalChannel === false;
        if (this.delayTerminalAck) ownsHostTerminalChannel = true;
        this.terminalChannelClosed = false;
      }

      addEventListener(type, listener, options) {
        if (type !== "message" || !this.delayTerminalAck) {
          return super.addEventListener(type, listener, options);
        }
        return super.addEventListener(type, (event) => {
          if (
            event.data?.type !== "released-and-closed" ||
            event.data?.released === true
          ) {
            listener.call(this, event);
            return;
          }
          setTimeout(() => {
            if (!this.terminalChannelClosed) listener.call(this, event);
          }, selectedDelayMs);
        }, options);
      }

      close() {
        this.terminalChannelClosed = true;
        return super.close();
      }
    };
  }, delayMs);
}


async function delayTerminalReleaseRequest(page, delayMs) {
  await page.addInitScript((selectedDelayMs) => {
    const NativeBroadcastChannel = globalThis.BroadcastChannel;
    let ownsHostTerminalChannel = false;
    globalThis.BroadcastChannel = class DelayedTerminalReleaseBroadcastChannel
      extends NativeBroadcastChannel {
      constructor(name) {
        super(name);
        this.delayTerminalRelease =
          name === "lmdj.web-runtime-host.terminal.v1" &&
          ownsHostTerminalChannel === false;
        if (this.delayTerminalRelease) ownsHostTerminalChannel = true;
        this.terminalChannelClosed = false;
      }

      postMessage(message) {
        if (
          this.delayTerminalRelease &&
          message?.type === "release-and-close"
        ) {
          setTimeout(() => {
            if (!this.terminalChannelClosed) {
              NativeBroadcastChannel.prototype.postMessage.call(this, message);
            }
          }, selectedDelayMs);
          return;
        }
        return super.postMessage(message);
      }

      close() {
        this.terminalChannelClosed = true;
        return super.close();
      }
    };
  }, delayMs);
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


async function observationMarker(page) {
  return page.evaluate(() => ({
    admissions: window.__lmdjTask11.admittedSequences.length,
    notifications: window.__lmdjTask11.notifications.length,
    responses: window.__lmdjTask11.responses.length,
  }));
}


async function waitForTriggerResponsesSince(page, responseMarker, expectedCount) {
  // Input release handlers enqueue their Runtime request without awaiting its
  // transport response, so the press outcome is not a release-response barrier.
  await expect.poll(() => page.evaluate((start) =>
    window.__lmdjTask11.responses.slice(start)
      .filter(({ operation }) => operation === "trigger").length,
  responseMarker)).toBe(expectedCount);
  return page.evaluate((start) =>
    window.__lmdjTask11.responses.slice(start)
      .filter(({ operation }) => operation === "trigger")
      .map(({ payload }) => payload),
  responseMarker);
}


async function waitForRecoveryReadiness(page, responseMarker) {
  await expect.poll(() => page.evaluate((start) =>
    window.__lmdjTask11.responses.slice(start).some(({ operation, response }) =>
      operation === "host.status" &&
      response?.ok === true &&
      response.result.control_generation ===
        response.result.acknowledged_generation),
  responseMarker)).toBe(true);
  await page.evaluate(() => new Promise((resolvePromise) => {
    window.setTimeout(resolvePromise, 0);
  }));
  await expect.poll(() => page.evaluate(() => {
    const diagnostics = window.lmdjWebRuntimeController.diagnostics();
    return diagnostics.state === "recovering" &&
      Number.isInteger(diagnostics.control_generation) &&
      diagnostics.control_generation > 0 &&
      diagnostics.control_generation === diagnostics.acknowledged_generation;
  })).toBe(true);
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
  { overallDeadlineMs = PROJECT_REOPEN_OVERALL_TIMEOUT_MS, retryDelayMs = 25 } = {},
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
  test.setTimeout(360_000);
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
  await page.locator("#diagnostic-project-load").click();
  await waitForDiagnosticProjectReady(page);
  await activateWithGesture(page);

  expect(runtimeModuleRequests).not.toContain("/lmdj-web-runtime.js");
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


test("Chromium packaged capability probe tolerates delayed Control Worker response", async ({
  browserName,
  page,
}) => {
  test.skip(browserName !== "chromium");
  await installCapabilityProbeScheduling(page, { delayMs: 2_500 });
  await openPackagedHost(page);
  expect(await page.evaluate(() => ({
    capabilities: window.lmdjWebRuntimeController.diagnostics().capabilities,
    cleanup: window.__lmdjCapabilityProbeScheduling,
  }))).toMatchObject({
    capabilities: {
      opfs: true,
      opfsSyncAccessHandle: true,
      opfsWritableReplace: true,
    },
    cleanup: { revocations: 1, terminations: 1 },
  });
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(true);
});

test("Chromium packaged capability probe deadline reports HOST_TIMEOUT", async ({
  browserName,
  page,
}) => {
  test.skip(browserName !== "chromium");
  await installCapabilityProbeScheduling(page, {
    delayMs: 100,
    timeoutMs: 25,
  });
  await installTransportObservability(page);
  await page.goto("/index.html");
  await expect(page.locator("#host-state")).toHaveText("failed");
  expect(await page.evaluate(() => ({
    cleanup: window.__lmdjCapabilityProbeScheduling,
    errorCode: window.lmdjWebRuntimeController.diagnostics().error_code,
  }))).toEqual({
    cleanup: { revocations: 1, terminations: 1 },
    errorCode: "HOST_TIMEOUT",
  });
  await page.waitForTimeout(125);
  expect(await page.evaluate(() => ({
    cleanup: window.__lmdjCapabilityProbeScheduling,
    errorCode: window.lmdjWebRuntimeController.diagnostics().error_code,
    state: document.querySelector("#host-state").textContent,
  }))).toEqual({
    cleanup: { revocations: 1, terminations: 1 },
    errorCode: "HOST_TIMEOUT",
    state: "failed",
  });
});

test("Chromium packaged capability probe Worker error fails closed and cleans up", async ({
  browserName,
  page,
}) => {
  test.skip(browserName !== "chromium");
  await installCapabilityProbeScheduling(page, {
    delayMs: 100,
    workerErrorMs: 0,
  });
  await installTransportObservability(page);
  await page.goto("/index.html");
  await expect(page.locator("#host-state")).toHaveText("failed");
  expect(await page.evaluate(() => ({
    cleanup: window.__lmdjCapabilityProbeScheduling,
    errorCode: window.lmdjWebRuntimeController.diagnostics().error_code,
  }))).toEqual({
    cleanup: { revocations: 1, terminations: 1 },
    errorCode: "UNSUPPORTED_WEB_RUNTIME",
  });
  await page.waitForTimeout(125);
  expect(await page.evaluate(() => ({
    cleanup: window.__lmdjCapabilityProbeScheduling,
    errorCode: window.lmdjWebRuntimeController.diagnostics().error_code,
    state: document.querySelector("#host-state").textContent,
  }))).toEqual({
    cleanup: { revocations: 1, terminations: 1 },
    errorCode: "UNSUPPORTED_WEB_RUNTIME",
    state: "failed",
  });
});


test("trigger response proof waits for the asynchronous release boundary", async ({
  page,
}) => {
  await page.evaluate(() => {
    window.__lmdjTask11 = {
      responses: [{
        operation: "trigger",
        payload: { slot: 0, velocity: 100 },
      }],
    };
    window.setTimeout(() => {
      window.__lmdjTask11.responses.push({
        operation: "trigger",
        payload: { slot: 0, kind: "release" },
      });
    }, 100);
  });

  expect(await waitForTriggerResponsesSince(page, 0, 2)).toEqual([
    { slot: 0, velocity: 100 },
    { slot: 0, kind: "release" },
  ]);
});


test("Chromium visible diagnostic project completes the packaged runtime journey", async ({
  browserName,
  context,
  page,
}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(720_000);
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
  await expect(page.locator("#audio-activate")).toBeDisabled();
  await page.locator("#diagnostic-project-load").click();
  await waitForDiagnosticProjectReady(page);
  await expect(page.locator("#audio-activate")).toBeEnabled();
  await page.locator("#audio-activate").click();
  await expect(page.locator("#host-state")).toHaveText("running");
  const runtimeScriptPath = await page.evaluate(async () => {
    const manifest = await fetch("./host-manifest.json").then((response) =>
      response.json());
    return manifest.assets.find(({ role }) => role === "runtime_script").path;
  });
  const runtimeScriptPathname = new URL(runtimeScriptPath, page.url()).pathname;
  const pointerMarker = await observationMarker(page);
  await page.locator("#pad-0").click();
  await expect.poll(() => page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.length - start,
  pointerMarker.admissions)).toBe(1);
  const pointerAdmissions = await page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.slice(start),
  pointerMarker.admissions);
  expect(pointerAdmissions).toHaveLength(1);
  await proveExactOutcomes(
    page,
    pointerAdmissions,
    pointerMarker.notifications,
  );
  expect(await waitForTriggerResponsesSince(
    page,
    pointerMarker.responses,
    2,
  )).toEqual([
    { slot: 0, velocity: 100 },
    { slot: 0, kind: "release" },
  ]);

  const keyboardMarker = await observationMarker(page);
  await page.keyboard.press("s");
  await expect.poll(() => page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.length - start,
  keyboardMarker.admissions)).toBe(1);
  const keyboardAdmissions = await page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.slice(start),
  keyboardMarker.admissions);
  expect(keyboardAdmissions).toHaveLength(1);
  await proveExactOutcomes(
    page,
    keyboardAdmissions,
    keyboardMarker.notifications,
  );
  expect(await waitForTriggerResponsesSince(
    page,
    keyboardMarker.responses,
    2,
  )).toEqual([
    { slot: 9, velocity: 100 },
    { slot: 9, kind: "release" },
  ]);

  const burstCodes = [
    "KeyQ", "KeyW", "KeyE", "KeyR", "KeyT", "KeyY", "KeyU", "KeyI",
    "KeyA", "KeyS", "KeyD", "KeyF", "KeyG", "KeyH", "KeyJ", "KeyK",
  ];
  const burstMarker = await observationMarker(page);
  await page.evaluate((codes) => {
    for (const code of codes) {
      window.dispatchEvent(new KeyboardEvent("keydown", { code }));
      window.dispatchEvent(new KeyboardEvent("keyup", { code }));
    }
  }, burstCodes);
  await expect.poll(() => page.evaluate((start) => {
    const diagnostics = window.lmdjWebRuntimeController.diagnostics();
    return {
      state: diagnostics.state,
      admissions:
        window.__lmdjTask11.admittedSequences.length - start.admissions,
      responses:
        window.__lmdjTask11.responses.slice(start.responses)
          .filter(({ operation }) => operation === "trigger").length,
    };
  }, burstMarker)).toEqual({
    state: "running",
    admissions: burstCodes.length,
    responses: burstCodes.length * 2,
  });
  const burstAdmissions = await page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.slice(start),
  burstMarker.admissions);
  await proveExactOutcomes(
    page,
    burstAdmissions,
    burstMarker.notifications,
  );
  expect(await page.evaluate((start) =>
    window.__lmdjTask11.responses.slice(start)
      .filter(({ operation }) => operation === "trigger")
      .map(({ payload }) => payload),
  burstMarker.responses)).toEqual(
    burstCodes.flatMap((_, slot) => [
      { slot, velocity: 100 },
      { slot, kind: "release" },
    ]),
  );

  const descriptor = await page.evaluate((storageKey) =>
    JSON.parse(localStorage.getItem(storageKey)),
  DIAGNOSTIC_PROJECT_STORAGE_KEY);
  expect(Object.keys(descriptor).sort()).toEqual([
    "asset_id",
    "contract",
    "pattern_id",
    "project_id",
  ]);
  expect(descriptor).toEqual({
    contract: DIAGNOSTIC_PROJECT_CONTRACT,
    project_id: expect.stringMatching(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    ),
    pattern_id: expect.stringMatching(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    ),
    asset_id: expect.stringMatching(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    ),
  });
  const diagnosticText = await page.locator("#diagnostics").textContent();
  for (const identifier of [
    descriptor.project_id,
    descriptor.pattern_id,
    descriptor.asset_id,
  ]) {
    expect(diagnosticText).not.toContain(identifier);
  }

  const firstPreparationResponses = await page.evaluate(() =>
    window.__lmdjTask11.responses.map(({ operation, response }) => ({
      operation,
      response,
    })));
  expect(firstPreparationResponses.filter(
    ({ operation }) => operation === "project.create",
  )).toHaveLength(1);
  expect(firstPreparationResponses.filter(
    ({ operation }) => operation === "asset.import",
  )).toHaveLength(1);
  expect(firstPreparationResponses.filter(
    ({ operation }) => operation === "pad.assign",
  )).toHaveLength(64);
  const initiallyPrepared = success(
    await hostRequest(page, "project.inspect", {}),
    "project.inspect after visible preparation",
  );
  expect(initiallyPrepared.project_revision).toBe(PREPARED_PROJECT_REVISION);
  expect(Object.keys(initiallyPrepared.project.assets)).toEqual([
    descriptor.asset_id,
  ]);
  expect(initiallyPrepared.project.banks).toHaveLength(4);
  for (const [bank, bankState] of initiallyPrepared.project.banks.entries()) {
    expect(bankState.bank).toBe(bank);
    expect(bankState.pads).toHaveLength(16);
    for (const [pad, padState] of bankState.pads.entries()) {
      expect(padState).toMatchObject({
        pad,
        asset_id: descriptor.asset_id,
      });
    }
  }
  const initialSnapshot = {
    generation: await page.evaluate(() =>
      window.lmdjWebRuntimeController.diagnostics()
        .diagnostic_project_generation),
  };
  expect(initialSnapshot.generation).toBeGreaterThan(0);

  await page.reload();
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  await expect(page.locator("#audio-activate")).toBeDisabled();
  await page.locator("#diagnostic-project-load").click();
  await waitForDiagnosticProjectReady(page);
  await expect(page.locator("#audio-activate")).toBeEnabled();
  const reopenedDescriptor = await page.evaluate((storageKey) =>
    JSON.parse(localStorage.getItem(storageKey)),
  DIAGNOSTIC_PROJECT_STORAGE_KEY);
  expect(reopenedDescriptor).toEqual(descriptor);
  const reopenResponses = await page.evaluate(() =>
    window.__lmdjTask11.responses.map(({ operation, response }) => ({
      operation,
      response,
    })));
  const projectOpenResponses = reopenResponses.filter(
    ({ operation }) => operation === "project.open",
  );
  expect(projectOpenResponses.length).toBeGreaterThan(0);
  expect(projectOpenResponses.filter(({ response }) => response.ok === true))
    .toHaveLength(1);
  expect(projectOpenResponses.at(-1)?.response).toMatchObject({
    ok: true,
    result: { project_revision: PREPARED_PROJECT_REVISION },
  });
  expect(projectOpenResponses.slice(0, -1).every(({ response }) =>
    response.error?.code === "PROJECT_BUSY")).toBe(true);
  expect(reopenResponses.filter(
    ({ operation }) => operation === "project.create",
  )).toHaveLength(0);
  expect(reopenResponses.filter(
    ({ operation }) => operation === "asset.import",
  )).toHaveLength(0);
  expect(reopenResponses.filter(
    ({ operation }) => operation === "pad.assign",
  )).toHaveLength(0);
  await page.locator("#audio-activate").click();
  await expect(page.locator("#host-state")).toHaveText("running");
  expect(success(
    await hostRequest(page, "project.inspect", {}),
    "project.inspect after visible reopen",
  ).project_revision).toBe(PREPARED_PROJECT_REVISION);

  const identity = {
    projectId: descriptor.project_id,
    patternId: descriptor.pattern_id,
    committedPatternId: crypto.randomUUID(),
    assetId: descriptor.asset_id,
    asset44100Id: crypto.randomUUID(),
  };
  expect(runtimeModuleRequests).not.toContain("/lmdj-web-runtime.js");
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

  const committed = success(await hostRequest(page, "pattern.create", {
    command_id: crypto.randomUUID(),
    expected_revision: PREPARED_PROJECT_REVISION,
    pattern_id: identity.committedPatternId,
    bars: 2,
  }), "pattern.create");
  expect(committed).toMatchObject({
    pattern_id: identity.committedPatternId,
    project_revision: COMMITTED_PROJECT_REVISION,
  });
  const inspectedAfterCommit = success(
    await hostRequest(page, "project.inspect", {}),
    "project.inspect after commit",
  );
  expect(inspectedAfterCommit.project_revision).toBe(COMMITTED_PROJECT_REVISION);
  expect(inspectedAfterCommit.project.patterns[identity.committedPatternId].events)
    .toEqual([]);
  expect(success(await hostRequest(page, "sequence.recovery.list", {}),
    "sequence.recovery.list").candidates).toEqual([]);

  await page.reload();
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  await page.locator("#diagnostic-project-load").click();
  try {
    await waitForDiagnosticProjectReady(page);
  } catch (error) {
    await recoverDiagnosticProjectAfterTimeout(page, error);
  }
  await expect(page.locator("#audio-activate")).toBeEnabled();
  const reopened = success(
    await reopenProject(page, identity, identity.committedPatternId),
    "project.open after page and Worker reload",
  );
  expect(reopened).toMatchObject({
    project_revision: COMMITTED_PROJECT_REVISION,
    runtime_ready: true,
    pattern_id: identity.committedPatternId,
  });
  const inspectedAfterRestart = success(
    await hostRequest(page, "project.inspect", {}),
    "project.inspect after restart",
  );
  expect(inspectedAfterRestart.project_revision).toBe(COMMITTED_PROJECT_REVISION);
  expect(inspectedAfterRestart.project.patterns[identity.committedPatternId].events)
    .toEqual([]);
  expect(success(await hostRequest(page, "sequence.recovery.list", {}),
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
    "status before 44.1 kHz Snapshot");
  expect(priorStatus.control_generation).toBe(reopened.generation);
  const imported44100 = success(await hostRequest(page, "asset.import", {
    command_id: crypto.randomUUID(),
    expected_revision: COMMITTED_PROJECT_REVISION,
    asset_id: identity.asset44100Id,
    media_type: "audio/wav",
    sidecar: {
      sidecar_bytes: fixture44100Bytes.byteLength,
      sidecar_sha256: createHash("sha256").update(fixture44100Bytes).digest("hex"),
    },
  }, { sidecar: fixture44100Bytes }), "44.1 kHz fixture import");
  expect(imported44100.project_revision).toBe(COMMITTED_PROJECT_REVISION + 1);
  expect(success(await hostRequest(page, "pad.assign", {
    command_id: crypto.randomUUID(),
    expected_revision: COMMITTED_PROJECT_REVISION + 1,
    slot: { bank: 0, pad: 0 },
    asset_id: identity.asset44100Id,
  }), "assign 44.1 kHz fixture").project_revision).toBe(
    COMMITTED_PROJECT_REVISION + 2,
  );
  const accepted44100Marker = await observationMarker(page);
  const accepted44100Snapshot = success(await hostRequest(page, "snapshot.reload", {
    pattern_id: identity.committedPatternId,
  }), "publish 44.1 kHz Snapshot");
  expect(accepted44100Snapshot.runtime_ready).toBe(true);
  expect(accepted44100Snapshot.generation).toBeGreaterThan(
    priorStatus.control_generation,
  );
  const accepted44100Status = success(await hostRequest(page, "host.status", {}),
    "status after accepted 44.1 kHz Snapshot");
  expect(await page.evaluate((start) =>
    window.__lmdjTask11.notifications.slice(start)
      .filter(({ event }) => event === "snapshot.rejected"),
  accepted44100Marker.notifications)).toEqual([]);
  expect(accepted44100Status.control_generation).toBe(
    accepted44100Snapshot.generation,
  );
  expect(accepted44100Status.acknowledged_generation).toBe(
    accepted44100Snapshot.generation,
  );
  expect(success(await hostRequest(page, "project.inspect", {}),
    "project.inspect after 44.1 kHz publication").project_revision).toBe(
    COMMITTED_PROJECT_REVISION + 2,
  );
  expect(success(await hostRequest(page, "pad.assign", {
    command_id: crypto.randomUUID(),
    expected_revision: COMMITTED_PROJECT_REVISION + 2,
    slot: { bank: 0, pad: 0 },
    asset_id: identity.assetId,
  }), "restore original 48 kHz fixture").project_revision).toBe(
    COMMITTED_PROJECT_REVISION + 3,
  );
  const republished = success(await hostRequest(page, "snapshot.reload", {
    pattern_id: identity.committedPatternId,
  }), "republish after restoring 48 kHz Snapshot");
  expect(republished.generation).toBeGreaterThan(accepted44100Snapshot.generation);

  await page.locator("#audio-suspend").click();
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  await activateWithGesture(page);
  const recoveryMarker = await observationMarker(page);
  await setDocumentVisibility(page, true);
  await expect(page.locator("#host-state")).toHaveText("recovering");
  await waitForRecoveryReadiness(page, recoveryMarker.responses);
  await page.locator("#pad-0").click();
  await expect.poll(() => page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.length - start,
  recoveryMarker.admissions)).toBe(1);
  await expect(page.locator("#host-state")).toHaveText("running");
  const recoverySequence = await page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.slice(start),
  recoveryMarker.admissions);
  await proveExactOutcomes(page, recoverySequence, recoveryMarker.notifications);
  await setDocumentVisibility(page, false);

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
  test.setTimeout(420_000);
  await openPackagedHost(page);
  await page.locator("#diagnostic-project-load").click();
  await waitForDiagnosticProjectReady(page);
  const descriptor = await page.evaluate((storageKey) =>
    JSON.parse(localStorage.getItem(storageKey)),
  DIAGNOSTIC_PROJECT_STORAGE_KEY);
  const identity = {
    projectId: descriptor.project_id,
    patternId: descriptor.pattern_id,
  };
  await activateWithGesture(page);
  const marker = await observationMarker(page);
  await setDocumentVisibility(page, true);
  await expect(page.locator("#host-state")).toHaveText("recovering");
  await waitForRecoveryReadiness(page, marker.responses);
  await page.evaluate(() => {
    window.__lmdjTask11.suppressTriggerOutcomes = true;
  });
  await page.locator("#pad-0").click();
  await expect.poll(() => page.evaluate((start) =>
    window.__lmdjTask11.admittedSequences.length - start,
  marker.admissions)).toBe(1);
  await expect(page.locator("#host-state")).toHaveText("restart-required", {
    timeout: 3_000,
  });
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.diagnostics()))
    .toMatchObject({ state: "restart-required", error_code: "HOST_TIMEOUT" });
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(false);
  await expect.poll(() => terminalTransportEvidence(page), {
    message: "recovery outcome timeout terminal owner release",
    timeout: TERMINAL_RELEASE_OBSERVATION_TIMEOUT_MS,
  }).toMatchObject({
    controller: { state: "restart-required", error_code: "HOST_TIMEOUT" },
    newSubmitCode: "HOST_STATE_INVALID",
    terminated: true,
    terminalOwnerReleased: true,
  });

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
  expect(reopened.project_revision).toBe(PREPARED_PROJECT_REVISION);
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
  test.setTimeout(180_000);
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
  await expect(page.locator("#host-state")).toHaveText("restart-required", {
    timeout: TERMINAL_RELEASE_OBSERVATION_TIMEOUT_MS,
  });
  await expect.poll(() => terminalTransportEvidence(page), {
    timeout: TERMINAL_RELEASE_OBSERVATION_TIMEOUT_MS,
  }).toMatchObject({
    controller: { state: "restart-required", error_code: "HOST_TIMEOUT" },
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
      claimAttempted: false,
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
    if (index === 0) {
      await delayTerminalAckDelivery(owner, 300);
    } else {
      await delayTerminalReleaseRequest(owner, 300);
    }
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
    await expect(owner.locator("#host-state"), selected.name).toHaveText(
      "restart-required",
    );
    await expect.poll(() => terminalTransportEvidence(owner), {
      message: `${selected.name} responsive owner release`,
      timeout: TERMINAL_RELEASE_OBSERVATION_TIMEOUT_MS,
    }).toMatchObject({
      controller: { state: "restart-required", error_code: "HOST_TIMEOUT" },
      newSubmitCode: "HOST_TIMEOUT",
      terminated: true,
      terminalOwnerReleased: true,
    });
    if (index === 0) {
      await expect.poll(
        () => terminalAckAttackEvidence(owner),
      ).toMatchObject({
        forgedAcksSent: 2,
        duplicateReleaseRequestsSent: 2,
        observedWorkerAcks: 1,
        acceptedConsumes: 1,
      });
      expect(await replayConsumedTerminalAck(owner)).toBe(-1);
      expect(await terminalAckAttackEvidence(owner)).toMatchObject({
        acceptedConsumes: 1,
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
    expect(await owner.evaluate(() =>
      window.lmdjWebRuntimeController.close()), selected.name).toBe(false);

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
    {
      deadlineMs: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS,
      gate: "unresponsive-cancellation",
    },
  );
  await expect.poll(
    () => deadlineProofState(page, requestId),
    { timeout: 30_000 },
  ).toMatchObject({
    entered_facade: true,
    claim_attempted: true,
    gate: "unresponsive-cancellation",
  });
  // The deadline may cancel publication immediately before the claim callback
  // records whether it started open. Both interleavings still enter and block
  // the real claim path; the assertions below retain cancellation authority.
  await expect.poll(() => deadlineProofState(page, requestId), {
    timeout: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS + 5_000,
  }).toMatchObject({
    publication: "cancelled",
    cancel_calls: 2,
    last_cancel_result: "cancelled",
  });
  expect(await deadlineMutationOutcome(page, requestId)).toMatchObject({
    error: { code: "HOST_TIMEOUT" },
  });
  await expect(page.locator("#host-state")).toHaveText("restart-required", {
    timeout: TERMINAL_RELEASE_OBSERVATION_TIMEOUT_MS,
  });
  await page.waitForTimeout(150);
  expect(await terminalTransportEvidence(page)).toMatchObject({
    controller: { state: "restart-required", error_code: "HOST_TIMEOUT" },
    newSubmitCode: "HOST_TIMEOUT",
    terminated: true,
    terminalOwnerReleased: false,
  });
  await expect.poll(() => terminalAckAttackEvidence(page)).toMatchObject({
    forgedAcksSent: 2,
    duplicateReleaseRequestsSent: 2,
    observedWorkerAcks: 0,
    acceptedConsumes: 0,
  });
  const attackEvidence = await terminalAckAttackEvidence(page);
  expect([1, 2, 3]).toContain(attackEvidence.rejectedConsumes);
  expect(await replayConsumedTerminalAck(page)).toBe(-1);
  expect(await terminalAckAttackEvidence(page)).toMatchObject({
    acceptedConsumes: 0,
    rejectedConsumes: attackEvidence.rejectedConsumes + 1,
  });
  expect(await releaseDeadlineProof(page), "release terminated proof gate")
    .toBe(true);
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
        deadlineMs: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS,
        gate: "after-claim",
        forcePublicationError: selected.forcePublicationError,
      },
    );
    await expect.poll(() => deadlineProofState(owner, requestId), {
      message: `${selected.name} entered Facade and won publication claim`,
      timeout: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS + 5_000,
    }).toMatchObject({
      entered_facade: true,
      claim_attempted: true,
      gate: "after-claim",
      publication: "publish-claimed",
    });
    await expect.poll(() => deadlineProofState(owner, requestId), {
      message: `${selected.name} deadline observed claimed publication`,
      timeout: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS + 1_000,
      intervals: [5, 10, 20, 50],
    }).toMatchObject({
      publication: "publish-claimed",
      cancel_calls: 1,
      last_cancel_result: "publish-claimed",
    });
    expect(await releaseDeadlineProof(owner), selected.name).toBe(true);
    const outcome = await deadlineMutationOutcome(owner, requestId);
    const settledProof = await deadlineProofState(owner, requestId);
    if (outcome?.error?.code === "HOST_RESTART_REQUIRED") {
      expect(outcome, `${selected.name}: ${JSON.stringify(settledProof)}`)
        .toMatchObject({
        error: {
          code: "HOST_RESTART_REQUIRED",
          details: {
            terminal_state: "restart-required",
            mutation_outcome: "unknown",
          },
        },
      });
      await expect(owner.locator("#host-state")).toHaveText("failed");
      expect(await terminalTransportEvidence(owner)).toMatchObject({
        controller: { state: "failed", error_code: "HOST_RESTART_REQUIRED" },
        newSubmitCode: "HOST_RESTART_REQUIRED",
        terminated: true,
      });

      const reopened = await context.newPage();
      await openPackagedHost(reopened);
      const recovered = success(await reopenProject(
        reopened,
        identity,
        identity.patternId,
        { overallDeadlineMs: 5_000, retryDelayMs: 10 },
      ), `${selected.name} reopen after settlement watchdog`);
      if (settledProof.publication === "committed") {
        expect(recovered.project_revision, selected.name).toBe(1);
      } else if (settledProof.publication === "aborted") {
        expect(recovered.project_revision, selected.name).toBe(0);
      } else {
        expect([0, 1], selected.name).toContain(recovered.project_revision);
      }
      expect(success(await hostRequest(reopened, "project.inspect", {})),
        `${selected.name} inspect recovered truth`).toMatchObject({
        project_revision: recovered.project_revision,
      });
      await expect.poll(async () => (await opfsInventory(reopened)).filter(
        (entry) => entry.includes(".lmdj-host/storage-intents/") &&
          entry.startsWith("file:"),
      )).toEqual([]);
      expect(await reopened.evaluate(() =>
        window.lmdjWebRuntimeController.close()), selected.name).toBe(true);
      await reopened.close();
      await owner.close();
      continue;
    }
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
    {
      deadlineMs: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS,
      gate: "after-claim",
    },
  );
  await expect.poll(() => deadlineProofState(page, requestId), {
    timeout: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS + 5_000,
  }).toMatchObject({
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
  await expect(page.locator("#host-state")).toHaveText("restart-required", {
    timeout: TERMINAL_RELEASE_OBSERVATION_TIMEOUT_MS,
  });
  expect(await terminalTransportEvidence(page)).toMatchObject({
    controller: {
      state: "restart-required",
      error_code: "HOST_RESTART_REQUIRED",
    },
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


test("Stage 9 Chromium records across an acknowledged switch, reloads, and exposes observer status", async ({
  browserName,
  context,
  page,
}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(420_000);
  await openPackagedHost(page);
  await page.locator("#diagnostic-project-load").click();
  await waitForDiagnosticProjectReady(page);
  const descriptor = await page.evaluate((storageKey) =>
    JSON.parse(localStorage.getItem(storageKey)),
  DIAGNOSTIC_PROJECT_STORAGE_KEY);
  await activateWithGesture(page);

  const firstSessionId = crypto.randomUUID();
  const firstCommandId = crypto.randomUUID();
  const begun = await page.evaluate(({sessionId, patternId, expectedRevision}) =>
    window.lmdjWebRuntimeController.beginSequence({
      sessionId,
      patternId,
      expectedRevision,
    }), {
    sessionId: firstSessionId,
    patternId: descriptor.pattern_id,
    expectedRevision: PREPARED_PROJECT_REVISION,
  });
  expect(begun).toMatchObject({
    state: "active",
    sessionId: firstSessionId,
    patternId: descriptor.pattern_id,
    expectedRevision: PREPARED_PROJECT_REVISION,
    transportAnchor: {bpm: 120, tickNumerator: 0},
  });
  const recorded = await page.evaluate(async ({sessionId}) => {
    const press = await window.lmdjWebRuntimeController.recordSequenceEvent({
      sessionId,
      slot: 0,
      velocity: 100,
      pressed: true,
    });
    const release = await window.lmdjWebRuntimeController.recordSequenceEvent({
      sessionId,
      slot: 0,
      velocity: 0,
      pressed: false,
    });
    return {press, release};
  }, {sessionId: firstSessionId});
  expect(recorded.press.inputSequence).toBe(1);
  expect(recorded.release.inputSequence).toBe(2);
  expect(recorded.release.runtimeFrame).toBeGreaterThanOrEqual(
    recorded.press.runtimeFrame,
  );

  const observer = await context.newPage();
  await openPackagedHost(observer);
  const observed = await observer.evaluate((projectId) =>
    window.lmdjWebRuntimeController.querySequenceStatus(projectId),
  descriptor.project_id);
  expect(observed).toMatchObject({
    state: "active",
    sessionId: firstSessionId,
    patternId: descriptor.pattern_id,
    pendingEventCount: 1,
  });
  expect(await hostRequest(observer, "project.open", {
    project_id: descriptor.project_id,
    pattern_id: descriptor.pattern_id,
  })).toMatchObject({ok: false, error: {code: "PROJECT_BUSY"}});
  expect(await observer.evaluate(() =>
    window.lmdjWebRuntimeController.refreshSequenceDiagnostics()))
    .toEqual({state: "active", switch_pending: false, recovery_count: 0});
  expect(await observer.evaluate(() =>
    window.lmdjWebRuntimeController.close())).toBe(true);
  await observer.close();

  const stopped = await page.evaluate(({sessionId, commandId}) =>
    window.lmdjWebRuntimeController.stopSequence({sessionId, commandId}),
  {sessionId: firstSessionId, commandId: firstCommandId});
  expect(stopped).toMatchObject({
    state: "inactive",
    committedRevision: PREPARED_PROJECT_REVISION + 1,
    replayed: false,
  });
  const replayed = await page.evaluate(({sessionId, commandId}) =>
    window.lmdjWebRuntimeController.stopSequence({sessionId, commandId}),
  {sessionId: firstSessionId, commandId: firstCommandId});
  expect(replayed).toMatchObject({
    committedRevision: stopped.committedRevision,
    replayed: true,
  });

  await page.reload();
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  await page.locator("#diagnostic-project-load").click();
  await waitForDiagnosticProjectReady(page);
  const persistedStatus = await page.evaluate((projectId) =>
    window.lmdjWebRuntimeController.querySequenceStatus(projectId),
  descriptor.project_id);
  expect(persistedStatus).toMatchObject({
    state: "inactive",
    pendingEventCount: 0,
  });
  expect(success(await hostRequest(page, "sequence.recovery.list", {}),
    "Stage 9 recovery after first Stop reload").candidates).toEqual([]);
  const persistedAfterStop = success(
    await hostRequest(page, "project.inspect", {}),
    "Stage 9 first Stop truth after page and Worker reload",
  );
  expect(persistedAfterStop.project_revision).toBe(stopped.committedRevision);
  const persistedEvent =
    persistedAfterStop.project.patterns[descriptor.pattern_id].events;
  expect(persistedEvent).toHaveLength(1);
  expect(persistedEvent[0]).toMatchObject({
    slot: {bank: 0, pad: 0},
    velocity: 100,
  });
  expect(persistedEvent[0].duration_tick).toBeGreaterThan(0);
  await activateWithGesture(page);

  const nextPatternId = crypto.randomUUID();
  const created = await page.evaluate(({patternId, expectedRevision}) =>
    window.lmdjWebRuntimeController.createPattern({
      patternId,
      bars: 1,
      expectedRevision,
    }), {
    patternId: nextPatternId,
    expectedRevision: stopped.committedRevision,
  });
  expect(created.committedRevision).toBe(stopped.committedRevision + 1);
  const secondSessionId = crypto.randomUUID();
  const secondCommandId = crypto.randomUUID();
  await page.evaluate(({sessionId, patternId, expectedRevision}) =>
    window.lmdjWebRuntimeController.beginSequence({
      sessionId,
      patternId,
      expectedRevision,
    }), {
    sessionId: secondSessionId,
    patternId: descriptor.pattern_id,
    expectedRevision: created.committedRevision,
  });
  await page.evaluate(() => {
    window.__sequenceBoundaries = [];
    window.lmdjWebRuntimeController.subscribeSequenceBarBoundary((boundary) => {
      window.__sequenceBoundaries.push(boundary);
    });
  });
  await page.evaluate(async ({sessionId, nextPatternId}) => {
    await window.lmdjWebRuntimeController.recordSequenceEvent({
      sessionId, slot: 1, velocity: 127, pressed: true,
    });
    await window.lmdjWebRuntimeController.recordSequenceEvent({
      sessionId, slot: 1, velocity: 0, pressed: false,
    });
    return window.lmdjWebRuntimeController.requestPatternSwitch({
      sessionId, nextPatternId,
    });
  }, {sessionId: secondSessionId, nextPatternId});
  await expect.poll(() => page.evaluate(() => window.__sequenceBoundaries), {
    timeout: 30_000,
  }).toEqual([expect.objectContaining({
    sessionId: secondSessionId,
    patternId: nextPatternId,
  })]);
  const continued = await page.evaluate(async ({sessionId}) => {
    const press = await window.lmdjWebRuntimeController.recordSequenceEvent({
      sessionId, slot: 2, velocity: 90, pressed: true,
    });
    const release = await window.lmdjWebRuntimeController.recordSequenceEvent({
      sessionId, slot: 2, velocity: 0, pressed: false,
    });
    return {press, release};
  }, {sessionId: secondSessionId});
  expect(continued.press).toMatchObject({
    state: "active",
    patternId: nextPatternId,
  });
  const switchedStop = await page.evaluate(({sessionId, commandId}) =>
    window.lmdjWebRuntimeController.stopSequence({sessionId, commandId}),
  {sessionId: secondSessionId, commandId: secondCommandId});
  expect(switchedStop).toMatchObject({
    committedRevision: created.committedRevision + 2,
    replayed: false,
  });

  const cancelledSessionId = crypto.randomUUID();
  const cancelledCommandId = crypto.randomUUID();
  await page.evaluate(({sessionId, patternId, expectedRevision}) =>
    window.lmdjWebRuntimeController.beginSequence({
      sessionId, patternId, expectedRevision,
    }), {
    sessionId: cancelledSessionId,
    patternId: nextPatternId,
    expectedRevision: switchedStop.committedRevision,
  });
  await page.evaluate(() => {
    window.__sequenceBoundaries = [];
  });
  await page.evaluate(async ({sessionId, nextPatternId}) => {
    await window.lmdjWebRuntimeController.recordSequenceEvent({
      sessionId, slot: 3, velocity: 80, pressed: true,
    });
    await window.lmdjWebRuntimeController.recordSequenceEvent({
      sessionId, slot: 3, velocity: 0, pressed: false,
    });
    return window.lmdjWebRuntimeController.requestPatternSwitch({
      sessionId, nextPatternId,
    });
  }, {sessionId: cancelledSessionId, nextPatternId: descriptor.pattern_id});
  const rejectedBpm = await page.evaluate(async ({
    sessionId, expectedRevision,
  }) => {
    try {
      await window.lmdjWebRuntimeController.updateSequenceSettings({
        expectedRevision,
        sessionId,
        bpm: 90,
        quantizeEnabled: null,
        swingPercent: null,
      });
      return null;
    } catch (error) {
      return {code: error.code, message: error.message};
    }
  }, {
    sessionId: cancelledSessionId,
    expectedRevision: switchedStop.committedRevision,
  });
  expect(rejectedBpm).toMatchObject({code: "INVALID_ARGUMENT"});
  const cancelledStopAttempt = await page.evaluate(async ({
    sessionId, commandId,
  }) => {
    try {
      return {
        result: await window.lmdjWebRuntimeController.stopSequence({
          sessionId, commandId,
        }),
        error: null,
      };
    } catch (error) {
      return {result: null, error: {code: error.code, message: error.message}};
    }
  }, {sessionId: cancelledSessionId, commandId: cancelledCommandId});
  let cancelledStop = cancelledStopAttempt.result;
  if (cancelledStopAttempt.error !== null) {
    // The realtime Pattern boundary may win the Stop linearization race. The
    // durable Stop receipt must remain replayable with the same command ID.
    expect(cancelledStopAttempt.error).toMatchObject({code: "INVALID_ARGUMENT"});
    cancelledStop = await page.evaluate(({sessionId, commandId}) =>
      window.lmdjWebRuntimeController.stopSequence({sessionId, commandId}),
    {sessionId: cancelledSessionId, commandId: cancelledCommandId});
    expect(cancelledStop.replayed).toBe(true);
  }
  expect(cancelledStop).toMatchObject({
    state: "inactive",
    committedRevision: switchedStop.committedRevision + 1,
  });
  await page.waitForTimeout(2_500);
  const cancelledBoundaries = await page.evaluate(() =>
    window.__sequenceBoundaries);
  if (cancelledStopAttempt.error === null) {
    expect(cancelledBoundaries).toEqual([]);
    expect(cancelledStop.replayed).toBe(false);
  } else {
    // Boundary notification delivery may itself race the fail-closed Runtime
    // clear. If it was already delivered, it must name the crossed target.
    expect(cancelledBoundaries.length).toBeLessThanOrEqual(1);
    if (cancelledBoundaries.length === 1) {
      expect(cancelledBoundaries[0]).toMatchObject({
        sessionId: cancelledSessionId,
        patternId: descriptor.pattern_id,
      });
    }
  }

  const truth = success(await hostRequest(page, "project.inspect", {}),
    "Stage 9 inspect switch truth");
  const pattern = truth.project.patterns[descriptor.pattern_id];
  expect(pattern.events).toHaveLength(2);
  expect(pattern.events.map(({slot}) => `${slot.bank}:${slot.pad}`).sort())
    .toEqual(["0:0", "0:1"]);
  expect(pattern.events.map(({velocity}) => velocity).sort((left, right) =>
    left - right)).toEqual([100, 127]);
  expect(pattern.events.every(({duration_tick: durationTick}) =>
    durationTick > 0)).toBe(true);
  const switchedPattern = truth.project.patterns[nextPatternId];
  expect(switchedPattern.events).toHaveLength(2);
  // Canonical Pattern order is onset-first. These events were recorded in
  // separate sessions, so a loop wrap can legitimately place either Pad
  // first even though both identities and values must survive.
  expect(switchedPattern.events.map(({slot, velocity}) => ({slot, velocity}))
    .sort((left, right) => left.slot.pad - right.slot.pad)).toEqual([
    {slot: {bank: 0, pad: 2}, velocity: 90},
    {slot: {bank: 0, pad: 3}, velocity: 80},
  ]);
  expect(switchedPattern.events.every(({duration_tick: durationTick}) =>
    durationTick > 0)).toBe(true);
  expect(success(await hostRequest(page, "snapshot.reload", {
    pattern_id: nextPatternId,
  }), "Stage 9 reload-visible truth")).toMatchObject({
    project_revision: cancelledStop.committedRevision,
    pattern_id: nextPatternId,
    runtime_ready: true,
  });
  expect(await page.evaluate(() =>
    window.lmdjWebRuntimeController.close())).toBe(true);
});


test("WebKit records capability limitation or completes protocol OPFS restart lifecycle smoke", async ({
  browserName,
  page,
}, testInfo) => {
  test.skip(browserName !== "webkit");
  test.setTimeout(420_000);
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
  await page.locator("#diagnostic-project-load").click();
  await waitForDiagnosticProjectReady(page);
  const descriptor = await page.evaluate((storageKey) =>
    JSON.parse(localStorage.getItem(storageKey)),
  DIAGNOSTIC_PROJECT_STORAGE_KEY);
  const identity = {
    projectId: descriptor.project_id,
    patternId: descriptor.pattern_id,
  };
  expect(success(await hostRequest(page, "host.status", {}), "WebKit status"))
    .toMatchObject({ state: "core-ready" });
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
  await page.locator("#diagnostic-project-load").click();
  await waitForDiagnosticProjectReady(page);
  expect(success(await reopenProject(page, identity, identity.patternId),
    "WebKit reopen").project_revision).toBe(PREPARED_PROJECT_REVISION);
  await activateWithGesture(page);
  await page.locator("#audio-suspend").click();
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  await activateWithGesture(page);
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(true);
  await expect(page.locator("#host-state")).toHaveText("closed");
  console.log("LMDJ_WEBKIT_SMOKE {\"status\":\"pass\",\"scope\":\"capability-protocol-opfs-restart-lifecycle\"}");
});
