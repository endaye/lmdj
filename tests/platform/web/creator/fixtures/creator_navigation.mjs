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

// `‹ GROOVE / NN ›` carries the selected Pattern and the Pattern count.
export const sequencePattern = (page) => page.getByTestId("sequence-pattern");
export const selectedSequencePatternId = (page) =>
  sequencePattern(page).getAttribute("data-pattern-id");

// Steps ‹ › to the Pattern with this id; stepping waits for Stop.
export async function selectSequencePattern(page, patternId) {
  const previous = page.getByRole("button", {name: "Previous Pattern", exact: true});
  const next = page.getByRole("button", {name: "Next Pattern", exact: true});
  while (await previous.isEnabled() && await selectedSequencePatternId(page) !== patternId) {
    const before = await selectedSequencePatternId(page);
    await previous.click();
    await sequencePattern(page).and(page.locator(`:not([data-pattern-id='${before}'])`)).waitFor();
  }
  while (await selectedSequencePatternId(page) !== patternId) {
    if (!await next.isEnabled()) throw new Error(`Pattern ${patternId} is not in the Project`);
    const before = await selectedSequencePatternId(page);
    await next.click();
    await sequencePattern(page).and(page.locator(`:not([data-pattern-id='${before}'])`)).waitFor();
  }
}

// + NEW, then the new Pattern's length, then CREATE (SETUP layer).
export async function createSequencePattern(page, bars = null) {
  await showSequenceLayer(page, "SETUP");
  await page.getByRole("button", {name: "New Pattern", exact: true}).click();
  if (bars !== null) await page.getByRole("button", {name: `${bars} bars`, exact: true}).click();
  await page.getByRole("button", {name: "Create Pattern", exact: true}).click();
}
