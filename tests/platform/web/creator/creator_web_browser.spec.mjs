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
  expect(download.suggestedFilename()).toBe("lmdj-creator-web-1.0.18.0.json");
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
test("one synthetic held-key Bank-A burst preserves the full Runtime tuple", async ({page, browserName}) => {
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

test("ready active Runtime survives portrait and landscape resize", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  await page.goto("/index.html");
  await importProject(page);
  await activate(page);
  await page.keyboard.press("KeyA");
  await expect.poll(async () => {
    const value = await downloadReport(page);
    return [value.trigger_admitted_count, value.trigger_outcome_count];
  }, {timeout: 30_000}).toEqual([1, 1]);

  const heading = page.getByRole("heading", {name: "Project 00000000"});
  const revision = page.locator(".project-summary div").filter({
    has: page.getByText("Revision", {exact: true}),
  }).getByRole("definition");
  const before = await downloadReport(page);
  const expectedRevision = await revision.textContent();

  for (const viewport of [
    {width: 768, height: 1024},
    {width: 1024, height: 768},
  ]) {
    await page.setViewportSize(viewport);
    await expect(heading).toBeVisible();
    await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
    await expect(revision).toHaveText(expectedRevision);
    const after = await downloadReport(page);
    expect({
      product_build: after.product_build,
      host_id: after.host_id,
      host_version: after.host_version,
      platform_version: after.platform_version,
      protocol_version: after.protocol_version,
      state: after.state,
      trigger_admitted_count: after.trigger_admitted_count,
      trigger_outcome_count: after.trigger_outcome_count,
      trigger_rejected_count: after.trigger_rejected_count,
    }).toEqual({
      product_build: before.product_build,
      host_id: before.host_id,
      host_version: before.host_version,
      platform_version: before.platform_version,
      protocol_version: before.protocol_version,
      state: before.state,
      trigger_admitted_count: before.trigger_admitted_count,
      trigger_outcome_count: before.trigger_outcome_count,
      trigger_rejected_count: before.trigger_rejected_count,
    });
  }
});
