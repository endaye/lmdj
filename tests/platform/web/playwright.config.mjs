import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";


const webRoot = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(webRoot, "../../..");
const port = Number.parseInt(process.env.LMDJ_WEB_TOOLCHAIN_PORT ?? "4174", 10);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error(`invalid LMDJ_WEB_TOOLCHAIN_PORT: ${process.env.LMDJ_WEB_TOOLCHAIN_PORT}`);
}
const baseURL = `http://127.0.0.1:${port}`;


export default defineConfig({
  testDir: webRoot,
  fullyParallel: false,
  workers: 1,
  reporter: [["line"]],
  outputDir: resolve(webRoot, "test-results"),
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  webServer: {
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
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],
});
