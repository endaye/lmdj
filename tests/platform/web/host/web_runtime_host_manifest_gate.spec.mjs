import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";


const baseURL = process.env.LMDJ_WEB_HOST_BASE_URL ?? "http://127.0.0.1:4175";
const productVersion = JSON.parse(await readFile(
  new URL("../../../../products/lmdj/version.json", import.meta.url),
  "utf8",
));
const currentProductBuild = ["milestone", "minor", "build", "patch"]
  .map((name) => productVersion[name])
  .join(".");
const wrongProductParts = currentProductBuild.split(".").map(Number);
wrongProductParts[3] += 1;
const wrongProductBuild = wrongProductParts.join(".");


function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}


test("packaged index binds exact canonical manifest bytes without inline script", async ({ request }) => {
  const indexResponse = await request.get(`${baseURL}/index.html`);
  expect(indexResponse.ok()).toBe(true);
  const index = await indexResponse.text();
  const manifestResponse = await request.get(`${baseURL}/host-manifest.json`);
  expect(manifestResponse.ok()).toBe(true);
  const manifestBytes = await manifestResponse.body();
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  expect(manifestBytes.toString("utf8")).toBe(canonicalJson(manifest));
  const digest = createHash("sha256").update(manifestBytes).digest("hex");
  expect(index).toContain(
    `<meta name="lmdj-host-manifest-sha256" content="${digest}">`,
  );
  expect(index).not.toMatch(/<script(?![^>]*\bsrc=)[^>]*>/i);
  expect(manifest).toMatchObject({
    product_build: currentProductBuild,
    host_version: "3.0.0",
    protocol_version: 1,
    heap_bytes: 536_870_912,
  });
});


test("packaged host starts through the real Window and Dedicated Worker realms", async ({ page }) => {
  await page.goto(`${baseURL}/index.html`);
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  const diagnostics = JSON.parse(await page.locator("#diagnostics").textContent());
  expect(diagnostics).toMatchObject({
    product_build: currentProductBuild,
    host_version: "3.0.0",
    protocol_version: 1,
  });
  expect(diagnostics.error_code ?? null).toBeNull();
  expect(await page.evaluate(() => ({
    failed: window.Module.ccall("lmdj_web_host_failed", "number", [], []),
    manifestReady: window.lmdjWebRuntimeHost.manifestReady,
    runtimeInitialized: window.lmdjWebRuntimeHost.runtimeInitialized,
  }))).toEqual({
    failed: 0,
    manifestReady: true,
    runtimeInitialized: true,
  });
});


test("late or repeated real manifest initialization terminally seals the real Host", async ({ browser }) => {
  for (const mode of ["repeated", "malformed"]) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.addInitScript(() => {
      Object.defineProperty(
        FileSystemFileHandle.prototype,
        "createSyncAccessHandle",
        { configurable: true, value() {} },
      );
    });
    await page.goto(`${baseURL}/index.html`);
    await expect(page.locator("#host-state"), mode).toHaveText("audio-suspended");
    const outcome = await page.evaluate(async (selectedMode) => {
      async function inventory(directory, prefix = "") {
        const paths = [];
        for await (const [name, handle] of directory.entries()) {
          const relative = `${prefix}${name}`;
          paths.push(`${handle.kind}:${relative}`);
          if (handle.kind === "directory") {
            paths.push(...await inventory(handle, `${relative}/`));
          }
        }
        return paths.sort();
      }
      async function request(operation, payload) {
        try {
          return {
            resolved: true,
            response: await window.lmdjWebRuntimeHost.transport.send({
              protocol_version: 1,
              request_id: crypto.randomUUID(),
              operation,
              payload,
            }, { deadlineMs: 1_000 }),
          };
        } catch (error) {
          return { resolved: false, code: error?.code ?? null };
        }
      }
      const root = await navigator.storage.getDirectory();
      const before = await inventory(root);
      const manifestResponse = await fetch("./host-manifest.json", { cache: "no-store" });
      const validBytes = new Uint8Array(await manifestResponse.arrayBuffer());
      const malformedBytes = new TextEncoder().encode("{");
      const bytes = selectedMode === "repeated" ? validBytes : malformedBytes;
      const digestBytes = await crypto.subtle.digest("SHA-256", bytes);
      const digest = [...new Uint8Array(digestBytes)]
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
      const initialization = window.Module.ccall(
        "lmdj_web_host_initialize_manifest",
        "number",
        ["array", "number", "string", "number"],
        [bytes, bytes.byteLength, digest, digest.length],
      );
      const deadline = performance.now() + 1_000;
      while (
        window.Module.ccall("lmdj_web_host_failed", "number", [], []) !== 1 &&
        performance.now() < deadline
      ) {
        await new Promise((resolve) => setTimeout(resolve, 5));
      }
      const status = await request("host.status", {});
      const project = await request("project.create", {
        project_id: `late-${crypto.randomUUID()}`,
        bpm: 120,
        initial_pattern: { pattern_id: crypto.randomUUID(), bars: 1, events: [] },
      });
      return {
        after: await inventory(root),
        before,
        failed: window.Module.ccall("lmdj_web_host_failed", "number", [], []),
        initialization,
        project,
        status,
      };
    }, mode);
    expect(outcome.initialization, mode).not.toBe(0);
    expect(outcome.failed, mode).toBe(1);
    expect(outcome.status.resolved, mode).toBe(false);
    expect(outcome.status.code, mode).toBe("HOST_PROTOCOL_MISMATCH");
    expect(outcome.project.resolved, mode).toBe(false);
    expect(outcome.project.code, mode).toBe("HOST_PROTOCOL_MISMATCH");
    expect(outcome.after, mode).toEqual(outcome.before);
    await context.close();
  }
});


test("missing malformed oversized mismatched and wrong-identity manifests load no runtime", async ({ browser, request }) => {
  test.setTimeout(120_000);
  const indexResponse = await request.get(`${baseURL}/index.html`);
  const originalIndex = await indexResponse.text();
  const manifestResponse = await request.get(`${baseURL}/host-manifest.json`);
  const originalManifest = JSON.parse(await manifestResponse.text());
  const runtimeScript = originalManifest.assets.find(
    ({ role }) => role === "runtime_script",
  ).path;
  const wrongIdentity = { ...originalManifest, product_build: wrongProductBuild };
  const wrongIdentityBytes = Buffer.from(canonicalJson(wrongIdentity));
  const wrongIdentityDigest = createHash("sha256")
    .update(wrongIdentityBytes)
    .digest("hex");
  const rebound = (name, mutate) => {
    const manifest = structuredClone(originalManifest);
    mutate(manifest);
    const body = Buffer.from(canonicalJson(manifest));
    const digest = createHash("sha256").update(body).digest("hex");
    return {
      name,
      status: 200,
      body,
      index: originalIndex.replace(
        /(<meta name="lmdj-host-manifest-sha256" content=")[0-9a-f]{64}("\>)/,
        `$1${digest}$2`,
      ),
    };
  };
  const scenarios = [
    { name: "missing", status: 404, body: "missing" },
    { name: "malformed", status: 200, body: "{" },
    { name: "oversized", status: 200, body: "x".repeat(65_537) },
    { name: "digest mismatch", status: 200, body: canonicalJson(originalManifest) + " " },
    {
      name: "wrong identity",
      status: 200,
      body: wrongIdentityBytes,
      index: originalIndex.replace(
        /(<meta name="lmdj-host-manifest-sha256" content=")[0-9a-f]{64}("\>)/,
        `$1${wrongIdentityDigest}$2`,
      ),
    },
    rebound("extra root field", (manifest) => { manifest.unexpected = true; }),
    rebound("ownership mismatch", (manifest) => {
      manifest.distribution_contract = "other";
    }),
    rebound("manifest version", (manifest) => { manifest.manifest_version = 2; }),
    rebound("wrong host", (manifest) => { manifest.host_version = "999.0.0"; }),
    rebound("wrong protocol", (manifest) => { manifest.protocol_version = 999; }),
    rebound("wrong heap", (manifest) => { manifest.heap_bytes = 1; }),
    rebound("wrong limit", (manifest) => {
      manifest.resource_limits.imported_wav_bytes = 1;
    }),
    rebound("wrong emsdk tag", (manifest) => {
      manifest.emscripten.emsdk_tag = "latest";
    }),
    rebound("wrong emsdk revision", (manifest) => {
      manifest.emscripten.emsdk_revision = "a".repeat(40);
    }),
    rebound("wrong releases revision", (manifest) => {
      manifest.emscripten.emscripten_releases_revision = "b".repeat(40);
    }),
    rebound("abbreviated emcc output", (manifest) => {
      manifest.emscripten.emcc_version = "emcc 6.0.5";
    }),
    rebound("empty inventory", (manifest) => { manifest.assets = []; }),
    rebound("duplicate role", (manifest) => {
      manifest.assets[0].role = "host_main";
    }),
    rebound("unknown role", (manifest) => {
      manifest.assets[0].role = "unknown";
    }),
    rebound("renamed production asset", (manifest) => {
      manifest.assets[0].path = manifest.assets[0].path.replace(
        /^assets\/[a-z0-9-]+\./,
        "assets/renamed.",
      );
    }),
    rebound("zero asset size", (manifest) => { manifest.assets[0].bytes = 0; }),
    rebound("filename digest mismatch", (manifest) => {
      manifest.assets[0].sha256 = "f".repeat(64);
    }),
    rebound("duplicate asset path", (manifest) => {
      manifest.assets[1].path = manifest.assets[0].path;
    }),
    rebound("extra asset field", (manifest) => {
      manifest.assets[0].unexpected = true;
    }),
    rebound("inventory order", (manifest) => {
      [manifest.assets[0], manifest.assets[1]] = [
        manifest.assets[1], manifest.assets[0],
      ];
    }),
  ];

  for (const scenario of scenarios) {
    const context = await browser.newContext();
    const page = await context.newPage();
    let runtimeRequests = 0;
    await page.addInitScript(() => {
      window.__manifestGateOpfsCalls = 0;
      const original = navigator.storage.getDirectory.bind(navigator.storage);
      navigator.storage.getDirectory = (...args) => {
        window.__manifestGateOpfsCalls += 1;
        return original(...args);
      };
    });
    await page.route(`**/${runtimeScript}`, async (route) => {
      runtimeRequests += 1;
      await route.continue();
    });
    if (scenario.index) {
      await page.route(`${baseURL}/index.html`, (route) => route.fulfill({
        status: 200,
        contentType: "text/html",
        body: scenario.index,
      }));
    }
    await page.route(`${baseURL}/host-manifest.json`, (route) => route.fulfill({
      status: scenario.status,
      contentType: "application/json",
      body: scenario.body,
    }));
    await page.goto(`${baseURL}/index.html`);
    await expect(page.locator("#host-state"), scenario.name).toHaveText("failed");
    const diagnostics = JSON.parse(await page.locator("#diagnostics").textContent());
    expect(diagnostics.error_code, scenario.name).toBe("HOST_PROTOCOL_MISMATCH");
    expect(runtimeRequests, scenario.name).toBe(0);
    expect(await page.evaluate(() => window.__manifestGateOpfsCalls), scenario.name).toBe(0);
    await context.close();
  }
});
