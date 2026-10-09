import {showSequenceLayer} from "./fixtures/creator_navigation.mjs";
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

// Desktop Final T2: the console scales to fit the stage, so its layout is
// asserted in console units -- every page box mapped back through the scale
// the console was drawn at -- and its fit in page pixels against the stage.
async function consoleGeometry(page) {
  const raw = await page.getByTestId("hardware-console").boundingBox();
  const scale = raw.width / 880;
  const box = async (locator) => {
    const b = await locator.boundingBox();
    return rounded({x: (b.x - raw.x) / scale, y: (b.y - raw.y) / scale,
      width: b.width / scale, height: b.height / scale});
  };
  return {raw, scale, box};
}

async function expectConsoleFitsStage(page) {
  const stage = await page.locator("#root").boundingBox();
  const {raw, scale} = await consoleGeometry(page);
  // Proportional: the 880:592 ratio survives the scale.
  expect(Math.abs(raw.height - 592 * scale)).toBeLessThanOrEqual(1);
  // Inside the stage on both axes, and centred in it.
  expect(raw.x).toBeGreaterThanOrEqual(stage.x - 1);
  expect(raw.y).toBeGreaterThanOrEqual(stage.y - 1);
  expect(raw.x + raw.width).toBeLessThanOrEqual(stage.x + stage.width + 1);
  expect(raw.y + raw.height).toBeLessThanOrEqual(stage.y + stage.height + 1);
  expect(Math.abs((stage.x + stage.width / 2) - (raw.x + raw.width / 2))).toBeLessThanOrEqual(2);
  expect(Math.abs((stage.y + stage.height / 2) - (raw.y + raw.height / 2))).toBeLessThanOrEqual(2);
  // Filled: one axis meets the stage (the console's 24px margins included).
  const fills = Math.min(
    Math.abs(stage.width - 880 * scale),
    Math.abs(stage.height - 640 * scale),
  );
  expect(fills).toBeLessThanOrEqual(2);
  return scale;
}

test("renders the 880×592 hardware shell and keeps the overview read-only", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  await waitForBootProject(page);
  await expect(page.getByRole("button", {name: "Activate audio"})).toHaveCount(0);

  const {box} = await consoleGeometry(page);
  const consoleBox = await box(page.getByTestId("hardware-console"));
  const physical = await box(page.getByTestId("physical-controls"));
  const overview = await box(page.getByTestId("overview-display"));
  const pads = await box(page.getByTestId("pad-matrix"));
  const touch = await box(page.getByTestId("touch-workspace"));

  expect(consoleBox).toMatchObject({x: 0, y: 0, width: 880, height: 592});
  // The device fills the stage proportionally and floats in its middle.
  expect(await expectConsoleFitsStage(page)).toBeGreaterThan(1);
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

  const pad = await box(page.getByRole("button", {name: /Pad A01 /}));
  expect(pad).toMatchObject({width: 80, height: 80});
  const encoders = await box(page.getByTestId("physical-encoders"));
  expect(encoders).toMatchObject({
    x: physical.x,
    y: physical.y + 80 + 16,
    width: 80,
    height: 80,
  });
  const encoder = await box(page.getByRole("button", {
    name: "Encoder 1 — unassigned until hardware mapping is approved",
  }));
  expect(encoder).toMatchObject({width: 32, height: 32});
  const keyBlock = await box(page.getByTestId("physical-keys"));
  expect(keyBlock).toMatchObject({
    x: physical.x,
    y: pads.y,
    width: 80,
    height: 368,
  });
  const keys = page.getByTestId("physical-controls");
  for (const bank of ["Bank A", "Bank B", "Bank C", "Bank D"]) {
    const bankBox = await box(keys.getByRole("button", {name: bank, exact: true}));
    expect(bankBox).toMatchObject({width: 32, height: 32});
  }
  // #1770: the −/+ placeholder row is gone and SHIFT holds its row as one
  // full-width key (both 32px cells plus the 16px gap) directly above the
  // record/play row, keeping the 8-row 368px key block. Rows step 48px
  // (32px key + 16px gap), so SHIFT's row starts 6 steps into the block.
  const shift = await box(keys.getByRole("button", {name: /^SHIFT/}));
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

  // A short window shrinks the console instead of scrolling it; a wide one
  // is limited by its height. Both keep the ratio and stay centred.
  for (const viewport of [{width: 768, height: 600}, {width: 1280, height: 720}]) {
    await page.setViewportSize(viewport);
    await expect.poll(async () => (await consoleGeometry(page)).scale).toBeLessThan(1.2);
    await expectConsoleFitsStage(page);
    // A tap on a known Pad still lands on that Pad under the scale.
    const padA06 = page.getByRole("button", {name: /^Pad A06 /});
    const target = await padA06.boundingBox();
    const hit = await page.evaluate(({x, y}) =>
      document.elementFromPoint(x, y)?.closest("button")?.getAttribute("aria-label") ?? null,
    {x: target.x + target.width / 2, y: target.y + target.height / 2});
    expect(hit).toMatch(/^Pad A06 /);
  }
  await expect(page.getByTestId("creator-phase")).toHaveText("ready");
});

const PROJECT_TRANSITION_TIMEOUT_MS = 125_000;
const AUDIO_TRANSITION_TIMEOUT_MS = 35_000;

test("all Banks put 01 at bottom left and preserve visual traversal and hit targets", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  await waitForBootProject(page);
  const matrix = page.getByLabel("Playable Pads", {exact: true});
  for (const bank of ["A", "B", "C", "D"]) {
    await page.getByTestId("physical-controls").getByRole("button", {
      name: `Bank ${bank}`, exact: true,
    }).click();
    await expect(matrix.locator("strong")).toHaveText([
      "13", "14", "15", "16", "09", "10", "11", "12",
      "05", "06", "07", "08", "01", "02", "03", "04",
    ].map(pad => `${bank}${pad}`));
    const topLeft = await matrix.getByRole("button", {name: new RegExp(`^Pad ${bank}13 `)}).boundingBox();
    const topRight = await matrix.getByRole("button", {name: new RegExp(`^Pad ${bank}16 `)}).boundingBox();
    const bottomLeft = await matrix.getByRole("button", {name: new RegExp(`^Pad ${bank}01 `)}).boundingBox();
    const bottomRight = await matrix.getByRole("button", {name: new RegExp(`^Pad ${bank}04 `)}).boundingBox();
    expect(bottomLeft.x).toBeCloseTo(topLeft.x, 0);
    expect(bottomRight.x).toBeCloseTo(topRight.x, 0);
    expect(bottomLeft.y).toBeGreaterThan(topLeft.y);
    expect(topRight.x).toBeGreaterThan(topLeft.x);
    expect(bottomRight.y).toBeCloseTo(bottomLeft.y, 0);
    for (const [number, box] of [["01", bottomLeft], ["04", bottomRight], ["13", topLeft], ["16", topRight]]) {
      const hit = await page.evaluate(({x, y}) =>
        document.elementFromPoint(x, y)?.closest("button")?.getAttribute("aria-label"),
      {x: box.x + box.width / 2, y: box.y + box.height / 2});
      expect(hit).toMatch(new RegExp(`^Pad ${bank}${number} `));
    }
  }
  const first = matrix.getByRole("button", {name: /^Pad D13 /});
  await first.focus();
  await page.keyboard.press("Tab");
  await expect(matrix.getByRole("button", {name: /^Pad D14 /})).toBeFocused();
  await expect(matrix.getByRole("button", {name: /^Pad D01 /}).locator("kbd")).toHaveText("Q");
});

const projectHeading = (page) =>
  page.getByRole("heading", {name: "Project 00000000"});

async function importAndOpenProject(page) {
  await page.getByRole("button", {name: "Project", exact: true}).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(bundle);
  // D01: a card selects the Project and OPEN PROJECT opens the selection.
  const select = page.getByRole("button", {name: "Select Project 00000000"});
  await expect.poll(async () =>
    await projectHeading(page).isVisible() ? "ready"
      : await select.isVisible() ? "open" : "",
  {timeout: PROJECT_TRANSITION_TIMEOUT_MS}).not.toBe("");
  if (!await projectHeading(page).isVisible()) {
    await select.click();
    await page.getByRole("button", {name: "Open Project 00000000"}).click();
  }
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
  await showSequenceLayer(page, "SETUP");
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

// Desktop Final plan T1b: the console face ships inside the stylesheet as a
// data: URL, so it needs the distribution CSP's `font-src data:` and no
// network. A blocked or missing face reports "error" or nothing here.
test("the console renders in the bundled IBM Plex Mono that the CSP admits", async ({page}) => {
  const violations = [];
  page.on("console", (message) => {
    if (/Content Security Policy|font-src/i.test(message.text())) violations.push(message.text());
  });
  await page.goto("/");
  await waitForBootProject(page);
  const loaded = await page.evaluate(async () =>
    (await document.fonts.load('12px "IBM Plex Mono"')).map((face) => face.status));
  expect(loaded).toEqual(["loaded"]);
  const family = await page.getByTestId("hardware-console")
    .evaluate((element) => getComputedStyle(element).fontFamily);
  expect(family).toMatch(/^"IBM Plex Mono"/);
  expect(violations).toEqual([]);
});
