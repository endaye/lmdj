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
  await page.getByRole("button", {name: "Open Project 00000000"}).click();
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 60_000});
  await expect(page.getByTestId("audio-state")).toHaveText("Audio inactive");
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
  expect((await report(page)).state).toBe("running");
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
