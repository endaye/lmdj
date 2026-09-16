import {expect, test} from "@playwright/test";

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

test("opts into the 880×592 hardware shell, keeps overview read-only, and returns", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  await expect(page.getByRole("button", {name: "Activate audio"})).toBeVisible();

  await page.getByRole("button", {name: "Hardware layout"}).click();
  const consoleBox = rounded(await page.getByTestId("hardware-console").boundingBox());
  const physical = rounded(await page.getByTestId("physical-controls").boundingBox());
  const overview = rounded(await page.getByTestId("overview-display").boundingBox());
  const pads = rounded(await page.getByTestId("pad-matrix").boundingBox());
  const touch = rounded(await page.getByTestId("touch-workspace").boundingBox());

  expect(consoleBox).toMatchObject({width: 880, height: 592});
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
  await expect(keys.getByRole("button", {name: "Project", exact: true})).toBeVisible();
  await expect(keys.getByRole("button", {name: "Sample", exact: true})).toBeVisible();
  await expect(keys.getByRole("button", {name: "Sequence — open a playable Project first"}))
    .toBeVisible();
  await expect(keys.getByRole("button", {name: /^Perform/})).toBeVisible();
  // V1 replaced the transport glyphs with the Desktop Final icon exports, so
  // these keys carry no text at all now; the accessible name is what V1
  // promised to keep, and the icon is what it promised to change.
  const record = keys.getByRole("button", {name: "Record", exact: true});
  await expect(record).toHaveClass(/\bhas-icon\b/);
  await expect(record.locator("img")).toHaveCount(1);
  await expect(record).toHaveText("");
  const playStop = keys.getByRole("button", {
    name: "Play/Stop — needs a playable Project and running audio",
    exact: true,
  });
  await expect(playStop).toHaveClass(/\bhas-icon\b/);
  await expect(playStop.locator("img")).toHaveCount(1);
  await expect(playStop).toHaveText("");
  const shot = process.env.LMDJ_HARDWARE_CONSOLE_SHOT;
  if (shot) {
    await page.getByTestId("hardware-console").screenshot({path: shot});
  }

  await expect(page.getByTestId("overview-display").locator("button")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Existing workspace"})).toBeVisible();
  await expect(page.getByRole("button", {name: "Activate audio"})).toBeVisible();

  await page.setViewportSize({width: 768, height: 600});
  await page.getByRole("button", {name: "Existing workspace"}).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", {name: "Existing workspace"})).toBeVisible();
  await expect(page.getByTestId("overview-display").locator("button")).toHaveCount(0);

  await page.getByRole("button", {name: "Existing workspace"}).click();
  await expect(page.getByTestId("hardware-console")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Hardware layout"})).toBeVisible();
  await expect(page.getByTestId("creator-phase")).toHaveText("empty");
});

const PROJECT_TRANSITION_TIMEOUT_MS = 125_000;
const AUDIO_TRANSITION_TIMEOUT_MS = 35_000;

const projectHeading = (page) =>
  page.getByRole("heading", {name: "Project 00000000"});

async function importAndOpenProject(page) {
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
  if (await projectHeading(page).isVisible()) return;
  const open = page.getByRole("button", {name: "Open Project 00000000"});
  if (!await open.isVisible()) {
    await page.getByRole("button", {name: "Open local"})
      .click({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    // That read was a point in time. Wait for the row by name, so a list that
    // never renders it fails as a missing Project row rather than as a click
    // timing out somewhere inside the reload leg.
    await expect(open).toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  }
  await open.click({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(projectHeading(page))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

// Both layouts publish the committed tempo, in their own element. This reads
// whichever one is mounted so a single drill can compare across the boundary.
async function committedBpm(page) {
  const overview = page.locator(".overview-bpm");
  const text = await overview.count() > 0
    ? await overview.innerText()
    : await page.locator(".status-facts div").filter({hasText: "BPM"})
      .getByRole("definition").first().innerText();
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

test("carries Project Truth and running audio across a layout fallback drill", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });

  await importAndOpenProject(page);
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  const committed = await committedBpm(page);
  expect(committed).toBeGreaterThan(0);

  // Leg 1 — opt in. The Runtime and Project Truth cross the boundary.
  await page.getByRole("button", {name: "Hardware layout"}).click();
  await expect(page.getByTestId("hardware-console")).toBeVisible();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
  expect(await committedBpm(page)).toBe(committed);

  // Leg 2 — an unapplied Tempo draft. Moving the fader is not a commit, so
  // the published tempo must not move with it. Whether the draft itself
  // survives a layout switch is D03 and is deliberately not asserted here.
  await page.getByRole("button", {name: "Sequence"}).click();
  const bpmFader = page.getByRole("slider", {name: "BPM"});
  await expect(bpmFader).toBeVisible();
  await bpmFader.fill(String(committed + 12));
  await expect(page.getByRole("button", {name: "Apply BPM"})).toBeVisible();
  expect(await committedBpm(page)).toBe(committed);

  // Leg 3 — fall back with that draft outstanding. The old shell must come
  // back with the same Project Truth and the same Runtime, and the abandoned
  // draft must not have been committed on the way out.
  await page.getByRole("button", {name: "Existing workspace"}).click();
  await expect(page.getByTestId("hardware-console")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Hardware layout"})).toBeVisible();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
  expect(await committedBpm(page)).toBe(committed);

  // Leg 4 — return. Same Project, same Runtime, still nothing committed.
  await page.getByRole("button", {name: "Hardware layout"}).click();
  await expect(page.getByTestId("hardware-console")).toBeVisible();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
  expect(await committedBpm(page)).toBe(committed);

  // Leg 5 — same-origin reload. The layout preference is Host settings, so it
  // survives; audio does not, because resuming it needs a fresh gesture, and
  // the Project the reload reopens still carries the uncommitted tempo.
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
  expect(await committedBpm(page)).toBe(committed);
});
