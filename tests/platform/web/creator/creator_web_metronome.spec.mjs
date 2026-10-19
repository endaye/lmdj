import {showPerformPage} from "./fixtures/creator_navigation.mjs";
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
