import {fileURLToPath} from "node:url";

import react from "@vitejs/plugin-react";
import {defineConfig} from "vitest/config";

const webRuntimePlatform = fileURLToPath(new URL(
  "../../packages/web-runtime-platform/web",
  import.meta.url,
));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@lmdj/web-runtime-platform": webRuntimePlatform,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
  },
});
