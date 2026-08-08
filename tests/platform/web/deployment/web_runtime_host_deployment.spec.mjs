import { expect, test } from "@playwright/test";


const expectedProductBuild = process.env.LMDJ_WEB_HOST_EXPECTED_PRODUCT_BUILD;
const expectedHostVersion = process.env.LMDJ_WEB_HOST_EXPECTED_VERSION;
if (!expectedProductBuild) {
  throw new Error("LMDJ_WEB_HOST_EXPECTED_PRODUCT_BUILD is required");
}
if (!expectedHostVersion) {
  throw new Error("LMDJ_WEB_HOST_EXPECTED_VERSION is required");
}


test("published Runtime Host completes the minimal diagnostic journey", async ({ page }) => {
  test.setTimeout(360_000);
  await page.goto("/index.html");
  await expect(page.locator("#host-state")).toHaveText(
    "audio-suspended",
    { timeout: 60_000 },
  );
  const identity = await page.evaluate(async () => {
    const manifest = await fetch("./host-manifest.json", { cache: "no-store" })
      .then((response) => response.json());
    return {
      secure: window.isSecureContext,
      isolated: window.crossOriginIsolated,
      sharedArrayBuffer: typeof SharedArrayBuffer === "function",
      productBuild: manifest.product_build,
      hostVersion: manifest.host_version,
      manifestReady: window.lmdjWebRuntimeHost.manifestReady,
      runtimeInitialized: window.lmdjWebRuntimeHost.runtimeInitialized,
    };
  });
  expect(identity).toEqual({
    secure: true,
    isolated: true,
    sharedArrayBuffer: true,
    productBuild: expectedProductBuild,
    hostVersion: expectedHostVersion,
    manifestReady: true,
    runtimeInitialized: true,
  });

  await page.locator("#diagnostic-project-load").click();
  await expect(page.locator("#diagnostic-project-state")).toHaveText(
    "ready",
    { timeout: 300_000 },
  );
  await page.locator("#audio-activate").click();
  await expect(page.locator("#host-state")).toHaveText(
    "running",
    { timeout: 60_000 },
  );
  const marker = await page.evaluate(() =>
    window.lmdjWebRuntimeController.diagnostics().trigger_outcome_count
  );
  await page.locator("#pad-0").click();
  await expect.poll(() => page.evaluate(() =>
    window.lmdjWebRuntimeController.diagnostics().trigger_outcome_count
  )).toBe(marker + 1);
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(true);
  await expect(page.locator("#host-state")).toHaveText("closed");
  expect(await page.evaluate(() =>
    window.lmdjWebRuntimeController.diagnostics().trigger_outcome_count
  )).toBe(marker + 1);
});
