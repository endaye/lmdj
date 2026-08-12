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
    window.__lmdjRealtimeFailureSubmit = async (operation, payload) => {
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
            new Uint8Array(),
            0,
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


test("processorerror seals an active Take and the failed session never resumes", async ({page}) => {
  test.setTimeout(120_000);
  await waitForFormalHost(page);
  expect((await activateFromClick(page)).ok).toBe(true);
  await installSubmissionHelper(page);

  const identity = await page.evaluate(async () => {
    const submit = window.__lmdjRealtimeFailureSubmit;
    const projectId = crypto.randomUUID();
    const patternId = crypto.randomUUID();
    const takeId = crypto.randomUUID();
    const created = await submit("project.create", {
      project_id: projectId,
      bpm: 120,
      initial_pattern: {pattern_id: patternId, bars: 1, events: []},
    });
    const snapshot = await submit("snapshot.reload", {pattern_id: patternId});
    const activated = await submit("audio.activate", {});
    const begun = await submit("take.begin", {
      take_id: takeId,
      expected_revision: 0,
    });
    return {projectId, patternId, takeId, created, snapshot, activated, begun};
  });
  for (const response of [
    identity.created,
    identity.snapshot,
    identity.activated,
    identity.begun,
  ]) expect(response.ok).toBe(true);

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
      recoverable: await submit("take.recoverable.list", {}),
    };
  }, identity);
  expect(recovery.opened.ok).toBe(true);
  expect(recovery.recoverable).toMatchObject({ok: true});
  expect(recovery.recoverable.result.candidates).toContainEqual(
    expect.objectContaining({take_id: identity.takeId}),
  );
});
