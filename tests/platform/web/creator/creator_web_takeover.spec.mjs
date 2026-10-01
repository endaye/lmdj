import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {clickCreatorSystemAction} from "./fixtures/creator_navigation.mjs";
import {readFile} from "node:fs/promises";

import {expect, test} from "./fixtures/refusal_diagnostics.mjs";
import {
  PROJECT_OPEN_TIMEOUT_MS,
  overviewProjectId,
  waitForBootProject,
  waitForProjectReopen,
} from "./fixtures/creator_boot.mjs";

// #1679: a second tab takes over a Project the first tab holds, and the first
// takes it back. Both pages share one browser context, so they share OPFS and
// the writer lease exactly as two real tabs do.

// The exported report is produced from published Project truth, which settles
// after the control that caused the mutation is re-enabled, so the report is
// reachable only within one more bounded Runtime request plus the download.
const REPORT_REVISION_TIMEOUT_MS = 30_000 + 5_000;
// Every audio lifecycle gesture owns one independently bounded 30-second
// Runtime request.
const AUDIO_TRANSITION_TIMEOUT_MS = 30_000 + 5_000;
// The holder answers within its 2-second bound and then releases through its
// shutdown barriers and one bounded 30-second host.close; the requester's open
// then runs the three bounded Project-open operations.
const TAKEOVER_TIMEOUT_MS = 2_000 + 30_000 + PROJECT_OPEN_TIMEOUT_MS;
const BUSY = "The local Project is busy in another tab or process.";
const TAKEN_OVER = "Project open in another tab";

function pcm16Wav(frames) {
  const bytes = Buffer.alloc(44 + frames * 2);
  bytes.write("RIFF", 0, "ascii");
  bytes.writeUInt32LE(36 + frames * 2, 4);
  bytes.write("WAVE", 8, "ascii");
  bytes.write("fmt ", 12, "ascii");
  bytes.writeUInt32LE(16, 16);
  bytes.writeUInt16LE(1, 20);
  bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(48_000, 24);
  bytes.writeUInt32LE(96_000, 28);
  bytes.writeUInt16LE(2, 32);
  bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36, "ascii");
  bytes.writeUInt32LE(frames * 2, 40);
  for (let frame = 0; frame < frames; frame += 1) {
    bytes.writeInt16LE(Math.round(((frame % 24) / 23 * 2 - 1) * 24_000), 44 + frame * 2);
  }
  return bytes;
}

function recordPageErrors(page) {
  const errors = [];
  page.on("pageerror", (error) => { errors.push(String(error?.message ?? error)); });
  return () => expect(errors, "the Wasm runtime must not trap").toEqual([]);
}

async function rawRequest(page, operation, payload = {}) {
  const response = await page.evaluate(async ({requested, body}) =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: requested,
      payload: body,
    }), {requested: operation, body: payload});
  expect(response.ok, `${operation} must succeed`).toBe(true);
  return response.result;
}

const projectTruth = async (page) => (await rawRequest(page, "project.inspect")).project;
const undoDepth = async (page) => (await rawRequest(page, "history.inspect")).undo_count;

async function downloadReport(page) {
  const downloadPromise = page.waitForEvent("download");
  await clickCreatorSystemAction(page, "Export report");
  return JSON.parse(await readFile(await (await downloadPromise).path(), "utf8"));
}

async function expectProjectRevision(page, expectedRevision) {
  await expect.poll(
    async () => (await downloadReport(page)).sample.project_revision,
    {timeout: REPORT_REVISION_TIMEOUT_MS},
  ).toBe(expectedRevision);
}

async function expectHolding(page, shortId) {
  await expect(page.getByTestId("creator-phase")).not.toHaveText("closed");
  await expect(overviewProjectId(page)).toHaveText(shortId);
  await expect(page.getByText(TAKEN_OVER)).toHaveCount(0);
}

async function expectTakenOver(page) {
  await expect(page.getByRole("alert").filter({hasText: TAKEN_OVER}))
    .toBeVisible({timeout: TAKEOVER_TIMEOUT_MS});
  await expect(page.getByTestId("creator-phase")).toHaveText("closed");
}

test("a second tab takes over the open Project and the first takes it back", async ({page, context, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(600_000);
  const holderErrors = recordPageErrors(page);

  // Leg 1: the first tab holds a Project and commits a write.
  await page.goto("/index.html");
  await waitForBootProject(page);
  const shortId = (await overviewProjectId(page).textContent()).trim();
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Add Sample to Pad A1"}).click();
  await (await chooser).setFiles({name: "takeover.wav", mimeType: "audio/wav", buffer: pcm16Wav(4_800)});
  const longSource = page.getByRole("dialog", {name: /Pad A1 Long Source/});
  await expect(longSource).toBeVisible({timeout: 30_000});
  await longSource.getByRole("button", {name: "Commit selection"}).click();
  await expectProjectRevision(page, 1);
  const holderWrite = await projectTruth(page);
  expect(holderWrite.banks[0].pads[0].asset_id).not.toBeNull();

  // Leg 2: a second tab's boot reopen of the same Project is refused busy and
  // offers Continue here.
  const second = await context.newPage();
  const secondErrors = recordPageErrors(second);
  await second.goto("/index.html");
  const busy = second.getByRole("alert").filter({hasText: BUSY});
  await expect(busy).toBeVisible({timeout: PROJECT_OPEN_TIMEOUT_MS});
  const continueSecond = busy.getByRole("button", {name: "Continue here"});

  // Leg 3 (refused): the holder is playing audio, so it refuses and keeps the
  // Project, its revision and its Runtime.
  await continueSecond.click();
  await expect(busy).toContainText("The other tab is playing, recording or saving.", {
    timeout: 10_000,
  });
  await expectHolding(page, shortId);
  await expectProjectRevision(page, 1);
  expect(await projectTruth(page)).toEqual(holderWrite);

  // Leg 4 (normal): once the holder is suspended it hands over. The holder's
  // Runtime closes; the second tab opens the holder's committed write with an
  // empty history.
  await clickCreatorSystemAction(page, "Suspend audio");
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await continueSecond.click();
  await expectTakenOver(page);
  await expect(second.getByTestId("creator-phase")).toHaveText("ready", {timeout: TAKEOVER_TIMEOUT_MS});
  await expect(overviewProjectId(second)).toHaveText(shortId);
  await expect(second.getByRole("alert")).toHaveCount(0);
  expect(await projectTruth(second)).toEqual(holderWrite);
  expect(await undoDepth(second)).toBe(0);

  // Leg 5: the new holder commits its own write while audio remains inactive.
  await second.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(second.getByRole("button", {name: "Delete Pad A1", exact: true}))
    .toBeEnabled({timeout: 30_000});
  await second.getByRole("button", {name: "Delete Pad A1", exact: true}).click();
  await expectProjectRevision(second, 2);
  const secondWrite = await projectTruth(second);
  expect(secondWrite.banks[0].pads[0].asset_id).toBeNull();
  expect(secondWrite.assets).toEqual(holderWrite.assets);

  // Keep main's inactive-audio Delete leg, then make the original suspended
  // handoff precondition real with a trusted activation gesture. This is an
  // empty Project, so the helper uses the explicit MIDI permission click.
  await wakeAudioWithPad(second);
  expect(await projectTruth(second)).toEqual(secondWrite);

  // Leg 6 (taken back): once the new holder is suspended, the first tab's
  // Continue here takes the Project back. It reopens the second tab's write
  // exactly once, with an empty history.
  await clickCreatorSystemAction(second, "Suspend audio");
  await expect(second.getByTestId("audio-state")).toHaveText("Audio suspended", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await page.getByRole("alert").filter({hasText: TAKEN_OVER})
    .getByRole("button", {name: "Continue here"}).click();
  await expectTakenOver(second);
  await expect(page.getByTestId("creator-phase")).toHaveText("ready", {timeout: TAKEOVER_TIMEOUT_MS});
  await expectHolding(page, shortId);
  await expectProjectRevision(page, 2);
  expect(await projectTruth(page)).toEqual(secondWrite);
  expect(await undoDepth(page)).toBe(0);

  // Leg 7 (reopened): the persisted Truth survives a reload of the holder.
  await page.reload();
  await waitForProjectReopen(page, shortId);
  expect(await projectTruth(page)).toEqual(secondWrite);
  holderErrors();
  secondErrors();
});
