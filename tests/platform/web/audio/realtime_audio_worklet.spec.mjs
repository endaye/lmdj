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

test("global Pattern transport records live input through real OPFS and settles off the dispatch tail", async ({page}) => {
  test.setTimeout(120_000);
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000)).ok).toBe(true);

  const sendTransport = (operation, payload) =>
    page.evaluate(({operation, payload}) =>
      window.lmdjWebRuntimeHost.transport.send({
        protocol_version: 1,
        request_id: crypto.randomUUID(),
        operation,
        payload,
      }), {operation, payload});
  const inspectTransport = (sessionId) =>
    sendTransport("pattern.transport.inspect", {session_id: sessionId});

  const journey = await page.evaluate(async () => {
    const send = (operation, payload, sidecar) =>
      window.lmdjWebRuntimeHost.transport.send(
        {
          protocol_version: 1,
          request_id: crypto.randomUUID(),
          operation,
          payload,
        },
        sidecar === undefined ? {} : {sidecar},
      );
    const projectId = crypto.randomUUID();
    const patternId = crypto.randomUUID();
    const sessionId = crypto.randomUUID();
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
    const importToken = crypto.randomUUID();
    const assetId = crypto.randomUUID();
    const created = await send("project.create", {
      project_id: projectId,
      bpm: 120,
      initial_pattern: {pattern_id: patternId, bars: 1, events: []},
      pattern_transport: true,
    });
    const importBegun = await send("sample.import.begin", {
      import_token: importToken,
      command_id: crypto.randomUUID(),
      expected_revision: 0,
      slot: {bank: 0, pad: 0},
      asset_id: assetId,
      byte_length: wav.byteLength,
    });
    const importChunked = await send("sample.import.chunk", {
      import_token: importToken,
      offset: 0,
      final: true,
      sidecar: {sidecar_bytes: wav.byteLength, sidecar_sha256: wavSha256},
    }, wav);
    const importCommitted = await send("sample.import.commit", {
      import_token: importToken,
    });
    const snapshot = await send("snapshot.reload", {pattern_id: patternId});
    const activated = await send("audio.activate", {});
    // The pending ticket returns through the ordinary serializer while the
    // audio receipt is still outstanding.
    const ticket = await send("pattern.transport.request", {
      session_id: sessionId,
      project_id: projectId,
      command_id: crypto.randomUUID(),
      expected_epoch: 1,
      intent: "record",
      expected_revision: null,
    });
    return {
      projectId, patternId, sessionId,
      created, importBegun, importChunked, importCommitted, snapshot,
      activated, ticket,
    };
  });
  expect(journey.created).toMatchObject({ok: true});
  expect(journey.importBegun).toMatchObject({ok: true});
  expect(journey.importChunked).toMatchObject({ok: true});
  expect(journey.importCommitted).toMatchObject({ok: true});
  expect(journey.snapshot).toMatchObject({ok: true});
  expect(journey.activated).toMatchObject({ok: true});
  // Completion ordering: the ticket's status snapshot precedes any
  // continuation step, so it always reports the pending phase.
  expect(journey.ticket).toMatchObject({
    ok: true,
    result: {submit: "accepted", status: {phase: "awaiting_audio"}},
  });

  await expect.poll(async () => {
    const status = await inspectTransport(journey.sessionId);
    return status.ok && status.result.recording === true &&
      status.result.phase === "idle";
  }, {timeout: 30_000}).toBe(true);

  // Live input is admitted post-enqueue and journaled durably before its
  // response returns.
  expect(await sendTransport("trigger", {slot: 0, velocity: 100}))
    .toMatchObject({ok: true, result: {status: "enqueued"}});
  expect(await sendTransport("trigger", {slot: 0, kind: "release"}))
    .toMatchObject({ok: true, result: {accepted: true}});

  expect((await sendTransport("pattern.transport.request", {
    session_id: journey.sessionId,
    project_id: journey.projectId,
    command_id: crypto.randomUUID(),
    expected_epoch: 2,
    intent: "record",
    expected_revision: null,
  }))).toMatchObject({ok: true, result: {submit: "accepted"}});
  // Storage settlement and the committed-Pattern publication are separate
  // completions; the cadence drives both without a dispatch tail.
  await expect.poll(async () => {
    const status = await inspectTransport(journey.sessionId);
    return status.ok && status.result.recording === false &&
      status.result.phase === "idle" &&
      status.result.publication_pending === false;
  }, {timeout: 30_000}).toBe(true);

  const truth = await sendTransport("project.inspect", {});
  expect(truth.ok).toBe(true);
  const events = truth.result.project.patterns[journey.patternId].events;
  expect(events).toHaveLength(1);
  expect(events[0]).toMatchObject({slot: {bank: 0, pad: 0}, velocity: 100});

  // A live Pad survives Record-off and Pattern Stop.
  expect(await sendTransport("trigger", {slot: 0, velocity: 100}))
    .toMatchObject({ok: true, result: {status: "enqueued"}});
  expect(await sendTransport("trigger", {slot: 0, kind: "release"}))
    .toMatchObject({ok: true, result: {accepted: true}});
  expect((await sendTransport("pattern.transport.request", {
    session_id: journey.sessionId,
    project_id: journey.projectId,
    command_id: crypto.randomUUID(),
    expected_epoch: 3,
    intent: "play_stop",
    expected_revision: null,
  }))).toMatchObject({ok: true, result: {submit: "accepted"}});
  await expect.poll(async () => {
    const status = await inspectTransport(journey.sessionId);
    return status.ok && status.result.playing === false &&
      status.result.phase === "idle";
  }, {timeout: 30_000}).toBe(true);
  expect(await sendTransport("trigger", {slot: 0, velocity: 100}))
    .toMatchObject({ok: true, result: {status: "enqueued"}});
  expect(await sendTransport("trigger", {slot: 0, kind: "release"}))
    .toMatchObject({ok: true, result: {accepted: true}});
});

test("a Sample commit during Pattern transport recording is honestly rejected and the journal survives", async ({page}) => {
  test.setTimeout(120_000);
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000)).ok).toBe(true);

  const sendTransport = (operation, payload, sidecar) =>
    page.evaluate(({operation, payload, hasSidecar}) =>
      window.lmdjWebRuntimeHost.transport.send(
        {
          protocol_version: 1,
          request_id: crypto.randomUUID(),
          operation,
          payload,
        },
        hasSidecar ? {sidecar: window.__lmdjTransportCaptureWav} : {},
      ), {operation, payload, hasSidecar: sidecar === true});
  const inspectTransport = (sessionId) =>
    sendTransport("pattern.transport.inspect", {session_id: sessionId});

  const setup = await page.evaluate(async () => {
    const send = (operation, payload, sidecar) =>
      window.lmdjWebRuntimeHost.transport.send(
        {
          protocol_version: 1,
          request_id: crypto.randomUUID(),
          operation,
          payload,
        },
        sidecar === undefined ? {} : {sidecar},
      );
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
      view.setInt16(44 + frame * 2, 2_000, true);
    }
    window.__lmdjTransportCaptureWav = wav;
    const wavSha256 = [...new Uint8Array(
      await crypto.subtle.digest("SHA-256", wav),
    )].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    const projectId = crypto.randomUUID();
    const patternId = crypto.randomUUID();
    const sessionId = crypto.randomUUID();
    const created = await send("project.create", {
      project_id: projectId,
      bpm: 120,
      initial_pattern: {pattern_id: patternId, bars: 1, events: []},
      pattern_transport: true,
    });
    const importToken = crypto.randomUUID();
    const assetId = crypto.randomUUID();
    const imported = await send("sample.import.begin", {
      import_token: importToken,
      command_id: crypto.randomUUID(),
      expected_revision: 0,
      slot: {bank: 0, pad: 0},
      asset_id: assetId,
      byte_length: wav.byteLength,
    });
    const chunked = await send("sample.import.chunk", {
      import_token: importToken,
      offset: 0,
      final: true,
      sidecar: {sidecar_bytes: wav.byteLength, sidecar_sha256: wavSha256},
    }, wav);
    const committed = await send("sample.import.commit", {
      import_token: importToken,
    });
    const snapshot = await send("snapshot.reload", {pattern_id: patternId});
    const activated = await send("audio.activate", {});
    const ticket = await send("pattern.transport.request", {
      session_id: sessionId,
      project_id: projectId,
      command_id: crypto.randomUUID(),
      expected_epoch: 1,
      intent: "record",
      expected_revision: null,
    });
    return {
      projectId, patternId, sessionId, wavSha256,
      created, imported, chunked, committed, snapshot, activated, ticket,
    };
  });
  expect(setup.created.ok).toBe(true);
  expect(setup.imported.ok).toBe(true);
  expect(setup.chunked.ok).toBe(true);
  expect(setup.committed.ok).toBe(true);
  expect(setup.snapshot.ok).toBe(true);
  expect(setup.activated.ok).toBe(true);
  expect(setup.ticket).toMatchObject({ok: true, result: {submit: "accepted"}});
  await expect.poll(async () => {
    const status = await inspectTransport(setup.sessionId);
    return status.ok && status.result.recording === true &&
      status.result.phase === "idle";
  }, {timeout: 30_000}).toBe(true);
  expect(await sendTransport("trigger", {slot: 0, velocity: 100}))
    .toMatchObject({ok: true, result: {status: "enqueued"}});
  expect(await sendTransport("trigger", {slot: 0, kind: "release"}))
    .toMatchObject({ok: true, result: {accepted: true}});

  // The capture-style commit keeps its legacy busy guard while the transport
  // journal is open: honestly rejected, never a silent journal seal.
  const capture = await page.evaluate(async (setup) => {
    const send = (operation, payload, sidecar) =>
      window.lmdjWebRuntimeHost.transport.send(
        {
          protocol_version: 1,
          request_id: crypto.randomUUID(),
          operation,
          payload,
        },
        sidecar === undefined ? {} : {sidecar},
      );
    const wav = window.__lmdjTransportCaptureWav;
    const importToken = crypto.randomUUID();
    const truth = await send("project.inspect", {});
    const begun = await send("sample.import.begin", {
      import_token: importToken,
      command_id: crypto.randomUUID(),
      expected_revision: truth.result.project_revision,
      slot: {bank: 0, pad: 1},
      asset_id: crypto.randomUUID(),
      byte_length: wav.byteLength,
    });
    const chunked = await send("sample.import.chunk", {
      import_token: importToken,
      offset: 0,
      final: true,
      sidecar: {sidecar_bytes: wav.byteLength, sidecar_sha256: setup.wavSha256},
    }, wav);
    const rejected = await send("sample.import.commit", {
      import_token: importToken,
    });
    const pressAfter = await send("trigger", {slot: 0, velocity: 100});
    const releaseAfter = await send("trigger", {slot: 0, kind: "release"});
    return {begun, chunked, rejected, pressAfter, releaseAfter};
  }, setup);
  expect(capture.begun.ok).toBe(true);
  expect(capture.chunked.ok).toBe(true);
  expect(capture.rejected).toMatchObject({
    ok: false,
    error: {code: "INVALID_ARGUMENT"},
  });
  expect(capture.pressAfter).toMatchObject({
    ok: true, result: {status: "enqueued"},
  });
  expect(capture.releaseAfter).toMatchObject({
    ok: true, result: {accepted: true},
  });
  const status = await inspectTransport(setup.sessionId);
  expect(status).toMatchObject({
    ok: true,
    result: {recording: true, phase: "idle", error: null},
  });
});

test("owner loss mid-recording seals the transport admission for the recovery surface on reopen", async ({page}) => {
  test.setTimeout(120_000);
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000)).ok).toBe(true);

  const setup = await page.evaluate(async () => {
    const send = (operation, payload, sidecar) =>
      window.lmdjWebRuntimeHost.transport.send(
        {
          protocol_version: 1,
          request_id: crypto.randomUUID(),
          operation,
          payload,
        },
        sidecar === undefined ? {} : {sidecar},
      );
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
      view.setInt16(44 + frame * 2, 2_000, true);
    }
    const wavSha256 = [...new Uint8Array(
      await crypto.subtle.digest("SHA-256", wav),
    )].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    const projectId = crypto.randomUUID();
    const patternId = crypto.randomUUID();
    const sessionId = crypto.randomUUID();
    const created = await send("project.create", {
      project_id: projectId,
      bpm: 120,
      initial_pattern: {pattern_id: patternId, bars: 1, events: []},
      pattern_transport: true,
    });
    const importToken = crypto.randomUUID();
    const imported = await send("sample.import.begin", {
      import_token: importToken,
      command_id: crypto.randomUUID(),
      expected_revision: 0,
      slot: {bank: 0, pad: 0},
      asset_id: crypto.randomUUID(),
      byte_length: wav.byteLength,
    });
    const chunked = await send("sample.import.chunk", {
      import_token: importToken,
      offset: 0,
      final: true,
      sidecar: {sidecar_bytes: wav.byteLength, sidecar_sha256: wavSha256},
    }, wav);
    const committed = await send("sample.import.commit", {
      import_token: importToken,
    });
    const snapshot = await send("snapshot.reload", {pattern_id: patternId});
    const activated = await send("audio.activate", {});
    const ticket = await send("pattern.transport.request", {
      session_id: sessionId,
      project_id: projectId,
      command_id: crypto.randomUUID(),
      expected_epoch: 1,
      intent: "record",
      expected_revision: null,
    });
    return {
      projectId, patternId, sessionId,
      created, imported, chunked, committed, snapshot, activated, ticket,
    };
  });
  expect(setup.created.ok).toBe(true);
  expect(setup.ticket).toMatchObject({ok: true, result: {submit: "accepted"}});

  const inspectTransport = (sessionId) =>
    page.evaluate((id) =>
      window.lmdjWebRuntimeHost.transport.send({
        protocol_version: 1,
        request_id: crypto.randomUUID(),
        operation: "pattern.transport.inspect",
        payload: {session_id: id},
      }), sessionId);
  await expect.poll(async () => {
    const status = await inspectTransport(setup.sessionId);
    return status.ok && status.result.recording === true &&
      status.result.phase === "idle";
  }, {timeout: 30_000}).toBe(true);
  await page.evaluate(() =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "trigger",
      payload: {slot: 0, velocity: 100},
    }));
  await page.evaluate(() =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "trigger",
      payload: {slot: 0, kind: "release"},
    }));

  // A mid-recording reload kills the Worker without a Close: owner loss.
  await page.reload();
  await waitForFormalHost(page);
  const reopened = await page.evaluate(async ({projectId, patternId}) => {
    const send = (operation, payload) =>
      window.lmdjWebRuntimeHost.transport.send({
        protocol_version: 1,
        request_id: crypto.randomUUID(),
        operation,
        payload,
      });
    const opened = await send("project.open", {
      project_id: projectId,
      pattern_id: patternId,
      pattern_transport: true,
    });
    const listed = await send("sequence.recovery.list", {});
    return {opened, listed};
  }, setup);
  expect(reopened.opened.ok).toBe(true);
  expect(reopened.opened.result.project_id).toBe(setup.projectId);
  expect(reopened.listed).toMatchObject({ok: true});
  // The Host injects the retained Project path into the listing; a regression
  // there answers with an error or another Project's candidates, not this one.
  expect(Object.keys(reopened.listed.result).sort()).toEqual([
    "candidates",
    "project_revision",
  ]);
  expect(reopened.listed.result.candidates).toHaveLength(1);
  expect(reopened.listed.result.candidates).toContainEqual(
    expect.objectContaining({
      session_id: setup.sessionId,
      reason: "owner_lost",
    }),
  );
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
