import {expect, test} from "@playwright/test";
import {test as opfsTest} from "../project_io/opfs_browser.fixture.mjs";
import {attachPairedEnergyProbe} from "./paired_energy_probe.mjs";
import {attachTempoOnsetProbe, nextTempoQuarterFrames} from "./tempo_onset_probe.mjs";
import {readFile, readdir, writeFile} from "node:fs/promises";
import {createHash} from "node:crypto";
import {WEB_RUNTIME_IDENTITY} from "../../../../products/lmdj/generated/web-runtime-identity.mjs";


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


async function activateFromClick(page, sampleRate, withMonitor = false) {
  await page.evaluate(({requestedSampleRate, withMonitor}) => {
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
        const monitor = withMonitor ? context.createGain() : null;
        const monitorAnalyser = withMonitor ? context.createAnalyser() : null;
        const monitorHandle = monitor === null ? null :
          window.lmdjWebRuntimeHost.registerAudioNode(monitor);
        if (monitor !== null) {
          analyser.connect(monitor);
          monitor.connect(monitorAnalyser);
          monitorAnalyser.connect(context.destination);
        } else {
          analyser.connect(context.destination);
        }
        const tapHandle = window.lmdjWebRuntimeHost.registerAudioNode(tapNode);
        window.__lmdjFormalAudioGraph = {
          context, tapNode, analyser, handle, monitor, monitorAnalyser, monitorHandle,
        };
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
  }, {requestedSampleRate: sampleRate, withMonitor});
  await page.locator("#activate-formal-audio").click();
  await page.waitForFunction(() => window.__lmdjFormalActivation !== undefined);
  return page.evaluate(() => window.__lmdjFormalActivation);
}

test("monitor attenuates the Wasm output after the master bus and survives direct recovery", async ({page}) => {
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000, true)).ok).toBe(true);
  expect((await page.evaluate(() =>
    window.lmdjWebRuntimeHostTest.runSharedEngineProof())).outputEnergy).toBeGreaterThan(0);

  await attachPairedEnergyProbe(page);
  try {
    for (const level of [1, 0.5, 0]) {
      const energy = await page.evaluate(async (level) => {
        const {context, analyser, monitor} = window.__lmdjFormalAudioGraph;
        const afterFrame = Math.ceil(context.currentTime * context.sampleRate);
        monitor.gain.setValueAtTime(level, context.currentTime);
        await window.lmdjWebRuntimeHostTest.runDirectOutputContinuationProof();
        // Collect one complete analyser-sized window on the rendering thread.
        // Both energies contain the same frames of the real 100 ms Bank voice.
        const paired = await window.__lmdjPairedEnergyProbe.read({
          frameCount: analyser.fftSize, afterFrame,
        });
        return {...paired, afterFrame, frameCount: analyser.fftSize};
      }, level);
      expect(energy.firstFrame).toBeGreaterThanOrEqual(energy.afterFrame);
      expect(energy.frames).toBe(energy.frameCount);
      expect(energy.master).toBeGreaterThan(0);
      expect(energy.output / energy.master).toBeCloseTo(level * level, 5);
    }
  } finally {
    await page.evaluate(() => window.__lmdjPairedEnergyProbe.close());
  }

  const recovery = await page.evaluate(async () => {
    const {context, tapNode, handle, monitorHandle} = window.__lmdjFormalAudioGraph;
    const otherContext = new AudioContext();
    window.lmdjWebRuntimeHost.registerAudioContext(otherContext);
    const otherHandle = window.lmdjWebRuntimeHost.registerAudioNode(otherContext.createGain());
    const crossContext = window.lmdjWebRuntimeHost.connectAudioWorkletDirect(handle, otherHandle);
    await otherContext.close();
    tapNode.disconnect();
    const connect = window.lmdjWebRuntimeHost.connectAudioWorkletDirect(handle, monitorHandle);
    const repeated = window.lmdjWebRuntimeHost.connectAudioWorkletDirect(handle, monitorHandle);
    // Once recovered, a different destination must not add an unattenuated path.
    const reroute = window.lmdjWebRuntimeHost.connectAudioWorkletDirect(handle);
    return {connect, repeated, crossContext, reroute, state: context.state,
      connections: window.lmdjWebRuntimeHostTest.directOutputConnections()};
  });
  expect(recovery).toEqual({connect: true, repeated: true, crossContext: false,
    reroute: false, state: "running", connections: 1});
  const muted = await page.evaluate(async () => {
    const {monitorAnalyser} = window.__lmdjFormalAudioGraph;
    const proof = await window.lmdjWebRuntimeHostTest.runDirectOutputContinuationProof();
    const values = new Float32Array(monitorAnalyser.fftSize);
    monitorAnalyser.getFloatTimeDomainData(values);
    return {engineEnergy: proof.outputEnergy,
      outputEnergy: values.reduce((sum, value) => sum + value * value, 0)};
  });
  expect(muted.engineEnergy).toBeGreaterThan(0);
  expect(muted.outputEnergy).toBe(0);
  await page.evaluate(() => {
    const {context, monitor} = window.__lmdjFormalAudioGraph;
    monitor.gain.setValueAtTime(0.5, context.currentTime);
  });
  await page.evaluate(() => window.lmdjWebRuntimeHostTest.runDirectOutputContinuationProof());
  await expect.poll(() => page.evaluate(() => {
    const {monitorAnalyser} = window.__lmdjFormalAudioGraph;
    const values = new Float32Array(monitorAnalyser.fftSize);
    monitorAnalyser.getFloatTimeDomainData(values);
    return values.reduce((sum, value) => sum + value * value, 0);
  }), {intervals: [10]}).toBeGreaterThan(0);
});


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
  // The accepted ticket precedes the durable-opening continuation. Audio
  // receipt polling starts only after that preparation has actually finished.
  expect(journey.ticket).toMatchObject({
    ok: true,
    result: {submit: "accepted", status: {phase: "preparing"}},
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

test("cross-identity snapshot reload under an armed transport rebinds instead of bricking", async ({page}) => {
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
    const patternA = crypto.randomUUID();
    const patternB = crypto.randomUUID();
    const sessionId = crypto.randomUUID();
    const created = await send("project.create", {
      project_id: projectId,
      bpm: 120,
      initial_pattern: {pattern_id: patternA, bars: 1, events: []},
      pattern_transport: true,
    });
    const importToken = crypto.randomUUID();
    await send("sample.import.begin", {
      import_token: importToken,
      command_id: crypto.randomUUID(),
      expected_revision: 0,
      slot: {bank: 0, pad: 0},
      asset_id: crypto.randomUUID(),
      byte_length: wav.byteLength,
    });
    await send("sample.import.chunk", {
      import_token: importToken,
      offset: 0,
      final: true,
      sidecar: {sidecar_bytes: wav.byteLength, sidecar_sha256: wavSha256},
    }, wav);
    await send("sample.import.commit", {import_token: importToken});
    const madeB = await send("pattern.create", {
      command_id: crypto.randomUUID(),
      expected_revision: 1,
      pattern_id: patternB,
      bars: 1,
    });
    const snapshot = await send("snapshot.reload", {pattern_id: patternA});
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
      projectId, patternA, patternB, sessionId,
      created, madeB, snapshot, activated, ticket,
    };
  });
  expect(setup.created.ok).toBe(true);
  expect(setup.madeB.ok).toBe(true);
  expect(setup.activated.ok).toBe(true);
  expect(setup.ticket).toMatchObject({ok: true, result: {submit: "accepted"}});

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
  const pollUntil = (predicate) => expect.poll(async () => {
    const status = await inspectTransport(setup.sessionId);
    return status.ok && predicate(status.result);
  }, {timeout: 30_000}).toBe(true);

  await pollUntil((s) => s.recording === true && s.phase === "idle");
  await sendTransport("trigger", {slot: 0, velocity: 100});
  await sendTransport("trigger", {slot: 0, kind: "release"});
  expect((await sendTransport("pattern.transport.request", {
    session_id: setup.sessionId,
    project_id: setup.projectId,
    command_id: crypto.randomUUID(),
    expected_epoch: 2,
    intent: "record",
    expected_revision: null,
  }))).toMatchObject({ok: true, result: {submit: "accepted"}});
  await pollUntil((s) =>
    s.recording === false && s.phase === "idle" &&
    s.publication_pending === false);
  expect((await sendTransport("pattern.transport.request", {
    session_id: setup.sessionId,
    project_id: setup.projectId,
    command_id: crypto.randomUUID(),
    expected_epoch: 3,
    intent: "play_stop",
    expected_revision: null,
  }))).toMatchObject({ok: true, result: {submit: "accepted"}});
  await pollUntil((s) => s.playing === false && s.phase === "idle");

  // Stopped-state cross-identity reload: the engagement rebinds and the next
  // Record works on the new Pattern instead of bricking. The reload's pending
  // publication applies at the Bar boundary; a Record before that is a
  // transient refusal, so poll it.
  expect(await sendTransport("snapshot.reload", {pattern_id: setup.patternB}))
    .toMatchObject({ok: true});
  let lastTicket = null;
  try {
    await expect.poll(async () => {
      lastTicket = await sendTransport("pattern.transport.request", {
        session_id: setup.sessionId,
        project_id: setup.projectId,
        command_id: crypto.randomUUID(),
        expected_epoch: 4,
        intent: "record",
        expected_revision: null,
      });
      return lastTicket.ok;
    }, {timeout: 30_000}).toBe(true);
  } catch (error) {
    throw new Error(
      `record after cross-identity reload never accepted: ${JSON.stringify(lastTicket)}`,
      {cause: error},
    );
  }
  await pollUntil((s) => s.recording === true && s.phase === "idle");
  await sendTransport("trigger", {slot: 0, velocity: 100});
  await sendTransport("trigger", {slot: 0, kind: "release"});
  expect((await sendTransport("pattern.transport.request", {
    session_id: setup.sessionId,
    project_id: setup.projectId,
    command_id: crypto.randomUUID(),
    expected_epoch: 5,
    intent: "record",
    expected_revision: null,
  }))).toMatchObject({ok: true, result: {submit: "accepted"}});
  await pollUntil((s) =>
    s.recording === false && s.phase === "idle" &&
    s.publication_pending === false);
  const truth = await sendTransport("project.inspect", {});
  expect(truth.ok).toBe(true);
  expect(
    truth.result.project.patterns[setup.patternB].events,
  ).toHaveLength(1);
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


test("activation waits for an in-flight paused callback instead of refusing it", async ({page}) => {
  // #2345: once the context is resumed every paused-gate callback briefly
  // holds a borrow. Activation racing that borrow failed the Host.
  await waitForFormalHost(page);
  expect((await activateFromClick(page, 48_000)).ok).toBe(true);
  const proof = await page.evaluate(async () =>
    window.lmdjWebRuntimeHostTest.runPausedBorrowActivationProof());
  expect(proof.held).toEqual({gate: "paused", callbackInFlight: 1});
  expect(proof.settledWhileHeld).toBe(false);
  expect(proof.beginMetHeldBorrow).toBe(true);
  expect(proof.activation).toMatchObject({
    ok: true,
    result: {state: "running", changed: true},
  });
});


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


test("real count-in cue ACK and callback last use independently fence terminal retirement", async ({page}, testInfo) => {
  await waitForFormalHost(page);
  const seam = await page.evaluate(() => Object.fromEntries([
    "armPhysicalFenceBarrier", "releasePhysicalFenceBarrier",
    "physicalFenceState", "runPhysicalFenceQuiescenceWait", "dispatchProcessorError",
  ].map((name) => [name, typeof window.lmdjWebRuntimeHostTest?.[name]])));
  for (const [name, type] of Object.entries(seam)) {
    expect(type, `UNEXECUTED: guarded packaged adapter requires ${name}`)
      .toBe("function");
  }

  // Keep the master tap and cue destination distinct. Output 1 joins the
  // monitor downstream of the master tap, using the actual packaged processor.
  await page.evaluate(() => {
    const button = document.createElement("button");
    button.id = "activate-physical-fence-audio";
    button.addEventListener("click", async () => {
      try {
        const host = window.lmdjWebRuntimeHost;
        const context = new AudioContext({sampleRate: 48_000});
        await context.resume();
        const handle = host.registerAudioContext(context);
        const masterTap = context.createGain();
        const monitor = context.createGain();
        masterTap.connect(monitor);
        monitor.connect(context.destination);
        const masterHandle = host.registerAudioNode(masterTap);
        const cueHandle = host.registerAudioNode(monitor);
        window.__lmdjPhysicalFenceGraph = {
          context, masterTap, monitor, handle, masterHandle, cueHandle,
        };
        window.__lmdjPhysicalFenceActivation = await host
          .startAudioWorkletWithCountIn(handle, masterHandle, cueHandle);
      } catch (error) {
        window.__lmdjPhysicalFenceActivation = {ok: false, error: String(error)};
      }
    }, {once: true});
    document.body.append(button);
  });
  await page.locator("#activate-physical-fence-audio").click();
  await page.waitForFunction(() =>
    window.__lmdjPhysicalFenceActivation !== undefined);
  expect(await page.evaluate(() => window.__lmdjPhysicalFenceActivation))
    .toMatchObject({ok: true, sampleRate: 48_000, inputs: 0,
      outputs: 2, channels: 2, frames: 128});

  const setup = await page.evaluate(async () => {
    const send = async (operation, payload, sidecar) => {
      const response = await window.lmdjWebRuntimeHost.transport.send({
        protocol_version: 1, request_id: crypto.randomUUID(), operation, payload,
      }, sidecar === undefined ? {} : {sidecar});
      if (!response.ok) {
        throw new Error(`real fence setup ${operation}: ${JSON.stringify(response)}`);
      }
      return response.result;
    };
    const projectId = crypto.randomUUID();
    const patternId = crypto.randomUUID();
    await send("project.create", {project_id: projectId, bpm: 120,
      initial_pattern: {pattern_id: patternId, bars: 1, events: []},
      pattern_transport: true});

    // A real imported Bank permits ordinary audio.activate. It does not
    // generate the cue: only the subsequent scheduled Record request does.
    const frames = 480;
    const wav = new Uint8Array(44 + frames * 2);
    const view = new DataView(wav.buffer);
    for (const [offset, tag] of [[0, "RIFF"], [8, "WAVE"], [12, "fmt "], [36, "data"]]) {
      for (let index = 0; index < tag.length; ++index) {
        wav[offset + index] = tag.charCodeAt(index);
      }
    }
    view.setUint32(4, 36 + frames * 2, true);
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, 48_000, true);
    view.setUint32(28, 96_000, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    view.setUint32(40, frames * 2, true);
    for (let frame = 0; frame < frames; ++frame) {
      view.setInt16(44 + frame * 2,
        Math.round(Math.sin(2 * Math.PI * 440 * frame / 48_000) * 8_000), true);
    }
    const sha256 = [...new Uint8Array(await crypto.subtle.digest("SHA-256", wav))]
      .map((byte) => byte.toString(16).padStart(2, "0")).join("");
    const importToken = crypto.randomUUID();
    await send("sample.import.begin", {import_token: importToken,
      command_id: crypto.randomUUID(), expected_revision: 0,
      slot: {bank: 0, pad: 0}, asset_id: crypto.randomUUID(), byte_length: wav.byteLength});
    await send("sample.import.chunk", {import_token: importToken, offset: 0, final: true,
      sidecar: {sidecar_bytes: wav.byteLength, sidecar_sha256: sha256}}, wav);
    await send("sample.import.commit", {import_token: importToken});
    await send("snapshot.reload", {pattern_id: patternId});
    const negotiated = await send("pattern.transport.count-in.capabilities", {negotiate: true});
    if (!negotiated.supported || !negotiated.negotiated || !negotiated.output_ready) {
      throw new Error(`UNEXECUTED: real count-in negotiation unavailable: ${JSON.stringify(negotiated)}`);
    }
    await send("audio.activate", {});
    const capability = await send("pattern.transport.count-in.capabilities", {negotiate: false});
    return {projectId, sessionId: crypto.randomUUID(), commandId: crypto.randomUUID(), capability};
  });
  expect(setup.capability).toMatchObject({supported: true, negotiated: true, output_ready: true});
  for (const field of ["runtime_generation", "frame_epoch", "next_serial"]) {
    expect(setup.capability[field], `actual count-in ${field}`).toMatch(/^[1-9]\d*$/);
  }

  const checkpoints = {setup};
  const assertValidFence = (state) => {
    expect(state.stage).toBeGreaterThanOrEqual(0);
    expect(state.stage).toBeLessThanOrEqual(0xffff_ffff);
    expect(state.stage & 0x8000_0000,
      "INVALID witness: the producer's original 1000 * 10 ms guard expired").toBe(0);
    expect(state.cuePendingBatch,
      "UNEXECUTED: actual atomic cue_batch_pending_ readback is required")
      .toEqual(expect.any(Number));
  };
  const readFence = () => page.evaluate(() =>
    window.lmdjWebRuntimeHostTest.physicalFenceState());
  const waitFence = async (stage, physicalQuiescent = false) => {
    // Only JS polling yields on browser main. No synchronous C quiescence
    // wait may prevent the main-loop release of an admitted Worklet callback.
    const handle = await page.waitForFunction(({stage, physicalQuiescent}) => {
      const state = window.lmdjWebRuntimeHostTest.physicalFenceState();
      if ((state.stage & 0x8000_0000) !== 0) {
        throw new Error("INVALID witness: physical fence guard expired");
      }
      return (state.stage & stage) === stage &&
        (!physicalQuiescent || state.physicalQuiescent === true) ? state : false;
    }, {stage, physicalQuiescent}, {polling: 10, timeout: 5_000});
    try {
      const state = await handle.jsonValue();
      assertValidFence(state);
      return state;
    } finally {
      await handle.dispose();
    }
  };

  try {
    expect(await page.evaluate(() =>
      window.lmdjWebRuntimeHostTest.armPhysicalFenceBarrier(3))).toBe(true);
    checkpoints.request = await page.evaluate(({projectId, sessionId, commandId, capability}) =>
      window.lmdjWebRuntimeHost.transport.send({
        protocol_version: 1, request_id: crypto.randomUUID(),
        operation: "pattern.transport.count-in.request", payload: {
          session_id: sessionId, project_id: projectId, command_id: commandId,
          runtime_generation: capability.runtime_generation, frame_epoch: capability.frame_epoch,
          schedule_serial: capability.next_serial, expected_epoch: "1", bars: 1, expected_revision: null,
        },
      }), setup);
    expect(checkpoints.request).toMatchObject({ok: true, result: {submit: "accepted",
      ticket: {session_id: setup.sessionId, command_id: setup.commandId,
        runtime_generation: setup.capability.runtime_generation,
        frame_epoch: setup.capability.frame_epoch, schedule_serial: setup.capability.next_serial}}});

    checkpoints.cueHeld = await waitFence(1);
    expect(checkpoints.cueHeld).toMatchObject({stage: 1, physicalQuiescent: false, callbackInFlight: 1});
    expect(checkpoints.cueHeld.cueBatch).toBeGreaterThan(0);
    expect(checkpoints.cueHeld.cuePendingBatch).toBe(checkpoints.cueHeld.cueBatch);
    expect(checkpoints.cueHeld.borrows).toBeGreaterThan(0);

    // The actual control wait exhausts both original 20 ms budgets against
    // this real held callback. Its failed Result cannot retire either borrow.
    checkpoints.operationalWait = await page.evaluate(() =>
      window.lmdjWebRuntimeHostTest.runPhysicalFenceQuiescenceWait(20));
    expect(checkpoints.operationalWait).toMatchObject({completed: true, has_value: false,
      error: {code: "INTERNAL_ERROR",
        message: "Wasm AudioWorklet quiescence timed out with callback still in flight"}});
    expect(checkpoints.operationalWait.elapsed_ms).toBeGreaterThanOrEqual(40);
    expect(checkpoints.operationalWait.observed_wall_ms).toBeLessThan(500);

    // The low-level adapter wait does not itself dispatch a Host lifecycle
    // failure. Deliver the separate processor-error notification through its
    // existing actual control handler while this same callback still borrows.
    // Its notification must preserve the first quiescence_timeout fatal and
    // cannot stand in for either physical release below.
    await page.evaluate(() => window.lmdjWebRuntimeHostTest.dispatchProcessorError());
    await page.waitForFunction(() =>
      window.Module._lmdj_web_audio_control_failure_committed() === 1);
    checkpoints.controlFailureCommitted = await page.evaluate(() =>
      window.Module._lmdj_web_audio_control_failure_committed() === 1);
    expect(checkpoints.controlFailureCommitted).toBe(true);
    checkpoints.phase1 = await readFence();
    assertValidFence(checkpoints.phase1);
    expect(checkpoints.phase1).toMatchObject({stage: 1, gate: "terminal", fatal: "quiescence_timeout",
      physicalQuiescent: false, callbackInFlight: 1,
      cueBatch: checkpoints.cueHeld.cueBatch, cuePendingBatch: checkpoints.cueHeld.cueBatch});
    expect(checkpoints.phase1.borrows).toBeGreaterThan(0);

    // Release only the actual cue consumer. Its real ACK must finish before
    // stage 2, while the SAME callback still protects its epilogue's Impl use.
    expect(await page.evaluate(() =>
      window.lmdjWebRuntimeHostTest.releasePhysicalFenceBarrier(1))).toBe(true);
    checkpoints.phase2 = await waitFence(3);
    expect(checkpoints.phase2).toMatchObject({stage: 3, gate: "terminal", fatal: "quiescence_timeout",
      cueBatch: checkpoints.cueHeld.cueBatch, cuePendingBatch: 0,
      physicalQuiescent: false, callbackInFlight: 1});
    expect(checkpoints.phase2.borrows).toBeGreaterThan(0);

    expect(await page.evaluate(() =>
      window.lmdjWebRuntimeHostTest.releasePhysicalFenceBarrier(2))).toBe(true);
    checkpoints.retired = await waitFence(3, true);
    expect(checkpoints.retired).toMatchObject({stage: 3, gate: "terminal", fatal: "quiescence_timeout",
      cuePendingBatch: 0, physicalQuiescent: true, borrows: 0, callbackInFlight: 0});
    checkpoints.retainedOperationalWait = await page.evaluate(() => JSON.parse(
      window.Module.ccall("lmdj_web_audio_test_quiescence_timeout_result", "string", [], [])));
    expect(checkpoints.retainedOperationalWait).toEqual({completed: true, has_value: false,
      elapsed_ms: checkpoints.operationalWait.elapsed_ms, error: checkpoints.operationalWait.error});

    // Physical retirement permits resource cleanup; it preserves the original
    // operational failure rather than reporting successful Host operation.
    checkpoints.hostStatus = await page.evaluate(async () => {
      try {
        const response = await window.lmdjWebRuntimeHost.transport.send({protocol_version: 1,
          request_id: crypto.randomUUID(), operation: "host.status", payload: {}});
        return {settlement: "response", response};
      } catch (error) {
        return {settlement: "rejected", error: {
          code: error.code, message: error.message, details: error.details,
        }};
      }
    });
    if (checkpoints.hostStatus.settlement === "response") {
      expect(checkpoints.hostStatus.response)
        .toMatchObject({ok: false, error: {code: "HOST_STATE_INVALID"}});
    } else {
      expect(checkpoints.hostStatus)
        .toMatchObject({settlement: "rejected", error: {code: "HOST_STATE_INVALID"}});
    }
  } finally {
    // Release both finite guards even when a diagnostic assertion fails.
    // Never kill the callback, Engine, Control, backend, or their owners.
    checkpoints.guardReleased = await page.evaluate(() =>
      window.lmdjWebRuntimeHostTest.releasePhysicalFenceBarrier(3));
    checkpoints.finalFence = await readFence();
    const checkpointPath = testInfo.outputPath("real-count-in-terminal-physical-fence.json");
    await (await import("node:fs/promises")).writeFile(checkpointPath,
      JSON.stringify(checkpoints, null, 2), {flag: "wx"});
    await testInfo.attach("real-count-in-terminal-physical-fence", {
      path: checkpointPath, contentType: "application/json",
    });
    expect(checkpoints.guardReleased).toBe(true);
    assertValidFence(checkpoints.finalFence);
  }
});

opfsTest("saved recording metadata RPC verifies real WAVs through two page reopens", async ({context}, testInfo) => {
  opfsTest.setTimeout(180_000);
  const validDigest="985ee1bbde8458eeb675cff7bb99b6bd61278b9646a127c7c39b1fb7634cb2d5";
  const unsupportedDigest="62aedd330eea859b7e3725d842cf089a97177d8a0f2918ad0d151212230c9d19";
  const mismatchDigest="6517a13adcf9f3e715104fd2d8fa6e738ae1ccad2437c615e2f85a7d7b706adc";
  const journeys=[];
  for(const variant of ["valid","unsupported","mismatch"]) {
    const projectId=crypto.randomUUID(),patternId=crypto.randomUUID(),performanceId=crypto.randomUUID();
    const artifact={sha256:variant==="unsupported"?unsupportedDigest:validDigest,
      media_type:"audio/wav",byte_length:192124};
    const reports=[];
    for(const phase of ["prepare","reopen","reopen"]) {
      const page=await context.newPage();
      await waitForFormalHost(page);
      if(phase==="prepare") expect((await activateFromClick(page,48000)).ok).toBe(true);
      const report=await page.evaluate(async ({variant,phase,projectId,patternId,performanceId,artifact}) => {
        const send=async (operation,payload) => {
          const response=await window.lmdjWebRuntimeHost.transport.send({protocol_version:1,
            request_id:crypto.randomUUID(),operation,payload});
          if(!response.ok) throw new Error(operation+": "+JSON.stringify(response));
          return response.result;
        };
        const root=await navigator.storage.getDirectory();
        if(phase==="prepare") {
          const created=await send("project.create",{project_id:projectId,bpm:120,
            initial_pattern:{pattern_id:patternId,bars:1,events:[]}});
          if(created.project_revision!==0) throw new Error("Project creation revision changed");
          await send("snapshot.reload",{pattern_id:patternId});await send("audio.activate",{});
          const begun=await send("performance.record.begin",{command_id:crypto.randomUUID(),expected_revision:0,
            session_id:performanceId,performance_id:performanceId});
          if(begun.project_revision!==1) throw new Error("Performance begin revision changed");
          await send("performance.record.stop",{session_id:performanceId,request_id:crypto.randomUUID()});
          // Independent fixture, not recorded PCM: zero events with an exact
          // positive WAV frame count and odd non-audio JUNK/padding.
          const bytes=new Uint8Array(192124),view=new DataView(bytes.buffer);
          const text=(at,value)=>{for(let i=0;i<value.length;++i) bytes[at+i]=value.charCodeAt(i);};
          const rate=variant==="unsupported"?32000:48000;
          text(0,"RIFF");view.setUint32(4,192116,true);text(8,"WAVE");text(12,"fmt ");view.setUint32(16,16,true);
          view.setUint16(20,1,true);view.setUint16(22,2,true);view.setUint32(24,rate,true);view.setUint32(28,rate*4,true);
          view.setUint16(32,4,true);view.setUint16(34,16,true);text(36,"JUNK");view.setUint32(40,3,true);
          bytes.set([1,2,3,171],44);text(48,"data");view.setUint32(52,192068,true);
          const projects=await root.getDirectoryHandle("projects");
          const bundle=await projects.getDirectoryHandle(projectId+".lmdj");
          const assets=await bundle.getDirectoryHandle("assets");
          const file=await assets.getFileHandle(artifact.sha256+".wav",{create:true});
          const writable=await file.createWritable();await writable.write(bytes);await writable.close();
          const saved=await send("performance.save",{command_id:crypto.randomUUID(),expected_revision:1,
            performance_id:performanceId,name:"silent recording metadata fixture",recording_artifact:artifact});
          if(saved.project_revision!==2) throw new Error("Performance save revision changed");
          if(variant==="mismatch") {
            const corrupt=await file.createWritable({keepExistingData:true});
            await corrupt.write({type:"write",position:192123,data:new Uint8Array([1])});await corrupt.close();
          }
        } else await send("project.open",{project_id:projectId,pattern_id:patternId});
        const inspected=await send("performance.inspect",{performance_id:performanceId});
        const response=await window.lmdjWebRuntimeHost.transport.send({protocol_version:1,
          request_id:crypto.randomUUID(),operation:"performance.recording.metadata",
          payload:{project_id:projectId,performance_id:performanceId,expected_revision:2,recording_artifact:artifact}});
        const queryHostState=(await send("host.status",{})).state;
        if(phase==="prepare") await send("audio.suspend",{});
        const projects=await root.getDirectoryHandle("projects");
        const bundle=await projects.getDirectoryHandle(projectId+".lmdj");
        const assets=await bundle.getDirectoryHandle("assets");
        const file=await (await assets.getFileHandle(artifact.sha256+".wav")).getFile();
        const bytes=new Uint8Array(await file.arrayBuffer());
        const sha256=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)),
          value=>value.toString(16).padStart(2,"0")).join("");
        const closed=await send("host.close",{});
        return {phase,queryHostState,inspected,response,physical:{sha256,length:file.size,
          prefix:Array.from(bytes.slice(0,56)),tail:Array.from(bytes.slice(-4))},closed};
      },{variant,phase,projectId,patternId,performanceId,artifact});
      expect(report.phase).toBe(phase);
      expect(report.queryHostState).toBe(phase==="prepare"?"running":"core-ready");
      expect(report.inspected).toEqual({performance:{id:performanceId,name:"silent recording metadata fixture",
        created_bpm:120,recording_artifact:artifact,events:[]},project_revision:2});
      const {request_id,...response}=report.response;
      expect(request_id).toMatch(/^[0-9a-f-]{36}$/);
      if(variant==="mismatch") expect(response).toEqual({protocol_version:1,ok:false,
        error:{code:"COOK_FAILED",message:"runtime snapshot preparation failed",details:{storage_condition:"artifact_mismatch"}}});
      else expect(response).toEqual({protocol_version:1,ok:true,result:{project_id:projectId,performance_id:performanceId,
        project_revision:2,recording_revision:0,recording_artifact:artifact,
        audio_metadata:variant==="valid"?{sample_rate:48000,channels:2,source_frames:48017}:null,
        audio_error:variant==="unsupported"?{code:"UNSUPPORTED_AUDIO",message:"audio input is unsupported",details:{}}:null}});
      const prefix=variant==="unsupported"
        ? "5249464674ee020057415645666d74201000000001000200007d000000f40100040010004a554e4b03000000010203ab6461746144ee0200"
        : "5249464674ee020057415645666d7420100000000100020080bb000000ee0200040010004a554e4b03000000010203ab6461746144ee0200";
      expect(report.physical).toEqual({sha256:variant==="mismatch"?mismatchDigest:artifact.sha256,length:192124,
        prefix:Array.from(Buffer.from(prefix,"hex")),tail:variant==="mismatch"?[0,0,0,1]:[0,0,0,0]});
      expect(report.closed.state).toBe("closed");
      reports.push(report);await page.close();expect(page.isClosed()).toBe(true);
    }
    journeys.push({variant,projectId,patternId,performanceId,artifact,reports,closedPages:3});
  }
  const evidencePath=testInfo.outputPath("recording-metadata-query-reopens.json");
  await (await import("node:fs/promises")).writeFile(evidencePath,JSON.stringify({journeys},null,2),{flag:"wx"});
  await testInfo.attach("recording-metadata-query-reopens",{path:evidencePath,contentType:"application/json"});
});

opfsTest("thirty-minute recording Save and bind preserve full identity through two page reopens", async ({context}, testInfo) => {
  opfsTest.setTimeout(180_000);
  const bundleSchema=JSON.parse(await (await import("node:fs/promises")).readFile(
    new URL("../../../../contracts/project/lmdj.project-bundle.v1.schema.json",import.meta.url),"utf8"));
  const bundleContractVersion=bundleSchema["x-lmdj-contract-version"];
  // Independent Python hashlib witness for this literal PCM16 stereo header
  // followed by345600000 zero bytes. This is a controlled physical file, not
  // device capture. Keep the production512MiB heap and default30s RPC budget.
  const headerHex="524946463070991457415645666d7420100000000100020080bb000000ee0200040010004a554e4b03000000010203ab6461746100709914";
  const artifact={sha256:"59602d6f8b90b228985c6254d5f843945c42fcbd33552d9326f4784da627fbc6",
    media_type:"audio/wav",byte_length:345600056};
  const journeys=[];
  for(const admission of ["save","bind"]) {
    const projectId=crypto.randomUUID(),patternId=crypto.randomUUID(),performanceId=crypto.randomUUID();
    const revision=admission==="save"?2:3,reports=[];
    for(const phase of ["prepare","reopen","reopen"]) {
      const page=await context.newPage(),errors=[];
      page.on("pageerror",error=>errors.push(error.message));
      const host=await waitForFormalHost(page);
      expect(host.memoryBytes).toBe(536870912);
      if(phase==="prepare") expect((await activateFromClick(page,48000)).ok).toBe(true);
      const report=await page.evaluate(async ({admission,phase,projectId,patternId,performanceId,revision,artifact,header,bundleContractVersion})=>{
        const send=async (operation,payload)=>{
          const response=await window.lmdjWebRuntimeHost.transport.send({protocol_version:1,
            request_id:crypto.randomUUID(),operation,payload});
          if(!response.ok)throw new Error(operation+": "+JSON.stringify(response));
          return response.result;
        };
        const root=await navigator.storage.getDirectory();
        let admitted=null,startupListed=null;
        if(phase==="prepare") {
          await send("project.create",{project_id:projectId,bpm:120,
            initial_pattern:{pattern_id:patternId,bars:1,events:[]}});
          await send("snapshot.reload",{pattern_id:patternId});await send("audio.activate",{});
          await send("performance.record.begin",{command_id:crypto.randomUUID(),expected_revision:0,
            session_id:performanceId,performance_id:performanceId});
          await send("performance.record.stop",{session_id:performanceId,request_id:crypto.randomUUID()});
          if(admission==="bind")await send("performance.save",{command_id:crypto.randomUUID(),expected_revision:1,
            performance_id:performanceId,name:"thirty minutes",recording_artifact:null});
          const assets=await (await (await root.getDirectoryHandle("projects"))
            .getDirectoryHandle(projectId+".lmdj")).getDirectoryHandle("assets");
          const file=await assets.getFileHandle(artifact.sha256+".wav",{create:true});
          const writable=await file.createWritable();await writable.truncate(artifact.byte_length);
          await writable.write({type:"write",position:0,data:new Uint8Array(header)});await writable.close();
          const started=performance.now();
          admitted=await send(admission==="save"?"performance.save":"performance.recording.bind",{
            command_id:crypto.randomUUID(),expected_revision:revision-1,performance_id:performanceId,
            ...(admission==="save"?{name:"thirty minutes"}:{}),recording_artifact:artifact});
          admitted={receipt:admitted,elapsedMs:performance.now()-started};
        } else {
          // Creator startup discovers on an unselected Session before opening.
          // Keep the later post-open full physical digest oracle as well.
          startupListed=await send("project.list",{});
          await send("project.open",{project_id:projectId,pattern_id:patternId});
        }
        const inspected=await send("performance.inspect",{performance_id:performanceId});
        const metadata=await send("performance.recording.metadata",{project_id:projectId,
          performance_id:performanceId,expected_revision:revision,recording_artifact:artifact});
        // Creator boot discovers before opening. Direct project.open alone
        // cannot prove this formerly whole-file allocation path works.
        const listed=await send("project.list",{});
        const project=await send("project.inspect",{});
        const assets=await (await (await root.getDirectoryHandle("projects"))
          .getDirectoryHandle(projectId+".lmdj")).getDirectoryHandle("assets");
        const file=await (await assets.getFileHandle(artifact.sha256+".wav")).getFile();
        const prefix=new Uint8Array(await file.slice(0,56).arrayBuffer());
        const sha256=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",await file.arrayBuffer())),
          value=>value.toString(16).padStart(2,"0")).join("");
        const view=new DataView(prefix.buffer);
        const physical={sha256,byteLength:file.size,prefix:Array.from(prefix),
          tail:Array.from(new Uint8Array(await file.slice(-4).arrayBuffer())),
          sampleRate:view.getUint32(24,true),channels:view.getUint16(22,true),
          sourceFrames:view.getUint32(52,true)/view.getUint16(32,true)};
        // Independent browser Crypto oracle for the complete canonical
        // inventory, using actual OPFS bytes rather than Core's hash helper.
        const inventory=[];
        const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)),
          value=>value.toString(16).padStart(2,"0")).join("");
        const walk=async (directory,parent="")=>{
          for await(const [name,entry] of directory.entries()) {
            const path=parent+name;
            if(entry.kind==="directory")await walk(entry,path+"/");
            else {
              const file=await entry.getFile();
              inventory.push({path,bytes:file.size,sha256:path===`assets/${artifact.sha256}.wav`
                ?physical.sha256:await digest(await file.arrayBuffer())});
            }
          }
        };
        const directory=await (await root.getDirectoryHandle("projects")).getDirectoryHandle(projectId+".lmdj");
        await walk(directory);
        // All fixture paths are ASCII, whose ordering is unsigned UTF-8 byte
        // ordering. Native canonical-path tests retain the non-ASCII cases.
        inventory.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
        let total=0;
        const entries=inventory.map(entry=>{const offset=total;total+=entry.bytes;return {...entry,offset};});
        const canonical=value=>Array.isArray(value)?value.map(canonical):value!==null&&typeof value==="object"
          ?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
        const index={compression:"none",contract:"lmdj.project-bundle.v1",contract_version:bundleContractVersion,
          entries,project_contract:project.project.contract,project_id:projectId,uncompressed_bytes:total};
        const inventoryDigest=await digest(new TextEncoder().encode(JSON.stringify(canonical(index))));
        if(phase==="prepare")await send("audio.suspend",{});
        const closed=await send("host.close",{});
        return {admitted,startupListed,inspected,metadata,physical,listed,inventory:{entries,total,digest:inventoryDigest},
          closed,memoryBytes:window.Module.wasmMemory.buffer.byteLength};
      },{admission,phase,projectId,patternId,performanceId,revision,artifact,bundleContractVersion,
        header:Array.from(Buffer.from(headerHex,"hex"))});
      if(phase==="prepare")expect(report.admitted.receipt.project_revision).toBe(revision);
      else expect(report.admitted).toBeNull();
      if(phase==="prepare") expect(report.startupListed).toBeNull();
      else expect(report.startupListed.projects.find(value=>value.project_id===projectId)).toEqual({
        project_id:projectId,pattern_id:patternId,revision,bpm:120,asset_count:0,assigned_pad_count:0,
        bundle_digest:expect.stringMatching(/^[0-9a-f]{64}$/),
      });
      expect(report.inspected).toEqual({performance:{id:performanceId,name:"thirty minutes",created_bpm:120,
        recording_artifact:artifact,events:[]},project_revision:revision});
      expect(report.metadata).toEqual({project_id:projectId,performance_id:performanceId,
        project_revision:revision,recording_revision:0,recording_artifact:artifact,
        audio_metadata:{sample_rate:48000,channels:2,source_frames:86400000},audio_error:null});
      expect(report.physical).toEqual({sha256:artifact.sha256,byteLength:345600056,
        prefix:Array.from(Buffer.from(headerHex,"hex")),tail:[0,0,0,0],
        sampleRate:48000,channels:2,sourceFrames:86400000});
      expect(report.listed.projects.find(value=>value.project_id===projectId)).toEqual({
        project_id:projectId,pattern_id:patternId,revision,bpm:120,asset_count:0,assigned_pad_count:0,
        bundle_digest:report.inventory.digest});
      expect(report.inventory.total).toBeGreaterThan(345600056);
      expect(report.closed.state).toBe("closed");expect(report.memoryBytes).toBe(536870912);
      expect(errors,"production Wasm must not trap while verifying long recordings").toEqual([]);
      reports.push({phase,...report});await page.close();expect(page.isClosed()).toBe(true);
    }
    journeys.push({admission,projectId,patternId,performanceId,artifact,reports,closedPages:3});
  }
  const evidencePath=testInfo.outputPath("thirty-minute-recording-save-bind-reopens.json");
  await (await import("node:fs/promises")).writeFile(evidencePath,JSON.stringify({journeys},null,2),{flag:"wx"});
  await testInfo.attach("thirty-minute-recording-save-bind-reopens",{path:evidencePath,contentType:"application/json"});
});

opfsTest("busy local Projects remain discoverable without taking foreign writer ownership", async ({context}, testInfo) => {
  const schema=JSON.parse(await (await import("node:fs/promises")).readFile(
    new URL("../../../../contracts/project/lmdj.project-bundle.v1.schema.json",import.meta.url),"utf8"));
  const busyId=crypto.randomUUID(),busyPattern=crypto.randomUUID();
  const freeId=crypto.randomUUID(),freePattern=crypto.randomUUID();
  const busy=await context.newPage(),free=await context.newPage(),reader=await context.newPage();
  const send=(page,operation,payload)=>page.evaluate(async ({operation,payload})=>
    window.lmdjWebRuntimeHost.transport.send({protocol_version:1,request_id:crypto.randomUUID(),operation,payload}),
    {operation,payload});
  await waitForFormalHost(reader);
  // Supported WebKit retains this run's earlier OPFS fixtures across contexts.
  // Enumerate the physical pre-existing inventory independently of project.list.
  const existingIds=await reader.evaluate(async ()=>{
    const root=await navigator.storage.getDirectory();
    const projects=await root.getDirectoryHandle("projects",{create:true});
    const ids=[];
    for await(const [name,entry] of projects.entries())
      if(entry.kind==="directory"&&name.endsWith(".lmdj"))ids.push(name.slice(0,-5));
    return ids.sort();
  });
  const seed=async (page,projectId,patternId,bpm)=>{
    await waitForFormalHost(page);
    const result=await send(page,"project.create",{project_id:projectId,bpm,
      initial_pattern:{pattern_id:patternId,bars:1,events:[]}});
    expect(result.ok).toBe(true);expect(result.result.project_revision).toBe(0);
    const inspected=await send(page,"project.inspect",{});expect(inspected.ok).toBe(true);
    return inspected.result.project.contract;
  };
  const busyContract=await seed(busy,busyId,busyPattern,120);
  const freeContract=await seed(free,freeId,freePattern,126);
  expect((await send(free,"host.close",{})).result.state).toBe("closed");
  await free.close();expect(free.isClosed()).toBe(true);
  const observed=await reader.evaluate(async ({projects,version})=>{
    const response=await window.lmdjWebRuntimeHost.transport.send({protocol_version:1,
      request_id:crypto.randomUUID(),operation:"project.list",payload:{}});
    const root=await navigator.storage.getDirectory(),digests={};
    const hash=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)),
      value=>value.toString(16).padStart(2,"0")).join("");
    const canonical=value=>Array.isArray(value)?value.map(canonical):value!==null&&typeof value==="object"
      ?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
    for(const project of projects) {
      const directory=await (await root.getDirectoryHandle("projects")).getDirectoryHandle(project.id+".lmdj");
      const entries=[];
      const walk=async (folder,parent="")=>{
        for await(const [name,entry] of folder.entries()) {
          const path=parent+name;
          if(entry.kind==="directory")await walk(entry,path+"/");
          else {const file=await entry.getFile();entries.push({path,bytes:file.size,sha256:await hash(await file.arrayBuffer())});}
        }
      };
      await walk(directory);entries.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
      let total=0;const indexed=entries.map(entry=>{const offset=total;total+=entry.bytes;return {...entry,offset};});
      const index={compression:"none",contract:"lmdj.project-bundle.v1",contract_version:version,
        entries:indexed,project_contract:project.contract,project_id:project.id,uncompressed_bytes:total};
      digests[project.id]=await hash(new TextEncoder().encode(JSON.stringify(canonical(index))));
    }
    return {response,digests};
  },{projects:[{id:busyId,contract:busyContract},{id:freeId,contract:freeContract}],version:schema["x-lmdj-contract-version"]});
  expect(observed.response.ok).toBe(true);
  expect(observed.response.result.projects.map(value=>value.project_id).sort()).toEqual(
    [...existingIds,busyId,freeId].sort());
  for(const [projectId,patternId,bpm] of [[busyId,busyPattern,120],[freeId,freePattern,126]])
    expect(observed.response.result.projects.find(value=>value.project_id===projectId)).toEqual({
      project_id:projectId,pattern_id:patternId,revision:0,bpm,asset_count:0,assigned_pad_count:0,
      bundle_digest:observed.digests[projectId]});
  const opened=await send(reader,"project.open",{project_id:freeId,pattern_id:freePattern});
  expect(opened.ok).toBe(true);
  const refused=await send(reader,"project.open",{project_id:busyId,pattern_id:busyPattern});
  expect(refused.ok).toBe(false);expect(refused.error).toEqual({
    code:"PROJECT_BUSY",details:{},message:"project is already open for writing"});
  const kept=await send(reader,"project.inspect",{});expect(kept.ok).toBe(true);
  expect(kept.result.project.project_id).toBe(freeId);
  const owner=await send(busy,"project.inspect",{});expect(owner.ok).toBe(true);
  expect(owner.result.project.project_id).toBe(busyId);
  expect((await send(reader,"host.close",{})).result.state).toBe("closed");
  expect((await send(busy,"host.close",{})).result.state).toBe("closed");
  await reader.close();await busy.close();expect(reader.isClosed()).toBe(true);expect(busy.isClosed()).toBe(true);
  const path=testInfo.outputPath("busy-project-discovery.json");
  await (await import("node:fs/promises")).writeFile(path,JSON.stringify({existingIds,busyId,freeId,observed,opened,refused,kept,owner,closedPages:3},null,2),{flag:"wx"});
  await testInfo.attach("busy-project-discovery",{path,contentType:"application/json"});
});

// The formal conformance Wasm has no application shell. Load the actual source
// SDK with a current derived source-shell digest; default verification, capability
// probe, native transport, gesture activation and physical cleanup remain real.
async function bootTempoSdk(page) {
  const webRoot = new URL("../../../../packages/web-runtime-platform/web/", import.meta.url);
  const modules = new Map(await Promise.all((await readdir(webRoot))
    .filter(name => name.endsWith(".mjs"))
    .map(async name => [name, await readFile(new URL(name, webRoot))])));
  await page.route("**/tempo-preview-sdk/*.mjs", async route => {
    const name = new URL(route.request().url()).pathname.split("/").at(-1);
    const body = modules.get(name);
    await route.fulfill({status: body ? 200 : 404, contentType: "text/javascript", body: body ?? ""});
  });
  const digest = createHash("sha256").update(JSON.stringify({
    product_build: WEB_RUNTIME_IDENTITY.product_build,
    host_version: WEB_RUNTIME_IDENTITY.hosts["web-runtime-host"].version,
    protocol_version: WEB_RUNTIME_IDENTITY.protocol_version, runtime_script: "source-shell",
  })).digest("hex");
  await waitForFormalHost(page);
  return page.evaluate(async ({identity, digest}) => {
    const {createRuntimeSession} = await import("/tempo-preview-sdk/runtime_session.mjs");
    const {createUserGestureToken} = await import("/tempo-preview-sdk/input_adapters.mjs");
    const meta = document.createElement("meta");
    meta.name = "lmdj-host-manifest-sha256"; meta.content = digest; document.head.append(meta);
    const host = identity.hosts["web-runtime-host"];
    const session = createRuntimeSession({document, window, navigator, crypto,
      inputOwnership: "host", patternTransport: true,
      assemblyIdentity: {distributionContract: host.distribution_contract, hostId: host.id,
        hostVersion: host.version, platformVersion: identity.platform.version,
        productBuild: identity.product_build, protocolVersion: identity.protocol_version},
      manifestSource: {heapBytes: identity.heap_bytes, resourceLimits: identity.resource_limits,
        emscripten: identity.emscripten, expectedAssets: host.expected_assets},
    });
    window.__lmdjTempoSession = session;
    window.__lmdjTempoTickets = [];
    if (!await session.start()) throw new Error(JSON.stringify(session.diagnostics()));
    const button = document.createElement("button"); button.id = "tempo-activate-audio";
    button.textContent = "Activate actual tempo audio";
    button.addEventListener("click", async event => {
      try { window.__lmdjTempoActivation = await session.activateAudio(createUserGestureToken(event)); }
      catch (error) { window.__lmdjTempoActivation = {error: String(error)}; }
    }, {once: true});
    document.body.append(button);
    return {frozen: Object.isFrozen(session), sameSession: window.lmdjWebRuntimeHost.session === session,
      methods: Object.keys(window.lmdjWebRuntimeHost.patternTransport).filter(name => name.includes("Tempo"))};
  }, {identity: WEB_RUNTIME_IDENTITY, digest});
}

async function activateTempoSdk(page) {
  await page.locator("#tempo-activate-audio").click();
  await page.waitForFunction(() => window.__lmdjTempoActivation !== undefined);
  expect(await page.evaluate(() => window.__lmdjTempoActivation)).toBe(true);
}

async function tempoSnapshot(page, projectId) {
  return page.evaluate(async projectId => {
    const session = window.__lmdjTempoSession;
    const view = await session.inspectProject();
    const history = await session.inspectAuthoringHistory();
    const root = await navigator.storage.getDirectory();
    const bundle = await (await root.getDirectoryHandle("projects")).getDirectoryHandle(`${projectId}.lmdj`);
    const json = async (directory, name) => JSON.parse(await (await (await directory.getFileHandle(name)).getFile()).text());
    const manifest = await json(bundle, "manifest.json");
    const checkpoints = await (await bundle.getDirectoryHandle("history")).getDirectoryHandle("checkpoints");
    const checkpoint = await json(checkpoints, `${manifest.head_revision}.json`);
    const assets = await bundle.getDirectoryHandle("assets");
    const artifacts = [];
    for await (const [name, handle] of assets.entries()) {
      if (handle.kind !== "file") throw new Error("unexpected non-file Artifact");
      const bytes = new Uint8Array(await (await handle.getFile()).arrayBuffer());
      const sha256 = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
        .map(value => value.toString(16).padStart(2, "0")).join("");
      artifacts.push({name, sha256, byteLength: bytes.length, bytes: [...bytes]});
    }
    artifacts.sort((a, b) => a.name.localeCompare(b.name));
    return {view, history, manifest, checkpoint, artifacts};
  }, projectId);
}

async function tempoStatus(page, turn) {
  return page.evaluate(turn => window.__lmdjTempoSession
    .inspectPatternTempoPreview(window.__lmdjTempoTickets[turn]), turn);
}

async function waitTempoPhase(page, turn, phase) {
  let value;
  await expect.poll(async () => {
    value = await tempoStatus(page, turn); return value.phase;
  }, {timeout: 5_000}).toBe(phase);
  return value;
}

function assertTempoContinuity(previous, actual) {
  expect(actual.startEpoch).toBe(previous.startEpoch);
  expect(BigInt(actual.anchor.tickNumerator)).toBe(BigInt(previous.anchor.tickNumerator) +
    (BigInt(actual.anchor.frame) - BigInt(previous.anchor.frame)) * BigInt(previous.anchor.bpm) * 960n);
}

async function observeTempoQuarters(page, status, offset, count = 2, afterFrame = status.applied.appliedFrame) {
  const frames = nextTempoQuarterFrames(status.applied.anchor, count, afterFrame)
    .map(frame => Number(frame + offset + 1n));
  expect(frames.every(Number.isSafeInteger)).toBe(true);
  const observation = await page.evaluate(frame => window.__lmdjTempoOnsetProbe.readThrough(frame), frames.at(-1) + 256);
  expect(observation.onsets.filter(frame => frame >= frames[0] && frame <= frames.at(-1))).toEqual(frames);
  return {frames, observation};
}

for (const sourceAdoption of [false, true]) {
  opfsTest(`actual SDK tempo Worklet preview/cancel/save ${sourceAdoption ? "adopts a settings-only revision and cold reopens saved Truth" : "keeps one Undo and cold reopens restored Truth"}`, async ({page, context}, testInfo) => {
    opfsTest.setTimeout(120_000);
    const evidence = {sourceAdoption, browser: context.browser()?.version() ?? null, legs: []};
    const sdk = await bootTempoSdk(page);
    evidence.userAgent = await page.evaluate(() => navigator.userAgent);
    expect(sdk).toEqual({frozen: true, sameSession: true, methods: [
      "beginPatternTempoPreview", "setPatternTempoPreview", "cancelPatternTempoPreview",
      "commitPatternTempoPreview", "inspectPatternTempoPreview",
    ]});
    const setup = await page.evaluate(async sourceAdoption => {
      const session = window.__lmdjTempoSession;
      const projectId = crypto.randomUUID(), patternId = crypto.randomUUID(), sessionId = crypto.randomUUID();
      await session.createProject({projectId, patternId, bpm: 120, bars: 1});
      const bytes = new Uint8Array(1004), view = new DataView(bytes.buffer);
      const text = (at, value) => { for (let n = 0; n < value.length; ++n) bytes[at + n] = value.charCodeAt(n); };
      text(0, "RIFF"); view.setUint32(4, 996, true); text(8, "WAVEfmt "); view.setUint32(16, 16, true);
      view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, 48_000, true);
      view.setUint32(28, 96_000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
      text(36, "data"); view.setUint32(40, 960, true);
      for (let n = 0; n < 480; ++n) view.setInt16(44 + n * 2, 10_000, true);
      const imported = await session.importAssignSample(new File([bytes], "tempo.wav", {type: "audio/wav"}),
        {slot: 0, expectedRevision: 0});
      const edited = await session.editPatternEvents({patternId, expectedRevision: 1, remove: [],
        put: [0, 960, 1920, 2880].map(onsetTick => ({slot: 0, onsetTick, durationTick: 1, velocity: 127}))});
      await session.reloadSnapshot(patternId);
      return {projectId, patternId, sessionId, imported, edited, originalBytes: [...bytes], revision: 2};
    }, sourceAdoption);
    let baseline = await tempoSnapshot(page, setup.projectId);
    expect(baseline.view.project_revision).toBe(setup.revision);
    expect(baseline.artifacts).toEqual([{name: "9545d7cb33070fd89c29147fb1ae68f58e098a9c4f14b83800f90739b9d364f8.wav",
      sha256: "9545d7cb33070fd89c29147fb1ae68f58e098a9c4f14b83800f90739b9d364f8", byteLength: 1004, bytes: setup.originalBytes}]);
    await activateTempoSdk(page);
    await attachTempoOnsetProbe(page);
    const read = frame => page.evaluate(frame => window.__lmdjTempoOnsetProbe.readThrough(frame), frame);
    const begin = () => page.evaluate(async ({projectId, patternId, revision}) => {
      const state = await window.__lmdjTempoSession.beginPatternTempoPreview({projectId, patternId, expectedRevision: revision});
      window.__lmdjTempoTickets.push(state.ticket); return state;
    }, setup);
    const set = (turn, bpm) => page.evaluate(({turn, bpm}) => window.__lmdjTempoSession
      .setPatternTempoPreview({ticket: window.__lmdjTempoTickets[turn], bpm}), {turn, bpm});
    const cancel = turn => page.evaluate(turn => window.__lmdjTempoSession
      .cancelPatternTempoPreview(window.__lmdjTempoTickets[turn]), turn);
    const checkUnchanged = async leg => {
      const actual = await tempoSnapshot(page, setup.projectId);
      const expected = structuredClone(baseline);
      // Host's existing playing interlock takes precedence over Facade's
      // preview interlock. The complete history and its counts stay checked.
      Object.assign(expected.history, {disabledReason: "pattern_transport_busy", canUndo: false, canRedo: false});
      expect(actual).toEqual(expected); evidence.legs.push({leg, snapshot: actual});
    };
    let closed = false;
    try {
      expect((await read(0)).onsets).toEqual([]);
      await page.evaluate(async setup => {
        await window.__lmdjTempoSession.requestPatternTransport({sessionId: setup.sessionId, projectId: setup.projectId,
          commandId: crypto.randomUUID(), expectedEpoch: 1, intent: "play_stop", expectedRevision: setup.revision});
      }, setup);
      let playing;
      await expect.poll(async () => {
        playing = await page.evaluate(id => window.__lmdjTempoSession.inspectPatternTransport(id), setup.sessionId);
        return playing.playing && playing.phase === "idle";
      }).toBe(true);
      if (sourceAdoption) {
        const settings = await page.evaluate(() => window.__lmdjTempoSession.updateSequenceSettings({
          expectedRevision: 2, sessionId: null, bpm: null, quantizeEnabled: false, swingPercent: null}));
        expect(settings.projectRevision).toBe(3); setup.revision = 3;
        const expectedSettings = structuredClone(baseline);
        expectedSettings.view.project.revision = 3; expectedSettings.view.project_revision = 3;
        expectedSettings.view.project.sequence_settings.quantize_enabled = false;
        expectedSettings.checkpoint.revision = 3; expectedSettings.checkpoint.sequence_settings.quantize_enabled = false;
        expectedSettings.manifest.head_revision = 3; expectedSettings.manifest.head_checkpoint = "history/checkpoints/3.json";
        expectedSettings.manifest.transactions.push(expect.stringMatching(
          /^history\/transactions\/3-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\.json$/));
        Object.assign(expectedSettings.history, {projectRevision: 3, undoCount: baseline.history.undoCount + 1,
          undoLabel: "Edit Sequence settings", disabledReason: "pattern_transport_busy", canUndo: false, canRedo: false});
        baseline = await tempoSnapshot(page, setup.projectId);
        expect(baseline).toEqual(expectedSettings);
        evidence.settingsOnly = settings;
      }
      const ready = await begin();
      expect(ready.phase).toBe("ready"); expect(ready.previewId).toBe("0");
      expect(ready.applied.anchor).toEqual({frame: String(playing.originFrame), tickNumerator: "0", bpm: 120});
      expect(ready.sourceRevision).toBe(2);
      let first;
      await expect.poll(async () => { first = await read(0); return first.onsets.length; }, {timeout: 5_000}).toBeGreaterThan(0);
      const offset = BigInt(first.onsets[0]) - BigInt(playing.originFrame) - 1n;
      const second = first.onsets[0] + 24_000;
      expect((await read(second + 256)).onsets.filter(frame => frame <= second)).toEqual([first.onsets[0], second]);
      evidence.start = {playing, ready, contextCoreOffset: String(offset), first, second};
      await checkUnchanged("ready and two baseline onsets");

      const initial = await set(0, 137);
      const preview = await waitTempoPhase(page, 0, "previewing");
      expect(preview.applied.anchor.bpm).toBe(137); assertTempoContinuity(ready.applied, preview.applied);
      expect(BigInt(preview.applied.patternGeneration)).toBe(BigInt(ready.ticket.sourceId) + (sourceAdoption ? 2n : 1n));
      expect(preview.sourceRevision).toBe(setup.revision);
      evidence.preview = {initial, actual: preview, pcm: await observeTempoQuarters(page, preview, offset)};
      await checkUnchanged("actual 137 BPM preview");

      await cancel(0);
      const cancelled = await waitTempoPhase(page, 0, "cancelled");
      expect(cancelled.applied.anchor.bpm).toBe(120); assertTempoContinuity(preview.applied, cancelled.applied);
      evidence.cancelled = {actual: cancelled, pcm: await observeTempoQuarters(page, cancelled, offset)};
      await checkUnchanged("actual cancellation");
      const secondReady = await begin(); expect(secondReady.ticket.previewToken).not.toBe(ready.ticket.previewToken);
      await set(1, 240);
      const secondPreview = await waitTempoPhase(page, 1, "previewing");
      assertTempoContinuity(cancelled.applied, secondPreview.applied);
      const secondPcm = await observeTempoQuarters(page, secondPreview, offset);
      await checkUnchanged("second actual preview");
      const stale = await page.evaluate(async () => {
        try { await window.__lmdjTempoSession.setPatternTempoPreview({ticket: window.__lmdjTempoTickets[0], bpm: 180}); return "accepted"; }
        catch (error) { return error.code; }
      });
      expect(stale).toBe("HOST_STATE_INVALID"); await checkUnchanged("old ticket refused");

      const committed = await page.evaluate(async () => {
        window.__lmdjTempoSaveCommand = crypto.randomUUID();
        return window.__lmdjTempoSession.commitPatternTempoPreview({ticket: window.__lmdjTempoTickets[1],
          commandId: window.__lmdjTempoSaveCommand});
      });
      expect(committed.committedRevision).toBe(setup.revision + 1);
      const saved = await waitTempoPhase(page, 1, "committed");
      assertTempoContinuity(secondPreview.applied, saved.applied);
      expect(saved.applied.anchor.bpm).toBe(240); expect(saved.sourceRevision).toBe(setup.revision + 1);
      const saveContextFrame = BigInt(saved.applied.appliedFrame) + offset;
      expect(saveContextFrame).toBeGreaterThan(BigInt(secondPcm.frames.at(-1)));
      const postSaveFrames = nextTempoQuarterFrames(saved.applied.anchor, 2, saved.applied.appliedFrame)
        .map(frame => Number(frame + offset + 1n));
      expect(BigInt(postSaveFrames[0])).toBeGreaterThan(saveContextFrame);
      const last = postSaveFrames.at(-1);
      const continued = await read(last + 256);
      const firstSavedRange = secondPcm.frames[0];
      const expectedSavedOnsets = [];
      for (let frame = firstSavedRange; frame <= last; frame += 12_000) expectedSavedOnsets.push(frame);
      expect(continued.onsets.filter(frame => frame >= firstSavedRange && frame <= last)).toEqual(expectedSavedOnsets);
      const expectedSaved = structuredClone(baseline);
      expectedSaved.view.project.bpm = 240; expectedSaved.view.project.revision = setup.revision + 1;
      expectedSaved.view.project_revision = setup.revision + 1;
      expectedSaved.checkpoint.bpm = 240; expectedSaved.checkpoint.revision = setup.revision + 1;
      expectedSaved.manifest.head_revision = setup.revision + 1;
      expectedSaved.manifest.head_checkpoint = `history/checkpoints/${setup.revision + 1}.json`;
      expectedSaved.manifest.transactions.push(`history/transactions/${setup.revision + 1}-${committed.commandId}.json`);
      Object.assign(expectedSaved.history, {projectRevision: setup.revision + 1, undoCount: baseline.history.undoCount + 1,
        redoCount: 0, undoLabel: "Edit Sequence settings", redoLabel: "", disabledReason: "pattern_transport_busy", canUndo: false, canRedo: false});
      expect(await tempoSnapshot(page, setup.projectId)).toEqual(expectedSaved);
      const retried = await page.evaluate(() => window.__lmdjTempoSession.commitPatternTempoPreview({
        ticket: window.__lmdjTempoTickets[1], commandId: window.__lmdjTempoSaveCommand}));
      expect(retried.committedRevision).toBe(setup.revision + 1);
      expect(await tempoSnapshot(page, setup.projectId)).toEqual(expectedSaved);
      evidence.saved = {committed, saved, retried, continued, expectedSavedOnsets, postSaveFrames,
        saveContextFrame: String(saveContextFrame), snapshot: expectedSaved};

      await page.evaluate(async setup => {
        const session = window.__lmdjTempoSession, current = await session.inspectPatternTransport(setup.sessionId);
        await session.requestPatternTransport({sessionId: setup.sessionId, projectId: setup.projectId,
          commandId: crypto.randomUUID(), expectedEpoch: current.transportEpoch + 1, intent: "play_stop", expectedRevision: setup.revision + 1});
      }, setup);
      let stopped;
      await expect.poll(async () => {
        stopped = await page.evaluate(id => window.__lmdjTempoSession.inspectPatternTransport(id), setup.sessionId);
        return !stopped.playing && stopped.phase === "idle";
      }).toBe(true);
      const silentFrom = Number(BigInt(stopped.runtimeFrame) + offset + 480n);
      expect((await read(silentFrom + 24_000)).onsets.filter(frame => frame >= silentFrom)).toEqual([]);
      const expectedStopped = structuredClone(expectedSaved);
      Object.assign(expectedStopped.history, {disabledReason: "", canUndo: true});
      expect(await tempoSnapshot(page, setup.projectId)).toEqual(expectedStopped);
      let expectedFinal = expectedStopped;
      if (!sourceAdoption) {
        const undoCommand = await page.evaluate(() => crypto.randomUUID());
        await page.evaluate(request => window.__lmdjTempoSession.undoAuthoring(request),
          {sessionId: baseline.history.sessionId, commandId: undoCommand, expectedRevision: setup.revision + 1});
        expectedFinal = structuredClone(baseline);
        expectedFinal.view.project.revision = setup.revision + 2; expectedFinal.view.project_revision = setup.revision + 2;
        expectedFinal.checkpoint.revision = setup.revision + 2; expectedFinal.manifest.head_revision = setup.revision + 2;
        expectedFinal.manifest.head_checkpoint = `history/checkpoints/${setup.revision + 2}.json`;
        expectedFinal.manifest.transactions.push(`history/transactions/${setup.revision + 1}-${committed.commandId}.json`,
          `history/transactions/${setup.revision + 2}-${undoCommand}.json`);
        Object.assign(expectedFinal.history, {projectRevision: setup.revision + 2, redoCount: 1,
          redoLabel: "Edit Sequence settings", canRedo: true});
        expect(await tempoSnapshot(page, setup.projectId)).toEqual(expectedFinal);
      }
      evidence.final = {stopped, snapshot: expectedFinal};
      await page.evaluate(() => window.__lmdjTempoOnsetProbe.close());
      await page.evaluate(() => window.__lmdjTempoSession.close());
      expect(await page.evaluate(() => window.lmdjWebRuntimeHost.transport.terminalOwnerReleased)).toBe(true);
      await page.close(); closed = true;
      const reopened = await context.newPage();
      try {
        await bootTempoSdk(reopened);
        await reopened.evaluate(async setup => {
          await window.__lmdjTempoSession.openProject(setup.projectId, setup.patternId);
        }, setup);
        const cold = await tempoSnapshot(reopened, setup.projectId);
        const {history: _oldHistory, ...persisted} = expectedFinal;
        const {history, ...actualPersisted} = cold;
        expect(actualPersisted).toEqual(persisted);
        expect(history).toEqual({sessionId: expect.stringMatching(/^[a-f0-9-]{36}$/),
          projectRevision: expectedFinal.view.project_revision, undoCount: 0, redoCount: 0,
          undoLabel: "", redoLabel: "", disabledReason: "", canUndo: false, canRedo: false});
        expect(history.sessionId).not.toBe(baseline.history.sessionId);
        evidence.coldReopen = cold;
        // Persisted Truth alone cannot prove that a fresh runtime schedules
        // it. Start the new real Worklet and hear the restored/saved tempo.
        await reopened.evaluate(id => window.__lmdjTempoSession.reloadSnapshot(id), setup.patternId);
        await activateTempoSdk(reopened); await attachTempoOnsetProbe(reopened);
        expect((await reopened.evaluate(() => window.__lmdjTempoOnsetProbe.readThrough(0))).onsets).toEqual([]);
        const coldSessionId = await reopened.evaluate(() => crypto.randomUUID());
        await reopened.evaluate(async ({setup, sessionId, revision}) => {
          await window.__lmdjTempoSession.requestPatternTransport({sessionId, projectId: setup.projectId,
            commandId: crypto.randomUUID(), expectedEpoch: 1, intent: "play_stop", expectedRevision: revision});
        }, {setup, sessionId: coldSessionId, revision: expectedFinal.view.project_revision});
        await expect.poll(() => reopened.evaluate(async id => {
          const state = await window.__lmdjTempoSession.inspectPatternTransport(id);
          return state.playing && state.phase === "idle";
        }, coldSessionId)).toBe(true);
        const coldReady = await reopened.evaluate(async ({projectId, patternId, revision}) =>
          window.__lmdjTempoSession.beginPatternTempoPreview({projectId, patternId, expectedRevision: revision}),
        {...setup, revision: expectedFinal.view.project_revision});
        expect(coldReady).toMatchObject({phase: "ready", previewId: "0", commandId: null, committedRevision: null,
          committedBpm: expectedFinal.view.project.bpm, sourceRevision: expectedFinal.view.project_revision});
        expect(coldReady.applied.anchor.bpm).toBe(expectedFinal.view.project.bpm);
        let coldPcm;
        await expect.poll(async () => {
          coldPcm = await reopened.evaluate(() => window.__lmdjTempoOnsetProbe.readThrough(0));
          return coldPcm.onsets.length;
        }, {timeout: 5_000}).toBeGreaterThan(0);
        const coldFirst = coldPcm.onsets[0];
        const coldSecond = coldFirst + (expectedFinal.view.project.bpm === 240 ? 12_000 : 24_000);
        coldPcm = await reopened.evaluate(frame => window.__lmdjTempoOnsetProbe.readThrough(frame), coldSecond + 256);
        expect(coldPcm.onsets.filter(frame => frame <= coldSecond)).toEqual([coldFirst, coldSecond]);
        const expectedColdPlaying = structuredClone(cold);
        Object.assign(expectedColdPlaying.history, {disabledReason: "pattern_transport_busy", canUndo: false, canRedo: false});
        expect(await tempoSnapshot(reopened, setup.projectId)).toEqual(expectedColdPlaying);
        evidence.coldAudio = {ready: coldReady, pcm: coldPcm};
        await reopened.evaluate(() => window.__lmdjTempoOnsetProbe.close());
        await reopened.evaluate(() => window.__lmdjTempoSession.close());
        expect(await reopened.evaluate(() => window.lmdjWebRuntimeHost.transport.terminalOwnerReleased)).toBe(true);
      } finally { await reopened.close(); }
    } finally {
      if (!closed && !page.isClosed()) {
        await page.evaluate(() => window.__lmdjTempoOnsetProbe?.close()).catch(() => {});
        await page.evaluate(() => window.__lmdjTempoSession?.close()).catch(() => {});
      }
      const path = testInfo.outputPath("actual-tempo-worklet-journey.json");
      await writeFile(path, JSON.stringify(evidence, null, 2));
      await testInfo.attach("actual-tempo-worklet-journey", {path, contentType: "application/json"});
    }
  });
}

async function playResumedTempoSdk(page, setup, revision, bpm) {
  const admission = await page.evaluate(async ({projectId, revision}) => {
    const session = window.__lmdjTempoSession, sessionId = crypto.randomUUID();
    const before = await session.inspectPatternTransport(sessionId);
    const afterFrame = Math.ceil(session.monitorDestination().context.currentTime * 48000);
    await session.requestPatternTransport({sessionId, projectId, commandId: crypto.randomUUID(),
      expectedEpoch: before.transportEpoch + 1, intent: "play_stop", expectedRevision: revision});
    return {sessionId, afterFrame};
  }, {projectId: setup.projectId, revision});
  let status;
  await expect.poll(async () => {
    status = await page.evaluate(id => window.__lmdjTempoSession.inspectPatternTransport(id), admission.sessionId);
    return status.playing && status.phase === "idle";
  }, {timeout: 5_000}).toBe(true);
  let pcm, onsets;
  await expect.poll(async () => {
    pcm = await page.evaluate(() => window.__lmdjTempoOnsetProbe.readThrough(0));
    onsets = pcm.onsets.filter(frame => frame >= admission.afterFrame);
    return onsets.length;
  }, {timeout: 5_000}).toBeGreaterThanOrEqual(2);
  expect(onsets[1] - onsets[0]).toBe(Math.ceil(2880000 / bpm));
  return {...admission, status, pcm, offset: String(BigInt(onsets[0]) - BigInt(status.originFrame) - 1n)};
}

for (const savedBeforeSuspend of [false, true]) {
  opfsTest(`actual SDK tempo ${savedBeforeSuspend ? "saved" : "cancelled"} receipt survives Suspend and same-Session resumed PCM`, async ({page, context}, testInfo) => {
    opfsTest.setTimeout(120_000);
    const evidence = {savedBeforeSuspend, legs: []}; let reopened = null;
    try {
      await bootTempoSdk(page);
      const setup = await page.evaluate(async () => {
        const session = window.__lmdjTempoSession;
        const projectId = crypto.randomUUID(), patternId = crypto.randomUUID();
        await session.createProject({projectId, patternId, bpm: 120, bars: 1});
        const bytes = new Uint8Array(1004), wav = new DataView(bytes.buffer);
        const text = (at, value) => {for (let n = 0; n < value.length; ++n) bytes[at + n] = value.charCodeAt(n);};
        text(0, "RIFF"); wav.setUint32(4, 996, true); text(8, "WAVEfmt "); wav.setUint32(16, 16, true);
        wav.setUint16(20, 1, true); wav.setUint16(22, 1, true); wav.setUint32(24, 48000, true);
        wav.setUint32(28, 96000, true); wav.setUint16(32, 2, true); wav.setUint16(34, 16, true);
        text(36, "data"); wav.setUint32(40, 960, true);
        for (let n = 0; n < 480; ++n) wav.setInt16(44 + n * 2, 10000, true);
        await session.importAssignSample(new File([bytes], "resume-tempo.wav", {type: "audio/wav"}),
          {slot: 0, expectedRevision: 0});
        await session.editPatternEvents({patternId, expectedRevision: 1, remove: [],
          put: [0, 960, 1920, 2880].map(onsetTick => ({slot: 0, onsetTick, durationTick: 1, velocity: 127}))});
        await session.reloadSnapshot(patternId);
        return {projectId, patternId, bytes: [...bytes]};
      });
      const baseline = await tempoSnapshot(page, setup.projectId);
      expect(baseline.artifacts).toEqual([{name: "9545d7cb33070fd89c29147fb1ae68f58e098a9c4f14b83800f90739b9d364f8.wav",
        sha256: "9545d7cb33070fd89c29147fb1ae68f58e098a9c4f14b83800f90739b9d364f8", byteLength: 1004, bytes: setup.bytes}]);
      await activateTempoSdk(page); await attachTempoOnsetProbe(page);
      const playing = await playResumedTempoSdk(page, setup, 2, 120);
      const first = await page.evaluate(async setup => {
        const session = window.__lmdjTempoSession;
        const ready = await session.beginPatternTempoPreview({...setup, expectedRevision: 2});
        window.__lmdjTempoTickets.push(ready.ticket);
        await session.setPatternTempoPreview({ticket: ready.ticket, bpm: 240});
        return ready;
      }, {projectId: setup.projectId, patternId: setup.patternId});
      const actual = await waitTempoPhase(page, 0, "previewing");
      evidence.legs.push({leg: "actual pre-Suspend preview", first, actual,
        pcm: await observeTempoQuarters(page, actual, BigInt(playing.offset))});
      let save = null;
      const expected = structuredClone(baseline);
      if (savedBeforeSuspend) {
        save = await page.evaluate(async () => {
          const session = window.__lmdjTempoSession;
          window.__lmdjTempoSaveCommand = crypto.randomUUID();
          return session.commitPatternTempoPreview({ticket: window.__lmdjTempoTickets[0], commandId: window.__lmdjTempoSaveCommand});
        });
        await waitTempoPhase(page, 0, "committed");
        expected.view.project.bpm = 240; expected.view.project.revision = 3; expected.view.project_revision = 3;
        expected.checkpoint.bpm = 240; expected.checkpoint.revision = 3;
        expected.manifest.head_revision = 3; expected.manifest.head_checkpoint = "history/checkpoints/3.json";
        expected.manifest.transactions.push(`history/transactions/3-${save.commandId}.json`);
        Object.assign(expected.history, {projectRevision: 3, undoCount: baseline.history.undoCount + 1,
          redoCount: 0, undoLabel: "Edit Sequence settings", redoLabel: ""});
      } else await page.evaluate(() => window.__lmdjTempoSession.cancelPatternTempoPreview(window.__lmdjTempoTickets[0]));
      expect(await page.evaluate(() => window.__lmdjTempoSession.suspendAudio())).toBe(true);
      const retired = await tempoStatus(page, 0);
      expect(retired.phase).toBe("source_lost"); expect(retired.applied).toBeNull();
      expect(retired.ticket).toEqual(first.ticket);
      expect(retired.committedBpm).toBe(savedBeforeSuspend ? 240 : 120);
      expect(retired.commandId).toBe(save?.commandId ?? null);
      expect(retired.committedRevision).toBe(save === null ? null : 3);
      const contextState = await page.evaluate(() => window.__lmdjTempoSession.monitorDestination().context.state);
      expect(contextState).toBe("suspended");
      Object.assign(expected.history, {disabledReason: "", canUndo: expected.history.undoCount > 0, canRedo: false});
      expect(await tempoSnapshot(page, setup.projectId)).toEqual(expected);
      const repeatedCancel = await page.evaluate(() => window.__lmdjTempoSession.cancelPatternTempoPreview(window.__lmdjTempoTickets[0]));
      expect(repeatedCancel).toEqual(retired);
      if (save !== null) expect(await page.evaluate(() => window.__lmdjTempoSession.commitPatternTempoPreview({
        ticket: window.__lmdjTempoTickets[0], commandId: window.__lmdjTempoSaveCommand}))).toEqual(retired);
      expect(await tempoSnapshot(page, setup.projectId)).toEqual(expected);
      evidence.legs.push({leg: "real Suspend and exact terminal replay", retired, repeatedCancel, snapshot: structuredClone(expected), contextState});

      // A fresh real gesture resumes the same frozen SDK Session and context.
      await page.evaluate(async () => {
        const {createUserGestureToken} = await import("/tempo-preview-sdk/input_adapters.mjs");
        const button = document.createElement("button"); button.id = "tempo-resume-audio";
        button.textContent = "Resume actual tempo audio";
        button.addEventListener("click", async event => {
          window.__lmdjTempoResumed = await window.__lmdjTempoSession.activateAudio(createUserGestureToken(event));
        }, {once: true});
        document.body.append(button);
      });
      await page.locator("#tempo-resume-audio").click();
      await expect.poll(() => page.evaluate(() => window.__lmdjTempoResumed)).toBe(true);
      expect(await page.evaluate(() => window.lmdjWebRuntimeHost.session === window.__lmdjTempoSession)).toBe(true);
      expect(await tempoStatus(page, 0)).toEqual(retired);
      const resumed = await playResumedTempoSdk(page, setup, savedBeforeSuspend ? 3 : 2, savedBeforeSuspend ? 240 : 120);
      const fresh = await page.evaluate(async ({projectId, patternId, expectedRevision}) => {
        const session = window.__lmdjTempoSession;
        const ready = await session.beginPatternTempoPreview({projectId, patternId, expectedRevision});
        window.__lmdjTempoTickets.push(ready.ticket);
        await session.setPatternTempoPreview({ticket: ready.ticket, bpm: 180}); return ready;
      }, {projectId: setup.projectId, patternId: setup.patternId, expectedRevision: savedBeforeSuspend ? 3 : 2});
      expect(fresh.ticket.previewToken).not.toBe(first.ticket.previewToken);
      const newPreview = await waitTempoPhase(page, 1, "previewing");
      const stale = await page.evaluate(async () => {
        try {await window.__lmdjTempoSession.setPatternTempoPreview({ticket: window.__lmdjTempoTickets[0], bpm: 200}); return "accepted";}
        catch (error) {return error.code;}
      });
      expect(stale).toBe("HOST_STATE_INVALID");
      const afterStale = await page.evaluate(() => Math.ceil(window.__lmdjTempoSession.monitorDestination().context.currentTime * 48000));
      const newPcm = await observeTempoQuarters(page, newPreview, BigInt(resumed.offset), 2,
        BigInt(afterStale) - BigInt(resumed.offset));
      await page.evaluate(() => window.__lmdjTempoSession.cancelPatternTempoPreview(window.__lmdjTempoTickets[1]));
      const restored = await waitTempoPhase(page, 1, "cancelled");
      expect(restored.applied.anchor.bpm).toBe(savedBeforeSuspend ? 240 : 120);
      const restoredPcm = await observeTempoQuarters(page, restored, BigInt(resumed.offset));
      Object.assign(expected.history, {disabledReason: "pattern_transport_busy", canUndo: false});
      expect(await tempoSnapshot(page, setup.projectId)).toEqual(expected);
      evidence.legs.push({leg: "same Session resumes actual cadence and a fresh independently owned preview", resumed,
        fresh, newPreview, stale, newPcm, restored, restoredPcm, snapshot: structuredClone(expected)});
      await page.evaluate(async ({sessionId, projectId, revision}) => {
        const session = window.__lmdjTempoSession, status = await session.inspectPatternTransport(sessionId);
        await session.requestPatternTransport({sessionId, projectId, commandId: crypto.randomUUID(),
          expectedEpoch: status.transportEpoch + 1, intent: "play_stop", expectedRevision: revision});
      }, {sessionId: resumed.sessionId, projectId: setup.projectId, revision: savedBeforeSuspend ? 3 : 2});
      await expect.poll(async () => !(await page.evaluate(id => window.__lmdjTempoSession.inspectPatternTransport(id), resumed.sessionId)).playing).toBe(true);
      Object.assign(expected.history, {disabledReason: "", canUndo: expected.history.undoCount > 0});
      expect(await tempoSnapshot(page, setup.projectId)).toEqual(expected);
      if (savedBeforeSuspend) {
        const undo = await page.evaluate(async () => {
          const session = window.__lmdjTempoSession, history = await session.inspectAuthoringHistory();
          window.__lmdjTempoUndoCommand = crypto.randomUUID();
          return session.undoAuthoring({sessionId: history.sessionId, commandId: window.__lmdjTempoUndoCommand, expectedRevision: 3});
        });
        expected.view.project.bpm = 120; expected.view.project.revision = 4; expected.view.project_revision = 4;
        expected.checkpoint.bpm = 120; expected.checkpoint.revision = 4;
        expected.manifest.head_revision = 4; expected.manifest.head_checkpoint = "history/checkpoints/4.json";
        expected.manifest.transactions.push(`history/transactions/4-${await page.evaluate(() => window.__lmdjTempoUndoCommand)}.json`);
        Object.assign(expected.history, {projectRevision: 4, undoCount: baseline.history.undoCount,
          redoCount: 1, undoLabel: baseline.history.undoLabel, redoLabel: "Edit Sequence settings", canUndo: baseline.history.canUndo, canRedo: true});
        expect(await tempoSnapshot(page, setup.projectId)).toEqual(expected);
        evidence.legs.push({leg: "Undo after resumed owner restores the complete original authoring state", undo, snapshot: structuredClone(expected)});
      }
      await page.evaluate(() => window.__lmdjTempoOnsetProbe.close());
      expect(await page.evaluate(() => window.__lmdjTempoSession.close())).toBe(true);
      await page.close(); expect(page.isClosed()).toBe(true);
      reopened = await context.newPage(); await bootTempoSdk(reopened);
      await reopened.evaluate(async setup => window.__lmdjTempoSession.openProject(setup.projectId, setup.patternId), setup);
      const cold = await tempoSnapshot(reopened, setup.projectId);
      const expectedCold = structuredClone(expected);
      Object.assign(expectedCold.history, {sessionId: expect.stringMatching(/^[a-f0-9-]{36}$/),
        undoCount: 0, redoCount: 0, undoLabel: "", redoLabel: "", canUndo: false, canRedo: false});
      expect(cold).toEqual(expectedCold); expect(cold.history.sessionId).not.toBe(expected.history.sessionId);
      await activateTempoSdk(reopened); await attachTempoOnsetProbe(reopened);
      const coldAudio = await playResumedTempoSdk(reopened, setup, savedBeforeSuspend ? 4 : 2, 120);
      evidence.legs.push({leg: "cold Runtime reopens exact Truth and actually plays restored 120 BPM", cold, coldAudio});
    } finally {
      for (const owned of [page, reopened]) if (owned !== null && !owned.isClosed()) {
        await owned.evaluate(() => window.__lmdjTempoOnsetProbe?.close()).catch(() => {});
        await owned.evaluate(() => window.__lmdjTempoSession?.close()).catch(() => {});
        if (owned === reopened) await owned.close();
      }
      const path = testInfo.outputPath("actual-tempo-suspend-resume.json");
      await writeFile(path, JSON.stringify(evidence, null, 2));
      await testInfo.attach("actual-tempo-suspend-resume", {path, contentType: "application/json"});
    }
  });
}
