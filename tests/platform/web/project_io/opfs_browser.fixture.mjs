import {test as base, expect, webkit} from "@playwright/test";
import {mkdtemp, realpath, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";

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
      await persistent.close();
    }
    // Retain the diagnostic profile for inspection; no user profile is used.
  },
});
