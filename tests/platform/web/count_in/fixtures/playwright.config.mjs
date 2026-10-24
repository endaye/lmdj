import {resolve, dirname, basename} from "node:path";
import {lstatSync, realpathSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {defineConfig, devices} from "@playwright/test";

const fixtureRoot = dirname(fileURLToPath(import.meta.url));
const baseURL = process.env.LMDJ_CREATOR_COUNT_IN_IO_BASE_URL;
const artifactRoot = process.env.LMDJ_CREATOR_COUNT_IN_IO_ARTIFACT_ROOT;
if (!baseURL || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]*$/.test(baseURL) || !artifactRoot) {
  throw new Error("the separate proof's owned loopback server and artifact root are required");
}
const ownedRoot = resolve(artifactRoot);
const expectedParent = resolve(fixtureRoot, "../../../../../build/web/creator-count-in-io/runs");
if (dirname(ownedRoot) !== expectedParent || !/^candidate\.[A-Za-z0-9]{6}$/.test(basename(ownedRoot)) ||
    lstatSync(ownedRoot).isSymbolicLink() || !lstatSync(ownedRoot).isDirectory() || realpathSync(ownedRoot) !== ownedRoot) {
  throw new Error("browser output must remain inside this entrypoint's owned non-symlink candidate directory");
}
export default defineConfig({
  testDir: resolve(fixtureRoot, ".."),
  testMatch: ["creator_count_in_opfs.spec.mjs", "creator_recording_switch_opfs.spec.mjs"],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 150_000, // Existing 125s Project-open bound plus this bounded I/O journey.
  expect: {timeout: 1_000},
  outputDir: resolve(artifactRoot, "browser-results"),
  reporter: [["line"], ["json", {outputFile: resolve(artifactRoot, "playwright-report.json")}]],
  use: {baseURL, trace: "retain-on-failure"},
  projects: [{name: "creator-count-in-io-chromium",
    use: {...devices["Desktop Chrome"], channel: "chromium"}}],
});
