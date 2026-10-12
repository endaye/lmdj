import {createHash} from "node:crypto";
import {expect} from "@playwright/test";
import {waitForBootProject, waitForProjectReopen} from "../../creator/fixtures/creator_boot.mjs";
import {pcm16Wav} from "../../creator/fixtures/perform_helpers.mjs";
import {clickCreatorSystemAction} from "../../creator/fixtures/creator_navigation.mjs";
import {decodeLegacyPatternTransportStatus} from
  "../../../../../packages/web-runtime-platform/test/fixtures/legacy_pattern_transport_status.mjs";

export const JOURNAL_PATH = "recovery/active/sequence.jsonl";

export async function installNativeNodeWitness(page) {
  await page.addInitScript(() => {
    const Original = window.AudioWorkletNode;
    window.__creatorIoNativeNodes = [];
    // The SDK injects these fields immediately before appending the runtime
    // script; production preRun consumes and deletes them. Observe the actual
    // injection before bootstrap, keeping the real Module and native append.
    const append = Element.prototype.append;
    Element.prototype.append = function (...nodes) {
      const module = window.Module;
      if (this === document.head && nodes.some(node => node instanceof HTMLScriptElement) &&
          module?.lmdjHostManifestBytes instanceof Uint8Array &&
          typeof module.lmdjHostManifestSha256 === "string") {
        window.__creatorIoManifestInjection = {
          module, bytes: Uint8Array.from(module.lmdjHostManifestBytes),
          sha: module.lmdjHostManifestSha256,
        };
        Element.prototype.append = append;
      }
      return Reflect.apply(append, this, nodes);
    };
    window.AudioWorkletNode = new Proxy(Original, {construct(Target, args) {
      const node = Reflect.construct(Target, args);
      if (args[1] === "lmdj-realtime-engine") window.__creatorIoNativeNodes.push(node);
      return node;
    }});
  });
}

async function installTrace(page) {
  await page.evaluate(() => {
    const host = window.lmdjWebRuntimeHost;
    const original = host.transport;
    const proof = {session: host.session, trace: [], calls: {}, checkpoints: []};
    const send = async (...args) => {
      const entry = {request: structuredClone(args[0]), began: performance.now()};
      proof.trace.push(entry);
      try {
        const response = await original.send(...args);
        entry.response = structuredClone(response);
        return response; // Return the exact real response, without synthesizing fields.
      } catch (error) {
        entry.error = {code: error.code ?? null, message: error.message,
          details: structuredClone(error.details ?? {})};
        throw error;
      } finally { entry.ended = performance.now(); }
    };
    // The genuine transport is frozen. An empty observation target avoids
    // violating Proxy invariants while every operation delegates to that owner.
    const proxy = new Proxy({}, {get(_target, key) {
      if (key === "send") return send;
      const value = Reflect.get(original, key, original);
      return typeof value === "function" ? value.bind(original) : value;
    }});
    host.transport = proxy;
    proof.restore = () => {if (host.transport === proxy) host.transport = original;};
    window.__creatorIoProof = proof;
  });
}

export async function sendHost(page, operation, payload, sidecar) {
  const response = await page.evaluate(async ({operation, payload, sidecar}) =>
    window.lmdjWebRuntimeHost.transport.send({protocol_version: 1,
      request_id: crypto.randomUUID(), operation, payload},
      sidecar === undefined ? {} : {sidecar: Uint8Array.from(sidecar)}),
  {operation, payload, sidecar});
  expect(response, `${operation}: ${JSON.stringify(response)}`).toHaveProperty("ok", true);
  return response.result;
}

export async function inspectTruth(page) {
  return (await page.evaluate(() => window.lmdjWebRuntimeHost.inspection.inspectProject())).project;
}

export async function prepareProductionProject(page, {muted = false} = {}) {
  await page.goto("/");
  await waitForBootProject(page);
  await installTrace(page);
  let truth = await inspectTruth(page);
  const projectId = truth.project_id;
  expect(projectId).toMatch(/^[0-9a-f-]{36}$/);
  expect(Array.isArray(truth.pattern_slots), "selection derives from actual Truth slots").toBe(true);
  expect(truth.pattern_slots).toHaveLength(16);
  let patternId = truth.pattern_slots.find(id => typeof id === "string");
  if (patternId === undefined) {
    // A fresh Creator Project has one real initial Pattern, not yet assigned
    // to a slot. Assign that existing identity through the public command.
    expect(truth.pattern_slots).toEqual(Array(16).fill(null));
    const bootPatterns = Object.keys(truth.patterns);
    expect(bootPatterns, "fresh boot has exactly one real initial Pattern").toHaveLength(1);
    const [bootPatternId] = bootPatterns;
    expect(bootPatternId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    const bootPattern = truth.patterns[bootPatternId];
    expect(bootPattern).toEqual({bars: 1, events: []});
    const patternSlot = truth.pattern_slots.findIndex(id => id === null);
    expect(patternSlot).toBeGreaterThanOrEqual(0);
    const assignedSlots = [...truth.pattern_slots];
    assignedSlots[patternSlot] = bootPatternId;
    const beforeRevision = truth.revision;
    const assigned = await sendHost(page, "pattern.slot.assign", {
      command_id: await page.evaluate(() => crypto.randomUUID()),
      expected_revision: beforeRevision, pattern_slot: patternSlot, pattern_id: bootPatternId,
    });
    expect(assigned).toMatchObject({pattern_slot: patternSlot, pattern_id: bootPatternId, replayed: false});
    expect(Number.isSafeInteger(assigned.committed_revision)).toBe(true);
    expect(assigned.committed_revision).toBeGreaterThan(beforeRevision);
    expect(assigned.project_revision).toBe(assigned.committed_revision);
    truth = await inspectTruth(page);
    expect(truth.project_id).toBe(projectId);
    expect(truth.revision).toBe(assigned.committed_revision);
    expect(truth.pattern_slots).toEqual(assignedSlots);
    expect(Object.keys(truth.patterns)).toEqual([bootPatternId]);
    expect(truth.patterns[bootPatternId]).toEqual(bootPattern);
    patternId = truth.pattern_slots[patternSlot];
    expect(patternId).toBe(bootPatternId);
  }
  expect(patternId, "Creator's actual boot Project has a selectable Pattern").toBeDefined();
  expect(Object.hasOwn(truth.patterns, patternId)).toBe(true);
  const bytes = pcm16Wav(); // Existing genuine PCM16 fixture, not an AudioContext source.
  const importToken = await page.evaluate(() => crypto.randomUUID());
  await sendHost(page, "sample.import.begin", {import_token: importToken,
    command_id: await page.evaluate(() => crypto.randomUUID()),
    expected_revision: truth.revision, slot: {bank: 0, pad: 0},
    asset_id: await page.evaluate(() => crypto.randomUUID()), byte_length: bytes.length});
  await sendHost(page, "sample.import.chunk", {import_token: importToken, offset: 0, final: true,
    sidecar: {sidecar_bytes: bytes.length, sidecar_sha256: createHash("sha256").update(bytes).digest("hex")}}, [...bytes]);
  await sendHost(page, "sample.import.commit", {import_token: importToken});
  truth = await inspectTruth(page);
  await sendHost(page, "sample.update_pad", {command_id: await page.evaluate(() => crypto.randomUUID()),
    expected_revision: truth.revision, slot: {bank: 0, pad: 0}, playback: {
      trim_start_frame: 0, trim_end_frame: 4800, trigger_mode: "gate", gain_millidb: 0, muted,
    }});
  truth = await inspectTruth(page);
  const remove = truth.patterns[patternId].events.map(({slot, onset_tick}) => ({slot, onset_tick}));
  if (remove.length > 0) {
    await sendHost(page, "pattern.events.edit", {command_id: await page.evaluate(() => crypto.randomUUID()),
      expected_revision: truth.revision, pattern_id: patternId, remove, put: []});
  }
  truth = await inspectTruth(page);
  expect(truth.patterns[patternId].events, "recording starts from actual empty Pattern Truth").toEqual([]);
  await sendHost(page, "sequence.settings.update", {command_id: await page.evaluate(() => crypto.randomUUID()),
    expected_revision: truth.revision, session_id: null, bpm: 120, quantize_enabled: false, swing_percent: 50});
  await sendHost(page, "snapshot.reload", {pattern_id: patternId});
  // This is the existing trusted Creator UI activation, using its existing SDK.
  await clickCreatorSystemAction(page, "Enable MIDI");
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {timeout: 30_000});
  const startup = await page.evaluate(async () => {
    const host = window.lmdjWebRuntimeHost;
    const session = host.session;
    const monitor = session.monitorDestination();
    const native = window.__creatorIoNativeNodes.filter(node => node.context === monitor.context);
    const bytes = new Uint8Array(await (await fetch("/host-manifest.json")).arrayBuffer());
    const injection = window.__creatorIoManifestInjection;
    const injected = injection?.bytes;
    const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
      .map(value => value.toString(16).padStart(2, "0")).join("");
    const result = {manifest: JSON.parse(new TextDecoder().decode(bytes)), sha,
      injectedSha: injection?.sha,
      injectedBytesEqual: injected?.length === bytes.length && bytes.every((value, i) => injected[i] === value),
      observedModuleIsSame: injection?.module === Module,
      bootstrapFieldsDeleted: !Object.hasOwn(Module, "lmdjHostManifestBytes") &&
        !Object.hasOwn(Module, "lmdjHostManifestSha256"),
      frozen: Object.isFrozen(session), sessionIsSame: session === window.__creatorIoProof.session,
      namespaceIsSame: host.patternTransport.trigger === session.trigger &&
        host.patternTransport.release === session.release,
      sessionDescriptor: {writable: Object.getOwnPropertyDescriptor(host, "session").writable,
        configurable: Object.getOwnPropertyDescriptor(host, "session").configurable},
      nativeNodes: native.length, nativeOutputs: native[0]?.numberOfOutputs,
      sampleRate: monitor.context.sampleRate,
      gateExport: typeof Module._lmdj_web_audio_test_pattern_controller_io_gate,
    };
    window.__creatorIoProof.startup = result;
    window.__creatorIoProof.native = native[0];
    return result;
  });
  expect(startup).toMatchObject({frozen: true, sessionIsSame: true, namespaceIsSame: true,
    injectedBytesEqual: true, observedModuleIsSame: true, bootstrapFieldsDeleted: true,
    nativeNodes: 1, nativeOutputs: 2, sampleRate: 48_000,
    sessionDescriptor: {writable: false, configurable: false}, gateExport: "function"});
  expect(startup.sha).toBe(startup.injectedSha);
  expect(startup.manifest.host_id).toBe("creator-web");
  return {projectId, patternId, sessionId: await page.evaluate(() => crypto.randomUUID()),
    baseline: await inspectTruth(page), startup};
}

async function observeGate(page, action) {
  return page.evaluate(action => {
    const result = Module._lmdj_web_audio_test_pattern_controller_io_gate(action);
    window.__creatorIoProof.checkpoints.push({type: "gate", action, result, at: performance.now()});
    return result;
  }, action);
}

export async function gate(page, action = 0) {
  const state = await observeGate(page, action);
  expect(state, "unknown/failed actual owner gate is never success").not.toBe(-1);
  expect(state).not.toBe(7);
  return state;
}

export async function failedOpeningGate(page) {
  const state = await observeGate(page, 0);
  // Only the already-held open may reach this failure observer. The worker
  // can move 6 -> 7 between polls; observing 6 is not required or fabricated.
  expect([4, 6, 7], "late opening allows only held, flushed or failed owner work").toContain(state);
  return state;
}

export async function releaseGateFinally(page) {
  // No closure claim: the successful journey separately requires state 8.
  try {
    return await page.evaluate(() => {
      const actionResult = Module._lmdj_web_audio_test_pattern_controller_io_gate(3);
      const state = Module._lmdj_web_audio_test_pattern_controller_io_gate(0);
      return {actionResult, state, closureProvenByRelease: false};
    });
  } catch (error) {
    return {state: "unknown", error: String(error), closureProvenByRelease: false};
  }
}

export async function expectSameRuntimeOwner(page, ticket) {
  const result = await page.evaluate(async () => {
    const host = window.lmdjWebRuntimeHost;
    const proof = window.__creatorIoProof;
    const native = window.__creatorIoNativeNodes.filter(node => node.context === host.session.monitorDestination().context);
    return {sameSession: host.session === proof.session, frozen: Object.isFrozen(host.session),
      sameNative: native.length === 1 && native[0] === proof.native,
      outputs: native[0]?.numberOfOutputs, capability: await host.session.queryPatternCountInCapabilities()};
  });
  expect(result).toMatchObject({sameSession: true, frozen: true, sameNative: true, outputs: 2,
    capability: {runtimeGeneration: ticket.runtimeGeneration, frameEpoch: ticket.frameEpoch,
      outputReady: true, negotiated: true}});
  await checkpoint(page, "same-real-frozen-Session-and-Native-epoch", result);
}

export async function requestCountIn(page, setup) {
  return page.evaluate(async setup => {
    const session = window.lmdjWebRuntimeHost.session;
    window.__creatorIoProof.sessionId = setup.sessionId;
    const capability = await session.queryPatternCountInCapabilities();
    if (!capability.supported || !capability.negotiated || !capability.outputReady)
      throw new Error("the actual packaged companion/two-output profile is unavailable");
    return session.requestPatternCountIn({sessionId: setup.sessionId, projectId: setup.projectId,
      commandId: crypto.randomUUID(), runtimeGeneration: capability.runtimeGeneration,
      frameEpoch: capability.frameEpoch, scheduleSerial: capability.nextSerial,
      expectedEpoch: "1", bars: 1, expectedRevision: setup.baseline.revision});
  }, setup);
}

export async function inspectCountIn(page, ticket, consume = false) {
  return page.evaluate(({ticket, consume}) =>
    window.lmdjWebRuntimeHost.session.inspectPatternCountIn(ticket, consume), {ticket, consume});
}

export async function expectRejectedCountInConsume(page, ticket) {
  const result = await page.evaluate(async ticket => {
    try {
      return {unexpectedSuccess: await window.lmdjWebRuntimeHost.session.inspectPatternCountIn(ticket, true)};
    } catch (error) {
      return {code: error.code ?? null, message: error.message, details: structuredClone(error.details ?? {})};
    }
  }, ticket);
  expect(result).toMatchObject({code: "HOST_STATE_INVALID"});
  return result;
}

export async function inspectOrdinary(page, sessionId) {
  const observed = await page.evaluate(async sessionId => {
    const proof = window.__creatorIoProof;
    const begin = proof.trace.length;
    const began = performance.now();
    const current = await proof.session.inspectPatternTransport(sessionId);
    const rows = proof.trace.slice(begin).filter(row => row.request.operation === "pattern.transport.inspect" &&
      row.request.payload.session_id === sessionId);
    if (rows.length !== 1 || rows[0].response?.ok !== true)
      throw new Error("ordinary SDK inspect must have exactly one actual Host response");
    return {raw: rows[0].response.result, current, elapsed: performance.now() - began};
  }, sessionId);
  const {raw, current, elapsed} = observed;
  const legacy = decodeLegacyPatternTransportStatus(raw); // Actual old-channel response only.
  const {observedAtMilliseconds: _oldTime, ...oldFields} = legacy;
  const {observedAtMilliseconds: _newTime, ...currentFields} = current;
  expect(currentFields, "old and current SDK decode the same unmodified real response").toEqual(oldFields);
  expect(elapsed, "inspect remains responsive while the actual I/O owner is held").toBeLessThan(1_000);
  return {raw, legacy, current, elapsed};
}

export async function beginPublicInput(page, name, kind) {
  await page.evaluate(async ({name, kind}) => {
    const proof = window.__creatorIoProof;
    const session = window.lmdjWebRuntimeHost.session;
    if (session !== proof.session) throw new Error("public input changed Session owner");
    const nativeBefore = await session.inspectPatternTransport(proof.sessionId);
    const call = {name, kind, nativeBefore: structuredClone(nativeBefore),
      began: performance.now(), state: "pending"};
    proof.calls[name] = call;
    const operation = kind === "press" ? session.trigger(0, 90, "pointer") : session.release(0, "pointer");
    operation.then(value => {call.state = "resolved"; call.value = structuredClone(value);},
      error => {call.state = "rejected"; call.error = {code: error.code ?? null,
        message: error.message, details: structuredClone(error.details ?? {})};})
      .finally(() => {call.ended = performance.now();});
  }, {name, kind});
}

export async function inputEvidence(page, kind) {
  return page.evaluate(kind => {
    const proof = window.__creatorIoProof;
    const rows = proof.trace.filter(row => row.request.operation === "pattern.transport.input.request" &&
      row.request.payload.kind === kind);
    const request = rows[0];
    const ticket = request?.response?.result?.ticket;
    const inspections = ticket ? proof.trace.filter(row => row.request.operation === "pattern.transport.input.inspect" &&
      row.request.payload.command_id === ticket.command_id && row.request.payload.ticket === ticket.ticket) : [];
    const statuses = [request, ...inspections].filter(Boolean).map(row => row.response?.result?.status ?? row.response?.result)
      .filter(value => value?.native_result !== undefined);
    return {requests: rows.length, request, ticket, inspections, statuses,
      latest: statuses.at(-1) ?? null,
      consumed: inspections.filter(row => row.request.payload.consume && row.response?.ok).map(row => row.response.result),
      call: proof.calls[kind]};
  }, kind);
}

export function expectNativeOwner(input, ticket, {releaseOf = null, disposition}) {
  expect(input.requests, "one physical input enqueued once, with no expiry replay").toBe(1);
  expect(input.request.response.ok).toBe(true);
  const status = input.latest;
  expect(status.ticket).toEqual(input.ticket);
  expect(status.native_result).toMatchObject({runtime_generation: ticket.runtimeGeneration,
    frame_epoch: ticket.frameEpoch, sequence: status.admission.sequence,
    acceptance_ordinal: status.admission.acceptance_ordinal, held_press_sequence: releaseOf,
    slot: 0, disposition, authority: {recording: true,
      schedule_serial: ticket.scheduleSerial, transport_epoch: "1"}});
  expect(status.native_result.authority).toEqual(status.admission.authority);
  expect(status.native_result.runtime_frame).toBeGreaterThanOrEqual(0);
  return status.native_result;
}

export async function cancelCountIn(page, setup, ticket, intent = "record") {
  return page.evaluate(({setup, ticket, intent}) =>
    window.lmdjWebRuntimeHost.session.cancelPatternCountIn({ticket, projectId: setup.projectId,
      commandId: crypto.randomUUID(), expectedEpoch: "2", intent}), {setup, ticket, intent});
}

export async function projectInventory(page, projectId, sealedPath = null) {
  return page.evaluate(async ({projectId, sealedPath}) => {
    const root = await navigator.storage.getDirectory();
    const bundle = await (await root.getDirectoryHandle("projects")).getDirectoryHandle(`${projectId}.lmdj`);
    const files = [];
    const sha = async bytes => [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
      .map(value => value.toString(16).padStart(2, "0")).join("");
    async function visit(directory, prefix) {
      for await (const [name, entry] of directory.entries()) {
        const path = prefix + name;
        if (entry.kind === "directory") await visit(entry, path + "/");
        else {
          const bytes = new Uint8Array(await (await entry.getFile()).arrayBuffer());
          const descriptor = {path, bytes: bytes.length, sha256: await sha(bytes)};
          if (path.endsWith("/sequence.jsonl") || path === sealedPath) {
            descriptor.text = new TextDecoder("utf-8", {fatal: true}).decode(bytes);
          }
          files.push(descriptor);
        }
      }
    }
    await visit(bundle, "");
    files.sort((a, b) => a.path.localeCompare(b.path));
    return {files, sha256: await sha(new TextEncoder().encode(JSON.stringify(files))),
      totalBytes: files.reduce((total, file) => total + file.bytes, 0)};
  }, {projectId, sealedPath});
}

export function canonical(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
}

export function checkedWholeJournal(inventory) {
  const journal = inventory.files.find(file => file.path === JOURNAL_PATH);
  expect(journal, "read the whole real Journal; absence is not a valid prefix").toBeDefined();
  const bytes = Buffer.from(journal.text, "utf8");
  expect(bytes.length).toBe(journal.bytes);
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(journal.sha256);
  expect(journal.text.endsWith("\n"), "complete Journal has no torn suffix").toBe(true);
  const lines = journal.text.slice(0, -1).split("\n");
  expect(lines.length).toBeGreaterThan(0);
  return lines.map(line => {
    const record = JSON.parse(line);
    expect(Object.keys(record).sort()).toEqual(["checksum", "payload"]);
    expect(canonical(record)).toBe(line);
    expect(createHash("sha256").update(canonical(record.payload)).digest("hex")).toBe(record.checksum);
    return record.payload;
  });
}

export function checkedDeadlineOpeningJournal(inventory, writtenBeforeFlush, setup, start) {
  const records = checkedWholeJournal(inventory);
  const pattern = setup.baseline.patterns[setup.patternId];
  expect(pattern.events).toEqual([]);
  const identity = {operation_id: start.admitted.ticket.commandId,
    runtime_generation: Number(start.admitted.ticket.runtimeGeneration), transport_epoch: 1};
  const generation = Number(start.applied.startReceipt.patternGeneration);
  expect(Number.isSafeInteger(identity.runtime_generation)).toBe(true);
  expect(Number.isSafeInteger(generation)).toBe(true);
  const begin = {armed_capture_slot: null, bars: pattern.bars, contract: "lmdj.sequence.journal.v3",
    expected_revision: setup.baseline.revision, kind: "begin",
    pattern_fingerprint: createHash("sha256").update(canonical({bars: pattern.bars, events: []})).digest("hex"),
    pattern_id: setup.patternId, session_id: setup.sessionId};
  const preparation = {identity, project_id: setup.projectId, pattern_id: setup.patternId,
    publication_generation: generation, first_watermark: 10, candidate_limit: 1024,
    candidate_byte_limit: 1024 * 1024, fence_timeout_ms: 5000, quantize_enabled: false, swing_percent: 50};
  const closure = {last_retained_watermark: null, reason: 2}; // SequenceAdmissionCloseReason::deadline.
  expect(checkedWholeJournal(writtenBeforeFlush), "the exact held begin survives the real flush").toEqual([begin]);
  expect(records, "whole failed opening Journal has no admission/cutoff fence, candidate, transfer or publication").toEqual([
    begin,
    {kind: "admission-prepare", session_id: setup.sessionId, identity, data: preparation},
    {kind: "admission-close", session_id: setup.sessionId, identity, data: closure},
  ]);
  // This is the complete snapshot implied by those checked records. Native
  // e1/F stay separate; an opening refusal has no durable admission fence.
  const expectedJournal = {admission: {preparation, candidates: [], admission_fence: null,
    cutoff_fence: null, closure, transfers: [], applied_switches: [], segment_generation: generation,
    published_generation: 0, completed: false, timing_profiles: []},
    armed_capture_slot: null, bars: begin.bars, capture_commit: null,
    expected_revision: begin.expected_revision, flushes: [], last_input_sequence: null,
    next_flush_seq: 0, next_tail_seq: 0, pattern_fingerprint: begin.pattern_fingerprint,
    pattern_id: setup.patternId, pending_events: [], session_id: setup.sessionId, state: "active"};
  return {records, expectedJournal};
}

export async function checkpoint(page, name, value) {
  await page.evaluate(({name, value}) => window.__creatorIoProof.checkpoints.push({name, value, at: performance.now()}),
    {name, value});
}

export async function reopenExact(page, setup, truth, inventory, report) {
  await checkpoint(page, "complete-before-reopen", {truth, inventory});
  const before = await collectProof(page);
  if (report) report.proofBeforeReload = before;
  await restoreTrace(page);
  await page.reload();
  await waitForProjectReopen(page, setup.projectId.slice(0, 8));
  const reopenedTruth = await inspectTruth(page);
  const reopenedInventory = await projectInventory(page, setup.projectId);
  expect(reopenedTruth, "reopened entire Truth and exact revision").toEqual(truth);
  expect(reopenedInventory, "reopened entire OPFS file inventory/lengths/SHA").toEqual(inventory);
  return {before, reopenedTruth, reopenedInventory};
}

export async function reopenDeadlineRecovery(page, setup, {truth, inventory, journal}, report) {
  expect(truth).toEqual(setup.baseline);
  expect(journal.state).toBe("active");
  expect(journal.session_id).toBe(setup.sessionId);
  const sealedPath = `recovery/sealed/${setup.sessionId}-owner_lost.json`;
  expect(inventory.files.filter(file => file.path === JOURNAL_PATH)).toHaveLength(1);
  expect(inventory.files.filter(file => file.path.startsWith(`recovery/sealed/${setup.sessionId}`)),
    "no earlier sealed candidate may collide with the original session").toEqual([]);
  const payload = {contract: "lmdj.sequence.recovery.v3",
    journal: {...journal, state: "owner_lost"}, reason: "owner_lost"};
  const checksum = createHash("sha256").update(canonical(payload)).digest("hex");
  const text = canonical({checksum, payload}) + "\n";
  const sealed = {path: sealedPath, bytes: Buffer.byteLength(text, "utf8"),
    sha256: createHash("sha256").update(text).digest("hex"), text};
  const files = [...inventory.files.filter(file => file.path !== JOURNAL_PATH), sealed]
    .sort((a, b) => a.path.localeCompare(b.path));
  const expectedInventory = {files,
    sha256: createHash("sha256").update(JSON.stringify(files)).digest("hex"),
    totalBytes: files.reduce((total, file) => total + file.bytes, 0)};
  const candidate = {sessionId: setup.sessionId, patternId: setup.patternId, bars: journal.bars,
    reason: "owner_lost", eventCount: 0};
  await checkpoint(page, "complete-failed-owner-before-reopen", {truth, inventory, journal});
  const before = await collectProof(page);
  if (report) report.proofBeforeReload = before;
  const reopen = async name => {
    await restoreTrace(page);
    await page.reload();
    await waitForProjectReopen(page, setup.projectId.slice(0, 8));
    await installTrace(page);
    let recovery;
    // The new public Session lists actual recovery. Project load alone is
    // not a seal; this runs the real owner-loss reconciliation path.
    await expect.poll(async () => {
      recovery = await page.evaluate(projectId =>
        window.lmdjWebRuntimeHost.session.listSequenceRecovery(projectId), setup.projectId);
      return recovery;
    }, {timeout: 5_000, intervals: [10]}).toEqual([candidate]);
    const reopenedTruth = await inspectTruth(page);
    const reopenedInventory = await projectInventory(page, setup.projectId, sealedPath);
    const actualSealed = reopenedInventory.files.find(file => file.path === sealedPath);
    expect(actualSealed, "complete canonical checked recovery bytes match every original Journal field").toEqual(sealed);
    const actualRecord = JSON.parse(actualSealed.text);
    expect(Object.keys(actualRecord).sort()).toEqual(["checksum", "payload"]);
    expect(actualRecord.payload).toEqual(payload);
    expect(actualRecord.checksum).toBe(createHash("sha256").update(canonical(actualRecord.payload)).digest("hex"));
    expect(reopenedTruth, "owner loss creates no Truth event or revision").toEqual(truth);
    expect(reopenedInventory, "only the original active Journal becomes one exact sealed owner_lost artifact").toEqual(expectedInventory);
    await checkpoint(page, name, {recovery, truth: reopenedTruth, inventory: reopenedInventory});
    return {recovery, reopenedTruth, reopenedInventory, proof: await collectProof(page)};
  };
  const first = await reopen("first-reopen-exact-deadline-owner-loss-recovery");
  if (report) report.firstRecoveryReopen = first;
  const second = await reopen("second-reopen-stable-deadline-owner-loss-recovery");
  expect(second.recovery, "second reopen offers the same single original candidate").toEqual(first.recovery);
  expect(second.reopenedTruth).toEqual(first.reopenedTruth);
  expect(second.reopenedInventory, "second reopen cannot add another seal or change any byte").toEqual(first.reopenedInventory);
  return {before, first, second};
}

export async function collectProof(page) {
  return page.evaluate(() => {
    const proof = window.__creatorIoProof;
    return proof ? {startup: proof.startup, trace: proof.trace, calls: proof.calls,
      checkpoints: proof.checkpoints} : {scope: "startup did not reach proof owner"};
  });
}

export async function restoreTrace(page) {
  await page.evaluate(() => window.__creatorIoProof?.restore()).catch(() => {});
}
