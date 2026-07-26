import { expect, test, type Locator, type Page } from "@playwright/test";

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const value = await locator.boundingBox();
  expect(value).not.toBeNull();
  return value!;
}

function overlaps(a: Box, b: Box): boolean {
  return (
    a.x < b.x + b.width
    && a.x + a.width > b.x
    && a.y < b.y + b.height
    && a.y + a.height > b.y
  );
}

async function openReadyPatch(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: /加载示例 patch/i }).click();
  await expect(page.getByTestId("pad-matrix")).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Chameleon assistant · Patch ready",
    }),
  ).toHaveAttribute("aria-expanded", "true");
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
]) {
  test(`${viewport.width}px keeps Chameleon out of Creator controls`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await openReadyPatch(page);

    const floating = await box(page.getByTestId("chameleon-floating"));
    const content = await box(page.getByTestId("workbench-content"));
    const matrix = await box(page.getByTestId("pad-matrix"));
    const status = await box(page.getByTestId("status-bar"));

    expect(overlaps(floating, content)).toBe(false);
    expect(overlaps(floating, matrix)).toBe(false);
    expect(overlaps(floating, status)).toBe(false);
  });
}

test("Gallery keeps the main character and version edition mark separate", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const character = await box(page.getByTestId("chameleon-stage-trigger"));
  const version = await box(page.getByTestId("app-version"));
  expect(overlaps(character, version)).toBe(false);
  await expect(
    page.getByRole("button", {
      name: "Choose a WAV or MP3 to make a Patch",
    }),
  ).toBeVisible();
});

test("Reduced Motion removes Chameleon animation without hiding state", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const character = page.getByTestId("chameleon-2d");
  await expect(character).toHaveAttribute("data-phase", "idle");
  const style = await character.evaluate((element) => {
    const computed = getComputedStyle(element);
    return {
      animationName: computed.animationName,
      transitionDuration: computed.transitionDuration,
    };
  });
  expect(style.animationName).toBe("none");
  expect(style.transitionDuration).toBe("0s");
});
