import {expect, test} from "@playwright/test";

const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

function rounded(box) {
  return {
    x: Math.round(box.x),
    y: Math.round(box.y),
    width: Math.round(box.width),
    height: Math.round(box.height),
  };
}

test("opts into the 880×592 hardware shell, keeps overview read-only, and returns", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  await expect(page.getByRole("button", {name: "Activate audio"})).toBeVisible();

  await page.getByRole("button", {name: "Hardware layout"}).click();
  const consoleBox = rounded(await page.getByTestId("hardware-console").boundingBox());
  const physical = rounded(await page.getByTestId("physical-controls").boundingBox());
  const overview = rounded(await page.getByTestId("overview-display").boundingBox());
  const pads = rounded(await page.getByTestId("pad-matrix").boundingBox());
  const touch = rounded(await page.getByTestId("touch-workspace").boundingBox());

  expect(consoleBox).toMatchObject({width: 880, height: 592});
  expect(physical).toMatchObject({
    x: consoleBox.x + 16,
    y: consoleBox.y + 16,
    width: 80,
    height: 560,
  });
  expect(overview).toMatchObject({
    x: consoleBox.x + 112,
    y: consoleBox.y + 16,
    width: 752,
    height: 176,
  });
  expect(pads).toMatchObject({
    x: consoleBox.x + 112,
    y: consoleBox.y + 208,
    width: 368,
    height: 368,
  });
  expect(touch).toMatchObject({
    x: consoleBox.x + 496,
    y: consoleBox.y + 208,
    width: 368,
    height: 368,
  });

  const pad = rounded(await page.getByRole("button", {name: /Pad A1 /}).boundingBox());
  expect(pad).toMatchObject({width: 80, height: 80});
  const encoders = rounded(await page.getByTestId("physical-encoders").boundingBox());
  expect(encoders).toMatchObject({
    x: physical.x,
    y: physical.y + 80 + 16,
    width: 80,
    height: 80,
  });
  const encoder = rounded(await page.getByRole("button", {
    name: "Encoder 1 — unassigned until hardware mapping is approved",
  }).boundingBox());
  expect(encoder).toMatchObject({width: 32, height: 32});
  const keyBlock = rounded(await page.getByTestId("physical-keys").boundingBox());
  expect(keyBlock).toMatchObject({
    x: physical.x,
    y: pads.y,
    width: 80,
    height: 368,
  });
  const keys = page.getByTestId("physical-controls");
  for (const bank of ["Bank A", "Bank B", "Bank C", "Bank D"]) {
    const box = rounded(await keys.getByRole("button", {name: bank, exact: true}).boundingBox());
    expect(box).toMatchObject({width: 32, height: 32});
  }
  await expect(keys.getByRole("button", {name: "Project", exact: true})).toBeVisible();
  await expect(keys.getByRole("button", {name: "Sample", exact: true})).toBeVisible();
  await expect(keys.getByRole("button", {name: "Sequence — open a playable Project first"}))
    .toBeVisible();
  await expect(keys.getByRole("button", {name: /^Perform/})).toBeVisible();
  await expect(keys.getByRole("button", {name: "Record", exact: true})).toHaveText("●");
  await expect(keys.getByRole("button", {
    name: "Play/Stop — needs a playable Project and running audio",
    exact: true,
  })).toHaveText("▶");
  const shot = process.env.LMDJ_HARDWARE_CONSOLE_SHOT;
  if (shot) {
    await page.getByTestId("hardware-console").screenshot({path: shot});
  }

  await expect(page.getByTestId("overview-display").locator("button")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Existing workspace"})).toBeVisible();
  await expect(page.getByRole("button", {name: "Activate audio"})).toBeVisible();

  await page.setViewportSize({width: 768, height: 600});
  await page.getByRole("button", {name: "Existing workspace"}).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", {name: "Existing workspace"})).toBeVisible();
  await expect(page.getByTestId("overview-display").locator("button")).toHaveCount(0);

  await page.getByRole("button", {name: "Existing workspace"}).click();
  await expect(page.getByTestId("hardware-console")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Hardware layout"})).toBeVisible();
  await expect(page.getByTestId("creator-phase")).toHaveText("empty");
});
