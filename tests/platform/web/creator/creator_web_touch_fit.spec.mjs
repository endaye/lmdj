import {fileURLToPath} from "node:url";
import {expect, test} from "@playwright/test";
import {waitForBootProject} from "./fixtures/creator_boot.mjs";
import {showSequenceLayer} from "./fixtures/creator_navigation.mjs";

const captureFile = fileURLToPath(new URL(
  "./fixtures/capture-440hz-2s-mono-48k.wav", import.meta.url,
));

// Measure actual rendered content, not overflow:hidden or a CSS class. A
// clipped wide child still fails this assertion. The Sequence time axis is a
// separately named editor viewport, never permission for outer-page overflow.
async function expectTouchFits(page) {
  const touch = page.getByTestId("touch-workspace");
  await expect.poll(() => touch.evaluate(element =>
    element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
}

async function expectControlFits(page, control) {
  await control.scrollIntoViewIfNeeded();
  const touch = await page.getByTestId("touch-workspace").boundingBox();
  const box = await control.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(touch.x - 1);
  expect(box.x + box.width).toBeLessThanOrEqual(touch.x + touch.width + 1);
  expect(box.y).toBeGreaterThanOrEqual(touch.y - 1);
  expect(box.y + box.height).toBeLessThanOrEqual(touch.y + touch.height + 1);
}

test.beforeEach(async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  await waitForBootProject(page);
});

test("SETUP fits the fixed touch panel and keeps navigation reachable", async ({page}) => {
  await page.getByTestId("physical-controls").getByRole("button", {name: "Sequence", exact: true}).click();
  await showSequenceLayer(page, "SETUP");
  for (const viewport of [{width: 1440, height: 900}, {width: 1280, height: 600},
    {width: 768, height: 600}]) {
    await page.setViewportSize(viewport);
    await expectTouchFits(page);
    await expectControlFits(page, page.getByRole("button", {name: "New Pattern", exact: true}));
    await page.getByRole("button", {name: "New Pattern", exact: true}).click();
    await expectControlFits(page, page.getByRole("button", {name: "Create Pattern", exact: true}));
    await expectTouchFits(page);
    await page.getByRole("button", {name: "CANCEL", exact: true}).click();
    await expect(page.getByRole("button", {name: "Create Pattern", exact: true})).toHaveCount(0);
    // The layer header remains visible even after the lower form was used.
    const edit = page.getByRole("button", {name: "EDIT", exact: true});
    await expect(edit).toBeInViewport();
    await edit.click();
    await expect(page.getByTestId("sequence-grid")).toBeVisible();
    await expectTouchFits(page);
    await page.getByRole("button", {name: "SETUP", exact: true}).click();
  }
});

test("Swing decrement, encoder label and increment share one row", async ({page}) => {
  await page.getByTestId("physical-controls").getByRole("button", {name: "Sequence", exact: true}).click();
  await showSequenceLayer(page, "SETUP");
  const actions = page.getByRole("group", {name: "Swing actions"});
  await actions.scrollIntoViewIfNeeded();
  const bounds = await actions.locator(":scope > *").evaluateAll(elements =>
    elements.map(element => {
      const box = element.getBoundingClientRect();
      return {left: box.left, right: box.right, centre: box.top + box.height / 2};
    }));
  expect(bounds).toHaveLength(3);
  expect(Math.max(...bounds.map(box => box.centre)) -
    Math.min(...bounds.map(box => box.centre))).toBeLessThanOrEqual(1);
  expect(bounds[0].right).toBeLessThanOrEqual(bounds[1].left);
  expect(bounds[1].right).toBeLessThanOrEqual(bounds[2].left);
});

test("long title and disabled controls fit without widening the panel", async ({page}) => {
  await page.getByTestId("physical-controls").getByRole("button", {name: "Sequence", exact: true}).click();
  await showSequenceLayer(page, "SETUP");
  // Text-only layout stress fixture: not a claim that Pattern rename exists.
  await page.getByTestId("sequence-pattern").locator("h1").evaluate(element => {
    element.textContent = "Pattern_" + "very_long_unbroken_name_".repeat(6);
  });
  await expectTouchFits(page);
  await expectControlFits(page, page.getByRole("button", {name: "EDIT", exact: true}));
  await expectControlFits(page, page.getByRole("button", {name: "SETUP", exact: true}));
  await page.getByTestId("physical-controls").getByRole("button", {name: "Sample", exact: true}).click();
  await page.getByTestId("physical-controls").getByRole("button", {name: "Bank B", exact: true}).click();
  const edit = page.getByRole("button", {name: "Edit Pad B01", exact: true});
  await expect(edit).toBeDisabled();
  await expectControlFits(page, edit);
  await expectTouchFits(page);
});

test("Perform and Sound Sets use the outer touch scroller", async ({page}) => {
  const keys = page.getByTestId("physical-controls");
  await keys.getByRole("button", {name: "Perform", exact: true}).click();
  await expectTouchFits(page);
  await page.getByRole("button", {name: "FX / MORE", exact: true}).click();
  await expectTouchFits(page);
  await expect(page.locator(".perform-surface")).toHaveCSS("overflow-y", "visible");
  await keys.getByRole("button", {name: "Project", exact: true}).click();
  await page.getByRole("button", {name: "Sound Sets", exact: true}).click();
  await expectTouchFits(page);
  await expect(page.locator(".soundset-surface")).toHaveCSS("overflow-y", "visible");
  await expectControlFits(page, page.getByRole("button", {name: "Back to Project", exact: true}));
});

test("Sample empty and assigned controls stay inside the touch panel", async ({page}) => {
  test.setTimeout(180_000); // Import + projection have existing bounded Host transitions.
  const keys = page.getByTestId("physical-controls");
  await keys.getByRole("button", {name: "Sample", exact: true}).click();
  await keys.getByRole("button", {name: "Bank B", exact: true}).click();
  await expectTouchFits(page);
  const add = page.getByRole("button", {name: "Add Sample to Pad B01", exact: true});
  await expectControlFits(page, add);
  const invalidChooser = page.waitForEvent("filechooser");
  await add.click();
  await (await invalidChooser).setFiles({
    name: "invalid.wav", mimeType: "audio/wav", buffer: Buffer.from("not a wave file"),
  });
  await expect(page.getByRole("alert")).toContainText("Choose a WAV", {timeout: 30_000});
  await expectTouchFits(page);
  await expectControlFits(page, add);
  const chooser = page.waitForEvent("filechooser");
  await add.click();
  await (await chooser).setFiles(captureFile);
  const selection = page.getByRole("dialog", {name: "Pad B01 Long Source"});
  await expect(selection).toBeVisible({timeout: 30_000});
  await selection.getByRole("button", {name: "Commit selection", exact: true}).click();
  await expect(selection).toHaveCount(0, {timeout: 125_000});
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("slider", {name: "Pad B01 Volume", exact: true}))
    .toBeVisible({timeout: 125_000});
  for (const viewport of [{width: 1440, height: 900}, {width: 1280, height: 600},
    {width: 768, height: 600}]) {
    await page.setViewportSize(viewport);
    await expectTouchFits(page);
    for (const name of ["Pad B01 Volume", "Pad B01 Pitch", "Pad B01 Pan"]) {
      await expectControlFits(page, page.getByRole("slider", {name, exact: true}));
    }
    await expectControlFits(page, page.getByRole("button", {name: "Reset Pad to Defaults", exact: true}));
    await expectTouchFits(page);
  }
});
