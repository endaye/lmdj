export async function openCreatorSystem(page) {
  if (await page.getByRole("button", {name: "Back to music", exact: true}).isVisible()) return;
  await page.getByRole("button", {name: "System", exact: true}).click();
}
export async function clickCreatorSystemAction(page, name) {
  await openCreatorSystem(page);
  await page.getByRole("button", {name, exact: true}).click();
  await page.getByRole("button", {name: "Back to music", exact: true}).click();
}
export async function openCreatorSlice(page) {
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await page.getByRole("button", {name: "Slice", exact: true}).click();
}

// The Sequence touch area has two layers: EDIT (the grid, the default) and
// SETUP (Tempo, Swing, BARS, Quantize, metronome, + NEW, TAP, Refresh). A
// mode change remounts it on EDIT.
export async function showSequenceLayer(page, layer) {
  const toggle = page.getByRole("region", {name: "Sequence editor"})
    .getByRole("button", {name: layer, exact: true});
  if (await toggle.getAttribute("aria-pressed") !== "true") await toggle.click();
  await toggle.and(page.locator("[aria-pressed='true']")).waitFor();
}

// The direct Pattern picker carries the selected Pattern and the Pattern count.
export const sequencePattern = (page) => page.getByTestId("sequence-pattern");
export const selectedSequencePatternId = (page) =>
  sequencePattern(page).getAttribute("data-pattern-id");

// Direct touch selection waits for Stop, like the physical direction keys.
export async function selectSequencePattern(page, patternId) {
  if (await selectedSequencePatternId(page) === patternId) return;
  await page.getByRole("button", {name: "Choose Pattern", exact: true}).click();
  await page.getByRole("dialog", {name: "Choose Pattern", exact: true})
    .locator(`[data-pattern-choice="${patternId}"]`).click();
  await sequencePattern(page).and(page.locator(`[data-pattern-id="${patternId}"]`)).waitFor();
}

// + NEW, then the new Pattern's length, then CREATE (SETUP layer).
export async function createSequencePattern(page, bars = null) {
  await showSequenceLayer(page, "SETUP");
  await page.getByRole("button", {name: "New Pattern", exact: true}).click();
  if (bars !== null) await page.getByRole("button", {name: `${bars} bars`, exact: true}).click();
  await page.getByRole("button", {name: "Create Pattern", exact: true}).click();
}

// Only the selected Sample page renders its controls. Selecting an already
// current page leaves focus and any in-progress gesture untouched.
export async function showSamplePage(page, name) {
  const button = page.getByRole("navigation", {name: "Sample pages"})
    .getByRole("button", {name, exact: true});
  if (await button.getAttribute("aria-current") !== "page") await button.click();
  await button.and(page.locator("[aria-current='page']")).waitFor();
}

export async function showSampleDetails(page) {
  await showSamplePage(page, "Pad");
  const details = page.locator(".sample-details");
  if (!(await details.evaluate(element => element.open))) await details.locator("summary").click();
  return details;
}

// Perform controller ownership outlives its visible subpage. An already active
// page is a no-op, preserving an in-progress native gesture and focus.
export async function showPerformPage(page, name) {
  const button = page.getByRole("navigation", {name: "Perform pages"})
    .getByRole("button", {name, exact: true});
  if (await button.getAttribute("aria-current") !== "page") await button.click();
  await button.and(page.locator("[aria-current='page']")).waitFor();
}

export async function showPatternLaunchGroup(page, slot) {
  const first = Math.floor((slot - 1) / 4) * 4 + 1;
  const button = page.getByRole("button", {name: `Pattern slots ${first} to ${first + 3}`, exact: true});
  if (await button.getAttribute("aria-pressed") !== "true") await button.click();
  await button.and(page.locator("[aria-pressed='true']")).waitFor();
}

// Each Sound Set step owns its visible controls while preserving one reducer.
export async function showSoundSetStep(page, name) {
  const button = page.getByRole("navigation", {name:"Sound Set steps"})
    .getByRole("button", {name, exact:true});
  if (await button.getAttribute("aria-current") !== "step") await button.click();
  await button.and(page.locator('[aria-current="step"]')).waitFor();
}
