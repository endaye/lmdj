import {readFile} from "node:fs/promises";

import {expect, test} from "@playwright/test";


const sampleBundle = process.env.LMDJ_CREATOR_WEB_SAMPLE_BUNDLE;

const SLOT_A1 = {bank: 0, pad: 0};
// Every audio lifecycle gesture owns one independently bounded 30-second
// Runtime request, so the state that follows an accepted gesture is promised
// only within that bound plus bounded render settling.
const AUDIO_TRANSITION_TIMEOUT_MS = 30_000 + 5_000;
let pointerSequence = 10;

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
                      message: "Sample runtime preparation failed",
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
  const report = await downloadReport(page);
  expect(report.sample.project_revision).toBe(expectedRevision);
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
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(sampleBundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.getByText("44 / 64")).toBeVisible();
  await expect(page.locator(".project-summary")).toContainText("Revision46");
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
  await page.getByRole("button", {name: label}).evaluate((element) => element.click());
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

test("packaged Sample Editor proves the real Facade v1-to-v2 journey", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(600_000);
  await installHostProofRecorder(page);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await activateAudio(page);
  await enterSampleEditor(page);

  await expect(page.getByRole("button", {name: "Pad A1 — empty"})).toBeVisible();
  await chooseSampleFile(
    page,
    "Add Sample to Pad A1",
    "proof-ramp.wav",
    pcm16Wav({}),
  );
  await commitLongSourceSelection(page);
  await expect(page.getByRole("button", {name: "Pad A1 — assigned"}))
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
  const padA1 = page.getByRole("button", {name: "Pad A1 — assigned"});
  await heldPadGesture(page, padA1, ["started", "completed"]);

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
    "why: the source container is not supported; remedy: choose WAV, MP3, M4A/AAC, or FLAC audio",
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
  expect(conflict).toEqual(expect.objectContaining({
    ok: false,
    error: expect.objectContaining({
      code: "REVISION_CONFLICT",
      details: {actual_revision: 55, expected_revision: 54},
    }),
  }));
  await expectProjectRevision(page, 55);

  await selectPadWithoutPress(page, "Pad A2 — assigned");
  await expect(page.getByText(/^Asset /)).toBeVisible({timeout: 30_000});
  const a2Loop = page.getByRole("button", {name: "Loop"});
  await waitForControlMutation(page, a2Loop, () => a2Loop.click(), 56);
  const padA2 = page.getByRole("button", {name: "Pad A2 — assigned"});
  await heldPadGesture(page, padA2, ["started"]);

  await selectPadWithoutPress(page, "Pad A1 — assigned");
  const a1Mute = page.getByRole("button", {name: "Mute"});
  await waitForControlMutation(page, a1Mute, () => a1Mute.click(), 57);

  await selectPadWithoutPress(page, "Pad A3 — assigned");
  const a3Loop = page.getByRole("button", {name: "Loop"});
  await waitForControlMutation(page, a3Loop, () => a3Loop.click(), 58);
  await heldPadGesture(
    page,
    page.getByRole("button", {name: "Pad A3 — assigned"}),
    ["started"],
  );

  await selectPadWithoutPress(page, "Pad A4 — assigned");
  const a4Loop = page.getByRole("button", {name: "Loop"});
  await waitForControlMutation(page, a4Loop, () => a4Loop.click(), 59);
  await heldPadGesture(
    page,
    page.getByRole("button", {name: "Pad A4 — assigned"}),
    ["started"],
  );

  await selectPadWithoutPress(page, "Pad A1 — assigned");
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
  await expect(page.getByRole("button", {name: "Open Project 00000000"}))
    .toBeVisible({timeout: 60_000});
  await page.getByRole("button", {name: "Open Project 00000000"}).click();
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.locator(".project-summary")).toContainText("Revision60");
  await expect(page.getByText("45 / 64")).toBeVisible();
  await enterSampleEditor(page);
  await expect(page.getByRole("button", {name: "Pad A1 — assigned"})).toBeVisible();
  await expectProjectRevision(page, 60);
  const postReloadOperations = await page.evaluate(() => window.__sampleProofOperations ?? []);
  expect(postReloadOperations.filter((operation) => operation === "sample.import.commit"))
    .toHaveLength(0);

  // F5: a pointer drag aimed at a trim grip moves only that trim point. The
  // retired invisible range bands grabbed the wrong handle or jumped the
  // trim point to the pressed track position.
  await selectPadWithoutPress(page, "Pad A1 — assigned");
  await expect(page.getByRole("img", {name: "Pad A1 mirrored waveform"}))
    .toBeVisible({timeout: 120_000});
  const trimStart = page.getByRole("spinbutton", {name: "Pad A1 Start time (seconds)"});
  const trimEnd = page.getByRole("spinbutton", {name: "Pad A1 End time (seconds)"});
  await expect(trimStart).toHaveValue("0");
  await expect(trimEnd).toHaveValue("2");
  const dragGrip = async (grip, deltaX) => {
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

test("Sample Editor WebKit capability boundary is explicit, private, and non-physical", async ({page, browserName}) => {
  test.skip(browserName !== "webkit");
  await installHostProofRecorder(page);
  await page.goto("/index.html");
  await expect(page.getByTestId("creator-phase")).toHaveText("unsupported", {
    timeout: 30_000,
  });
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("UNSUPPORTED_WEB_RUNTIME");
  const publicText = await alert.textContent();
  expect(publicText).not.toMatch(/HOST_PROTOCOL_MISMATCH|\/Users\/|file:\/\/|\.lmdj|\.wav/i);
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
  await expect(page.getByRole("button", {name: "Pad A1 — empty"})).toBeVisible();
  await chooseSampleFile(
    page,
    "Add Sample to Pad A1",
    "proof-ramp.wav",
    pcm16Wav({}),
  );
  await commitLongSourceSelection(page);
  await expect(page.getByRole("button", {name: "Pad A1 — assigned"}))
    .toBeVisible({timeout: 120_000});
  await expectProjectRevision(page, 47);

  // Re-importing the original bundle is refused as DUPLICATE_ID: the local
  // copy of the same Project has newer changes. The refusal must present as
  // a recoverable situation, not as "Creator unavailable".
  await page.getByRole("button", {name: "Suspend audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await page.getByRole("button", {name: "Project"}).click();
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
  await expect(page.locator(".project-summary")).toContainText("Revision47");
});
