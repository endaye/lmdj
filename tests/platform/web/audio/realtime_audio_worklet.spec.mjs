import {expect, test} from "@playwright/test";
import {test as opfsTest} from "../project_io/opfs_browser.fixture.mjs";


const FORMAL_HOST_PAGE = "/formal-audio/lmdj-web-runtime.html";


async function waitForFormalHost(page) {
  await page.goto(FORMAL_HOST_PAGE);
  await page.waitForFunction(
    () => window.lmdjWebRuntimeHost?.runtimeInitialized === true,
    undefined,
    {timeout: 5_000},
  );
  return page.evaluate(() => ({
    registrationHelpers: Object.keys(window.lmdjWebRuntimeHost)
      .filter((name) => [
        "registerAudioContext",
        "registerAudioNode",
        "connectAudioWorkletDirect",
      ].includes(name)).sort(),
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
        const tapNode = context.createGain();
        tapNode.gain.value = 1;
        const analyser = context.createAnalyser();
        tapNode.connect(analyser);
        analyser.connect(context.destination);
        const tapHandle = window.lmdjWebRuntimeHost.registerAudioNode(tapNode);
        window.__lmdjFormalAudioGraph = {context, tapNode, analyser, handle};
        window.__lmdjFormalActivation = await window.lmdjWebRuntimeHost
          .startAudioWorklet(handle, tapHandle);
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


opfsTest("live press and release complete while an executor owns a paused OPFS write", async ({page}) => {
  opfsTest.setTimeout(120_000);
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000)).ok).toBe(true);
  const command = (action) => page.evaluate((value) =>
    window.Module._lmdj_web_audio_test_transport_probe(value), action);
  const until = async (expected) => {
    await expect.poll(async () => {
      expect(await command(2)).toBeGreaterThanOrEqual(0);
      const state = await command(0);
      expect(state, "OPFS probe failed").not.toBe(9);
      return state;
    }, {timeout: 30_000}).toBe(expected);
  };
  try {
    expect(await command(1)).toBe(1);
    await expect.poll(async () => {
      await command(2);
      expect(await command(0), "OPFS prepare failed").not.toBe(9);
      return command(5);
    }, {timeout: 30_000}).toBe(1);
    expect(await command(0)).toBe(1);

    // This is the existing real Bank/press/voice outcome journey, on the same
    // control lane which would be blocked by an inline storage operation.
    const proof = await page.evaluate(() =>
      window.lmdjWebRuntimeHostTest.runSharedEngineProof());
    expect(proof.outcome).toMatchObject({
      sequence: proof.admittedSequence, outcome: "voice_started",
    });
    expect(proof.outputEnergy).toBeGreaterThan(0);
    const released = await page.evaluate(() =>
      window.lmdjWebRuntimeHost.transport.send({
        protocol_version: 1, request_id: crypto.randomUUID(),
        operation: "trigger", payload: {slot: 0, kind: "release"},
      }));
    expect(released).toMatchObject({ok: true, result: {accepted: true}});
    expect(await command(0)).toBe(1); // IO still held, no early completion.
    await expect.poll(() => command(4)).toBe(1);
    const status = await page.evaluate(() =>
      window.lmdjWebRuntimeHost.transport.send({
        protocol_version: 1, request_id: crypto.randomUUID(),
        operation: "host.status", payload: {},
      }));
    expect(status.ok).toBe(true); // Shutdown request did not join inline.
    expect(await command(0)).toBe(1);
    expect(await command(6)).toBe(1);
    await until(4); // Exact bytes read, completion consumed once, owner stopped.
    await expect.poll(() => command(3)).toBe(1);
    await until(6); // New worker reacquires lease and reads the same exact bytes.
    expect(await page.evaluate(async () => {
      const root = await navigator.storage.getDirectory();
      const directory = await root.getDirectoryHandle("transport-executor-proof");
      return (await (await directory.getFileHandle("receipt")).getFile()).text();
    })).toBe("retained OPFS transport completion");
  } finally {
    await command(6); // Never leave the intentional latch held on assertion failure.
  }
});

test("compatibility press renders the published Bank through the Wasm AudioWorklet", async ({page}) => {
  test.setTimeout(120_000);
  const module = await waitForFormalHost(page);
  expect(module.registrationHelpers).toEqual([
    "connectAudioWorkletDirect",
    "registerAudioContext",
    "registerAudioNode",
  ]);
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
  const graph = await page.evaluate(() => {
    const {analyser, context, tapNode, handle} = window.__lmdjFormalAudioGraph;
    const values = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(values);
    const tapEnergy = values.reduce((sum, value) => sum + value * value, 0);
    const connectionsBefore = window.lmdjWebRuntimeHostTest
      .directOutputConnections();
    tapNode.disconnect();
    const direct = window.lmdjWebRuntimeHost.connectAudioWorkletDirect(handle);
    const connectionsAfterDirect = window.lmdjWebRuntimeHostTest
      .directOutputConnections();
    const repeated = window.lmdjWebRuntimeHost.connectAudioWorkletDirect(handle);
    return {
      tapEnergy, direct, repeated,
      connectionsBefore,
      connectionsAfterDirect,
      connectionsAfterRepeated: window.lmdjWebRuntimeHostTest
        .directOutputConnections(),
      contextState: context.state,
    };
  });
  expect(graph.tapEnergy).toBeGreaterThan(0);
  expect(graph.direct).toBe(true);
  expect(graph.repeated).toBe(true);
  expect(graph.connectionsBefore).toBe(0);
  expect(graph.connectionsAfterDirect).toBe(1);
  expect(graph.connectionsAfterRepeated).toBe(1);
  expect(graph.contextState).toBe("running");
  const continuation = await page.evaluate(() =>
    window.lmdjWebRuntimeHostTest.runDirectOutputContinuationProof());
  expect(continuation.renderCallsAfter).toBeGreaterThan(
    continuation.renderCallsBefore,
  );
  expect(continuation.outputEnergy).toBeGreaterThan(0);
  expect(proof.memory.bufferShared).toBe(true);
  expect(proof.memory.allowGrowth).toBe(false);
  expect(proof.memory.initialBytes).toBe(536_870_912);
  expect(proof.callback).toEqual({
    inputs: 0,
    outputs: 1,
    channels: 2,
    frames: 128,
  });
  expect(
    proof.deadlines.renderDeadline - proof.deadlines.renderStartedAt,
  ).toBeCloseTo(30_000, 6);
  expect(
    proof.deadlines.outcomeDeadline - proof.deadlines.outcomeStartedAt,
  ).toBeCloseTo(30_000, 6);
  expect(proof.deadlines.outcomeStartedAt).toBeGreaterThanOrEqual(
    proof.deadlines.renderStartedAt,
  );
  expect(proof.deadlines.outcomeDeadline).toBeGreaterThanOrEqual(
    proof.deadlines.renderDeadline,
  );
});


test("outcome drain receives a fresh budget after the render budget expires", async ({page}) => {
  test.setTimeout(120_000);
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000)).ok).toBe(true);

  const proof = await page.evaluate(async () =>
    window.lmdjWebRuntimeHostTest.runFreshOutcomeDeadlineProof());
  expect(proof.renderDeadline).toBeLessThan(proof.outcomeStartedAt);
  expect(proof.outcomeReadyAt).toBeGreaterThan(proof.renderDeadline);
  expect(proof.outcomeReadyAt).toBeLessThan(proof.outcomeDeadline);
  expect(proof.outcome).toEqual({
    count: 1,
    sequence: proof.expectedSequence,
    outcome: "voice_started",
    runtime_frame: expect.any(Number),
  });
});


test("an outcome mirrored during a diagnostic request is delivered exactly once", async ({page}) => {
  test.setTimeout(120_000);
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000)).ok).toBe(true);

  const proof = await page.evaluate(async () =>
    window.lmdjWebRuntimeHostTest.runOutcomeMirrorRaceProof());
  expect(proof.writerTimedOut).toBe(false);
  expect(proof.first).toEqual({
    count: 1,
    sequence: proof.expectedSequence,
    outcome: "voice_started",
    runtime_frame: expect.any(Number),
  });
  expect(proof.first.runtime_frame).toBeGreaterThanOrEqual(0);
  expect(proof.second).toEqual({state: 2, count: 0});
});


test("an unreleased proof writer times out without occupying Control", async ({page}) => {
  test.setTimeout(120_000);
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000)).ok).toBe(true);

  const proof = await page.evaluate(async () =>
    window.lmdjWebRuntimeHostTest.runOutcomeMirrorWriterTimeoutProof());
  expect(proof.writerTimedOut).toBe(true);
  expect(proof.writerElapsedMs).toBeGreaterThanOrEqual(4_500);
  expect(proof.writerElapsedMs).toBeLessThan(7_000);
  expect(proof.mirrorState).toBe(0);
  expect(proof.first).toEqual({state: 2, count: 0});
  expect(proof.followup).toEqual({state: 2, count: 0});
  expect(proof.followupElapsedMs).toBeLessThan(1_000);
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
    controlFailureCommitted: true,
  });
  expect(result.renderCallsAfterFatal).toBe(result.renderCallsAtFatal);
});


test("a stalled callback returns a typed quiescence failure within two caller budgets", async ({page}) => {
  await waitForFormalHost(page);
  const timeoutMs = 25;
  const result = await page.evaluate((timeout) =>
    window.lmdjWebRuntimeHostTest.runQuiescenceTimeoutProof(timeout),
  timeoutMs);
  expect(result).toMatchObject({
    completed: true,
    has_value: false,
    error: {
      code: "INTERNAL_ERROR",
      message:
        "Wasm AudioWorklet quiescence timed out with callback still in flight",
    },
    fatal: "quiescence_timeout",
    gate: "terminal",
    callback_in_flight: 1,
  });
  expect(result.elapsed_ms).toBeGreaterThanOrEqual(timeoutMs);
  expect(result.elapsed_ms).toBeLessThan(timeoutMs * 2 + 250);
  expect(result.observed_wall_ms).toBeLessThan(500);
});


test("start is exactly-once and suspend can reactivate the same processor", async ({page}) => {
  await waitForFormalHost(page);
  const start = await page.evaluate(async () => {
    const context = new AudioContext({sampleRate: 48_000});
    await context.resume();
    const handle = window.lmdjWebRuntimeHost.registerAudioContext(context);
    const destination = context.createGain();
    destination.connect(context.destination);
    const destinationHandle = window.lmdjWebRuntimeHost
      .registerAudioNode(destination);
    const first = window.lmdjWebRuntimeHost.startAudioWorklet(
      handle, destinationHandle);
    const second = window.lmdjWebRuntimeHost.startAudioWorklet(
      handle, destinationHandle);
    const otherContext = new AudioContext({sampleRate: 48_000});
    const otherHandle = window.lmdjWebRuntimeHost
      .registerAudioContext(otherContext);
    const differentHandleRejected = await window.lmdjWebRuntimeHost
      .startAudioWorklet(otherHandle, destinationHandle)
      .then(() => false, () => true);
    const invalidDestinationRejected = await window.lmdjWebRuntimeHost
      .startAudioWorklet(handle, 999_999)
      .then(() => false, () => true);
    return {
      samePromise: first === second,
      activation: await first,
      differentHandleRejected,
      invalidDestinationRejected,
      startCalls: window.lmdjWebRuntimeHostTest.startCalls(),
    };
  });
  expect(start.samePromise).toBe(true);
  expect(start.activation.ok).toBe(true);
  expect(start.differentHandleRejected).toBe(true);
  expect(start.invalidDestinationRejected).toBe(true);
  expect(start.startCalls).toBe(1);

  const proof = await page.evaluate(async () =>
    window.lmdjWebRuntimeHostTest.runSuspendReactivateProof());
  expect(proof.firstAcknowledgement).toBeGreaterThan(0);
  expect(proof.latestGeneration).toBeGreaterThan(proof.firstAcknowledgement);
  expect(proof.liveAcknowledgement).toBe(proof.latestGeneration);
  expect(proof.suspended).toMatchObject({
    ok: true,
    result: {state: "audio-suspended", changed: true},
  });
  expect(proof.paused).toEqual({gate: "paused", callbackInFlight: 0});
  expect(proof.heartbeatAfterResume).not.toBe(proof.heartbeatBeforeResume);
  expect(proof.secondAcknowledgement).toBe(proof.latestGeneration);
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
