import {expect, test} from "@playwright/test";


const FORMAL_HOST_PAGE = "/formal-audio/lmdj-web-runtime-host.html";


async function waitForFormalHost(page) {
  await page.goto(FORMAL_HOST_PAGE);
  await page.waitForFunction(
    () => window.lmdjWebRuntimeHost?.runtimeInitialized === true,
    undefined,
    {timeout: 5_000},
  );
  return page.evaluate(() => ({
    registrationHelpers: Object.keys(window.lmdjWebRuntimeHost)
      .filter((name) => name === "registerAudioContext"),
    sharedMemory:
      window.Module.wasmMemory?.buffer instanceof SharedArrayBuffer,
    memoryBytes: window.Module.wasmMemory?.buffer.byteLength ?? 0,
  }));
}


async function activateFromClick(page, sampleRate) {
  await page.evaluate((requestedSampleRate) => {
    const button = document.createElement("button");
    button.id = "activate-formal-audio";
    button.addEventListener("click", async () => {
      try {
        const context = new AudioContext({sampleRate: requestedSampleRate});
        await context.resume();
        const handle = window.lmdjWebRuntimeHost.registerAudioContext(context);
        window.__lmdjFormalActivation = await window.lmdjWebRuntimeHost
          .startAudioWorklet(handle);
      } catch (error) {
        window.__lmdjFormalActivation = {
          ok: false,
          error: String(error),
        };
      }
    }, {once: true});
    document.body.append(button);
  }, sampleRate);
  await page.locator("#activate-formal-audio").click();
  await page.waitForFunction(() => window.__lmdjFormalActivation !== undefined);
  return page.evaluate(() => window.__lmdjFormalActivation);
}


test("shared RealtimeEngine renders a current Bank in the Wasm AudioWorklet", async ({page}) => {
  test.setTimeout(120_000);
  const module = await waitForFormalHost(page);
  expect(module.registrationHelpers).toEqual(["registerAudioContext"]);
  expect(module.sharedMemory).toBe(true);
  expect(module.memoryBytes).toBe(536_870_912);

  const activation = await activateFromClick(page, 48_000);
  expect(activation).toMatchObject({
    ok: true,
    sampleRate: 48_000,
    inputs: 0,
    outputs: 1,
    channels: 2,
    frames: 128,
  });

  await page.waitForTimeout(100);
  expect(await page.evaluate(() =>
    window.lmdjWebRuntimeHostTest.preactivationState())).toEqual({
    gate: "paused",
    callbackInFlight: 0,
    renderCalls: 0,
    acknowledgedGeneration: 0,
  });

  const proof = await page.evaluate(async () =>
    window.lmdjWebRuntimeHostTest.runSharedEngineProof());
  expect(proof.controlGeneration).toBeGreaterThan(0);
  expect(proof.acknowledgedGeneration).toBe(proof.controlGeneration);
  expect(proof.outcome).toEqual({
    sequence: proof.admittedSequence,
    outcome: "voice_started",
    runtime_frame: expect.any(Number),
  });
  expect(proof.outcome.runtime_frame).toBeGreaterThanOrEqual(0);
  expect(proof.outputEnergy).toBeGreaterThan(0);
  expect(proof.memory.bufferShared).toBe(true);
  expect(proof.memory.allowGrowth).toBe(false);
  expect(proof.memory.initialBytes).toBe(536_870_912);
  expect(proof.callback).toEqual({
    inputs: 0,
    outputs: 1,
    channels: 2,
    frames: 128,
  });
});


test("realized 44.1 kHz is rejected before Engine activation", async ({page}) => {
  await waitForFormalHost(page);
  const activation = await activateFromClick(page, 44_100);
  expect(activation).toEqual({
    ok: false,
    error: {
      code: "UNSUPPORTED_WEB_RUNTIME",
      message: "realized Web Audio configuration is unsupported",
      details: {
        expected_sample_rate: 48_000,
        observed_sample_rate: 44_100,
        expected_render_quantum: 128,
        observed_render_quantum: 128,
      },
    },
  });
  expect(await page.evaluate(() =>
    window.lmdjWebRuntimeHostTest.engineRenderCalls())).toBe(0);
  expect(await page.evaluate(() =>
    window.lmdjWebRuntimeHostTest.hostStatus())).toMatchObject({
    ok: false,
    error: {code: "HOST_STATE_INVALID"},
  });
});


test("the conformance quantum validator seals the real Control runtime", async ({page}) => {
  await waitForFormalHost(page);
  const result = await page.evaluate(async () =>
    window.lmdjWebRuntimeHostTest.validateUnsupportedConfiguration({
      sampleRate: 48_000,
      renderQuantum: 256,
    }));
  expect(result.activation).toEqual({
    ok: false,
    error: {
      code: "UNSUPPORTED_WEB_RUNTIME",
      message: "realized Web Audio configuration is unsupported",
      details: {
        expected_sample_rate: 48_000,
        observed_sample_rate: 48_000,
        expected_render_quantum: 128,
        observed_render_quantum: 256,
      },
    },
  });
  expect(result.hostStatus).toMatchObject({
    ok: false,
    error: {code: "HOST_STATE_INVALID"},
  });
});


for (const frames of [127, 256]) {
  test(`a ${frames}-frame callback atomically latches fatal and returns false`, async ({page}) => {
    await waitForFormalHost(page);
    const result = await page.evaluate((callbackFrames) =>
      window.lmdjWebRuntimeHostTest.invokeAdapterShape({
        inputs: 0,
        outputs: 1,
        channels: 2,
        frames: callbackFrames,
      }), frames);
    expect(result).toEqual({
      returned: false,
      fatal: "invalid_callback_shape",
      gate: "terminal",
      expectedFrames: 128,
      observedFrames: frames,
      engineRenderCalls: 0,
    });
  });
}


test("processorerror closes the callback gate and seals the Host", async ({page}) => {
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000)).ok).toBe(true);
  const result = await page.evaluate(async () => {
    window.lmdjWebRuntimeHostTest.dispatchProcessorError();
    return window.lmdjWebRuntimeHostTest.waitForFatal();
  });
  expect(result).toMatchObject({
    fatal: "processor_error",
    callbackGate: "closed",
    callbackInFlight: 0,
    hostStatus: {
      ok: false,
      error: {code: "HOST_STATE_INVALID"},
    },
  });
  expect(result.renderCallsAfterFatal).toBe(result.renderCallsAtFatal);
});


test("start is exactly-once and suspend can reactivate the same processor", async ({page}) => {
  await waitForFormalHost(page);
  const start = await page.evaluate(async () => {
    const context = new AudioContext({sampleRate: 48_000});
    await context.resume();
    const handle = window.lmdjWebRuntimeHost.registerAudioContext(context);
    const first = window.lmdjWebRuntimeHost.startAudioWorklet(handle);
    const second = window.lmdjWebRuntimeHost.startAudioWorklet(handle);
    const otherContext = new AudioContext({sampleRate: 48_000});
    const otherHandle = window.lmdjWebRuntimeHost
      .registerAudioContext(otherContext);
    const differentHandleRejected = await window.lmdjWebRuntimeHost
      .startAudioWorklet(otherHandle)
      .then(() => false, () => true);
    return {
      samePromise: first === second,
      activation: await first,
      differentHandleRejected,
      startCalls: window.lmdjWebRuntimeHostTest.startCalls(),
    };
  });
  expect(start.samePromise).toBe(true);
  expect(start.activation.ok).toBe(true);
  expect(start.differentHandleRejected).toBe(true);
  expect(start.startCalls).toBe(1);

  const proof = await page.evaluate(async () =>
    window.lmdjWebRuntimeHostTest.runSuspendReactivateProof());
  expect(proof.firstAcknowledgement).toBeGreaterThan(0);
  expect(proof.suspended).toMatchObject({
    ok: true,
    result: {state: "audio-suspended", changed: true},
  });
  expect(proof.paused).toEqual({gate: "paused", callbackInFlight: 0});
  expect(proof.secondAcknowledgement).toBe(proof.firstAcknowledgement);
  expect(proof.secondActivation).toMatchObject({
    ok: true,
    result: {state: "running", changed: true},
  });
});


for (const fatal of [
  "worklet_thread_start_failed",
  "processor_create_failed",
  "node_create_failed",
  "coordinator_install_failed",
  "bootstrap_timeout",
]) {
  test(`${fatal} commits Control failure before the start Promise returns`, async ({page}) => {
    await waitForFormalHost(page);
    const result = await page.evaluate(async (selectedFatal) =>
      window.lmdjWebRuntimeHostTest.runBootstrapFailureProof(selectedFatal),
    fatal);
    expect(result.activation).toEqual({ok: false, fatal});
    expect(result.controlFailureCommitted).toBe(1);
    for (const response of [
      result.hostStatus,
      result.snapshotReload,
      result.trigger,
    ]) {
      expect(response).toMatchObject({
        ok: false,
        error: {code: "HOST_STATE_INVALID"},
      });
    }
  });
}


test("a stale Bank generation never masquerades as the current acknowledgement", async ({page}) => {
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000)).ok).toBe(true);
  const result = await page.evaluate(async () =>
    window.lmdjWebRuntimeHostTest.runGenerationMismatchProof());
  expect(result.expectedGeneration).not.toBe(result.acknowledgedGeneration);
  expect(result).toMatchObject({
    accepted: false,
    reason: "generation_mismatch",
  });
});
