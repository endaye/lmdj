import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

const repoRoot = resolve(import.meta.dirname, "../../../..");
const hostRoot = resolve(repoRoot, "apps/web-runtime-host");
const sourceRoutes = new Map([
  ["/formal-host/index.html", resolve(hostRoot, "index.html")],
  ["/formal-host/styles.css", resolve(hostRoot, "styles.css")],
  ["/formal-host/src/diagnostic_project.mjs", resolve(hostRoot, "src/diagnostic_project.mjs")],
  ["/formal-host/src/main.mjs", resolve(hostRoot, "src/main.mjs")],
  ["/formal-host/src/input_adapters.mjs", resolve(hostRoot, "src/input_adapters.mjs")],
  ["/formal-host/src/preflight.mjs", resolve(hostRoot, "src/preflight.mjs")],
  ["/formal-host/src/protocol.mjs", resolve(hostRoot, "src/protocol.mjs")],
  ["/formal-host/src/state_machine.mjs", resolve(hostRoot, "src/state_machine.mjs")],
]);

test("source shell enforces activation, interruption, one-sequence recovery, and once-only cleanup", async ({ page }) => {
  for (const [pathname, source] of sourceRoutes) {
    await page.route(`**${pathname}`, async (route) => {
      const body = await readFile(source);
      const contentType = pathname.endsWith(".html")
        ? "text/html"
        : pathname.endsWith(".css")
          ? "text/css"
          : "text/javascript";
      await route.fulfill({ status: 200, contentType, body });
    });
  }

  await page.addInitScript(() => {
    class FakeAudioContext extends EventTarget {
      constructor(options) {
        super();
        this.sampleRate = options.sampleRate;
        this.state = "suspended";
      }
      async resume() {
        this.state = "running";
        this.dispatchEvent(new Event("statechange"));
      }
      async suspend() {
        this.state = "suspended";
        this.dispatchEvent(new Event("statechange"));
      }
      async close() {
        this.state = "closed";
      }
    }
    const notificationListeners = new Set();
    let sequence = 1;
    let cleanupCalls = 0;
    let projectExists = false;
    let projectRevision = 0;
    const operations = [];
    const project = {
      assets: {},
      banks: Array.from({ length: 4 }, (_, bank) => ({
        bank,
        pads: Array.from({ length: 16 }, (_, pad) => ({
          bank,
          pad,
          asset_id: null,
        })),
      })),
    };
    const worker = new EventTarget();
    const worklet = new EventTarget();
    window.__task9 = {
      operations,
      worker,
      worklet,
      emit(event, payload) {
        for (const listener of notificationListeners) {
          listener({ protocol_version: 1, event, payload });
        }
      },
      cleanupCalls: () => cleanupCalls,
    };
    window.__LMDJ_WEB_HOST_SEAMS__ = {
      capabilities: Object.fromEntries([
        "secureContext",
        "crossOriginIsolated",
        "sharedArrayBuffer",
        "webAssembly",
        "audioWorklet",
        "opfs",
        "opfsSyncAccessHandle",
        "opfsWritableReplace",
      ].map((name) => [name, true])),
      verifyManifest: async () => ({
        product_build: "1.0.15.1",
        host_version: "1.1.1",
        protocol_version: 1,
      }),
      loadRuntime: async () => ({
        registerAudioContext: () => 1,
        startAudioWorklet: async () => ({ ok: true }),
        workers: [worker],
        worklet,
      }),
      createAudioContext: (options) => new FakeAudioContext(options),
      navigator: { requestMIDIAccess: async () => ({ inputs: new Map() }) },
      transport: {
        async send(request, options) {
          operations.push({ operation: request.operation, payload: request.payload, options });
          if (request.operation === "project.open" && !projectExists) {
            return {
              protocol_version: 1,
              request_id: request.request_id,
              ok: false,
              error: { code: "NOT_FOUND", message: "NOT_FOUND", details: {} },
            };
          }
          if (request.operation === "project.create") {
            projectExists = true;
            projectRevision = 0;
          }
          if (request.operation === "asset.import") {
            project.assets[request.payload.asset_id] = {
              asset_id: request.payload.asset_id,
            };
            projectRevision += 1;
          }
          if (request.operation === "pad.assign") {
            project.banks[request.payload.slot.bank].pads[
              request.payload.slot.pad
            ].asset_id = request.payload.asset_id;
            projectRevision += 1;
          }
          const results = {
            "project.open": { project_revision: projectRevision },
            "project.create": { project_revision: projectRevision },
            "project.inspect": { project_revision: projectRevision, project },
            "asset.import": { project_revision: projectRevision },
            "pad.assign": { project_revision: projectRevision },
            "snapshot.reload": { runtime_ready: true, generation: 7 },
            "audio.activate": { state: "running", changed: true, generation: 7 },
            "audio.suspend": { state: "audio-suspended", changed: true },
            "host.status": { control_generation: 7, acknowledged_generation: 7 },
            "host.close": { state: "closed" },
          };
          const result = request.operation === "trigger"
            ? { sequence: sequence++, status: "enqueued" }
            : results[request.operation];
          return {
            protocol_version: 1,
            request_id: request.request_id,
            ok: true,
            result,
          };
        },
        subscribe(listener) {
          notificationListeners.add(listener);
          return () => notificationListeners.delete(listener);
        },
      },
      runtimeTerminator: async () => {
        cleanupCalls += 1;
      },
    };
  });

  await page.goto("/formal-host/index.html");
  await expect(page.locator("#host-state")).toHaveText("audio-suspended");
  await expect(page.locator("button[data-bank][data-pad]")).toHaveCount(64);
  await expect(page.locator("#audio-activate")).toBeDisabled();

  await page.locator("#pad-0").dispatchEvent("pointerdown", {
    isPrimary: true,
    button: 0,
    pointerId: 1,
  });
  expect(await page.evaluate(() => window.__task9.operations.filter(({ operation }) => operation === "trigger").length)).toBe(0);

  await page.locator("#diagnostic-project-load").click();
  await expect(page.locator("#diagnostic-project-state")).toHaveText("ready");
  await expect(page.locator("#audio-activate")).toBeEnabled();
  expect(await page.evaluate(() => ({
    creates: window.__task9.operations.filter(({ operation }) => operation === "project.create").length,
    imports: window.__task9.operations.filter(({ operation }) => operation === "asset.import").length,
    assignments: window.__task9.operations.filter(({ operation }) => operation === "pad.assign").length,
    inspections: window.__task9.operations.filter(({ operation }) => operation === "project.inspect").length,
    reloads: window.__task9.operations.filter(({ operation }) => operation === "snapshot.reload").length,
  }))).toEqual({
    creates: 1,
    imports: 1,
    assignments: 64,
    inspections: 2,
    reloads: 1,
  });

  await page.locator("#audio-activate").click();
  await expect(page.locator("#host-state")).toHaveText("running");
  await page.locator("#pad-0").dispatchEvent("pointerdown", {
    isPrimary: true,
    button: 0,
    pointerId: 2,
  });
  await expect.poll(() => page.evaluate(() => window.__task9.operations.filter(({ operation }) => operation === "trigger").length)).toBe(1);

  await page.evaluate(() => window.lmdjWebRuntimeController.observeVisibility(true));
  await expect(page.locator("#host-state")).toHaveText("recovering");
  await page.locator("#pad-1").dispatchEvent("pointerdown", {
    isPrimary: true,
    button: 0,
    pointerId: 3,
  });
  await page.locator("#pad-2").dispatchEvent("pointerdown", {
    isPrimary: true,
    button: 0,
    pointerId: 4,
  });
  await expect.poll(() => page.evaluate(() => window.__task9.operations.filter(({ operation }) => operation === "trigger").length)).toBe(2);
  await expect(page.locator("#host-state")).toHaveText("recovering");

  await page.evaluate(() => window.__task9.emit("runtime.trigger_outcomes", {
    events: [{ sequence: 2, outcome: "voice_started", runtime_frame: 128 }],
  }));
  await expect(page.locator("#host-state")).toHaveText("running");

  await page.evaluate(() => {
    window.__task9.worklet.dispatchEvent(new Event("processorerror"));
    window.__task9.worker.dispatchEvent(new Event("error"));
  });
  await expect(page.locator("#host-state")).toHaveText("failed");
  await expect.poll(() => page.evaluate(() => window.__task9.cleanupCalls())).toBe(1);
});
