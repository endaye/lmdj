import {expect, test} from "@playwright/test";


const FORMAL_HOST_PAGE = "/formal-audio/lmdj-web-runtime.html";


async function waitForFormalHost(page) {
  await page.goto(FORMAL_HOST_PAGE);
  await page.waitForFunction(
    () => window.lmdjWebRuntimeHost?.runtimeInitialized === true,
    undefined,
    {timeout: 5_000},
  );
}


async function activateFromClick(page) {
  await page.evaluate(() => {
    const button = document.createElement("button");
    button.id = "activate-realtime-failure-audio";
    button.addEventListener("click", async () => {
      const context = new AudioContext({sampleRate: 48_000});
      await context.resume();
      const handle = window.lmdjWebRuntimeHost.registerAudioContext(context);
      window.__lmdjRealtimeFailureActivation =
        await window.lmdjWebRuntimeHost.startAudioWorklet(handle);
    }, {once: true});
    document.body.append(button);
  });
  await page.locator("#activate-realtime-failure-audio").click();
  await page.waitForFunction(
    () => window.__lmdjRealtimeFailureActivation !== undefined,
  );
  return page.evaluate(() => window.__lmdjRealtimeFailureActivation);
}


async function installSubmissionHelper(page) {
  await page.evaluate(() => {
    const encoder = new TextEncoder();
    const delay = (milliseconds) =>
      new Promise((resolve) => window.setTimeout(resolve, milliseconds));
    window.__lmdjRealtimeFailureSubmit = async (
      operation,
      payload,
      sidecar,
    ) => {
      const submittedSidecar = sidecar ?? new Uint8Array();
      const requestId = crypto.randomUUID();
      const envelope = encoder.encode(JSON.stringify({
        protocol_version: 1,
        request_id: requestId,
        operation,
        payload,
      }));
      const deadline = performance.now() + 30_000;
      let submitted = -1;
      while (performance.now() < deadline) {
        submitted = window.Module.ccall(
          "lmdj_web_host_submit",
          "number",
          ["array", "number", "array", "number", "number"],
          [
            envelope,
            envelope.byteLength,
            submittedSidecar,
            submittedSidecar.byteLength,
            performance.timeOrigin + deadline,
          ],
        );
        if (submitted === 0) break;
        if (submitted !== -1) {
          throw new Error(`Host submit failed: ${operation}: ${submitted}`);
        }
        await delay(5);
      }
      if (submitted !== 0) {
        throw new Error(`Host submit timed out: ${operation}`);
      }
      while (performance.now() < deadline) {
        const serialized = window.Module.ccall(
          "lmdj_web_audio_test_poll", "string", [], []);
        if (serialized) {
          const message = JSON.parse(serialized);
          if (message.request_id === requestId) return message;
        }
        await delay(2);
      }
      throw new Error(`Host response timed out: ${operation}`);
    };
  });
}


async function uncorrelatableResponseEvidence(page, reuseSettledId) {
  return page.evaluate(async (reuseSettledRequestId) => {
    const transport = window.lmdjWebRuntimeHost.transport;
    const requestId = crypto.randomUUID();
    const failures = [];
    const notifications = [];
    const terminalFailure = new Promise((resolve) => {
      transport.subscribeFailure((error) => {
        failures.push({
          code: error.code,
          message: error.message,
          details: {...error.details},
        });
        resolve(failures.at(-1));
      });
    });
    transport.subscribe((notification) => {
      notifications.push(structuredClone(notification));
    });

    let settled = null;
    if (reuseSettledRequestId) {
      settled = await transport.send({
        protocol_version: 1,
        request_id: requestId,
        operation: "host.status",
        payload: {},
      });
    }
    await window.lmdjWebRuntimeHostTest.submitUntrackedHostStatus(requestId);
    const failure = await Promise.race([
      terminalFailure,
      new Promise((_, reject) => window.setTimeout(
        () => reject(new Error("terminal transport failure timed out")),
        10_000,
      )),
    ]);
    const rejected = await transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "host.status",
      payload: {},
    }).then(
      () => null,
      (error) => ({
        code: error.code,
        message: error.message,
        details: {...error.details},
      }),
    );
    transport.terminate();
    await new Promise((resolve) => window.setTimeout(resolve, 50));
    return {
      failure,
      failures,
      notifications,
      rejected,
      settled,
      terminated: transport.terminated,
      terminalOwnerReleased: transport.terminalOwnerReleased,
    };
  }, reuseSettledId);
}


async function pendingRejectionEvidence(page) {
  return page.evaluate(async () => {
    const transport = window.lmdjWebRuntimeHost.transport;
    const conformance = window.lmdjWebRuntimeHostTest;
    const untrackedRequestId = crypto.randomUUID();
    const pendingRequestId = crypto.randomUUID();
    const failures = [];
    const notifications = [];
    const terminalFailure = new Promise((resolve) => {
      transport.subscribeFailure((error) => {
        const serialized = {
          code: error.code,
          message: error.message,
          details: {...error.details},
        };
        failures.push(serialized);
        resolve(serialized);
      });
    });
    transport.subscribe((notification) => {
      notifications.push(structuredClone(notification));
    });

    await conformance.submitUntrackedHostStatus(untrackedRequestId);
    const pending = transport.send({
      protocol_version: 1,
      request_id: pendingRequestId,
      operation: "host.status",
      payload: {},
    });
    const pendingIdsBefore = conformance.pendingRequestIds();
    const rejected = await Promise.race([
      pending.then(
        () => null,
        (error) => ({
          code: error.code,
          message: error.message,
          details: {...error.details},
        }),
      ),
      new Promise((resolve) => window.setTimeout(
        () => resolve({code: "PENDING_REJECTION_TIMEOUT"}),
        5_000,
      )),
    ]);
    const failure = await Promise.race([
      terminalFailure,
      new Promise((_, reject) => window.setTimeout(
        () => reject(new Error("terminal transport failure timed out")),
        10_000,
      )),
    ]);
    const pendingIdsAfter = conformance.pendingRequestIds();
    const laterRejected = await transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "host.status",
      payload: {},
    }).then(
      () => null,
      (error) => ({
        code: error.code,
        message: error.message,
        details: {...error.details},
      }),
    );
    transport.terminate();
    await new Promise((resolve) => window.setTimeout(resolve, 50));
    return {
      failure,
      failures,
      notifications,
      rejected,
      laterRejected,
      pendingRequestId,
      pendingIdsBefore,
      pendingIdsAfter,
      terminated: transport.terminated,
      terminalOwnerReleased: transport.terminalOwnerReleased,
    };
  });
}


for (const scenario of [
  {name: "unknown response request ID", reuseSettledId: false},
  {
    name: "response request ID whose first request already settled",
    reuseSettledId: true,
  },
]) {
  test(
    `${scenario.name} terminally seals the Browser Main transport`,
    async ({page}) => {
      test.setTimeout(30_000);
      await waitForFormalHost(page);

      const evidence = await uncorrelatableResponseEvidence(
        page,
        scenario.reuseSettledId,
      );
      if (scenario.reuseSettledId) {
        expect(evidence.settled).toMatchObject({ok: true});
      } else {
        expect(evidence.settled).toBeNull();
      }
      expect(evidence).toMatchObject({
        failure: {code: "HOST_PROTOCOL_MISMATCH"},
        failures: [{code: "HOST_PROTOCOL_MISMATCH"}],
        notifications: [],
        rejected: {code: "HOST_PROTOCOL_MISMATCH"},
        terminated: true,
        terminalOwnerReleased: true,
      });
    },
  );
}


test("unknown response rejects and clears another real pending Browser Main request", async ({page}) => {
  test.setTimeout(30_000);
  await waitForFormalHost(page);

  const evidence = await pendingRejectionEvidence(page);
  expect(evidence.pendingIdsBefore).toEqual([evidence.pendingRequestId]);
  expect(evidence.pendingIdsAfter).toEqual([]);
  expect(evidence.failure).toMatchObject({code: "HOST_PROTOCOL_MISMATCH"});
  expect(evidence.rejected).toEqual(evidence.failure);
  expect(evidence.laterRejected).toEqual(evidence.failure);
  expect(evidence.failures).toEqual([evidence.failure]);
  expect(evidence.notifications).toEqual([]);
  expect(evidence.terminated).toBe(true);
  expect(evidence.terminalOwnerReleased).toBe(true);
});


test("processorerror seals an active Sequence and the failed session never resumes", async ({page}) => {
  test.setTimeout(120_000);
  await waitForFormalHost(page);
  expect((await activateFromClick(page)).ok).toBe(true);
  await installSubmissionHelper(page);

  const identity = await page.evaluate(async () => {
    const submit = window.__lmdjRealtimeFailureSubmit;
    const projectId = crypto.randomUUID();
    const patternId = crypto.randomUUID();
    const sessionId = crypto.randomUUID();
    const importToken = crypto.randomUUID();
    const assetId = crypto.randomUUID();
    const frames = 480;
    const wav = new Uint8Array(44 + frames * 2);
    const view = new DataView(wav.buffer);
    const ascii = (offset, value) => {
      for (let index = 0; index < value.length; ++index) {
        wav[offset + index] = value.charCodeAt(index);
      }
    };
    ascii(0, "RIFF");
    view.setUint32(4, 36 + frames * 2, true);
    ascii(8, "WAVE");
    ascii(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, 48_000, true);
    view.setUint32(28, 96_000, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    ascii(36, "data");
    view.setUint32(40, frames * 2, true);
    for (let frame = 0; frame < frames; ++frame) {
      view.setInt16(
        44 + frame * 2,
        Math.round(Math.sin(2 * Math.PI * 440 * frame / 48_000) * 8_000),
        true,
      );
    }
    const wavSha256 = [...new Uint8Array(
      await crypto.subtle.digest("SHA-256", wav),
    )].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    const created = await submit("project.create", {
      project_id: projectId,
      bpm: 120,
      initial_pattern: {pattern_id: patternId, bars: 1, events: []},
    });
    const importBegun = await submit("sample.import.begin", {
      import_token: importToken,
      command_id: crypto.randomUUID(),
      expected_revision: 0,
      slot: {bank: 0, pad: 0},
      asset_id: assetId,
      byte_length: wav.byteLength,
      sequence_session_id: null,
    });
    const importChunked = await submit("sample.import.chunk", {
      import_token: importToken,
      offset: 0,
      final: true,
      sidecar: {
        sidecar_bytes: wav.byteLength,
        sidecar_sha256: wavSha256,
      },
    }, wav);
    const importCommitted = await submit("sample.import.commit", {
      import_token: importToken,
    });
    const snapshot = await submit("snapshot.reload", {pattern_id: patternId});
    const activated = await submit("audio.activate", {});
    const begun = await submit("sequence.record.begin", {
      session_id: sessionId,
      pattern_id: patternId,
      expected_revision: 1,
      armed_capture_slot: null,
    });
    const recorded = await submit("sequence.record.event", {
      session_id: sessionId,
      event: {slot: {bank: 0, pad: 0}, velocity: 100, pressed: true},
    });
    return {
      projectId,
      patternId,
      sessionId,
      created,
      importBegun,
      importChunked,
      importCommitted,
      snapshot,
      activated,
      begun,
      recorded,
    };
  });
  for (const [operation, response] of Object.entries({
    created: identity.created,
    importBegun: identity.importBegun,
    importChunked: identity.importChunked,
    importCommitted: identity.importCommitted,
    snapshot: identity.snapshot,
    activated: identity.activated,
    begun: identity.begun,
    recorded: identity.recorded,
  })) expect(response, operation).toMatchObject({ok: true});

  const fatal = await page.evaluate(async () => {
    window.lmdjWebRuntimeHostTest.dispatchProcessorError();
    return window.lmdjWebRuntimeHostTest.waitForFatal();
  });
  expect(fatal).toMatchObject({
    fatal: "processor_error",
    callbackGate: "closed",
    callbackInFlight: 0,
    controlFailureCommitted: true,
  });

  await waitForFormalHost(page);
  await installSubmissionHelper(page);
  const recovery = await page.evaluate(async ({projectId, patternId}) => {
    const submit = window.__lmdjRealtimeFailureSubmit;
    return {
      opened: await submit("project.open", {
        project_id: projectId,
        pattern_id: patternId,
      }),
      recoverable: await submit("sequence.recovery.list", {}),
    };
  }, identity);
  expect(recovery.opened.ok).toBe(true);
  expect(recovery.recoverable).toMatchObject({ok: true});
  expect(recovery.recoverable.result.candidates).toContainEqual(
    expect.objectContaining({session_id: identity.sessionId}),
  );
});


test("Voice-state overflow terminalizes the real Worklet at production capacity", async ({page}) => {
  test.setTimeout(120_000);
  await waitForFormalHost(page);
  expect((await activateFromClick(page)).ok).toBe(true);
  const initial = await page.evaluate(async () =>
    window.lmdjWebRuntimeHostTest.runSharedEngineProof());
  expect(initial.outcome).toMatchObject({outcome: "voice_started"});

  const result = await page.evaluate(async () => {
    const delay = (milliseconds) =>
      new Promise((resolve) => window.setTimeout(resolve, milliseconds));

    const metric = (name) => window.Module.ccall(
      `lmdj_web_audio_test_voice_state_${name}`, "number", [], []);
    const capacity = metric("capacity");
    const idleDeadline = performance.now() + 3_000;
    while (metric("active_voices") !== 0 && performance.now() < idleDeadline) {
      await delay(2);
    }
    if (metric("active_voices") !== 0) {
      throw new Error("initial proof Voice did not complete");
    }

    let published = metric("published");
    const baseline = published;
    let batch = 0;
    while (published < capacity) {
      const remaining = capacity - published;
      if (remaining % 2 !== 0) {
        throw new Error(`odd Voice-state capacity remainder: ${remaining}`);
      }
      const voices = Math.min(128, remaining / 2);
      const accepted = window.Module.ccall(
        "lmdj_web_audio_test_enqueue_voice_state_batch",
        "number",
        ["number", "number"],
        [batch, voices],
      );
      if (accepted !== voices + 2) {
        throw new Error(`Voice-state batch rejected: ${accepted}`);
      }
      const target = published + voices * 2;
      const batchDeadline = performance.now() + 3_000;
      while (metric("published") !== target &&
             performance.now() < batchDeadline) {
        await delay(2);
      }
      published = metric("published");
      if (published !== target || metric("state") !== 0) {
        throw new Error(
          `Voice-state batch did not settle: ${published}/${target}`,
        );
      }
      ++batch;
    }

    const beforeOverflow = {
      capacity,
      baseline,
      published: metric("published"),
      state: metric("state"),
      drops: metric("drops"),
      outcomeDrops: metric("outcome_drops"),
    };
    const overflowAccepted = window.Module.ccall(
      "lmdj_web_audio_test_enqueue_voice_state_batch",
      "number",
      ["number", "number"],
      [batch, 1],
    );
    const overflowDeadline = performance.now() + 3_000;
    while ((metric("state") !== 1 ||
            window.Module._lmdj_web_audio_fatal() !== 11 ||
            metric("process_return") !== 0 ||
            window.Module._lmdj_web_audio_test_gate_closed() !== 1 ||
            window.Module._lmdj_web_audio_test_in_flight() !== 0) &&
           performance.now() < overflowDeadline) {
      await delay(2);
    }
    const afterOverflow = {
      published: metric("published"),
      state: metric("state"),
      drops: metric("drops"),
      outcomeDrops: metric("outcome_drops"),
      processReturn: metric("process_return"),
      fatal: window.Module._lmdj_web_audio_fatal(),
      gateClosed:
        window.Module._lmdj_web_audio_test_gate_closed() === 1,
      callbackInFlight:
        window.Module._lmdj_web_audio_test_in_flight() === 1,
      renderCallsAtFatal:
        window.Module._lmdj_web_audio_test_render_calls(),
    };
    await delay(20);
    afterOverflow.renderCallsAfterFatal =
      window.Module._lmdj_web_audio_test_render_calls();
    return {
      beforeOverflow,
      overflowAccepted,
      afterOverflow,
    };
  });

  expect(result.beforeOverflow.baseline).toBe(2);
  expect(result.beforeOverflow.published).toBe(
    result.beforeOverflow.capacity,
  );
  expect(result.beforeOverflow).toMatchObject({
    state: 0,
    drops: 0,
    outcomeDrops: 0,
  });
  expect(result.overflowAccepted).toBe(3);
  expect(result.afterOverflow).toMatchObject({
    state: 1,
    drops: 1,
    outcomeDrops: 0,
    processReturn: 0,
    fatal: 11,
    gateClosed: true,
    callbackInFlight: false,
    renderCallsAtFatal: expect.any(Number),
    renderCallsAfterFatal: expect.any(Number),
  });
  expect(result.afterOverflow.published).toBeGreaterThanOrEqual(
    result.beforeOverflow.capacity,
  );
  expect(result.afterOverflow.published).toBeLessThanOrEqual(
    result.beforeOverflow.capacity + 1,
  );
  expect(result.afterOverflow.renderCallsAfterFatal).toBe(
    result.afterOverflow.renderCallsAtFatal,
  );

  // Later Host layers own automatic propagation. This existing conformance
  // seam is used only to commit bounded Control teardown after the real audio
  // fatal above has already been proven.
  const cleanup = await page.evaluate(async () => {
    window.lmdjWebRuntimeHostTest.dispatchProcessorError();
    return window.lmdjWebRuntimeHostTest.waitForFatal();
  });
  expect(cleanup).toMatchObject({
    fatal: "processor_error",
    callbackGate: "closed",
    callbackInFlight: 0,
    controlFailureCommitted: true,
  });
  expect(cleanup.renderCallsAfterFatal).toBe(cleanup.renderCallsAtFatal);
});
