import {expect} from "@playwright/test";
import {waitForBootProject} from "./creator_boot.mjs";
import {wakeAudioWithPad} from "./creator_audio.mjs";
import {pcm16Wav, PROJECT_TRANSITION_TIMEOUT_MS} from "./perform_helpers.mjs";

export async function sendCountInHost(page, operation, payload) {
  const response = await page.evaluate(({operation, payload}) =>
    window.lmdjWebRuntimeHost.transport.send({protocol_version: 1,
      request_id: crypto.randomUUID(), operation, payload}), {operation, payload});
  expect(response, `${operation} actual Host response`).toHaveProperty("ok", true);
  return response.result;
}

export async function prepareCountInProject(page, bpm, {silentPattern = false} = {}) {
  await page.goto("/");
  await waitForBootProject(page);
  const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
  if (!bundle) throw new Error("count-in proof requires the original Creator bundle");
  await page.getByRole("button", {name: "Project", exact: true}).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  const bytes = [...pcm16Wav()];
  const setup = await page.evaluate(async ({bytes, bpm, silentPattern}) => {
    const host = window.lmdjWebRuntimeHost;
    const send = async (operation, payload, sidecar) => {
      const result = await host.transport.send({protocol_version: 1,
        request_id: crypto.randomUUID(), operation, payload},
        sidecar === undefined ? {} : {sidecar});
      if (!result.ok) throw new Error(`${operation}: ${JSON.stringify(result.error)}`);
      return result.result;
    };
    let truth = await host.inspection.inspectProject();
    const projectId = truth.project.project_id;
    if (typeof projectId !== "string") throw new Error("actual Project identity missing");
    const patternId = "00000000-0000-4000-8000-000000000010";
    const pcm = Uint8Array.from(bytes);
    const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", pcm))]
      .map(byte => byte.toString(16).padStart(2, "0")).join("");
    const token = crypto.randomUUID();
    await send("sample.import.begin", {import_token: token, command_id: crypto.randomUUID(),
      expected_revision: truth.project.revision, slot: {bank: 0, pad: 0},
      asset_id: crypto.randomUUID(), byte_length: pcm.length});
    await send("sample.import.chunk", {import_token: token, offset: 0, final: true,
      sidecar: {sidecar_bytes: pcm.length, sidecar_sha256: sha}}, pcm);
    await send("sample.import.commit", {import_token: token});
    truth = await host.inspection.inspectProject();
    await send("sample.update_pad", {command_id: crypto.randomUUID(),
      expected_revision: truth.project.revision, slot: {bank: 0, pad: 0}, playback: {
        trim_start_frame: 0, trim_end_frame: 4800, trigger_mode: "gate",
        gain_millidb: 0, muted: false,
      }});
    truth = await host.inspection.inspectProject();
    if (!Object.hasOwn(truth.project.patterns, patternId))
      throw new Error("actual Pattern ID must exist");
    const remove = truth.project.patterns[patternId].events
      .map(({slot, onset_tick}) => ({slot, onset_tick}));
    const put = silentPattern ? [] : [{slot: {bank: 0, pad: 0}, onset_tick: 0,
      duration_tick: 960, velocity: 100}];
    // An already empty actual Pattern needs no authoring mutation. A nonempty
    // imported Pattern still goes through the real removal command.
    if (remove.length || put.length) await send("pattern.events.edit", {
      command_id: crypto.randomUUID(), expected_revision: truth.project.revision,
      pattern_id: patternId, remove, put,
    });
    truth = await host.inspection.inspectProject();
    if (silentPattern && truth.project.patterns[patternId].events.length !== 0)
      throw new Error("silent setup did not produce actual empty Pattern Truth");
    await send("sequence.settings.update", {command_id: crypto.randomUUID(),
      expected_revision: truth.project.revision, session_id: null, bpm,
      quantize_enabled: false, swing_percent: 50});
    await send("snapshot.reload", {pattern_id: patternId});
    return {projectId, patternId, sessionId: crypto.randomUUID()};
  }, {bytes, bpm, silentPattern});
  await wakeAudioWithPad(page, {padAddress: "A01"});
  await page.evaluate(() => window.lmdjWebRuntimeHost.session.setMonitorVolume(100));
  return setup;
}

export async function countInProjectInventory(page, projectId) {
  return page.evaluate(async projectId => {
    const root = await navigator.storage.getDirectory();
    const projects = await root.getDirectoryHandle("projects");
    const bundle = await projects.getDirectoryHandle(`${projectId}.lmdj`);
    const files = [];
    async function visit(directory, prefix) {
      for await (const [name, entry] of directory.entries()) {
        const path = `${prefix}${name}`;
        if (entry.kind === "directory") await visit(entry, `${path}/`);
        else {
          const bytes = await (await entry.getFile()).arrayBuffer();
          const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
            .map(byte => byte.toString(16).padStart(2, "0")).join("");
          files.push({path, bytes: bytes.byteLength, sha});
        }
      }
    }
    await visit(bundle, "");
    return files.sort((a, b) => a.path.localeCompare(b.path));
  }, projectId);
}

export async function installCountInAudioObserver(page) {
  await page.addInitScript(() => {
    const NativeNode = window.AudioWorkletNode;
    window.__countInNativeNodes = [];
    window.AudioWorkletNode = class extends NativeNode {
      constructor(context, name, options) {
        super(context, name, options);
        if (name === "lmdj-realtime-engine") {
          window.__countInNativeNodes.push(this);
        } else if (name === "lmdj-perform-master-tap") {
          this.port.addEventListener("message", ({data}) => {
            if (data.type === "stopped" && window.__countInPcm?.context === context) window.__countInTapStopAck = {
              generation: data.generation, finalSequence: data.finalSequence,
              observedFrame: Math.round(context.currentTime * context.sampleRate),
            };
          });
        }
      }
    };
  });
}

export async function attachCountInPcmObserver(page) {
  const shape = await page.evaluate(async () => {
    const session = window.lmdjWebRuntimeHost.session;
    const monitor = session.monitorDestination();
    const context = monitor.context;
    const native = window.__countInNativeNodes.findLast(node => node.context === context);
    if (!native || native.numberOfOutputs !== 2) throw new Error("actual two-output Native node missing");
    await context.audioWorklet.addModule("/__lmdj-test__/audio-observer.js");
    const capacity = 16 * 48_000;
    const headerBuffer = new SharedArrayBuffer(4 * Int32Array.BYTES_PER_ELEMENT);
    const sampleBuffer = new SharedArrayBuffer(6 * capacity * Float32Array.BYTES_PER_ELEMENT);
    const header = new Int32Array(headerBuffer);
    const samples = new Float32Array(sampleBuffer);
    const node = new AudioWorkletNode(context, "lmdj-count-in-pcm-probe", {
      numberOfInputs: 3, numberOfOutputs: 1, outputChannelCount: [1],
      channelCount: 2, channelCountMode: "explicit",
      processorOptions: {header: headerBuffer, samples: sampleBuffer, capacity},
    });
    native.connect(node, 0, 0);
    native.connect(node, 1, 1);
    monitor.connect(node, 0, 2);
    node.connect(context.destination); // Observer produces silence only.
    function command(value, expected) {
      return new Promise((resolve, reject) => {
        node.port.onmessage = ({data}) => {
          node.port.onmessage = null;
          if (data.type !== expected) reject(new Error("observer ownership handshake failed"));
          else resolve();
        };
        node.port.postMessage(value);
      });
    }
    window.__countInPcm = {
      context, capacity, header, samples,
      arm: () => command("arm", "armed"),
      freeze: () => command("freeze", "frozen"),
      close() {
        native.disconnect(node);
        monitor.disconnect(node);
        node.disconnect();
        node.port.close();
      },
    };
    return {sampleRate: context.sampleRate, outputs: native.numberOfOutputs,
      frozenPublicSession: Object.isFrozen(session),
      sharedInputOwner: session.requestPatternInput === window.lmdjWebRuntimeHost.patternTransport.requestPatternInput};
  });
  expect(shape).toEqual({sampleRate: 48_000, outputs: 2,
    frozenPublicSession: true, sharedInputOwner: true});
}

export async function armCountInPcm(page) {
  await page.evaluate(() => window.__countInPcm.arm());
}

export async function readCountInPcm(page, markers = [], {cueMarkers = markers} = {}) {
  const snapshot = await page.evaluate(async ({markers, cueMarkers}) => {
    const recorder = window.__countInPcm;
    await recorder.freeze();
    const firstFrame = Atomics.load(recorder.header, 1);
    const frames = Atomics.load(recorder.header, 2);
    const error = Atomics.load(recorder.header, 3);
    const planes = [];
    for (let plane = 0; plane < 6; ++plane) {
      const offset = plane * recorder.capacity;
      const onsets = [];
      let quiet = 96, energy = 0, outsideCueNonzero = 0;
      for (let frame = 0; frame < frames; ++frame) {
        const sample = recorder.samples[offset + frame];
        energy += sample * sample;
        if ((plane === 2 || plane === 3) && cueMarkers.length && sample !== 0 &&
            !cueMarkers.some(marker => firstFrame + frame >= marker && firstFrame + frame < marker + 1920))
          outsideCueNonzero++;
        if (Math.abs(sample) > 1e-9) {
          if (quiet >= 96) onsets.push(firstFrame + frame);
          quiet = 0;
        } else quiet++;
      }
      const windows = markers.map(marker => {
        const relative = marker - firstFrame;
        if (relative < 96 || relative + 2016 > frames) throw new Error("PCM marker outside retained observation");
        return {
          marker,
          before: Array.from(recorder.samples.subarray(offset + relative - 96, offset + relative)),
          values: Array.from(recorder.samples.subarray(offset + relative, offset + relative + 1920)),
          tail: Array.from(recorder.samples.subarray(offset + relative + 1920, offset + relative + 2016)),
        };
      });
      planes.push({onsets, energy, windows, outsideCueNonzero});
    }
    window.__countInFrozen = {firstFrame, frames, error, markers: [...markers]};
    return {firstFrame, frames, error, planes};
  }, {markers, cueMarkers});
  expect(snapshot.error, "bounded aligned PCM observer").toBe(0);
  expect(snapshot.frames).toBeGreaterThan(0);
  return snapshot;
}

export async function requestCountInInput(page, request) {
  return page.evaluate(async request => {
    const session = window.lmdjWebRuntimeHost.session;
    const capability = await session.queryPatternCountInCapabilities();
    window.__countInInputSerial ??= 9_007_199_254_740_993n;
    if (request.phaseWindow) {
      const {startFrame, offset} = request.phaseWindow;
      const phaseDeadline = performance.now() + 2_000;
      while (true) {
        const nativeFrame = Math.floor(window.__countInPcm.context.currentTime * 48_000) - offset;
        const phase = Math.floor((nativeFrame - startFrame) / 25) % 3840;
        if (phase >= 0 && phase < 960) break;
        if (performance.now() >= phaseDeadline) throw new Error("early Native phase was not available");
        await new Promise(resolve => setTimeout(resolve, 10));
      }
    }
    const began = performance.now();
    const result = await session.requestPatternInput({
      commandId: crypto.randomUUID(),
      runtimeGeneration: capability.runtimeGeneration,
      frameEpoch: capability.frameEpoch,
      inputSerial: String(window.__countInInputSerial++),
      slot: request.slot ?? 0,
      velocity: request.kind === "release" ? 0 : request.velocity ?? 100,
      kind: request.kind ?? "press",
      held: request.held ?? true,
      heldPressSequence: request.heldPressSequence ?? null,
    });
    window.__countInInputDeadlines ??= new Map();
    window.__countInInputDeadlines.set(result.ticket.ticket, began + 1_000);
    if (performance.now() >= began + 1_000) throw new Error("input request exhausted original one-second budget");
    return result;
  }, request);
}

export async function settleCountInInput(page, ticket) {
  const result = await page.evaluate(async ticket => {
    const session = window.lmdjWebRuntimeHost.session;
    const deadline = window.__countInInputDeadlines.get(ticket.ticket);
    if (!Number.isFinite(deadline)) throw new Error("original input observer deadline missing");
    let status;
    do {
      if (performance.now() >= deadline) throw new Error("input total completion exceeded original one-second budget");
      status = await session.inspectPatternInput(ticket);
      if (performance.now() >= deadline) throw new Error("input observation exceeded original one-second budget");
      if (!status.complete) await new Promise(resolve => setTimeout(resolve, 10));
    } while (!status.complete);
    if (status.expired || status.error !== null || !status.durableSettled || status.nativeResult === null)
      throw new Error(`input did not complete timely: ${JSON.stringify(status)}`);
    const consumed = await session.inspectPatternInput(ticket, true);
    window.__countInSettledInputs ??= new Map();
    window.__countInSettledInputs.set(ticket.ticket, status);
    return {status, consumed};
  }, ticket);
  expect(result.status.nativeResult.sequence).toBe(result.status.admission.sequence);
  expect(result.status.nativeResult.acceptanceOrdinal).toBe(result.status.admission.acceptanceOrdinal);
  expect(result.status.nativeResult.authority).toEqual(result.status.admission.authority);
  expect(result.consumed.complete).toBe(true);
  if (result.status.admission.authority.recording)
    expect(result.status.retained, "recorded input has actual durable candidate retention").toBe(true);
  return result.status.nativeResult;
}

async function calibrateOneCountInClock(page) {
  // This is a real Bank voice admitted independently of any count-in request.
  // No cue producer marker, Host wall clock or status-derived offset is used.
  await armCountInPcm(page);
  const admission = await requestCountInInput(page, {held: true});
  const native = await settleCountInInput(page, admission.ticket);
  expect(native.disposition).toBe("voice_started");
  expect(native.authority.recording).toBe(false);
  const release = await requestCountInInput(page, {
    kind: "release", heldPressSequence: native.sequence,
  });
  const released = await settleCountInInput(page, release.ticket);
  expect(released.heldPressSequence).toBe(native.sequence);
  await expect.poll(() => page.evaluate(() => {
    const {header, samples} = window.__countInPcm;
    const frames = Atomics.load(header, 2);
    if (frames < 256) return false;
    return samples.subarray(frames - 256, frames).every(value => value === 0);
  }), {timeout: 1_000, intervals: [10]}).toBe(true);
  const pcm = await readCountInPcm(page);
  expect(pcm.planes[0].onsets).toHaveLength(1);
  expect(pcm.planes[2].energy).toBe(0);
  // The fixture source has a nonzero first sample; Native's existing dry
  // 96-frame attack is zero at frame 0, so its first nonzero sample is F+1.
  const offset = pcm.planes[0].onsets[0] - native.runtimeFrame - 1;
  expect(Number.isSafeInteger(offset)).toBe(true);
  return {offset, runtimeGeneration: native.runtimeGeneration, frameEpoch: native.frameEpoch};
}

export async function calibrateCountInClock(page) {
  const first = await calibrateOneCountInClock(page);
  const second = await calibrateOneCountInClock(page);
  expect(second, "two independent Bank admissions calibrate the same actual epoch")
    .toEqual(first);
  return second;
}

export async function requestCountIn(page, setup, bars) {
  return page.evaluate(async ({setup, bars}) => {
    if (!window.__countInRpcProof) {
      const host = window.lmdjWebRuntimeHost;
      const transport = host.transport;
      const module = window.Module;
      if (typeof module?.ccall !== "function" || !(module.wasmMemory instanceof WebAssembly.Memory))
        throw new Error("actual Host dispatch instrumentation is unavailable");
      const proof = window.__countInRpcProof = {requests: [], stalls: [], instrumentationErrors: []};
      const byRequest = new Map();
      const originalCcall = module.ccall;
      module.ccall = function observedCountInDispatch(...arguments_) {
        const [identifier, , types, values] = arguments_;
        let entry;
        if (identifier === "lmdj_web_host_submit") {
          try {
            if (!Array.isArray(types) || types.length !== 5 || types.some(type => type !== "number") ||
                !Array.isArray(values) || values.length !== 5)
              throw new Error("actual Host submit arguments differ from the production signature");
            const envelope = JSON.parse(new TextDecoder().decode(
              new Uint8Array(module.wasmMemory.buffer).subarray(values[0], values[0] + values[1])));
            entry = byRequest.get(envelope.request_id);
            if (entry) {
              entry.nativeRequestId = envelope.request_id;
              entry.dispatchAt = performance.now();
              entry.nativeDeadlineAtEpoch = values[4];
              entry.nativeDeadlineAt = values[4] - performance.timeOrigin;
            }
          } catch (error) { proof.instrumentationErrors.push(String(error.message)); }
        }
        // The observer never substitutes this, arguments, a native receipt,
        // or an exception from the production submission.
        const result = Reflect.apply(originalCcall, this, arguments_);
        if (entry) entry.submitResult = result;
        return result;
      };
      const proxy = new Proxy({}, {get(_target, key) {
        if (!["send", "sendRetained"].includes(key)) return Reflect.get(transport, key);
        const send = transport[key];
        if (typeof send !== "function") return send;
        return function observedCountInSend(...arguments_) {
          const [request, options] = arguments_;
          const originalThis = this === proxy ? transport : this;
          if (request.operation !== "pattern.transport.count-in.inspect")
            return Reflect.apply(send, originalThis, arguments_);
          const entry = {requestId: request.request_id, operation: request.operation,
            payload: structuredClone(request.payload),
            handoffAt: performance.now(), deadlineMs: options?.deadlineMs ?? null,
            nativeRequestId: null, responseRequestId: null,
            dispatchAt: null, nativeDeadlineAtEpoch: null, nativeDeadlineAt: null,
            submitResult: null, settledAt: null, ok: null, error: null};
          proof.requests.push(entry);
          byRequest.set(request.request_id, entry);
          const failed = error => {
            entry.error = {message: String(error?.message ?? error), code: error?.code ?? null,
              pending: error?.details?.pending ?? null};
            entry.settledAt = performance.now();
          };
          try {
            const pending = Reflect.apply(send, originalThis, arguments_);
            // Observe completion without replacing the original Promise or
            // its rejection. SDK's default transport dynamically forwards to
            // runtime.transport, even after its Session has been created.
            void pending.then(response => {
              entry.responseRequestId = response?.request_id ?? null;
              entry.ok = response?.ok ?? null;
              entry.settledAt = performance.now();
            }, failed);
            return pending;
          } catch (error) {
            failed(error);
            throw error;
          }
        };
      }});
      host.transport = proxy;
    }
    const session = window.lmdjWebRuntimeHost.session;
    const capability = await session.queryPatternCountInCapabilities();
    if (!capability.supported || !capability.negotiated || !capability.outputReady)
      throw new Error("actual packaged scheduled transport is unavailable");
    const truth = await window.lmdjWebRuntimeHost.inspection.inspectProject();
    const admitted = await session.requestPatternCountIn({
      sessionId: setup.sessionId, projectId: setup.projectId,
      commandId: crypto.randomUUID(),
      runtimeGeneration: capability.runtimeGeneration, frameEpoch: capability.frameEpoch,
      scheduleSerial: "9007199254740993", expectedEpoch: "1", bars,
      expectedRevision: truth.project.revision,
    });
    // Observe immediately on short turns, so a later PCM read/opening wait
    // cannot create a fresh budget. The controller's retained error enforces
    // its own first-acquired-Applied deadline; S is not its timer's start.
    window.__countInOpeningWatches ??= new Map();
    const watch = {firstAppliedAt: null, deadline: null, status: null, failure: null,
      paused: false, inFlight: null, resumeObserver: null};
    watch.settled = (async () => {
      try {
        while (true) {
          if (watch.paused) {
            await new Promise(resolve => { watch.resumeObserver = resolve; });
            continue;
          }
          watch.inFlight = session.inspectPatternCountIn(admitted.ticket);
          let status;
          try { status = await watch.inFlight; }
          finally { watch.inFlight = null; }
          watch.status = status;
          if (status.startReceipt?.result === "applied" && watch.deadline === null) {
            watch.firstAppliedAt = performance.now();
            watch.deadline = watch.firstAppliedAt + 5_000;
          }
          if (status.error !== null) throw new Error(`actual opening failed: ${JSON.stringify(status.error)}`);
          if (watch.deadline !== null && performance.now() >= watch.deadline)
            throw new Error("opening observer exceeded original five-second Applied budget");
          if (status.openingComplete || ["cancelled", "refused"].includes(status.startReceipt?.result)) return;
          await new Promise(resolve => setTimeout(resolve, 10));
        }
      } catch (error) { watch.failure = String(error.message); }
    })();
    window.__countInOpeningWatches.set(admitted.ticket.scheduleSerial, watch);
    return admitted;
  }, {setup, bars});
}

export async function pauseCountInOpeningObserver(page, ticket, label) {
  const fence = await page.evaluate(async ({ticket, label}) => {
    const watch = window.__countInOpeningWatches.get(ticket.scheduleSerial);
    if (!watch || watch.paused) throw new Error("original opening watch cannot be fenced");
    const pauseRequestedAt = performance.now();
    watch.paused = true;
    // Drain the original query; neither abort nor a new RPC deadline counts
    // as receiving its real response. The next watch turn sees paused first.
    if (watch.inFlight !== null) await watch.inFlight;
    if (watch.failure !== null) throw new Error(watch.failure);
    const proof = window.__countInRpcProof;
    if (proof.instrumentationErrors.length)
      throw new Error(`actual RPC observation failed: ${JSON.stringify(proof.instrumentationErrors)}`);
    const requests = proof.requests.filter(entry => entry.payload.command_id === ticket.commandId &&
      entry.payload.session_id === ticket.sessionId && entry.payload.runtime_generation === ticket.runtimeGeneration &&
      entry.payload.frame_epoch === ticket.frameEpoch && entry.payload.schedule_serial === ticket.scheduleSerial &&
      entry.payload.consume === false);
    if (!requests.length) throw new Error("stall fence has no positive original inspect evidence");
    const pending = requests.filter(entry => entry.settledAt === null);
    if (pending.length) throw new Error("original count-in inspect remains in flight at stall fence");
    if (requests.some(entry => entry.nativeRequestId !== entry.requestId ||
        entry.responseRequestId !== entry.requestId || entry.submitResult !== 0 || entry.ok !== true ||
        entry.error !== null || entry.dispatchAt === null || entry.nativeDeadlineAt === null ||
        entry.nativeDeadlineAtEpoch === null || entry.deadlineMs !== 1_000))
      throw new Error("stall fence lacks successful exact-ID Native dispatch and original response evidence");
    const fence = {label, scheduleSerial: ticket.scheduleSerial,
      commandId: ticket.commandId, pauseRequestedAt, drainedAt: performance.now(),
      firstAppliedAt: watch.firstAppliedAt, deadline: watch.deadline,
      observedRequestIds: requests.map(entry => entry.requestId),
      pendingRequestIds: pending.map(entry => entry.requestId)};
    window.__countInRpcProof.stalls.push(fence);
    return fence;
  }, {ticket, label});
  expect(fence.pendingRequestIds, "every original inspect settled before blocking its observer").toEqual([]);
  expect(fence.observedRequestIds.length, "fence has positive exact original RPC evidence").toBeGreaterThan(0);
  return fence;
}

export async function resumeCountInOpeningObserver(page, ticket, observed) {
  await page.evaluate(({ticket, observed}) => {
    const watch = window.__countInOpeningWatches.get(ticket.scheduleSerial);
    if (!watch?.paused) throw new Error("original opening watch was not paused");
    const fence = window.__countInRpcProof.stalls.at(-1);
    if (fence.scheduleSerial !== ticket.scheduleSerial || fence.resumedAt !== undefined)
      throw new Error("stall fence identity does not match the original watch");
    if (watch.firstAppliedAt !== fence.firstAppliedAt || watch.deadline !== fence.deadline)
      throw new Error("opening observer budget changed while paused");
    Object.assign(fence, observed, {resumedAt: performance.now()});
    watch.paused = false;
    const resume = watch.resumeObserver;
    watch.resumeObserver = null;
    resume?.();
  }, {ticket, observed});
}

export async function inspectCountIn(page, ticket, consume = false) {
  return page.evaluate(({ticket, consume}) =>
    window.lmdjWebRuntimeHost.session.inspectPatternCountIn(ticket, consume), {ticket, consume});
}

export async function cancelCountIn(page, setup, ticket, intent = "play_stop") {
  return page.evaluate(({setup, ticket, intent}) =>
    window.lmdjWebRuntimeHost.session.cancelPatternCountIn({
      ticket, projectId: setup.projectId, commandId: crypto.randomUUID(),
      expectedEpoch: "2", intent,
    }), {setup, ticket, intent});
}

export async function waitForCountInBoundary(page, ticket) {
  let status;
  await expect.poll(async () => {
    status = await inspectCountIn(page, ticket);
    return Number.isSafeInteger(status.countIn?.countInFrame) &&
      Number.isSafeInteger(status.countIn?.startFrame);
  }, {timeout: 1_000, intervals: [10]}).toBe(true);
  expect(status.error).toBeNull();
  return status;
}

export async function waitForObservedFrame(page, frame, timeout) {
  await expect.poll(() => page.evaluate(() => {
    const {header} = window.__countInPcm;
    return Atomics.load(header, 1) + Atomics.load(header, 2);
  }), {timeout, intervals: [10]}).toBeGreaterThan(frame);
}

export async function startCountInMasterCapture(page) {
  const status = await page.evaluate(async () => {
    const session = window.lmdjWebRuntimeHost.session;
    const status = session.performanceMasterCaptureStatus();
    window.__countInMaster = {frames: 0, nonzero: 0, failures: [], stopped: false, batches: [[], []], overflow: false,
      startRequestedFrame: Math.round(session.monitorDestination().context.currentTime * 48_000)};
    window.__countInTapStopAck = null;
    window.__countInMaster.capture = await session.startPerformanceMasterCapture({
      onBatch(channels) {
        const master = window.__countInMaster;
        if (master.frames + channels[0].length > 16 * 48_000) {
          master.overflow = true;
          return;
        }
        master.frames += channels[0].length;
        for (let channel = 0; channel < 2; ++channel)
          window.__countInMaster.batches[channel].push(channels[channel].slice());
        for (const channel of channels) for (const sample of channel)
          if (sample !== 0) window.__countInMaster.nonzero++;
      },
      onFailure(code, droppedFrames) { window.__countInMaster.failures.push({code, droppedFrames}); },
      onStopped() { window.__countInMaster.stopped = true; },
    });
    return status;
  });
  expect(status.state, "the existing packaged Creator master tap is the capture owner").toBe("ready");
}

export async function stopCountInMasterCapture(page, {silent = true} = {}) {
  const result = await page.evaluate(async () => {
    const stopRequestedFrame = Math.round(window.__countInPcm.context.currentTime * 48_000);
    await window.__countInMaster.capture.stop();
    const {frames, nonzero, failures, stopped, overflow, batches} = window.__countInMaster;
    return {frames, nonzero, failures, stopped, overflow, batchCount: batches[0].length, stopRequestedFrame, ack: window.__countInTapStopAck};
  });
  expect(result.overflow, "fixed 16-second capture witness capacity").toBe(false);
  expect(result.frames).toBeGreaterThan(0);
  if (silent) expect(result.nonzero, "forced cues never enter the product master capture").toBe(0);
  expect(result.failures).toEqual([]);
  expect(result.stopped).toBe(true);
  expect(result.ack, "actual tap stopped ACK, not only logical capture resolution").not.toBeNull();
  expect(result.ack.finalSequence).toBe(result.batchCount);
  expect(result.ack.observedFrame).toBeGreaterThanOrEqual(result.stopRequestedFrame);
  return result;
}

export function expectForcedCountInPcm(pcm, markers, {monitorLevel = 1} = {}) {
  expect(pcm.planes[2].onsets).toEqual(markers.map(frame => frame + 1));
  expect(pcm.planes[3].onsets).toEqual(markers.map(frame => frame + 1));
  for (const plane of [2, 3]) {
    expect(pcm.planes[plane].outsideCueNonzero, "no late or unscheduled cue sample").toBe(0);
    for (const [marker, window] of pcm.planes[plane].windows.slice(0, markers.length).entries()) {
      expect(window.before).toEqual(Array(96).fill(0));
      expect(window.values[0]).toBe(0);
      let error = 0;
      for (let frame = 1; frame < window.values.length; ++frame) {
        // Preserve the existing metronome's first-beat accent in each Bar.
        // This analytic reference uses that rule, not Native descriptors.
        const frequency = marker % 4 === 0 ? 1800 : 1200;
        const expected = 0.2 * Math.sin(2 * Math.PI * frequency * frame / 48_000) *
          Math.exp(Math.log(0.0001 / 0.2) * frame / 1920);
        error = Math.max(error, Math.abs(window.values[frame] - expected));
      }
      expect(error, "all 1920 analytic cue samples").toBeLessThan(1e-7);
      expect(window.tail).toEqual(Array(96).fill(0));
    }
  }
  for (const [monitorPlane, cuePlane] of [[4, 2], [5, 3]]) {
    for (let marker = 0; marker < markers.length; ++marker) {
      const monitor = pcm.planes[monitorPlane].windows[marker];
      const cue = pcm.planes[cuePlane].windows[marker];
      const product = pcm.planes[monitorPlane - 4].windows[marker];
      let error = 0;
      for (const part of ["before", "values", "tail"])
        for (let frame = 0; frame < cue[part].length; ++frame)
          error = Math.max(error, Math.abs(monitor[part][frame] -
            (product[part][frame] + cue[part][frame]) * monitorLevel));
      expect(error, "every aligned monitor sample equals (product + cue) * gain").toBeLessThan(1e-7);
    }
  }
  if (pcm.planes[0].energy === 0 && pcm.planes[1].energy === 0) {
    expect(pcm.planes[4].energy / pcm.planes[2].energy)
      .toBeCloseTo(monitorLevel * monitorLevel, 6);
    expect(pcm.planes[5].energy / pcm.planes[3].energy)
      .toBeCloseTo(monitorLevel * monitorLevel, 6);
  }
}

export function countInPattern(project, patternId) {
  expect(Object.hasOwn(project.patterns, patternId), "actual Project Pattern ID exists").toBe(true);
  return project.patterns[patternId];
}

export async function ensureCountInClock(page, previous) {
  const capability = await page.evaluate(() =>
    window.lmdjWebRuntimeHost.session.queryPatternCountInCapabilities());
  if (previous && previous.runtimeGeneration === capability.runtimeGeneration &&
      previous.frameEpoch === capability.frameEpoch) return previous;
  const contextChanged = await page.evaluate(() =>
    window.__countInPcm.context !== window.lmdjWebRuntimeHost.session.monitorDestination().context);
  if (contextChanged) {
    await page.evaluate(() => window.__countInPcm.close());
    await attachCountInPcmObserver(page);
  }
  const clock = await calibrateCountInClock(page);
  expect(clock.runtimeGeneration).toBe(capability.runtimeGeneration);
  expect(clock.frameEpoch).toBe(capability.frameEpoch);
  return clock;
}

export function expectCountInClock(ticket, clock) {
  expect(ticket.runtimeGeneration).toBe(clock.runtimeGeneration);
  expect(ticket.frameEpoch).toBe(clock.frameEpoch);
}

export async function setCountInMonitor(page, level) {
  const ramp = await page.evaluate(level => {
    const session = window.lmdjWebRuntimeHost.session;
    const context = session.monitorDestination().context;
    const before = Math.round(context.currentTime * 48_000);
    session.setMonitorVolume(level);
    return {before, end: Math.ceil(context.currentTime * 48_000) + 960};
  }, level);
  await expect.poll(() => page.evaluate(() =>
    Math.floor(window.__countInPcm.context.currentTime * 48_000)),
  {timeout: 1_000, intervals: [10]}).toBeGreaterThanOrEqual(ramp.end);
  return ramp;
}

export async function stallCountInObserver(page, marker, framesAfter = 1920) {
  // A timer/poll only positions the observer before the real marker; it never
  // schedules sound. Both ends are measured from the actual AudioContext.
  await expect.poll(() => page.evaluate(() =>
    Math.round(window.__countInPcm.context.currentTime * 48_000)),
  {timeout: 16_000, intervals: [10]}).toBeGreaterThanOrEqual(marker - 9600);
  const observed = await page.evaluate(({marker, framesAfter}) => {
    const context = window.__countInPcm.context;
    const stallBeganAt = performance.now();
    const before = Math.round(context.currentTime * 48_000);
    if (before >= marker) throw new Error("observer missed the pre-marker stall window");
    const deadline = performance.now() + 2_000;
    while (context.currentTime * 48_000 < marker + framesAfter)
      if (performance.now() >= deadline) throw new Error("AudioContext stopped during bounded cue stall");
    return {before, after: Math.round(context.currentTime * 48_000), stallBeganAt,
      stallEndedAt: performance.now()};
  }, {marker, framesAfter});
  expect(observed.before).toBeLessThan(marker);
  expect(observed.after).toBeGreaterThanOrEqual(marker + framesAfter);
  return observed;
}

export async function waitForCountInOpening(page, ticket, clock, startFrame) {
  expectCountInClock(ticket, clock);
  const result = await page.evaluate(async ticket => {
    const watch = window.__countInOpeningWatches.get(ticket.scheduleSerial);
    if (!watch) throw new Error("original opening observation missing");
    await watch.settled;
    return {status: watch.status, failure: watch.failure, firstAppliedAt: watch.firstAppliedAt};
  }, ticket);
  expect(result.failure, "retained original opening deadline and owner outcome").toBeNull();
  expect(result.firstAppliedAt).not.toBeNull();
  expect(result.status.error).toBeNull();
  expect(result.status.openingComplete).toBe(true);
  expect(result.status.startReceipt).toMatchObject({result: "applied", effectiveFrame: startFrame,
    originFrame: startFrame, transportEpoch: "1"});
  return result.status;
}

export async function readCountInJournal(page, setup) {
  return page.evaluate(async setup => {
    let dir = await navigator.storage.getDirectory();
    for (const component of ["projects", `${setup.projectId}.lmdj`, "recovery", "active"])
      dir = await dir.getDirectoryHandle(component);
    const text = await (await (await dir.getFileHandle("sequence.jsonl")).getFile()).text();
    if (!text.endsWith("\n")) throw new Error("durable Journal has a torn suffix");
    const records = [];
    for (const line of text.split("\n").filter(Boolean)) {
      // The actual writer emits sorted compact canonical JSON. Hash that exact
      // payload before lossless integer parsing; JSON Number would round uint64.
      const match = /^\{"checksum":"([0-9a-f]{64})","payload":(.*)\}$/.exec(line);
      if (!match) throw new Error("noncanonical Journal envelope");
      const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(match[2])))]
        .map(byte => byte.toString(16).padStart(2, "0")).join("");
      if (hash !== match[1]) throw new Error("durable Journal checksum mismatch");
      const lossless = match[2].replace(/"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g,
        token => token.startsWith('"') ? token : /^\d+$/.test(token) ? `"${token}"` : token);
      records.push(JSON.parse(lossless));
    }
    return records;
  }, setup);
}

export function expectedCountInHeldEvent(records, setup, ticket, startFrame, pressed, released, velocity, startReceipt) {
  const unique = (kind, predicate = () => true) => {
    const matches = records.filter(record => record.kind === kind && predicate(record));
    expect(matches, `one durable ${kind} for retained identity`).toHaveLength(1);
    return matches[0];
  };
  const preparation = unique("admission-prepare");
  expect(preparation.session_id).toBe(setup.sessionId);
  expect(preparation.data.project_id).toBe(setup.projectId);
  expect(preparation.data.pattern_id).toBe(setup.patternId);
  expect(preparation.identity.operation_id).toBe(ticket.commandId);
  expect(preparation.identity.runtime_generation).toBe(ticket.runtimeGeneration);
  expect(preparation.identity.transport_epoch).toBe("1");
  const fence = unique("admission-fence", record => record.data.kind === "0");
  expect(fence.identity).toEqual(preparation.identity);
  expect(fence.data.effective_frame).toBe(String(startFrame));
  expect(fence.data.origin_frame).toBe(String(startFrame));
  expect(fence.data.transport_epoch).toBe("1");
  expect(fence.data.command_id).toBe(ticket.commandId);
  expect(preparation.data.identity).toEqual(preparation.identity);
  expect(preparation.data.quantize_enabled).toBe(false);
  expect(preparation.data.swing_percent).toBe("50");
  expect(unique("begin").contract).toBe("lmdj.sequence.journal.v3");
  expect(unique("begin").bars).toBe("1");
  expect(fence.data.pattern_id).toBe(setup.patternId);
  expect(fence.data.bpm).toBe("120");
  expect(fence.data.playing).toBe(true);
  expect(fence.data.publication_generation).toBe(preparation.data.publication_generation);
  expect(fence.data.publication_generation).toBe(startReceipt.patternGeneration);
  expect(startReceipt).toMatchObject({runtimeGeneration: ticket.runtimeGeneration,
    frameEpoch: ticket.frameEpoch, scheduleSerial: ticket.scheduleSerial, transportEpoch: "1",
    result: "applied", effectiveFrame: startFrame, originFrame: startFrame, patternId: setup.patternId});
  for (const native of [pressed, released]) {
    expect(native.runtimeGeneration).toBe(ticket.runtimeGeneration);
    expect(native.frameEpoch).toBe(ticket.frameEpoch);
    expect(native.authority).toEqual({recording: true,
      scheduleSerial: ticket.scheduleSerial, transportEpoch: "1"});
  }
  expect(released.heldPressSequence).toBe(pressed.sequence);
  expect(BigInt(released.sequence)).toBeGreaterThan(BigInt(pressed.sequence));
  expect(BigInt(released.acceptanceOrdinal)).toBeGreaterThan(BigInt(pressed.acceptanceOrdinal));
  const press = unique("admission-candidate", record =>
    record.data.watermark === String(BigInt(pressed.acceptanceOrdinal) + 9n));
  const release = unique("admission-candidate", record =>
    record.data.watermark === String(BigInt(released.acceptanceOrdinal) + 9n));
  expect(records.filter(record => record.kind === "admission-candidate")).toHaveLength(2);
  for (const record of [press, release]) {
    expect(record.session_id).toBe(setup.sessionId);
    expect(record.identity).toEqual(preparation.identity);
    expect(record.data.slot).toEqual({bank: "0", pad: "1"});
    expect(record.data.press_sequence).toBe(pressed.sequence);
    expect(BigInt(record.data.runtime_frame)).toBeGreaterThanOrEqual(BigInt(startFrame));
  }
  expect(press.data.kind).toBe("0");
  expect(release.data.kind).toBe("1");
  expect(press.data.velocity).toBe(String(velocity));
  expect(release.data.velocity).toBe("0");
  expect(BigInt(release.data.watermark)).toBeGreaterThan(BigInt(press.data.watermark));
  const attack = (BigInt(press.data.runtime_frame) - BigInt(startFrame)) / 25n;
  const end = (BigInt(release.data.runtime_frame) - BigInt(startFrame)) / 25n;
  const onset = Number(attack % 3840n);
  const duration = Math.min(Number(end - attack), 3840 - onset);
  expect(end - attack).toBeGreaterThan(240n);
  expect(duration, "actual stored duration distinguishes a lost-release 240-tick fallback").toBeGreaterThan(240);
  return {slot: {bank: 0, pad: 1}, onset_tick: onset, duration_tick: duration, velocity};
}

export function expectCountInProductMonitor(pcm, marker, level) {
  const index = pcm.planes[0].windows.findIndex(window => window.marker === marker);
  expect(index).toBeGreaterThanOrEqual(0);
  for (const [productPlane, cuePlane, monitorPlane] of [[0, 2, 4], [1, 3, 5]]) {
    const product = pcm.planes[productPlane].windows[index];
    const cue = pcm.planes[cuePlane].windows[index];
    const monitor = pcm.planes[monitorPlane].windows[index];
    let error = 0;
    for (const part of ["before", "values", "tail"])
      for (let frame = 0; frame < product[part].length; ++frame)
        error = Math.max(error, Math.abs(monitor[part][frame] - (product[part][frame] + cue[part][frame]) * level));
    expect(error, "all product/monitor samples at actual S").toBeLessThan(1e-7);
  }
}


export async function expectCountInMixedCapture(page, productOnset, cueMarkers) {
  const result = await page.evaluate(({productOnset, cueMarkers}) => {
    const {samples, capacity} = window.__countInPcm;
    const frozen = window.__countInFrozen;
    const master = window.__countInMaster;
    const capture = master.batches.map(batches => {
      const out = new Float32Array(master.frames);
      let at = 0;
      for (const batch of batches) { out.set(batch, at); at += batch.length; }
      return out;
    });
    const firstSignal = capture[0].findIndex(sample => Math.abs(sample) > 1e-9);
    if (firstSignal < 0) throw new Error("mixed Master capture did not receive real Bank PCM");
    const captureOrigin = productOnset - firstSignal;
    let compared = 0, differences = 0, overlapping = 0, cueOnly = 0;
    for (let frame = 0; frame < master.frames; ++frame) {
      const absolute = captureOrigin + frame;
      const observed = absolute - frozen.firstFrame;
      if (observed < 0 || observed >= frozen.frames) continue;
      compared++;
      for (let channel = 0; channel < 2; ++channel) {
        const product = samples[channel * capacity + observed];
        const cue = samples[(channel + 2) * capacity + observed];
        if (capture[channel][frame] !== product) differences++;
        if (product !== 0 && cue !== 0) overlapping++;
        if (product === 0 && cue !== 0) {
          cueOnly++;
          if (capture[channel][frame] !== 0) differences++;
        }
      }
    }
    // The entire forced-cue kernels must be in the actual capture interval.
    const containsCues = cueMarkers.every(marker => marker >= captureOrigin &&
      marker + 2016 <= captureOrigin + master.frames);
    window.__countInMixedCaptureOrigin = captureOrigin;
    return {compared, capturedFrames: master.frames, differences, overlapping, cueOnly, containsCues, captureOrigin};
  }, {productOnset, cueMarkers});
  expect(result.compared).toBe(result.capturedFrames);
  expect(result.capturedFrames).toBeGreaterThan(0);
  expect(result.differences, "every aligned Master sample equals real product only").toBe(0);
  expect(result.overlapping, "live Bank really overlaps a forced cue in both output streams").toBeGreaterThan(0);
  expect(result.cueOnly).toBeGreaterThan(0);
  expect(result.containsCues).toBe(true);
  return result;
}

export async function resampleCountInMasterCapture(page, setup, markers) {
  const result = await page.evaluate(async ({setup, markers}) => {
    const host = window.lmdjWebRuntimeHost;
    const session = host.session;
    const send = async (operation, payload, sidecar) => {
      const response = await host.transport.send({protocol_version: 1,
        request_id: crypto.randomUUID(), operation, payload},
      sidecar === undefined ? {} : {sidecar});
      if (!response.ok) throw new Error(`${operation}: ${JSON.stringify(response.error)}`);
      return response.result;
    };
    const project = async () => (await host.inspection.inspectProject()).project;
    const sha = async bytes => [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
      .map(byte => byte.toString(16).padStart(2, "0")).join("");
    const master = window.__countInMaster;
    if (!master.stopped || master.failures.length || master.overflow || master.frames > 16 * 48_000)
      throw new Error("only genuinely stopped, bounded real Master capture can be resampled");
    const channels = master.batches.map(batches => {
      const channel = new Float32Array(master.frames);
      let at = 0;
      for (const batch of batches) { channel.set(batch, at); at += batch.length; }
      return channel;
    });
    // Serialize ONLY actual received PCM, using the original Creator WAV
    // encoder's clamp/32767/ties-away rule. No expected cue/Bank waveform is
    // used to produce these source bytes or the resample result.
    const wav = new Uint8Array(44 + master.frames * 4);
    const view = new DataView(wav.buffer);
    const ascii = (offset, value) => [...value].forEach((character, index) =>
      wav[offset + index] = character.charCodeAt(0));
    ascii(0, "RIFF"); view.setUint32(4, wav.length - 8, true); ascii(8, "WAVE");
    ascii(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 2, true); view.setUint32(24, 48_000, true);
    view.setUint32(28, 192_000, true); view.setUint16(32, 4, true); view.setUint16(34, 16, true);
    ascii(36, "data"); view.setUint32(40, wav.length - 44, true);
    for (let frame = 0; frame < master.frames; ++frame)
      for (let channel = 0; channel < 2; ++channel) {
        const scaled = Math.min(1, Math.max(-1, channels[channel][frame])) * 32767;
        view.setInt16(44 + frame * 4 + channel * 2,
          Math.sign(scaled) * Math.round(Math.abs(scaled)), true);
      }
    const capturedSha = await sha(wav);
    let truth = await project();
    const importRevision = truth.revision;
    const importToken = crypto.randomUUID(), assetId = crypto.randomUUID();
    // Existing importer owns exact managed installation; the witness never
    // edits Truth or fabricates Journal records or managed OPFS files.
    await send("sample.import.begin", {import_token: importToken, command_id: crypto.randomUUID(),
      expected_revision: importRevision, slot: {bank: 1, pad: 0}, asset_id: assetId, byte_length: wav.length});
    for (let offset = 0; offset < wav.length; offset += 64 * 1024) {
      const chunk = wav.slice(offset, offset + 64 * 1024);
      await send("sample.import.chunk", {import_token: importToken, offset,
        final: offset + chunk.length === wav.length,
        sidecar: {sidecar_bytes: chunk.length, sidecar_sha256: await sha(chunk)}}, chunk);
    }
    await send("sample.import.commit", {import_token: importToken});
    truth = await project();
    const asset = id => {
      if (!Object.hasOwn(truth.assets, id))
        throw new Error("actual managed Asset ID must exist");
      return truth.assets[id];
    };
    const installed = asset(assetId).artifact;
    if (truth.revision !== importRevision + 1 || installed.sha256 !== capturedSha ||
        installed.byte_length !== wav.length || installed.media_type !== "audio/wav")
      throw new Error("actual managed import differs from captured product WAV");
    const performanceId = crypto.randomUUID(), sessionId = crypto.randomUUID();
    const began = await session.beginPerformanceRecording({sessionId, performanceId, expectedRevision: truth.revision});
    const stopRequestId = crypto.randomUUID();
    const stopped = await session.stopPerformanceRecording({sessionId, requestId: stopRequestId});
    truth = await project();
    const saveRevision = truth.revision;
    const recordingArtifact = {sha256: capturedSha, mediaType: "audio/wav", byteLength: wav.length};
    const saved = await session.savePerformance({expectedRevision: saveRevision, performanceId,
      name: "Count-in actual product capture", recordingArtifact});
    const inspected = await session.inspectPerformance(performanceId);
    truth = await project();
    const sourceStartFrame = markers[0] - window.__countInMixedCaptureOrigin;
    const sourceEndFrame = markers.at(-1) + 2016 - window.__countInMixedCaptureOrigin;
    if (!Number.isSafeInteger(sourceStartFrame) || sourceStartFrame < 0 ||
        sourceEndFrame > master.frames || sourceEndFrame <= sourceStartFrame)
      throw new Error("all forced cue windows must belong to the real captured source selection");
    const resampleRevision = truth.revision;
    const committed = await session.commitPerformanceResample({expectedRevision: resampleRevision,
      performanceId, sourceStartFrame, sourceEndFrame, targetSlot: 17});
    truth = await project();
    const selectedAssetId = truth.banks[1].pads[1].asset_id;
    const selectedArtifact = asset(selectedAssetId).artifact;
    let directory = await navigator.storage.getDirectory();
    for (const name of ["projects", `${setup.projectId}.lmdj`, "assets"])
      directory = await directory.getDirectoryHandle(name);
    const readArtifact = async artifact => new Uint8Array(await
      (await (await directory.getFileHandle(`${artifact.sha256}.wav`)).getFile()).arrayBuffer());
    const actualManaged = await readArtifact(installed);
    const actualSelected = await readArtifact(selectedArtifact);
    const selectedView = new DataView(actualSelected.buffer);
    const selectedFrames = sourceEndFrame - sourceStartFrame;
    const validHeader = String.fromCharCode(...actualSelected.slice(0, 4)) === "RIFF" &&
      String.fromCharCode(...actualSelected.slice(8, 16)) === "WAVEfmt " &&
      selectedView.getUint32(4, true) === actualSelected.length - 8 &&
      selectedView.getUint16(20, true) === 1 && selectedView.getUint16(22, true) === 2 &&
      selectedView.getUint32(24, true) === 48_000 && selectedView.getUint16(34, true) === 16 &&
      String.fromCharCode(...actualSelected.slice(36, 40)) === "data" &&
      selectedView.getUint32(40, true) === selectedFrames * 4 && actualSelected.length === 44 + selectedFrames * 4;
    let differences = 0, nonzero = 0, cueOnly = 0;
    for (let frame = 0; frame < selectedFrames; ++frame)
      for (let channel = 0; channel < 2; ++channel) {
        const actual = selectedView.getInt16(44 + frame * 4 + channel * 2, true);
        const expected = view.getInt16(44 + (frame + sourceStartFrame) * 4 + channel * 2, true);
        if (actual !== expected) differences++;
        if (actual !== 0) nonzero++;
        const absolute = window.__countInMixedCaptureOrigin + sourceStartFrame + frame;
        const relative = absolute - window.__countInFrozen.firstFrame;
        const {samples, capacity} = window.__countInPcm;
        if (samples[channel * capacity + relative] === 0 && samples[(channel + 2) * capacity + relative] !== 0) {
          cueOnly++;
          if (actual !== 0) differences++;
        }
      }
    return {importRevision, installed, capturedSha, byteLength: wav.length,
      managedSha: await sha(actualManaged), began, stopped, stopRequestId,
      saveRevision, saved, inspected, performanceId, sessionId, recordingArtifact,
      resampleRevision, committed, truth, selectedArtifact, selectedSha: await sha(actualSelected),
      validHeader, differences, nonzero, cueOnly};
  }, {setup, markers});
  expect(result.managedSha).toBe(result.capturedSha);
  expect(result.began).toMatchObject({performanceId: result.performanceId,
    committedRevision: result.importRevision + 2, replayed: false, projectRevision: result.importRevision + 2});
  expect(result.stopped).toMatchObject({requestId: result.stopRequestId, sessionId: result.sessionId,
    performanceId: result.performanceId, state: "stopped", pendingEventCount: 0, replayed: false, projectRevision: null});
  expect(result.saved).toMatchObject({performanceId: result.performanceId,
    committedRevision: result.saveRevision + 1, projectRevision: result.saveRevision + 1, replayed: false});
  expect(result.inspected.recordingArtifact).toEqual(result.recordingArtifact);
  expect(result.inspected.events).toEqual([]);
  expect(result.committed).toEqual({performanceId: result.performanceId,
    committedRevision: result.resampleRevision + 1, runtimePrepareRequired: true,
    projectRevision: result.resampleRevision + 1});
  expect(result.truth.revision).toBe(result.resampleRevision + 1);
  expect(result.selectedSha).toBe(result.selectedArtifact.sha256);
  expect(result.validHeader).toBe(true);
  expect(result.differences, "every selected resample sample is captured product PCM, never cue").toBe(0);
  expect(result.nonzero).toBeGreaterThan(0);
  expect(result.cueOnly).toBeGreaterThan(0);
  return result.truth;
}
