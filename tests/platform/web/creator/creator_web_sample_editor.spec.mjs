import {readFile} from "node:fs/promises";

import {expect, test} from "./fixtures/refusal_diagnostics.mjs";
import {
  openProjectPageAfterBoot,
  waitForBootProject,
  waitForProjectReopen,
} from "./fixtures/creator_boot.mjs";


const sampleBundle = process.env.LMDJ_CREATOR_WEB_SAMPLE_BUNDLE;

const SLOT_A1 = {bank: 0, pad: 0};
// Every audio lifecycle gesture owns one independently bounded 30-second
// Runtime request, so the state that follows an accepted gesture is promised
// only within that bound plus bounded render settling.
const AUDIO_TRANSITION_TIMEOUT_MS = 30_000 + 5_000;
// The exported report is produced from published Project truth, which settles
// after the control that caused the mutation is re-enabled, so the report is
// reachable only within one more bounded Runtime request plus the download.
const REPORT_REVISION_TIMEOUT_MS = 30_000 + 5_000;
let pointerSequence = 10;

// Session history is the rail's SHIFT chord (#1770): SHIFT toggles the
// modifier, ← / → consume it, and each direction key's lamp lights while its
// action is available -- there is no Undo/Redo control outside the console.
const RAIL_LIT = /\bis-lit\b/;
function railHistoryKeys(page) {
  const rail = page.getByTestId("physical-controls");
  return {
    shift: rail.getByRole("button", {name: /^SHIFT/}),
    undo: rail.getByRole("button", {name: "Undo — SHIFT + ←", exact: true}),
    redo: rail.getByRole("button", {name: "Redo — SHIFT + →", exact: true}),
  };
}
async function pressRailUndo(page) {
  const keys = railHistoryKeys(page);
  await keys.shift.click();
  await keys.undo.click();
}
async function pressRailRedo(page) {
  const keys = railHistoryKeys(page);
  await keys.shift.click();
  await keys.redo.click();
}

function pcm16Wav({frames = 96_000, sampleRate = 48_000, phase = 0}) {
  const channels = 1;
  const bytes = Buffer.alloc(44 + frames * channels * 2);
  bytes.write("RIFF", 0, "ascii");
  bytes.writeUInt32LE(bytes.length - 8, 4);
  bytes.write("WAVE", 8, "ascii");
  bytes.write("fmt ", 12, "ascii");
  bytes.writeUInt32LE(16, 16);
  bytes.writeUInt16LE(1, 20);
  bytes.writeUInt16LE(channels, 22);
  bytes.writeUInt32LE(sampleRate, 24);
  bytes.writeUInt32LE(sampleRate * channels * 2, 28);
  bytes.writeUInt16LE(channels * 2, 32);
  bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36, "ascii");
  bytes.writeUInt32LE(frames * channels * 2, 40);
  for (let frame = 0; frame < frames; frame += 1) {
    const period = 24 + phase;
    const ramp = ((frame + phase) % period) / Math.max(1, period - 1);
    const value = Math.round((ramp * 2 - 1) * 24_000);
    bytes.writeInt16LE(value, 44 + frame * 2);
  }
  return bytes;
}

async function installHostProofRecorder(page) {
  await page.addInitScript(() => {
    let exposed;
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get() {
        return exposed;
      },
      set(nativeHost) {
        const nativeTransport = nativeHost.transport;
        const transport = Object.freeze({
          async send(...arguments_) {
              const [request] = arguments_;
              window.__sampleProofOperations ??= [];
              window.__sampleProofOperations.push(request?.operation ?? null);
              // A manufactured failure never reaches the Runtime, so the
              // Project cannot change; only the Creator's handling is proven.
              if (request?.operation === "sample.update_pad" &&
                  window.__failNextSampleUpdate === true) {
                window.__failNextSampleUpdate = false;
                return {
                  protocol_version: 1,
                  request_id: request.request_id,
                  ok: false,
                  error: {code: "INTERNAL_ERROR", message: "Sample update failed", details: {}},
                };
              }
              const response = await nativeTransport.send(...arguments_);
              window.__sampleProofResponses ??= [];
              window.__sampleProofResponses.push({
                operation: request?.operation ?? null,
                ok: response?.ok ?? null,
                result: response?.result ?? null,
                error: response?.error ?? null,
              });
              if (request?.operation === "sample.inspect") {
                window.__sampleProofInspects ??= [];
                window.__sampleProofInspects.push(response?.result ?? response?.error ?? null);
              }
              const snapshot = response?.result?.snapshot_error;
              if (window.__normalizeNextResourceFailureToCook === true &&
                  response?.ok === true &&
                  response?.result?.runtime_published === false &&
                  snapshot?.code === "WEB_RUNTIME_RESOURCE_LIMIT") {
                window.__normalizeNextResourceFailureToCook = false;
                window.__sampleProofObservedResourceFailure = true;
                return {
                  ...response,
                  result: {
                    ...response.result,
                    snapshot_error: {
                      code: "COOK_FAILED",
                      message: "The sound was saved but is not ready to play yet.",
                      details: {},
                    },
                  },
                };
              }
              return response;
          },
          subscribe(...arguments_) {
            return nativeTransport.subscribe(...arguments_);
          },
          subscribeFailure(...arguments_) {
            return nativeTransport.subscribeFailure(...arguments_);
          },
          terminate(...arguments_) {
            return nativeTransport.terminate(...arguments_);
          },
          get terminated() {
            return nativeTransport.terminated;
          },
          get terminalOwnerReleased() {
            return nativeTransport.terminalOwnerReleased;
          },
        });
        nativeHost.transport = transport;
        exposed = nativeHost;
      },
    });
  });
}

// A Wasm trap in the runtime worker surfaces to the page as a `pageerror`
// ("memory access out of bounds") and only afterwards as whatever sanitized
// refusal the suspended Facade call turns into (#443 diagnosed INVALID_PROJECT
// that way). Recording page errors and asserting on them next to the refusal
// assertion makes the trap the failure's headline rather than its footnote.
function recordPageErrors(page) {
  const errors = [];
  page.on("pageerror", (error) => {
    errors.push(String(error?.message ?? error));
  });
  return () => expect(errors, "the Wasm runtime must not trap").toEqual([]);
}

async function rawRequest(page, operation, payload) {
  return page.evaluate(async ({operation: requestedOperation, payload: requestedPayload}) => {
    return window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: requestedOperation,
      payload: requestedPayload,
    });
  }, {operation, payload});
}

async function expectProjectRevision(page, expectedRevision) {
  // A control is re-enabled when its own Runtime request returns, which is not
  // when the Project revision it committed has been published into the report;
  // on a loaded host a single read of the report sampled the near side of that
  // transition and saw the previous revision (#713). Polling only re-reads the
  // report, so the assertion stays exact equality: a revision that never
  // arrives, or one that overshoots, still fails.
  await expect.poll(
    async () => (await downloadReport(page)).sample.project_revision,
    {timeout: REPORT_REVISION_TIMEOUT_MS},
  ).toBe(expectedRevision);
}

async function downloadReport(page) {
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export report"}).click();
  const download = await downloadPromise;
  return JSON.parse(await readFile(await download.path(), "utf8"));
}

async function importV1SampleProject(page) {
  if (!sampleBundle) {
    throw new Error("LMDJ_CREATOR_WEB_SAMPLE_BUNDLE is required");
  }
  await openProjectPageAfterBoot(page);
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(sampleBundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.getByText("44 / 64")).toBeVisible();
  await expect(page.locator(".overview-display > .overview-facts")).toContainText("Rev46");
  await expectProjectRevision(page, 46);
}

async function activateAudio(page) {
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: 30_000,
  });
}

async function enterSampleEditor(page) {
  await page.getByRole("button", {name: "Sample"}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
}

async function waitForControlMutation(page, control, action, expectedRevision) {
  await action();
  await expect(control).toBeDisabled({timeout: 10_000});
  await expect(control).toBeEnabled({timeout: 120_000});
  await expectProjectRevision(page, expectedRevision);
  const publication = await page.evaluate((revision) =>
    (window.__sampleProofResponses ?? []).findLast((entry) =>
      entry?.result?.committed_revision === revision), expectedRevision);
  expect(publication?.result).toEqual(expect.objectContaining({
    committed_revision: expectedRevision,
    runtime_revision: expectedRevision,
    runtime_published: true,
  }));
}

async function chooseSampleFile(page, buttonName, name, buffer) {
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: buttonName}).click();
  await (await chooserPromise).setFiles({
    name,
    mimeType: "audio/wav",
    buffer,
  });
}

async function commitLongSourceSelection(page) {
  const longSource = page.getByRole("dialog", {name: /Pad [A-D]\d+ Long Source/});
  await expect(longSource).toBeVisible({timeout: 30_000});
  await longSource.getByRole("button", {name: "Commit selection"}).click();
}

async function selectPadWithoutPress(page, label) {
  // The Sample picker pad; the console matrix pad shares the prefix and adds
  // its key hint, so the name is matched exactly.
  await page.getByRole("button", {name: label, exact: true}).evaluate((element) => element.click());
}

async function expectDefaultPlaybackUi(page) {
  await expect(page.getByRole("button", {name: "Loop"}))
    .toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", {name: "One Shot"}))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", {name: "Mute"}))
    .toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("slider", {name: "Pad A1 Volume"})).toHaveValue("0");
  await expect(page.getByRole("spinbutton", {name: "Pad A1 Start time (seconds)"}))
    .toHaveValue("0");
  await expect(page.getByRole("spinbutton", {name: "Pad A1 End time (seconds)"}))
    .toHaveValue("2");
}

async function waitForVoiceStates(page, offset, expected) {
  try {
    await expect.poll(() => page.evaluate((start) =>
      (window.__sampleVoiceStates ?? []).slice(start).map(({state}) => state), offset), {
      timeout: 30_000,
    }).toEqual(expected);
  } catch (error) {
    const operations = await page.evaluate(() =>
      (window.__sampleProofOperations ?? []).slice(-12));
    const inspects = await page.evaluate(() =>
      (window.__sampleProofInspects ?? []).slice(-4));
    const responses = await page.evaluate(() =>
      (window.__sampleProofResponses ?? []).slice(-6));
    throw new Error(`${error.message}\nRecent Host operations: ${JSON.stringify(operations)}` +
      `\nRecent Sample inspections: ${JSON.stringify(inspects)}` +
      `\nRecent Host responses: ${JSON.stringify(responses)}`);
  }
}

async function heldPadGesture(page, pad, expectedStates) {
  const offset = await page.evaluate(() => (window.__sampleVoiceStates ?? []).length);
  const pointerId = ++pointerSequence;
  await pad.dispatchEvent("pointerdown", {
    pointerId,
    isPrimary: true,
    button: 0,
    clientX: 10,
    clientY: 10,
  });
  if (!expectedStates.includes("started")) {
    await waitForVoiceStates(page, offset, expectedStates);
    await pad.dispatchEvent("pointerup", {
      pointerId,
      isPrimary: true,
      button: 0,
      clientX: 10,
      clientY: 10,
    });
    return;
  }
  await expect.poll(() => page.evaluate((start) =>
    (window.__sampleVoiceStates ?? []).slice(start).some(({state}) => state === "started"),
  offset), {timeout: 30_000}).toBe(true);
  await pad.dispatchEvent("pointerup", {
    pointerId,
    isPrimary: true,
    button: 0,
    clientX: 10,
    clientY: 10,
  });
  await waitForVoiceStates(page, offset, expectedStates);
}

function assertMirroredWaveform(path) {
  const points = [...path.matchAll(/[ML] (\d+) (\d+)/g)].map((match) => ({
    x: Number(match[1]),
    y: Number(match[2]),
  }));
  expect(points.length).toBeGreaterThan(8);
  expect(points.length % 2).toBe(0);
  const half = points.length / 2;
  expect(points.slice(0, half).some(({y}) => y !== 64)).toBe(true);
  for (let index = 0; index < half; index += 1) {
    const upper = points[index];
    const lower = points[points.length - 1 - index];
    expect(lower.x).toBe(upper.x);
    expect(lower.y + upper.y).toBe(160);
  }
}

test("packaged Sample Editor proves the real Facade v1-to-v2 journey", async ({page, browserName, refusalDiagnostics}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(600_000);
  const expectNoPageErrors = recordPageErrors(page);
  await installHostProofRecorder(page);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await activateAudio(page);
  await enterSampleEditor(page);

  await expect(page.getByRole("button", {name: "Pad A1 — empty — Key Q", exact: true})).toBeVisible();
  await chooseSampleFile(
    page,
    "Add Sample to Pad A1",
    "proof-ramp.wav",
    pcm16Wav({}),
  );
  await commitLongSourceSelection(page);
  await expect(page.getByRole("button", {name: "Pad A1 — assigned — Key Q", exact: true}))
    .toBeVisible({timeout: 120_000});
  await expect(page.getByRole("img", {name: "Pad A1 mirrored waveform"}))
    .toBeVisible({timeout: 120_000});
  await expectProjectRevision(page, 47);
  await expect(page.getByText("48 kHz · Mono · 96,000 frames")).toBeVisible();
  await expectDefaultPlaybackUi(page);

  const waveformPath = page.locator("path[data-waveform]");
  assertMirroredWaveform(await waveformPath.getAttribute("d"));
  const editor = page.locator("[data-waveform-viewport]");
  expect(await editor.getAttribute("data-viewport-start")).toBe("0");
  expect(await editor.getAttribute("data-viewport-end")).toBe("96000");
  await page.getByRole("button", {name: "Zoom In"}).click();
  await expect(editor).not.toHaveAttribute("data-viewport-end", "96000");
  await page.getByRole("button", {name: "Fit waveform"}).click();
  await expect(editor).toHaveAttribute("data-viewport-start", "0");
  await expect(editor).toHaveAttribute("data-viewport-end", "96000");

  const startTime = page.getByRole("spinbutton", {name: "Pad A1 Start time (seconds)"});
  await startTime.focus();
  await startTime.fill("0.01");
  await startTime.blur();
  await expect(startTime).toBeDisabled({timeout: 10_000});
  await expect(startTime).toBeEnabled({timeout: 120_000});
  await expectProjectRevision(page, 48);
  await expect(startTime).toHaveValue("0.01");

  await page.evaluate(() => {
    window.__sampleVoiceStates = [];
    window.__sampleVoiceUnsubscribe = window.lmdjWebRuntimeHost.transport.subscribe(
      (notification) => {
        if (notification?.event === "runtime.voice_state") {
          window.__sampleVoiceStates.push(...notification.payload.events);
        }
      },
    );
  });
  const padA1 = page.getByRole("button", {name: "Pad A1 — assigned — Key Q", exact: true});
  await page.emulateMedia({reducedMotion: "reduce"});
  const playheadOffset = await page.evaluate(() =>
    (window.__sampleVoiceStates ?? []).length);
  const playheadPointer = ++pointerSequence;
  await padA1.dispatchEvent("pointerdown", {
    pointerId: playheadPointer,
    isPrimary: true,
    button: 0,
    clientX: 10,
    clientY: 10,
  });
  await expect.poll(() => page.evaluate((start) =>
    (window.__sampleVoiceStates ?? []).slice(start).some(({state}) => state === "started"),
  playheadOffset), {timeout: 30_000}).toBe(true);
  const playhead = page.locator("line[data-playhead]");
  await expect(playhead).toHaveCount(1);
  await expect(playhead).toHaveAttribute("aria-hidden", "true");
  const initialPlayheadX = Number(await playhead.getAttribute("x1"));
  await expect.poll(async () => Number(await playhead.getAttribute("x1")), {
    timeout: 5_000,
  }).toBeGreaterThan(initialPlayheadX + 4);
  await padA1.dispatchEvent("pointerup", {
    pointerId: playheadPointer,
    isPrimary: true,
    button: 0,
    clientX: 10,
    clientY: 10,
  });
  await waitForVoiceStates(page, playheadOffset, ["started", "completed"]);
  await expect(playhead).toHaveCount(0);

  const loop = page.getByRole("button", {name: "Loop"});
  const oneShot = page.getByRole("button", {name: "One Shot"});
  await waitForControlMutation(page, oneShot, () => oneShot.click(), 49);
  await expect(oneShot).toHaveAttribute("aria-pressed", "false");
  await heldPadGesture(page, padA1, ["started", "stopped"]);

  await waitForControlMutation(page, loop, () => loop.click(), 50);
  const hold = page.getByRole("button", {name: "Hold"});
  await expect(hold).toHaveAttribute("aria-pressed", "false");
  await heldPadGesture(page, padA1, ["started", "stopped"]);

  await waitForControlMutation(page, hold, () => hold.click(), 51);
  const loopToggleOffset = await page.evaluate(() => window.__sampleVoiceStates.length);
  await heldPadGesture(page, padA1, ["started"]);
  await heldPadGesture(page, padA1, ["stopped"]);
  expect((await page.evaluate((offset) =>
    window.__sampleVoiceStates.slice(offset).map(({state}) => state), loopToggleOffset)))
    .toEqual(["started", "stopped"]);

  const volume = page.getByRole("slider", {name: "Pad A1 Volume"});
  await volume.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(volume).toBeDisabled({timeout: 10_000});
  await expect(volume).toBeEnabled({timeout: 120_000});
  await expectProjectRevision(page, 52);
  await expect(volume).toHaveValue("-0.1");

  const mute = page.getByRole("button", {name: "Mute"});
  await waitForControlMutation(page, mute, () => mute.click(), 53);
  await expect(mute).toHaveAttribute("aria-pressed", "true");
  const reset = page.getByRole("button", {name: "Reset Pad to Defaults"});
  await reset.click();
  await expect(page.getByRole("dialog", {name: "Reset Pad A1?"})).toBeVisible();
  const confirmReset = page.getByRole("button", {name: "Confirm reset"});
  await confirmReset.click();
  await expect(reset).toBeDisabled({timeout: 10_000});
  await expect(reset).toBeEnabled({timeout: 120_000});
  await expectProjectRevision(page, 54);
  await expectDefaultPlaybackUi(page);

  const replacement = pcm16Wav({phase: 7});
  await chooseSampleFile(
    page,
    "Replace Sample",
    "replacement-proof.wav",
    replacement,
  );
  await expect(page.getByRole("dialog", {name: "Replace Pad A1?"})).toBeVisible();
  await page.getByRole("button", {name: "Cancel replace"}).click();
  await expectProjectRevision(page, 54);
  await chooseSampleFile(
    page,
    "Replace Sample",
    "replacement-proof.wav",
    replacement,
  );
  await page.getByRole("button", {name: "Confirm replace"}).click();
  await commitLongSourceSelection(page);
  await expect(page.getByRole("button", {name: "Replace Sample"}))
    .toBeEnabled({timeout: 120_000});
  await expectProjectRevision(page, 55);
  await expectDefaultPlaybackUi(page);

  await chooseSampleFile(
    page,
    "Replace Sample",
    "not-a-wave.wav",
    Buffer.from("not a RIFF/WAVE file"),
  );
  await page.getByRole("button", {name: "Confirm replace"}).click();
  await expect(page.getByRole("alert")).toContainText(
    "This type of audio file is not supported. Choose a WAV, MP3, M4A/AAC or FLAC file.",
    {timeout: 30_000},
  );
  await expectProjectRevision(page, 55);

  const conflictPlayback = {
    trim_start_frame: 0,
    trim_end_frame: null,
    trigger_mode: "one_shot",
    gain_millidb: 0,
    muted: false,
  };
  const conflict = await rawRequest(page, "sample.update_pad", {
    command_id: "00000000-0000-4000-8000-000000009999",
    expected_revision: 54,
    slot: SLOT_A1,
    playback: conflictPlayback,
  });
  expectNoPageErrors();
  expect(conflict).toEqual(expect.objectContaining({
    ok: false,
    error: expect.objectContaining({
      code: "REVISION_CONFLICT",
      details: {actual_revision: 55, expected_revision: 54},
    }),
  }));
  await expectProjectRevision(page, 55);
  // Fail-closed collection proof: if diagnostic emission, worker console
  // forwarding, or collection regresses, this assertion turns the lane red
  // instead of silently losing the pre-sanitization reason again.
  const conflictDiagnostic = refusalDiagnostics
    .map((entry) => entry.parsed)
    .find((parsed) => parsed && parsed.normalized === "REVISION_CONFLICT");
  expect(conflictDiagnostic, "expected a collected lmdj-refusal-diagnostic line for the manufactured REVISION_CONFLICT")
    .toEqual(expect.objectContaining({
      normalized: "REVISION_CONFLICT",
      details: expect.objectContaining({actual_revision: 55, expected_revision: 54}),
    }));

  await selectPadWithoutPress(page, "Pad A2 — assigned — Key W");
  await expect(page.getByText(/^Asset /)).toBeVisible({timeout: 30_000});
  const a2Loop = page.getByRole("button", {name: "Loop"});
  await waitForControlMutation(page, a2Loop, () => a2Loop.click(), 56);
  const padA2 = page.getByRole("button", {name: "Pad A2 — assigned — Key W", exact: true});
  await heldPadGesture(page, padA2, ["started"]);

  await selectPadWithoutPress(page, "Pad A1 — assigned — Key Q");
  const a1Mute = page.getByRole("button", {name: "Mute"});
  await waitForControlMutation(page, a1Mute, () => a1Mute.click(), 57);

  await selectPadWithoutPress(page, "Pad A3 — assigned — Key E");
  const a3Loop = page.getByRole("button", {name: "Loop"});
  await waitForControlMutation(page, a3Loop, () => a3Loop.click(), 58);
  await heldPadGesture(
    page,
    page.getByRole("button", {name: "Pad A3 — assigned — Key E", exact: true}),
    ["started"],
  );

  await selectPadWithoutPress(page, "Pad A4 — assigned — Key R");
  const a4Loop = page.getByRole("button", {name: "Loop"});
  await waitForControlMutation(page, a4Loop, () => a4Loop.click(), 59);
  await heldPadGesture(
    page,
    page.getByRole("button", {name: "Pad A4 — assigned — Key R", exact: true}),
    ["started"],
  );

  await selectPadWithoutPress(page, "Pad A1 — assigned — Key Q");
  await page.evaluate(() => {
    window.__normalizeNextResourceFailureToCook = true;
  });
  await a1Mute.click();
  await expect.poll(() => page.evaluate(() =>
    (window.__sampleProofResponses ?? []).findLast((entry) =>
      entry?.result?.committed_revision === 60)?.result ?? null), {
    timeout: 120_000,
  }).toEqual(expect.objectContaining({
    committed_revision: 60,
    runtime_revision: 59,
    runtime_published: false,
    snapshot_error: expect.objectContaining({
      code: "WEB_RUNTIME_RESOURCE_LIMIT",
      details: {
        resource: "resident_pcm_bytes",
        observed: 273_296_528,
        limit: 268_435_456,
      },
    }),
  }));
  await expect(page.getByText(
    "Saved at revision 60; Runtime is still revision 59",
  )).toBeVisible(
    {timeout: 120_000},
  );
  expect(await page.evaluate(() => window.__sampleProofObservedResourceFailure)).toBe(true);
  await expectProjectRevision(page, 60);

  await page.getByRole("button", {name: "Suspend audio"}).click();
  // An explicit Suspend publishes "Audio suspended" only after the Runtime has
  // committed the suspend, so the Activate gesture that follows is guaranteed
  // to be accepted. Both gestures own one independently bounded 30-second
  // Runtime request, which Playwright's 5-second default does not cover.
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText(
    /Audio (running|recovering)/,
    {timeout: AUDIO_TRANSITION_TIMEOUT_MS},
  );
  await page.getByRole("button", {name: "Retry Prepare"}).click();
  await expect(page.getByRole("button", {name: "Retry Prepare"})).toHaveCount(0, {
    timeout: 120_000,
  });
  const recoveredReport = await downloadReport(page);
  expect(recoveredReport.sample.project_revision).toBe(60);
  expect(recoveredReport.sample.runtime_revision).toBe(60);

  await page.reload();
  // The imported Project is remembered, so the reload reopens it by itself.
  await waitForProjectReopen(page, "00000000");
  await page.getByRole("button", {name: "Project", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.locator(".overview-display > .overview-facts")).toContainText("Rev60");
  await expect(page.getByText("45 / 64")).toBeVisible();
  await enterSampleEditor(page);
  await expect(page.getByRole("button", {name: "Pad A1 — assigned — Key Q", exact: true})).toBeVisible();
  await expectProjectRevision(page, 60);
  const postReloadOperations = await page.evaluate(() => window.__sampleProofOperations ?? []);
  expect(postReloadOperations.filter((operation) => operation === "sample.import.commit"))
    .toHaveLength(0);

  // F5: a pointer drag aimed at a trim grip moves only that trim point. The
  // retired invisible range bands grabbed the wrong handle or jumped the
  // trim point to the pressed track position.
  await selectPadWithoutPress(page, "Pad A1 — assigned — Key Q");
  await expect(page.getByRole("img", {name: "Pad A1 mirrored waveform"}))
    .toBeVisible({timeout: 120_000});
  const trimStart = page.getByRole("spinbutton", {name: "Pad A1 Start time (seconds)"});
  const trimEnd = page.getByRole("spinbutton", {name: "Pad A1 End time (seconds)"});
  await expect(trimStart).toHaveValue("0");
  await expect(trimEnd).toHaveValue("2");
  const dragGrip = async (grip, deltaX) => {
    // The touch workspace is a fixed 368 × 368 region that scrolls; the mouse
    // must be aimed at where the grip actually is, not where it was laid out.
    await grip.scrollIntoViewIfNeeded();
    const box = await grip.boundingBox();
    expect(box).not.toBeNull();
    const pressX = box.x + box.width / 2;
    const pressY = box.y + box.height / 2;
    await page.mouse.move(pressX, pressY);
    await page.mouse.down();
    await page.mouse.move(pressX + deltaX, pressY, {steps: 4});
    await page.mouse.up();
  };
  await waitForControlMutation(page, trimStart, async () => {
    await dragGrip(page.locator('[data-grip-zone="start"]'), 40);
  }, 61);
  await expect(trimStart).not.toHaveValue("0");
  await expect(trimEnd).toHaveValue("2");
  const movedStart = await trimStart.inputValue();
  await waitForControlMutation(page, trimEnd, async () => {
    await dragGrip(page.locator('[data-grip-zone="end"]'), -40);
  }, 62);
  await expect(trimEnd).not.toHaveValue("2");
  await expect(trimStart).toHaveValue(movedStart);

  await page.evaluate(() => window.__sampleVoiceUnsubscribe?.());
});

test("packaged Sample Editor clamps a plus-one-frame source and admits the quota-bound selection", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  await installHostProofRecorder(page);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await activateAudio(page);
  await enterSampleEditor(page);

  const operationOffset = await page.evaluate(() =>
    (window.__sampleProofOperations ?? []).length);
  await chooseSampleFile(
    page,
    "Add Sample to Pad A1",
    "bank-quota-plus-one.wav",
    pcm16Wav({frames: 16_777_217}),
  );
  const quotaBoundFrames = Number(await page.getByRole("slider", {
    name: "Long source selection length",
  }).inputValue());
  expect(quotaBoundFrames).toBeLessThan(16_777_217);
  expect(44 + quotaBoundFrames * 2).toBeGreaterThan(1_048_576);
  await commitLongSourceSelection(page);

  await expect(page.getByRole("button", {name: "Pad A1 — assigned — Key Q", exact: true}))
    .toBeVisible({timeout: 120_000});
  await expect(page.getByText(
    `48 kHz · Mono · ${quotaBoundFrames.toLocaleString("en-US")} frames`,
  )).toBeVisible();
  await expectProjectRevision(page, 47);
  const operations = await page.evaluate((offset) =>
    (window.__sampleProofOperations ?? []).slice(offset), operationOffset);
  expect(operations.filter((operation) => operation === "sample.import.begin"))
    .toHaveLength(1);
  expect(operations.filter((operation) => operation === "sample.import.chunk"))
    .toHaveLength(Math.ceil((44 + quotaBoundFrames * 2) / 1_048_576));
  expect(operations.filter((operation) => operation === "sample.import.commit"))
    .toHaveLength(1);
});

test("Sample Editor WebKit capability boundary is explicit, private, and non-physical", async ({page, browserName}) => {
  test.skip(browserName !== "webkit");
  await installHostProofRecorder(page);
  await page.goto("/index.html");
  await expect(page.getByTestId("creator-phase")).toHaveText("unsupported", {
    timeout: 30_000,
  });
  const alert = page.getByRole("alert");
  // #1680: user language in the alert; the code is in Developer diagnostics.
  await expect(alert).toContainText("This browser cannot run Creator.");
  const publicText = await alert.textContent();
  expect(publicText).not.toMatch(/UNSUPPORTED_WEB_RUNTIME|HOST_PROTOCOL_MISMATCH|\/Users\/|file:\/\/|\.lmdj|\.wav/i);
  await page.getByText(/^Developer diagnostics \(\d+\)$/).click();
  await expect(page.getByRole("region", {name: "Developer diagnostics"}))
    .toContainText("UNSUPPORTED_WEB_RUNTIME");
  expect(await page.evaluate(() => window.lmdjWebRuntimeHost === undefined)).toBe(true);
  await expect(page.getByRole("button", {name: "Activate audio"})).toBeDisabled();
  await expect(page.getByRole("button", {name: "Export report"})).toBeDisabled();
});

test("re-importing a diverged Project Bundle recovers through Open local Project without a reload", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  await installHostProofRecorder(page);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await activateAudio(page);
  await enterSampleEditor(page);

  // F3: diverge the local Project from the imported bundle. Committing a
  // Sample to Pad A1 advances the local Project to revision 47.
  await expect(page.getByRole("button", {name: "Pad A1 — empty — Key Q", exact: true})).toBeVisible();
  await chooseSampleFile(
    page,
    "Add Sample to Pad A1",
    "proof-ramp.wav",
    pcm16Wav({}),
  );
  await commitLongSourceSelection(page);
  await expect(page.getByRole("button", {name: "Pad A1 — assigned — Key Q", exact: true}))
    .toBeVisible({timeout: 120_000});
  await expectProjectRevision(page, 47);

  // Re-importing the original bundle is refused as DUPLICATE_ID: the local
  // copy of the same Project has newer changes. The refusal must present as
  // a recoverable situation, not as "Creator unavailable".
  await page.getByRole("button", {name: "Suspend audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await page.getByRole("button", {name: "Project", exact: true}).click();
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(sampleBundle);
  const alert = page.getByRole("alert");
  await expect(alert).toBeVisible({timeout: 120_000});
  await expect(alert).toContainText("Project already on this device");
  await expect(alert).toContainText(
    "The import was refused because the local copy of this Project has newer changes. Nothing was lost.",
  );
  await expect(alert).not.toContainText("Creator unavailable");

  // The recovery control dismisses the panel and leads to the local Projects
  // list — the same destination as Open local — without a reload.
  await page.getByRole("button", {name: "Open local Project"}).click();
  await expect(alert).toHaveCount(0);
  await expect(page.getByRole("heading", {name: "Local Projects"}))
    .toBeVisible();
  const diverged = page.locator(".local-projects li")
    .filter({hasText: "Project 00000000"});
  await expect(diverged).toContainText("Revision 47");
  await diverged.getByRole("button", {name: "Open Project 00000000"}).click();
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.locator(".overview-display > .overview-facts")).toContainText("Rev47");
});

test("Creator history preserves sound identity across modes, cancelled edits and persisted reopen", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  const noErrors = recordPageErrors(page);
  await installHostProofRecorder(page);
  // A fresh store boots into a newly created, empty Project (#1660).
  await page.goto("/index.html");
  await waitForBootProject(page);
  const {undo, redo} = railHistoryKeys(page);
  await expect(undo).not.toHaveClass(RAIL_LIT);
  await expect(redo).not.toHaveClass(RAIL_LIT);
  await activateAudio(page);
  await chooseSampleFile(page, "Add Sample to Pad A1", "history.wav", pcm16Wav({frames: 4800}));
  await commitLongSourceSelection(page);
  await expectProjectRevision(page, 1);
  const imported = (await rawRequest(page, "project.inspect", {})).result.project;
  await expect(undo).toHaveClass(RAIL_LIT);
  await page.getByRole("button", {name: "Mute", exact: true}).click();
  await expectProjectRevision(page, 2);
  expect((await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.playback.muted).toBe(true);
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(undo).toHaveClass(RAIL_LIT);
  await pressRailUndo(page);
  await expectProjectRevision(page, 3);
  expect((await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.playback.muted).toBe(false);
  await pressRailUndo(page);
  await expectProjectRevision(page, 4);
  const cleared = (await rawRequest(page, "project.inspect", {})).result.project;
  expect(cleared.assets).toEqual({});
  expect(cleared.banks[0].pads[0].asset_id).toBeNull();
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(redo).toHaveClass(RAIL_LIT);
  await chooseSampleFile(page, "Add Sample to Pad A1", "cancelled.wav", pcm16Wav({frames: 9600}));
  const draft = page.getByRole("dialog", {name: /Pad A1 Long Source/});
  await expect(draft).toBeVisible();
  await draft.getByRole("button", {name: "Cancel", exact: true}).click();
  const retained = (await rawRequest(page, "history.inspect", {})).result;
  expect(retained.project_revision).toBe(4);
  expect(retained.redo_count).toBe(2);
  const refused = await rawRequest(page, "history.redo", {session_id: retained.session_id,
    command_id: crypto.randomUUID(), expected_revision: 3});
  expect(refused.ok).toBe(false);
  expect((await rawRequest(page, "history.inspect", {})).result).toEqual(retained);
  await expect(redo).toHaveClass(RAIL_LIT);
  const responseOffset = await page.evaluate(() => window.__sampleProofResponses.length);
  await pressRailRedo(page);
  await expect.poll(() => page.evaluate((offset) =>
    window.__sampleProofResponses.slice(offset).some((r) => r.operation === "history.redo"), responseOffset)).toBe(true);
  const redoResponse = await page.evaluate((offset) =>
    window.__sampleProofResponses.slice(offset).find((r) => r.operation === "history.redo"), responseOffset);
  expect(redoResponse.ok, JSON.stringify({redoResponse, operations: await page.evaluate(() => window.__sampleProofOperations)})).toBe(true);
  await expectProjectRevision(page, 5);
  const restored = (await rawRequest(page, "project.inspect", {})).result.project;
  expect(restored.assets).toEqual(imported.assets);
  expect(restored.banks).toEqual(imported.banks);
  await pressRailRedo(page);
  await expectProjectRevision(page, 6);
  expect((await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.playback.muted).toBe(true);
  await pressRailUndo(page);
  await expectProjectRevision(page, 7);
  await expect(page.getByRole("button", {name: "Mute", exact: true})).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", {name: "Loop", exact: true}).click();
  await expectProjectRevision(page, 8);
  await expect(redo).not.toHaveClass(RAIL_LIT);
  const saved = (await rawRequest(page, "project.inspect", {})).result.project;
  await page.getByRole("button", {name: "Project", exact: true}).click();
  expect((await rawRequest(page, "history.inspect", {})).result.undo_count).toBeGreaterThan(0);
  // The reload reopens the remembered Project with no user action (#1660).
  await page.reload();
  await waitForProjectReopen(page, saved.project_id.slice(0, 8));
  expect((await rawRequest(page, "project.inspect", {})).result.project).toEqual(saved);
  const reopened = (await rawRequest(page, "history.inspect", {})).result;
  expect(reopened.session_id).not.toBe(retained.session_id);
  expect(reopened.undo_count).toBe(0);
  expect(reopened.redo_count).toBe(0);
  await expect(undo).not.toHaveClass(RAIL_LIT);
  await expect(redo).not.toHaveClass(RAIL_LIT);
  noErrors();
});

async function slideAndRelease(slider, value) {
  const pointerId = ++pointerSequence;
  await slider.dispatchEvent("pointerdown", {pointerId, isPrimary: true, button: 0});
  await slider.fill(value);
  await slider.dispatchEvent("pointerup", {pointerId, isPrimary: true, button: 0});
}

async function editValueCard(input, value) {
  await input.fill(value);
  await input.blur();
}

async function inspectedPlayback(page) {
  return (await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.playback;
}

test("Sample playback parity commits, cancels, refuses, fails and reopens through the real Runtime", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  const noErrors = recordPageErrors(page);
  await installHostProofRecorder(page);
  await page.goto("/index.html");
  await waitForBootProject(page);
  await activateAudio(page);
  // 4 800 frames at 48 kHz: 0.1 s, so the loop point and crossfade stay
  // well inside one loop.
  await chooseSampleFile(page, "Add Sample to Pad A1", "parity.wav", pcm16Wav({frames: 4800}));
  await commitLongSourceSelection(page);
  await expectProjectRevision(page, 1);
  const base = await inspectedPlayback(page);
  expect(Object.keys(base).sort()).toEqual(
    ["gain_millidb", "muted", "trigger_mode", "trim_end_frame", "trim_start_frame"]);

  // normal: every parity control commits one revision.
  await page.getByRole("button", {name: "Reverse", exact: true}).click();
  await expectProjectRevision(page, 2);
  await slideAndRelease(page.getByRole("slider", {name: "Pad A1 Pitch"}), "3.5");
  await expectProjectRevision(page, 3);
  await slideAndRelease(page.getByRole("slider", {name: "Pad A1 Pan"}), "-100");
  await expectProjectRevision(page, 4);
  await page.getByRole("button", {name: "Loop", exact: true}).click();
  await expectProjectRevision(page, 5);
  // Reverse is on, so the card edits the mirrored boundary: 0.025 s is frame
  // 1 200 from Start, stored as 0 + 4 800 - 1 200 = 3 600.
  await editValueCard(
    page.getByRole("spinbutton", {name: "Pad A1 Loop start time (seconds)"}), "0.025");
  await expectProjectRevision(page, 6);
  await editValueCard(
    page.getByRole("spinbutton", {name: "Pad A1 Loop crossfade (milliseconds)"}), "5");
  await expectProjectRevision(page, 7);
  expect(await inspectedPlayback(page)).toEqual({
    ...base,
    trigger_mode: "loop_toggle",
    reverse: true,
    pitch_cents: 350,
    pan: -100,
    loop_start_frame: 3_600,
    loop_crossfade_frames: 240,
  });
  // Ping-pong has no seam to blend, so choosing it clears the crossfade.
  await page.getByRole("button", {name: "Ping-pong", exact: true}).click();
  await expectProjectRevision(page, 8);
  const committed = {
    ...base,
    trigger_mode: "loop_toggle",
    reverse: true,
    pitch_cents: 350,
    pan: -100,
    loop_mode: "ping_pong",
    loop_start_frame: 3_600,
  };
  expect(await inspectedPlayback(page)).toEqual(committed);
  await expect(page.getByRole("spinbutton", {name: "Pad A1 Loop crossfade (milliseconds)"}))
    .toHaveCount(0);

  // cancelled: Escape mid-gesture previews, then restores without a commit.
  const pan = page.getByRole("slider", {name: "Pad A1 Pan"});
  const panReadout = page.locator(".pan-control output");
  const cancelOffset = await page.evaluate(() => window.__sampleProofOperations.length);
  const pointerId = ++pointerSequence;
  await pan.dispatchEvent("pointerdown", {pointerId, isPrimary: true, button: 0});
  await pan.fill("40");
  await expect(panReadout).toHaveText("R40");
  await pan.press("Escape");
  await expect(panReadout).toHaveText("L100");
  await pan.dispatchEvent("pointerup", {pointerId, isPrimary: true, button: 0});
  await expect.poll(() => page.evaluate((offset) =>
    window.__sampleProofOperations.slice(offset), cancelOffset))
    .toEqual(expect.arrayContaining(["sample.preview.set", "sample.preview.clear"]));
  expect(await page.evaluate((offset) =>
    window.__sampleProofOperations.slice(offset), cancelOffset)).not.toContain("sample.update_pad");
  await expectProjectRevision(page, 8);
  expect(await inspectedPlayback(page)).toEqual(committed);

  // refused: an out-of-range value and a stale revision change nothing.
  const outOfRange = await rawRequest(page, "sample.update_pad", {
    command_id: crypto.randomUUID(),
    expected_revision: 8,
    slot: SLOT_A1,
    playback: {...committed, pan: 101},
  });
  expect(outOfRange).toEqual(expect.objectContaining({
    ok: false,
    error: expect.objectContaining({code: "HOST_PROTOCOL_MISMATCH"}),
  }));
  const stale = await rawRequest(page, "sample.update_pad", {
    command_id: crypto.randomUUID(),
    expected_revision: 7,
    slot: SLOT_A1,
    playback: {...committed, pan: 0},
  });
  expect(stale).toEqual(expect.objectContaining({
    ok: false,
    error: expect.objectContaining({
      code: "REVISION_CONFLICT",
      details: {actual_revision: 8, expected_revision: 7},
    }),
  }));
  await expectProjectRevision(page, 8);
  expect(await inspectedPlayback(page)).toEqual(committed);

  // failed: a failed commit reports, and the control keeps committed truth.
  const reverse = page.getByRole("button", {name: "Reverse", exact: true});
  await page.evaluate(() => { window.__failNextSampleUpdate = true; });
  await reverse.click();
  await expect(page.getByRole("alert")).toContainText("Creator could not change this sound.");
  await expect(reverse).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => window.__failNextSampleUpdate)).toBe(false);
  await expectProjectRevision(page, 8);
  expect(await inspectedPlayback(page)).toEqual(committed);

  // reopened: the reload restores the same truth and the same controls.
  const projectId = (await rawRequest(page, "project.inspect", {})).result.project.project_id;
  await page.reload();
  await waitForProjectReopen(page, projectId.slice(0, 8));
  expect(await inspectedPlayback(page)).toEqual(committed);
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await selectPadWithoutPress(page, "Pad A1 — assigned — Key Q");
  await expect(page.getByRole("button", {name: "Reverse", exact: true}))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".pitch-control output")).toHaveText("+3.5 st");
  await expect(page.locator(".pan-control output")).toHaveText("L100");
  await expect(page.getByRole("button", {name: "Ping-pong", exact: true}))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("spinbutton", {name: "Pad A1 Loop start time (seconds)"}))
    .toHaveValue("0.025");
  noErrors();
});

// lmdj.project.v5 5.2.0. Each EQ key step previews; releasing the key commits
// once, so a held run of steps is one revision.
async function holdKeySteps(page, target, key, steps) {
  await target.focus();
  for (let step = 0; step < steps; step += 1) await page.keyboard.down(key);
  await page.keyboard.up(key);
}

test("Sample tone parity commits, cancels, refuses, fails and reopens through the real Runtime", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  const noErrors = recordPageErrors(page);
  await installHostProofRecorder(page);
  await page.goto("/index.html");
  await waitForBootProject(page);
  await activateAudio(page);
  await chooseSampleFile(page, "Add Sample to Pad A1", "tone.wav", pcm16Wav({frames: 4800}));
  await commitLongSourceSelection(page);
  await expectProjectRevision(page, 1);
  const base = await inspectedPlayback(page);
  // Release applies once the Pad stops being a one-shot.
  await page.getByRole("button", {name: "One Shot", exact: true}).click();
  await expectProjectRevision(page, 2);

  // normal: each control commits one revision.
  await slideAndRelease(page.getByRole("slider", {name: "Pad A1 Attack"}), "120");
  await expectProjectRevision(page, 3);
  await slideAndRelease(page.getByRole("slider", {name: "Pad A1 Release"}), "900");
  await expectProjectRevision(page, 4);
  await slideAndRelease(page.getByRole("slider", {name: "Pad A1 Tone"}), "-40");
  await expectProjectRevision(page, 5);
  await holdKeySteps(page, page.getByRole("slider", {name: "Pad A1 EQ High"}), "ArrowUp", 2);
  await expectProjectRevision(page, 6);
  // 36 half-dB steps reach the floor; one more makes the low shelf a cut.
  await holdKeySteps(page, page.getByRole("slider", {name: "Pad A1 EQ Low"}), "ArrowDown", 37);
  await expectProjectRevision(page, 7);
  // A real mouse drag up and right turns the mid band on, through the
  // browser's own hit-testing, focus and pointer capture.
  const mid = page.getByRole("slider", {name: "Pad A1 EQ Mid"});
  const poleCentre = async () => {
    await mid.scrollIntoViewIfNeeded();
    const box = await mid.boundingBox();
    return {x: box.x + box.width / 2, y: box.y + box.height / 2};
  };
  const centre = await poleCentre();
  await page.mouse.move(centre.x, centre.y);
  await page.mouse.down();
  await page.mouse.move(centre.x + 30, centre.y - 30, {steps: 5});
  await page.mouse.up();
  await expectProjectRevision(page, 8);
  const committed = await inspectedPlayback(page);
  expect(committed).toEqual({
    ...base,
    trigger_mode: "gate",
    attack_ms: 120,
    release_ms: 900,
    tone: -40,
    eq: {
      low: {kind: "cut", freq_hz: 100, gain_millidb: -18_000},
      mid: {freq_hz: expect.any(Number), gain_millidb: expect.any(Number), q_milli: 707},
      high: {kind: "shelf", freq_hz: 8_000, gain_millidb: 1_000},
    },
  });
  expect(committed.eq.mid.freq_hz).toBeGreaterThan(1_000);
  expect(committed.eq.mid.gain_millidb).toBeGreaterThan(0);

  // cancelled: Escape mid-gesture previews, then restores without a commit,
  // on a slider and on the EQ.
  const tone = page.getByRole("slider", {name: "Pad A1 Tone"});
  const toneReadout = page.locator(".tone-control output");
  const cancelOffset = await page.evaluate(() => window.__sampleProofOperations.length);
  const pointerId = ++pointerSequence;
  await tone.dispatchEvent("pointerdown", {pointerId, isPrimary: true, button: 0});
  await tone.fill("60");
  await expect(toneReadout).toHaveText("HP 60");
  await tone.press("Escape");
  await expect(toneReadout).toHaveText("LP 40");
  await tone.dispatchEvent("pointerup", {pointerId, isPrimary: true, button: 0});
  const high = page.getByRole("slider", {name: "Pad A1 EQ High"});
  await high.focus();
  await page.keyboard.down("ArrowUp");
  await expect(high).toHaveAttribute("aria-valuetext", "High shelf 8.00 kHz +1.5 dB");
  await page.keyboard.down("Escape");
  await page.keyboard.up("Escape");
  await page.keyboard.up("ArrowUp");
  await expect(high).toHaveAttribute("aria-valuetext", "High shelf 8.00 kHz +1.0 dB");
  // A pointer press never focuses the pole, so the browser delivers Escape to
  // whatever had focus; the drag still cancels.
  const midText = await mid.getAttribute("aria-valuetext");
  const grab = await poleCentre();
  await page.mouse.move(grab.x, grab.y);
  await page.mouse.down();
  await page.mouse.move(grab.x - 20, grab.y + 20, {steps: 4});
  await expect(mid).not.toHaveAttribute("aria-valuetext", midText);
  await page.keyboard.press("Escape");
  await expect(mid).toHaveAttribute("aria-valuetext", midText);
  await page.mouse.up();
  await expect.poll(() => page.evaluate((offset) =>
    window.__sampleProofOperations.slice(offset), cancelOffset))
    .toEqual(expect.arrayContaining(["sample.preview.set", "sample.preview.clear"]));
  expect(await page.evaluate((offset) =>
    window.__sampleProofOperations.slice(offset), cancelOffset)).not.toContain("sample.update_pad");
  await expectProjectRevision(page, 8);
  expect(await inspectedPlayback(page)).toEqual(committed);

  // refused: an out-of-range value and a stale revision change nothing.
  const outOfRange = await rawRequest(page, "sample.update_pad", {
    command_id: crypto.randomUUID(),
    expected_revision: 8,
    slot: SLOT_A1,
    playback: {...committed, eq: {...committed.eq, mid: {...committed.eq.mid, q_milli: 10_001}}},
  });
  expect(outOfRange).toEqual(expect.objectContaining({
    ok: false,
    error: expect.objectContaining({code: "HOST_PROTOCOL_MISMATCH"}),
  }));
  const stale = await rawRequest(page, "sample.update_pad", {
    command_id: crypto.randomUUID(),
    expected_revision: 7,
    slot: SLOT_A1,
    playback: {...committed, tone: 0},
  });
  expect(stale).toEqual(expect.objectContaining({
    ok: false,
    error: expect.objectContaining({
      code: "REVISION_CONFLICT",
      details: {actual_revision: 8, expected_revision: 7},
    }),
  }));
  await expectProjectRevision(page, 8);
  expect(await inspectedPlayback(page)).toEqual(committed);

  // failed: a failed commit reports, and the control keeps committed truth.
  const attackReadout = page.locator(".attack-control output");
  await page.evaluate(() => { window.__failNextSampleUpdate = true; });
  await slideAndRelease(page.getByRole("slider", {name: "Pad A1 Attack"}), "500");
  await expect(page.getByRole("alert")).toContainText("Creator could not change this sound.");
  await expect(attackReadout).toHaveText("120 ms");
  expect(await page.evaluate(() => window.__failNextSampleUpdate)).toBe(false);
  await expectProjectRevision(page, 8);
  expect(await inspectedPlayback(page)).toEqual(committed);

  // reopened: the reload restores the same truth and the same controls.
  const projectId = (await rawRequest(page, "project.inspect", {})).result.project.project_id;
  await page.reload();
  await waitForProjectReopen(page, projectId.slice(0, 8));
  expect(await inspectedPlayback(page)).toEqual(committed);
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await selectPadWithoutPress(page, "Pad A1 — assigned — Key Q");
  await expect(attackReadout).toHaveText("120 ms");
  await expect(page.locator(".release-control output")).toHaveText("900 ms");
  await expect(toneReadout).toHaveText("LP 40");
  await expect(page.getByRole("slider", {name: "Pad A1 EQ Low"}))
    .toHaveAttribute("aria-valuetext", "Low cut 100 Hz");
  await expect(page.getByRole("slider", {name: "Pad A1 EQ High"}))
    .toHaveAttribute("aria-valuetext", "High shelf 8.00 kHz +1.0 dB");
  await expect(page.getByRole("slider", {name: "Pad A1 EQ Mid"}))
    .not.toHaveAttribute("aria-valuetext", "Mid off");
  noErrors();
});

test("Pattern history keeps the Project open when its inventory anchor changes", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  const noErrors = recordPageErrors(page);
  await installHostProofRecorder(page);
  // A fresh store boots into a newly created, empty Project (#1660).
  await page.goto("/index.html");
  await waitForBootProject(page);
  const initial = (await rawRequest(page, "project.inspect", {})).result.project;
  const history = (await rawRequest(page, "history.inspect", {})).result;
  const originalPatternId = Object.keys(initial.patterns)[0];
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  // Choose unique UUIDs for this gesture; Runtime and storage still run normally.
  // Other gesture IDs can precede the Pattern ID, so inspect the committed ID.
  await page.evaluate(() => {
    window.__restoreHistoryProofUuid = crypto.randomUUID.bind(crypto);
    let next = 100;
    crypto.randomUUID = () => `00000000-0000-4000-8000-${String(next++).padStart(12, "0")}`;
  });
  await page.getByRole("button", {name: "Create Pattern", exact: true}).click();
  await expectProjectRevision(page, 1);
  await page.evaluate(() => { crypto.randomUUID = window.__restoreHistoryProofUuid; });
  const created = (await rawRequest(page, "project.inspect", {})).result.project;
  const earlierPatternId = Object.keys(created.patterns).find((id) => id !== originalPatternId);
  expect(earlierPatternId).toBeDefined();
  expect(earlierPatternId < originalPatternId).toBe(true);
  await pressRailUndo(page);
  await expectProjectRevision(page, 2);
  expect((await rawRequest(page, "project.inspect", {})).result.project.patterns).toEqual(initial.patterns);
  await pressRailRedo(page);
  await expectProjectRevision(page, 3);
  await expect(page.getByTestId("creator-phase")).toHaveText("ready");
  await expect(page.getByRole("combobox", {name: "Pattern"}).locator("option")).toHaveCount(2);
  expect((await rawRequest(page, "history.inspect", {})).result.session_id).toBe(history.session_id);
  await pressRailUndo(page);
  await expectProjectRevision(page, 4);
  expect((await rawRequest(page, "project.inspect", {})).result.project.patterns).toEqual(initial.patterns);
  noErrors();
});

test("Pad Delete commits while audio is inactive after a reopen", async ({page, browserName}) => {
  // #1724: Delete used to require a Runtime stop that is refused unless audio
  // runs, so a freshly reopened Project could not delete a Pad.
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  const noErrors = recordPageErrors(page);
  await page.goto("/index.html");
  await waitForBootProject(page);
  await activateAudio(page);
  await chooseSampleFile(page, "Add Sample to Pad A1", "inactive-delete.wav", pcm16Wav({frames: 4800}));
  await commitLongSourceSelection(page);
  await expectProjectRevision(page, 1);
  const before = (await rawRequest(page, "project.inspect", {})).result.project;
  expect(before.banks[0].pads[0].asset_id).not.toBeNull();

  await page.reload();
  await waitForProjectReopen(page, before.project_id.slice(0, 8));
  await expect(page.getByTestId("audio-state")).toHaveText("Audio inactive");
  // Boot lands on Sample, where "Replace Sample" and "Record Sample" also
  // match a loose name, so the mode key is named exactly.
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  await expect(page.getByRole("button", {name: "Delete Pad A1", exact: true})).toBeEnabled();
  await page.getByRole("button", {name: "Delete Pad A1", exact: true}).click();
  await expectProjectRevision(page, 2);
  await expect(page.getByRole("button", {name: "Pad A1 — empty — Key Q", exact: true})).toBeVisible();
  await expect(page.getByText("That can't be done right now.")).toHaveCount(0);
  const deleted = (await rawRequest(page, "project.inspect", {})).result.project;
  expect(deleted.banks[0].pads[0].asset_id).toBeNull();
  expect(deleted.patterns).toEqual(before.patterns);
  expect(deleted.assets).toEqual(before.assets);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio inactive");
  noErrors();
});

test("Pad Delete preserves recorded rhythm through Undo, Redo, reassignment and reopen", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  const noErrors = recordPageErrors(page);
  await installHostProofRecorder(page);
  await page.goto("/index.html");
  await waitForBootProject(page);
  await activateAudio(page);
  await chooseSampleFile(page, "Add Sample to Pad A1", "delete-source.wav", pcm16Wav({frames: 4800}));
  await commitLongSourceSelection(page);
  await expectProjectRevision(page, 1);

  // Record one actual admitted press, then settle the recording before Delete.
  const physical = page.getByTestId("physical-controls");
  const play = physical.getByRole("button", {name: /^Play\/Stop/});
  const record = physical.getByRole("button", {name: /^Record\b/});
  const transportStatus = (text) => page.getByRole("status").filter({
    has: page.getByTestId("creator-phase"), hasText: text,
  });
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await play.click();
  await expect(transportStatus("playing")).toBeVisible();
  await record.click();
  await expect(transportStatus("recording")).toBeVisible();
  const triggerOffset = await page.evaluate(() => window.__sampleProofResponses.length);
  await page.keyboard.press("KeyQ");
  await expect.poll(() => page.evaluate((offset) =>
    window.__sampleProofResponses.slice(offset).some((entry) => entry.operation === "trigger" && entry.ok),
  triggerOffset), {timeout: 30_000}).toBe(true);
  await record.click();
  await expect(transportStatus("playing")).toBeVisible();
  await play.click();
  await expect(transportStatus("stopped")).toBeVisible();
  await expectProjectRevision(page, 2);
  const recorded = (await rawRequest(page, "project.inspect", {})).result.project;
  expect(Object.values(recorded.patterns).flatMap((pattern) => pattern.events)).toHaveLength(1);
  await enterSampleEditor(page);
  // The surface remounts with the prior cached inspect while its authoritative
  // refresh is pending. Delete stays unavailable until the new revision lands.
  await expect(page.getByRole("button", {name: "Delete Pad A1", exact: true})).toBeEnabled();
  await page.getByRole("button", {name: "Loop", exact: true}).click();
  await expectProjectRevision(page, 3);
  const before = (await rawRequest(page, "project.inspect", {})).result.project;
  const oldAsset = before.banks[0].pads[0].asset_id;
  const oldArtifact = before.assets[oldAsset].artifact;
  expect(oldArtifact.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(oldArtifact.byte_length).toBeGreaterThan(44);
  const {redo} = railHistoryKeys(page);

  await page.getByRole("button", {name: "Delete Pad A1", exact: true}).click();
  await expectProjectRevision(page, 4);
  await expect(page.getByRole("button", {name: "Pad A1 — empty — Key Q", exact: true})).toBeVisible();
  const deleted = (await rawRequest(page, "project.inspect", {})).result.project;
  expect(deleted.patterns).toEqual(before.patterns);
  expect(deleted.assets).toEqual(before.assets);
  const cleared = (await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result;
  expect(cleared.asset_id).toBeNull();
  expect(cleared.playback).toEqual({trim_start_frame: 0, trim_end_frame: null,
    trigger_mode: "one_shot", gain_millidb: 0, muted: false});
  const deletion = await page.evaluate(() => window.__sampleProofResponses
    .findLast((entry) => entry.operation === "pad.delete"));
  expect(deletion).toMatchObject({ok: true, result: {
    committed_revision: 4, runtime_revision: 4, runtime_published: true,
  }});
  // The native host.web_control_runtime companion renders and checks both PCM
  // channels are exactly silent after deleting an active voice. Publication
  // here is real Wasm/OPFS/AudioWorklet evidence, not physical listening.
  await pressRailUndo(page);
  await expectProjectRevision(page, 5);
  const restored = (await rawRequest(page, "project.inspect", {})).result.project;
  expect(restored.banks).toEqual(before.banks);
  expect(restored.patterns).toEqual(before.patterns);
  expect(restored.assets[oldAsset].artifact).toEqual(oldArtifact);
  await expect(page.getByRole("button", {name: "Loop", exact: true})).toHaveAttribute("aria-pressed", "true");
  await pressRailRedo(page);
  await expectProjectRevision(page, 6);
  expect((await rawRequest(page, "project.inspect", {})).result.project.banks).toEqual(deleted.banks);
  await chooseSampleFile(page, "Add Sample to Pad A1", "new-sound.wav", pcm16Wav({frames: 9600, phase: 7}));
  await commitLongSourceSelection(page);
  await expectProjectRevision(page, 7);
  const reassigned = (await rawRequest(page, "project.inspect", {})).result.project;
  expect(reassigned.patterns).toEqual(before.patterns);
  expect(reassigned.banks[0].pads[0].asset_id).not.toBe(oldAsset);
  expect(reassigned.assets[oldAsset].artifact).toEqual(oldArtifact);
  await expect(redo).not.toHaveClass(RAIL_LIT);
  await page.reload();
  await waitForProjectReopen(page, reassigned.project_id.slice(0, 8));
  expect((await rawRequest(page, "project.inspect", {})).result.project).toEqual(reassigned);
  const reopened = (await rawRequest(page, "history.inspect", {})).result;
  expect(reopened.undo_count).toBe(0);
  expect(reopened.redo_count).toBe(0);
  noErrors();
});
