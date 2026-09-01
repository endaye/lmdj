import {readFile} from "node:fs/promises";

import {expect, test} from "@playwright/test";

import {creatorProjectBundle} from "./creator_project_fixture.mjs";

const expectedProductBuild = process.env.LMDJ_CREATOR_WEB_EXPECTED_PRODUCT_BUILD;
const expectedHostVersion = process.env.LMDJ_CREATOR_WEB_EXPECTED_VERSION;
if (!expectedProductBuild) {
  throw new Error("LMDJ_CREATOR_WEB_EXPECTED_PRODUCT_BUILD is required");
}
if (!expectedHostVersion) {
  throw new Error("LMDJ_CREATOR_WEB_EXPECTED_VERSION is required");
}


function pcm16Wav({frames = 4_800, sampleRate = 48_000} = {}) {
  const bytes = Buffer.alloc(44 + frames * 2);
  bytes.write("RIFF", 0, "ascii");
  bytes.writeUInt32LE(bytes.length - 8, 4);
  bytes.write("WAVE", 8, "ascii");
  bytes.write("fmt ", 12, "ascii");
  bytes.writeUInt32LE(16, 16);
  bytes.writeUInt16LE(1, 20);
  bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(sampleRate, 24);
  bytes.writeUInt32LE(sampleRate * 2, 28);
  bytes.writeUInt16LE(2, 32);
  bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36, "ascii");
  bytes.writeUInt32LE(frames * 2, 40);
  for (let frame = 0; frame < frames; frame += 1) {
    const sample = Math.round(Math.sin((2 * Math.PI * 440 * frame) / sampleRate) * 24_000);
    bytes.writeInt16LE(sample, 44 + frame * 2);
  }
  return bytes;
}


async function importProject(page) {
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 60_000,
  });
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles({
    name: "creator-deployment-project.lmdj",
    mimeType: "application/vnd.lmdj.project-bundle",
    buffer: creatorProjectBundle(),
  });
  await expect(page.getByRole("heading", {name: /^Project /}))
    .toBeVisible({timeout: 120_000});
}


async function report(page) {
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export report"}).click();
  const download = await downloadPromise;
  return JSON.parse(await readFile(await download.path(), "utf8"));
}


test("published Creator completes authoring, playback, and durable reload", async ({page}) => {
  test.setTimeout(300_000);
  await page.goto("/");
  const identity = await page.evaluate(async () => {
    const manifest = await fetch("./host-manifest.json", {cache: "no-store"})
      .then((response) => response.json());
    return {
      hostId: manifest.host_id,
      hostVersion: manifest.host_version,
      isolated: window.crossOriginIsolated,
      productBuild: manifest.product_build,
      secure: window.isSecureContext,
      sharedArrayBuffer: typeof SharedArrayBuffer === "function",
    };
  });
  expect(identity).toEqual({
    hostId: "creator-web",
    hostVersion: expectedHostVersion,
    isolated: true,
    productBuild: expectedProductBuild,
    secure: true,
    sharedArrayBuffer: true,
  });

  await importProject(page);
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: 30_000,
  });

  const before = await report(page);
  const pad = page.getByRole("button", {
    name: /^Pad A1 — assigned — Key Q$/,
  });
  await pad.click();
  await expect.poll(async () => {
    const after = await report(page);
    return [after.trigger_admitted_count, after.trigger_outcome_count];
  }, {timeout: 30_000}).toEqual([
    before.trigger_admitted_count + 1,
    before.trigger_outcome_count + 1,
  ]);

  await page.getByRole("button", {name: "Sample"}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  await page.getByRole("button", {name: /^Pad A1 — assigned$/}).click();
  const sampleChooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Replace Sample"}).click();
  await (await sampleChooser).setFiles({
    name: "deployment-440hz.wav",
    mimeType: "audio/wav",
    buffer: pcm16Wav(),
  });
  await page.getByRole("button", {name: "Confirm replace"}).click();
  await expect(page.getByRole("button", {name: "Replace Sample"}))
    .toBeEnabled({timeout: 120_000});

  await page.getByRole("button", {name: "Sequence"}).click();
  await expect(page.getByRole("heading", {name: "Sequence"})).toBeVisible();
  await expect(page.getByRole("button", {name: "Record"})).toBeEnabled();

  await page.reload();
  await expect(page.getByTestId("creator-phase")).toHaveText("ready", {
    timeout: 120_000,
  });
  await expect(page.getByRole("heading", {name: "Local Projects"})).toBeVisible();
  const open = page.getByRole("button", {name: /^Open Project /}).first();
  await expect(open).toBeEnabled({timeout: 30_000});
  await open.click();
  await expect(page.getByRole("heading", {name: /^Project /}))
    .toBeVisible({timeout: 120_000});
  await expect(page.getByText("64 / 64")).toBeVisible();
});
