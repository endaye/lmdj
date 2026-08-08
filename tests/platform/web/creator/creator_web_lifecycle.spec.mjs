import {readFile} from "node:fs/promises";

import {expect, test} from "@playwright/test";


const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

async function importAndActivate(page) {
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
}

async function report(page) {
  const pending = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export report"}).click();
  return JSON.parse(await readFile(await (await pending).path(), "utf8"));
}

async function reopenWithVisibleBusyRetry(page) {
  const heading = page.getByRole("heading", {name: "Project 00000000"});
  const open = () => page.getByRole("button", {
    name: "Open Project 00000000",
  });
  const alert = page.getByRole("alert");
  const deadline = Date.now() + 120_000;
  await open().click();
  while (Date.now() < deadline) {
    await expect.poll(async () =>
      await heading.isVisible() || await alert.isVisible(),
    {timeout: 35_000}).toBe(true);
    if (await heading.isVisible()) return;
    await expect(alert).toContainText("PROJECT_BUSY");
    await page.getByRole("button", {name: "Retry"}).click();
    await expect(alert).toHaveCount(0);
    await page.waitForTimeout(100);
  }
  throw new Error("Project writer lease did not become available after Retry");
}

test("suspend and reload require explicit reopen and explicit reactivation", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  await page.goto("/index.html");
  await importAndActivate(page);
  await page.getByRole("button", {name: "Suspend audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended");
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running");

  await page.reload();
  await expect(page.getByRole("button", {name: "Open Project 00000000"}))
    .toBeVisible({timeout: 60_000});
  await expect(page.getByTestId("audio-state")).toHaveText("Audio inactive");
  await reopenWithVisibleBusyRetry(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio inactive");
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
  expect((await report(page)).state).toBe("running");
});

test("persisted page lifecycle retains the Project and live input surface", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  await page.goto("/index.html");
  await importAndActivate(page);

  await page.evaluate(() => {
    window.dispatchEvent(new PageTransitionEvent("pagehide", {persisted: true}));
    window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted: true}));
  });

  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible();
  await expect(page.getByTestId("creator-phase")).not.toHaveText("closed");
  await expect(page.getByTestId("audio-state")).toHaveText("Audio recovering", {
    timeout: 30_000,
  });
  await page.keyboard.down("KeyA");
  await expect.poll(async () => {
    const value = await report(page);
    return [value.state, value.trigger_admitted_count, value.trigger_outcome_count];
  }, {timeout: 30_000}).toEqual(["running", 1, 1]);
  await page.keyboard.up("KeyA");
});
test.describe("synthetic Web MIDI", () => {
  test.beforeEach(async ({page}) => {
    await page.addInitScript(() => {
      const listeners = new Set();
      const input = {
        type: "input",
        state: "connected",
        addEventListener(type, listener) {
          if (type === "midimessage") listeners.add(listener);
        },
        removeEventListener(type, listener) {
          if (type === "midimessage") listeners.delete(listener);
        },
      };
      const access = new EventTarget();
      access.inputs = new Map([["synthetic", input]]);
      Object.defineProperty(navigator, "requestMIDIAccess", {
        configurable: true,
        value: async () => access,
      });
      window.__creatorMidi = {
        emit(note, velocity = 100) {
          for (const listener of listeners) {
            listener({data: new Uint8Array([0x90, note, velocity])});
          }
        },
        listenerCount() {
          return listeners.size;
        },
      };
    });
  });

  test("notes 36 through 51 map to the selected Bank and listeners clean up", async ({page, browserName}) => {
    test.skip(browserName !== "chromium");
    test.setTimeout(180_000);
    await page.goto("/index.html");
    await importAndActivate(page);
    await page.getByRole("button", {name: "Bank C"}).click();
    await page.getByRole("button", {name: "Enable MIDI"}).click();
    await page.evaluate(() => {
      for (let note = 36; note <= 51; note += 1) window.__creatorMidi.emit(note);
    });
    await expect.poll(async () => {
      const value = await report(page);
      return [value.trigger_admitted_count, value.trigger_outcome_count];
    }, {timeout: 30_000}).toEqual([16, 16]);
    await page.evaluate(() => {
      window.dispatchEvent(new PageTransitionEvent("pagehide"));
    });
    await expect.poll(() => page.evaluate(() => window.__creatorMidi.listenerCount()))
      .toBe(0);
    await page.reload();
  });
});

test("a denied MIDI permission does not mutate Runtime state or Trigger counts", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "requestMIDIAccess", {
      configurable: true,
      value: async () => { throw new DOMException("denied", "NotAllowedError"); },
    });
  });
  await page.goto("/index.html");
  await importAndActivate(page);
  await page.getByRole("button", {name: "Enable MIDI"}).click();
  const value = await report(page);
  expect([
    value.state,
    value.trigger_admitted_count,
    value.trigger_outcome_count,
    value.trigger_rejected_count,
  ]).toEqual(["running", 0, 0, 0]);
});
