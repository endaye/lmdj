import {writeFile} from "node:fs/promises";
import {showSamplePage, showSequenceLayer} from "./fixtures/creator_navigation.mjs";
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

// Full and compact shells both scale to fit without shrinking below 1 in the
// supported viewports. Assert each layout's own dimensions, not a weakened
// version of the full 880×592 oracle. Portrait rotation is covered separately.
async function consoleGeometry(page) {
  const raw = await page.getByTestId("hardware-console").boundingBox();
  const compact = await page.locator("html").getAttribute("data-creator-layout") === "compact";
  const width = compact ? Math.min(880, page.viewportSize().width - 16) : 880;
  const scale = raw.width / width;
  const box = async (locator) => {
    const b = await locator.boundingBox();
    return rounded({x: (b.x - raw.x) / scale, y: (b.y - raw.y) / scale,
      width: b.width / scale, height: b.height / scale});
  };
  return {raw, scale, box, compact, width};
}

// Playwright's setViewportSize resolves once Chromium accepts the new
// metrics. It does not wait for the page's resulting `resize` event, and the
// console refits only in that handler (main.tsx fitStage). Reading geometry
// straight after it raced the refit on the CI hosts (#2268). The failures read
// the previous viewport's fit, or a stage and a console measured on opposite
// sides of the refit. Wait for the new inner size, then for one rendering
// frame: HTML's resize steps run before animation-frame callbacks in the same
// update, so the measurement sees the refitted console.
async function resizeViewport(page, viewport) {
  await page.setViewportSize(viewport);
  await page.waitForFunction(({width, height}) =>
    window.innerWidth === width && window.innerHeight === height, viewport);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => resolve())));
}

async function expectConsoleFitsStage(page) {
  const stage = await page.locator("#root").boundingBox();
  const {raw, scale, compact, width} = await consoleGeometry(page);
  const height = compact ? 544 : 592;
  expect(Math.abs(raw.height - height * scale)).toBeLessThanOrEqual(1);
  expect(scale).toBeGreaterThanOrEqual(1);
  // Inside the stage on both axes, and centred in it.
  expect(raw.x).toBeGreaterThanOrEqual(stage.x - 1);
  expect(raw.y).toBeGreaterThanOrEqual(stage.y - 1);
  expect(raw.x + raw.width).toBeLessThanOrEqual(stage.x + stage.width + 1);
  expect(raw.y + raw.height).toBeLessThanOrEqual(stage.y + stage.height + 1);
  expect(Math.abs((stage.x + stage.width / 2) - (raw.x + raw.width / 2))).toBeLessThanOrEqual(2);
  expect(Math.abs((stage.y + stage.height / 2) - (raw.y + raw.height / 2))).toBeLessThanOrEqual(2);
  if (compact) {
    // Compact reserves actual margins and never grows to consume them.
    expect(scale).toBe(1);
    expect(raw.x - stage.x).toBeGreaterThanOrEqual(8);
    expect(stage.x + stage.width - raw.x - raw.width).toBeGreaterThanOrEqual(8);
    expect(raw.y - stage.y).toBeGreaterThanOrEqual(4);
    expect(stage.y + stage.height - raw.y - raw.height).toBeGreaterThanOrEqual(4);
  } else {
    // Full retains its original fill-to-stage oracle, including 24px margins.
    const fills = Math.min(
      Math.abs(stage.width - width * scale),
      Math.abs(stage.height - 640 * scale),
    );
    expect(fills).toBeLessThanOrEqual(2);
  }
  return scale;
}

// Short landscape must reflow before stage fitting. Measure rendered targets
// and their real pointer owners: equal CSS widths can hide a shared transform.
async function expectShortLandscape(page, info, observations, label) {
  const value = await page.getByTestId("hardware-console").evaluate(root => {
    const rect = node => node.getBoundingClientRect().toJSON();
    const transform = new DOMMatrixReadOnly(getComputedStyle(root.closest(".hardware-workspace")).transform);
    const targets = [...root.querySelectorAll(
      '[data-testid="physical-controls"] button,[data-testid="pad-matrix"] button',
    )].map(node => {
      const b = node.getBoundingClientRect();
      const cx = b.x + b.width / 2, cy = b.y + b.height / 2;
      const points = [[cx, cy], [b.x + 2, cy], [b.right - 2, cy], [cx, b.y + 2], [cx, b.bottom - 2]];
      const face = node.matches(".physical-key") ? getComputedStyle(node, "::before") : null;
      return {name: node.getAttribute("aria-label"), disabled: node.disabled, rect: rect(node),
        face: face === null ? null : {width: face.width, height: face.height},
        encoderFace: node.matches(".physical-encoder") ? rect(node.querySelector("svg")) : null,
        hits: points.map(([x, y]) => {
          const top = document.elementFromPoint(x, y);
          return top === node || node.contains(top);
        })};
    });
    const padLabels = [...root.querySelectorAll(".pad")].map(pad => {
      const range = document.createRange();
      range.selectNodeContents(pad.querySelector("span"));
      const dot = pad.querySelector(".pad-selected-dot");
      const heading = [...pad.querySelectorAll("strong,kbd")].flatMap(node => {
        const text = document.createRange();
        text.selectNodeContents(node);
        return [...text.getClientRects()].map(b => b.toJSON());
      });
      return {name: pad.getAttribute("aria-label"), rect: rect(pad),
        heading, text: [...range.getClientRects()].map(b => b.toJSON()), dot: dot === null ? null : rect(dot)};
    });
    const touch = root.querySelector('[data-testid="touch-workspace"]');
    return {viewport: {width: innerWidth, height: innerHeight},
      scale: Math.hypot(transform.a, transform.b), console: rect(root),
      stage: rect(document.querySelector("#root")), regions: [...root.children].map(rect),
      targets, padLabels, keyOrder: [...root.querySelectorAll(".physical-key")].map(node => node.textContent),
      padOrder: [...root.querySelectorAll(".pad strong")].map(node => node.textContent),
      touch: {width: touch.clientWidth, scrollWidth: touch.scrollWidth},
      document: {width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth}};
  });
  observations.push({label, ...value});
  await writeFile(info.outputPath("short-landscape-observations.json"), JSON.stringify({observations}, null, 2));
  expect(value.scale, `${label}: stage must preserve actual input size`).toBe(1);
  expect(value.console.width).toBe(Math.min(880, value.viewport.width - 16));
  expect(value.console.height).toBe(value.viewport.height - 32);
  expect(value.console.x).toBeGreaterThanOrEqual(value.stage.x);
  expect(value.console.right).toBeLessThanOrEqual(value.stage.right);
  expect(value.console.y).toBeGreaterThanOrEqual(value.stage.y);
  expect(value.console.bottom).toBeLessThanOrEqual(value.stage.bottom);
  expect(value.touch.scrollWidth).toBeLessThanOrEqual(value.touch.width);
  expect(value.document.scrollWidth).toBeLessThanOrEqual(value.document.width);
  expect(value.regions).toHaveLength(4);
  for (let i = 0; i < value.regions.length; i++) for (let j = i + 1; j < value.regions.length; j++) {
    const a = value.regions[i], b = value.regions[j];
    expect(a.right <= b.x || b.right <= a.x || a.bottom <= b.y || b.bottom <= a.y,
      `${label}: regions ${i}/${j} overlap`).toBe(true);
  }
  expect(value.targets).toHaveLength(36);
  for (const target of value.targets) {
    expect(target.rect.width, `${label}: ${target.name} width`).toBeGreaterThanOrEqual(44);
    expect(target.rect.height, `${label}: ${target.name} height`).toBeGreaterThanOrEqual(44);
    if (!target.disabled) expect(target.hits, `${label}: ${target.name} centre/edge owner`)
      .toEqual([true, true, true, true, true]);
    if (target.face !== null) expect(target.face).toEqual({
      width: target.name.startsWith("SHIFT") ? "80px" : "32px", height: "32px",
    });
    if (target.encoderFace !== null) expect(target.encoderFace).toMatchObject({width: 32, height: 32});
  }
  expect(value.keyOrder).toEqual(["PRJ", "SMP", "SEQ", "PRF", "A", "B", "C", "D",
    "SHIFT", "↑", "↓", "←", "→", "REC", "PLAY"]);
  const keyTargets = value.targets.filter(target => target.face !== null);
  for (const target of keyTargets.slice(0, 8)) expect(target.rect.y).toBe(keyTargets[0].rect.y);
  for (const target of keyTargets.slice(8)) expect(target.rect.y).toBe(keyTargets[0].rect.y + 44);
  expect(keyTargets[8].rect.width).toBe(92);
  expect(value.padLabels).toHaveLength(16);
  for (const pad of value.padLabels) for (const text of pad.text) {
    expect(text.x, pad.name).toBeGreaterThanOrEqual(pad.rect.x);
    expect(text.right, pad.name).toBeLessThanOrEqual(pad.rect.right);
    expect(text.y, pad.name).toBeGreaterThanOrEqual(pad.rect.y);
    expect(text.bottom, pad.name).toBeLessThanOrEqual(pad.rect.bottom);
    if (pad.dot !== null) expect(text.right <= pad.dot.x || pad.dot.right <= text.x ||
      text.bottom <= pad.dot.y || pad.dot.bottom <= text.y, `${pad.name}: label overlaps selection dot`).toBe(true);
    for (const heading of pad.heading) expect(text.right <= heading.x || heading.right <= text.x ||
      text.bottom <= heading.y || heading.bottom <= text.y, `${pad.name}: status overlaps address or key`).toBe(true);
  }
  await expectOverviewFits(page.getByTestId("overview-display"), label);
  return value;
}

for (const viewport of [{width: 648, height: 364}, {width: 667, height: 375}, {width: 844, height: 390}]) {
  test(`short landscape preserves actual controls and navigation at ${viewport.width}x${viewport.height}`, async ({page}, info) => {
    test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS);
    const observations = [];
    await page.setViewportSize(viewport);
    await page.goto("/");
    await waitForBootProject(page);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
    const keys = page.getByTestId("physical-controls");
    await expectShortLandscape(page, info, observations, "fresh short boot");
    await importAndOpenProject(page);
    const before = await inspectTruth(page);
    for (const mode of ["Project", "Sample", "Sequence", "Perform"]) {
      await keys.getByRole("button", {name: mode, exact: true}).click();
      await expect(page.locator(".overview-display")).toHaveAttribute("data-mode", mode.toLowerCase());
      await expect(keys.getByRole("button", {name: mode, exact: true})).toBeFocused();
      await expectShortLandscape(page, info, observations, mode);
      expect(await inspectTruth(page)).toEqual(before);
    }
    await keys.getByRole("button", {name: "Bank B", exact: true}).click();
    const bankB = await expectShortLandscape(page, info, observations, "Bank B");
    expect(bankB.padOrder).toEqual([13, 14, 15, 16, 9, 10, 11, 12, 5, 6, 7, 8, 1, 2, 3, 4]
      .map(number => `B${String(number).padStart(2, "0")}`));
    await keys.getByRole("button", {name: "Bank A", exact: true}).click();
    await keys.getByRole("button", {name: "System", exact: true}).click();
    await expect(page.locator(".overview-display")).toHaveAttribute("data-mode", "system");
    await expectShortLandscape(page, info, observations, "System");
    await page.getByRole("button", {name: "Back to music", exact: true}).click();
    await expect(page.locator(".overview-display")).toHaveAttribute("data-mode", "perform");
    await expect(keys.getByRole("button", {name: "System", exact: true})).toBeFocused();
    await expectShortLandscape(page, info, observations, "System return");
    expect(await inspectTruth(page)).toEqual(before);
    // Preserve the old strict full and compact oracles, then cross the
    // portrait boundary in both directions before returning to the new form.
    for (const regular of [{width: 768, height: 600}, {width: 1440, height: 900}]) {
      await resizeViewport(page, regular);
      await expectConsoleFitsStage(page);
      expect(await inspectTruth(page)).toEqual(before);
    }
    await resizeViewport(page, {width: 768, height: 1024});
    const portrait = await page.locator(".hardware-workspace").evaluate(node => {
      const matrix = new DOMMatrixReadOnly(getComputedStyle(node).transform);
      return {a: matrix.a, b: matrix.b};
    });
    expect(portrait).toEqual({a: 0, b: -1});
    expect(await inspectTruth(page)).toEqual(before);
    await resizeViewport(page, viewport);
    await expectShortLandscape(page, info, observations, "returned short stage");
    await page.reload();
    await waitForProjectReopen(page, before.project_id.slice(0, 8));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
    await expectShortLandscape(page, info, observations, "cold reopened short stage");
    expect(await inspectTruth(page)).toEqual(before);
    const screenshot = info.outputPath("short-landscape.png");
    await page.screenshot({path: screenshot});
    await info.attach("short landscape", {path: screenshot, contentType: "image/png"});
    await info.attach("all short landscape transitions", {
      path: info.outputPath("short-landscape-observations.json"), contentType: "application/json",
    });
  });
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
    x: physical.x - 6,
    y: physical.y + 80 + 16 - 6,
    width: 92,
    height: 92,
  });
  const encoder = await box(page.getByRole("button", {
    name: "Encoder 1 — Start",
  }));
  expect(encoder).toMatchObject({width: 44, height: 44});
  expect(await box(page.getByRole("button", {name: "Encoder 1 — Start"}).locator("svg")))
    .toMatchObject({width: 32, height: 32});
  const keyBlock = await box(page.getByTestId("physical-keys"));
  expect(keyBlock).toMatchObject({
    x: physical.x - 6,
    y: pads.y - 6,
    width: 92,
    height: 380,
  });
  const keys = page.getByTestId("physical-controls");
  for (const bank of ["Bank A", "Bank B", "Bank C", "Bank D"]) {
    const bankBox = await box(keys.getByRole("button", {name: bank, exact: true}));
    expect(bankBox).toMatchObject({width: 44, height: 44});
    const face = await keys.getByRole("button", {name: bank, exact: true}).evaluate(element => {
      const style = getComputedStyle(element, "::before");
      return {width: style.width, height: style.height, inset: style.top};
    });
    expect(face).toEqual({width: "32px", height: "32px", inset: "6px"});
  }
  for (const [name, text] of [["Project", "PRJ"], ["Sample", "SMP"],
    ["Sequence", "SEQ"], ["Perform", "PRF"], ["Record", "REC"], ["Play/Stop", "PLAY"]]) {
    await expect(keys.getByRole("button", {name, exact: true})).toHaveText(text);
  }
  await expect(keys.getByRole("button", {name: "Record", exact: true}))
    .toHaveCSS("color", "rgb(229, 173, 196)");
  await expect(keys.getByRole("button", {name: "Play/Stop", exact: true}))
    .toHaveCSS("color", "rgb(221, 244, 120)");
  // Interaction UI puts SHIFT after Bank D and before both direction rows.
  // Its 80px face keeps the original centres; the 92px target shares the
  // unchanged 48px pitch, so SHIFT still starts four rows down.
  const shift = await box(keys.getByRole("button", {name: /^SHIFT/}));
  expect(shift).toMatchObject({
    x: keyBlock.x,
    y: keyBlock.y + 4 * 48,
    width: 92,
    height: 44,
  });
  const up = await box(keys.getByRole("button", {name: /^Previous Pad — ↑$/}));
  const left = await box(keys.getByRole("button", {name: "Previous Sample page — ←", exact: true}));
  expect(up.y).toBe(keyBlock.y + 5 * 48);
  expect(left.y).toBe(keyBlock.y + 6 * 48);
  // Undo/Redo is the SHIFT + ← / → chord on the direction row; the lamp, not
  // a greyed button pair, reports availability, and nothing sits outside the
  // console frame.
  await expect(keys.getByRole("button", {name: "Previous Sample page — ←", exact: true}))
    .toBeDisabled();
  await expect(keys.getByRole("button", {name: "Next Sample page — →", exact: true}))
    .toBeEnabled();
  await keys.getByRole("button", {name: /^SHIFT/}).click();
  const undoKey = keys.getByRole("button", {name: "Undo — SHIFT + ←", exact: true});
  await expect(undoKey).toBeDisabled();
  await expect(undoKey).not.toHaveClass(/\bis-lit\b/);
  await expect(keys.getByRole("button", {name: "Redo — SHIFT + →", exact: true}))
    .toBeDisabled();
  await keys.getByRole("button", {name: /^SHIFT/}).click();
  await expect(page.getByTestId("authoring-history")).toHaveCount(0);
  await expect(keys.getByRole("button", {name: "Project", exact: true})).toBeVisible();
  await expect(keys.getByRole("button", {name: "Sample", exact: true})).toBeVisible();
  // Boot opens a playable Project (#1660), so Sequence is reachable at once.
  await expect(keys.getByRole("button", {name: "Sequence", exact: true}))
    .toBeEnabled();
  await expect(keys.getByRole("button", {name: /^Perform/})).toBeVisible();
  // Interaction UI uses readable transport faces while retaining the full
  // accessible identities used by the native controls and keyboard journey.
  const record = keys.getByRole("button", {name: "Record", exact: true});
  await expect(record.locator("svg")).toHaveCount(0);
  await expect(record).toHaveText("REC");
  const playStop = keys.getByRole("button", {
    name: "Play/Stop",
    exact: true,
  });
  await expect(playStop.locator("svg")).toHaveCount(0);
  await expect(playStop).toHaveText("PLAY");
  const shot = process.env.LMDJ_HARDWARE_CONSOLE_SHOT;
  if (shot) {
    await page.getByTestId("hardware-console").screenshot({path: shot});
  }

  await expect(page.getByTestId("overview-display").locator("button")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Existing workspace"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Activate audio"})).toHaveCount(0);

  // Short windows use the compact geometry before fitting, retaining every
  // control and actual targets without outer scrolling or overlap.
  for (const viewport of [{width: 768, height: 600}, {width: 1280, height: 720}]) {
    await page.setViewportSize(viewport);
    await expect(page.locator("html")).toHaveAttribute("data-creator-layout", "compact");
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
  await expect(matrix.getByRole("button", {name: /^Pad D01 /}).locator("kbd")).toHaveText("Z");
});

const projectHeading = (page) =>
  page.getByRole("heading", {name: "Project 00000000"});

async function importAndOpenProject(page, source = bundle) {
  await page.getByRole("button", {name: "Project", exact: true}).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(source);
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
async function displayedBpm(page) {
  const text = await page.locator(".overview-bpm").innerText();
  const bpm = Number.parseFloat(text.replace(/[^0-9]/g, ""));
  // An unreadable tempo has to fail right here. `toBe` compares with
  // Object.is, under which two NaNs agree, so a drill that never managed to
  // read the displayed tempo would otherwise report every leg as unchanged.
  expect(
    Number.isFinite(bpm),
    `displayed tempo must be readable, got ${JSON.stringify(text)}`,
  ).toBe(true);
  return bpm;
}

// Project Truth answers with the same authority the Host writes through.
async function inspectTruth(page) {
  const inspected = await page.evaluate(() =>
    window.lmdjWebRuntimeHost.inspection.inspectProject());
  return inspected.project;
}

test("Project arrows follow the single list and only Open changes Project", async ({page}, testInfo) => {
  // Observe the same native transport the application uses; navigation must
  // neither reopen a Project nor produce a Pad trigger, even without audio.
  await page.addInitScript(() => {
    let exposed;
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get: () => exposed,
      set(host) {
        const transport = host.transport;
        window.__projectNavigationCommands = [];
        host.transport = Object.freeze({
          send(...args) {
            if (["project.open", "trigger"].includes(args[0]?.operation)) {
              window.__projectNavigationCommands.push(structuredClone(args[0]));
            }
            return transport.send(...args);
          },
          subscribe: (...args) => transport.subscribe(...args),
          subscribeFailure: (...args) => transport.subscribeFailure(...args),
          terminate: (...args) => transport.terminate(...args),
          get terminated() { return transport.terminated; },
          get terminalOwnerReleased() { return transport.terminalOwnerReleased; },
        });
        exposed = host;
      },
    });
  });
  await page.goto("/");
  await waitForBootProject(page);
  const keys = page.getByTestId("physical-controls");
  const touch = page.getByTestId("touch-workspace");
  // Four real local Projects force scrolling in the single column. Create
  // them through the UI rather than cloning cards or fabricating inventory.
  for (let index = 0; index < 3; index += 1) {
    const before = await inspectTruth(page);
    await keys.getByRole("button", {name: "Project", exact: true}).click();
    await page.getByRole("button", {name: "New Project", exact: true}).click();
    await expect.poll(async () => (await inspectTruth(page)).project_id,
      {timeout: PROJECT_TRANSITION_TIMEOUT_MS}).not.toBe(before.project_id);
    await waitForBootProject(page);
  }
  await keys.getByRole("button", {name: "Project", exact: true}).click();
  const cards = touch.locator(".project-card");
  await expect(cards).toHaveCount(4);
  const labels = await cards.evaluateAll(elements => elements.map(element => element.getAttribute("aria-label")));
  const before = await inspectTruth(page);
  const commandsBefore = await page.evaluate(() => window.__projectNavigationCommands);
  const expectSelection = async (index) => {
    await expect.poll(() => cards.evaluateAll(elements => elements.map(element => element.getAttribute("aria-pressed"))))
      .toEqual([0, 1, 2, 3].map(cardIndex => String(cardIndex === index)));
    expect(await inspectTruth(page)).toEqual(before);
    expect(await page.evaluate(() => window.__projectNavigationCommands)).toEqual(commandsBefore);
    // The entire selected card, including its explicit Open action, must be
    // visible after rail/encoder navigation without a Playwright auto-scroll.
    const visible = await touch.evaluate(element => {
      const card = element.querySelector(".local-projects .is-selected").getBoundingClientRect();
      const panel = element.getBoundingClientRect();
      return card.top >= panel.top - 1 && card.bottom <= panel.bottom + 1 &&
        card.left >= panel.left - 1 && card.right <= panel.right + 1;
    });
    expect(visible).toBe(true);
  };
  for (const viewport of [{width: 1440, height: 900}, {width: 1280, height: 600}, {width: 768, height: 600}]) {
    await resizeViewport(page, viewport);
    await expectConsoleFitsStage(page);
    await cards.nth(0).click();
    await expectSelection(0);
    await page.screenshot({path:testInfo.outputPath(`project-list-top-${viewport.width}x${viewport.height}.png`)});
    const geometry = await touch.evaluate(element => ({
      width: element.clientWidth, scrollWidth: element.scrollWidth,
      listWidth: element.querySelector(".local-projects").getBoundingClientRect().width,
      headingWidth: element.querySelector(".project-chooser-header").getBoundingClientRect().width,
      createWidth: element.querySelector(".project-create-row").getBoundingClientRect().width,
      cards: [...element.querySelectorAll(".project-card")].map(card => ({
        rect: card.getBoundingClientRect().toJSON(), width: card.clientWidth, scrollWidth: card.scrollWidth,
        fullId: card.title,
      })),
    }));
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width);
    expect(geometry.headingWidth, "Project title row spans the same content width as the cards").toBeCloseTo(geometry.listWidth, 0);
    expect(geometry.createWidth, "New and Import fill the same content width as the cards").toBeCloseTo(geometry.listWidth, 0);
    for (const [index, card] of geometry.cards.entries()) {
      expect(card.scrollWidth).toBeLessThanOrEqual(card.width);
      expect(card.fullId).toMatch(/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/);
      expect(card.rect.left).toBeCloseTo(geometry.cards[0].rect.left, 0);
      if (index > 0) expect(card.rect.top).toBeGreaterThan(geometry.cards[index - 1].rect.bottom);
    }
    await cards.nth(1).scrollIntoViewIfNeeded();
    const target = await cards.nth(1).boundingBox();
    const hit = await page.evaluate(({x, y}) =>
      document.elementFromPoint(x, y)?.closest("button")?.getAttribute("aria-label"),
    {x: target.x + target.width / 2, y: target.y + target.height / 2});
    expect(hit).toBe(labels[1]);
    await cards.nth(1).click();
    await expectSelection(1);
    await keys.getByRole("button", {name: "Previous Project — ↑", exact: true}).click();
    await expectSelection(0);
    await expect(keys.getByRole("button", {name: "Previous Project — ↑", exact: true})).toBeDisabled();
    for (const name of ["Undo — SHIFT + ←", "Redo — SHIFT + →"]) {
      await expect(keys.getByRole("button", {name, exact: true})).toBeDisabled();
    }
    for (let index = 1; index <= 3; index += 1) {
      await keys.getByRole("button", {name: "Next Project — ↓", exact: true}).click();
      await expectSelection(index);
    }
    await expect(keys.getByRole("button", {name: "Next Project — ↓", exact: true})).toBeDisabled();
    for (let index = 2; index >= 0; index -= 1) {
      await keys.getByRole("button", {name: "Previous Project — ↑", exact: true}).click();
      await expectSelection(index);
    }
    const encoder = keys.getByRole("button", {name: "Encoder 1 — Select Project", exact: true});
    await encoder.focus();
    await page.keyboard.press("ArrowUp");
    await expectSelection(1);
    const scrollBefore = await touch.evaluate(element => element.scrollTop);
    const scroller = keys.getByRole("button", {name: "Encoder 2 — Scroll Projects", exact: true});
    await scroller.focus();
    await page.keyboard.press("ArrowUp");
    expect(await touch.evaluate(element => element.scrollTop)).toBeGreaterThan(scrollBefore);
    await expect(cards.nth(1)).toHaveAttribute("aria-pressed", "true");
    expect(await inspectTruth(page)).toEqual(before);
    expect(await page.evaluate(() => window.__projectNavigationCommands)).toEqual(commandsBefore);
    await encoder.focus();
    await page.keyboard.press("ArrowUp");
    await expectSelection(2);
    await page.screenshot({path:testInfo.outputPath(`project-list-selected-${viewport.width}x${viewport.height}.png`)});
  }
  const currentIndex = await cards.evaluateAll(elements => elements.findIndex(element =>
    element.parentElement.getAttribute("aria-current") === "true"));
  expect(currentIndex).toBeGreaterThanOrEqual(0);
  const targetIndex = currentIndex === 3 ? 0 : 3;
  await cards.nth(targetIndex).click();
  await expectSelection(targetIndex);
  const selectedId = labels[targetIndex].slice("Select Project ".length);
  await page.getByRole("button", {name: `Open Project ${selectedId}`, exact: true}).click();
  await expect(page.getByRole("heading", {name: `Project ${selectedId}`, exact: true}))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  const opened = await inspectTruth(page);
  expect(opened.project_id.slice(0, 8)).toBe(selectedId);
  const commandsAfter = await page.evaluate(() => window.__projectNavigationCommands);
  expect(commandsAfter.slice(commandsBefore.length).map(command => command.operation)).toEqual(["project.open"]);
  expect(commandsAfter.at(-1).payload.project_id).toBe(opened.project_id);
  await page.reload();
  await waitForProjectReopen(page, selectedId);
  expect(await inspectTruth(page)).toEqual(opened);
});

test("commits Tempo only on release and keeps Project Truth across a reload", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  await waitForBootProject(page);

  await importAndOpenProject(page);
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  const committed = await displayedBpm(page);
  expect(committed).toBeGreaterThan(0);
  const baseline = await inspectTruth(page);
  expect(baseline.bpm).toBe(committed);

  // Leg 1 — a draft without release is not a commit. Moving the fader only
  // previews on both displays: Project Truth stays put, and no
  // Apply button exists to turn the draft into a commit.
  await page.getByRole("button", {name: "Sequence"}).click();
  await showSequenceLayer(page, "SETUP");
  const bpmFader = page.getByRole("slider", {name: "BPM"});
  await expect(bpmFader).toBeVisible();
  await bpmFader.fill(String(committed + 12));
  await expect(page.getByRole("button", {name: /Apply/})).toHaveCount(0);
  expect(await displayedBpm(page)).toBe(committed + 12);
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
  await expect.poll(() => displayedBpm(page)).toBe(committed + 12);
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
  expect(await displayedBpm(page)).toBe(committed + 12);
  expect((await inspectTruth(page)).bpm).toBe(committed + 12);
});

// Desktop Final plan T1b: the console face ships inside the stylesheet as a
// data: URL, so it needs the distribution CSP's `font-src data:` and no
// network. A blocked or missing face reports "error" or nothing here.
test("the console loads both bundled font roles under its distribution CSP", async ({page}) => {
  const violations = [];
  page.on("console", (message) => {
    if (/Content Security Policy|font-src/i.test(message.text())) violations.push(message.text());
  });
  await page.goto("/");
  await waitForBootProject(page);
  const loaded = await page.evaluate(async () =>
    (await document.fonts.load('12px "IBM Plex Mono"')).map((face) => face.status));
  expect(loaded).toEqual(["loaded"]);
  const actionLoaded = await page.evaluate(async () =>
    (await document.fonts.load('500 12px "Space Grotesk"')).map((face) => face.status));
  expect(actionLoaded).toEqual(["loaded"]);
  const family = await page.getByTestId("hardware-console")
    .evaluate((element) => getComputedStyle(element).fontFamily);
  expect(family).toMatch(/^"IBM Plex Mono"/);
  expect(violations).toEqual([]);
});

// The hit box is laid out at its full size, rather than enlarged over a
// neighbour. Read the separately painted face and transformed target geometry;
// a CSS class alone cannot prove either property. These design-unit checks do
// not discharge the separate minimum effective CSS-pixel target acceptance.
test("compact actions keep their font, visible face and separate hit boxes after scaling", async ({page}) => {
  await page.goto("/");
  await waitForBootProject(page);
  const touch = page.getByTestId("touch-workspace");
  const keys = page.getByTestId("physical-controls");
  for (const viewport of [{width:1440, height:900}, {width:1280, height:600}, {width:768, height:600}]) {
    await page.setViewportSize(viewport);
    for (const mode of ["Project", "Sample", "Sequence", "Perform"]) {
      await keys.getByRole("button", {name:mode, exact:true}).click();
      await touch.evaluate(element => { element.scrollTop = 0; });
      // Mode effects may scroll the touch panel, never its scaled stage.
      await expectConsoleFitsStage(page);
      const group = mode === "Project" ? touch.locator(".project-open-row")
        : mode === "Sample" ? touch.getByRole("navigation", {name:"Sample pages"})
        : mode === "Perform" ? touch.getByRole("navigation", {name:"Perform pages"})
        : touch.locator(".sequence-layer");
      await expect(group).toBeVisible();
      const rendered = await group.locator("button").evaluateAll(elements => elements.map(element => {
        const style = getComputedStyle(element);
        const face = getComputedStyle(element, "::before");
        const rect = element.getBoundingClientRect();
        return {text:element.textContent, height:element.offsetHeight,
          face:parseFloat(face.height), radius:face.borderRadius, family:style.fontFamily,
          size:style.fontSize, leading:style.lineHeight, weight:style.fontWeight,
          rect:rect.toJSON()};
      }));
      expect(rendered.length).toBeGreaterThan(1);
      for (const button of rendered) {
        expect(button.height, `${mode}: ${button.text}`).toBe(44);
        expect(button.rect.width).toBeGreaterThanOrEqual(44);
        expect(button.rect.height).toBeGreaterThanOrEqual(44);
        expect(button.face).toBe(32);
        expect(button.radius).toBe("6px");
        expect(button.family).toMatch(/^"IBM Plex Mono"/);
        expect(button.size).toBe("9px");
        expect(button.leading).toBe("13px");
        expect(button.weight).toBe("400");
      }
      for (let i=0; i<rendered.length; i++) for (let j=i+1; j<rendered.length; j++) {
        const a=rendered[i].rect, b=rendered[j].rect;
        const intersection=Math.max(0, Math.min(a.right,b.right)-Math.max(a.left,b.left)) *
          Math.max(0, Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));
        expect(intersection, `${mode}: ${rendered[i].text} / ${rendered[j].text}`).toBe(0);
      }
      const fit = await touch.evaluate(element => ({width:element.clientWidth, content:element.scrollWidth}));
      expect(fit.content).toBeLessThanOrEqual(fit.width);
      const overviewFamily = await page.getByTestId("overview-display").evaluate(element => getComputedStyle(element).fontFamily);
      expect(overviewFamily).toMatch(/^"IBM Plex Mono"/);
    }
  }
});

async function expectOverviewFits(overview, context) {
  const geometry = await overview.evaluate(element => {
    const outer = element.getBoundingClientRect();
    const errors = [];
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.textContent.trim() || node.parentElement.closest(".visually-hidden")) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const rect of range.getClientRects()) {
        if (rect.width === 0 || rect.height === 0) continue;
        if (rect.left < outer.left - 1 || rect.right > outer.right + 1 ||
            rect.top < outer.top - 1 || rect.bottom > outer.bottom + 1) {
          errors.push({text: node.textContent, rect: rect.toJSON()});
        }
      }
    }
    return {errors, width: element.clientWidth, scrollWidth: element.scrollWidth,
      height: element.clientHeight, scrollHeight: element.scrollHeight};
  });
  expect(geometry.errors, context).toEqual([]);
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width);
  expect(geometry.scrollHeight).toBeLessThanOrEqual(geometry.height);
}

// Text can stay inside the outer display while fields overlap or an encoder
// label is ellipsized. Inspect actual drawn fragments against their own box
// and every other field; do not infer readability from the console's size.
async function overviewTextGeometry(overview) {
  return overview.evaluate(root => {
    const bounds = root.getBoundingClientRect();
    const fields = [...root.querySelectorAll([
      ".overview-context", ".overview-transport > *",
      ".overview-summary-columns dt", ".overview-summary-columns dd",
      ".encoder-readbacks dt", ".encoder-readbacks dd",
    ].join(","))].filter(field => !field.closest(".visually-hidden"));
    const errors = [];
    const observations = fields.map((field, index) => {
      const box = field.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(field);
      const fragments = [...range.getClientRects()].filter(rect => rect.width > 0 && rect.height > 0);
      const text = field.textContent.trim();
      const style = getComputedStyle(field);
      if (style.visibility !== "visible" || box.width <= 0 || box.height <= 0) {
        errors.push({kind: "hidden", text});
      }
      for (const rect of fragments) {
        if (rect.left < bounds.left - 0.5 || rect.right > bounds.right + 0.5 ||
            rect.top < bounds.top - 0.5 || rect.bottom > bounds.bottom + 0.5) {
          errors.push({kind: "outside display", text});
        }
        if (rect.left < box.left - 0.5 || rect.right > box.right + 0.5 ||
            rect.top < box.top - 0.5 || rect.bottom > box.bottom + 0.5) {
          errors.push({kind: "clipped field", text});
        }
      }
      if (field.classList.contains("overview-value") &&
          field.closest('[aria-label="Project"], [aria-label="Audio"]') && fragments.length !== 1) {
        errors.push({kind: "split identity or audio state", text});
      }
      return {index, text, fontSize: style.fontSize,
        box: box.toJSON(), fragments: fragments.map(rect => rect.toJSON())};
    });
    for (const [index, field] of observations.entries()) {
      for (const other of observations.slice(index + 1)) {
        if (field.fragments.some(a => other.fragments.some(b =>
          Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.5 &&
          Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5))) {
          errors.push({kind: "overlapping fields", text: field.text, other: other.text});
        }
      }
    }
    return {bounds: bounds.toJSON(), observations, errors,
      text: fields.map(field => field.textContent.trim())};
  });
}

test("Project and System keep full readable facts and encoder labels on narrow portrait consoles", async ({page, browserName}, info) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(360_000);
  const report = {observations: [], pageErrors: []};
  page.on("pageerror", error => report.pageErrors.push(error.message));
  try {
    await page.goto("/");
    await waitForBootProject(page);
    await importAndOpenProject(page);
    const baseline = await inspectTruth(page);
    report.baseline = baseline;
    // The unchanged wide view is a positive control for the same instrument.
    for (const audio of ["inactive", "running"]) {
      if (audio === "running") {
        await page.getByRole("button", {name: "Back to music", exact: true}).click();
        await wakeAudioWithPad(page);
      }
      for (const viewport of [{width:1440,height:900}, {width:390,height:844},
        {width:480,height:844}, {width:600,height:900}, {width:707,height:900},
        {width:768,height:1024}]) {
        await resizeViewport(page, viewport);
        for (const mode of ["project", "system"]) {
          if (await page.getByRole("button", {name: "Back to music", exact: true}).count()) {
            await page.getByRole("button", {name: "Back to music", exact: true}).click();
          }
          await page.getByTestId("physical-controls").getByRole("button", {
            name: mode === "project" ? "Project" : "System", exact: true,
          }).click();
          const overview = page.getByTestId("overview-display");
          await expect(overview.locator(".overview-display")).toHaveAttribute("data-mode", mode);
          await expect(overview.locator('[aria-label="Audio"] .overview-value')).toHaveText(audio);
          await expect(overview.locator("button,input,select,[tabindex]")).toHaveCount(0);
          const normal = await overviewTextGeometry(overview);
          const label = `${mode}-${viewport.width}-${audio}`;
          report.observations.push({label, viewport, presentationOnly:false, ...normal});
          if (viewport.width === 390 || viewport.width === 1440) {
            const path = info.outputPath(label + ".png");
            await overview.screenshot({path});
            await info.attach(label, {path, contentType:"image/png"});
          }
          await writeFile(info.outputPath("readable-overviews.json"), JSON.stringify(report, null, 2));
          expect(normal.errors, label).toEqual([]);

          // Stylesheet fixture only: this is the actual longest existing
          // storage qualifier, not a manufactured Native prepare failure.
          const storage = overview.locator('[aria-label="Project"] dt');
          const saved = await storage.textContent();
          try {
            await storage.evaluate(element => {
              element.textContent = "SAMPLE SAVED · AUDIO PENDING";
            });
            const qualified = await overviewTextGeometry(overview);
            report.observations.push({label:label+"-qualified", viewport,
              presentationOnly:true, ...qualified});
            expect(qualified.text).toContain("SAMPLE SAVED · AUDIO PENDING");
            await writeFile(info.outputPath("readable-overviews.json"), JSON.stringify(report, null, 2));
            if (viewport.width === 390 || viewport.width === 1440) {
              const path = info.outputPath(label + "-qualified.png");
              await overview.screenshot({path});
              await info.attach(label + " qualified", {path, contentType:"image/png"});
            }
            expect(qualified.errors, label+" qualified").toEqual([]);
          } finally {
            await storage.evaluate((element, text) => {element.textContent = text;}, saved);
          }
          expect(await inspectTruth(page)).toEqual(baseline);
        }
      }
    }
    await page.reload();
    await waitForProjectReopen(page, "00000000");
    report.reopened = await inspectTruth(page);
    expect(report.reopened).toEqual(baseline);
    expect(report.pageErrors).toEqual([]);
  } finally {
    const path = info.outputPath("readable-overviews.json");
    await writeFile(path, JSON.stringify(report, null, 2));
    await info.attach("readable overview facts", {path, contentType:"application/json"});
  }
});

test("mode-specific overview stays read-only and fits every supported viewport", async ({page}, testInfo) => {
  await page.goto("/");
  await waitForBootProject(page);
  await importAndOpenProject(page);
  await expect(page.locator(".overview-context")).toHaveText("PROJECT / 00000000");
  for (const viewport of [{width: 1440, height: 900}, {width: 1280, height: 600}, {width: 768, height: 600}]) {
    await page.setViewportSize(viewport);
    for (const mode of ["Project", "Sample", "Sequence", "Perform"]) {
      await page.getByRole("button", {name: mode, exact: true}).click();
      const overview = page.getByTestId("overview-display");
      await expect(overview.locator("button,input,select,[tabindex]")).toHaveCount(0);
      await expect(overview.getByText("Rev", {exact: true})).toHaveCount(0);
      await expectOverviewFits(overview, `${mode} at ${viewport.width}×${viewport.height}`);
      if (viewport.width === 1440) await testInfo.attach(`${mode} overview`, {
        body: await overview.screenshot(), contentType: "image/png",
      });
    }
  }
});

test("mode-specific overview identity, read-only feedback and details survive navigation and reopen", async ({page}) => {
  // Fault/latency injection proves Creator's rendering and recovery, not a
  // physical device or Runtime I/O failure. Other operations reach real Wasm.
  await page.addInitScript(() => {
    let exposed;
    Object.defineProperty(window, "lmdjWebRuntimeHost", {configurable: true,
      get: () => exposed,
      set(host) {
        const native = host.transport;
        host.transport = new Proxy({}, {get(_target, key) {
          const target = native;
          if (key === "send") return async (...args) => {
            const [request] = args;
            if (request.operation === "sample.inspect" && window.__holdOverviewInspect) {
              window.__holdOverviewInspect = false;
              await new Promise(resolve => { window.__releaseOverviewInspect = resolve; });
            }
            if (request.operation === "sample.update_pad" && window.__failOverviewUpdate) {
              window.__failOverviewUpdate = false;
              return {protocol_version: 1, request_id: request.request_id, ok: false,
                error: {code: "INTERNAL_ERROR", message: "Injected update failure", details: {}}};
            }
            return target.send(...args);
          };
          const value = Reflect.get(target, key);
          return typeof value === "function" ? value.bind(target) : value;
        }});
        exposed = host;
      },
    });
  });
  await page.goto("/");
  await waitForBootProject(page);
  // This journey needs one assigned Pad, not 64 incidental assignment entries.
  // Keep the full fixture for the independent layout matrix and other journeys.
  await importAndOpenProject(page, process.env.LMDJ_CREATOR_WEB_OVERVIEW_BUNDLE ?? bundle);
  await expect(page.locator(".overview-context")).toHaveText("PROJECT / 00000000");
  await page.setViewportSize({width: 768, height: 600});
  await page.getByRole("button", {name: "Perform", exact: true}).click();
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await page.getByRole("button", {name: "Bank B", exact: true}).click();
  await page.evaluate(() => { window.__holdOverviewInspect = true; });
  await page.getByRole("button", {name: /^Pad B03 /}).click();
  await expect(page.locator(".overview-context")).toHaveText("SAMPLE / PAD B03");
  await expect(page.locator(".sample-overview-pad")).toHaveText("SAMPLE · LOADING");
  const loadingOverlay = page.locator(".sample-overview-empty");
  await expect(loadingOverlay.locator("strong")).toHaveText("LOADING");
  await expect(loadingOverlay.locator("span")).toHaveText("Loading Sample details…");
  await expect(loadingOverlay).not.toContainText("unavailable");
  await expectOverviewFits(page.getByTestId("overview-display"), "Sample loading");
  await expect.poll(() => page.evaluate(() => typeof window.__releaseOverviewInspect)).toBe("function");
  await page.evaluate(() => window.__releaseOverviewInspect());
  await expect(page.locator(".sample-overview-pad")).toHaveText("SAMPLE");
  await expect(loadingOverlay).toHaveCount(0);
  await expect(page.locator(".sample-overview-facts")).toContainText(/(?:mono|stereo) [1-9]\d* Hz/);
  await showSamplePage(page, "Playback");
  const reverse = page.getByRole("button", {name: "Reverse", exact: true});
  await expect(reverse).toBeEnabled();
  const beforeFailure = await inspectTruth(page);
  await page.evaluate(() => { window.__failOverviewUpdate = true; });
  await reverse.click();
  await expect(page.locator(".sample-overview-pad")).toHaveText("SAMPLE · CHECK LAST ACTION");
  await expect(page.getByRole("alert")).toContainText("Creator could not change this sound.");
  await expect(reverse).toHaveAttribute("aria-pressed", "false");
  expect(await inspectTruth(page)).toEqual(beforeFailure);
  await expectOverviewFits(page.getByTestId("overview-display"), "Sample commit failure");
  // The same operation can recover; the failure must not leave a stale cue.
  await reverse.click();
  await expect(reverse).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".sample-overview-pad")).toHaveText("SAMPLE");
  // B03 owns an unclassified Sample before and after the failed/retried edit.
  await expect(page.locator(".sample-overview-pad")).toHaveText("SAMPLE");
  await expect(page.locator(".selected-sample strong")).toHaveText("Pad B03");
  await showSamplePage(page, "Pad");
  await page.getByRole("button", {name: "Delete Pad B03", exact: true}).click();
  await expect(page.locator(".sample-overview-pad")).toHaveText("EMPTY");
  await expectOverviewFits(page.getByTestId("overview-display"), "Empty Pad");
  await expect(page.getByRole("button", {name: /^Pad B03 — empty/})).toBeVisible();
  await page.getByRole("button", {name: /^SHIFT/}).click();
  await page.getByRole("button", {name: "Undo — SHIFT + ←", exact: true}).click();
  await expect(page.locator(".sample-overview-pad")).toHaveText("SAMPLE");
  await expect(page.getByRole("button", {name: /^Pad B03 — assigned/})).toBeVisible();

  await page.getByRole("button", {name: "System", exact: true}).click();
  await page.locator(".creator-details summary").click();
  const detailIdentity = page.locator(".creator-details-facts div").filter({
    has: page.locator("dt", {hasText: /^Project ID$/}),
  }).locator("dd");
  await expect(detailIdentity).toBeVisible();
  const truth = await inspectTruth(page);
  await expect(detailIdentity).toHaveText(truth.project_id);
  await page.getByRole("button", {name: "Back to music"}).click();
  await expect(page.locator(".overview-context")).toHaveText("SAMPLE / PAD B03");
  await page.reload();
  await reopenLocalProject(page);
  await expect(page.locator(".overview-context")).toHaveText("PROJECT / 00000000");
  expect((await inspectTruth(page)).project_id).toBe(truth.project_id);
});

// Observe real Facade requests while retaining its original transport and
// responses. These journeys click the rendered App, never injected handlers.
async function observePerformPadRequests(page) {
  await page.addInitScript(() => {
    window.__performPadRequests = [];
    let exposed;
    Object.defineProperty(window, "lmdjWebRuntimeHost", {configurable: true,
      get: () => exposed,
      set(host) {
        const native = host.transport;
        host.transport = new Proxy({}, {get(_target, key) {
          const value = Reflect.get(native, key, native);
          if ((key === "send" || key === "sendRetained") && typeof value === "function") {
            return (...args) => {
              const observed = {operation: args[0]?.operation, ok: null};
              window.__performPadRequests.push(observed);
              const result = Reflect.apply(value, native, args);
              if (key === "send") {
                Promise.resolve(result).then(response => {observed.ok = response?.ok;}, () => {});
              }
              return result;
            };
          }
          return typeof value === "function" ? value.bind(native) : value;
        }});
        exposed = host;
      },
    });
  });
}

test("Perform Pad arrows share all 64 silent selections and retain SHIFT/System boundaries", async ({page}) => {
  await observePerformPadRequests(page);
  await page.goto("/");
  await waitForBootProject(page);
  await importAndOpenProject(page);
  const truth = await inspectTruth(page);
  await page.getByRole("button", {name: "Perform", exact: true}).click();
  await page.evaluate(() => {window.__performPadRequests.length = 0;});
  const matrix = page.getByTestId("pad-matrix");
  const current = matrix.locator('[aria-current="true"]');
  const up = page.getByRole("button", {name: "Previous Pad — ↑", exact: true});
  const down = page.getByRole("button", {name: "Next Pad — ↓", exact: true});
  const address = slot => `${"ABCD"[Math.floor(slot / 16)]}${String(slot % 16 + 1).padStart(2, "0")}`;
  const assertCurrent = async slot => {
    await expect(current).toHaveCount(1);
    await expect(current).toHaveAttribute("aria-label", new RegExp(`^Pad ${address(slot)} —`));
    await expect(current).toHaveClass(/is-selected/);
    await expect(page.getByRole("button", {name: `Bank ${"ABCD"[Math.floor(slot / 16)]}`, exact: true}))
      .toHaveAttribute("aria-current", "page");
  };
  await assertCurrent(0);
  await expect(up).toBeDisabled();
  for (let slot = 1; slot < 64; slot += 1) {
    await down.click();
    await assertCurrent(slot);
  }
  await expect(down).toBeDisabled();
  await assertCurrent(63);
  for (let slot = 62; slot >= 0; slot -= 1) {
    await up.click();
    await assertCurrent(slot);
  }
  await expect(up).toBeDisabled();
  await assertCurrent(0);
  await down.click();
  await assertCurrent(1);
  const shift = page.getByRole("button", {name: "SHIFT — engage the Undo/Redo layer", exact: true});
  await shift.click();
  await expect(page.getByRole("button", {name: "Up — unassigned until direction mapping is approved", exact: true})).toBeDisabled();
  await expect(page.getByRole("button", {name: "Down — unassigned until direction mapping is approved", exact: true})).toBeDisabled();
  await expect(page.getByRole("button", {name: "Undo — SHIFT + ←", exact: true})).toBeVisible();
  await expect(page.getByRole("button", {name: "Redo — SHIFT + →", exact: true})).toBeVisible();
  await assertCurrent(1);
  await shift.click();
  await expect(down).toBeEnabled();
  await page.getByRole("button", {name: "System", exact: true}).click();
  await expect(page.getByRole("button", {name: "Up — unassigned until direction mapping is approved", exact: true})).toBeDisabled();
  await expect(page.getByRole("button", {name: "Down — unassigned until direction mapping is approved", exact: true})).toBeDisabled();
  await assertCurrent(1);
  await page.getByRole("button", {name: "Back to music", exact: true}).click();
  await expect(down).toBeEnabled();
  await assertCurrent(1);
  await down.click();
  await assertCurrent(2);
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.locator(".overview-context")).toHaveText("SAMPLE / PAD A03");
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByTestId("sequence-overview")).toContainText("A03");
  await assertCurrent(2);
  await page.getByRole("button", {name: "Perform", exact: true}).click();
  await assertCurrent(2);
  expect(await inspectTruth(page)).toEqual(truth);
  const requests = await page.evaluate(() => window.__performPadRequests);
  expect(requests.filter(request => ["trigger", "sample.stop", "sample.update_pad",
    "pattern.transport.input.request", "performance.fx.gesture"].includes(request.operation))).toEqual([]);
});

test("Perform Pad steps keep real held FX, HOLD and the shared ENC4 MASTER value", async ({page}) => {
  await observePerformPadRequests(page);
  await page.goto("/");
  await waitForBootProject(page);
  await importAndOpenProject(page);
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await wakeAudioWithPad(page, {padAddress: "A01"});
  await page.getByRole("button", {name: "Perform", exact: true}).click();
  const filter = page.getByRole("slider", {name: "Filter", exact: true});
  await expect(page.getByRole("button", {name: "Encoder 1 — Cutoff", exact: true})).toBeEnabled();
  await expect(filter).toHaveValue("1000");
  const acceptedFxBefore = await page.evaluate(() => window.__performPadRequests
    .filter(request => request.operation === "performance.live.control" && request.ok === true).length);
  await page.getByRole("button", {name: "Encoder 1 — Cutoff", exact: true}).press("ArrowDown");
  await expect(filter).toHaveValue("990");
  const hold = page.getByRole("button", {name: "HOLD", exact: true});
  await hold.click();
  await expect(hold).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => page.evaluate(() => window.__performPadRequests
    .filter(request => request.operation === "performance.live.control" && request.ok === true).length))
    .toBe(acceptedFxBefore + 2);
  const master = page.getByRole("slider", {name: "MASTER", exact: true});
  const monitorBefore = Number(await master.inputValue());
  expect(Number.isFinite(monitorBefore)).toBe(true);
  expect(monitorBefore).toBeGreaterThan(0);
  await page.getByRole("button", {name: "Encoder 4 — Output Volume", exact: true}).press("ArrowDown");
  await expect(master).toHaveValue(String(monitorBefore - 1));
  const truth = await inspectTruth(page);
  await page.evaluate(() => {window.__performPadRequests.length = 0;});
  const down = page.getByRole("button", {name: "Next Pad — ↓", exact: true});
  for (let slot = 1; slot <= 16; slot += 1) {
    await down.click();
    await expect(page.getByTestId("pad-matrix").locator('[aria-current="true"]'))
      .toHaveAttribute("aria-label", new RegExp(`^Pad ${slot === 16 ? "B01" : `A${String(slot + 1).padStart(2, "0")}`} —`));
    await expect(filter).toHaveValue("990");
    await expect(hold).toHaveAttribute("aria-pressed", "true");
    await expect(master).toHaveValue(String(monitorBefore - 1));
  }
  await expect(page.getByRole("button", {name: "Bank B", exact: true})).toHaveAttribute("aria-current", "page");
  expect(await inspectTruth(page)).toEqual(truth);
  const requests = await page.evaluate(() => window.__performPadRequests);
  expect(requests.filter(request => ["trigger", "sample.stop", "sample.update_pad",
    "pattern.transport.input.request", "performance.fx.gesture", "performance.live.control",
    "performance.record.begin", "performance.record.stop",
    "pattern.transport.request"].includes(request.operation))).toEqual([]);
});


// The old compact shell kept a368px touch pane in a374px console, covering
// the Project key and leaving the Pad matrix at0px. A mode-only fit test (or
// the formerly special Perform frame) misses fresh Sample boot and reload.
test("narrow console keeps every mode key and Pad reachable before and after reload", async ({page}, info) => {
  test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS);
  await page.setViewportSize({width:390,height:844});
  await page.goto("/");await waitForBootProject(page);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));
  const keys=page.getByTestId("physical-controls");
  const observations=[];
  async function inspect(label) {
    const value=await page.getByTestId("hardware-console").evaluate(root=>{
      const rect=node=>{const b=node.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height,right:b.right,bottom:b.bottom};};
      const geometry=rect(root);
      const targets=[...root.querySelectorAll('[data-testid="physical-controls"] button,[data-testid="pad-matrix"] button')].map(node=>{
        const b=node.getBoundingClientRect();
        const cx=b.x+b.width/2,cy=b.y+b.height/2;
        const points=[[cx,cy],[b.x+2,cy],[b.right-2,cy],[cx,b.y+2],[cx,b.bottom-2]];
        return {name:node.getAttribute("aria-label")??node.textContent,disabled:node.disabled,rect:rect(node),
          hits:points.map(([x,y])=>{const top=document.elementFromPoint(x,y);return top===node||node.contains(top);})};
      });
      return {viewport:{width:innerWidth,height:innerHeight},geometry,stage:rect(document.querySelector("#root")),
        regions:[...root.children].map(rect),targets,
        padCount:root.querySelectorAll('[data-testid="pad-matrix"] button').length};
    });
    observations.push({label,...value});
    await writeFile(info.outputPath("last-console-observation.json"),JSON.stringify({label,...value},null,2));
    // Check the actual DOM hit owner, not CSS width alone or equality between
    // two layouts that could share the same missing physical input region.
    for(const target of value.targets) {
      expect(target.rect.width,`${label}: ${target.name} width`).toBeGreaterThanOrEqual(44);
      expect(target.rect.height,`${label}: ${target.name} height`).toBeGreaterThanOrEqual(44);
      if(!target.disabled)expect(target.hits,`${label}: ${target.name} centre/edges intercepted`).toEqual([true,true,true,true,true]);
    }
    expect(value.padCount).toBe(16);
    const b=value.geometry,stage=value.stage;
    expect(b.x).toBeGreaterThanOrEqual(stage.x-1);expect(b.right).toBeLessThanOrEqual(stage.right+1);
    expect(b.y).toBeGreaterThanOrEqual(stage.y-1);expect(b.bottom).toBeLessThanOrEqual(stage.bottom+1);
    for(let i=0;i<value.regions.length;i++)for(let j=i+1;j<value.regions.length;j++) {
      const a=value.regions[i],b=value.regions[j];
      expect(a.right<=b.x||b.right<=a.x||a.bottom<=b.y||b.bottom<=a.y,`${label}: regions ${i}/${j} overlap`).toBe(true);
    }
    if(value.viewport.width<708) {
      expect(b.width).toBe(value.viewport.width-16);expect(b.height).toBe(778);
    }
    return value;
  }
  await inspect("fresh phone boot");
  for(const viewport of [{width:390,height:844},{width:480,height:844},
    {width:707,height:900},{width:708,height:900},{width:1440,height:900}]) {
    await resizeViewport(page,viewport);
    for(const mode of ["Project","Sample","Sequence","Perform"]) {
      await keys.getByRole("button",{name:mode,exact:true}).click();
      await expect(page.locator(".overview-display")).toHaveAttribute("data-mode",mode.toLowerCase());
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));
      await inspect(`${mode} ${viewport.width}x${viewport.height}`);
      if(viewport.width===390||viewport.width===1440) {
        const path=info.outputPath(`console-${viewport.width}-${mode}.png`);
        await page.screenshot({path});await info.attach(`${viewport.width} ${mode}`,{path,contentType:"image/png"});
      }
    }
    await keys.getByRole("button",{name:"System",exact:true}).click();
    await expect(page.locator(".overview-display")).toHaveAttribute("data-mode","system");
    await inspect(`System ${viewport.width}`);
    await page.getByRole("button",{name:"Back to music",exact:true}).click();
    await expect(page.locator(".overview-display")).toHaveAttribute("data-mode","perform");
    await inspect(`System return ${viewport.width}`);
  }
  await resizeViewport(page,{width:390,height:844});await page.reload();await waitForBootProject(page);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));
  await inspect("reopened phone");
  await keys.getByRole("button",{name:"Project",exact:true}).click();
  await expect(page.locator(".overview-display")).toHaveAttribute("data-mode","project");
  await expect(page.getByRole("button",{name:"Import .lmdj",exact:true})).toBeEnabled();
  await inspect("reopened Project pointer");
  const path=info.outputPath("narrow-console-hit-targets.json");
  await writeFile(path,JSON.stringify({observations},null,2));
  await info.attach("actual console geometry and pointer owners",{path,contentType:"application/json"});
});
