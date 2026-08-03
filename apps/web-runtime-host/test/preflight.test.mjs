import assert from "node:assert/strict";
import test from "node:test";

import {
  PREFLIGHT_CAPABILITIES,
  PreflightError,
  runPreflight,
} from "../src/preflight.mjs";

test("uses the exact ordered mandatory preflight list", () => {
  assert.deepEqual(PREFLIGHT_CAPABILITIES, [
    "secureContext",
    "crossOriginIsolated",
    "sharedArrayBuffer",
    "webAssembly",
    "audioWorklet",
    "opfs",
    "opfsSyncAccessHandle",
    "opfsWritableReplace",
  ]);
});

test("passes only when every injected capability probe passes", async () => {
  const visited = [];
  const capabilities = Object.fromEntries(
    PREFLIGHT_CAPABILITIES.map((capability) => [
      capability,
      () => {
        visited.push(capability);
        return true;
      },
    ]),
  );
  const result = await runPreflight(capabilities);
  assert.deepEqual(visited, PREFLIGHT_CAPABILITIES);
  assert.deepEqual(result, {
    ok: true,
    capabilities: PREFLIGHT_CAPABILITIES,
  });
});

test("reports all missing capabilities in locked order with no fallback", async () => {
  const capabilities = Object.fromEntries(
    PREFLIGHT_CAPABILITIES.map((capability) => [capability, true]),
  );
  capabilities.crossOriginIsolated = false;
  capabilities.audioWorklet = () => false;
  capabilities.opfsSyncAccessHandle = () => {
    throw new Error("not available");
  };

  await assert.rejects(
    runPreflight(capabilities),
    (error) => {
      assert.equal(error instanceof PreflightError, true);
      assert.equal(error.code, "UNSUPPORTED_WEB_RUNTIME");
      assert.deepEqual(error.details, {
        missing: [
          "crossOriginIsolated",
          "audioWorklet",
          "opfsSyncAccessHandle",
        ],
      });
      return true;
    },
  );
});
