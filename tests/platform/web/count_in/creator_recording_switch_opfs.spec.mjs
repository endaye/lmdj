import {writeFile} from "node:fs/promises";
import {expect, test} from "@playwright/test";
import {
  JOURNAL_PATH, checkedWholeJournal, collectProof, gate,
  inspectTruth, installNativeNodeWitness, prepareProductionProject,
  projectInventory, rebindProductionProof, releaseGateFinally, sendHost,
} from "./fixtures/production_io.mjs";
import {waitForProjectReopen} from "../creator/fixtures/creator_boot.mjs";
import {showSequenceLayer, sequencePattern} from "../creator/fixtures/creator_navigation.mjs";
import {wakeAudioWithPad} from "../creator/fixtures/creator_audio.mjs";
import {pcm16Wav} from "../creator/fixtures/perform_helpers.mjs";

const key = (page, name) => page.getByTestId("physical-controls").getByRole("button", {name});
const record = page => key(page, /^Record\b/);
const stop = page => key(page, /^Play\/Stop/);
const picker = page => page.getByRole("button", {name: "Choose Pattern", exact: true});
const trace = page => page.evaluate(() => window.__creatorIoProof.trace);

async function retain(testInfo, name, value) {
  const path = testInfo.outputPath(`${name}.json`);
  await writeFile(path, JSON.stringify(value, null, 2));
  await testInfo.attach(name, {path, contentType: "application/json"});
}

async function prepare(page, bars) {
  const setup = await prepareProductionProject(page);
  let truth = await inspectTruth(page);
  const bytes = pcm16Wav();
  const token = await page.evaluate(() => crypto.randomUUID());
  const sha = await page.evaluate(async values => [...new Uint8Array(
    await crypto.subtle.digest("SHA-256", Uint8Array.from(values)))]
    .map(value => value.toString(16).padStart(2, "0")).join(""), [...bytes]);
  await sendHost(page, "sample.import.begin", {import_token: token,
    command_id: await page.evaluate(() => crypto.randomUUID()), expected_revision: truth.revision,
    slot: {bank: 0, pad: 1}, asset_id: await page.evaluate(() => crypto.randomUUID()), byte_length: bytes.length});
  await sendHost(page, "sample.import.chunk", {import_token: token, offset: 0, final: true,
    sidecar: {sidecar_bytes: bytes.length, sidecar_sha256: sha}}, [...bytes]);
  await sendHost(page, "sample.import.commit", {import_token: token});
  // Loop Gate prevents natural sample expiry from standing in for either
  // physical Release across the two real Native boundaries.
  for (const pad of [0, 1]) {
    truth = await inspectTruth(page);
    await sendHost(page, "sample.update_pad", {command_id: await page.evaluate(() => crypto.randomUUID()),
      expected_revision: truth.revision, slot: {bank: 0, pad}, playback: {
        trim_start_frame: 0, trim_end_frame: 4800, trigger_mode: "loop_gate", gain_millidb: 0, muted: false,
      }});
  }
  const patterns = [setup.patternId];
  for (let index = 0; index < 3; index += 1) {
    const id = await page.evaluate(() => crypto.randomUUID());
    truth = await inspectTruth(page);
    await sendHost(page, "pattern.create", {command_id: await page.evaluate(() => crypto.randomUUID()),
      expected_revision: truth.revision, pattern_id: id, bars: 1});
    patterns.push(id);
  }
  for (const [slot, id] of patterns.entries()) {
    truth = await inspectTruth(page);
    if (truth.pattern_slots[slot] !== id) await sendHost(page, "pattern.slot.assign", {
      command_id: await page.evaluate(() => crypto.randomUUID()), expected_revision: truth.revision,
      pattern_slot: slot, pattern_id: id,
    });
  }
  // Public setup advanced Truth; the genuine App must reopen its current
  // projection before any user mutation. No revision guard is bypassed.
  await page.reload();
  await waitForProjectReopen(page, setup.projectId.slice(0, 8));
  await wakeAudioWithPad(page, {padAddress: "A01"});
  const startup = await rebindProductionProof(page);
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await picker(page).click();
  await page.getByRole("dialog", {name: "Choose Pattern"})
    .locator(`[data-pattern-choice="${setup.patternId}"]`).click();
  await showSequenceLayer(page, "SETUP");
  await page.getByRole("group", {name: "Count-in", exact: true})
    .getByRole("button", {name: bars ? "Count-in 1 bar" : "Count-in Off", exact: true}).click();
  // Keep the original C4 BAR window: admit the claimed predecessor and its
  // successor before the first segment write is held, then observe both S.
  await page.getByRole("group", {name: "Sequence snap"})
    .getByRole("button", {name: "1 BAR", exact: true}).click();
  await showSequenceLayer(page, "EDIT");
  const baseline = await inspectTruth(page);
  for (const id of patterns) expect(baseline.patterns[id]).toEqual({bars: 1, events: []});
  await page.evaluate(() => { window.__creatorIoProof.trace.length = 0; });
  return {...setup, patterns, baseline, startup, inventory: await projectInventory(page, setup.projectId)};
}

async function inspectCreator(page, sessionId) {
  const value = await page.evaluate(async sessionId => {
    const host = window.lmdjWebRuntimeHost;
    const proof = window.__creatorIoProof;
    const began = performance.now();
    const status = await proof.session.inspectPatternTransport(sessionId);
    const nodes = window.__creatorIoNativeNodes.filter(node =>
      node.context === host.session.monitorDestination().context);
    return {status, elapsed: performance.now() - began,
      owner: {sameSession: host.session === proof.session, frozen: Object.isFrozen(host.session),
        nativeNodes: nodes.length, sameNative: nodes[0] === proof.native}};
  }, sessionId);
  // Actual SDK return, not a guessed concurrent RPC. Original three cases
  // retain their separate legacy/current decode comparison unchanged.
  expect(value.elapsed, "ordinary inspect keeps its original one-second budget").toBeLessThan(1_000);
  expect(value.owner).toEqual({sameSession: true, frozen: true, nativeNodes: 1, sameNative: true});
  return value;
}

async function observedInput(page, kind, index, predicate) {
  let evidence;
  await expect.poll(async () => {
    const all = await trace(page);
    const admitted = all.filter(row => row.request.operation === "pattern.transport.input.request" &&
      row.request.payload.kind === kind)[index];
    const ticket = admitted?.response?.result?.ticket;
    if (!ticket) return false;
    const inspections = all.filter(row => row.request.operation === "pattern.transport.input.inspect" &&
      row.request.payload.command_id === ticket.command_id && row.request.payload.ticket === ticket.ticket && row.response?.ok);
    const statuses = [admitted.response.result.status, ...inspections.map(row => row.response.result)];
    evidence = {admitted, inspections, statuses, latest: statuses.at(-1),
      consumed: inspections.filter(row => row.request.payload.consume).map(row => row.response.result)};
    return predicate(evidence);
  }, {timeout: 1_000, intervals: [10]}).toBe(true);
  return evidence;
}

async function choose(page, target) {
  await picker(page).click();
  await page.getByRole("dialog", {name: "Choose Pattern"})
    .locator(`[data-pattern-choice="${target}"]`).click();
}

async function switchGesture(page, target, gesture) {
  const before = (await trace(page)).filter(row => row.request.operation === "pattern.transport.switch").length;
  await gesture();
  let request;
  await expect.poll(async () => {
    request = (await trace(page)).filter(row => row.request.operation === "pattern.transport.switch")[before];
    return request?.response !== undefined || request?.error !== undefined;
  }, {timeout: 1_000, intervals: [10]}).toBe(true);
  expect(request.error).toBeUndefined();
  expect(request.request.payload).toMatchObject({pattern_id: target, snap: "bar"});
  return request;
}

async function admitSwitchGesture(page, sessionId, source, target, gesture) {
  // Reuse C4's existing explicit-gesture policy. A genuine pending overlay is
  // a refusal, not an admission or permission for the SDK to replay a choice.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await expect.poll(async () => {
      const status = (await inspectCreator(page, sessionId)).status;
      if (!status.playing || status.currentPatternId !== source || status.pendingSwitch !== null) return false;
      const phase = (status.runtimeFrame - status.originFrame) % 96_000;
      return phase >= 0 && phase < 19_200;
    }, {timeout: 5_000, intervals: [20]}).toBe(true);
    const row = await switchGesture(page, target, gesture);
    if (row.response.ok) return row;
    expect(row.response.error).toMatchObject({code: "HOST_STATE_INVALID", details: {pending: true}});
    expect(["recording_switch_preparation_pending", "recording_switch_material_pending",
      "recording_switch_overlay_pending"]).toContain(row.response.error.details.reason);
    const count = (await trace(page)).filter(row => row.request.operation === "pattern.transport.switch").length;
    await page.waitForTimeout(250);
    expect((await trace(page)).filter(row => row.request.operation === "pattern.transport.switch")).toHaveLength(count);
    if (attempt === 2) throw new Error(`Pattern remains unavailable: ${JSON.stringify(row.response.error)}`);
  }
}

async function current(page, sessionId, target, pending = null) {
  let result;
  await expect.poll(async () => {
    result = await inspectCreator(page, sessionId);
    return result.status.currentPatternId === target &&
      (pending === null ? result.status.pendingSwitch === null : result.status.pendingSwitch?.patternId === pending);
  }, {timeout: 5_000, intervals: [20]}).toBe(true); // Original C4 actual-apply bound; each inspect keeps 1s.
  expect(result.status.error).toBeNull();
  return result;
}

function heldEvent(records, input, slot, origin) {
  const native = input.latest.native_result;
  const candidates = records.filter(row => row.kind === "admission-candidate" &&
    String(row.data.press_sequence) === native.sequence && Number(row.data.kind) === 0);
  expect(candidates).toHaveLength(1);
  const candidate = candidates[0];
  expect(candidate.data.slot).toEqual({bank: 0, pad: slot});
  expect(candidate.data.velocity).toBe(100);
  const frame = BigInt(candidate.data.runtime_frame);
  expect(frame).toBeGreaterThanOrEqual(BigInt(origin));
  // Independent absolute 48kHz/120BPM oracle. Consumer/SDK agreement alone
  // could preserve a shared wrong segment origin or leaked source Release.
  const onset = Number(((frame - BigInt(origin)) / 25n) % 3840n);
  return {slot: {bank: 0, pad: slot}, onset_tick: onset,
    duration_tick: Math.min(240, 3840 - onset), velocity: 100};
}

for (const bars of [0, 1]) for (const intent of ["record", "play_stop"])
  test(`Creator ${bars ? "COUNT-IN" : "immediate"} two switches retain real held segment I/O through ${intent} and reopen`, async ({page}, testInfo) => {
    const report = {scope: "conformance-only real Creator gestures and original segment flush", bars, intent};
    const failures = [];
    page.on("pageerror", error => failures.push({message: error.message, stack: error.stack}));
    await installNativeNodeWitness(page);
    try {
      const setup = report.setup = await prepare(page, bars);
      const [a, b, c, d] = setup.patterns;
      await record(page).click();
      let start;
      await expect.poll(async () => {
        start = (await trace(page)).find(row => row.request.operation ===
          (bars ? "pattern.transport.count-in.request" : "pattern.transport.request"));
        return start?.response?.ok === true;
      }, {timeout: 1_000, intervals: [10]}).toBe(true);
      setup.sessionId = start.request.payload.session_id;
      report.start = start;
      await expect(record(page)).toHaveClass(/is-active/, {timeout: 5_000});
      await expect(picker(page)).toBeEnabled({timeout: 5_000});
      const initial = report.initial = await inspectCreator(page, setup.sessionId);
      expect(initial.status).toMatchObject({playing: true, recording: true, currentPatternId: a});
      await page.keyboard.down("KeyZ");
      const source = report.source = await observedInput(page, "press", 0, value => value.consumed.length === 1);
      expect(source.latest).toMatchObject({complete: true, retained: true, durable_settled: true, error: null,
        native_result: {slot: 0, disposition: "voice_started"}});
      const authority = bars ? {recording: true, schedule_serial: start.request.payload.schedule_serial,
        transport_epoch: start.request.payload.expected_epoch}
        : {recording: false, schedule_serial: null, transport_epoch: null};
      expect(source.latest.native_result.authority).toEqual(authority);
      expect(await gate(page, 4), "old observer cannot select the actual segment append").toBe(1);
      const first = report.firstSwitch = await admitSwitchGesture(page, setup.sessionId, a, b, () => choose(page, b));
      expect(first.response).toMatchObject({ok: true, result: {pattern_id: b}});
      // The successor must be prepared before the actual segment worker is
      // held. Real B then C apply independently of that blocked worker.
      // Workspace navigation legitimately releases held physical input.
      // Stay in Sequence so the two cross-S holds are real, not manufactured.
      const second = report.secondSwitch = await switchGesture(page, c, () => choose(page, c));
      expect(second.response).toMatchObject({ok: true, result: {pattern_id: c}});
      expect(second.response.result.activation_frame).toBeGreaterThan(first.response.result.activation_frame);
      const heldB = report.heldB = await current(page, setup.sessionId, b, c);
      await expect.poll(() => gate(page), {timeout: 1_000, intervals: [10]}).toBe(10);
      expect(heldB.status).toMatchObject({playing: true, recording: true, phase: "idle"});
      expect(heldB.status.originFrame).toBe(first.response.result.activation_frame);
      const written = report.writtenBeforeFlush = await projectInventory(page, setup.projectId);
      const records = checkedWholeJournal(written);
      expect(records.at(-1)).toMatchObject({kind: "admission-switch",
        session_id: setup.sessionId, data: {pattern_id: b}});
      expect(await inspectTruth(page), "written switch bytes are not a committed source segment").toEqual(setup.baseline);
      await page.keyboard.down("KeyX");
      const target = report.target = await observedInput(page, "press", 1, value => value.latest?.native_result != null);
      expect(target.latest).toMatchObject({complete: false, durable_settled: false, retained: false,
        native_result: {slot: 1, disposition: "voice_started"}});
      expect(target.latest.native_result.authority).toEqual(authority);
      const heldC = report.heldC = await current(page, setup.sessionId, c);
      expect(heldC.status.originFrame).toBe(second.response.result.activation_frame);
      expect(heldC.status.originFrame).toBeGreaterThan(heldB.status.originFrame);
      expect(heldC.status.transportEpoch).toBe(initial.status.transportEpoch);
      await expect(sequencePattern(page)).toHaveAttribute("data-pattern-id", c);
      const refused = report.thirdSwitch = await switchGesture(page, d, () => choose(page, d));
      expect(refused.response).toMatchObject({ok: false, error: {code: "HOST_STATE_INVALID",
        details: {pending: true}}});
      // The Host may refuse preparation before the Core capacity check. Both
      // must precede any further Native admission; assert that far side too.
      expect(["recording_switch_capacity", "recording_switch_preparation_pending"])
        .toContain(refused.response.error.details.reason);
      const requestCount = (await trace(page)).filter(row => row.request.operation === "pattern.transport.switch").length;
      await page.waitForTimeout(250);
      expect((await trace(page)).filter(row => row.request.operation === "pattern.transport.switch")).toHaveLength(requestCount);
      const afterRefusal = report.afterThirdRefusal = await inspectCreator(page, setup.sessionId);
      expect(afterRefusal.status).toMatchObject({currentPatternId: c, pendingSwitch: null,
        publicationPending: false, originFrame: heldC.status.originFrame,
        transportEpoch: initial.status.transportEpoch, recording: true, playing: true});
      await page.keyboard.up("KeyZ");
      await page.keyboard.up("KeyX");
      const released = [];
      for (const [index, held] of [source, target].entries()) {
        const value = await observedInput(page, "release", index, row => row.latest?.native_result != null);
        expect(value.latest.native_result).toMatchObject({held_press_sequence: held.latest.native_result.sequence,
          slot: index, disposition: "release_applied"});
        expect(value.latest.native_result.runtime_frame).toBeGreaterThanOrEqual(heldC.status.originFrame);
        expect(value.latest.native_result.authority).toEqual(authority);
        expect(value.consumed).toEqual([]);
        released.push(value);
      }
      report.heldReleases = released;
      const began = await page.evaluate(() => performance.now());
      await (intent === "record" ? record(page) : stop(page)).click();
      let terminal, cutoff;
      await expect.poll(async () => {
        terminal = await inspectCreator(page, setup.sessionId);
        cutoff = await page.evaluate(() => {
          const text = Module.ccall("lmdj_web_audio_test_pattern_controller_io_cutoff", "string", [], []);
          return text ? JSON.parse(text) : null;
        });
        return cutoff !== null && terminal.status.playing === (intent === "record");
      }, {timeout: 1_000, intervals: [10]}).toBe(true);
      expect(await page.evaluate(() => performance.now()) - began).toBeLessThan(1_000);
      expect(cutoff).toMatchObject({runtime_generation: initial.status.runtimeGeneration,
        epoch: initial.status.transportEpoch + 1, pattern_id: c, origin_frame: heldC.status.originFrame,
        bpm: 120, playing: intent === "record"});
      for (const field of ["runtime_generation", "epoch", "effective_frame", "origin_frame", "pattern_generation", "bpm"])
        expect(Number.isSafeInteger(cutoff[field]), `exact Native cutoff ${field}`).toBe(true);
      expect(cutoff.effective_frame).toBeGreaterThanOrEqual(Math.max(
        ...released.map(value => value.latest.native_result.runtime_frame)));
      expect(terminal.status.recording, "Native F precedes durable Journal closure").toBe(true);
      expect(terminal.status.currentPatternId).toBe(c);
      expect(await gate(page)).toBe(10);
      report.nativeTerminalWhileHeld = terminal;
      report.actualNativeCutoff = cutoff;
      report.expiredReleases = [];
      for (let index = 0; index < 2; index += 1) report.expiredReleases.push(
        await observedInput(page, "release", index, row => row.latest?.expired === true));
      expect(await gate(page, 3)).toBe(1);
      await expect.poll(() => gate(page), {timeout: 1_000, intervals: [10]}).toBe(8);
      for (const [kind, index] of [["press", 1], ["release", 0], ["release", 1]]) {
        const settled = await observedInput(page, kind, index, row => row.consumed.length === 1);
        expect(settled.latest).toMatchObject({complete: true, durable_settled: true, error: null});
      }
      let closed;
      await expect.poll(async () => {
        closed = await inspectCreator(page, setup.sessionId);
        return closed.status.phase === "idle" && !closed.status.recording && !closed.status.publicationPending;
      }, {timeout: 5_000, intervals: [10]}).toBe(true);
      report.closed = closed;
      const expected = structuredClone(setup.baseline);
      expected.revision += 2;
      // Source input was durable before the held append. Independently copy
      // the selected worker's actual original target-admit request fields.
      const completeTrace = await trace(page);
      report.traceBeforeStop = completeTrace;
      const sourceEvent = heldEvent(records, source, 0, initial.status.originFrame);
      expected.patterns[a].events = [sourceEvent];
      const ingress = report.originalTargetIngress = await page.evaluate(() => {
        const observe = Module._lmdj_web_audio_test_pattern_controller_io_input;
        return {count: observe(0, 7), fields: Array.from({length: 7}, (_, field) => observe(0, field))};
      });
      expect(ingress.count, "one actual original target press-admit work").toBe(1);
      const [frame, correlation, bank, pad, generation, epoch, watermark] = ingress.fields;
      expect(ingress.fields.every(Number.isSafeInteger)).toBe(true);
      expect(correlation).toBe(Number(target.latest.native_result.sequence));
      expect([bank, pad, generation, epoch, watermark]).toEqual([0, 1,
        Number(target.latest.native_result.runtime_generation), initial.status.transportEpoch,
        Number(target.latest.native_result.acceptance_ordinal) + 9]);
      expect(frame).toBeGreaterThanOrEqual(heldB.status.originFrame);
      expect(frame).toBeLessThan(heldC.status.originFrame);
      expect(frame).toBeLessThanOrEqual(target.latest.native_result.runtime_frame);
      const onset = Math.floor((frame - heldB.status.originFrame) / 25) % 3840;
      expected.patterns[b].events = [{slot: {bank: 0, pad: 1}, onset_tick: onset,
        duration_tick: Math.min(240, 3840 - onset), velocity: 100}];
      expect(await inspectTruth(page), "complete per-Pattern Truth after every retained segment").toEqual(expected);
      if (bars) {
        await expect.poll(async () => (await trace(page)).some(row =>
          row.request.operation === "pattern.transport.count-in.inspect" && row.request.payload.consume && row.response?.ok),
        {timeout: 1_000, intervals: [10]}).toBe(true);
        const consumed = (await trace(page)).findLast(row => row.request.operation ===
          "pattern.transport.count-in.inspect" && row.request.payload.consume && row.response?.ok);
        expect(consumed.response.result.ticket).toEqual(start.response.result.ticket);
        expect(consumed.response.result.start_receipt).toMatchObject({pattern_id: a,
          origin_frame: initial.status.originFrame});
        expect(consumed.response.result.cancel_receipt).toMatchObject({pattern_id: a});
        expect(consumed.response.result.cancel_receipt.effective_frame).toBe(cutoff.effective_frame);
        expect(consumed.response.result.cancel_receipt.origin_frame).toBe(initial.status.originFrame);
        expect(String(consumed.response.result.start_receipt.pattern_generation)).not.toBe(String(cutoff.pattern_generation));
      }
      if (intent === "record") {
        await expect(stop(page)).toBeEnabled();
        await stop(page).click();
        await expect.poll(async () => (await inspectCreator(page, setup.sessionId)).status.playing,
          {timeout: 1_000, intervals: [10]}).toBe(false);
      }
      const inventory = report.finalInventory = await projectInventory(page, setup.projectId);
      expect(inventory.files.some(file => file.path === JOURNAL_PATH)).toBe(false);
      const assets = value => value.files.filter(file => file.path.startsWith("assets/"));
      expect(assets(inventory)).toEqual(assets(setup.inventory));
      report.expected = expected;
      report.proofBeforeReload = await collectProof(page);
      await page.reload();
      await waitForProjectReopen(page, setup.projectId.slice(0, 8));
      expect(await inspectTruth(page), "fresh reopen retains all Truth fields and exact revision").toEqual(expected);
      report.reopenedInventory = await projectInventory(page, setup.projectId);
      expect(report.reopenedInventory, "all OPFS paths, lengths and hashes survive reopen").toEqual(inventory);
    } finally {
      report.gateCleanup = await releaseGateFinally(page);
      report.finalProof = await collectProof(page).catch(error => ({error: String(error)}));
      report.pageErrors = failures;
      await retain(testInfo, "recording-switch-held-opfs", report);
      expect(failures, "the real Runtime does not trap").toEqual([]);
    }
  });

for (const bars of [0, 1])
  test(`Creator ${bars ? "COUNT-IN" : "immediate"} cold renderer restart recovers the original Pattern after a held switch`, async ({page, context}, testInfo) => {
    const report = {scope: "actual renderer crash and fresh OPFS recovery; conformance-only", bars};
    let fresh;
    await installNativeNodeWitness(page);
    try {
      const setup = report.setup = await prepare(page, bars);
      const [a, b] = setup.patterns;
      await record(page).click();
      let start;
      await expect.poll(async () => {
        start = (await trace(page)).find(row => row.request.operation ===
          (bars ? "pattern.transport.count-in.request" : "pattern.transport.request"));
        return start?.response?.ok === true;
      }, {timeout: 1_000, intervals: [10]}).toBe(true);
      const sessionId = start.request.payload.session_id;
      report.start = start;
      await expect(record(page)).toHaveClass(/is-active/, {timeout: 5_000});
      await expect(picker(page)).toBeEnabled({timeout: 5_000});
      const initial = report.initial = await inspectCreator(page, sessionId);
      await page.keyboard.down("KeyZ");
      const source = report.source = await observedInput(page, "press", 0, value => value.consumed.length === 1);
      expect(source.latest).toMatchObject({complete: true, retained: true, durable_settled: true, error: null,
        native_result: {slot: 0, disposition: "voice_started"}});
      const authority = bars ? {recording: true, schedule_serial: start.request.payload.schedule_serial,
        transport_epoch: start.request.payload.expected_epoch}
        : {recording: false, schedule_serial: null, transport_epoch: null};
      expect(source.latest.native_result.authority).toEqual(authority);
      expect(await gate(page, 4)).toBe(1);
      const chosen = report.switch = await admitSwitchGesture(page, sessionId, a, b, () => choose(page, b));
      expect(chosen.response).toMatchObject({ok: true, result: {pattern_id: b}});
      const applied = report.applied = await current(page, sessionId, b);
      expect(applied.status.originFrame).toBe(chosen.response.result.activation_frame);
      expect(applied.status.transportEpoch).toBe(initial.status.transportEpoch);
      await expect.poll(() => gate(page), {timeout: 1_000, intervals: [10]}).toBe(10);
      const written = report.beforeCrash = await projectInventory(page, setup.projectId);
      const records = checkedWholeJournal(written);
      expect(records.at(-1)).toMatchObject({kind: "admission-switch", session_id: sessionId,
        data: {pattern_id: b, frame: applied.status.originFrame}});
      const expected = report.expected = structuredClone(setup.baseline);
      expected.revision += 1;
      expected.patterns[a].events = [heldEvent(records, source, 0, initial.status.originFrame)];
      expect(await inspectTruth(page), "the held switch has not committed the source segment").toEqual(setup.baseline);
      report.originalProof = await collectProof(page);

      // Terminate the actual renderer with its I/O worker still in flush.
      // Do not release the gate or replay the old controller's work request.
      const cdp = await context.newCDPSession(page);
      const crashed = page.waitForEvent("crash", {timeout: 5_000});
      const crashCommand = cdp.send("Page.crash").catch(error => ({error: String(error)}));
      await crashed;
      report.rendererCrashed = true;
      await page.close();
      report.crashCommand = await crashCommand;
      fresh = await context.newPage();
      expect(fresh, "recovery starts in a different page/document").not.toBe(page);
      const freshErrors = [];
      fresh.on("pageerror", error => freshErrors.push({message: error.message, stack: error.stack}));
      await fresh.goto("/");
      await waitForProjectReopen(fresh, setup.projectId.slice(0, 8));
      report.coldTruth = await inspectTruth(fresh);
      report.coldInventory = await projectInventory(fresh, setup.projectId);
      const candidates = report.candidates = await fresh.evaluate(() =>
        window.lmdjWebRuntimeHost.session.listSequenceRecovery());
      expect(candidates).toHaveLength(1);
      expect(candidates[0]).toMatchObject({sessionId, patternId: a, reason: "owner_lost"});
      const prompt = fresh.getByRole("region", {name: "Interrupted recording"});
      await expect(prompt).toBeVisible({timeout: 60_000});
      await prompt.getByRole("button", {name: "Keep recording"}).click();
      await expect(prompt).toContainText("The interrupted recording is back in this Project.", {timeout: 60_000});
      const recovered = report.recoveredTruth = await inspectTruth(fresh);
      expect(recovered, "durable source data recovers once into A despite actual B before the crash").toEqual(expected);
      expect(await fresh.evaluate(() => window.lmdjWebRuntimeHost.session.listSequenceRecovery())).toEqual([]);
      const inventory = report.recoveredInventory = await projectInventory(fresh, setup.projectId);
      expect(inventory.files.some(file => file.path === JOURNAL_PATH)).toBe(false);
      const assets = value => value.files.filter(file => file.path.startsWith("assets/"));
      expect(assets(inventory)).toEqual(assets(setup.inventory));
      await fresh.reload();
      await waitForProjectReopen(fresh, setup.projectId.slice(0, 8));
      report.reopenedTruth = await inspectTruth(fresh);
      expect(report.reopenedTruth, "a further cold open keeps the complete recovered Truth and exact revision").toEqual(expected);
      report.reopenedInventory = await projectInventory(fresh, setup.projectId);
      expect(report.reopenedInventory, "all paths, lengths and hashes survive the repeated reopen").toEqual(inventory);
      expect(await fresh.evaluate(() => window.lmdjWebRuntimeHost.session.listSequenceRecovery())).toEqual([]);
      report.freshErrors = freshErrors;
      expect(freshErrors).toEqual([]);
    } finally {
      // A failed pre-crash assertion must not leave a live blocked worker.
      // After the real crash this is only cleanup, never a durability ACK.
      report.cleanup = page.isClosed() ? {originalPageClosed: true}
        : await releaseGateFinally(page);
      await retain(testInfo, "recording-switch-cold-recovery", report);
      if (fresh) await fresh.close();
    }
  });
