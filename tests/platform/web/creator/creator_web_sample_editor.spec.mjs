import {showSampleDetails} from "./fixtures/creator_navigation.mjs";
import {
  clickCreatorSystemAction,
  showSamplePage,
  createSequencePattern,
  openCreatorSystem,
  sequencePattern,
} from "./fixtures/creator_navigation.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {readFile, writeFile} from "node:fs/promises";

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
  await showRailHistoryLayer(page);
  await keys.undo.click();
}
async function pressRailRedo(page) {
  const keys = railHistoryKeys(page);
  await showRailHistoryLayer(page);
  await keys.redo.click();
}

async function showRailHistoryLayer(page) {
  const shift = railHistoryKeys(page).shift;
  if (await shift.getAttribute("aria-pressed") !== "true") await shift.click();
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
        window.__sampleInputProof = [];
        window.__sampleVoiceProof = [];
        nativeTransport.subscribe(message => {
          if (message.event === "runtime.voice_state") {
            window.__sampleVoiceProof.push(...structuredClone(message.payload.events));
          }
        });
        // Observe actual transport receipts only; never issue a synthetic
        // inspection or consume. Admission cannot enter the proof counter.
        const inputAdmissions = new Map();
        const consumedInputs = new Set();
        const ticketKey = ticket => JSON.stringify([ticket?.command_id,
          ticket?.runtime_generation, ticket?.frame_epoch, ticket?.ticket]);
        const observeInput = (request, response) => {
          if (request?.operation === "pattern.transport.input.request" &&
              request.payload?.kind === "press" && response?.ok === true &&
              response.request_id === request.request_id) {
            const ticket = {command_id: request.payload.command_id,
              runtime_generation: request.payload.runtime_generation,
              frame_epoch: request.payload.frame_epoch, ticket: request.payload.input_serial};
            const sameTicket = value => Object.keys(ticket).length === Object.keys(value ?? {}).length &&
              Object.entries(ticket).every(([key, expected]) => value?.[key] === expected);
            if (sameTicket(response.result?.ticket) && sameTicket(response.result?.status?.ticket)) {
              inputAdmissions.set(ticketKey(ticket), structuredClone({request, response}));
            }
          }
          if (request?.operation !== "pattern.transport.input.inspect" ||
              request.payload?.consume !== true || response?.ok !== true ||
              response.request_id !== request.request_id) return null;
          const key = ticketKey(request.payload);
          const original = inputAdmissions.get(key);
          if (!original || consumedInputs.has(key)) return null;
          const status = response.result;
          const admission = original.response.result.status.admission;
          const native = status?.native_result;
          if (!admission?.authority) return null;
          const ticket = original.response.result.ticket;
          const decimal = value => typeof value === "string" && /^[1-9][0-9]*$/.test(value) &&
            BigInt(value) <= 18446744073709551615n;
          if (Object.keys(ticket).length !== Object.keys(status?.ticket ?? {}).length ||
              !Object.entries(ticket).every(([field, expected]) => status.ticket[field] === expected) ||
              status.complete !== true || status.durable_settled !== true || status.error !== null ||
              (admission.authority.recording === true && status.retained !== true) ||
              !native || native.disposition !== "voice_started" ||
              JSON.stringify(status.admission) !== JSON.stringify(admission) ||
              !decimal(native.sequence) || native.sequence !== admission.sequence ||
              !decimal(native.acceptance_ordinal) || native.acceptance_ordinal !== admission.acceptance_ordinal ||
              native.runtime_generation !== ticket.runtime_generation || native.frame_epoch !== ticket.frame_epoch ||
              native.slot !== original.request.payload.slot || native.held_press_sequence !== null ||
              JSON.stringify(native.authority) !== JSON.stringify(admission.authority) ||
              !Number.isSafeInteger(native.runtime_frame) || native.runtime_frame < 0 ||
              !Number.isSafeInteger(Number(native.sequence)) || Number(native.sequence) <= 0) return null;
          consumedInputs.add(key);
          return {payload: original.request.payload, ok: response.ok, sequence: Number(native.sequence),
            operation: "pattern.transport.input.inspect", status: structuredClone(status),
            evidence: {admission: original, consume: structuredClone({request, response})}};
        };

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
              const consumed = observeInput(request, response);
              if (consumed) window.__sampleInputProof.push(consumed);
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
  await clickCreatorSystemAction(page, "Export report");
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
  await expect(page.getByTestId("project-overview")
    .getByText("44 Pads · 1 Patterns", {exact: true})).toBeVisible();
  await expect(page.getByRole("button", {name: "Select Project 00000000", exact: true}))
    .toContainText("Revision 46");
  const inspected = await rawRequest(page, "project.inspect", {});
  expect(inspected.ok, JSON.stringify(inspected.error ?? null)).toBe(true);
  expect(inspected.result.project.banks).toHaveLength(4);
  for (const bank of inspected.result.project.banks) expect(bank.pads).toHaveLength(16);
  expect(inspected.result.project.banks.flatMap(bank => bank.pads)
    .filter(pad => typeof pad.asset_id === "string")).toHaveLength(44);
  await expectProjectRevision(page, 46);
}

async function activateAudio(page) {
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: 30_000,
  });
}

async function enterSampleEditor(page) {
  await page.getByRole("button", {name: "Sample"}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  // The wake gesture selects its assigned Pad. This journey edits A1 explicitly.
  await selectPadWithoutPress(page, await page.getByRole("button", {name: /^Pad A01 —/}).getAttribute("aria-label"));
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
  await showSamplePage(page, "Pad");
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
  // Select the console Pad without synthesizing a musical press or opening
  // the empty-Pad file chooser. Actual audio input is proved separately.
  await page.getByRole("button", {name: label, exact: true}).evaluate((element) =>
    element.dispatchEvent(new MouseEvent("click", {bubbles: true, detail: 1})));
}

async function expectDefaultPlaybackUi(page) {
  await showSamplePage(page, "Playback");
  await expect(page.getByRole("button", {name: "Loop"}))
    .toHaveAttribute("aria-pressed", "false");
  await showSamplePage(page, "Playback");
  await expect(page.getByRole("button", {name: "One Shot"}))
    .toHaveAttribute("aria-pressed", "true");
  await showSamplePage(page, "Playback");
  await expect(page.getByRole("button", {name: "Mute"}))
    .toHaveAttribute("aria-pressed", "false");
  await showSamplePage(page, "Playback");
  await expect(page.getByRole("slider", {name: "Pad A01 Volume"})).toHaveValue("0");
  await showSamplePage(page, "Trim");
  await expect(page.getByRole("spinbutton", {name: "Pad A01 Start time (seconds)"}))
    .toHaveValue("0");
  await showSamplePage(page, "Trim");
  await expect(page.getByRole("spinbutton", {name: "Pad A01 End time (seconds)"}))
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

  await expect(page.getByRole("button", {name: "Pad A01 — empty — Key Z", exact: true})).toBeVisible();
  await chooseSampleFile(
    page,
    "Add Sample to Pad A01",
    "proof-ramp.wav",
    pcm16Wav({}),
  );
  await commitLongSourceSelection(page);
  await expect(page.getByRole("button", {name: "Pad A01 — assigned — Key Z", exact: true}))
    .toBeVisible({timeout: 120_000});
  await showSamplePage(page, "Trim");
  await expect(page.getByRole("img", {name: "Pad A01 mirrored waveform"}))
    .toBeVisible({timeout: 120_000});
  await expectProjectRevision(page, 47);
  await showSampleDetails(page);
  await expect(page.getByText("48 kHz · Mono · 96,000 frames")).toBeVisible();
  await showSamplePage(page, "Trim");
  await expectDefaultPlaybackUi(page);

  const waveformPath = page.locator("path[data-waveform]");
  assertMirroredWaveform(await waveformPath.getAttribute("d"));
  const editor = page.locator("[data-waveform-viewport]");
  expect(await editor.getAttribute("data-viewport-start")).toBe("0");
  expect(await editor.getAttribute("data-viewport-end")).toBe("96000");
  await showSamplePage(page, "Trim");
  await page.getByRole("button", {name: "Zoom In"}).click();
  await expect(editor).not.toHaveAttribute("data-viewport-end", "96000");
  await page.getByRole("button", {name: "Fit waveform"}).click();
  await expect(editor).toHaveAttribute("data-viewport-start", "0");
  await expect(editor).toHaveAttribute("data-viewport-end", "96000");

  await showSamplePage(page, "Trim");
  const startTime = page.getByRole("spinbutton", {name: "Pad A01 Start time (seconds)"});
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
  const padA1 = page.getByRole("button", {name: "Pad A01 — assigned — Key Z", exact: true});
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

  await showSamplePage(page, "Playback");
  const loop = page.getByRole("button", {name: "Loop"});
  await showSamplePage(page, "Playback");
  const oneShot = page.getByRole("button", {name: "One Shot"});
  await waitForControlMutation(page, oneShot, () => oneShot.click(), 49);
  await expect(oneShot).toHaveAttribute("aria-pressed", "false");
  await heldPadGesture(page, padA1, ["started", "stopped"]);

  await waitForControlMutation(page, loop, () => loop.click(), 50);
  await showSamplePage(page, "Playback");
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

  await showSamplePage(page, "Playback");
  const volume = page.getByRole("slider", {name: "Pad A01 Volume"});
  await volume.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(volume).toBeDisabled({timeout: 10_000});
  await expect(volume).toBeEnabled({timeout: 120_000});
  await expectProjectRevision(page, 52);
  await expect(volume).toHaveValue("-0.1");

  await showSamplePage(page, "Playback");
  const mute = page.getByRole("button", {name: "Mute"});
  await waitForControlMutation(page, mute, () => mute.click(), 53);
  await expect(mute).toHaveAttribute("aria-pressed", "true");
  await showSamplePage(page, "Pad");
  const reset = page.getByRole("button", {name: "Reset Pad to Defaults"});
  await reset.click();
  await expect(page.getByRole("dialog", {name: "Reset Pad A01?"})).toBeVisible();
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
  await expect(page.getByRole("dialog", {name: "Replace Pad A01?"})).toBeVisible();
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
  await showSamplePage(page, "Pad");
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

  await selectPadWithoutPress(page, "Pad A02 — assigned — Key X");
  await showSampleDetails(page);
  await expect(page.locator(".sample-details div").filter({
    has: page.locator("dt", {hasText: /^Asset ID$/}),
  }).locator("dd")).toHaveText(/^[0-9a-f-]{36}$/, {timeout: 30_000});
  await showSamplePage(page, "Playback");
  const a2Loop = page.getByRole("button", {name: "Loop"});
  await waitForControlMutation(page, a2Loop, () => a2Loop.click(), 56);
  const padA2 = page.getByRole("button", {name: "Pad A02 — assigned — Key X", exact: true});
  await heldPadGesture(page, padA2, ["started"]);

  await selectPadWithoutPress(page, "Pad A01 — assigned — Key Z");
  await showSamplePage(page, "Playback");
  const a1Mute = page.getByRole("button", {name: "Mute"});
  await waitForControlMutation(page, a1Mute, () => a1Mute.click(), 57);

  await selectPadWithoutPress(page, "Pad A03 — assigned — Key C");
  await showSamplePage(page, "Playback");
  const a3Loop = page.getByRole("button", {name: "Loop"});
  await waitForControlMutation(page, a3Loop, () => a3Loop.click(), 58);
  await heldPadGesture(
    page,
    page.getByRole("button", {name: "Pad A03 — assigned — Key C", exact: true}),
    ["started"],
  );

  await selectPadWithoutPress(page, "Pad A04 — assigned — Key V");
  await showSamplePage(page, "Playback");
  const a4Loop = page.getByRole("button", {name: "Loop"});
  await waitForControlMutation(page, a4Loop, () => a4Loop.click(), 59);
  await heldPadGesture(
    page,
    page.getByRole("button", {name: "Pad A04 — assigned — Key V", exact: true}),
    ["started"],
  );

  await selectPadWithoutPress(page, "Pad A01 — assigned — Key Z");
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
  await expect(page.getByText("Sample saved · playback needs preparation.")).toBeVisible();
  await page.getByText("Sample playback details", {exact: true}).click();
  await expect(page.getByText(
    "Saved at revision 60; Runtime is still revision 59",
  )).toBeVisible(
    {timeout: 120_000},
  );
  expect(await page.evaluate(() => window.__sampleProofObservedResourceFailure)).toBe(true);
  await expectProjectRevision(page, 60);

  await clickCreatorSystemAction(page, "Suspend audio");
  // An explicit Suspend publishes "Audio suspended" only after the Runtime has
  // committed the suspend, so the Activate gesture that follows is guaranteed
  // to be accepted. Both gestures own one independently bounded 30-second
  // Runtime request, which Playwright's 5-second default does not cover.
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  // A1 Truth is unmuted at 60 while retained Runtime 59 still mutes A1.
  // A5 was not edited: prove the resume gesture against an audible Pad, then
  // return to the failed A1 preparation without admitting another gesture.
  await wakeAudioWithPad(page, {padAddress: "A05"});
  await selectPadWithoutPress(page, "Pad A01 — assigned — Key Z");
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
  await expect(page.locator(".creator-details-facts")).toContainText("Rev60");
  await expect(page.getByTestId("project-overview")
    .getByText("45 Pads · 1 Patterns", {exact: true})).toBeVisible();
  const reopenedPadTruth = await rawRequest(page, "project.inspect", {});
  expect(reopenedPadTruth.ok, JSON.stringify(reopenedPadTruth.error ?? null)).toBe(true);
  expect(reopenedPadTruth.result.project.banks).toHaveLength(4);
  for (const bank of reopenedPadTruth.result.project.banks) expect(bank.pads).toHaveLength(16);
  expect(reopenedPadTruth.result.project.banks.flatMap(bank => bank.pads)
    .filter(pad => typeof pad.asset_id === "string")).toHaveLength(45);
  await enterSampleEditor(page);
  await expect(page.getByRole("button", {name: "Pad A01 — assigned — Key Z", exact: true})).toBeVisible();
  await expectProjectRevision(page, 60);
  const postReloadOperations = await page.evaluate(() => window.__sampleProofOperations ?? []);
  expect(postReloadOperations.filter((operation) => operation === "sample.import.commit"))
    .toHaveLength(0);

  // F5: a pointer drag aimed at a trim grip moves only that trim point. The
  // retired invisible range bands grabbed the wrong handle or jumped the
  // trim point to the pressed track position.
  await selectPadWithoutPress(page, "Pad A01 — assigned — Key Z");
  await showSamplePage(page, "Trim");
  await expect(page.getByRole("img", {name: "Pad A01 mirrored waveform"}))
    .toBeVisible({timeout: 120_000});
  await showSamplePage(page, "Trim");
  const trimStart = page.getByRole("spinbutton", {name: "Pad A01 Start time (seconds)"});
  await showSamplePage(page, "Trim");
  const trimEnd = page.getByRole("spinbutton", {name: "Pad A01 End time (seconds)"});
  await expect(trimStart).toHaveValue("0");
  await expect(trimEnd).toHaveValue("2");
  const dragGrip = async (grip, deltaX, beforeRelease) => {
    // The touch workspace is a fixed 368 × 368 region that scrolls; the mouse
    // must be aimed at where the grip actually is, not where it was laid out.
    await expect(grip).toBeVisible();
    await grip.scrollIntoViewIfNeeded();
    const box = await grip.boundingBox();
    expect(box).not.toBeNull();
    const pressX = box.x + box.width / 2;
    const pressY = box.y + box.height / 2;
    await page.mouse.move(pressX, pressY);
    await page.mouse.down();
    await page.mouse.move(pressX + deltaX, pressY, {steps: 4});
    await beforeRelease?.();
    await page.mouse.up();
  };
  await waitForControlMutation(page, trimStart, async () => {
    await dragGrip(page.locator('[data-grip-zone="start"]'), 40, async () => {
      const startSeconds = Number(await trimStart.inputValue());
      expect(startSeconds).toBeGreaterThan(0);
      await expect(page.locator(".sample-overview-facts")).toContainText(
        `${startSeconds.toFixed(3)} – 2.000 s`);
      const truth = await rawRequest(page, "sample.inspect", {slot: SLOT_A1});
      expect(truth.result.project_revision).toBe(60);
      expect(truth.result.playback.trim_start_frame).toBe(0);
    });
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
    "Add Sample to Pad A01",
    "bank-quota-plus-one.wav",
    pcm16Wav({frames: 16_777_217}),
  );
  const quotaBoundFrames = Number(await page.getByRole("slider", {
    name: "Long source selection length",
  }).inputValue());
  expect(quotaBoundFrames).toBeLessThan(16_777_217);
  expect(44 + quotaBoundFrames * 2).toBeGreaterThan(1_048_576);
  await commitLongSourceSelection(page);

  await expect(page.getByRole("button", {name: "Pad A01 — assigned — Key Z", exact: true}))
    .toBeVisible({timeout: 120_000});
  await showSampleDetails(page);
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
  await openCreatorSystem(page);
  await expect(page.getByRole("region", {name: "System", exact: true}))
    .toBeVisible();
  await page.getByText(/^Developer diagnostics \(\d+\)$/).click();
  await expect(page.getByRole("region", {name: "Developer diagnostics"}))
    .toContainText("UNSUPPORTED_WEB_RUNTIME");
  expect(await page.evaluate(() => window.lmdjWebRuntimeHost === undefined)).toBe(true);
  await expect(page.getByRole("button", {name: "Activate audio"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Export report"})).toBeDisabled();
  await page.getByRole("button", {name: "Back to music", exact: true}).click();
  await expect(alert).toContainText("This browser cannot run Creator.");
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
  // Sample to Pad A01 advances the local Project to revision 47.
  await expect(page.getByRole("button", {name: "Pad A01 — empty — Key Z", exact: true})).toBeVisible();
  await chooseSampleFile(
    page,
    "Add Sample to Pad A01",
    "proof-ramp.wav",
    pcm16Wav({}),
  );
  await commitLongSourceSelection(page);
  await expect(page.getByRole("button", {name: "Pad A01 — assigned — Key Z", exact: true}))
    .toBeVisible({timeout: 120_000});
  await expectProjectRevision(page, 47);

  // Re-importing the original bundle is refused as DUPLICATE_ID: the local
  // copy of the same Project has newer changes. The refusal must present as
  // a recoverable situation, not as "Creator unavailable".
  await clickCreatorSystemAction(page, "Suspend audio");
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
  await diverged.getByRole("button", {name: "Select Project 00000000"}).click();
  await page.getByRole("button", {name: "Open Project 00000000"}).click();
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.locator(".creator-details-facts")).toContainText("Rev47");
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
  await showRailHistoryLayer(page);
  await expect(undo).not.toHaveClass(RAIL_LIT);
  await expect(redo).not.toHaveClass(RAIL_LIT);
  await activateAudio(page);
  await chooseSampleFile(page, "Add Sample to Pad A01", "history.wav", pcm16Wav({frames: 4800}));
  await commitLongSourceSelection(page);
  await expectProjectRevision(page, 1);
  const imported = (await rawRequest(page, "project.inspect", {})).result.project;
  await showRailHistoryLayer(page);
  await expect(undo).toHaveClass(RAIL_LIT);
  await showSamplePage(page, "Playback");
  await page.getByRole("button", {name: "Mute", exact: true}).click();
  await expectProjectRevision(page, 2);
  expect((await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.playback.muted).toBe(true);
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  // On Sequence, ← without SHIFT steps Patterns (Desktop Final T6); the
  // history lamp and Undo are on the SHIFT layer, still lit across modes.
  await railHistoryKeys(page).shift.click();
  await showRailHistoryLayer(page);
  await expect(undo).toHaveClass(RAIL_LIT);
  await undo.click();
  await expectProjectRevision(page, 3);
  expect((await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.playback.muted).toBe(false);
  await pressRailUndo(page);
  await expectProjectRevision(page, 4);
  const cleared = (await rawRequest(page, "project.inspect", {})).result.project;
  expect(cleared.assets).toEqual({});
  expect(cleared.banks[0].pads[0].asset_id).toBeNull();
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await showRailHistoryLayer(page);
  await expect(redo).toHaveClass(RAIL_LIT);
  await chooseSampleFile(page, "Add Sample to Pad A01", "cancelled.wav", pcm16Wav({frames: 9600}));
  const draft = page.getByRole("dialog", {name: /Pad A01 Long Source/});
  await expect(draft).toBeVisible();
  await draft.getByRole("button", {name: "Cancel", exact: true}).click();
  const retained = (await rawRequest(page, "history.inspect", {})).result;
  expect(retained.project_revision).toBe(4);
  expect(retained.redo_count).toBe(2);
  const refused = await rawRequest(page, "history.redo", {session_id: retained.session_id,
    command_id: crypto.randomUUID(), expected_revision: 3});
  expect(refused.ok).toBe(false);
  expect((await rawRequest(page, "history.inspect", {})).result).toEqual(retained);
  await showRailHistoryLayer(page);
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
  await showSamplePage(page, "Playback");
  await expect(page.getByRole("button", {name: "Mute", exact: true})).toHaveAttribute("aria-pressed", "false");
  await showSamplePage(page, "Playback");
  await page.getByRole("button", {name: "Loop", exact: true}).click();
  await expectProjectRevision(page, 8);
  await showRailHistoryLayer(page);
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
  await showRailHistoryLayer(page);
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
  await chooseSampleFile(page, "Add Sample to Pad A01", "parity.wav", pcm16Wav({frames: 4800}));
  await commitLongSourceSelection(page);
  await expectProjectRevision(page, 1);
  const base = await inspectedPlayback(page);
  expect(Object.keys(base).sort()).toEqual(
    ["gain_millidb", "muted", "trigger_mode", "trim_end_frame", "trim_start_frame"]);

  // normal: every parity control commits one revision.
  await showSamplePage(page, "Playback");
  await page.getByRole("button", {name: "Reverse", exact: true}).click();
  await expectProjectRevision(page, 2);
  await showSamplePage(page, "Playback");
  await slideAndRelease(page.getByRole("slider", {name: "Pad A01 Pitch"}), "3.5");
  await expectProjectRevision(page, 3);
  await showSamplePage(page, "Playback");
  await slideAndRelease(page.getByRole("slider", {name: "Pad A01 Pan"}), "-100");
  await expectProjectRevision(page, 4);
  await showSamplePage(page, "Playback");
  await page.getByRole("button", {name: "Loop", exact: true}).click();
  await expectProjectRevision(page, 5);
  // Reverse is on, so the card edits the mirrored boundary: 0.025 s is frame
  // 1 200 from Start, stored as 0 + 4 800 - 1 200 = 3 600.
  await showSamplePage(page, "Trim");
  await editValueCard(
    page.getByRole("spinbutton", {name: "Pad A01 Loop start time (seconds)"}), "0.025");
  await expectProjectRevision(page, 6);
  await showSamplePage(page, "Trim");
  await editValueCard(
    page.getByRole("spinbutton", {name: "Pad A01 Loop crossfade (milliseconds)"}), "5");
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
  await showSamplePage(page, "Playback");
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
  await showSamplePage(page, "Trim");
  await expect(page.getByRole("spinbutton", {name: "Pad A01 Loop crossfade (milliseconds)"}))
    .toHaveCount(0);

  // cancelled: Escape mid-gesture previews, then restores without a commit.
  await showSamplePage(page, "Playback");
  const pan = page.getByRole("slider", {name: "Pad A01 Pan"});
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
  await showSamplePage(page, "Playback");
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
  await selectPadWithoutPress(page, "Pad A01 — assigned — Key Z");
  await showSamplePage(page, "Playback");
  await expect(page.getByRole("button", {name: "Reverse", exact: true}))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".pitch-control output")).toHaveText("+3.5 st");
  await expect(page.locator(".pan-control output")).toHaveText("L100");
  await showSamplePage(page, "Playback");
  await expect(page.getByRole("button", {name: "Ping-pong", exact: true}))
    .toHaveAttribute("aria-pressed", "true");
  await showSamplePage(page, "Trim");
  await expect(page.getByRole("spinbutton", {name: "Pad A01 Loop start time (seconds)"}))
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
  await chooseSampleFile(page, "Add Sample to Pad A01", "tone.wav", pcm16Wav({frames: 4800}));
  await commitLongSourceSelection(page);
  await expectProjectRevision(page, 1);
  const base = await inspectedPlayback(page);
  // Release applies once the Pad stops being a one-shot.
  await showSamplePage(page, "Playback");
  await page.getByRole("button", {name: "One Shot", exact: true}).click();
  await expectProjectRevision(page, 2);

  // normal: each control commits one revision.
  await showSamplePage(page, "Playback");
  await slideAndRelease(page.getByRole("slider", {name: "Pad A01 Attack"}), "120");
  await expectProjectRevision(page, 3);
  await showSamplePage(page, "Playback");
  await slideAndRelease(page.getByRole("slider", {name: "Pad A01 Release"}), "900");
  await expectProjectRevision(page, 4);
  await showSamplePage(page, "Tone / EQ");
  await slideAndRelease(page.getByRole("slider", {name: "Pad A01 Tone"}), "-40");
  await expectProjectRevision(page, 5);
  await showSamplePage(page, "Tone / EQ");
  await holdKeySteps(page, page.getByRole("slider", {name: "Pad A01 EQ High"}), "ArrowUp", 2);
  await expectProjectRevision(page, 6);
  // 36 half-dB steps reach the floor; one more makes the low shelf a cut.
  await showSamplePage(page, "Tone / EQ");
  await holdKeySteps(page, page.getByRole("slider", {name: "Pad A01 EQ Low"}), "ArrowDown", 37);
  await expectProjectRevision(page, 7);
  // A real mouse drag up and right turns the mid band on, through the
  // browser's own hit-testing, focus and pointer capture.
  await showSamplePage(page, "Tone / EQ");
  const mid = page.getByRole("slider", {name: "Pad A01 EQ Mid"});
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
  await showSamplePage(page, "Tone / EQ");
  const tone = page.getByRole("slider", {name: "Pad A01 Tone"});
  const toneReadout = page.locator(".tone-control output");
  const cancelOffset = await page.evaluate(() => window.__sampleProofOperations.length);
  const pointerId = ++pointerSequence;
  await tone.dispatchEvent("pointerdown", {pointerId, isPrimary: true, button: 0});
  await tone.fill("60");
  await expect(toneReadout).toHaveText("HP 60");
  await tone.press("Escape");
  await showSamplePage(page, "Tone / EQ");
  await expect(toneReadout).toHaveText("LP 40");
  await tone.dispatchEvent("pointerup", {pointerId, isPrimary: true, button: 0});
  await showSamplePage(page, "Tone / EQ");
  const high = page.getByRole("slider", {name: "Pad A01 EQ High"});
  await high.focus();
  await page.keyboard.down("ArrowUp");
  await expect(high).toHaveAttribute("aria-valuetext", "High shelf 8.00 kHz +1.5 dB");
  await page.keyboard.down("Escape");
  await page.keyboard.up("Escape");
  await page.keyboard.up("ArrowUp");
  await expect(high).toHaveAttribute("aria-valuetext", "High shelf 8.00 kHz +1.0 dB");
  // A pointer press never focuses the pole, so the browser delivers Escape to
  // whatever had focus; the drag still cancels. Nothing in the editor holds
  // focus here, so only the editor's window listener can hear it.
  await page.evaluate(() => document.activeElement?.blur?.());
  expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true);
  const midText = await mid.getAttribute("aria-valuetext");
  const grab = await poleCentre();
  await page.mouse.move(grab.x, grab.y);
  await page.mouse.down();
  await page.mouse.move(grab.x - 20, grab.y + 20, {steps: 4});
  await expect(mid).not.toHaveAttribute("aria-valuetext", midText);
  expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true);
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
  await showSamplePage(page, "Playback");
  await slideAndRelease(page.getByRole("slider", {name: "Pad A01 Attack"}), "500");
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
  await selectPadWithoutPress(page, "Pad A01 — assigned — Key Z");
  await showSamplePage(page, "Playback");
  await expect(attackReadout).toHaveText("120 ms");
  await expect(page.locator(".release-control output")).toHaveText("900 ms");
  await showSamplePage(page, "Tone / EQ");
  await expect(toneReadout).toHaveText("LP 40");
  await showSamplePage(page, "Tone / EQ");
  await expect(page.getByRole("slider", {name: "Pad A01 EQ Low"}))
    .toHaveAttribute("aria-valuetext", "Low cut 100 Hz");
  await showSamplePage(page, "Tone / EQ");
  await expect(page.getByRole("slider", {name: "Pad A01 EQ High"}))
    .toHaveAttribute("aria-valuetext", "High shelf 8.00 kHz +1.0 dB");
  await showSamplePage(page, "Tone / EQ");
  await expect(page.getByRole("slider", {name: "Pad A01 EQ Mid"}))
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
  await createSequencePattern(page);
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
  await expect(sequencePattern(page)).toHaveAttribute("data-pattern-count", "2");
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
  await chooseSampleFile(page, "Add Sample to Pad A01", "inactive-delete.wav", pcm16Wav({frames: 4800}));
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
  await showSamplePage(page, "Pad");
  await expect(page.getByRole("button", {name: "Delete Pad A01", exact: true})).toBeEnabled();
  await showSamplePage(page, "Pad");
  await page.getByRole("button", {name: "Delete Pad A01", exact: true}).click();
  await expectProjectRevision(page, 2);
  await expect(page.getByRole("button", {name: "Pad A01 — empty — Key Z", exact: true})).toBeVisible();
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
  await chooseSampleFile(page, "Add Sample to Pad A01", "delete-source.wav", pcm16Wav({frames: 4800}));
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
  const triggerOffset = await page.evaluate(() => ({
    responses: window.__sampleProofResponses.length, consumed: window.__sampleInputProof.length,
  }));
  await page.keyboard.press("KeyZ");
  // Gate Record-off on the actual complete durable consume of this press,
  // with its matching Native voice. Ordinary Record's Native authority may
  // be live-only; this recording window still requires actual retained=true.
  // Request admission or a live-only completed consume cannot satisfy it.
  await expect.poll(() => page.evaluate((offset) => {
    const presses = window.__sampleInputProof.slice(offset.consumed);
    const legacy = window.__sampleProofResponses.slice(offset.responses)
      .filter(entry => entry.operation === "trigger" && entry.ok === true);
    const sequences = presses.map(entry => entry.sequence).concat(legacy.map(entry => entry.result.sequence));
    return presses.every(entry => entry.status.retained === true) &&
      sequences.length === 1 && sequences.every(sequence =>
      Number.isSafeInteger(sequence) && sequence > 0 && window.__sampleVoiceProof.some(event =>
        event.sequence === sequence && event.slot === 0 && event.state === "started"));
  }, triggerOffset), {timeout: 30_000}).toBe(true);
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
  await showSamplePage(page, "Pad");
  await expect(page.getByRole("button", {name: "Delete Pad A01", exact: true})).toBeEnabled();
  await showSamplePage(page, "Playback");
  await page.getByRole("button", {name: "Loop", exact: true}).click();
  await expectProjectRevision(page, 3);
  const before = (await rawRequest(page, "project.inspect", {})).result.project;
  const oldAsset = before.banks[0].pads[0].asset_id;
  const oldArtifact = before.assets[oldAsset].artifact;
  expect(oldArtifact.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(oldArtifact.byte_length).toBeGreaterThan(44);
  const {redo} = railHistoryKeys(page);

  await showSamplePage(page, "Pad");
  await page.getByRole("button", {name: "Delete Pad A01", exact: true}).click();
  await expectProjectRevision(page, 4);
  await expect(page.getByRole("button", {name: "Pad A01 — empty — Key Z", exact: true})).toBeVisible();
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
  await showSamplePage(page, "Playback");
  await expect(page.getByRole("button", {name: "Loop", exact: true})).toHaveAttribute("aria-pressed", "true");
  await pressRailRedo(page);
  await expectProjectRevision(page, 6);
  expect((await rawRequest(page, "project.inspect", {})).result.project.banks).toEqual(deleted.banks);
  await chooseSampleFile(page, "Add Sample to Pad A01", "new-sound.wav", pcm16Wav({frames: 9600, phase: 7}));
  await commitLongSourceSelection(page);
  await expectProjectRevision(page, 7);
  const reassigned = (await rawRequest(page, "project.inspect", {})).result.project;
  expect(reassigned.patterns).toEqual(before.patterns);
  expect(reassigned.banks[0].pads[0].asset_id).not.toBe(oldAsset);
  expect(reassigned.assets[oldAsset].artifact).toEqual(oldArtifact);
  await showRailHistoryLayer(page);
  await expect(redo).not.toHaveClass(RAIL_LIT);
  await page.reload();
  await waitForProjectReopen(page, reassigned.project_id.slice(0, 8));
  expect((await rawRequest(page, "project.inspect", {})).result.project).toEqual(reassigned);
  const reopened = (await rawRequest(page, "history.inspect", {})).result;
  expect(reopened.undo_count).toBe(0);
  expect(reopened.redo_count).toBe(0);
  noErrors();
});


test("contextual Sample encoders merge one save, cancel old targets and restore monitoring level", async ({page, browserName}) => {
  // Boot/import, two authoring transitions, Undo and persisted reopen each
  // retain their existing bounded transition budgets within this journey.
  test.setTimeout(300_000);
  test.skip(browserName !== "chromium");
  const noErrors = recordPageErrors(page);
  await installHostProofRecorder(page);
  await page.goto("/index.html");
  await waitForBootProject(page);
  // The real Native fixture has ready assigned Pads; default seed slots
  // may be loading/failed and cannot receive a target-change gesture.
  const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
  if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");
  await page.getByRole("button", {name: "Project", exact: true}).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"})).toBeVisible({timeout: 120_000});
  const baseRevision = (await rawRequest(page, "project.inspect", {})).result.project.revision;
  // The report helper opens System, which intentionally cancels an idle
  // turn. Inspect committed Truth directly while waiting for the timer.
  const expectEncoderRevision = async (revision) => {
    await expect.poll(async () => (await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.project_revision,
      {timeout: REPORT_REVISION_TIMEOUT_MS}).toBe(revision);
  };
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await activateAudio(page);
  await chooseSampleFile(page, "Replace Sample", "encoder.wav", pcm16Wav({frames: 4800}));
  await page.getByRole("button", {name: "Confirm replace", exact: true}).click();
  await commitLongSourceSelection(page);
  await expectEncoderRevision(baseRevision + 1);
  const rail = page.getByTestId("physical-controls");
  const knob = (name) => rail.getByRole("button", {name, exact: true});
  await expect(knob("Encoder 3 — Pitch")).toBeEnabled();
  const playbackBeforeTurn = (await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.playback;
  const savesBefore = await page.evaluate(() => (window.__sampleProofOperations ?? []).filter(op => op === "sample.update_pad").length);
  await knob("Encoder 3 — Pitch").focus();
  await page.keyboard.press("Shift+ArrowUp");
  await expect(page.locator('.encoder-readbacks [data-encoder="3"]')).toContainText("0.1 st");
  await expectEncoderRevision(baseRevision + 2);
  const changed = await rawRequest(page, "sample.inspect", {slot: SLOT_A1});
  expect(changed.result.playback.pitch_cents).toBe(10);
  expect(await page.evaluate(() => (window.__sampleProofOperations ?? []).filter(op => op === "sample.update_pad").length)).toBe(savesBefore + 1);
  const history = await rawRequest(page, "history.inspect", {});
  expect(history.result.undo_count).toBe(2);

  // A Sample subpage switch also retires the old rotary preview. Keep the
  // turn and navigation in one task so driver latency cannot commit it first.
  await showSamplePage(page, "Trim");
  await knob("Encoder 3 — Pitch").evaluate((element) => {
    const navigation = document.querySelector('.sample-page-nav');
    const playback = [...(navigation?.querySelectorAll('button') ?? [])]
      .find((candidate) => candidate.textContent === 'Playback');
    if (playback === undefined) throw new Error("Playback page is unavailable");
    element.dispatchEvent(new KeyboardEvent("keydown", {key: "ArrowUp", bubbles: true}));
    playback.dispatchEvent(new MouseEvent("click", {bubbles: true, detail: 1}));
  });
  await expect(page.getByRole("slider", {name: "Pad A01 Volume", exact: true})).toBeVisible();
  await page.waitForTimeout(450);
  expect((await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.playback.pitch_cents).toBe(10);
  await expectEncoderRevision(baseRevision + 2);
  expect(await page.evaluate(() => (window.__sampleProofOperations ?? [])
    .filter(op => op === "sample.update_pad").length)).toBe(savesBefore + 1);

  // Start a second preview and change its Pad before its 400 ms save.
  const nextPadLabel = await page.getByRole("button", {name: /^Pad A02 —/}).getAttribute("aria-label");
  await knob("Encoder 3 — Pitch").focus();
  // Dispatch both inputs in one browser task so driver round trips cannot
  // consume the idle interval before the target actually changes.
  await knob("Encoder 3 — Pitch").evaluate((element, label) => {
    const pad = [...document.querySelectorAll(".pad")].find((candidate) => candidate.getAttribute("aria-label") === label);
    if (pad === undefined) throw new Error("The next Pad is unavailable");
    element.dispatchEvent(new KeyboardEvent("keydown", {key: "ArrowUp", bubbles: true}));
    pad.dispatchEvent(new MouseEvent("click", {bubbles: true, detail: 1}));
  }, nextPadLabel);
  await expect(page.getByRole("button", {name: nextPadLabel, exact: true})).toHaveAttribute("aria-pressed", "true");
  // An observation after the complete idle interval proves the old timer cannot save.
  await expect.poll(async () => {
    const result = await rawRequest(page, "sample.inspect", {slot: SLOT_A1});
    return {revision: result.result.project_revision, pitch: result.result.playback.pitch_cents};
  }).toEqual({revision: baseRevision + 2, pitch: 10});
  await page.waitForTimeout(450);
  expect((await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.playback.pitch_cents).toBe(10);
  await expectEncoderRevision(baseRevision + 2);
  await pressRailUndo(page);
  await expectEncoderRevision(baseRevision + 3);
  expect((await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result.playback).toEqual(playbackBeforeTurn);

  const truth = (await rawRequest(page, "project.inspect", {})).result;
  // Truth acknowledgement precedes the history controller finishing its
  // refresh; wait for its actual input lock before sending keyboard turns.
  await expect(page.locator(".creator-console-frame")).not.toHaveAttribute("inert", "");
  await knob("Encoder 4 — Output Volume").focus();
  for (let i = 0; i < 5; i++) await page.keyboard.press("Shift+ArrowDown");
  await expect(page.locator('.encoder-readbacks [data-encoder="4"]')).toContainText("95%");
  expect((await rawRequest(page, "project.inspect", {})).result).toEqual(truth);
  await openCreatorSystem(page);
  await expect(knob("Encoder 4 — Output Volume")).toBeEnabled();
  await expect(knob("Encoder 1 — unassigned until hardware mapping is approved")).toBeDisabled();
  await page.reload();
  await waitForProjectReopen(page, truth.project.project_id.slice(0, 8));
  await expect(knob("Encoder 4 — Output Volume")).toBeEnabled();
  await expect(page.locator('.encoder-readbacks [data-encoder="4"]')).toContainText("95%");
  expect((await rawRequest(page, "project.inspect", {})).result).toEqual(truth);
  await noErrors();
});

for (const viewport of [{width: 1440, height: 900}, {width: 1024, height: 768},
  {width: 768, height: 600}]) {
  test(`Playback groups real toggle readbacks and keyboard actions at ${viewport.width}x${viewport.height}`, async ({page, browserName}, testInfo) => {
    test.skip(browserName !== "chromium");
    test.setTimeout(180_000);
    const noErrors = recordPageErrors(page);
    await page.setViewportSize(viewport);
    await page.goto("/index.html");
    await openProjectPageAfterBoot(page);
    const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
    if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", {name: "Import .lmdj"}).click();
    await (await chooser).setFiles(bundle);
    await expect(page.getByRole("heading", {name: "Project 00000000"}))
      .toBeVisible({timeout: 120_000});
    let revision = (await rawRequest(page, "project.inspect", {})).result.project.revision;
    await page.getByRole("button", {name: "Sample", exact: true}).click();
    await showSamplePage(page, "Playback");
    const controls = page.getByRole("region", {name: "Pad A01 Sample controls", exact: true});
    const toggles = controls.locator(".sample-toggle-row");
    const button = (name) => toggles.getByRole("button", {name, exact: true});
    await expect(button("One Shot")).toBeEnabled();
    await expect(toggles.getByRole("button")).toHaveText([
      "Loop: Off", "One Shot: On", "Mute: Off", "Reverse: Off",
    ]);
    await toggles.scrollIntoViewIfNeeded();
    const geometry = await toggles.evaluate((element) => {
      const bounds = (item) => {
        const box = item.getBoundingClientRect();
        return {x: box.x, y: box.y, right: box.right, bottom: box.bottom,
          width: box.width, height: box.height};
      };
      const rect = bounds(element);
      const buttons = [...element.querySelectorAll("button")].map((item) => {
        const box = bounds(item);
        const points = [[box.width / 2, 1], [box.width / 2, box.height - 1],
          [1, box.height / 2], [box.width - 1, box.height / 2],
          [box.width / 2, box.height / 2]];
        return {label: item.textContent, ...box,
          horizontalOverflow: item.scrollWidth - item.clientWidth,
          hits: points.map(([x, y]) => document.elementFromPoint(box.x + x, box.y + y)
            ?.closest("button") === item)};
      });
      const overlaps = buttons.flatMap((left, index) => buttons.slice(index + 1)
        .filter((right) => left.x < right.right && left.right > right.x &&
          left.y < right.bottom && left.bottom > right.y));
      return {rect, buttons, overlaps: overlaps.length,
        horizontalOverflow: element.scrollWidth - element.clientWidth,
        insideViewport: rect.x >= 0 && rect.y >= 0 &&
          rect.right <= innerWidth && rect.bottom <= innerHeight};
    });
    expect(geometry.insideViewport).toBe(true);
    expect(geometry.horizontalOverflow).toBe(0);
    expect(geometry.overlaps).toBe(0);
    expect(geometry.buttons).toHaveLength(4);
    const [loop, primary, mute, reverse] = geometry.buttons;
    expect(loop.y).toBeCloseTo(primary.y, 1);
    expect(mute.y).toBeCloseTo(reverse.y, 1);
    expect(mute.y).toBeGreaterThan(loop.bottom);
    expect(loop.x).toBeCloseTo(mute.x, 1);
    expect(primary.x).toBeCloseTo(reverse.x, 1);
    expect(primary.x).toBeGreaterThan(loop.right);
    for (const item of geometry.buttons) {
      expect(item.width).toBeCloseTo(loop.width, 1);
      expect(item.horizontalOverflow, item.label).toBe(0);
      expect(item.width, item.label).toBeGreaterThanOrEqual(44);
      expect(item.height, item.label).toBeGreaterThanOrEqual(44);
      expect(item.hits, item.label).toEqual([true, true, true, true, true]);
    }
    // U01 supplies shared 32-face/44-actual sizing. Check its real Playback
    // consumers, including unpainted target edges after scrolling into view;
    // rectangles alone cannot rule out clipping or another hit owner.
    const geometryPath = testInfo.outputPath("playback-toggles-geometry.json");
    const screenshotPath = testInfo.outputPath("playback-toggles.png");
    await writeFile(geometryPath, JSON.stringify(geometry, null, 2));
    await page.screenshot({path: screenshotPath});
    await testInfo.attach("playback-toggles-geometry", {path: geometryPath, contentType: "application/json"});
    await testInfo.attach("playback-toggles", {path: screenshotPath, contentType: "image/png"});

    await button("Loop").focus();
    for (const name of ["One Shot", "Mute", "Reverse"]) {
      await page.keyboard.press("Tab");
      await expect(button(name)).toBeFocused();
    }
    const commitToggle = async (name, key, expectedPlayback, nextName, text, pressed) => {
      await button(name).focus();
      await expect(button(name)).toBeFocused();
      await page.keyboard.press(key);
      revision += 1;
      await expect.poll(async () => {
        const inspected = (await rawRequest(page, "sample.inspect", {slot: SLOT_A1})).result;
        return {revision: inspected.project_revision, playback: inspected.playback};
      }, {timeout: REPORT_REVISION_TIMEOUT_MS}).toEqual({
        revision, playback: expect.objectContaining(expectedPlayback),
      });
      await expect(button(nextName)).toBeEnabled();
      await expect(button(nextName)).toHaveText(text);
      await expect(button(nextName)).toHaveAttribute("aria-pressed", String(pressed));
    };
    await commitToggle("Reverse", "Space", {reverse: true}, "Reverse", "Reverse: On", true);
    await commitToggle("Loop", "Enter", {trigger_mode: "loop_toggle"}, "Loop", "Loop: On", true);
    await expect(button("Hold")).toHaveText("Hold: On");
    await commitToggle("Hold", "Space", {trigger_mode: "loop_gate"}, "Hold", "Hold: Off", false);
    await commitToggle("Mute", "Enter", {muted: true}, "Mute", "Mute: On", true);
    await commitToggle("Loop", "Space", {trigger_mode: "gate"}, "Loop", "Loop: Off", false);
    await expect(button("One Shot")).toHaveText("One Shot: Off");
    await commitToggle("One Shot", "Enter", {trigger_mode: "one_shot"}, "One Shot", "One Shot: On", true);
    await noErrors();
  });
}

// Trim owns the ordinary action/value targets below. Its existing dragging
// zones are intentionally not claimed as universal 44px targets: the 20px
// per-side zones still clip at the source edge and shared midpoint.
async function recordTrimGeometry(page, editor, state, testInfo) {
  const canvas = editor.locator(".waveform-canvas");
  await canvas.scrollIntoViewIfNeeded();
  const waveform = await canvas.evaluate((element) => ({
    height: element.clientHeight,
    waveformFill: getComputedStyle(element.querySelector("[data-waveform]")).fill,
    grips: [...element.querySelectorAll("[data-grip-zone]")].map((grip) => {
      const rect = grip.getBoundingClientRect();
      return {kind: grip.dataset.gripZone, width: rect.width, height: rect.height};
    }),
  }));
  expect(waveform.height).toBe(80);
  const waveformShot = testInfo.outputPath(`trim-${state}-waveform.png`);
  await page.screenshot({path: waveformShot});
  await testInfo.attach(`trim-${state}-waveform`, {path: waveformShot, contentType: "image/png"});

  const groups = [];
  for (const selector of [".waveform-values", ".waveform-viewport-actions"]) {
    const group = editor.locator(selector);
    await group.scrollIntoViewIfNeeded();
    const geometry = await group.evaluate((element) => {
      const controls = [...element.querySelectorAll("button, input.sample-value-input")];
      const boxes = controls.map((control) => {
        const rect = control.getBoundingClientRect();
        const points = [[rect.width / 2, 1], [rect.width / 2, rect.height - 1],
          [1, rect.height / 2], [rect.width - 1, rect.height / 2],
          [rect.width / 2, rect.height / 2]];
        return {
          label: control.getAttribute("aria-label") ?? control.textContent.trim(),
          x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom,
          width: rect.width, height: rect.height,
          localX: control.offsetLeft, localY: control.offsetTop,
          localRight: control.offsetLeft + control.offsetWidth,
          localBottom: control.offsetTop + control.offsetHeight,
          insideViewport: rect.x >= 0 && rect.y >= 0 &&
            rect.right <= innerWidth && rect.bottom <= innerHeight,
          hits: points.map(([x, y]) => {
            const hit = document.elementFromPoint(rect.x + x, rect.y + y);
            return hit === control || control.contains(hit);
          }),
        };
      });
      return {boxes, horizontalOverflow: element.scrollWidth - element.clientWidth};
    });
    expect(geometry.horizontalOverflow).toBe(0);
    for (const control of geometry.boxes) {
      expect(control.width, `${state}: ${control.label}`).toBeGreaterThanOrEqual(44);
      expect(control.height, `${state}: ${control.label}`).toBeGreaterThanOrEqual(44);
      expect(control.insideViewport, `${state}: ${control.label}`).toBe(true);
      expect(control.hits, `${state}: ${control.label}`).toEqual([true, true, true, true, true]);
    }
    groups.push({selector, ...geometry});
  }
  expect(groups[0].boxes).toHaveLength(state === "looping" ? 4 : 2);
  const actions = groups[1].boxes;
  expect(actions.map(({label}) => label)).toEqual([
    "Zoom Out", "Zoom In", "Fit waveform", "Pan Left", "Pan Right",
  ]);
  // Logical layout coordinates retain their meaning when the whole console
  // rotates; the actual CSS-pixel rectangles/hits above stay screen-relative.
  const [out, inside, fit, left, right] = actions;
  expect(out.localY).toBe(inside.localY);
  expect(inside.localY).toBe(fit.localY);
  expect(inside.localX).toBeGreaterThan(out.localRight);
  expect(fit.localX).toBeGreaterThan(inside.localRight);
  expect(left.localY).toBeGreaterThan(out.localBottom);
  expect(left.localY).toBe(right.localY);
  expect(right.localX).toBeGreaterThan(left.localRight);
  const overall = await editor.evaluate((element) => {
    const boxes = [...element.querySelectorAll("button, input.sample-value-input")]
      .map((control) => control.getBoundingClientRect());
    return {
      overlapCount: boxes.flatMap((a, index) => boxes.slice(index + 1).filter((b) =>
        a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top)).length,
      horizontalOverflow: element.scrollWidth - element.clientWidth,
    };
  });
  expect(overall.overlapCount).toBe(0);
  expect(overall.horizontalOverflow).toBe(0);
  const jsonPath = testInfo.outputPath(`trim-${state}-geometry.json`);
  const actionsShot = testInfo.outputPath(`trim-${state}-actions.png`);
  await writeFile(jsonPath, JSON.stringify({waveform, groups, overall}, null, 2));
  await page.screenshot({path: actionsShot});
  await testInfo.attach(`trim-${state}-geometry`, {path: jsonPath, contentType: "application/json"});
  await testInfo.attach(`trim-${state}-actions`, {path: actionsShot, contentType: "image/png"});
}

for (const viewport of [{width: 1440, height: 900}, {width: 1280, height: 720},
  {width: 1280, height: 600}, {width: 1024, height: 768},
  {width: 768, height: 600}, {width: 768, height: 1024}]) {
  test(`Trim groups preserve real local viewport and editing at ${viewport.width}x${viewport.height}`, async ({page, browserName}, testInfo) => {
    test.skip(browserName !== "chromium");
    test.setTimeout(180_000);
    const noErrors = recordPageErrors(page);
    await installHostProofRecorder(page);
    await page.setViewportSize(viewport);
    await page.goto("/index.html");
    await waitForBootProject(page);
    await activateAudio(page);
    await chooseSampleFile(page, "Add Sample to Pad A01", "trim-layout.wav", pcm16Wav({}));
    await commitLongSourceSelection(page);
    await expectProjectRevision(page, 1);
    await showSamplePage(page, "Trim");
    const editor = page.getByRole("region", {name: "Pad A01 waveform editor", exact: true});
    await expect(editor.getByRole("img", {name: "Pad A01 mirrored waveform"})).toBeVisible();
    const inspectTruth = async () => {
      const response = await rawRequest(page, "project.inspect", {});
      expect(response.ok).toBe(true);
      return response.result;
    };
    const initialTruth = await inspectTruth();
    expect(initialTruth.project.revision).toBe(1);
    await recordTrimGeometry(page, editor, "ordinary", testInfo);
    const button = (name) => editor.getByRole("button", {name, exact: true});
    await button("Zoom Out").focus();
    for (const name of ["Zoom In", "Fit waveform", "Pan Left", "Pan Right"]) {
      await page.keyboard.press("Tab");
      await expect(button(name)).toBeFocused();
    }

    const view = async (name, start, end, keyboard = false) => {
      const offset = await page.evaluate(() => window.__sampleProofResponses.length);
      if (keyboard) {
        await button(name).focus();
        await page.keyboard.press("Enter");
      } else {
        await button(name).click();
      }
      await expect(editor).toHaveAttribute("data-viewport-start", String(start));
      await expect(editor).toHaveAttribute("data-viewport-end", String(end));
      // Wait for the real viewport query to settle before the negative Truth
      // read, so an in-flight request cannot masquerade as local-only success.
      await expect.poll(() => page.evaluate((from) =>
        window.__sampleProofResponses.slice(from).filter((r) =>
          r.operation === "sample.waveform" && r.ok).length, offset),
      {timeout: REPORT_REVISION_TIMEOUT_MS}).toBe(1);
      expect(await inspectTruth()).toEqual(initialTruth);
    };
    const localFrom = await page.evaluate(() => window.__sampleProofOperations.length);
    await view("Zoom In", 24_000, 72_000);
    await recordTrimGeometry(page, editor, "zoomed", testInfo);
    await view("Pan Right", 36_000, 84_000, true);
    await view("Pan Left", 24_000, 72_000);
    await view("Zoom Out", 0, 96_000, true);
    await view("Zoom In", 24_000, 72_000);
    await view("Fit waveform", 0, 96_000, true);
    expect(await page.evaluate((from) => window.__sampleProofOperations.slice(from)
      .filter((operation) => ["sample.update_pad", "sample.preview.set", "trigger"]
        .includes(operation)), localFrom)).toEqual([]);

    await showSamplePage(page, "Playback");
    await page.getByRole("button", {name: "Loop", exact: true}).click();
    await expect.poll(async () => {
      const response = await rawRequest(page, "sample.inspect", {slot: SLOT_A1});
      expect(response.ok).toBe(true);
      return {revision: response.result.project_revision, mode: response.result.playback.trigger_mode};
    }, {timeout: REPORT_REVISION_TIMEOUT_MS}).toEqual({revision: 2, mode: "loop_toggle"});
    await showSamplePage(page, "Trim");
    await expect(editor.getByRole("spinbutton", {name: "Pad A01 Loop start time (seconds)"})).toBeEnabled();
    await recordTrimGeometry(page, editor, "looping", testInfo);
    const loopedPlayback = await inspectedPlayback(page);
    const start = editor.getByRole("spinbutton", {name: "Pad A01 Start time (seconds)"});
    // Real pointer focus plus keyboard editing works in the rotated portrait
    // viewport too; no synthetic grip event or coordinate rewrite is used.
    await start.click();
    await start.fill("0.25");
    await page.keyboard.press("Tab");
    await expect.poll(async () => {
      const response = await rawRequest(page, "sample.inspect", {slot: SLOT_A1});
      expect(response.ok).toBe(true);
      return {revision: response.result.project_revision, playback: response.result.playback};
    }, {timeout: REPORT_REVISION_TIMEOUT_MS}).toEqual({
      revision: 3, playback: {...loopedPlayback, trim_start_frame: 12_000},
    });
    await expect(start).toBeEnabled();
    await expect(start).toHaveValue("0.25");
    const saved = await inspectTruth();
    expect(saved.project.revision).toBe(3);
    expect(await page.evaluate((from) => window.__sampleProofOperations.slice(from)
      .filter((operation) => operation === "trigger"), localFrom)).toEqual([]);
    await page.reload();
    await waitForProjectReopen(page, saved.project.project_id.slice(0, 8));
    expect(await inspectTruth()).toEqual(saved);
    await page.getByRole("button", {name: "Sample", exact: true}).click();
    await showSamplePage(page, "Trim");
    await expect(page.getByRole("spinbutton", {name: "Pad A01 Start time (seconds)"})).toHaveValue("0.25");
    await noErrors();
  });
}

// Import-only observation calls the original AudioContext/AudioBufferSource
// methods. It neither supplies audio nor manufactures Runtime responses. The
// complete original twenty cases and their History helpers above stay intact.
async function observeLongSourcePreview(page) {
  await page.addInitScript(() => {
    const create = AudioContext.prototype.createBufferSource;
    const close = AudioContext.prototype.close;
    const owners = new WeakMap();
    window.__importAudio = [];
    AudioContext.prototype.createBufferSource = function (...args) {
      const node = create.apply(this, args);
      if (!document.querySelector('.long-source-dialog[open]')) return node;
      const record = {starts: [], stops: 0, disconnects: 0, ended: 0, closes: 0};
      window.__importAudio.push(record);
      owners.set(this, record);
      const start = node.start, stop = node.stop, disconnect = node.disconnect;
      node.start = function (...startArgs) {
        const result = start.apply(this, startArgs);
        record.starts.push(startArgs);
        return result;
      };
      node.stop = function (...stopArgs) {
        const result = stop.apply(this, stopArgs);
        record.stops += 1;
        return result;
      };
      node.disconnect = function (...disconnectArgs) {
        const result = disconnect.apply(this, disconnectArgs);
        record.disconnects += 1;
        return result;
      };
      node.addEventListener('ended', () => { record.ended += 1; });
      return node;
    };
    AudioContext.prototype.close = function (...args) {
      const result = close.apply(this, args);
      const record = owners.get(this);
      if (record) record.closes += 1;
      return result;
    };
  });
}

async function recordImportGeometry(page, dialog, state, testInfo) {
  const expectedNames = ["Long source selection start", "Long source selection length",
    "Preview selection", "Stop preview", "Commit selection", "Cancel", "Delete Pad A01"];
  const controls = dialog.locator('input[type="range"], button');
  const evidence = {state, controls: []};
  // Persist inventory before any assertion, including failures, rather than
  // letting a missing or clipped control disappear from the evidence.
  evidence.inventory = await controls.evaluateAll(elements => elements.map(element =>
    element.getAttribute('aria-label') ?? element.textContent.trim()));
  const path = testInfo.outputPath(`import-${state}-geometry.json`);
  await writeFile(path, JSON.stringify(evidence, null, 2));
  expect(evidence.inventory).toEqual(expectedNames);
  for (let index = 0; index < expectedNames.length; index += 1) {
    const control = controls.nth(index);
    await control.scrollIntoViewIfNeeded();
    const sample = await control.evaluate(element => {
      const box = element.getBoundingClientRect();
      const content = element.closest('.long-source-content');
      const panel = element.closest('dialog');
      const region = (content ?? panel).getBoundingClientRect();
      const points = [[box.x + box.width / 2, box.y + box.height / 2],
        [box.left + 2, box.y + box.height / 2], [box.right - 2, box.y + box.height / 2],
        [box.x + box.width / 2, box.top + 2], [box.x + box.width / 2, box.bottom - 2]];
      const range = document.createRange(); range.selectNodeContents(element);
      const text = [...range.getClientRects()].filter(rect => rect.width && rect.height);
      return {name: element.getAttribute('aria-label') ?? element.textContent.trim(),
        box: box.toJSON(), region: region.toJSON(), disabled: element.disabled,
        hits: points.map(([x, y]) => { const hit = document.elementFromPoint(x, y);
          return hit === element || element.contains(hit); }),
        textInside: text.every(rect => rect.left >= box.left - .5 && rect.right <= box.right + .5 &&
          rect.top >= box.top - .5 && rect.bottom <= box.bottom + .5),
        inView: box.left >= region.left - .5 && box.right <= region.right + .5 &&
          box.top >= region.top - .5 && box.bottom <= region.bottom + .5 &&
          box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight};
    });
    evidence.controls.push(sample);
    await writeFile(path, JSON.stringify(evidence, null, 2));
    expect(sample.box.width, sample.name).toBeGreaterThanOrEqual(44);
    expect(sample.box.height, sample.name).toBeGreaterThanOrEqual(44);
    expect(sample.inView, sample.name).toBe(true);
    expect(sample.textInside, sample.name).toBe(true);
    expect(sample.disabled, sample.name).toBe(false);
    expect(sample.hits, sample.name).toEqual([true, true, true, true, true]);
  }
  evidence.layout = await dialog.evaluate(element => {
    const box = element.getBoundingClientRect();
    const content = element.querySelector('.long-source-content');
    const controls = [...element.querySelectorAll('input[type="range"], button')].map(control => control.getBoundingClientRect());
    const overlaps = controls.flatMap((a, i) => controls.slice(i + 1).filter(b =>
      a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top));
    const anchor = document.querySelector('[data-testid="touch-workspace"]');
    const style = getComputedStyle(element);
    const transform = new DOMMatrix(style.transform);
    const labels = [...element.querySelectorAll('.long-source-heading, .long-source-selection > span, .long-source-details p, [role="alert"]')]
      .map(label => ({text: label.textContent, overflow: label.scrollWidth - label.clientWidth}));
    return {dialog: box.toJSON(), anchor: anchor.getBoundingClientRect().toJSON(),
      insideViewport: box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight,
      upright: transform.b === 0 && transform.c === 0, scale: transform.a,
      contentHeight: content.clientHeight, contentScrollHeight: content.scrollHeight,
      contentOverflowX: content.scrollWidth - content.clientWidth,
      pageOverflowX: document.documentElement.scrollWidth - innerWidth,
      overlapCount: overlaps.length, labels};
  });
  await writeFile(path, JSON.stringify(evidence, null, 2));
  expect(evidence.layout.insideViewport).toBe(true);
  expect(evidence.layout.upright).toBe(true);
  expect(evidence.layout.scale).toBeGreaterThanOrEqual(1);
  expect(evidence.layout.contentOverflowX).toBe(0);
  expect(evidence.layout.pageOverflowX).toBe(0);
  expect(evidence.layout.overlapCount).toBe(0);
  expect(evidence.layout.labels.every(label => label.overflow === 0)).toBe(true);
  for (const edge of ['top', 'bottom']) {
    await dialog.locator('.long-source-content').evaluate((element, edge) => {
      element.scrollTop = edge === 'top' ? 0 : element.scrollHeight;
    }, edge);
    const shot = testInfo.outputPath(`import-${state}-${edge}.png`);
    await page.screenshot({path: shot});
    await testInfo.attach(`import-${state}-${edge}`, {path: shot, contentType: 'image/png'});
  }
  await testInfo.attach(`import-${state}-geometry`, {path, contentType: 'application/json'});
}

for (const viewport of [{width: 1440, height: 900}, {width: 1280, height: 720},
  {width: 1280, height: 600}, {width: 1024, height: 768},
  {width: 768, height: 600}, {width: 768, height: 1024}]) {
  test(`Import keeps exact selection and preview ownership at ${viewport.width}x${viewport.height}`, async ({page, browserName}, testInfo) => {
    test.skip(browserName !== 'chromium');
    test.setTimeout(180_000);
    const noErrors = recordPageErrors(page);
    await installHostProofRecorder(page);
    await observeLongSourcePreview(page);
    await page.setViewportSize(viewport);
    await page.goto('/index.html');
    // The official Sample fixture supplies an empty A01 plus real assigned
    // Pads for the stale-quota mutation; default seeding is not a prerequisite.
    await importV1SampleProject(page);
    await activateAudio(page);
    await enterSampleEditor(page);
    const truth = async () => {
      const response = await rawRequest(page, 'project.inspect', {});
      expect(response.ok).toBe(true);
      return response.result;
    };
    const initial = await truth();
    expect(initial.project.banks[0].pads[0].asset_id).toBeNull();
    const operationsFrom = await page.evaluate(() => window.__sampleProofOperations.length);
    const sourceName = 'import-<long-name>-'.repeat(10) + '.wav';
    const wav = pcm16Wav({frames: 480_000});
    const open = async () => {
      await chooseSampleFile(page, 'Add Sample to Pad A01', sourceName, wav);
      await expect(page.getByRole('dialog', {name: 'Pad A01 Long Source', exact: true})).toBeVisible({timeout: 30_000});
    };
    const dialog = page.getByRole('dialog', {name: 'Pad A01 Long Source', exact: true});
    const start = dialog.getByRole('slider', {name: 'Long source selection start', exact: true});
    const length = dialog.getByRole('slider', {name: 'Long source selection length', exact: true});
    const button = name => dialog.getByRole('button', {name, exact: true});
    const audio = () => page.evaluate(() => window.__importAudio);
    const unchanged = async (expected = initial) => { expect(await truth()).toEqual(expected); };
    const preview = async (startFrame, frameCount) => {
      const index = (await audio()).length;
      await button('Preview selection').click();
      await expect.poll(async () => (await audio())[index]?.starts).toEqual([[0, startFrame / 48_000, frameCount / 48_000]]);
      await unchanged();
      return index;
    };
    await open();
    await expect(dialog.getByRole('heading', {name: 'IMPORT AUDIO'})).toBeVisible();
    await expect(dialog.getByText('TARGET A01', {exact: true})).toBeVisible();
    await expect(start).toBeFocused();
    await recordImportGeometry(page, dialog, 'ready', testInfo);
    await start.focus();
    const focusOrder = [length, button('Preview selection'), button('Stop preview'), button('Commit selection'), button('Cancel'), button('Delete Pad A01'), start];
    for (const control of focusOrder) { await page.keyboard.press('Tab'); await expect(control).toBeFocused(); }
    await page.keyboard.press('Shift+Tab'); await expect(button('Delete Pad A01')).toBeFocused();
    await start.focus();
    const padBox = await page.locator('.pad-grid button').first().boundingBox();
    expect(padBox).not.toBeNull();
    await page.mouse.click(padBox.x + padBox.width / 2, padBox.y + padBox.height / 2);
    await expect(dialog).toBeVisible();
    await start.focus(); await page.keyboard.press('z');
    await unchanged();
    expect(await page.evaluate(from => window.__sampleProofOperations.slice(from).filter(op => op === 'trigger'), operationsFrom)).toEqual([]);

    const first = await preview(0, 480_000);
    await length.focus(); await page.keyboard.press('PageDown');
    const selectedFrames = Number(await length.inputValue());
    expect(selectedFrames).toBeGreaterThan(1); expect(selectedFrames).toBeLessThan(480_000);
    await unchanged();
    await start.focus(); await page.keyboard.press('End');
    const selectedStart = Number(await start.inputValue());
    expect(selectedStart).toBeGreaterThan(0); expect(selectedStart + selectedFrames).toBe(480_000);
    await unchanged();
    // Independent Figma colour oracle: unresolved custom properties can leave
    // all geometry and selection-state assertions green while painting black.
    const colours = await dialog.evaluate(element => ({
      selected: [...element.querySelectorAll('.long-source-waveform rect[data-selected="true"]')]
        .map(bin => getComputedStyle(bin).fill),
      unselected: [...element.querySelectorAll('.long-source-waveform rect[data-selected="false"]')]
        .map(bin => getComputedStyle(bin).fill),
      lengthTrack: getComputedStyle(element.querySelector('input[aria-label="Long source selection length"]')).backgroundImage,
    }));
    const colourPath = testInfo.outputPath('import-selection-colours.json');
    await writeFile(colourPath, JSON.stringify(colours, null, 2));
    await testInfo.attach('import-selection-colours', {path: colourPath, contentType: 'application/json'});
    expect(colours.selected.length).toBeGreaterThan(0);
    expect(colours.unselected.length).toBeGreaterThan(0);
    expect([...new Set(colours.selected)]).toEqual(['rgb(149, 212, 223)']);
    expect([...new Set(colours.unselected)]).toEqual(['rgb(124, 135, 123)']);
    expect(colours.lengthTrack.match(/rgba?\([^)]+\)/g)?.[0]).toBe('rgb(149, 212, 223)');
    const second = await preview(selectedStart, selectedFrames);
    expect((await audio())[first]).toMatchObject({stops: 1, disconnects: 1, closes: 1});
    await button('Stop preview').click();
    await expect.poll(async () => (await audio())[second]).toMatchObject({stops: 1, disconnects: 1, closes: 1});
    await unchanged();
    await button('Stop preview').click();
    await unchanged();
    expect((await audio())[second]).toMatchObject({stops: 1, disconnects: 1, closes: 1});
    await length.focus(); await page.keyboard.press('Home'); await page.keyboard.press('PageUp');
    const shortFrames = Number(await length.inputValue());
    expect(shortFrames).toBeGreaterThan(1); expect(shortFrames).toBeLessThanOrEqual(48_001);
    await unchanged();
    const third = await preview(selectedStart, shortFrames);
    await expect.poll(async () => (await audio())[third]).toMatchObject({ended: 1, closes: 1, stops: 0});
    await unchanged();
    await length.focus(); await page.keyboard.press('End');
    await unchanged();
    const fourth = await preview(selectedStart, Number(await length.inputValue()));
    await button('Cancel').click();
    await expect(dialog).toHaveCount(0);
    await expect.poll(async () => (await audio())[fourth]).toMatchObject({stops: 1, disconnects: 1, closes: 1});
    await unchanged();
    await expect(page.getByRole('button', {name: 'Add Sample to Pad A01', exact: true})).toBeFocused();

    await open();
    const escapePreview = await preview(0, 480_000);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect.poll(async () => (await audio())[escapePreview]).toMatchObject({stops: 1, disconnects: 1, closes: 1});
    await unchanged();
    await expect(page.getByRole('button', {name: 'Add Sample to Pad A01', exact: true})).toBeFocused();

    // Induce a real stale quota using another assigned Pad's public mutation,
    // not a substituted failed response. D03's controller/writer is untouched.
    await open();
    await length.focus(); await page.keyboard.press('Home'); await page.keyboard.press('PageUp');
    const commitFrames = Number(await length.inputValue());
    await start.focus(); await page.keyboard.press('End');
    const commitStart = Number(await start.inputValue());
    expect(commitStart).toBeGreaterThan(0); expect(commitStart + commitFrames).toBe(480_000);
    const assigned = initial.project.banks.flatMap((bank, bankIndex) => bank.pads.map((pad, padIndex) =>
      ({pad, slot: {bank: bankIndex, pad: padIndex}}))).find(entry => entry.pad.asset_id !== null);
    expect(assigned).toBeDefined();
    const other = await rawRequest(page, 'sample.inspect', {slot: assigned.slot});
    expect(other.ok).toBe(true);
    const changed = await rawRequest(page, 'sample.update_pad', {
      command_id: crypto.randomUUID(), expected_revision: initial.project.revision,
      slot: assigned.slot, playback: {...other.result.playback, gain_millidb: other.result.playback.gain_millidb === 0 ? -1 : 0},
    });
    expect(changed.ok).toBe(true);
    const changedTruth = await truth();
    expect(changedTruth.project.revision).toBe(initial.project.revision + 1);
    await button('Commit selection').click();
    await expect(dialog.getByRole('alert')).toBeVisible({timeout: 120_000});
    await expect(start).toHaveValue(String(commitStart)); await expect(length).toHaveValue(String(commitFrames));
    await expect(button('Commit selection')).toBeEnabled();
    expect(await truth()).toEqual(changedTruth);
    await recordImportGeometry(page, dialog, 'refused', testInfo);
    await button('Cancel').click(); await expect(dialog).toHaveCount(0);
    expect(await truth()).toEqual(changedTruth);

    await open();
    await length.focus(); await page.keyboard.press('Home'); await page.keyboard.press('PageUp');
    await expect(length).toHaveValue(String(commitFrames));
    await start.focus(); await page.keyboard.press('End'); await expect(start).toHaveValue(String(commitStart));
    await button('Commit selection').click();
    await expect(dialog).toHaveCount(0, {timeout: 120_000});
    await expect.poll(async () => (await truth()).project.revision, {timeout: REPORT_REVISION_TIMEOUT_MS}).toBe(changedTruth.project.revision + 1);
    const saved = await truth();
    const assetId = saved.project.banks[0].pads[0].asset_id;
    expect(assetId).not.toBeNull();
    const artifact = saved.project.assets[assetId].artifact;
    expect(artifact.sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(artifact.byte_length).toBe(44 + commitFrames * 2);
    const inspected = await page.evaluate(() => window.lmdjWebRuntimeHost.inspection.inspectSample(0));
    expect(inspected).toMatchObject({assetId, projectRevision: saved.project.revision,
      metadata: {sourceFrames: commitFrames, sampleRate: 48_000, channels: 1}});
    expect(await page.evaluate(from => window.__sampleProofOperations.slice(from).filter(op => op === 'trigger'), operationsFrom)).toEqual([]);
    await page.reload();
    await waitForProjectReopen(page, saved.project.project_id.slice(0, 8));
    expect(await truth()).toEqual(saved);
    await page.getByRole('button', {name: 'Sample', exact: true}).click();
    await showSamplePage(page, 'Trim');
    await expect(page.getByRole('img', {name: 'Pad A01 mirrored waveform'})).toBeVisible({timeout: 120_000});
    const reopened = await page.evaluate(() => window.lmdjWebRuntimeHost.inspection.inspectSample(0));
    expect(reopened).toEqual(inspected);
    expect((await truth()).project.assets[assetId].artifact).toEqual(artifact);
    await noErrors();
  });
}
