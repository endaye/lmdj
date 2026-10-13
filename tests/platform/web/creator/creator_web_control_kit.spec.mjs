import {writeFile} from "node:fs/promises";
import {expect, test} from "@playwright/test";
import {overviewProjectId, waitForBootProject, waitForProjectReopen} from "./fixtures/creator_boot.mjs";

const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

const viewports = [
  {width: 1440, height: 900, layout: "full", rotated: false},
  {width: 1024, height: 768, layout: "full", rotated: false},
  {width: 1280, height: 600, layout: "compact", rotated: false},
  {width: 768, height: 600, layout: "compact", rotated: false},
  {width: 768, height: 900, layout: "compact", rotated: false},
  {width: 768, height: 1024, layout: "full", rotated: true},
];

async function geometry(page) {
  return page.evaluate(() => {
    const workspace = document.querySelector(".hardware-workspace");
    const console = document.querySelector(".hardware-console");
    const touch = console.querySelector('[aria-label="Touch workspace"]');
    const transform = new DOMMatrix(getComputedStyle(workspace).transform);
    const local = element => ({x: element.offsetLeft, y: element.offsetTop,
      width: element.offsetWidth, height: element.offsetHeight});
    const buttons = [...console.querySelectorAll(
      '[aria-label="Physical controls"] button, [aria-label="Pad matrix"] button, .sample-page-nav button',
    )];
    return {
      layout: document.documentElement.dataset.creatorLayout,
      scale: Math.hypot(transform.a, transform.b), rotated: transform.b < 0,
      horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
      stage: document.querySelector("#root").getBoundingClientRect().toJSON(),
      console: {...local(console), rect: console.getBoundingClientRect().toJSON()},
      regions: [...console.children].map(local),
      touchOverflow: touch.scrollWidth - touch.clientWidth,
      targets: buttons.map(button => {
        const rect = button.getBoundingClientRect();
        // Probe actual exposed target edges, including the unpainted inset.
        // A transformed or overlapping box with the right width alone fails.
        const points = [[rect.width / 2, 1], [rect.width / 2, rect.height - 1],
          [1, rect.height / 2], [rect.width - 1, rect.height / 2],
          [rect.width / 2, rect.height / 2]];
        return {name: button.getAttribute("aria-label") ?? button.textContent,
          rect: rect.toJSON(), disabled: button.disabled,
          hits: points.map(([x, y]) => document.elementFromPoint(rect.x + x, rect.y + y)
            ?.closest("button") === button)};
      }),
    };
  });
}

async function expectGeometry(page, viewport) {
  await expect(page.locator("html")).toHaveAttribute("data-creator-layout", viewport.layout);
  const measured = await geometry(page);
  expect(measured.rotated).toBe(viewport.rotated);
  expect(measured.scale).toBeGreaterThanOrEqual(1);
  expect(measured.horizontalOverflow).toBe(0);
  expect(measured.touchOverflow).toBe(0);
  const compact = viewport.layout === "compact";
  const width = compact ? Math.min(880, viewport.width - 16) : 880;
  expect(measured.console).toMatchObject({width, height: compact ? 544 : 592});
  expect(measured.regions).toEqual(compact ? [
    {x: 8, y: 8, width: 92, height: 528},
    {x: 108, y: 8, width: width - 116, height: 152},
    {x: 108, y: 168, width: width - 492, height: 368},
    {x: width - 376, y: 168, width: 368, height: 368},
  ] : [
    {x: 16, y: 16, width: 80, height: 560},
    {x: 112, y: 16, width: 752, height: 176},
    {x: 112, y: 208, width: 368, height: 368},
    {x: 496, y: 208, width: 368, height: 368},
  ]);
  const {rect} = measured.console, {stage} = measured;
  expect(rect.left).toBeGreaterThanOrEqual(stage.left);
  expect(rect.top).toBeGreaterThanOrEqual(stage.top);
  expect(rect.right).toBeLessThanOrEqual(stage.right);
  expect(rect.bottom).toBeLessThanOrEqual(stage.bottom);
  expect(Math.abs(rect.left + rect.width / 2 - stage.left - stage.width / 2)).toBeLessThanOrEqual(1);
  expect(Math.abs(rect.top + rect.height / 2 - stage.top - stage.height / 2)).toBeLessThanOrEqual(1);
  if (compact) {
    expect(measured.scale).toBe(1);
    expect(rect.left - stage.left).toBeGreaterThanOrEqual(8);
    expect(stage.right - rect.right).toBeGreaterThanOrEqual(8);
    expect(rect.top - stage.top).toBeGreaterThanOrEqual(4);
    expect(stage.bottom - rect.bottom).toBeGreaterThanOrEqual(4);
  }
  // 20 rail controls + 16 Pads + the four existing Sample page actions.
  expect(measured.targets).toHaveLength(40);
  for (const target of measured.targets) {
    expect(target.rect.width, target.name).toBeGreaterThanOrEqual(44);
    expect(target.rect.height, target.name).toBeGreaterThanOrEqual(44);
    expect(target.hits, target.name).toEqual([true, true, true, true, true]);
  }
  for (let i = 0; i < measured.targets.length; i++) {
    for (const b of measured.targets.slice(i + 1)) {
      const a = measured.targets[i];
      const overlap = Math.max(0, Math.min(a.rect.right, b.rect.right) - Math.max(a.rect.left, b.rect.left)) *
        Math.max(0, Math.min(a.rect.bottom, b.rect.bottom) - Math.max(a.rect.top, b.rect.top));
      expect(overlap, `${a.name} / ${b.name}`).toBe(0);
    }
  }
  return measured;
}

test.beforeEach(async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  await waitForBootProject(page);
});

for (const viewport of viewports) {
  test(`exposes nonoverlapping 44px targets at ${viewport.width}×${viewport.height}`, async ({page}, testInfo) => {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    await page.getByTestId("physical-controls").getByRole("button", {name: "Sample", exact: true}).click();
    await page.getByTestId("touch-workspace").evaluate(element => { element.scrollTop = 0; });
    const measured = await expectGeometry(page, viewport);
    const receipt = testInfo.outputPath("control-geometry.json");
    await writeFile(receipt, JSON.stringify(measured, null, 2));
    await testInfo.attach("control-geometry", {path: receipt, contentType: "application/json"});
    const screenshot = testInfo.outputPath("control-kit.png");
    await page.screenshot({path: screenshot});
    await testInfo.attach("control-kit", {path: screenshot, contentType: "image/png"});

    // Native pointer activation in a rail key's unpainted target inset.
    const key = page.getByTestId("physical-controls").getByRole("button", {name: "Project", exact: true});
    const box = await key.boundingBox();
    await page.mouse.click(box.x + 2, box.y + box.height / 2);
    await expect(key).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", {name: /^Project [0-9a-f]{8}$/})).toBeVisible();
  });
}

test("viewport round trips and an asynchronous Runtime boot remount retain geometry", async ({page}) => {
  const id = await overviewProjectId(page).innerText();
  // Cross both width/orientation and height thresholds in both directions.
  for (const viewport of [...viewports, ...viewports.toReversed()]) {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    await page.getByTestId("physical-controls").getByRole("button", {name: "Sample", exact: true}).click();
    await page.getByTestId("touch-workspace").evaluate(element => { element.scrollTop = 0; });
    await expectGeometry(page, viewport);
  }
  const compact = viewports[3];
  await page.setViewportSize({width: compact.width, height: compact.height});
  await page.reload();
  await waitForProjectReopen(page, id);
  await page.getByTestId("physical-controls").getByRole("button", {name: "Sample", exact: true}).click();
  await page.getByTestId("touch-workspace").evaluate(element => { element.scrollTop = 0; });
  await expectGeometry(page, compact);
});

test("ordinary touch actions preserve a usable unpainted inset and keyboard focus", async ({page}) => {
  // The owned proof server deliberately has no Catalog. Import a real assigned
  // Sample through the ordinary UI before asserting its playback/tone controls.
  await page.getByTestId("physical-controls").getByRole("button", {name: "Project", exact: true}).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj", exact: true}).click();
  await (await chooser).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000", exact: true})).toBeVisible();
  await page.getByTestId("physical-controls").getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("button", {name: /^Pad A01 — assigned/})).toBeVisible();
  const pages = page.getByRole("navigation", {name: "Sample pages"});
  const playback = pages.getByRole("button", {name: "Playback", exact: true});
  await playback.scrollIntoViewIfNeeded();
  const geometry = await playback.evaluate(element => {
    const box = element.getBoundingClientRect();
    const scale = box.height / element.offsetHeight;
    const inset = parseFloat(getComputedStyle(element, "::before").top) * scale;
    const x = box.x + box.width / 2, y = box.y + inset / 2;
    return {width: box.width, height: box.height, x, y,
      hit: document.elementFromPoint(x, y)?.closest("button") === element};
  });
  expect(geometry.width).toBeGreaterThanOrEqual(44);
  expect(geometry.height).toBeGreaterThanOrEqual(44);
  expect(geometry.hit).toBe(true);
  // This genuine pointer action is outside the painted face. It must invoke
  // the same existing navigation action, with a far-side visible result.
  await page.mouse.click(geometry.x, geometry.y);
  await expect(playback).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("slider", {name: /^Pad A\d+ Volume$/})).toBeVisible();
  await playback.focus();
  await page.keyboard.press("Tab");
  const focused = pages.getByRole("button", {name: "Tone / EQ", exact: true});
  await expect(focused).toBeFocused();
  await expect(focused).toHaveCSS("outline-style", "solid");
  await expect(focused).toHaveCSS("outline-width", "3px");
  await page.keyboard.press("Enter");
  await expect(focused).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("slider", {name: /^Pad A\d+ Tone$/})).toBeVisible();
});

test("Grid Tools consumes the shared face and states inside its existing modal", async ({page}, testInfo) => {
  await page.getByTestId("physical-controls").getByRole("button", {name: "Sequence", exact: true}).click();
  const trigger = page.getByRole("button", {name: "Grid tools", exact: true});
  for (const viewport of [viewports[0], viewports[3]]) {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    await trigger.click();
    const dialog = page.getByRole("dialog", {name: "Grid tools", exact: true});
    const buttons = await dialog.getByRole("button").evaluateAll(elements => elements.map(element => {
      const style = getComputedStyle(element), face = getComputedStyle(element, "::before");
      return {name: element.getAttribute("aria-label") ?? element.textContent,
        selected: element.getAttribute("aria-pressed") === "true",
        primary: element.classList.contains("is-primary"),
        rect: element.getBoundingClientRect().toJSON(), face: parseFloat(face.height),
        radius: face.borderRadius, font: style.fontFamily, size: style.fontSize,
        leading: style.lineHeight, fill: face.backgroundColor, color: style.color,
        outline: face.borderTopColor};
    }));
    expect(buttons).toHaveLength(8);
    expect(buttons.filter(button => button.selected)).toHaveLength(2);
    expect(buttons.filter(button => button.primary)).toHaveLength(1);
    for (const button of buttons) {
      expect(button.rect.width, button.name).toBeGreaterThanOrEqual(44);
      expect(button.rect.height, button.name).toBeGreaterThanOrEqual(44);
      expect(button.face).toBe(32);
      expect(button.radius).toBe("6px");
      expect(button.font).toMatch(/^"IBM Plex Mono"/);
      expect(button.size).toBe("9px");
      expect(button.leading).toBe("13px");
      expect(button.fill).toBe(button.primary ? "rgb(221, 244, 120)"
        : button.selected ? "rgb(41, 45, 41)" : "rgb(52, 58, 52)");
      expect(button.color).toBe(button.primary ? "rgb(32, 37, 28)"
        : button.selected ? "rgb(221, 244, 120)" : "rgb(241, 242, 233)");
      if (button.selected) expect(button.outline).toBe("rgb(221, 244, 120)");
    }
    const screenshot = testInfo.outputPath(`grid-tools-${viewport.width}x${viewport.height}.png`);
    await dialog.screenshot({path: screenshot});
    await testInfo.attach(`grid-tools-${viewport.width}x${viewport.height}`, {path: screenshot, contentType: "image/png"});
    await dialog.getByRole("button", {name: "Done", exact: true}).click();
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  }
});

test("the shared five-state palette preserves native disabled behavior", async ({page}) => {
  // A CSS component fixture uses the production class and stylesheet. It
  // checks the reusable Danger hook before page Tasks adopt it; it does not
  // claim an implemented destructive product action or rewrite live controls.
  await page.evaluate(() => {
    const fixture = document.createElement("dialog");
    fixture.id = "control-kit-states";
    for (const state of ["Secondary", "Primary", "Selected", "Danger", "Disabled"]) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `touch-control${state === "Primary" ? " is-primary" : state === "Danger" ? " is-danger" : ""}`;
      button.textContent = state;
      if (state === "Selected") button.setAttribute("aria-pressed", "true");
      button.disabled = state === "Disabled";
      button.addEventListener("click", () => fixture.setAttribute("data-clicked", state));
      fixture.append(button);
    }
    document.body.append(fixture);
    fixture.showModal();
  });
  const fixture = page.locator("#control-kit-states");
  const palette = await fixture.locator("button").evaluateAll(buttons => buttons.map(button => {
    const face = getComputedStyle(button, "::before");
    const style = getComputedStyle(button);
    return {label: button.textContent, fill: face.backgroundColor, text: style.color,
      line: face.borderTopColor, opacity: style.opacity, face: parseFloat(face.height)};
  }));
  expect(palette).toEqual([
    {label: "Secondary", fill: "rgb(52, 58, 52)", text: "rgb(241, 242, 233)", line: "rgba(0, 0, 0, 0)", opacity: "1", face: 32},
    {label: "Primary", fill: "rgb(221, 244, 120)", text: "rgb(32, 37, 28)", line: "rgba(0, 0, 0, 0)", opacity: "1", face: 32},
    {label: "Selected", fill: "rgb(41, 45, 41)", text: "rgb(221, 244, 120)", line: "rgb(221, 244, 120)", opacity: "1", face: 32},
    {label: "Danger", fill: "rgb(52, 58, 52)", text: "rgb(229, 173, 196)", line: "rgba(0, 0, 0, 0)", opacity: "1", face: 32},
    {label: "Disabled", fill: "rgb(52, 58, 52)", text: "rgb(241, 242, 233)", line: "rgba(0, 0, 0, 0)", opacity: "0.4", face: 32},
  ]);
  const disabled = fixture.getByRole("button", {name: "Disabled", exact: true});
  await expect(disabled).toBeDisabled();
  const box = await disabled.boundingBox();
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(fixture).not.toHaveAttribute("data-clicked");
  await fixture.getByRole("button", {name: "Danger", exact: true}).focus();
  await page.keyboard.press("Tab");
  await expect(disabled).not.toBeFocused();
});
