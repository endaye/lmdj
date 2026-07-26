import { expect, test, type Locator, type Page } from "@playwright/test";

const VIEWPORTS = [
  { name: "desktop-wide", width: 1440, height: 900 },
  { name: "desktop-compact", width: 1280, height: 720 },
  { name: "landscape-tablet", width: 1024, height: 768 },
  { name: "portrait-tablet", width: 768, height: 1024 },
  { name: "phone", width: 390, height: 844 },
] as const;

const SHELL_BREAKPOINTS = [
  { name: "wide", width: 1280, layout: "wide" },
  { name: "compact-wide-start", width: 960, layout: "compact-wide" },
  { name: "compact-wide-end", width: 1279, layout: "compact-wide" },
  { name: "tablet-start", width: 600, layout: "tablet" },
  { name: "tablet-end", width: 959, layout: "tablet" },
  { name: "nested-narrow", width: 676, layout: "tablet" },
  { name: "phone-start", width: 360, layout: "phone" },
  { name: "phone-end", width: 599, layout: "phone" },
] as const;

type Box = { x: number; y: number; width: number; height: number };

function overlaps(a: Box, b: Box): boolean {
  return a.x < b.x + b.width
    && a.x + a.width > b.x
    && a.y < b.y + b.height
    && a.y + a.height > b.y;
}

async function box(locator: Locator): Promise<Box> {
  const value = await locator.boundingBox();
  expect(value).not.toBeNull();
  return value!;
}

async function visualSignature(locator: Locator): Promise<string> {
  return locator.evaluate((element) => {
    const style = getComputedStyle(element);
    return [
      style.backgroundColor,
      style.borderColor,
      style.borderStyle,
      style.boxShadow,
      style.outlineStyle,
      style.outlineWidth,
      style.transform,
      style.filter,
    ].join("|");
  });
}

async function openExampleWithMissingAsset(page: Page): Promise<void> {
  // The product remains contract-pure: a 404 makes loadPatch mark the referenced
  // Patch element missing; the test does not inject view-only Pad data.
  await page.route("**/example-patch/samples/melody_a.wav", (route) =>
    route.fulfill({ status: 404, body: "missing for responsive state gate" }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: /加载示例 patch/i }).click();
  await expect(page.getByTestId("pad-matrix")).toBeVisible();
  // A loaded Patch auto-reveals the Chameleon once and collapses it after
  // 4000ms, which re-flows the reserved assistant strip in the App Bar. These
  // instrument-layout assertions predate the assistant, so dismiss the reveal
  // up front and measure a settled shell. Assistant clearance itself is
  // covered by e2e/chameleon-exhibition.spec.ts.
  await page.getByRole("button", { name: "Close assistant" }).click();
  await expect(page.getByTestId("app-bar")).toHaveAttribute(
    "data-assistant-open",
    "false",
  );
  await page.mouse.move(0, 0);
}

async function setShellWidth(shell: Locator, width: number): Promise<void> {
  await shell.evaluate((element, exactWidth) => {
    const shellElement = element as HTMLElement;
    const style = getComputedStyle(shellElement);
    const borderInline =
      Number.parseFloat(style.borderLeftWidth) +
      Number.parseFloat(style.borderRightWidth);
    shellElement.style.width = `${exactWidth + borderInline}px`;
    shellElement.style.maxWidth = "none";
  }, width);
  await expect(shell).toHaveAttribute(
    "data-layout",
    width >= 1280
      ? "wide"
      : width >= 960
        ? "compact-wide"
        : width >= 600
          ? "tablet"
          : "phone",
  );
  expect(await shell.evaluate((element) => element.clientWidth)).toBe(width);
}

test("Source file chooser is the Chameleon, not a bare native input", async ({
  page,
}) => {
  await page.goto("/");

  // The Gallery Stage replaced the visible native file picker: the character
  // itself is the accessible upload control and the input stays hidden, so the
  // old ::file-selector-button colour is no longer a real product surface.
  const input = page.getByTestId("api-file-input");
  await expect(input).toBeHidden();
  await expect(input).toHaveAttribute(
    "accept",
    ".wav,.mp3,audio/wav,audio/mpeg",
  );

  const trigger = page.getByRole("button", {
    name: "Choose a WAV or MP3 to make a Patch",
  });
  await expect(trigger).toBeVisible();
  await expect(trigger).toHaveCSS("color", "rgb(17, 17, 15)");
});

for (const breakpoint of SHELL_BREAKPOINTS) {
  test(`${breakpoint.name} ${breakpoint.width}px uses the specified responsive shell`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await openExampleWithMissingAsset(page);

    const shell = page.getByTestId("workbench-shell");
    await setShellWidth(shell, breakpoint.width);
    const appBar = page.getByTestId("app-bar");
    const tools = page.getByTestId("creator-tools");
    const canvas = page.getByTestId("instrument-canvas");
    const inspector = page.getByTestId("context-inspector");
    const toggle = page.getByTestId("inspector-toggle");
    const status = page.getByTestId("status-bar");
    const shellBox = await box(shell);
    const appBarBox = await box(appBar);
    const toolsBox = await box(tools);
    const canvasBox = await box(canvas);
    const statusBox = await box(status);

    if (breakpoint.layout === "wide") {
      await expect(toggle).toBeHidden();
      await expect(inspector).toBeVisible();
      const inspectorBox = await box(inspector);
      expect(toolsBox.x + toolsBox.width).toBeLessThanOrEqual(canvasBox.x);
      expect(canvasBox.x + canvasBox.width).toBeLessThanOrEqual(inspectorBox.x);
      expect(inspectorBox.x + inspectorBox.width).toBeLessThanOrEqual(
        shellBox.x + shellBox.width,
      );
      await expect(
        tools.getByRole("button", { name: "Performance" }),
      ).toContainText("Performance");
      return;
    }

    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toHaveAttribute(
      "aria-controls",
      "workbench-context-inspector",
    );
    await expect(inspector).toBeHidden();

    if (breakpoint.layout === "compact-wide") {
      expect(toolsBox.x + toolsBox.width).toBeLessThanOrEqual(canvasBox.x);
      const performance = tools.getByRole("button", { name: "Performance" });
      await expect(performance).toHaveAccessibleName("Performance");
      await expect(performance.locator(".creator-tool-rail__text")).toBeHidden();
    } else {
      expect(toolsBox.y).toBeGreaterThanOrEqual(canvasBox.y + canvasBox.height);
      expect(toolsBox.y + toolsBox.height).toBeLessThanOrEqual(statusBox.y);
      expect(toolsBox.width).toBeGreaterThanOrEqual(canvasBox.width - 1);
    }

    if (breakpoint.layout === "phone") {
      expect(appBarBox.height).toBeLessThanOrEqual(58);
      await expect(appBar).toHaveAttribute("data-compact", "true");
    } else {
      await expect(appBar).toHaveAttribute("data-compact", "false");
    }

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(inspector).toBeVisible();
    const backdrop = page.getByTestId("inspector-backdrop");
    const close = page.getByTestId("inspector-close");
    await expect(backdrop).toBeVisible();
    await expect(backdrop).toHaveAttribute("tabindex", "-1");
    await expect(close).toBeFocused();
    for (const inertRegion of [appBar, tools, canvas, status]) {
      await expect(inertRegion).toHaveAttribute("inert", "");
    }
    await page.keyboard.press("Tab");
    await expect(close).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(close).toBeFocused();
    const inspectorBox = await box(inspector);
    expect(overlaps(inspectorBox, canvasBox)).toBe(true);
    if (breakpoint.layout === "phone") {
      const contentBox = await box(page.getByTestId("workbench-content"));
      expect(inspectorBox.width).toBeGreaterThanOrEqual(contentBox.width - 1);
      expect(inspectorBox.height).toBeGreaterThanOrEqual(contentBox.height - 1);
    }

    await page.keyboard.press("Escape");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(inspector).toBeHidden();
    await expect(toggle).toBeFocused();
    for (const inertRegion of [appBar, tools, canvas, status]) {
      await expect(inertRegion).not.toHaveAttribute("inert", "");
    }

    await toggle.click();
    await page.getByTestId("inspector-backdrop").click({ position: { x: 2, y: 2 } });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(inspector).toBeHidden();
    await expect(toggle).toBeFocused();
  });
}

for (const viewport of VIEWPORTS) {
  test(`${viewport.name} ${viewport.width}x${viewport.height} keeps the instrument usable`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await openExampleWithMissingAsset(page);

    const matrix = page.getByTestId("pad-matrix");
    const pads = matrix.locator("[data-pad-index]");
    const shell = page.getByTestId("workbench-shell");
    const shellWidth = (await box(shell)).width;
    await expect(pads).toHaveCount(16);

    const layout = await matrix.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        columns: style.gridTemplateColumns.split(" ").filter(Boolean).length,
        rowGap: Number.parseFloat(style.rowGap),
        columnGap: Number.parseFloat(style.columnGap),
      };
    });
    const expectedColumns = shellWidth >= 960 ? 8 : 4;
    expect(layout.columns).toBe(expectedColumns);
    if (expectedColumns === 4) expect(layout.rowGap).toBe(layout.columnGap);

    await page.evaluate(() => document.fonts.ready);
    const boxes = await pads.evaluateAll((elements) =>
      elements.map((element) => {
        const bounds = element.getBoundingClientRect();
        return {
          x: bounds.x,
          y: bounds.y,
          width: bounds.width,
          height: bounds.height,
        };
      }),
    );
    for (const padBox of boxes) {
      expect(Math.abs(padBox.width - padBox.height)).toBeLessThanOrEqual(1);
    }
    for (let left = 0; left < boxes.length; left += 1) {
      for (let right = left + 1; right < boxes.length; right += 1) {
        expect(overlaps(boxes[left], boxes[right])).toBe(false);
      }
    }
    const rowTops = new Set(boxes.map((padBox) => Math.round(padBox.y)));
    expect(rowTops.size).toBe(16 / expectedColumns);

    const patternBox = await box(page.getByTestId("pattern-surface"));
    const firstRowTop = Math.min(...boxes.slice(0, expectedColumns).map((padBox) => padBox.y));
    expect(patternBox.y + patternBox.height).toBeLessThanOrEqual(firstRowTop);

    const inspector = page.getByTestId("context-inspector");
    const inspectorToggle = page.getByTestId("inspector-toggle");
    if (shellWidth < 1280) {
      await inspectorToggle.click();
      await expect(inspectorToggle).toHaveAttribute("aria-expanded", "true");
    }
    const inspectorBox = await box(inspector);
    const statusBox = await box(page.getByTestId("status-bar"));
    if (shellWidth >= 1280) {
      for (const padBox of boxes) {
        expect(overlaps(inspectorBox, padBox)).toBe(false);
      }
    } else {
      expect(boxes.some((padBox) => overlaps(inspectorBox, padBox))).toBe(true);
    }
    for (const padBox of boxes) {
      expect(overlaps(statusBox, padBox)).toBe(false);
    }
    if (viewport.width <= 620) {
      const headingTitle = await box(page.locator(".workbench-canvas-heading > div > span"));
      const headingMeta = await box(page.locator(".workbench-canvas-heading > div > small"));
      expect(overlaps(headingTitle, headingMeta)).toBe(false);
    }

    const lastPad = pads.nth(15);
    await lastPad.scrollIntoViewIfNeeded();
    await expect(lastPad).toBeInViewport();
    const lastBox = await box(lastPad);
    const currentStatusBox = await box(page.getByTestId("status-bar"));
    expect(overlaps(lastBox, currentStatusBox)).toBe(false);

    const inspectorContent = page.getByTestId("context-inspector-content");
    const inspectorHeader = page.getByTestId("context-inspector-header");
    const initialInspectorStyle = await inspectorHeader.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        backgroundColor: style.backgroundColor,
        transitionProperty: style.transitionProperty,
        transitionDuration: style.transitionDuration,
      };
    });
    expect(initialInspectorStyle.transitionProperty.split(", ")).toContain("background-color");
    expect(initialInspectorStyle.transitionDuration).toBe("0.16s");
    if (shellWidth < 1280) {
      await page.getByTestId("inspector-close").click();
      await expect(inspector).toBeHidden();
    }

    await pads.nth(4).focus();
    await page.keyboard.press("Tab");
    const focused = pads.nth(5);
    await expect(focused).toBeFocused();
    const focusStyle = await focused.evaluate((element) => {
      const style = getComputedStyle(element);
      return { outlineStyle: style.outlineStyle, outlineWidth: Number.parseFloat(style.outlineWidth) };
    });
    expect(focusStyle.outlineStyle).toBe("solid");
    expect(focusStyle.outlineWidth).toBeGreaterThan(0);
    const focusSignature = await visualSignature(focused);

    const selected = pads.nth(1);
    await selected.click();
    await expect(selected).toHaveAttribute("data-visual-state", "playing");
    const playingSignature = await visualSignature(selected);
    await expect(selected).toHaveAttribute("data-visual-state", "selected");
    if (shellWidth < 1280) {
      await inspectorToggle.click();
      await expect(inspector).toBeVisible();
    }
    await expect(inspectorContent).toHaveAttribute("data-inspector-accent", "bass");
    await expect.poll(
      () => inspectorHeader.evaluate((element) => getComputedStyle(element).backgroundColor),
    ).not.toBe(initialInspectorStyle.backgroundColor);
    const selectedSignature = await visualSignature(selected);
    if (shellWidth < 1280) {
      await page.getByTestId("inspector-close").click();
    }
    await selected.focus();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(selected).toBeFocused();
    expect(await selected.evaluate((element) => element.matches(":focus-visible"))).toBe(true);
    const selectedFocusSignature = await visualSignature(selected);
    expect(selectedFocusSignature).not.toBe(selectedSignature);
    expect(selectedFocusSignature).not.toBe(focusSignature);

    const empty = pads.nth(8);
    await expect(empty).toHaveAttribute("data-visual-state", "empty");
    const emptySignature = await visualSignature(empty);

    const missing = pads.nth(2);
    await expect(missing).toHaveAttribute("data-visual-state", "missing");
    const missingSignature = await visualSignature(missing);

    expect(new Set([
      focusSignature,
      selectedFocusSignature,
      playingSignature,
      selectedSignature,
      emptySignature,
      missingSignature,
    ]).size).toBe(6);

    if (viewport.name === "phone") {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await pads.nth(0).click();
      await expect(pads.nth(0)).toHaveAttribute("data-visual-state", "playing");
      await expect(pads.nth(0)).toContainText("PLAYING");
      expect(await pads.nth(0).evaluate((element) => getComputedStyle(element).transform)).toBe("none");
      expect(
        await inspectorHeader.evaluate((element) => getComputedStyle(element).transitionDuration),
      ).toBe("0s");
    }
  });
}

for (const viewport of [
  { name: "compact-wide-opposite-side", width: 1024, height: 768 },
  { name: "tablet-opposite-side", width: 768, height: 1024 },
] as const) {
  test(`${viewport.name} keeps the selected Pad clear of the Inspector drawer`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await openExampleWithMissingAsset(page);

    const shell = page.getByTestId("workbench-shell");
    const pads = page.getByTestId("pad-matrix").locator("[data-pad-index]");
    const inspector = page.getByTestId("context-inspector");
    const toggle = page.getByTestId("inspector-toggle");

    const playableLeftPad = pads.nth(1);
    await playableLeftPad.click();
    await expect(playableLeftPad).toHaveAttribute("data-visual-state", "playing");
    await expect(playableLeftPad).toHaveAttribute("data-visual-state", "selected");
    await toggle.click();
    await expect(inspector).toHaveAttribute("data-side", "right");
    await expect(page.getByTestId("context-inspector-header")).toContainText(
      "Pad 02 · bass",
    );
    expect(overlaps(await box(inspector), await box(playableLeftPad))).toBe(false);
    expect((await box(inspector)).width).toBeLessThanOrEqual((await box(shell)).width / 2 + 1);
    await page.keyboard.press("Escape");

    const rightPadIndex = 7;
    const rightPad = pads.nth(rightPadIndex);
    await page.keyboard.press("8");
    await expect(rightPad).toHaveAttribute("data-visual-state", "selected");
    await toggle.click();
    await expect(inspector).toHaveAttribute("data-side", "left");
    await expect(page.getByTestId("context-inspector-header")).toContainText(
      `Pad ${String(rightPadIndex + 1).padStart(2, "0")}`,
    );
    await expect.poll(async () =>
      overlaps(await box(inspector), await box(rightPad)),
    ).toBe(false);
    expect((await box(inspector)).width).toBeLessThanOrEqual((await box(shell)).width / 2 + 1);
  });
}

test("phone Sheet preserves selection, playback, and creator mode state", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openExampleWithMissingAsset(page);

  const pad = page.getByTestId("pad-0");
  await pad.click();
  await expect(pad).toHaveAttribute("data-visual-state", "selected");
  await page.getByTestId("play-toggle").click();
  await expect(page.getByTestId("play-toggle")).toHaveText("■");
  const sourceMode = page.getByRole("button", { name: "Source" });
  const performanceMode = page.getByRole("button", { name: "Performance" });
  const toggle = page.getByTestId("inspector-toggle");
  await toggle.click();
  await expect(page.getByTestId("context-inspector")).toBeVisible();
  await expect(page.getByTestId("context-inspector-header")).toContainText(
    "Pad 01 · kick",
  );
  await page.getByTestId("inspector-close").click();

  await expect(pad).toHaveAttribute("data-visual-state", "selected");
  await expect(page.getByTestId("play-toggle")).toHaveText("■");
  await expect(performanceMode).toHaveAttribute("aria-pressed", "true");

  await sourceMode.click();
  await expect(sourceMode).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("loaded-source-panel")).toContainText(
    "已加载来源",
  );
  await expect(page.getByTestId("loaded-source-panel")).toContainText(
    "Example package",
  );
  await expect(page.getByTestId("pad-matrix")).toBeHidden();

  await performanceMode.click();
  await expect(performanceMode).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("pad-0")).toHaveAttribute(
    "data-visual-state",
    "selected",
  );
  await expect(page.getByTestId("play-toggle")).toHaveText("■");

  const exportMode = page.getByRole("button", { name: "Export" });
  await exportMode.click();
  await expect(exportMode).toHaveAttribute("aria-pressed", "true");
  await toggle.click();
  await expect(page.getByTestId("context-inspector")).toBeVisible();
  await expect(page.getByTestId("export-unavailable")).toContainText("Example");
  await page.getByTestId("inspector-close").click();

  await expect(pad).toHaveAttribute("data-visual-state", "selected");
  await expect(page.getByTestId("play-toggle")).toHaveText("■");
  await expect(exportMode).toHaveAttribute("aria-pressed", "true");
});
