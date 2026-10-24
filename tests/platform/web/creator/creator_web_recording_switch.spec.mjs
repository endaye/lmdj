import {writeFile} from "node:fs/promises";
import {expect, test} from "@playwright/test";
import {waitForProjectReopen} from "./fixtures/creator_boot.mjs";
import {createSequencePattern, sequencePattern, showSequenceLayer} from "./fixtures/creator_navigation.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {prepareCountInProject, countInProjectInventory, readCountInJournal, sendCountInHost} from "./fixtures/count_in_helpers.mjs";
import {pcm16Wav, PROJECT_TRANSITION_TIMEOUT_MS} from "./fixtures/perform_helpers.mjs";

async function retainJson(testInfo, name, value) {
  const path = testInfo.outputPath(`${name}.json`);
  await writeFile(path, JSON.stringify(value, null, 2));
  await testInfo.attach(name, {path, contentType: "application/json"});
}

// An observer of the real shared transport. It never supplies an acknowledgement,
// changes a receipt, consumes another owner, or introduces another Session.
async function installTrace(page) {
  await page.addInitScript(() => {
    let exposed;
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get: () => exposed,
      set(host) {
        const original = host.transport;
        window.__recordingSwitchTrace = [];
        host.transport = new Proxy({}, {get(_target, key) {
          if (key === "send") return async (...args) => {
            const row = {request: structuredClone(args[0]), began: performance.now()};
            window.__recordingSwitchTrace.push(row);
            try {
              const response = await original.send(...args);
              row.response = structuredClone(response);
              return response;
            } catch (error) {
              row.error = {code: error.code ?? null, message: error.message};
              throw error;
            } finally {row.ended = performance.now();}
          };
          const value = Reflect.get(original, key, original);
          return typeof value === "function" ? value.bind(original) : value;
        }});
        exposed = host;
      },
    });
  });
}
const truth = async page => (await page.evaluate(() => window.lmdjWebRuntimeHost.inspection.inspectProject())).project;
const rows = (page, operation) => page.evaluate(operation =>
  window.__recordingSwitchTrace.filter(row => row.request.operation === operation), operation);
const key = (page, name) => page.getByTestId("physical-controls").getByRole("button", {name});
const record = page => key(page, /^Record\b/);
const stop = page => key(page, /^Play\/Stop/);
const picker = page => page.getByRole("button", {name: "Choose Pattern", exact: true});
const ordinary = (page, sessionId) => sendCountInHost(page, "pattern.transport.inspect", {session_id: sessionId});

async function prepare(page) {
  const setup = await prepareCountInProject(page, 120, {silentPattern: true});
  // A real loop-Gate voice stays owned across S until its original release;
  // a loaded browser cannot turn this into a naturally expired sample. Keep
  // production import, immutable material and exact release_applied proof.
  await page.evaluate(async bytes => {
    const host = window.lmdjWebRuntimeHost;
    const send = async (operation, payload, sidecar) => {
      const response = await host.transport.send({protocol_version: 1,
        request_id: crypto.randomUUID(), operation, payload},
        sidecar === undefined ? {} : {sidecar});
      if (!response.ok) throw new Error(`${operation}: ${JSON.stringify(response.error)}`);
      return response.result;
    };
    let inspected = await host.inspection.inspectProject();
    const pcm = Uint8Array.from(bytes);
    const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", pcm))]
      .map(value => value.toString(16).padStart(2, "0")).join("");
    const token = crypto.randomUUID();
    await send("sample.import.begin", {import_token: token, command_id: crypto.randomUUID(),
      expected_revision: inspected.project.revision, slot: {bank: 0, pad: 0},
      asset_id: crypto.randomUUID(), byte_length: pcm.byteLength});
    await send("sample.import.chunk", {import_token: token, offset: 0, final: true,
      sidecar: {sidecar_bytes: pcm.byteLength, sidecar_sha256: sha}}, pcm);
    await send("sample.import.commit", {import_token: token});
    inspected = await host.inspection.inspectProject();
    await send("sample.update_pad", {command_id: crypto.randomUUID(),
      expected_revision: inspected.project.revision, slot: {bank: 0, pad: 0}, playback: {
        trim_start_frame: 0, trim_end_frame: 240000, trigger_mode: "loop_gate", gain_millidb: 0, muted: false,
      }});
  }, [...pcm16Wav({frames: 240000})]);
  // Setup wrote through the public Host while the App retained its older
  // authoring revision. Reopen before a UI mutation; its revision guard must
  // keep refusing that stale view rather than the fixture bypassing it.
  await page.reload();
  await waitForProjectReopen(page, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await createSequencePattern(page, 1);
  await expect(sequencePattern(page)).toHaveAttribute("data-pattern-count", "2");
  const afterCreate = await truth(page);
  const ids = Object.keys(afterCreate.patterns);
  expect(ids).toHaveLength(2);
  const target = ids.find(id => id !== setup.patternId);
  expect(afterCreate.patterns[target]).toEqual({bars: 1, events: []});
  let latest = afterCreate;
  for (const [slot, id] of [[0, setup.patternId], [1, target]]) {
    if (latest.pattern_slots[slot] === id) continue;
    await sendCountInHost(page, "pattern.slot.assign", {
      command_id: await page.evaluate(() => crypto.randomUUID()),
      expected_revision: latest.revision, pattern_slot: slot, pattern_id: id,
    });
    latest = await truth(page);
    expect(latest.pattern_slots[slot]).toBe(id);
  }
  // A fresh real App projection sees the setup commands before recording.
  await page.reload();
  await waitForProjectReopen(page, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await wakeAudioWithPad(page, {padAddress: "A01"});
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await picker(page).click();
  await page.getByRole("dialog", {name: "Choose Pattern"})
    .locator(`[data-pattern-choice="${setup.patternId}"]`).click();
  await expect(sequencePattern(page)).toHaveAttribute("data-pattern-id", setup.patternId);
  await showSequenceLayer(page, "SETUP");
  // COUNT-IN is restored; this ordinary-recording journey explicitly chooses
  // Off. Its final trace must still contain no scheduled count-in request.
  const countInOff = page.getByRole("group", {name: "Count-in", exact: true})
    .getByRole("button", {name: "Count-in Off", exact: true});
  await countInOff.click();
  await expect(countInOff).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("group", {name: "Sequence snap"}).getByRole("button", {name: "1 BAR", exact: true}).click();
  await showSequenceLayer(page, "EDIT");
  return {...setup, target, baseline: await truth(page), inventory: await countInProjectInventory(page, setup.projectId)};
}

async function waitInput(page, setup, since, kind, authority, retained = true) {
  let completed;
  await expect.poll(async () => {
    const trace = await rows(page, "pattern.transport.input.request");
    const admitted = trace.slice(since).find(row => row.request.payload.kind === kind && row.response?.ok === true);
    if (!admitted) return false;
    const ticket = admitted.response.result.ticket;
    const matches = await rows(page, "pattern.transport.input.inspect");
    const consumed = matches.find(row => row.request.payload.consume === true &&
      row.request.payload.command_id === ticket.command_id && row.response?.ok === true);
    if (!consumed) return false;
    completed = {admitted, status: consumed.response.result};
    return true;
  }, {timeout: 1_000, intervals: [10]}).toBe(true);
  const {admitted, status} = completed;
  expect(status).toMatchObject({complete: true, retained, durable_settled: true, error: null});
  expect(status.ticket).toEqual(admitted.response.result.ticket);
  expect(status.admission).toEqual(admitted.response.result.status.admission);
  expect(status.admission.authority).toEqual(authority);
  expect(status.native_result.sequence).toBe(status.admission.sequence);
  expect(status.native_result.acceptance_ordinal).toBe(status.admission.acceptance_ordinal);
  expect(status.native_result.authority).toEqual(status.admission.authority);
  expect(status.native_result.disposition).toBe(kind === "press" ? "voice_started" : "release_applied");
  const native = status.native_result;
  if (!retained) return native;
  // Recording retains the original Host ingress frame. Native completion is
  // later queue consumption; crossing a callback can make those frames differ.
  // Derive exact Truth independently from the checksum-verified Journal input,
  // while preserving the genuine Native completion and correlation assertions.
  const records = await readCountInJournal(page, setup);
  const candidates = records.filter(record => record.kind === "admission-candidate" &&
    record.data.kind === (kind === "press" ? "0" : "1") &&
    record.data.press_sequence === (kind === "press" ? native.sequence : native.held_press_sequence));
  expect(candidates, "one durable candidate for this Native input identity").toHaveLength(1);
  const candidate = candidates[0];
  expect(candidate.session_id).toBe(setup.sessionId);
  expect(candidate.identity.runtime_generation).toBe(native.runtime_generation);
  expect(candidate.data.slot).toEqual({bank: "0", pad: "0"});
  expect(candidate.data.velocity).toBe(kind === "press" ? "100" : "0");
  await retainJson(test.info(), `recorded-${kind}-${native.sequence}`, {native, candidate});
  return {...native, recording_frame: candidate.data.runtime_frame};
}

async function press(page, setup, authority) {
  const since = (await rows(page, "pattern.transport.input.request")).length;
  await page.keyboard.down("KeyZ");
  return waitInput(page, setup, since, "press", authority);
}
async function release(page, setup, pressed, retained = true) {
  const since = (await rows(page, "pattern.transport.input.request")).length;
  await page.keyboard.up("KeyZ");
  const released = await waitInput(page, setup, since, "release", pressed.authority, retained);
  expect(released.held_press_sequence).toBe(pressed.sequence);
  expect(BigInt(released.acceptance_ordinal)).toBeGreaterThan(BigInt(pressed.acceptance_ordinal));
  return released;
}

async function earlyBar(page, sessionId, pattern) {
  await expect.poll(async () => {
    const status = await ordinary(page, sessionId);
    if (!status.playing || status.current_pattern_id !== pattern || status.pending_switch !== null) return false;
    const phase = (status.runtime_frame - status.origin_frame) % 96_000;
    return phase >= 0 && phase < 19_200;
  }, {timeout: 5_000, intervals: [20]}).toBe(true);
}
async function choose(page, target) {
  await picker(page).click();
  await page.getByRole("dialog", {name: "Choose Pattern"})
    .locator(`[data-pattern-choice="${target}"]`).click();
}
async function switchByGesture(page, sessionId, current, target, gesture) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await earlyBar(page, sessionId, current);
    const before = (await rows(page, "pattern.transport.switch")).length;
    await gesture();
    let row;
    await expect.poll(async () => {
      const requests = await rows(page, "pattern.transport.switch");
      row = requests[before];
      return row?.response !== undefined || row?.error !== undefined;
    }, {timeout: 1_000, intervals: [10]}).toBe(true);
    expect(row.error).toBeUndefined();
    expect(row.request.payload).toMatchObject({pattern_id: target, snap: "bar"});
    if (row.response.ok) return row;
    expect(row.response.error).toMatchObject({code: "HOST_STATE_INVALID", details: {pending: true}});
    expect(["recording_switch_preparation_pending", "recording_switch_capacity",
      "recording_switch_material_pending", "recording_switch_overlay_pending"])
      .toContain(row.response.error.details.reason);
    const refused = await ordinary(page, sessionId);
    expect(refused.current_pattern_id).toBe(current);
    expect(refused.recording).toBe(true);
    // A refused musical choice never becomes an automatic future request.
    await page.waitForTimeout(250);
    expect((await rows(page, "pattern.transport.switch")).length).toBe(before + 1);
    if (attempt === 2) throw new Error(`Pattern remains unavailable: ${JSON.stringify(row.response.error)}`);
    // The next iteration is another explicit user gesture at the next actual
    // early bar, not an SDK replay or fabricated Native boundary.
  }
}

async function applied(page, sessionId, target, queued) {
  let actual;
  await expect.poll(async () => {
    actual = await ordinary(page, sessionId);
    return actual.phase === "idle" && actual.recording && actual.playing &&
      actual.current_pattern_id === target && actual.pending_switch === null;
  }, {timeout: 5_000, intervals: [20]}).toBe(true);
  expect(actual.error).toBeNull();
  expect(actual.origin_frame).toBe(queued.activation_frame);
  return actual;
}
function eventFor(pressed, released, origin, bars, fallback = false) {
  const attack = (BigInt(pressed.recording_frame) - BigInt(origin)) / 25n;
  const onset = Number(attack % BigInt(bars * 3840));
  const duration = fallback ? 240 : Math.max(1,
    Number((BigInt(released.recording_frame) - BigInt(origin)) / 25n - attack));
  return {slot: {bank: 0, pad: 0}, onset_tick: onset,
    duration_tick: Math.min(duration, bars * 3840 - onset), velocity: 100};
}

for (const terminalB of [false, true]) test(`Creator S3 immediate recording switches GROOVE and Perform A-B-A${terminalB ? "-B" : ""} with exact Truth and reopen`,
  async ({page, browserName}, testInfo) => {
    test.skip(browserName !== "chromium");
    test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS + 40_000);
    const failures = [];
    page.on("pageerror", error => failures.push(error.message));
    await installTrace(page);
    const setup = await prepare(page);
    await record(page).click();
    let sessionId;
    await expect.poll(async () => {
      const requests = await rows(page, "pattern.transport.request");
      sessionId = requests.at(-1)?.request.payload.session_id;
      return typeof sessionId === "string";
    }).toBe(true);
    setup.sessionId = sessionId;
    await expect(record(page)).toHaveClass(/is-active/, {timeout: 5_000});
    await expect(picker(page)).toBeEnabled({timeout: 5_000});
    const initial = await ordinary(page, sessionId);
    expect(initial).toMatchObject({recording: true, playing: true, current_pattern_id: setup.patternId});
    const beforeInput = (await rows(page, "pattern.transport.input.request")).length;
    // Ordinary recording is bounded by the Facade's acknowledged fence. Its
    // Native input has no scheduled authority; retained=true below separately
    // proves real Core admission.
    const authority = {recording: false, schedule_serial: null, transport_epoch: null};
    await earlyBar(page, sessionId, setup.patternId);
    const first = await press(page, setup, authority);
    const firstSwitch = await switchByGesture(page, sessionId, setup.patternId, setup.target,
      () => choose(page, setup.target));
    expect(firstSwitch.response).toMatchObject({ok: true, result: {pattern_id: setup.target}});
    expect(firstSwitch.request.payload.snap).toBe("bar");
    const queuedB = firstSwitch.response.result;
    expect(first.runtime_frame).toBeLessThan(queuedB.activation_frame);
    await expect(picker(page)).toContainText("→");
    await expect(sequencePattern(page)).toHaveAttribute("data-pattern-id", setup.patternId);
    const currentB = await applied(page, sessionId, setup.target, queuedB);
    await expect(sequencePattern(page)).toHaveAttribute("data-pattern-id", setup.target);
    // The old prefix is already durable: this matching late release consumes
    // its real physical owner, with retained=false rather than another event.
    const oldRelease = await release(page, setup, first, false);
    expect(oldRelease.runtime_frame).toBeGreaterThanOrEqual(currentB.origin_frame);
    expect(oldRelease.authority).toEqual(first.authority);
    const aSaved = await truth(page);
    expect(aSaved.patterns[setup.target].events, "old release creates no target event").toEqual([]);
    expect(aSaved.patterns[setup.patternId].events).toEqual([
      eventFor(first, oldRelease, initial.origin_frame, setup.baseline.patterns[setup.patternId].bars, true),
    ]);
    const middle = await press(page, setup, authority);
    await page.waitForTimeout(40);
    const middleRelease = await release(page, setup, middle);
    expect(middle.runtime_frame).toBeGreaterThanOrEqual(currentB.origin_frame);
    // Ordinary Perform Launch joins the same global recording, not a second
    // Performance event journal. Its UI is a distinct consumer of the switch.
    await page.getByRole("button", {name: "Perform", exact: true}).click();
    const launch = page.getByRole("button", {name: /^Launch Pattern 1\b/});
    await expect(launch).toBeEnabled();
    const returnSwitch = await switchByGesture(page, sessionId, setup.target, setup.patternId,
      () => launch.click());
    expect(returnSwitch.response).toMatchObject({ok: true, result: {pattern_id: setup.patternId}});
    expect(returnSwitch.request.payload.snap).toBe("bar");
    const currentA = await applied(page, sessionId, setup.patternId, returnSwitch.response.result);
    expect((await rows(page, "performance.record.launch-request")).length).toBe(0);
    await page.getByRole("button", {name: "Sequence", exact: true}).click();
    await expect(sequencePattern(page)).toHaveAttribute("data-pattern-id", setup.patternId);
    const last = await press(page, setup, authority);
    await page.waitForTimeout(40);
    const lastRelease = await release(page, setup, last);
    const expected = structuredClone(setup.baseline);
    expected.revision += 3;
    expected.patterns[setup.target].events = [eventFor(middle, middleRelease, currentB.origin_frame, 1)];
    expected.patterns[setup.patternId].events = [
      eventFor(first, oldRelease, initial.origin_frame, expected.patterns[setup.patternId].bars, true),
      eventFor(last, lastRelease, currentA.origin_frame, expected.patterns[setup.patternId].bars),
    ].sort((a, b) => a.onset_tick - b.onset_tick);
    if (terminalB) {
      const finalSwitch = await switchByGesture(page, sessionId, setup.patternId, setup.target,
        () => choose(page, setup.target));
      expect(finalSwitch.response).toMatchObject({ok: true, result: {pattern_id: setup.target}});
      await applied(page, sessionId, setup.target, finalSwitch.response.result);
      await expect(sequencePattern(page)).toHaveAttribute("data-pattern-id", setup.target);
    }
    await record(page).click();
    let closed;
    await expect.poll(async () => {
      closed = await ordinary(page, sessionId);
      return closed.phase === "idle" && closed.playing && !closed.recording;
    }, {timeout: 5_000, intervals: [20]}).toBe(true);
    expect(closed.current_pattern_id).toBe(terminalB ? setup.target : setup.patternId);
    expect(await truth(page), "complete committed Project Truth after final segment").toEqual(expected);
    await expect(stop(page)).toBeEnabled();
    await stop(page).click();
    await expect.poll(async () => {
      const status = await ordinary(page, sessionId);
      return status.phase === "idle" && !status.playing && !status.recording;
    }, {timeout: 5_000, intervals: [20]}).toBe(true);
    expect(await truth(page), "Stop does not rewrite a committed segment").toEqual(expected);
    const inputs = (await rows(page, "pattern.transport.input.request")).slice(beforeInput);
    expect(inputs.map(row => row.request.payload.kind)).toEqual(["press", "release", "press", "release", "press", "release"]);
    expect((await rows(page, "pattern.transport.count-in.request")).length).toBe(0);
    const assetFiles = files => files.filter(file => file.path.startsWith("assets/"));
    expect(assetFiles(setup.inventory).length).toBeGreaterThan(0);
    const finalAssets = assetFiles(await countInProjectInventory(page, setup.projectId));
    expect(finalAssets).toEqual(assetFiles(setup.inventory));
    await retainJson(testInfo, "actual-recording-switch-authority", {
      setup, initial, first, oldRelease, currentB, middle, middleRelease, currentA,
      last, lastRelease, closed, expected, finalAssets,
      trace: await page.evaluate(() => window.__recordingSwitchTrace),
    });
    await page.reload();
    await waitForProjectReopen(page, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    const reopened = await truth(page);
    expect(reopened, "fresh reopen preserves complete committed Truth").toEqual(expected);
    await retainJson(testInfo, "recording-switch-reopened-truth", {expected, reopened});
    expect(failures).toEqual([]);
  });

test.afterEach(async ({page}, testInfo) => {
  const trace = await page.evaluate(() => window.__recordingSwitchTrace ?? null).catch(() => null);
  if (trace !== null) await retainJson(testInfo, "complete-recording-switch-transport-trace", trace);
});
