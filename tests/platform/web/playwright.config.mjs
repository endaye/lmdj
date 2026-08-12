import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";


const webRoot = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(webRoot, "../../..");
const cleanRoom = process.env.LMDJ_WEB_HOST_CLEAN_ROOM === "1";
const creatorExternal = process.env.LMDJ_CREATOR_WEB_EXTERNAL_SERVER === "1";
const fullChromium = process.env.LMDJ_WEB_HOST_FULL_CHROMIUM === "1" ||
  process.env.LMDJ_CREATOR_WEB_FULL_CHROMIUM === "1";
const sampleEditorSpec = /creator_web_sample_editor\.spec\.mjs/;
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
  ],
});
