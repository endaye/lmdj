import {expect, test} from "@playwright/test";

import {REPLACEMENT_FAULT_POINTS} from "./project_io_web_faults.mjs";

const STORAGE_CAPABILITY_ORDER = Object.freeze([
  "opfs",
  "opfsSyncAccessHandle",
  "opfsWritableReplace",
]);

async function inspectStorageCapabilities(page) {
  return page.evaluate(async (order) => {
    const source = `
      onmessage = async () => {
        const capabilities = {opfs: false, opfsSyncAccessHandle: false, opfsWritableReplace: false};
        try {
          capabilities.opfs = typeof navigator.storage?.getDirectory === "function";
          if (capabilities.opfs) {
            const root = await navigator.storage.getDirectory();
            const file = await root.getFileHandle(".lmdj-project-io-capability", {create: true});
            capabilities.opfsSyncAccessHandle = typeof file.createSyncAccessHandle === "function";
            capabilities.opfsWritableReplace = typeof file.createWritable === "function";
            await root.removeEntry(".lmdj-project-io-capability");
          }
        } catch (_) {}
        postMessage(capabilities);
      };
    `;
    const url = URL.createObjectURL(new Blob([source], {type: "text/javascript"}));
    const capabilities = await new Promise((resolve) => {
      const worker = new Worker(url);
      worker.onmessage = ({data}) => { worker.terminate(); resolve(data); };
      worker.postMessage(null);
    });
    URL.revokeObjectURL(url);
    const missing = order.filter((name) => capabilities[name] !== true);
    return missing.length === 0
      ? {status: "supported", missing: [], capabilities}
      : {status: "unsupported", error: {code: "UNSUPPORTED_WEB_RUNTIME", missing}, capabilities};
  }, STORAGE_CAPABILITY_ORDER);
}


async function waitForResult(page) {
  await page.waitForFunction(() => window.lmdjProjectIoWeb?.complete === true);
  return page.evaluate(() => window.lmdjProjectIoWeb.result);
}

async function writeFaultControl(page, bundle, point) {
  await page.evaluate(async ({bundle, point}) => {
    const root = await navigator.storage.getDirectory();
    const host = await root.getDirectoryHandle(".lmdj-host", {create: true});
    await host.removeEntry("test-fault-reached").catch(() => {});
    const control = await host.getFileHandle("test-fault.json", {create: true});
    const writable = await control.createWritable({keepExistingData: false});
    await writable.write(JSON.stringify({bundle: `${bundle}.lmdj`, point}));
    await writable.close();
  }, {bundle, point});
}

async function waitForFault(page, point) {
  await expect.poll(() => page.evaluate(async () => {
    try {
      const root = await navigator.storage.getDirectory();
      const host = await root.getDirectoryHandle(".lmdj-host");
      return (await (await host.getFileHandle("test-fault-reached")).getFile()).text();
    } catch (_) { return ""; }
  })).toBe(point);
}

async function clearFaultControl(page) {
  await page.evaluate(async () => {
    const root = await navigator.storage.getDirectory();
    const host = await root.getDirectoryHandle(".lmdj-host");
    await host.removeEntry("test-fault.json").catch(() => {});
    await host.removeEntry("test-fault-reached").catch(() => {});
  });
}

async function acquireLeaseWorker(page, projectPath) {
  return page.evaluate(async (path) => {
    const source = `
      let access;
      const hex = (bytes) => [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
      onmessage = async ({data}) => {
        try {
          const parts = data.replaceAll("\\\\", "/").split("/").filter((part) => part && part !== ".");
          if (parts[0] === "lmdj-workspace") parts.shift();
          if (parts.includes("..")) throw new DOMException("", "InvalidStateError");
          const canonical = "/lmdj-workspace/" + parts.join("/");
          const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical)));
          const name = hex(digest) + ".lock";
          const origin = await navigator.storage.getDirectory();
          const host = await origin.getDirectoryHandle(".lmdj-host", {create: true});
          const leases = await host.getDirectoryHandle("leases", {create: true});
          const file = await leases.getFileHandle(name, {create: true});
          access = await file.createSyncAccessHandle();
          if (access.getSize() === 0) {
            const identity = crypto.getRandomValues(new Uint8Array(32));
            access.write(identity, {at: 0});
            access.flush();
          }
          const identity = new Uint8Array(access.getSize());
          access.read(identity, {at: 0});
          postMessage({status: "acquired", identity: hex(identity)});
        } catch (error) {
          postMessage({status: error?.name === "NoModificationAllowedError" ? "project_busy" : "io_error"});
        }
      };
    `;
    const worker = new Worker(URL.createObjectURL(new Blob([source], {type: "text/javascript"})));
    window.__lmdjLeaseWorkers ??= [];
    window.__lmdjLeaseWorkers.push(worker);
    const result = await new Promise((resolve) => {
      worker.onmessage = ({data}) => resolve(data);
      worker.postMessage(path);
    });
    return {...result, workerIndex: window.__lmdjLeaseWorkers.length - 1};
  }, projectPath);
}

async function terminateLeaseWorker(page, workerIndex) {
  await page.evaluate((index) => window.__lmdjLeaseWorkers[index].terminate(), workerIndex);
}

test("Web Project I/O runs common parity and interruption recovery", async ({page, context, browserName}, testInfo) => {
  await page.goto("/preflight.html");
  const capabilities = await inspectStorageCapabilities(page);
  if (capabilities.status === "unsupported") {
    expect(browserName).toBe("webkit");
    expect(capabilities.error).toEqual({
      code: "UNSUPPORTED_WEB_RUNTIME",
      missing: STORAGE_CAPABILITY_ORDER.filter(
          (name) => capabilities.capabilities[name] !== true),
    });
    testInfo.annotations.push({
      type: "platform-limitation",
      description: capabilities.error.missing.join(","),
    });
    console.log(`WebKit Project I/O capability limitation: ${JSON.stringify(capabilities)}`);
    return;
  }
  await page.goto("/project_io/project_io_web_test.html");
  const result = await waitForResult(page);

  expect(result.projectStore).toBe("pass");
  expect(result.takeJournal).toBe("pass");
  expect(result.replay).toBe("pass");
  expect(result.recovery).toBe("pass");
  expect(result.appendContracts).toBe("pass");
  expect(result.lease).toBe("pass");
  expect(result.directoryBarrier).toBe("absent");
  expect(result.replacementFaultPoints).toEqual(REPLACEMENT_FAULT_POINTS);

  const firstLeasePage = await context.newPage();
  const competingLeasePage = await context.newPage();
  await firstLeasePage.goto("/preflight.html");
  await competingLeasePage.goto("/preflight.html");
  const leasePath = `lease-${Date.now()}.lmdj`;
  const firstLease = await acquireLeaseWorker(firstLeasePage, `/lmdj-workspace/${leasePath}`);
  expect(firstLease.status).toBe("acquired");
  const busyLease = await acquireLeaseWorker(competingLeasePage, leasePath);
  expect(busyLease.status).toBe("project_busy");
  await terminateLeaseWorker(firstLeasePage, firstLease.workerIndex);
  let reacquiredLease;
  await expect.poll(async () => {
    reacquiredLease = await acquireLeaseWorker(competingLeasePage, `/lmdj-workspace/${leasePath}`);
    return reacquiredLease.status;
  }).toBe("acquired");
  expect(reacquiredLease.identity).toBe(firstLease.identity);
  await terminateLeaseWorker(competingLeasePage, reacquiredLease.workerIndex);
  await firstLeasePage.close();
  await competingLeasePage.close();

  for (const [index, point] of REPLACEMENT_FAULT_POINTS.entries()) {
    const bundle = `fault-${index}-${Date.now()}`;
    const prepare = await context.newPage();
    await prepare.goto(`/project_io/project_io_web_test.html?action=prepare&bundle=${bundle}`);
    expect((await waitForResult(prepare)).revision).toBe(0);
    await writeFaultControl(prepare, bundle, point);

    const interrupted = await context.newPage();
    await interrupted.goto(`/project_io/project_io_web_test.html?action=advance&bundle=${bundle}`);
    await waitForFault(prepare, point);
    await interrupted.close();
    await clearFaultControl(prepare);

    const restarted = await context.newPage();
    await restarted.goto(`/project_io/project_io_web_test.html?action=reopen&bundle=${bundle}`);
    const expectedRevision = ["after_close", "before_cleanup"].includes(point) ? 1 : 0;
    expect((await waitForResult(restarted)).revision).toBe(expectedRevision);
    await restarted.close();
    await prepare.close();
  }
});
