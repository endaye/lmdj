import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";

import { ensureCaptureFixture } from "./creator/fixtures/make_capture_fixture.mjs";

const webRoot = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(webRoot, "../../..");
const cleanRoom = process.env.LMDJ_WEB_HOST_CLEAN_ROOM === "1";
const creatorExternal = process.env.LMDJ_CREATOR_WEB_EXTERNAL_SERVER === "1";
const fullChromium = process.env.LMDJ_WEB_HOST_FULL_CHROMIUM === "1" ||
  process.env.LMDJ_CREATOR_WEB_FULL_CHROMIUM === "1";
const sampleEditorSpec = /creator_web_sample_editor\.spec\.mjs/;
const captureSpec = /creator_web_capture\.spec\.mjs/;
// Written at config load so the file exists before Chromium launches with
// --use-file-for-fake-audio-capture; the flag silently yields silence if the
// path is missing, which would turn a real capture regression into a green run.
const captureFixture = ensureCaptureFixture(
  resolve(webRoot, "creator/fixtures/capture-440hz-2s-mono-48k.wav"),
);
const externalServer =
  cleanRoom || creatorExternal ||
  process.env.LMDJ_WEB_HOST_EXTERNAL_SERVER === "1";
const port = Number.parseInt(process.env.LMDJ_WEB_TOOLCHAIN_PORT ?? "4174", 10);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error(`invalid LMDJ_WEB_TOOLCHAIN_PORT: ${process.env.LMDJ_WEB_TOOLCHAIN_PORT}`);
}
const baseURL = `http://127.0.0.1:${port}`;
if (externalServer && !process.env.LMDJ_WEB_HOST_BASE_URL) {
  if (!creatorExternal || !process.env.LMDJ_CREATOR_WEB_BASE_URL) {
    throw new Error("an owned external-server base URL is required");
  }
}
const browserProofBaseURL = creatorExternal
  ? process.env.LMDJ_CREATOR_WEB_BASE_URL
  : process.env.LMDJ_WEB_HOST_BASE_URL ?? baseURL;
const webServer = externalServer
  ? undefined
  : {
      command: [
        "python3",
        resolve(webRoot, "toolchain/server.py"),
        "--root",
        resolve(repoRoot, "build/web/toolchain"),
        "--port",
        String(port),
      ].join(" "),
      url: `${baseURL}/health.json`,
      reuseExistingServer: false,
      timeout: 120_000,
    };


export default defineConfig({
  testDir: webRoot,
  fullyParallel: false,
  workers: 1,
  reporter: [["line"]],
  outputDir: resolve(webRoot, "test-results"),
  use: {
    baseURL: browserProofBaseURL,
    trace: "retain-on-failure",
  },
  webServer,
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(fullChromium ? { channel: "chromium" } : {}),
      },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "creator-sample-chromium",
      testMatch: sampleEditorSpec,
      use: {
        ...devices["Desktop Chrome"],
        ...(fullChromium ? { channel: "chromium" } : {}),
      },
    },
    {
      name: "creator-sample-webkit",
      testMatch: sampleEditorSpec,
      use: { ...devices["Desktop Safari"] },
    },
    // S8B-D8: Chromium's fake device replaying a fixed WAV is the automated
    // acceptance gate for capture. Real-microphone, Safari and iPadOS
    // behaviour stay in the deferred ledger and are never inferred from these.
    {
      name: "creator-capture-chromium",
      testMatch: captureSpec,
      use: {
        ...devices["Desktop Chrome"],
        ...(fullChromium ? { channel: "chromium" } : {}),
        permissions: ["microphone"],
        launchOptions: {
          args: [
            "--use-fake-device-for-media-stream",
            `--use-file-for-fake-audio-capture=${captureFixture}`,
            "--use-fake-ui-for-media-stream",
          ],
        },
      },
    },
    // No --use-fake-ui-for-media-stream and no granted permission, so the
    // headless prompt auto-dismisses into a deterministic NotAllowedError.
    {
      name: "creator-capture-denied-chromium",
      testMatch: captureSpec,
      use: {
        ...devices["Desktop Chrome"],
        ...(fullChromium ? { channel: "chromium" } : {}),
        launchOptions: {
          args: ["--use-fake-device-for-media-stream"],
        },
      },
    },
  ],
});
