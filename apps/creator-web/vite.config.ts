import {fileURLToPath} from "node:url";

import react from "@vitejs/plugin-react";
import {defineConfig} from "vitest/config";

const webRuntimePlatform = fileURLToPath(new URL(
  "../../packages/web-runtime-platform/web",
  import.meta.url,
));

export default defineConfig({
  plugins: [react()],
  build: {
    // The console font ships inside the one stylesheet the packager admits
    // (no separate font asset role); the Creator CSP allows data: fonts.
    assetsInlineLimit: (file) => file.endsWith(".woff2") ? true : undefined,
  },
  resolve: {
    alias: {
      "@lmdj/web-runtime-platform": webRuntimePlatform,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
    // Must stay clearly above the Testing Library `asyncUtilTimeout` set in
    // test/setup.ts, so a missing element reports "unable to find role" rather
    // than being cut short by the per-test timeout.
    testTimeout: 20_000,
  },
});
