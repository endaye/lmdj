import {readFile} from "node:fs/promises";

import {expect, test} from "./fixtures/refusal_diagnostics.mjs";


const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

async function importProject(page) {
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  const chooser = await chooserPromise;
  await chooser.setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.getByText("64 / 64")).toBeVisible();
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
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
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
  const revision = page.locator(".project-summary div").filter({
    has: page.getByText("Revision", {exact: true}),
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
