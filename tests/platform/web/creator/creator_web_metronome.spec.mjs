import {openCreatorSlice, showSamplePage, showPerformPage} from "./fixtures/creator_navigation.mjs";
import {selectedSequencePatternId, showSequenceLayer} from "./fixtures/creator_navigation.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {expect, test} from "./fixtures/refusal_diagnostics.mjs";
import {openProjectPageAfterBoot, waitForProjectReopen} from "./fixtures/creator_boot.mjs";
import {
  PROJECT_TRANSITION_TIMEOUT_MS,
  beginRecording,
  exportPerformanceWav,
  firstSignalFrame,
  installPerformWitnessSample,
  openPerform,
  parsePcm16StereoWav,
  stopRecording,
} from "./fixtures/perform_helpers.mjs";

import {
  armCountInPcm, attachCountInPcmObserver, countInProjectInventory,
  ensureCountInClock, expectCountInClock, expectCountInMixedCapture,
  expectForcedCountInPcm, inspectCountIn, installCountInAudioObserver,
  prepareCountInProject, readCountInJournal, readCountInPcm, sendCountInHost,
  startCountInMasterCapture, stopCountInMasterCapture,
  waitForCountInBoundary, waitForObservedFrame,
} from "./fixtures/count_in_helpers.mjs";

const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

// The documented observability seam: every click the metronome schedules
// dispatches lmdj:metronome-click with {contextTime, beat, accent}. Collecting
// the events is the far side of the scheduling loop — the contextTime is the
// exact AudioContext time the click was scheduled at, so cadence assertions
// read scheduled audio time, never timer jitter.
async function installMetronomeProof(page) {
  await page.addInitScript(() => {
    window.__metronomeClicks = [];
    window.addEventListener("lmdj:metronome-click", (event) => {
      window.__metronomeClicks.push({
        contextTime: event.detail?.contextTime ?? null,
        beat: event.detail?.beat ?? null,
        accent: event.detail?.accent ?? null,
      });
    });
  });
}

async function metronomeClicks(page) {
  return page.evaluate(() => window.__metronomeClicks ?? []);
}

async function observedFrame(page) {
  return page.evaluate(() => {
    const {header} = window.__countInPcm;
    return Atomics.load(header, 1) + Atomics.load(header, 2);
  });
}

// First observed frame from which both product planes stay exactly zero for
// at least 100 ms. A Gate that never stops times out here instead of passing.
async function waitForProductSilence(page, fromFrame, timeout) {
  let silentFrom;
  await expect.poll(async () => {
    const observed = await page.evaluate(fromFrame => {
      const {header, samples, capacity} = window.__countInPcm;
      const first = Atomics.load(header, 1);
      const frames = Atomics.load(header, 2);
      let quietFrom = Math.max(fromFrame, first);
      for (let frame = Math.max(0, fromFrame - first); frame < frames; ++frame)
        if (samples[frame] !== 0 || samples[capacity + frame] !== 0) quietFrom = first + frame + 1;
      return {quietFrom, end: first + frames};
    }, fromFrame);
    silentFrom = observed.quietFrom;
    return observed.end - observed.quietFrom >= 4_800;
  }, {timeout, intervals: [10], message: "held pre-S Gate release reaches the product output"}).toBe(true);
  return silentFrom;
}

async function importProject(page) {
  await openProjectPageAfterBoot(page);
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(bundle);
  // Boot already shows its own Project; wait for the imported one by name.
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

async function enterSequenceAndActivate(page) {
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  // The Sequence editor is one component in both layouts and names itself
  // "Sequence editor"; that region is the destination, whichever shell
  // mounts it.
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state"))
    .toHaveText("Audio running", {timeout: 30_000});
  // Tempo, Swing and the metronome switch live in the SETUP layer.
  await showSequenceLayer(page, "SETUP");
}

// Play/Stop and Record are the console's physical keys. Their accessible
// names carry their state, so they are addressed by prefix inside the
// physical column, which also keeps "Record Sample" and "Record Performance"
// out of reach.
const physicalKey = (page, name) =>
  page.getByTestId("physical-controls").getByRole("button", {name});
const playStopKey = (page) => physicalKey(page, /^Play\/Stop/);
const recordKey = (page) => physicalKey(page, /^Record\b/);
const metronomeToggle = (page) => page.getByRole("button", {name: "Metronome"});

const transportStatus = (page, text) =>
  expect(page.getByRole("status").filter({
    has: page.getByTestId("creator-phase"), hasText: text,
  }))
    .toBeVisible({timeout: 30_000});

async function inspectTruth(page) {
  const response = await page.evaluate(() =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "project.inspect",
      payload: {},
    }));
  expect(response.ok).toBe(true);
  return response.result.project;
}

// The device-level far side of the preference: the raw stored value in the
// Host settings store, read in the page.
async function readStoredMetronomePreference(page) {
  return page.evaluate(() => new Promise((resolve) => {
    const request = indexedDB.open("lmdj.creator.host", 1);
    request.onerror = () => resolve(null);
    request.onsuccess = () => {
      const database = request.result;
      try {
        const get = database.transaction("settings", "readonly")
          .objectStore("settings").get("metronome.v1");
        get.onsuccess = () => {
          database.close();
          resolve(get.result ?? null);
        };
        get.onerror = () => {
          database.close();
          resolve(null);
        };
      } catch {
        database.close();
        resolve(null);
      }
    };
  }));
}

test("metronome clicks follow the beat grid while playing and stop with playback", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installMetronomeProof(page);
  await page.goto("/index.html");
  await importProject(page);
  const truth = await inspectTruth(page);
  await enterSequenceAndActivate(page);

  const toggle = metronomeToggle(page);
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");

  await playStopKey(page).click();
  await transportStatus(page, "playing");
  await expect.poll(async () => (await metronomeClicks(page)).length,
    {timeout: 30_000}).toBeGreaterThanOrEqual(8);

  const clicks = await metronomeClicks(page);
  const intervalSeconds = 60 / truth.bpm;
  // Far side: the scheduled context times sit on the beat grid. Frame
  // quantization is the only admitted error, far below the 10% bound.
  for (let index = 1; index < clicks.length; index += 1) {
    const delta = clicks[index].contextTime - clicks[index - 1].contextTime;
    expect(delta).toBeGreaterThan(intervalSeconds * 0.9);
    expect(delta).toBeLessThan(intervalSeconds * 1.1);
  }
  for (const click of clicks) {
    expect(click.accent).toBe(click.beat % 4 === 0);
  }
  expect(clicks.some((click) => click.accent === true)).toBe(true);

  // Stopping playback stops the loop: past the 120 ms scheduling horizon no
  // new click can be scheduled.
  await playStopKey(page).click();
  await transportStatus(page, "stopped");
  await page.waitForTimeout(600);
  const atStop = (await metronomeClicks(page)).length;
  await page.waitForTimeout(400);
  expect((await metronomeClicks(page)).length).toBe(atStop);
});

test("metronome keeps clicking while recording and leaves Pattern truth untouched", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installMetronomeProof(page);
  await page.goto("/index.html");
  await importProject(page);
  await enterSequenceAndActivate(page);
  const patternId = await selectedSequencePatternId(page);

  await metronomeToggle(page).click();
  await playStopKey(page).click();
  await transportStatus(page, "playing");
  await expect.poll(async () => (await metronomeClicks(page)).length,
    {timeout: 30_000}).toBeGreaterThanOrEqual(2);
  const baseline = await inspectTruth(page);

  await recordKey(page).click();
  await transportStatus(page, "recording");
  // The toggle is not covered by the transport recording disable, and the
  // clicks keep flowing while recording is open.
  await expect(metronomeToggle(page)).toBeEnabled();
  const atRecord = (await metronomeClicks(page)).length;
  await expect.poll(async () => (await metronomeClicks(page)).length,
    {timeout: 30_000}).toBeGreaterThan(atRecord + 1);

  await recordKey(page).click();
  await transportStatus(page, "playing");
  // Far side: the metronome is no input — the Pattern's events in Truth are
  // exactly what they were before the recording.
  const after = await inspectTruth(page);
  expect(after.patterns[patternId].events)
    .toEqual(baseline.patterns[patternId].events);
});

test("metronome never enters the Perform capture; the witness sample proves the chain records signal", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(420_000);
  await installMetronomeProof(page);
  await page.goto("/index.html");
  await importProject(page);
  await enterSequenceAndActivate(page);
  await installPerformWitnessSample(page);

  // The playing Pattern is empty, so the master output is silent apart from
  // anything the metronome would leak into the tap.
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  await showSequenceLayer(page, "SETUP");
  await metronomeToggle(page).click();
  await playStopKey(page).click();
  await transportStatus(page, "playing");

  await openPerform(page);
  await beginRecording(page);
  // Clicks keep flowing while the Perform recording runs — no Pad is
  // triggered, so the tap should hear nothing at all.
  await expect.poll(async () => (await metronomeClicks(page)).length,
    {timeout: 30_000}).toBeGreaterThanOrEqual(2);
  await stopRecording(page);
  const silentWav = parsePcm16StereoWav(await exportPerformanceWav(page));
  expect(silentWav.frames).toBeGreaterThan(0);
  // Far side: digital silence on both channels for every frame — the click
  // routed straight to the destination never reached the tap. The peak over
  // every frame asserts the same fact as per-sample expects without millions
  // of matcher invocations (a per-sample loop starved the worker for tens of
  // minutes on longer recordings).
  let peak = 0;
  for (const sample of silentWav.left) peak = Math.max(peak, Math.abs(sample));
  for (const sample of silentWav.right) peak = Math.max(peak, Math.abs(sample));
  expect(peak).toBeLessThanOrEqual(2);

  await showPerformPage(page, "Takes");
  await page.getByRole("button", {name: "Discard Performance"}).click();
  await expect(page.getByRole("status", {name: "WAV recording status"}))
    .toContainText("temporary removed", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});

  // Witness: the same session's capture chain records a real Pad signal, so
  // the silence above is routing, not a dead tap.
  await beginRecording(page);
  const pad = page.getByRole("button", {name: /^Pad A01\b/});
  await pad.dispatchEvent("pointerdown", {
    button: 0,
    isPrimary: true,
    pointerId: 71,
  });
  await page.waitForTimeout(120);
  await pad.dispatchEvent("pointerup", {
    button: 0,
    isPrimary: true,
    pointerId: 71,
  });
  await stopRecording(page);
  const witnessWav = parsePcm16StereoWav(await exportPerformanceWav(page));
  expect(firstSignalFrame(witnessWav.left)).toBeGreaterThanOrEqual(0);

  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await playStopKey(page).click();
  await transportStatus(page, "stopped");
});

test("toggling the metronome off mid-play cancels the click flow", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installMetronomeProof(page);
  await page.goto("/index.html");
  await importProject(page);
  await enterSequenceAndActivate(page);

  const toggle = metronomeToggle(page);
  await toggle.click();
  await playStopKey(page).click();
  await transportStatus(page, "playing");
  await expect.poll(async () => (await metronomeClicks(page)).length,
    {timeout: 30_000}).toBeGreaterThanOrEqual(4);

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  // Past the 120 ms scheduling horizon no queued click remains that could
  // still dispatch; playback itself is untouched.
  await page.waitForTimeout(600);
  const atToggleOff = (await metronomeClicks(page)).length;
  await page.waitForTimeout(400);
  expect((await metronomeClicks(page)).length).toBe(atToggleOff);
  await transportStatus(page, "playing");
});

test("the metronome preference survives a reload and defaults off on a fresh device", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installMetronomeProof(page);
  await page.goto("/index.html");
  await importProject(page);
  await enterSequenceAndActivate(page);

  // A fresh browser profile is a fresh device: no stored preference, and the
  // boot read leaves the switch at its default off.
  const toggle = metronomeToggle(page);
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await page.waitForTimeout(500);
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  // Far side: the device store holds the preference before any reload.
  await expect.poll(() => readStoredMetronomePreference(page),
    {timeout: 30_000}).toBe(true);

  await page.reload();
  await waitForProjectReopen(page, "00000000",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  await showSequenceLayer(page, "SETUP");
  await expect(metronomeToggle(page)).toHaveAttribute("aria-pressed", "true");
  expect(await readStoredMetronomePreference(page)).toBe(true);
});


// The UI alone submits/cancels/consumes. This forwarding observer retains the
// original request/response and never changes its arguments, Promise or budget.
async function observeCountInUi(page) {
  await page.evaluate(() => {
    const host = window.lmdjWebRuntimeHost;
    const transport = host.transport;
    window.__countInUi = [];
    const proxy = new Proxy({}, {get(_target, key) {
      const send = Reflect.get(transport, key);
      if (!["send", "sendRetained"].includes(key) || typeof send !== "function") return send;
      return function(...args) {
        const request = args[0];
        const pending = Reflect.apply(send, this === proxy ? transport : this, args);
        if (request.operation.startsWith("pattern.transport.")) {
          const entry = {request: structuredClone(request), response: null, failure: null};
          window.__countInUi.push(entry);
          void pending.then(response => {entry.response = structuredClone(response);},
            error => {entry.failure = String(error?.message ?? error);});
        }
        return pending;
      };
    }});
    host.transport = proxy;
  });
}

test.afterEach(async ({page}, testInfo) => {
  const proof = await page.evaluate(() => window.__countInUi ?? null).catch(() => null);
  if (proof !== null) await testInfo.attach("original-count-in-ui-rpc-proof", {
    body: Buffer.from(JSON.stringify(proof, null, 2)), contentType: "application/json",
  });
});

async function uiRequests(page, operation) {
  return page.evaluate(operation => window.__countInUi.filter(entry =>
    entry.request.operation === operation), operation);
}

async function uiCountInTicket(page, index = 0) {
  let entries;
  await expect.poll(async () => {
    entries = await uiRequests(page, "pattern.transport.count-in.request");
    return entries[index]?.response?.ok === true;
  }, {timeout: 5_000, intervals: [10]}).toBe(true);
  const p = entries[index].request.payload;
  return {sessionId: p.session_id, commandId: p.command_id,
    runtimeGeneration: p.runtime_generation, frameEpoch: p.frame_epoch,
    scheduleSerial: p.schedule_serial};
}

async function uiConsumed(page, ticket) {
  let consumed;
  await expect.poll(async () => {
    consumed = (await uiRequests(page, "pattern.transport.count-in.inspect"))
      .filter(entry => entry.request.payload.command_id === ticket.commandId &&
        entry.request.payload.consume && entry.response?.ok).at(-1);
    return consumed !== undefined;
  }, {timeout: 5_000, intervals: [10]}).toBe(true);
  expect(consumed.request.payload).toEqual({session_id: ticket.sessionId,
    command_id: ticket.commandId, runtime_generation: ticket.runtimeGeneration,
    frame_epoch: ticket.frameEpoch, schedule_serial: ticket.scheduleSerial, consume: true});
  return consumed.response.result;
}

async function countInSetup(page) {
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  await showSequenceLayer(page, "SETUP");
}
const countInChoice = (page, bars) => page.getByRole("button", {
  name: bars === 0 ? "Count-in Off" : bars === 1 ? "Count-in 1 bar" : "Count-in 2 bars", exact: true,
});

async function storedCountIn(page, write) {
  return page.evaluate(({write}) => new Promise((resolve, reject) => {
    const open = indexedDB.open("lmdj.creator.host", 1);
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const db = open.result;
      const tx = db.transaction("settings", write === undefined ? "readonly" : "readwrite");
      const store = tx.objectStore("settings");
      const request = write === undefined ? store.get("count-in.v1") : store.put(write, "count-in.v1");
      let result;
      request.onsuccess = () => {result = request.result;};
      tx.oncomplete = () => {db.close(); resolve(result ?? null);};
      tx.onerror = () => {db.close(); reject(tx.error);};
    };
  }), {write});
}

for (const initial of [null, "2"]) {
  test(`COUNT-IN UI defaults Off for ${initial === null ? "missing" : "corrupt"} preference and persists numeric bars`,
    async ({page, browserName}) => {
      test.skip(browserName !== "chromium");
      test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS + 15_000);
      await page.goto("/index.html");
      await openProjectPageAfterBoot(page);
      if (initial !== null) {
        await storedCountIn(page, initial);
        await page.reload();
        await openProjectPageAfterBoot(page);
      }
      await countInSetup(page);
      await expect(countInChoice(page, 0)).toHaveAttribute("aria-pressed", "true");
      const baseline = await inspectTruth(page);
      await countInChoice(page, 2).click();
      await expect.poll(() => storedCountIn(page)).toBe(2);
      expect(await inspectTruth(page)).toEqual(baseline);
      await page.reload();
      await openProjectPageAfterBoot(page);
      await countInSetup(page);
      await expect(countInChoice(page, 2)).toHaveAttribute("aria-pressed", "true");
      expect(await storedCountIn(page)).toBe(2);
      expect(await inspectTruth(page)).toEqual(baseline);
    });
}

test("COUNT-IN UI explicit choice survives the actual late IndexedDB read", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS + 15_000);
  await page.goto("/index.html");
  await openProjectPageAfterBoot(page);
  await storedCountIn(page, 1);
  await page.addInitScript(() => {
    const get = IDBObjectStore.prototype.get;
    let first = true;
    IDBObjectStore.prototype.get = function(key) {
      const request = Reflect.apply(get, this, [key]);
      if (this.name === "settings" && key === "count-in.v1" && first) {
        first = false;
        request.addEventListener("success", event => {
          event.stopImmediatePropagation();
          const at = performance.now();
          window.__lateCountIn = {value: request.result, at, releasedAt: null};
          window.__releaseCountInRead = () => {
            window.__lateCountIn.releasedAt = performance.now();
            request.onsuccess?.call(request, new Event("success"));
          };
        });
      }
      return request;
    };
  });
  await page.reload();
  await countInSetup(page);
  await expect.poll(() => page.evaluate(() => window.__lateCountIn?.value)).toBe(1);
  await countInChoice(page, 2).click();
  await expect.poll(() => storedCountIn(page)).toBe(2);
  const timing = await page.evaluate(() => {
    window.__releaseCountInRead();
    return window.__lateCountIn;
  });
  // A delivery after the settings reader's original timeout would not prove
  // this race. Keep that boundary unchanged and require the stale success.
  expect(timing.releasedAt - timing.at).toBeLessThan(5_000);
  await expect(countInChoice(page, 2)).toHaveAttribute("aria-pressed", "true");
  expect(await storedCountIn(page)).toBe(2);
});

for (const scenario of [
  {bpm: 120, bars: 1, barFrames: 96_000, onAtS: true},
  {bpm: 40, bars: 2, barFrames: 288_000, onAtS: false},
]) {
  test(`COUNT-IN UI ${scenario.bars} bar/${scenario.bpm} BPM records only post-S input and reopens complete Truth`,
    async ({page, browserName}, testInfo) => {
      test.skip(browserName !== "chromium");
      test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS * 2 + 30_000);
      await installMetronomeProof(page);
      await installCountInAudioObserver(page);
      const setup = await prepareCountInProject(page, scenario.bpm, {silentPattern: true});
      const sample = await sendCountInHost(page, "sample.inspect", {slot: {bank: 0, pad: 0}});
      const authored = await inspectTruth(page);
      await sendCountInHost(page, "sample.update_pad", {command_id: crypto.randomUUID(),
        expected_revision: authored.revision, slot: {bank: 0, pad: 0},
        playback: {...sample.playback, trigger_mode: "loop_gate", loop_mode: "forward", loop_start_frame: 0}});
      const loop = await sendCountInHost(page, "sample.inspect", {slot: {bank: 0, pad: 0}});
      expect(loop.playback).toMatchObject({trigger_mode: "loop_gate", loop_start_frame: 0});
      expect(loop.playback.loop_mode ?? "forward").toBe("forward");
      // A held real Gate spans later cues even if the UI admission arrives
      // after the nearest cue; its actual post-S release still owns the tail.
      // Refresh the real App projection after fixture authoring. No fake
      // Session or component state supplies BPM, quantize or Pattern identity.
      await page.reload();
      await waitForProjectReopen(page, "00000000");
      await enterSequenceAndActivate(page);
      await attachCountInPcmObserver(page);
      const clock = await ensureCountInClock(page);
      await countInChoice(page, scenario.bars).click();
      await expect.poll(() => storedCountIn(page)).toBe(scenario.bars);
      if (scenario.onAtS) await metronomeToggle(page).click();
      const baseline = await inspectTruth(page);
      const inventory = await countInProjectInventory(page, setup.projectId);
      const tempo = page.getByRole("button", {name: "Encoder 3 — Tempo", exact: true});
      const pattern = page.getByRole("button", {name: "Choose Pattern", exact: true});
      await expect(tempo).toBeEnabled();
      await expect(pattern).toBeEnabled();
      if (scenario.bars === 2) {
        for (const viewport of [{width: 1100, height: 760}, {width: 390, height: 844}]) {
          await page.setViewportSize(viewport);
          const group = page.getByRole("group", {name: "Count-in", exact: true});
          await group.scrollIntoViewIfNeeded();
          const box = await group.boundingBox();
          expect(box.x).toBeGreaterThanOrEqual(0);
          expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
          await page.screenshot({path: testInfo.outputPath(`count-in-${viewport.width}.png`)});
        }
        await page.setViewportSize({width: 1280, height: 720});
      }
      await observeCountInUi(page);
      await armCountInPcm(page);
      await startCountInMasterCapture(page);
      await recordKey(page).click();
      const ticket = await uiCountInTicket(page);
      expectCountInClock(ticket, clock);
      expect((await uiRequests(page, "pattern.transport.count-in.request"))[0].request.payload)
        .toMatchObject({project_id: setup.projectId, bars: scenario.bars, expected_revision: baseline.revision});
      const armed = await waitForCountInBoundary(page, ticket);
      expect(armed.countIn.bpm).toBe(scenario.bpm);
      expect(armed.countIn.barFrames).toBe(scenario.barFrames);
      const cues = Array.from({length: scenario.bars * 4}, (_, beat) =>
        armed.countIn.countInFrame + clock.offset + Math.floor(beat / 4) * scenario.barFrames +
        Math.floor(((beat % 4) * scenario.barFrames + 2) / 4));
      const start = armed.countIn.startFrame + clock.offset;
      const markers = scenario.onAtS ? [...cues, start] : cues;
      await expect(page.getByLabel("Count-in status")).toContainText(/COUNT-IN · \d+ beats? left/);
      await expect(recordKey(page)).toHaveClass(/is-counting-in/);
      await expect(recordKey(page)).not.toHaveClass(/is-active/);
      await expect(tempo).toBeDisabled();
      await expect(pattern).toBeDisabled();
      await expect(page.getByRole("button", {name: /^Pad A01\b/})).toBeEnabled();
      expect(await inspectTruth(page)).toEqual(baseline);
      expect(await countInProjectInventory(page, setup.projectId)).toEqual(inventory);
      // A real pre-S UI hold overlaps one forced cue; release is deliberately
      // after S. Native authority must keep this pair out of the Journal.
      await waitForObservedFrame(page, cues[1] - 1920, 2_000);
      await page.keyboard.down("z");
      await waitForObservedFrame(page, start + 9600, scenario.bars * scenario.barFrames / 48 + 1_000);
      let opened;
      await expect.poll(async () => {
        opened = await inspectCountIn(page, ticket);
        return opened.startReceipt?.result === "applied" && opened.openingComplete;
      }, {timeout: 5_000, intervals: [10]}).toBe(true);
      expect(opened.error).toBeNull();
      expect(opened.startReceipt.effectiveFrame).toBe(armed.countIn.startFrame);
      await expect(recordKey(page)).toHaveClass(/is-active/);
      await expect(recordKey(page)).not.toHaveClass(/is-counting-in/);
      await expect(page.getByLabel("Count-in status")).toHaveCount(0);
      const releasedFrame = await observedFrame(page);
      await page.keyboard.up("z");
      if (!scenario.onAtS) await metronomeToggle(page).click();
      await expect.poll(async () => (await metronomeClicks(page)).length,
        {timeout: 2_000, intervals: [10]}).toBeGreaterThan(0);
      const clicks = await metronomeClicks(page);
      expect(clicks[0].beat, "JS begins at beat 1 and never duplicates native S").toBe(1);
      expect(clicks.every(click => click.beat > 0)).toBe(true);
      const beatFrames = 2_880_000 / scenario.bpm;
      expect(Math.abs(Math.round(clicks[0].contextTime * 48_000) - (start + beatFrames))).toBeLessThanOrEqual(256);
      // The real post-S Gate release reaches the product output at a
      // load-dependent frame, which can follow beat 1. Inspect the first JS
      // click after that observed silence; its product/cue planes stay exact.
      const silentFrom = await waitForProductSilence(page, releasedFrame, beatFrames / 48 + 2_000);
      let jsFrame;
      await expect.poll(async () => {
        jsFrame = (await metronomeClicks(page)).map(click => Math.round(click.contextTime * 48_000))
          .find(frame => frame - 96 > silentFrom);
        return jsFrame !== undefined;
      }, {timeout: beatFrames / 48 + 2_000, intervals: [10]}).toBe(true);
      await waitForObservedFrame(page, jsFrame + 2016, beatFrames / 48 + 2_000);
      await stopCountInMasterCapture(page, {silent: false});
      const pcm = await readCountInPcm(page, [...markers, jsFrame], {cueMarkers: markers});
      expectForcedCountInPcm(pcm, markers);
      const js = pcm.planes.map(plane => plane.windows.at(-1));
      for (const plane of [0, 1, 2, 3]) expect(js[plane].values).toEqual(Array(1920).fill(0));
      for (const plane of [4, 5]) expect(js[plane].values.some(value => value !== 0)).toBe(true);
      await expectCountInMixedCapture(page, pcm.planes[0].onsets[0], markers);
      // Real post-S UI press/release: the held duration is an input gesture,
      // not a settling sleep. Journal frames independently determine Truth.
      await page.evaluate(async ({start, offset, bpm}) => {
        const context = window.__countInPcm.context;
        const deadline = performance.now() + 2_000;
        while (true) {
          const frame = Math.floor(context.currentTime * 48_000) - offset;
          const phase = Math.floor((frame - start) * bpm * 960 / 2_880_000) % 3840;
          const room = Math.ceil(0.9 * bpm * 960 / 60);
          if (phase >= 0 && phase < 3840 - room) return;
          if (performance.now() >= deadline) throw new Error("native phase with room for the UI hold unavailable");
          await new Promise(resolve => setTimeout(resolve, 10));
        }
      }, {start: armed.countIn.startFrame, offset: clock.offset, bpm: scenario.bpm});
      await page.keyboard.down("z");
      await page.waitForTimeout(650);
      await page.keyboard.up("z");
      let records;
      await expect.poll(async () => {
        records = (await readCountInJournal(page, setup)).filter(record => record.kind === "admission-candidate");
        return records.length;
      }, {timeout: 5_000, intervals: [10]}).toBe(2);
      const [press, release] = records;
      expect(press.session_id).toBe(ticket.sessionId);
      expect(press.data.kind).toBe("0");
      expect(release.data.kind).toBe("1");
      expect(press.data.slot).toEqual({bank: "0", pad: "0"});
      expect(release.data.press_sequence).toBe(press.data.press_sequence);
      expect(press.data.velocity).toBe("100");
      const nativeStart = BigInt(armed.countIn.startFrame);
      const tick = frame => (BigInt(frame) - nativeStart) * BigInt(scenario.bpm) * 960n / 2_880_000n;
      expect(BigInt(press.data.runtime_frame)).toBeGreaterThanOrEqual(nativeStart);
      const onset = Number(tick(press.data.runtime_frame) % 3840n);
      const duration = Math.min(Number(tick(release.data.runtime_frame) - tick(press.data.runtime_frame)), 3840 - onset);
      expect(duration, "real release cannot become a 240-tick lost-release fallback").toBeGreaterThan(240);
      const expected = structuredClone(baseline);
      expected.revision++;
      expected.patterns[setup.patternId].events = [{slot: {bank: 0, pad: 0},
        onset_tick: onset, duration_tick: duration, velocity: 100}];
      await recordKey(page).click();
      const consumed = await uiConsumed(page, ticket);
      expect(consumed.start_receipt.result).toBe("applied");
      expect(consumed.cancel_receipt).toMatchObject({result: "applied", playing: true});
      await expect(recordKey(page)).toHaveAccessibleName("Record");
      await expect(page.getByLabel("Count-in status")).toHaveCount(0);
      await expect(pattern).toBeEnabled();
      await expect(tempo).toBeEnabled();
      expect(await inspectTruth(page)).toEqual(expected);
      await playStopKey(page).click();
      await transportStatus(page, "stopped");
      expect(await inspectTruth(page)).toEqual(expected);
      expect(await uiRequests(page, "pattern.transport.count-in.request")).toHaveLength(1);
      await page.reload();
      await waitForProjectReopen(page, "00000000");
      expect(await inspectTruth(page), "the complete Project survives reopen").toEqual(expected);
      await countInSetup(page);
      await expect(countInChoice(page, scenario.bars)).toHaveAttribute("aria-pressed", "true");
    });
}

test("global COUNT-IN on every page cancels through both physical keys without authoring bytes", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS * 2 + 30_000);
  const setup = await prepareCountInProject(page, 40, {silentPattern: true});
  await page.reload();
  await waitForProjectReopen(page, "00000000");
  await enterSequenceAndActivate(page);
  await countInChoice(page, 2).click();
  const baseline = await inspectTruth(page);
  const inventory = await countInProjectInventory(page, setup.projectId);
  await observeCountInUi(page);
  for (const [index, mode] of ["Project", "Sample", "Sequence", "Perform", "Sound Sets", "Slice"].entries()) {
    if (mode === "Sound Sets") {
      await page.getByRole("button", {name: "Project", exact: true}).click();
      await page.getByRole("button", {name: "Sound Sets", exact: true}).click();
    } else if (mode === "Slice") {
      // Slice now sits on the Sample page's Pad layer (#2462).
      await openCreatorSlice(page);
    } else await page.getByRole("button", {name: mode, exact: true}).click();
    await recordKey(page).click();
    const ticket = await uiCountInTicket(page, index);
    await expect(page.getByLabel("Count-in status")).toContainText("COUNT-IN");
    await expect(recordKey(page)).toHaveClass(/is-counting-in/);
    // Change page during the original owner, too: a remount must not retire
    // or replace the global schedule. System keeps the same physical keys.
    await page.getByRole("button", {name: "System", exact: true}).click();
    await expect(page.getByLabel("Count-in status")).toContainText("COUNT-IN");
    await (index % 2 ? playStopKey(page) : recordKey(page)).click();
    const consumed = await uiConsumed(page, ticket);
    expect(consumed.start_receipt).toMatchObject({result: "cancelled", origin_frame: null, effective_frame: null});
    expect(consumed.cancel_receipt).toMatchObject({result: "cancelled", playing: false});
    await expect(page.getByLabel("Count-in status")).toHaveCount(0);
    await expect(recordKey(page)).toHaveAccessibleName("Record");
    await page.getByRole("button", {name: "Back to music", exact: true}).click();
    expect(await inspectTruth(page)).toEqual(baseline);
    expect(await countInProjectInventory(page, setup.projectId)).toEqual(inventory);
  }
  const cancels = await uiRequests(page, "pattern.transport.count-in.cancel");
  expect(cancels.map(entry => entry.request.payload.intent)).toEqual(["record", "play_stop", "record", "play_stop", "record", "play_stop"]);
  await page.reload();
  await waitForProjectReopen(page, "00000000");
  expect(await inspectTruth(page)).toEqual(baseline);
  expect(await countInProjectInventory(page, setup.projectId)).toEqual(inventory);
});

test("COUNT-IN Off and a playing overdub retain the ordinary UI Record path", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS + 15_000);
  await page.goto("/index.html");
  await importProject(page);
  await enterSequenceAndActivate(page);
  const baseline = await inspectTruth(page);
  await observeCountInUi(page);
  await recordKey(page).click();
  await transportStatus(page, "recording");
  expect(await uiRequests(page, "pattern.transport.count-in.request")).toEqual([]);
  await recordKey(page).click();
  await transportStatus(page, "playing");
  await countInChoice(page, 2).click();
  await recordKey(page).click();
  await transportStatus(page, "recording");
  expect(await uiRequests(page, "pattern.transport.count-in.request")).toEqual([]);
  await playStopKey(page).click();
  await transportStatus(page, "stopped");
  expect(await inspectTruth(page)).toEqual(baseline);
});

test("COUNT-IN preference does not route Sample and Performance recording into Pattern Record", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS + 20_000);
  await page.goto("/index.html");
  await importProject(page);
  await enterSequenceAndActivate(page);
  await countInChoice(page, 2).click();
  await observeCountInUi(page);
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await showSamplePage(page, "Pad");
  await page.getByRole("button", {name: /^Pad A01\b/}).evaluate(element => element.click());
  await expect(page.getByRole("button", {name: "Replace Sample", exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Record Sample", exact: true}).click();
  const confirmation = page.getByRole("dialog", {name: "Replace Pad A01?"});
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole("button", {name: "Confirm replace", exact: true}).click();
  const capture = page.getByRole("dialog", {name: "Pad A01 Pad Capture"});
  await expect(capture).toBeVisible();
  // Explicit permission refusal is the adapter boundary in this project;
  // the capture project's deterministic microphone owns successful capture.
  await page.evaluate(() => {navigator.mediaDevices.getUserMedia = async () => {
    throw new DOMException("COUNT-IN exclusion fixture denies microphone", "NotAllowedError");
  };});
  await capture.getByRole("button", {name: "Record into Pad A01", exact: true}).click();
  await expect(capture).toContainText("Creator is not allowed to use the microphone.");
  await expect(page.getByLabel("Count-in status")).toHaveCount(0);
  await capture.getByRole("button", {name: "Close", exact: true}).click();
  await openPerform(page);
  await beginRecording(page);
  await expect(recordKey(page)).toBeDisabled();
  await stopRecording(page);
  const wav = parsePcm16StereoWav(await exportPerformanceWav(page));
  expect(wav.frames).toBeGreaterThan(0);
  expect(await uiRequests(page, "pattern.transport.count-in.request")).toEqual([]);
  expect(await uiRequests(page, "pattern.transport.request")).toEqual([]);
  expect(await storedCountIn(page)).toBe(2);
});
