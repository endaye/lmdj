import {createHash} from "node:crypto";
import {readFile} from "node:fs/promises";

import {expect, test} from "@playwright/test";


const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

test("packaged Creator owns an exact local-only asset inventory", async ({request, baseURL, browserName}) => {
  test.skip(browserName !== "chromium");
  const manifestResponse = await request.get(`${baseURL}/host-manifest.json`);
  expect(manifestResponse.ok()).toBe(true);
  const manifestBytes = await manifestResponse.body();
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  expect(manifest.distribution_contract).toBe("lmdj.creator-web.distribution.v1");
  expect(manifest.compatible_hosts).toEqual([
    {host_id: "web-runtime-host", host_version: "1.2.5"},
  ]);
  expect(manifest.assets.map(({role}) => role)).toEqual([
    "host_main", "runtime_script", "runtime_wasm", "host_style",
  ]);
  const index = await (await request.get(`${baseURL}/index.html`)).text();
  expect(index).toContain(createHash("sha256").update(manifestBytes).digest("hex"));
  expect(index).not.toMatch(/https?:\/\//i);
  for (const asset of manifest.assets) {
    expect(asset.path).toMatch(/^assets\/[a-z0-9-]+\.[0-9a-f]{64}\.(?:css|js|wasm)$/);
    expect(asset.path).not.toMatch(/(?:fixture|\.map$|test)/i);
    const response = await request.get(`${baseURL}/${asset.path}`);
    expect(response.ok()).toBe(true);
    const payload = await response.body();
    expect(payload.byteLength).toBe(asset.bytes);
    expect(createHash("sha256").update(payload).digest("hex")).toBe(asset.sha256);
    const text = payload.toString("utf8");
    expect(text).not.toMatch(/sourceMappingURL|\/Users\/|file:\/+(?:Users|home)\//);
    expect(text).not.toMatch(/[A-Za-z]:\\/);
  }
});

for (const viewport of [
  {width: 768, height: 1024},
  {width: 1024, height: 768},
  {width: 1440, height: 900},
]) {
  test(`responsive keyboard surface ${viewport.width}x${viewport.height}`, async ({page, browserName}, testInfo) => {
    test.skip(browserName !== "chromium");
    test.setTimeout(120_000);
    await page.setViewportSize(viewport);
    await page.goto("/index.html");
    await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
      timeout: 30_000,
    });
    await expect(page.getByRole("button", {name: /^Pad A\d+ — empty$/}))
      .toHaveCount(16);
    expect(await page.evaluate(() =>
      document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    )).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`creator-empty-${viewport.width}x${viewport.height}.png`),
      fullPage: true,
    });

    const chooserPromise = page.waitForEvent("filechooser");
    await page.getByRole("button", {name: "Import .lmdj"}).click();
    await (await chooserPromise).setFiles(bundle);
    await expect(page.getByRole("heading", {name: "Project 00000000"}))
      .toBeVisible({timeout: 120_000});
    const pads = page.getByRole("button", {name: /^Pad A\d+ — assigned$/});
    await expect(pads).toHaveCount(16);
    for (let index = 0; index < 16; index += 1) {
      const box = await pads.nth(index).boundingBox();
      expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
    for (const mode of ["Sample", "Sequence", "Perform"]) {
      await expect(page.getByRole("button", {name: new RegExp(`^${mode}`)}))
        .toBeDisabled();
    }
    await page.getByRole("button", {name: "Activate audio"}).focus();
    const focusOrder = [];
    for (let index = 0; index < 5; index += 1) {
      await page.keyboard.press("Tab");
      focusOrder.push(await page.evaluate(() =>
        document.activeElement?.textContent?.trim()));
    }
    expect(focusOrder).toEqual([
      "Enable MIDI", "Export report", "PProject", "Open local", "Import .lmdj",
    ]);
    expect(await page.evaluate(() =>
      document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    )).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`creator-ready-${viewport.width}x${viewport.height}.png`),
      fullPage: true,
    });
  });
}

test("WebKit capability boundary remains unsupported and is not physical acceptance", async ({page, browserName}) => {
  test.skip(browserName !== "webkit");
  await page.goto("/index.html");
  await expect(page.getByTestId("creator-phase")).toHaveText("unsupported", {
    timeout: 30_000,
  });
  await expect(page.getByRole("alert")).toContainText("UNSUPPORTED_WEB_RUNTIME");
  await expect(page.getByRole("button", {name: "Activate audio"})).toBeDisabled();
  await expect(page.getByRole("button", {name: "Export report"})).toBeDisabled();
});
