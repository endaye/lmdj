import {expect, test} from "@playwright/test";
import {waitForBootProject, waitForProjectReopen} from "./fixtures/creator_boot.mjs";

test("complete same-build Creator shell reopens its stored Project offline", async ({page, context, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  const manifest = await (await page.request.get("/host-manifest.json")).json();
  // P1 source lands before its coordinated Host MAJOR inventory settlement.
  test.skip(!manifest.assets.some(asset => asset.role === "offline_worker"),
    "Offline activation awaits the coordinated Creator Host MAJOR inventory");
  await page.goto("/index.html");
  await waitForBootProject(page);
  await expect.poll(() => page.evaluate(() => window.__LMDJ_OFFLINE_SHELL__),
    {timeout: 60_000}).toBe("ready");
  await page.getByRole("button", {name: "Project", exact: true}).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(process.env.LMDJ_CREATOR_WEB_BUNDLE);
  await expect(page.getByRole("heading", {name: "Project 00000000"})).toBeVisible({timeout: 120_000});
  const before = await page.evaluate(() => ({
    manifest: document.querySelector('meta[name="lmdj-host-manifest-sha256"]').content,
    build: document.querySelector('meta[name="lmdj-product-build"]').content,
  }));
  await page.close();
  await context.setOffline(true);
  const successor = await context.newPage();
  try {
    const response = await successor.goto("/index.html");
    expect(response.fromServiceWorker()).toBe(true);
    expect(response.headers()["cross-origin-opener-policy"]).toBe("same-origin");
    expect(response.headers()["cross-origin-embedder-policy"]).toBe("require-corp");
    await waitForProjectReopen(successor, "00000000");
    expect(await successor.evaluate(() => crossOriginIsolated)).toBe(true);
    expect(await successor.evaluate(() => ({
      manifest: document.querySelector('meta[name="lmdj-host-manifest-sha256"]').content,
      build: document.querySelector('meta[name="lmdj-product-build"]').content,
    }))).toEqual(before);
    await expect(successor.getByRole("button", {name: /^Pad A1 — assigned/})).toBeVisible();
    // Cache must serve every immutable JS/Wasm/worklet object with its headers.
    for (const asset of manifest.assets) {
      expect(await successor.evaluate(async asset => {
        const response = await fetch(asset.path);
        const bytes = await response.arrayBuffer();
        const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
          .map(value => value.toString(16).padStart(2, "0")).join("");
        return {length: bytes.byteLength, hash,
          isolated: response.headers.get("Cross-Origin-Embedder-Policy") === "require-corp"};
      }, asset)).toEqual({length: asset.bytes, hash: asset.sha256, isolated: true});
    }
  } finally {await context.setOffline(false); await successor.close();}
});
