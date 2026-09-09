import {createHash} from "node:crypto";
import {readFile} from "node:fs/promises";

import {expect, test} from "@playwright/test";

import {WEB_RUNTIME_IDENTITY} from
  "../../../../products/lmdj/generated/web-runtime-identity.mjs";


const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");
const MAX_OPEN_ATTEMPTS = 8;
const BUSY_RETRY_INTERVAL_MS = 500;
// openProjectJourney owns three independently bounded 30-second Project
// operations: open, inspect, and snapshot reload. The UI hang detector covers
// their 90-second protocol ceiling plus bounded runner/render settling time.
const OPEN_TRANSITION_TIMEOUT_MS = 3 * 30_000 + 35_000;

async function projectOpenOutcome(heading, open, retry) {
  if (await heading.isVisible()) return "ready";
  if (await retry.isVisible()) return "busy";
  if (await open.isVisible() && await open.isEnabled()) return "open";
  return "pending";
}

async function waitForProjectOpenOutcome(heading, open, retry) {
  let outcome = "pending";
  await expect.poll(async () => {
    outcome = await projectOpenOutcome(heading, open, retry);
    return outcome;
  }, {timeout: OPEN_TRANSITION_TIMEOUT_MS}).not.toBe("pending");
  return outcome;
}

async function waitForOpenActionTransition(heading, open, retry) {
  await expect.poll(async () =>
    await projectOpenOutcome(heading, open, retry),
  {timeout: OPEN_TRANSITION_TIMEOUT_MS}).not.toBe("open");
}

async function pressProjectAction(page, action) {
  await action.focus();
  await expect(action).toBeFocused();
  await page.keyboard.press("Enter");
}

async function waitForKeyboardProjectInventory(page) {
  const open = page.getByRole("button", {name: "Open Project 00000000"});
  const retry = page.getByRole("button", {name: "Retry project"});
  const alert = page.getByRole("alert");
  for (let attempt = 0; attempt < MAX_OPEN_ATTEMPTS; attempt += 1) {
    await expect.poll(async () =>
      await open.isVisible() ? "open" : await retry.isVisible() ? "retry" : "",
    {timeout: OPEN_TRANSITION_TIMEOUT_MS}).not.toBe("");
    if (await open.isVisible()) return open;
    await expect(alert).toContainText(
      "The local Project is busy in another tab or process.",
    );
    await retry.focus();
    await expect(retry).toBeFocused();
    await page.keyboard.press("Enter");
  }
  await expect(open).toBeVisible();
  return open;
}

test("keyboard-only Project and Bank journey preserves native activation", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(360_000);
  await page.goto("/index.html");
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });

  const importButton = page.getByRole("button", {name: "Import .lmdj"});
  await importButton.focus();
  await expect(importButton).toBeFocused();
  const chooserPromise = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooserPromise).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});

  await page.reload();
  const heading = page.getByRole("heading", {name: "Project 00000000"});
  const openButton = await waitForKeyboardProjectInventory(page);
  const retry = page.getByRole("button", {name: "Retry project"});
  let actionKind = "open";
  let action = openButton;
  for (let attempt = 0; attempt < MAX_OPEN_ATTEMPTS; attempt += 1) {
    await pressProjectAction(page, action);
    if (actionKind === "open") {
      await waitForOpenActionTransition(heading, openButton, retry);
    }
    const outcome = await waitForProjectOpenOutcome(
      heading, openButton, retry,
    );
    if (outcome === "ready") break;
    if (outcome === "busy") {
      await expect(page.getByRole("alert")).toContainText(
        "The local Project is busy in another tab or process.",
      );
      // A reload can briefly overlap the previous document's asynchronous
      // writer release. Model a deliberate user retry instead of hammering the
      // visible action fast enough to exhaust the bounded attempt budget.
      await page.waitForTimeout(BUSY_RETRY_INTERVAL_MS);
      actionKind = "busy";
      action = retry;
    } else {
      // A timed-out request may be followed by the one allowed automatic
      // Runtime replacement. The replacement intentionally requires another
      // explicit Open gesture instead of silently resuming the Project.
      actionKind = "open";
      action = openButton;
    }
  }
  await expect(heading).toBeVisible();

  const bankB = page.getByRole("button", {name: "Bank B"});
  await bankB.focus();
  await expect(bankB).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(bankB).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", {name: /^Pad B\d+ — assigned — Key [QWERTYUIASDFGHJK]$/}))
    .toHaveCount(16);
});

test("packaged Creator owns an exact local-only asset inventory", async ({request, baseURL, browserName}) => {
  test.skip(browserName !== "chromium");
  const manifestResponse = await request.get(`${baseURL}/host-manifest.json`);
  expect(manifestResponse.ok()).toBe(true);
  const manifestBytes = await manifestResponse.body();
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  expect(manifest.distribution_contract).toBe("lmdj.creator-web.distribution.v1");
  expect(manifest.compatible_hosts).toEqual(
    WEB_RUNTIME_IDENTITY.hosts["creator-web"].compatible_hosts,
  );
  // capture_worklet ships as its own same-origin asset because the CSP below
  // (script-src 'self') rejects blob:/data: AudioWorklet module URLs.
  // perform_master_tap_worklet joins the inventory at Product Build 1.0.42.0 and
  // ships same-origin for the same reason as capture_worklet.
  expect(manifest.assets.map(({role}) => role)).toEqual([
    "host_main", "runtime_script", "runtime_wasm", "host_style", "capture_worklet",
    "perform_master_tap_worklet",
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
    await expect(page.getByRole("button", {name: /^Pad A\d+ — empty — Key [QWERTYUIASDFGHJK]$/}))
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
    const pads = page.getByRole("button", {name: /^Pad A\d+ — assigned — Key [QWERTYUIASDFGHJK]$/});
    await expect(pads).toHaveCount(16);
    for (let index = 0; index < 16; index += 1) {
      const box = await pads.nth(index).boundingBox();
      expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
    await expect(page.getByRole("button", {name: "Sample"})).toBeEnabled();
    await expect(page.getByRole("button", {name: "Sequence"})).toBeEnabled();
    // The walk below depends on Sound Sets being tabbable, and `mode_rail.tsx`
    // gives it `disabled={!soundSetEnabled}`. Without this line a regression
    // that disables it would surface as an off-by-one tab-order diff -- the
    // very shape that made #977 read as a Creator defect. Assert the
    // precondition so that failure names itself instead.
    await expect(page.getByRole("button", {name: "Sound Sets"})).toBeEnabled();
    await expect(page.getByRole("button", {name: /^Perform/})).toBeEnabled();
    await page.getByRole("button", {name: "Activate audio"}).focus();
    const focusOrder = [];
    for (let index = 0; index < 7; index += 1) {
      await page.keyboard.press("Tab");
      // Mode buttons carry a decorative glyph before their label; read the
      // label so the order does not depend on the glyph set.
      focusOrder.push(await page.evaluate(() => {
        const active = document.activeElement;
        return (active?.querySelector(".mode-label") ?? active)?.textContent?.trim();
      }));
    }
    // The window is the whole rail, not a prefix of it. Product Build
    // 1.0.42.0 activated Perform, which joined the tab order after Sample;
    // Stage 11 Task 5 (#846) then inserted Sound Sets between them, and the
    // six-stop window read at Stage 10 by #664 (`0ffa77c0`) silently dropped
    // Perform off the end -- so the case failed reporting `Sound Sets` where
    // it expected `Perform`, and read as a Creator defect when the rail was
    // right. Asserting the full rail means the next insertion changes the
    // expected list rather than shifting what the loop can see (#977).
    expect(focusOrder).toEqual([
      "Enable MIDI", "Export report", "Project", "Sequence", "Sample",
      "Sound Sets", "Perform",
    ]);
    await page.getByRole("button", {name: "Sample"}).click();
    await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
    const picker = page.locator("input.sample-file-input");
    await expect(picker).toHaveCount(1);
    await expect(picker).toHaveAttribute(
      "accept",
      ".wav,.mp3,.m4a,.aac,.flac,audio/wav,audio/wave,audio/mpeg,audio/mp4,audio/aac,audio/flac",
    );
    const samplePads = page.getByRole("button", {name: /^Pad A\d+ — assigned$/});
    await expect(samplePads).toHaveCount(16);
    for (let index = 0; index < 16; index += 1) {
      const box = await samplePads.nth(index).boundingBox();
      expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
    expect(await page.evaluate(() =>
      document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    )).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`creator-sample-${viewport.width}x${viewport.height}.png`),
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
