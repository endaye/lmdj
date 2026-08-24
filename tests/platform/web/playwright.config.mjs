import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";

import { ensureCaptureFixture } from "./creator/fixtures/make_capture_fixture.mjs";

const webRoot = dirname(fileURLToPath(import.meta.url));
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
// Every proof owns the server it drives: the lane starts one on a
// kernel-assigned ephemeral port and passes its base URL in. Playwright's
// managed `webServer` cannot work that way — it needs the URL before the
// server exists, so it can only bind a fixed port. Two runner services on one
// host then contend for that port, and a server leaked by a crashed lane keeps
// holding it and fails every later lane (issue #297). So there is no managed
// server here and no default base URL: an unowned run fails closed instead of
// silently proving itself against whatever already listens.
const browserProofBaseURL = creatorExternal
  ? process.env.LMDJ_CREATOR_WEB_BASE_URL
  : process.env.LMDJ_WEB_HOST_BASE_URL;
if (!browserProofBaseURL) {
  throw new Error(
    "an owned external-server base URL is required: set " +
      "LMDJ_WEB_HOST_BASE_URL, or LMDJ_CREATOR_WEB_BASE_URL together with " +
      "LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1",
  );
}

export default defineConfig({
  testDir: webRoot,
  fullyParallel: false,
  workers: 1,
  reporter: [["line"]],
  // The Creator proof drives Playwright six times in a row. Playwright clears
  // outputDir at the start of every run, so a single shared directory means
  // each invocation destroys the previous one's traces and only the last
  // failure is ever diagnosable — including in the CI artifact upload. Give
  // each invocation its own subdirectory, keyed by the projects it runs.
  outputDir: resolve(
    webRoot,
    "test-results",
    (process.env.LMDJ_WEB_RESULTS_SLOT ?? "default").replace(/[^A-Za-z0-9._-]/g, "_"),
  ),
  use: {
    baseURL: browserProofBaseURL,
    trace: "retain-on-failure",
  },
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
