import {readFile} from "node:fs/promises";

import {expect, test} from "./fixtures/refusal_diagnostics.mjs";
import {
  openProjectFromLibrary,
  openProjectPageAfterBoot,
  overviewProjectId,
  waitForBootProject,
  waitForProjectReopen,
} from "./fixtures/creator_boot.mjs";


const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

async function importProject(page) {
  await openProjectPageAfterBoot(page);
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  const chooser = await chooserPromise;
  await chooser.setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.getByText("64 / 64")).toBeVisible();
}

async function inspectProject(page) {
  const response = await page.evaluate(() => window.lmdjWebRuntimeHost.transport.send({
    protocol_version: 1,
    request_id: crypto.randomUUID(),
    operation: "project.inspect",
    payload: {},
  }));
  expect(response.ok, JSON.stringify(response.error ?? null)).toBe(true);
  return response.result;
}

// Project Truth without the fields a copy must change.
function withoutIdentity({project_id: _id, revision: _revision, ...truth}) {
  return truth;
}

async function activate(page) {
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: 30_000,
  });
}

async function downloadReport(page) {
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export report"}).click();
  const download = await downloadPromise;
  // The Build lives in the packaged manifest the app already loads; naming it
  // again here made an identity bump cost a CI cycle to discover.
  expect(download.suggestedFilename()).toMatch(
      /^lmdj-creator-web-\d+\.\d+\.\d+\.\d+\.json$/);
  return JSON.parse(await readFile(await download.path(), "utf8"));
}

async function armPadOutcomeObservation(pad) {
  await pad.evaluate((element) => {
    element.removeAttribute("data-proof-outcome-observed");
    const observeOutcome = () => {
      const outcome = element.getAttribute("data-outcome");
      if (outcome !== null && outcome !== "idle") {
        element.setAttribute("data-proof-outcome-observed", outcome);
        return true;
      }
      return false;
    };
    if (observeOutcome()) return;
    const observer = new MutationObserver((records) => {
      const observed = records.some((record) =>
        record.oldValue !== null && record.oldValue !== "idle"
      );
      if (observed || observeOutcome()) {
        element.setAttribute("data-proof-outcome-observed", "true");
        observer.disconnect();
      }
    });
    observer.observe(element, {
      attributes: true,
      attributeFilter: ["data-outcome"],
      attributeOldValue: true,
    });
  });
}

// A Pad press reaches the Runtime through an asynchronous journey serialized
// behind the presses before it, so a burst of unacknowledged clicks cannot tell
// a dispatch that was lost from one that has not landed yet: the report simply
// reads short. Holding each press until that Pad reports its own outcome makes a
// lost admission fail at the Pad that lost it.
async function pressAdmittedPad(page, pad) {
  await expect(pad).toHaveAttribute("data-outcome", "idle", {timeout: 30_000});
  await armPadOutcomeObservation(pad);
  await pad.hover();
  await page.mouse.down();
  await expect(pad).toHaveAttribute("data-proof-outcome-observed", /.+/, {
    timeout: 30_000,
  });
  await page.mouse.up();
  await expect(pad).toHaveAttribute("data-outcome", "idle", {timeout: 30_000});
}

test("visible Creator journey imports, activates, and admits all 64 unique Pad addresses", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  // Sixty-four acknowledged presses cost more wall clock than sixty-four
  // unobserved clicks did, and this journey shares a loaded host with the rest
  // of the Chromium group.
  test.setTimeout(240_000);
  await page.goto("/index.html");
  await waitForBootProject(page);
  await importProject(page);
  await activate(page);

  const visited = new Set();
  for (const bank of ["A", "B", "C", "D"]) {
    await page.getByRole("button", {name: `Bank ${bank}`}).click();
    const pads = page.getByRole("button", {
      name: /^Pad [A-D]\d+ — assigned — Key [QWERTYUIASDFGHJK]$/,
    });
    await expect(pads).toHaveCount(16);
    for (let index = 0; index < 16; index += 1) {
      const pad = pads.nth(index);
      const name = await pad.getAttribute("aria-label");
      expect(visited.has(name)).toBe(false);
      visited.add(name);
      await pressAdmittedPad(page, pad);
    }
  }
  expect(visited.size).toBe(64);
  await expect.poll(async () => {
    const report = await downloadReport(page);
    return [
      report.state,
      report.trigger_admitted_count,
      report.trigger_outcome_count,
      report.trigger_rejected_count,
    ];
  }, {timeout: 30_000}).toEqual(["running", 64, 64, 0]);
});
test("physical key order addresses the matching Bank-A Pads and preserves the full Runtime tuple", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(120_000);
  await page.goto("/index.html");
  await importProject(page);
  await activate(page);
  const keys = [
    ["KeyQ", "Q"], ["KeyW", "W"], ["KeyE", "E"], ["KeyR", "R"],
    ["KeyT", "T"], ["KeyY", "Y"], ["KeyU", "U"], ["KeyI", "I"],
    ["KeyA", "A"], ["KeyS", "S"], ["KeyD", "D"], ["KeyF", "F"],
    ["KeyG", "G"], ["KeyH", "H"], ["KeyJ", "J"], ["KeyK", "K"],
  ];
  for (const [index, [code, key]] of keys.entries()) {
    const pad = page.getByRole("button", {
      name: `Pad A${index + 1} — assigned — Key ${key}`,
    });
    await armPadOutcomeObservation(pad);
    await page.keyboard.down(code);
    await expect(pad).toHaveAttribute("data-proof-outcome-observed", /.+/);
    await page.keyboard.up(code);
    await expect(pad).toHaveAttribute("data-outcome", "idle");
  }
  await expect.poll(async () => {
    const report = await downloadReport(page);
    return [
      report.trigger_admitted_count,
      report.trigger_outcome_count,
      report.trigger_rejected_count,
      report.state,
    ];
  }, {timeout: 30_000}).toEqual([16, 16, 0, "running"]);
});

test("ready active Runtime survives portrait and landscape resize", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  await page.goto("/index.html");
  await importProject(page);
  await activate(page);
  await page.keyboard.press("KeyQ");
  await expect.poll(async () => {
    const value = await downloadReport(page);
    return [value.trigger_admitted_count, value.trigger_outcome_count];
  }, {timeout: 30_000}).toEqual([1, 1]);

  const heading = page.getByRole("heading", {name: "Project 00000000"});
  const revision = page.locator(".overview-facts div").filter({
    has: page.getByText("Rev", {exact: true}),
  }).getByRole("definition");
  const before = await downloadReport(page);
  const expectedRevision = await revision.textContent();

  for (const viewport of [
    {width: 768, height: 1024},
    {width: 1024, height: 768},
  ]) {
    await page.setViewportSize(viewport);
    await expect(heading).toBeVisible();
    await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
    await expect(revision).toHaveText(expectedRevision);
    const after = await downloadReport(page);
    expect({
      product_build: after.product_build,
      host_id: after.host_id,
      host_version: after.host_version,
      platform_version: after.platform_version,
      protocol_version: after.protocol_version,
      state: after.state,
      trigger_admitted_count: after.trigger_admitted_count,
      trigger_outcome_count: after.trigger_outcome_count,
      trigger_rejected_count: after.trigger_rejected_count,
    }).toEqual({
      product_build: before.product_build,
      host_id: before.host_id,
      host_version: before.host_version,
      platform_version: before.platform_version,
      protocol_version: before.protocol_version,
      state: before.state,
      trigger_admitted_count: before.trigger_admitted_count,
      trigger_outcome_count: before.trigger_outcome_count,
      trigger_rejected_count: before.trigger_rejected_count,
    });
  }
});

test("boot creates a stored Project, New Project adds one, and a reload reopens the last", async ({page}) => {
  test.setTimeout(180_000);
  const emptyPads = page.getByRole("button", {name: /^Pad A\d+ — empty — Key [QWERTYUIASDFGHJK]$/});
  const sampleKey = page.getByRole("button", {name: "Sample", exact: true});

  // A fresh store boots into an automatically created, empty Project on Sample.
  await page.goto("/index.html");
  await waitForBootProject(page);
  await expect(sampleKey).toHaveAttribute("aria-current", "page");
  await expect(emptyPads).toHaveCount(16);
  const first = (await overviewProjectId(page).textContent())?.trim();
  expect(first).toMatch(/^[0-9a-f]{8}$/);

  // New Project opens a second, different Project, again on Sample.
  await page.getByRole("button", {name: "Project", exact: true}).click();
  await page.getByRole("button", {name: "New Project"}).click();
  await expect(overviewProjectId(page)).not.toHaveText(first, {timeout: 60_000});
  await expect(sampleKey).toHaveAttribute("aria-current", "page");
  const second = (await overviewProjectId(page).textContent())?.trim();
  expect(second).toMatch(/^[0-9a-f]{8}$/);

  // The far side of both creations is storage, and the far side of "last
  // opened" is the next boot: a fresh document reopens the second Project and
  // lists both. A reload can overlap the previous document's writer release,
  // which surfaces as a visible, retryable PROJECT_BUSY.
  await page.reload();
  await waitForProjectReopen(page, second);
  await page.getByRole("button", {name: "Project", exact: true}).click();
  await page.getByRole("button", {name: "Open local"}).click();
  await expect(page.getByRole("button", {name: /^Open Project [0-9a-f]{8}$/})).toHaveCount(2);
});

test("Duplicate copies the open Project under a new identity, keeps edits apart, and a reload reopens the copy", async ({page}) => {
  test.setTimeout(300_000);
  await page.goto("/index.html");
  await waitForBootProject(page);
  await importProject(page);
  const source = await inspectProject(page);

  // The copy opens with identical Pads, Patterns and settings and a new identity.
  await page.getByRole("button", {name: "Duplicate Project"}).click();
  await expect(overviewProjectId(page)).not.toHaveText("00000000", {timeout: 120_000});
  const copyShort = (await overviewProjectId(page).textContent())?.trim();
  expect(copyShort).toMatch(/^[0-9a-f]{8}$/);
  await expect(page.getByRole("heading", {name: `Project ${copyShort}`})).toBeVisible();
  const copy = await inspectProject(page);
  expect(copy.project.project_id).not.toBe(source.project.project_id);
  expect(copy.project.project_id.slice(0, 8)).toBe(copyShort);
  expect(copy.project_revision).toBe(0);
  expect(withoutIdentity(copy.project)).toEqual(withoutIdentity(source.project));

  // An edit commits to the copy.
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await page.getByRole("button", {name: "Create Pattern", exact: true}).click();
  await expect.poll(async () => (await inspectProject(page)).project_revision,
    {timeout: 60_000}).toBe(1);
  const edited = await inspectProject(page);
  expect(Object.keys(edited.project.patterns))
    .toHaveLength(Object.keys(copy.project.patterns).length + 1);

  // The copy is now the remembered Project: a reload reopens it, edit included.
  await page.reload();
  await waitForProjectReopen(page, copyShort);
  expect((await inspectProject(page)).project).toEqual(edited.project);

  // The source never saw the copy's edit.
  await openProjectFromLibrary(page, "00000000");
  await expect(overviewProjectId(page)).toHaveText("00000000", {timeout: 120_000});
  const reopenedSource = await inspectProject(page);
  expect(reopenedSource.project_revision).toBe(source.project_revision);
  expect(reopenedSource.project).toEqual(source.project);
});
