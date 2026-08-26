import {readFile} from "node:fs/promises";

import {expect, test} from "@playwright/test";

const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

async function importProject(page) {
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {timeout: 30_000});
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(bundle);
  await expect(page.getByRole("heading", {name: /^Project /}))
    .toBeVisible({timeout: 120_000});
}

async function report(page) {
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export report"}).click();
  return JSON.parse(await readFile(await (await downloadPromise).path(), "utf8"));
}

test("Sequence authors settings, records unified input, switches at a Bar, and flushes", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await page.goto("/index.html");
  await importProject(page);
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {timeout: 30_000});
  await page.getByRole("button", {name: "Sequence"}).click();
  await expect(page.getByRole("heading", {name: "Sequence"})).toBeVisible();

  const pattern = page.getByRole("combobox", {name: "Pattern"});
  const originalPattern = await pattern.locator("option").first().getAttribute("value");
  await page.getByRole("combobox", {name: "Bars"}).selectOption("2");
  await page.getByRole("button", {name: "Create Pattern"}).click();
  await expect(pattern.locator("option")).toHaveCount(2, {timeout: 30_000});

  const quantize = page.getByRole("checkbox", {name: "Quantize"});
  await quantize.click();
  await expect(quantize).not.toBeChecked({timeout: 30_000});
  await page.getByRole("spinbutton", {name: "BPM"}).fill("132");
  await page.getByRole("button", {name: "Apply BPM"}).click();
  await expect(page.locator(".status-facts")).toContainText("BPM132", {timeout: 30_000});
  await page.getByRole("slider", {name: "Swing"}).fill("60");
  await page.getByRole("button", {name: "Apply Swing"}).click();
  await expect(page.getByRole("status", {name: "Swing 60"})).toBeVisible({timeout: 30_000});

  await page.getByRole("button", {name: "Record"}).click();
  await expect(page.getByRole("status").filter({hasText: "recording"})).toBeVisible();
  await page.keyboard.press("KeyQ");
  await pattern.selectOption(originalPattern);
  await expect(page.getByRole("status").filter({hasText: "switch-pending"}))
    .toBeVisible();
  await expect(pattern).toHaveValue(originalPattern, {timeout: 30_000});
  await page.getByRole("button", {name: "Stop"}).click();
  await expect(page.getByRole("status").filter({hasText: "stopped"}))
    .toBeVisible({timeout: 30_000});

  const evidence = (await report(page)).sequence;
  expect(evidence.semantic_state).toBe("stopped");
  expect(evidence.pending_event_count).toBe(0);
  expect(evidence.project_revision).toBe(evidence.expected_revision);
  expect(evidence.effective_runtime_frame).toBeGreaterThanOrEqual(0);
});
