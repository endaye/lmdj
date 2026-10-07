import {expect} from "@playwright/test";

// Creator boot opens a Project: a fresh store gets an automatically created
// one, and a store with a remembered Project reopens it (#1660). Specs that
// import their own fixture bundle therefore start from an open Project, not
// from an empty library.

// Opening a Project runs three independently bounded 30-second operations
// (open, inspect, snapshot reload); the UI settles within their 90-second
// ceiling plus bounded runner/render time. Creation has the same shape.
export const PROJECT_OPEN_TIMEOUT_MS = 3 * 30_000 + 35_000;

// The short identity the read-only overview shows for the open Project.
export function overviewProjectId(page) {
  return page.getByRole("region", {name: "Overview display"})
    .locator(".overview-facts div", {has: page.locator("dt", {hasText: /^Project$/})})
    .locator("dd");
}

// Wait for boot to settle on an open Project.
export async function waitForBootProject(page, {timeout = PROJECT_OPEN_TIMEOUT_MS} = {}) {
  await expect(page.getByTestId("creator-phase")).toHaveText("ready", {timeout});
  await expect(overviewProjectId(page)).not.toHaveText("—", {timeout});
}

// Wait for boot, then show the Project page with Import available.
export async function openProjectPageAfterBoot(page, options = {}) {
  await waitForBootProject(page, options);
  await page.getByRole("button", {name: "Project", exact: true}).click();
  await expect(page.getByRole("button", {name: "Import .lmdj"})).toBeEnabled({
    timeout: options.timeout ?? 30_000,
  });
}

// After a reload, the remembered Project reopens by itself. A reload, or a
// successor after an owner crash, can overlap the previous owner's writer
// release, which surfaces as a visible, retryable PROJECT_BUSY. Retry it as a
// user would, one second apart, within the same Project-open bound, and
// require the named Project to be the one that opened.
export async function waitForProjectReopen(page, shortId, {timeout = PROJECT_OPEN_TIMEOUT_MS} = {}) {
  const reopened = overviewProjectId(page).filter({hasText: new RegExp(`^${shortId}$`)});
  const retry = page.getByRole("button", {name: "Retry project"});
  const alert = page.getByRole("alert");
  const deadline = Date.now() + timeout;
  while (!(await reopened.isVisible()) && Date.now() < deadline) {
    // The busy alert renders with its retry, so take the first match.
    await expect(reopened.or(retry).or(alert).first())
      .toBeVisible({timeout: Math.max(deadline - Date.now(), 1)});
    if (await reopened.isVisible()) break;
    // Only a writer-release overlap is retried. Any other refusal fails here
    // with its own alert text rather than as a visibility timeout at the
    // deadline.
    await expect(alert).toContainText(
      "The local Project is busy in another tab or process.",
    );
    // A retry in flight may hide its button while the busy alert remains.
    await expect(reopened.or(retry).first())
      .toBeVisible({timeout: Math.max(deadline - Date.now(), 1)});
    if (await reopened.isVisible()) break;
    await page.waitForTimeout(1_000);
    await retry.click();
  }
  await expect(reopened).toBeVisible({timeout: Math.max(deadline - Date.now(), 1)});
  await expect(page.getByTestId("creator-phase")).toHaveText("ready", {timeout});
  await expect(alert).toHaveCount(0);
}

// Explicitly open a listed Project from the library, replacing whichever
// Project boot opened.
export async function openProjectFromLibrary(page, shortId, {timeout = PROJECT_OPEN_TIMEOUT_MS} = {}) {
  await waitForBootSettled(page, {timeout});
  await page.getByRole("button", {name: "Project", exact: true}).click();
  // D01: a card tap selects the Project; OPEN PROJECT opens the selection.
  const select = page.getByRole("button", {name: `Select Project ${shortId}`, exact: true});
  if (!(await select.isVisible())) {
    await page.getByRole("button", {name: "Open local", exact: true}).click();
  }
  await select.click({timeout});
  await page.getByRole("button", {name: `Open Project ${shortId}`, exact: true}).click({timeout});
}

// Wait for boot to stop acting, whether it opened a Project or refused one
// (a remembered Project whose bytes a test damaged fails to reopen, as an
// ordinary open must). Raw transport commands issued after this cannot race a
// boot open or creation.
export async function waitForBootSettled(page, {timeout = PROJECT_OPEN_TIMEOUT_MS} = {}) {
  await expect(page.getByTestId("creator-phase")).toHaveText(/^(ready|failed)$/, {timeout});
}
