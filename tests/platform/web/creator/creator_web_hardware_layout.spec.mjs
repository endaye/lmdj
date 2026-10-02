import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {expect, test} from "@playwright/test";
import {waitForBootProject, waitForProjectReopen} from "./fixtures/creator_boot.mjs";

const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

function rounded(box) {
  return {
    x: Math.round(box.x),
    y: Math.round(box.y),
    width: Math.round(box.width),
    height: Math.round(box.height),
  };
}

test("renders the 880×592 hardware shell and keeps the overview read-only", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  await waitForBootProject(page);
  await expect(page.getByRole("button", {name: "Activate audio"})).toHaveCount(0);

  const consoleBox = rounded(await page.getByTestId("hardware-console").boundingBox());
  const physical = rounded(await page.getByTestId("physical-controls").boundingBox());
  const overview = rounded(await page.getByTestId("overview-display").boundingBox());
  const pads = rounded(await page.getByTestId("pad-matrix").boundingBox());
  const touch = rounded(await page.getByTestId("touch-workspace").boundingBox());

  expect(consoleBox).toMatchObject({width: 880, height: 592});
  // The device floats in the middle of the stage on both axes. Old shell
  // code only centred it horizontally (fixed 24px top margin), so the
  // vertical leg is the one that proves the fix.
  const stage = rounded(await page.locator(".hardware-workspace").boundingBox());
  const centreDelta = (outer, inner) =>
    Math.abs((outer.x + outer.width / 2) - (inner.x + inner.width / 2)) +
    Math.abs((outer.y + outer.height / 2) - (inner.y + inner.height / 2));
  expect(centreDelta(stage, consoleBox)).toBeLessThanOrEqual(2);
  expect(physical).toMatchObject({
    x: consoleBox.x + 16,
    y: consoleBox.y + 16,
    width: 80,
    height: 560,
  });
  expect(overview).toMatchObject({
    x: consoleBox.x + 112,
    y: consoleBox.y + 16,
    width: 752,
    height: 176,
  });
  expect(pads).toMatchObject({
    x: consoleBox.x + 112,
    y: consoleBox.y + 208,
    width: 368,
    height: 368,
  });
  expect(touch).toMatchObject({
    x: consoleBox.x + 496,
    y: consoleBox.y + 208,
    width: 368,
    height: 368,
  });

  const pad = rounded(await page.getByRole("button", {name: /Pad A1 /}).boundingBox());
  expect(pad).toMatchObject({width: 80, height: 80});
  const encoders = rounded(await page.getByTestId("physical-encoders").boundingBox());
  expect(encoders).toMatchObject({
    x: physical.x,
    y: physical.y + 80 + 16,
    width: 80,
    height: 80,
  });
  const encoder = rounded(await page.getByRole("button", {
    name: "Encoder 1 — unassigned until hardware mapping is approved",
  }).boundingBox());
  expect(encoder).toMatchObject({width: 32, height: 32});
  const keyBlock = rounded(await page.getByTestId("physical-keys").boundingBox());
  expect(keyBlock).toMatchObject({
    x: physical.x,
    y: pads.y,
    width: 80,
    height: 368,
  });
  const keys = page.getByTestId("physical-controls");
  for (const bank of ["Bank A", "Bank B", "Bank C", "Bank D"]) {
    const box = rounded(await keys.getByRole("button", {name: bank, exact: true}).boundingBox());
    expect(box).toMatchObject({width: 32, height: 32});
  }
  // #1770: the −/+ placeholder row is gone and SHIFT holds its row as one
  // full-width key (both 32px cells plus the 16px gap) directly above the
  // record/play row, keeping the 8-row 368px key block. Rows step 48px
  // (32px key + 16px gap), so SHIFT's row starts 6 steps into the block.
  const shift = rounded(await keys.getByRole("button", {name: /^SHIFT/}).boundingBox());
  expect(shift).toMatchObject({
    x: physical.x,
    y: keyBlock.y + 6 * 48,
    width: 80,
    height: 32,
  });
  // Undo/Redo is the SHIFT + ← / → chord on the direction row; the lamp, not
  // a greyed button pair, reports availability, and nothing sits outside the
  // console frame.
  const undoKey = keys.getByRole("button", {name: "Undo — SHIFT + ←", exact: true});
  await expect(undoKey).toBeDisabled();
  await expect(undoKey).not.toHaveClass(/\bis-lit\b/);
  await expect(keys.getByRole("button", {name: "Redo — SHIFT + →", exact: true}))
    .toBeDisabled();
  await expect(page.getByTestId("authoring-history")).toHaveCount(0);
  await expect(keys.getByRole("button", {name: "Project", exact: true})).toBeVisible();
  await expect(keys.getByRole("button", {name: "Sample", exact: true})).toBeVisible();
  // Boot opens a playable Project (#1660), so Sequence is reachable at once.
  await expect(keys.getByRole("button", {name: "Sequence", exact: true}))
    .toBeEnabled();
  await expect(keys.getByRole("button", {name: /^Perform/})).toBeVisible();
  // V1 replaced the transport glyphs with the Desktop Final icon exports, so
  // these keys carry no text at all now; the accessible name is what V1
  // promised to keep, and the icon is what it promised to change.
  const record = keys.getByRole("button", {name: "Record", exact: true});
  await expect(record).toHaveClass(/\bhas-icon\b/);
  await expect(record.locator("svg")).toHaveCount(1);
  await expect(record).toHaveText("");
  const playStop = keys.getByRole("button", {
    name: "Play/Stop",
    exact: true,
  });
  await expect(playStop).toHaveClass(/\bhas-icon\b/);
  await expect(playStop.locator("svg")).toHaveCount(1);
  await expect(playStop).toHaveText("");
  const shot = process.env.LMDJ_HARDWARE_CONSOLE_SHOT;
  if (shot) {
    await page.getByTestId("hardware-console").screenshot({path: shot});
  }

  await expect(page.getByTestId("overview-display").locator("button")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Existing workspace"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Activate audio"})).toHaveCount(0);

  await page.setViewportSize({width: 768, height: 600});
  // Short stage: the auto margins collapse, so the console's top edge sits
  // at or below the scrollport origin -- a justify-content-centred stage
  // would clip it above the reachable area instead.
  const shortStage = rounded(await page.locator(".hardware-workspace").boundingBox());
  const shortConsole = rounded(await page.getByTestId("hardware-console").boundingBox());
  expect(shortConsole.y).toBeGreaterThanOrEqual(shortStage.y);
  await page.getByTestId("touch-workspace").scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", {name: "Activate audio"})).toHaveCount(0);
  await expect(page.getByTestId("overview-display").locator("button")).toHaveCount(0);
  await expect(page.getByTestId("creator-phase")).toHaveText("ready");
});

const PROJECT_TRANSITION_TIMEOUT_MS = 125_000;
const AUDIO_TRANSITION_TIMEOUT_MS = 35_000;

const projectHeading = (page) =>
  page.getByRole("heading", {name: "Project 00000000"});

async function importAndOpenProject(page) {
  await page.getByRole("button", {name: "Project", exact: true}).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(bundle);
  const open = page.getByRole("button", {name: "Open Project 00000000"});
  await expect.poll(async () =>
    await projectHeading(page).isVisible() ? "ready"
      : await open.isVisible() ? "open" : "",
  {timeout: PROJECT_TRANSITION_TIMEOUT_MS}).not.toBe("");
  if (!await projectHeading(page).isVisible()) await open.click();
  await expect(projectHeading(page))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

// After a reload the Bundle is already in OPFS, so this reopens it from the
// local list. Importing it a second time would be a DUPLICATE_ID, which is a
// different journey than the one this drill is asserting.
async function reopenLocalProject(page) {
  // The imported Project is the remembered one, so the reload reopens it by
  // itself; the Project page then names it.
  await waitForProjectReopen(page, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await page.getByRole("button", {name: "Project", exact: true}).click();
  await expect(projectHeading(page))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

// The upper screen publishes the committed tempo.
async function committedBpm(page) {
  const text = await page.locator(".overview-bpm").innerText();
  const bpm = Number.parseFloat(text.replace(/[^0-9]/g, ""));
  // An unreadable tempo has to fail right here. `toBe` compares with
  // Object.is, under which two NaNs agree, so a drill that never managed to
  // read the published tempo would otherwise report every leg as unchanged.
  expect(
    Number.isFinite(bpm),
    `published tempo must be readable, got ${JSON.stringify(text)}`,
  ).toBe(true);
  return bpm;
}

// Project Truth answers with the same authority the Host writes through.
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

test("commits Tempo only on release and keeps Project Truth across a reload", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  await waitForBootProject(page);

  await importAndOpenProject(page);
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  const committed = await committedBpm(page);
  expect(committed).toBeGreaterThan(0);
  const baseline = await inspectTruth(page);
  expect(baseline.bpm).toBe(committed);

  // Leg 1 — a draft without release is not a commit. Moving the fader only
  // previews locally: the published tempo and Project Truth stay put, and no
  // Apply button exists to turn the draft into a commit.
  await page.getByRole("button", {name: "Sequence"}).click();
  const bpmFader = page.getByRole("slider", {name: "BPM"});
  await expect(bpmFader).toBeVisible();
  await bpmFader.fill(String(committed + 12));
  await expect(page.getByRole("button", {name: /Apply/})).toHaveCount(0);
  expect(await committedBpm(page)).toBe(committed);
  expect((await inspectTruth(page)).bpm).toBe(committed);

  // Leg 2 — Escape cancels the draft: the control falls back to the
  // committed value and Truth never moved, not even by a revision.
  await bpmFader.press("Escape");
  await expect(bpmFader).toHaveValue(String(committed));
  const cancelled = await inspectTruth(page);
  expect(cancelled.bpm).toBe(committed);
  expect(cancelled.revision).toBe(baseline.revision);

  // Leg 3 — release commits exactly once: the published tempo and Truth move
  // to the dragged value with one revision.
  await bpmFader.fill(String(committed + 12));
  await bpmFader.dispatchEvent("pointerup");
  await expect.poll(() => committedBpm(page)).toBe(committed + 12);
  const released = await inspectTruth(page);
  expect(released.bpm).toBe(committed + 12);
  expect(released.revision).toBe(baseline.revision + 1);

  // Leg 4 — same-origin reload. Audio does not survive, because resuming it
  // needs a fresh gesture; the Project the reload reopens must carry the
  // committed tempo.
  await page.reload();
  await expect(page.getByTestId("hardware-console")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("audio-state")).not.toHaveText("Audio running");
  await reopenLocalProject(page);
  // Audio being stopped is not the same fact as the Runtime being healthy. A
  // reload that left it failed, closed or still booting would keep answering
  // with a stale tempo, so the phase is asserted rather than inferred.
  await expect(page.getByTestId("creator-phase"))
    .toHaveText("ready", {timeout: 30_000});
  expect(await committedBpm(page)).toBe(committed + 12);
  expect((await inspectTruth(page)).bpm).toBe(committed + 12);
});
