import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

import { parseAllHeaders } from "../../../tests/platform/web/node_modules/@netlify/headers-parser/lib/index.js";

const repoRoot = path.resolve(import.meta.dirname, "../../..");
const orchestrator = path.join(repoRoot, "apps/web-runtime-host/tools/deploy_orchestrator.py");
const baseHeaders = path.join(repoRoot, "apps/web-runtime-host/deploy/_headers");

function pythonEnvironment(source = process.env) {
  const environment = { LANG: "C", PATH: source.PATH ?? "" };
  for (const name of ["LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"]) {
    if (source[name]) {
      environment[name] = source[name];
    }
  }
  return environment;
}

test("Python subprocess environment preserves loader paths but omits credentials", () => {
  assert.deepEqual(
    pythonEnvironment({
      DYLD_LIBRARY_PATH: "/mac-libs",
      GITHUB_TOKEN: "must-not-leak",
      LD_LIBRARY_PATH: "/linux-libs",
      PATH: "/tools",
    }),
    {
      DYLD_LIBRARY_PATH: "/mac-libs",
      LANG: "C",
      LD_LIBRARY_PATH: "/linux-libs",
      PATH: "/tools",
    },
  );
});

test("assembled Netlify headers cache only the nine manifest assets immutably", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "lmdj-netlify-headers-"));
  try {
    const dist = path.join(root, "dist");
    const assetsRoot = path.join(dist, "assets");
    await mkdir(assetsRoot, { recursive: true });
    const assets = Array.from({ length: 9 }, (_, index) => ({
      bytes: 1,
      path: `assets/asset-${index}.${String(index).repeat(64)}.mjs`,
      role: "host_module",
      sha256: String(index).repeat(64),
    }));
    for (const asset of assets) {
      await writeFile(path.join(dist, asset.path), "x");
    }
    await writeFile(
      path.join(dist, "host-manifest.json"),
      JSON.stringify({ assets }),
    );
    const rendered = spawnSync(
      "python3",
      [orchestrator, "render-headers", dist, baseHeaders],
      { encoding: "utf8", env: pythonEnvironment() },
    );
    assert.equal(rendered.status, 0, rendered.stderr);
    assert.doesNotMatch(rendered.stdout, /^\/assets\/\*$/m);
    const headersPath = path.join(root, "_headers");
    await writeFile(headersPath, rendered.stdout);
    const parsed = await parseAllHeaders({ headersFiles: [headersPath] });
    assert.deepEqual(parsed.errors, []);

    const cacheControl = (requestPath) => {
      let value;
      for (const rule of parsed.headers) {
        if (rule.forRegExp.test(requestPath)) {
          value = rule.values["Cache-Control"] ?? value;
        }
      }
      return value;
    };
    for (const asset of assets) {
      assert.equal(
        cacheControl(`/${asset.path}`),
        "public, max-age=31536000, immutable",
      );
    }
    assert.equal(cacheControl("/assets/missing.map"), "no-store");
    assert.equal(cacheControl("/assets/source.mjs.map"), "no-store");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
