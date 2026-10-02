import {readFile} from "node:fs/promises";

import {expect, test} from "@playwright/test";

import {creatorProjectBundle} from "./creator_project_fixture.mjs";
import {
  PROJECT_OPEN_TIMEOUT_MS,
  openProjectPageAfterBoot,
  overviewProjectId,
  waitForProjectReopen,
} from "../creator/fixtures/creator_boot.mjs";

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


// A release is deployed after main has moved on, and the deploy job may run a
// later main revision of this spec against it. Hosts from #1711 open a Project
// at boot; earlier ones (such as 1.0.66.0) stop on the empty Project library.
// Decide from the settled boot state: a booting host passes through "empty"
// only on its way to creating a Project, so "empty" that persists through the
// settle window is a library boot. A wrong decision fails the journey below;
// it can never turn a failure into a pass.
const LIBRARY_SETTLE_MS = 15_000;

async function bootMode(page) {
  const phase = page.getByTestId("creator-phase");
  await expect(phase).toHaveText(/^(empty|ready)$/, {timeout: PROJECT_OPEN_TIMEOUT_MS});
  const settled = Date.now() + LIBRARY_SETTLE_MS;
  while (Date.now() < settled) {
    if ((await phase.textContent())?.trim() !== "empty") return "project";
    await page.waitForTimeout(500);
  }
  return "library";
}


async function importIntoLibrary(page) {
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles({
    name: "creator-deployment-project.lmdj",
    mimeType: "application/vnd.lmdj.project-bundle",
    buffer: creatorProjectBundle(),
  });
  await expect(page.getByRole("heading", {name: /^Project /}))
    .toBeVisible({timeout: 120_000});
  return null;
}


async function importProject(page, mode) {
  if (mode === "library") return importIntoLibrary(page);
  await openProjectPageAfterBoot(page);
  // Boot opened its own Project; the import is done when a different one is open.
  const booted = (await overviewProjectId(page).textContent())?.trim();
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles({
    name: "creator-deployment-project.lmdj",
    mimeType: "application/vnd.lmdj.project-bundle",
    buffer: creatorProjectBundle(),
  });
  await expect(overviewProjectId(page)).not.toHaveText(booted, {timeout: 120_000});
  await expect(page.getByRole("heading", {name: /^Project /}))
    .toBeVisible({timeout: 120_000});
  return (await overviewProjectId(page).textContent())?.trim();
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

  const mode = await bootMode(page);
  const imported = await importProject(page, mode);
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
  // The Sample workspace selects Pads on the hardware rail (ad343a6b).
  await page.getByRole("button", {name: "Pad A1 — assigned — Key Q", exact: true}).click();
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
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  await expect(page.getByRole("button", {name: "Record"})).toBeEnabled();

  await page.reload();
  await expect(page.getByTestId("creator-phase")).toHaveText("ready", {
    timeout: 120_000,
  });
  if (mode === "library") {
    // A library host lists the stored Project and opens it on request.
    await expect(page.getByRole("heading", {name: "Local Projects"})).toBeVisible();
    const open = page.getByRole("button", {name: /^Open Project /}).first();
    await expect(open).toBeEnabled({timeout: 30_000});
    await open.click();
    await expect(page.getByRole("heading", {name: /^Project /}))
      .toBeVisible({timeout: 120_000});
  } else {
    // The imported Project is remembered, so the reload reopens it by itself.
    await waitForProjectReopen(page, imported, {timeout: 120_000});
    await page.getByRole("button", {name: "Project", exact: true}).click();
    await expect(page.getByRole("heading", {name: `Project ${imported}`}))
      .toBeVisible({timeout: 120_000});
  }
  await expect(page.getByText("64 / 64")).toBeVisible();
});
