import {readFile} from "node:fs/promises";

import {expect, test} from "@playwright/test";


const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

async function importProject(page) {
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  const chooser = await chooserPromise;
  await chooser.setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.getByText("64 / 64")).toBeVisible();
}

async function activate(page) {
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: 30_000,
  });
}

async function downloadReport(page) {
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export report"}).click();
  const download = await downloadPromise;
  // The Build lives in the packaged manifest the app already loads; naming it
  // again here made an identity bump cost a CI cycle to discover.
  expect(download.suggestedFilename()).toMatch(
      /^lmdj-creator-web-\d+\.\d+\.\d+\.\d+\.json$/);
  return JSON.parse(await readFile(await download.path(), "utf8"));
}

test("visible Creator journey imports, activates, and admits all 64 unique Pad addresses", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  await page.goto("/index.html");
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  await importProject(page);
  await activate(page);

  const visited = new Set();
  for (const bank of ["A", "B", "C", "D"]) {
    await page.getByRole("button", {name: `Bank ${bank}`}).click();
    const pads = page.getByRole("button", {name: /^Pad [A-D]\d+ — assigned$/});
    await expect(pads).toHaveCount(16);
    for (let index = 0; index < 16; index += 1) {
      const pad = pads.nth(index);
      const name = await pad.getAttribute("aria-label");
      expect(visited.has(name)).toBe(false);
      visited.add(name);
      await pad.click();
    }
  }
  expect(visited.size).toBe(64);
  await expect.poll(async () => {
    const report = await downloadReport(page);
    return [
      report.state,
      report.trigger_admitted_count,
      report.trigger_outcome_count,
      report.trigger_rejected_count,
    ];
  }, {timeout: 30_000}).toEqual(["running", 64, 64, 0]);
});
test("one held-key Bank-A burst has exactly 16 admissions and outcomes", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(120_000);
  await page.goto("/index.html");
  await importProject(page);
  await activate(page);
  const keys = [
    "KeyA", "KeyS", "KeyD", "KeyF", "KeyG", "KeyH", "KeyJ", "KeyK",
    "KeyQ", "KeyW", "KeyE", "KeyR", "KeyT", "KeyY", "KeyU", "KeyI",
  ];
  for (const key of keys) await page.keyboard.down(key);
  for (const key of keys) await page.keyboard.up(key);
  await expect.poll(async () => {
    const report = await downloadReport(page);
    return [
      report.trigger_admitted_count,
      report.trigger_outcome_count,
      report.trigger_rejected_count,
      report.state,
    ];
  }, {timeout: 30_000}).toEqual([16, 16, 0, "running"]);
});
