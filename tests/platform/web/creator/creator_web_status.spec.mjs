import {writeFile} from "node:fs/promises";

import {expect, test} from "./fixtures/refusal_diagnostics.mjs";
import {openProjectPageAfterBoot, waitForProjectReopen} from "./fixtures/creator_boot.mjs";
import {countInProjectInventory} from "./fixtures/count_in_helpers.mjs";

const bundle = process.env.LMDJ_CREATOR_WEB_OVERVIEW_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_OVERVIEW_BUNDLE is required");

// This injects only a typed SDK failure notification. It neither establishes a
// Native failure nor models physical device loss. Original requests, close and
// terminal-owner receipts remain real. The independent lifecycle spec owns the
// genuine timeout/delivery-fault proof; runtime_context.test.tsx owns rejected
// shutdown barriers and negative cleanup results that this page seam cannot
// reproduce. No factory or owner-release result is synthesized here.
async function installFailureNotificationProbe(page) {
  await page.addInitScript(() => {
    let exposed;
    let generation = 0;
    const owners = new Map();
    const boundaries = [];
    const notifications = [];
    const terminalOwners = () => [...owners].map(([id, owner]) => ({
      generation: id,
      terminated: owner.transport.terminated,
      terminalOwnerReleased: owner.transport.terminalOwnerReleased,
    }));
    Object.defineProperty(window, "__LMDJ_WEB_HOST_SEAMS__", {
      get() {
        boundaries.push({generation: ++generation, priorOwners: terminalOwners()});
        return {};
      },
    });
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get() { return exposed; },
      set(host) {
        const id = generation;
        if (owners.has(id)) throw new Error("Runtime generation exposed more than one Native owner");
        const transport = host.transport;
        const listeners = new Set();
        owners.set(id, {transport, listeners});
        host.transport = Object.freeze({
          send(...args) { return transport.send(...args); },
          get sendRetained() {
            return typeof transport.sendRetained === "function"
              ? (...args) => transport.sendRetained(...args) : undefined;
          },
          subscribe(...args) { return transport.subscribe(...args); },
          subscribeFailure(listener) {
            listeners.add(listener);
            const unsubscribe = transport.subscribeFailure(listener);
            return () => { listeners.delete(listener); unsubscribe(); };
          },
          terminate(...args) { return transport.terminate(...args); },
          get terminated() { return transport.terminated; },
          get terminalOwnerReleased() { return transport.terminalOwnerReleased; },
        });
        exposed = host;
      },
    });
    window.__statusRecoveryProof = {
      snapshot: () => ({generations: generation, boundaries, notifications,
        owners: terminalOwners()}),
      fail(code) {
        const owner = owners.get(generation);
        if (!owner || owner.listeners.size !== 1 || owner.transport.terminated) {
          throw new Error("Failure fixture requires this generation's one live SDK subscriber");
        }
        notifications.push({generation, code, kind: "reduced-sdk-notification"});
        for (const listener of [...owner.listeners]) listener(Object.assign(
          new Error("Reduced Creator recovery notification fixture"), {code, details: {}}));
      },
    };
  });
}

async function truth(page) {
  const response = await page.evaluate(() => window.lmdjWebRuntimeHost.transport.send({
    protocol_version: 1, request_id: crypto.randomUUID(), operation: "project.inspect", payload: {},
  }));
  expect(response.ok, "the actual Project inspection must succeed").toBe(true);
  return response.result.project;
}

async function retainProof(testInfo, name, value) {
  const path = testInfo.outputPath(`${name}.json`);
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`);
  await testInfo.attach(name, {path, contentType: "application/json"});
}

for (const viewport of [{width: 648, height: 364}, {width: 1440, height: 900}]) {
  test(`manual Runtime recovery retains the Project and usable action ${viewport.width}x${viewport.height}`, async ({page, browserName}, testInfo) => {
    test.skip(browserName !== "chromium");
    test.setTimeout(300_000);
    const errors = [];
    page.on("pageerror", error => errors.push(String(error.message)));
    await page.setViewportSize(viewport);
    await installFailureNotificationProbe(page);
    await page.goto("/index.html");
    await openProjectPageAfterBoot(page);
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", {name: "Import .lmdj", exact: true}).click();
    await (await chooser).setFiles(bundle);
    await expect(page.getByRole("heading", {name: "Project 00000000", exact: true}))
      .toBeVisible({timeout: 120_000});
    const before = await truth(page);
    const inventory = await countInProjectInventory(page, before.project_id);
    expect(inventory.some(entry => entry.path.startsWith("assets/") && entry.bytes > 0)).toBe(true);

    // The first notification consumes the one automatic allowance. Deliberately
    // never activate audio: stable running would replenish it and test another
    // automatic replacement instead of the manual recovery path.
    await page.evaluate(() => window.__statusRecoveryProof.fail("HOST_RESTART_REQUIRED"));
    await expect.poll(() => page.evaluate(() => window.__statusRecoveryProof.snapshot().generations),
      {timeout: 120_000}).toBe(2);
    await expect(page.getByTestId("creator-phase")).toHaveText("ready", {timeout: 120_000});
    await expect(page.getByRole("heading", {name: "Project 00000000", exact: true})).toBeVisible();
    expect(await truth(page)).toEqual(before);

    await page.evaluate(() => window.__statusRecoveryProof.fail("HOST_TIMEOUT"));
    await expect(page.getByTestId("creator-phase")).toHaveText("restart-required");
    const notice = page.getByRole("alert").filter({hasText: "The audio engine stopped responding."});
    await expect(notice).toBeVisible();
    await expect(notice).toContainText("Your Project is saved and not affected.");
    await expect(notice).toContainText("Choose Retry runtime to restart it.");
    const retry = notice.getByRole("button", {name: "Retry runtime", exact: true});
    await expect(retry).toBeEnabled();
    await expect(page.getByRole("button", {name: "New Project", exact: true})).toBeDisabled();
    const geometry = await retry.evaluate(button => {
      const box = element => {const r = element.getBoundingClientRect();
        return {left: r.left, right: r.right, top: r.top, bottom: r.bottom,
          width: r.width, height: r.height};};
      const r = button.getBoundingClientRect();
      return {viewport: {width: innerWidth, height: innerHeight},
        panel: box(button.closest("[role=alert]")), action: box(button),
        hit: document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2) === button};
    });
    for (const rect of [geometry.panel, geometry.action]) {
      expect(rect.left).toBeGreaterThanOrEqual(0);
      expect(rect.top).toBeGreaterThanOrEqual(0);
      expect(rect.right).toBeLessThanOrEqual(viewport.width);
      expect(rect.bottom).toBeLessThanOrEqual(viewport.height);
    }
    expect(geometry.action.width).toBeGreaterThanOrEqual(44);
    expect(geometry.action.height).toBeGreaterThanOrEqual(44);
    expect(geometry.hit).toBe(true);
    const screenshot = testInfo.outputPath("runtime-retry.png");
    await page.screenshot({path: screenshot});
    await testInfo.attach("runtime-retry", {path: screenshot, contentType: "image/png"});

    await page.getByRole("button", {name: "System", exact: true}).click();
    await page.getByText(/^Developer diagnostics \(\d+\)$/).click();
    await expect(page.getByRole("region", {name: "Developer diagnostics"})).toContainText("HOST_TIMEOUT");
    await page.getByRole("button", {name: "Back to music", exact: true}).click();
    expect((await page.evaluate(() => window.__statusRecoveryProof.snapshot())).generations).toBe(2);

    await retry.focus();
    await expect(retry).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("creator-phase")).toHaveText("ready", {timeout: 120_000});
    await expect(notice).toHaveCount(0);
    await expect(page.getByRole("heading", {name: "Project 00000000", exact: true})).toBeVisible();
    expect(await truth(page)).toEqual(before);
    expect(await countInProjectInventory(page, before.project_id)).toEqual(inventory);
    const proof = await page.evaluate(() => window.__statusRecoveryProof.snapshot());
    expect(proof.generations).toBe(3);
    expect(proof.notifications).toEqual([
      {generation: 1, code: "HOST_RESTART_REQUIRED", kind: "reduced-sdk-notification"},
      {generation: 2, code: "HOST_TIMEOUT", kind: "reduced-sdk-notification"},
    ]);
    for (const generation of [2, 3]) {
      expect(proof.boundaries.find(entry => entry.generation === generation).priorOwners)
        .toContainEqual({generation: generation - 1, terminated: true, terminalOwnerReleased: true});
    }
    await retainProof(testInfo, "manual-runtime-recovery", {viewport, geometry, before, inventory, proof});

    await page.reload();
    await waitForProjectReopen(page, "00000000");
    expect(await truth(page)).toEqual(before);
    expect(await countInProjectInventory(page, before.project_id)).toEqual(inventory);
    expect(errors).toEqual([]);
  });
}
