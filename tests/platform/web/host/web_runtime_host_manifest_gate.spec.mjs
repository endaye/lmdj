import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";


const baseURL = process.env.LMDJ_WEB_HOST_BASE_URL ?? "http://127.0.0.1:4175";
const productVersion = JSON.parse(await readFile(
  new URL("../../../../products/lmdj/version.json", import.meta.url),
  "utf8",
));
const currentProductBuild = ["milestone", "minor", "build", "patch"]
  .map((name) => productVersion[name])
  .join(".");
const wrongProductParts = currentProductBuild.split(".").map(Number);
wrongProductParts[3] += 1;
const wrongProductBuild = wrongProductParts.join(".");


function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}


test("packaged index binds exact canonical manifest bytes without inline script", async ({ request }) => {
  const indexResponse = await request.get(`${baseURL}/index.html`);
  expect(indexResponse.ok()).toBe(true);
  const index = await indexResponse.text();
  const manifestResponse = await request.get(`${baseURL}/host-manifest.json`);
  expect(manifestResponse.ok()).toBe(true);
  const manifestBytes = await manifestResponse.body();
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  expect(manifestBytes.toString("utf8")).toBe(canonicalJson(manifest));
  const digest = createHash("sha256").update(manifestBytes).digest("hex");
  expect(index).toContain(
    `<meta name="lmdj-host-manifest-sha256" content="${digest}">`,
  );
  expect(index).not.toMatch(/<script(?![^>]*\bsrc=)[^>]*>/i);
  expect(manifest).toMatchObject({
    product_build: currentProductBuild,
    host_version: "1.0.0",
    protocol_version: 1,
    heap_bytes: 536_870_912,
  });
});


test("missing malformed oversized mismatched and wrong-identity manifests load no runtime", async ({ browser, request }) => {
  const indexResponse = await request.get(`${baseURL}/index.html`);
  const originalIndex = await indexResponse.text();
  const manifestResponse = await request.get(`${baseURL}/host-manifest.json`);
  const originalManifest = JSON.parse(await manifestResponse.text());
  const runtimeScript = originalManifest.assets.find(
    ({ role }) => role === "runtime_script",
  ).path;
  const wrongIdentity = { ...originalManifest, product_build: wrongProductBuild };
  const wrongIdentityBytes = Buffer.from(canonicalJson(wrongIdentity));
  const wrongIdentityDigest = createHash("sha256")
    .update(wrongIdentityBytes)
    .digest("hex");
  const scenarios = [
    { name: "missing", status: 404, body: "missing" },
    { name: "malformed", status: 200, body: "{" },
    { name: "oversized", status: 200, body: "x".repeat(65_537) },
    { name: "digest mismatch", status: 200, body: canonicalJson(originalManifest) + " " },
    {
      name: "wrong identity",
      status: 200,
      body: wrongIdentityBytes,
      index: originalIndex.replace(
        /(<meta name="lmdj-host-manifest-sha256" content=")[0-9a-f]{64}("\>)/,
        `$1${wrongIdentityDigest}$2`,
      ),
    },
  ];

  for (const scenario of scenarios) {
    const context = await browser.newContext();
    const page = await context.newPage();
    let runtimeRequests = 0;
    await page.addInitScript(() => {
      window.__manifestGateOpfsCalls = 0;
      const original = navigator.storage.getDirectory.bind(navigator.storage);
      navigator.storage.getDirectory = (...args) => {
        window.__manifestGateOpfsCalls += 1;
        return original(...args);
      };
    });
    await page.route(`**/${runtimeScript}`, async (route) => {
      runtimeRequests += 1;
      await route.continue();
    });
    if (scenario.index) {
      await page.route(`${baseURL}/index.html`, (route) => route.fulfill({
        status: 200,
        contentType: "text/html",
        body: scenario.index,
      }));
    }
    await page.route(`${baseURL}/host-manifest.json`, (route) => route.fulfill({
      status: scenario.status,
      contentType: "application/json",
      body: scenario.body,
    }));
    await page.goto(`${baseURL}/index.html`);
    await expect(page.locator("#host-state"), scenario.name).toHaveText("failed");
    const diagnostics = JSON.parse(await page.locator("#diagnostics").textContent());
    expect(diagnostics.error_code, scenario.name).toBe("HOST_PROTOCOL_MISMATCH");
    expect(runtimeRequests, scenario.name).toBe(0);
    expect(await page.evaluate(() => window.__manifestGateOpfsCalls), scenario.name).toBe(0);
    await context.close();
  }
});
