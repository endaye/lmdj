import {expect, test} from "./fixtures/refusal_diagnostics.mjs";
import {openProjectPageAfterBoot, waitForProjectReopen} from "./fixtures/creator_boot.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {showSamplePage} from "./fixtures/creator_navigation.mjs";

const SLOT_A01 = {bank: 0, pad: 0};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
// The existing Sample cases give one SDK request its 30-second bound plus
// five seconds of render settling. This case retains that same action budget.
const SAMPLE_TRANSITION_MS = 30_000 + 5_000;

async function recordNativeSend(page) {
  await page.addInitScript(() => {
    let exposed;
    window.__sampleNumericNativeReceipts = [];
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get: () => exposed,
      set(host) {
        const nativeTransport = host.transport;
        // Wrap only the original nativeHost.transport.send method. Forward
        // its exact arguments with the original receiver, return the original
        // response, and rethrow the same error. No request or response is
        // manufactured, changed, retried or sent outside the owning SDK lane.
        const recordedSend = async (...args) => {
          const receipt = {request: args[0], response: null, error: null};
          window.__sampleNumericNativeReceipts.push(receipt);
          try {
            const response = await Reflect.apply(nativeTransport.send, nativeTransport, args);
            receipt.response = response;
            return response;
          } catch (error) {
            receipt.error = {name: error?.name, code: error?.code, message: error?.message};
            throw error;
          }
        };
        const boundMethods = new Map();
        host.transport = new Proxy({}, {
          get(_target, key) {
            if (key === "send") return recordedSend;
            const value = Reflect.get(nativeTransport, key, nativeTransport);
            if (typeof value !== "function") return value;
            if (!boundMethods.has(key)) boundMethods.set(key, value.bind(nativeTransport));
            return boundMethods.get(key);
          },
        });
        exposed = host;
      },
    });
  });
}

const offset = (page) => page.evaluate(() => window.__sampleNumericNativeReceipts.length);
const receipts = (page, from, operation) => page.evaluate(({from, operation}) =>
  window.__sampleNumericNativeReceipts.slice(from)
    .filter(({request}) => request.operation === operation), {from, operation});

async function oneNativeResponse(page, from, operation) {
  await expect.poll(async () => (await receipts(page, from, operation))
    .filter(({response, error}) => response !== null || error !== null).length,
  {timeout: SAMPLE_TRANSITION_MS}).toBe(1);
  const observed = await receipts(page, from, operation);
  expect(observed).toHaveLength(1);
  const [receipt] = observed;
  expect(receipt.error, JSON.stringify(receipt)).toBeNull();
  expect(receipt.response, JSON.stringify(receipt)).toMatchObject({
    request_id: receipt.request.request_id, ok: true,
  });
  return receipt;
}

// PR #1991 publishes these existing session methods in the Host's inspection
// namespace. Calls retain its ordinary owner/control queue; never issue a raw
// transport query in parallel with the Creator's pending operations.
const projectTruth = (page) => page.evaluate(async () =>
  (await window.lmdjWebRuntimeHost.inspection.inspectProject()).project);
const sampleTruth = (page) => page.evaluate(() =>
  window.lmdjWebRuntimeHost.inspection.inspectSample(0));

async function historyAtRevision(page, revision) {
  // Observe the far-side response of the Creator's own history refresh. This
  // observer issues no extra history request and cannot bypass its queue.
  const read = () => page.evaluate((revision) =>
    window.__sampleNumericNativeReceipts.filter(({request, response}) =>
      request.operation === "history.inspect" && response?.ok === true &&
      response.result.project_revision === revision).at(-1)?.response.result ?? null, revision);
  await expect.poll(read, {timeout: SAMPLE_TRANSITION_MS}).not.toBeNull();
  return read();
}

async function expectSaved(page, project, playback) {
  await expect.poll(() => projectTruth(page), {timeout: SAMPLE_TRANSITION_MS}).toEqual(project);
  const sample = await sampleTruth(page);
  expect(sample).toMatchObject({slot: 0, projectRevision: project.revision,
    assetId: project.banks[0].pads[0].asset_id});
  expect(sample.playback).toEqual(playback);
}

async function previewValue(page, input, value, playback) {
  const from = await offset(page);
  await input.fill(value);
  const receipt = await oneNativeResponse(page, from, "sample.preview.set");
  expect(receipt.request.payload).toEqual({slot: SLOT_A01,
    playback: {...playback, gain_millidb: Math.round(Number(value) * 1_000)}});
  expect(receipt.response.result).toEqual({accepted: true});
}

async function restoreOnce(page, direction, sessionId, revision) {
  const rail = page.getByTestId("physical-controls");
  await expect(page.locator(".creator-console-frame")).not.toHaveAttribute("inert", "");
  await rail.getByRole("button", {name: /^SHIFT/}).click();
  const key = rail.getByRole("button", {name: direction === "undo"
    ? "Undo — SHIFT + ←" : "Redo — SHIFT + →", exact: true});
  await expect(key).toHaveClass(/\bis-lit\b/);
  const from = await offset(page);
  await key.click();
  const receipt = await oneNativeResponse(page, from, `history.${direction}`);
  expect(receipt.request.payload).toEqual({session_id: sessionId,
    command_id: expect.stringMatching(UUID), expected_revision: revision});
  expect(receipt.response.result).toMatchObject({committed_revision: revision + 1,
    runtime_published: true});
  return receipt.request.payload.command_id;
}

test("precise Sample values preview, commit one native command, cancel, Undo/Redo and reopen", async ({page}, testInfo) => {
  // Import, numeric save, Undo, Redo and reopen retain the existing 300-second
  // Sample history/encoder case budget. Volume represents this shared path;
  // component tests independently cover all six parameter units and bounds.
  test.setTimeout(300_000);
  const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
  expect(bundle, "the runner's real Native fixture is required").toBeTruthy();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error.message)));
  await recordNativeSend(page);
  await page.goto("/index.html");
  await openProjectPageAfterBoot(page);
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj", exact: true}).click();
  await (await chooser).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000", exact: true}))
    .toBeVisible({timeout: 120_000});
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await wakeAudioWithPad(page, {padAddress: "A01"});
  await showSamplePage(page, "Playback");

  const editValue = page.getByRole("button", {name: "Edit Pad A01 Volume", exact: true});
  await expect(editValue).toBeEnabled({timeout: SAMPLE_TRANSITION_MS});
  const before = await projectTruth(page);
  const beforeSample = await sampleTruth(page);
  // Project inspection projects the authoring state; Sample inspection owns
  // the full saved playback. Native requests retain all five base fields.
  const nativePlayback = {
    trim_start_frame: beforeSample.playback.trimStartFrame,
    trim_end_frame: beforeSample.playback.trimEndFrame,
    trigger_mode: beforeSample.playback.triggerMode,
    gain_millidb: beforeSample.playback.gainMillidb,
    muted: beforeSample.playback.muted,
  };
  const historyBefore = await historyAtRevision(page, before.revision);
  expect(beforeSample.assetId).toBe(before.banks[0].pads[0].asset_id);
  expect(beforeSample.assetId).toMatch(UUID);
  expect(historyBefore.session_id).toMatch(UUID);
  expect(historyBefore.redo_count).toBe(0);
  expect(beforeSample.playback.gainMillidb).not.toBe(-3_200);
  const editingFrom = await offset(page);

  await editValue.click();
  const dialog = page.getByRole("dialog", {name: "Edit Pad A01 Volume", exact: true});
  const input = dialog.getByRole("spinbutton", {name: "Pad A01 Volume value", exact: true});
  await expect(input).toBeFocused();
  await expect(input).toHaveValue(String(beforeSample.playback.gainMillidb / 1_000));
  await input.press("a"); // A Pad-mapped key remains owned by the numeric input.
  await previewValue(page, input, "-2.1", nativePlayback);
  // Crossing the encoder's existing 400 ms interval proves typing cannot
  // silently become rotary auto-save. This is an observation, not a retry.
  await page.waitForTimeout(450);
  await expectSaved(page, before, beforeSample.playback);
  expect(await historyAtRevision(page, before.revision)).toEqual(historyBefore);
  expect(await receipts(page, editingFrom, "sample.update_pad")).toEqual([]);
  expect(await receipts(page, editingFrom, "trigger")).toEqual([]);

  const invalidFrom = await offset(page);
  await input.fill("-3.25");
  await expect(input).toHaveAttribute("aria-invalid", "true");
  await expect(dialog.getByRole("button", {name: "Apply Volume", exact: true})).toBeDisabled();
  const invalidClear = await oneNativeResponse(page, invalidFrom, "sample.preview.clear");
  expect(invalidClear.request.payload).toEqual({slot: SLOT_A01});
  expect(invalidClear.response.result).toEqual({accepted: true});
  expect(await receipts(page, invalidFrom, "sample.preview.set")).toEqual([]);
  await expectSaved(page, before, beforeSample.playback);
  await previewValue(page, input, "-3.2", nativePlayback);
  await expectSaved(page, before, beforeSample.playback);
  expect(await receipts(page, editingFrom, "sample.update_pad")).toEqual([]);

  await dialog.getByRole("button", {name: "Apply Volume", exact: true}).click();
  const saved = await oneNativeResponse(page, editingFrom, "sample.update_pad");
  expect(saved.request.payload).toEqual({command_id: expect.stringMatching(UUID),
    expected_revision: before.revision, slot: SLOT_A01,
    playback: {...nativePlayback, gain_millidb: -3_200}});
  expect(saved.response.result).toMatchObject({committed_revision: before.revision + 1,
    runtime_revision: before.revision + 1, runtime_published: true});
  const changed = structuredClone(before);
  changed.revision += 1;
  const changedPlayback = {...beforeSample.playback, gainMillidb: -3_200};
  await expectSaved(page, changed, changedPlayback);
  await expect(dialog).toHaveCount(0);
  await expect(editValue).toHaveText("-3.2 dB");
  await expect(editValue).toBeEnabled({timeout: SAMPLE_TRANSITION_MS});
  const savedHistory = await historyAtRevision(page, changed.revision);
  expect(savedHistory).toMatchObject({session_id: historyBefore.session_id,
    undo_count: historyBefore.undo_count + 1, redo_count: 0});

  const cancelFrom = await offset(page);
  await editValue.click();
  await previewValue(page, input, "-4.8", nativePlayback);
  await input.press("Escape");
  const cancelled = await oneNativeResponse(page, cancelFrom, "sample.preview.clear");
  expect(cancelled.request.payload).toEqual({slot: SLOT_A01});
  expect(cancelled.response.result).toEqual({accepted: true});
  await expect(dialog).toHaveCount(0);
  await expect(editValue).toBeFocused();
  await expectSaved(page, changed, changedPlayback);
  expect(await historyAtRevision(page, changed.revision)).toEqual(savedHistory);
  expect(await receipts(page, cancelFrom, "sample.update_pad")).toEqual([]);

  const undoCommand = await restoreOnce(page, "undo", historyBefore.session_id, changed.revision);
  const undone = {...before, revision: before.revision + 2};
  await expectSaved(page, undone, beforeSample.playback);
  await expect(editValue).toHaveText(`${(beforeSample.playback.gainMillidb / 1_000).toFixed(1)} dB`);
  expect(await historyAtRevision(page, undone.revision)).toMatchObject({
    session_id: historyBefore.session_id, undo_count: historyBefore.undo_count, redo_count: 1});

  const redoCommand = await restoreOnce(page, "redo", historyBefore.session_id, undone.revision);
  const redone = {...changed, revision: before.revision + 3};
  await expectSaved(page, redone, changedPlayback);
  await expect(editValue).toHaveText("-3.2 dB");
  expect(await historyAtRevision(page, redone.revision)).toMatchObject({
    session_id: historyBefore.session_id, undo_count: historyBefore.undo_count + 1, redo_count: 0});
  expect(new Set([saved.request.payload.command_id, undoCommand, redoCommand]).size).toBe(3);
  expect(await receipts(page, editingFrom, "sample.update_pad")).toHaveLength(1);
  const failed = await page.evaluate((from) => window.__sampleNumericNativeReceipts.slice(from)
    .filter(({response, error}) => error !== null || response?.ok === false), editingFrom);
  expect(failed, JSON.stringify(failed)).toEqual([]);
  const nativeCommands = await page.evaluate(() => window.__sampleNumericNativeReceipts
    .filter(({request}) => /^(sample\.preview\.|sample\.update_pad$|history\.)/.test(request.operation)));
  await testInfo.attach("sample-numeric-native-commands.json", {
    body: JSON.stringify(nativeCommands, null, 2), contentType: "application/json",
  });

  await page.reload();
  await waitForProjectReopen(page, redone.project_id.slice(0, 8));
  await expectSaved(page, redone, changedPlayback);
  const reopenedHistory = await historyAtRevision(page, redone.revision);
  expect(reopenedHistory.session_id).not.toBe(historyBefore.session_id);
  expect(reopenedHistory).toMatchObject({undo_count: 0, redo_count: 0});
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await showSamplePage(page, "Playback");
  await expect(editValue).toHaveText("-3.2 dB");
  expect(pageErrors, "the real packaged Runtime must not trap").toEqual([]);
});
