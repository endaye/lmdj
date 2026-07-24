import { expect, test, type Locator, type Page } from "@playwright/test";

const VIEWPORTS = [
  { name: "desktop-wide", width: 1440, height: 900 },
  { name: "desktop-compact", width: 1280, height: 720 },
  { name: "landscape-tablet", width: 1024, height: 768 },
  { name: "portrait-tablet", width: 768, height: 1024 },
  { name: "phone", width: 390, height: 844 },
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
  await page.mouse.move(0, 0);
}

for (const viewport of VIEWPORTS) {
  test(`${viewport.name} ${viewport.width}x${viewport.height} keeps the instrument usable`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await openExampleWithMissingAsset(page);

    const matrix = page.getByTestId("pad-matrix");
    const pads = matrix.locator("[data-pad-index]");
    await expect(pads).toHaveCount(16);

    const layout = await matrix.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        columns: style.gridTemplateColumns.split(" ").filter(Boolean).length,
        rowGap: Number.parseFloat(style.rowGap),
        columnGap: Number.parseFloat(style.columnGap),
      };
    });
    const expectedColumns = viewport.width >= 960 ? 8 : 4;
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

    const inspectorBox = await box(page.getByTestId("context-inspector"));
    const statusBox = await box(page.getByTestId("status-bar"));
    for (const padBox of boxes) {
      expect(overlaps(inspectorBox, padBox)).toBe(false);
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
    await expect(inspectorContent).toHaveAttribute("data-inspector-accent", "bass");
    await expect.poll(
      () => inspectorHeader.evaluate((element) => getComputedStyle(element).backgroundColor),
    ).not.toBe(initialInspectorStyle.backgroundColor);
    const selectedSignature = await visualSignature(selected);
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
