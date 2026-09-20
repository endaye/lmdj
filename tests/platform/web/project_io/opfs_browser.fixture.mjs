import {test as base, expect, webkit} from "@playwright/test";
import {mkdtemp, realpath, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";

import {collectBrowserProcessState} from "./opfs_browser_process_state.mjs";

export {expect};

// Explicit test-environment override, not a product dependency upgrade. Keep
// the ordinary fixtures untouched unless the caller selects an OPFS-capable
// WebKit executable. The original context retains Playwright's normal options
// and lifecycle for Chromium and for the default locked-browser proof.
export const test = base.extend({
  context: async ({context, browserName, baseURL, contextOptions, viewport,
    userAgent, deviceScaleFactor, isMobile, hasTouch}, use, testInfo) => {
    const selected = process.env.LMDJ_WEBKIT_OPFS_EXECUTABLE;
    if (browserName !== "webkit" || !selected) {
      await use(context);
      return;
    }

    const executablePath = await realpath(selected);
    const profile = await mkdtemp(join(tmpdir(), "lmdj-opfs-webkit-"));
    const persistent = await webkit.launchPersistentContext(profile, {
      ...contextOptions, headless: true, executablePath, baseURL, viewport,
      userAgent, deviceScaleFactor, isMobile, hasTouch,
    });
    try {
      const evidencePath = testInfo.outputPath("opfs-browser-environment.json");
      await writeFile(evidencePath, JSON.stringify({executablePath, profile, persistent: true,
        note: "Explicit executable override; locked client version is not browser build identity."}));
      await testInfo.attach("opfs-browser-environment", {
        path: evidencePath, contentType: "application/json",
      });
      // The test runner owns tracing. Starting/stopping a second trace here
      // conflicts with its automatic context-close handling.
      await use(persistent);
    } finally {
      // A navigation that hangs until the test timeout leaves only the URL it
      // was loading; the browser's process, thread, descriptor and shared
      // memory state at that moment is what names the cause (#1570). Read it
      // before the browser goes away, on the Linux runners where it happens.
      if (testInfo.status === "timedOut" && process.platform === "linux") {
        try {
          const urls = persistent.pages().map((page) => page.url());
          const state = collectBrowserProcessState(executablePath, urls);
          const statePath = testInfo.outputPath("webkit-process-state.txt");
          await writeFile(statePath, state);
          await testInfo.attach("webkit-process-state", {
            path: statePath, contentType: "text/plain",
          });
          console.log(`webkit process state at timeout:\n${state}`);
        } catch (error) {
          console.log(`webkit process state unavailable: ${error.message}`);
        }
      }
      await persistent.close();
    }
    // Retain the diagnostic profile for inspection; no user profile is used.
  },
});
