import {expect, test} from "@playwright/test";

import {REPLACEMENT_FAULT_POINTS} from "./project_io_web_faults.mjs";

const STORAGE_CAPABILITY_ORDER = Object.freeze([
  "opfs",
  "opfsSyncAccessHandle",
  "opfsWritableReplace",
]);
const FAULT_REACHED_OBSERVATION_TIMEOUT_MS = 15_000;

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

async function writeFaultControl(page, destination, point) {
  await page.evaluate(async ({destination, point}) => {
    const root = await navigator.storage.getDirectory();
    const host = await root.getDirectoryHandle(".lmdj-host", {create: true});
    await host.removeEntry("test-fault-reached").catch(() => {});
    const control = await host.getFileHandle("test-fault.json", {create: true});
    const writable = await control.createWritable({keepExistingData: false});
    await writable.write(JSON.stringify({destination, point}));
    await writable.close();
  }, {destination, point});
}

async function waitForFault(page, point) {
  await expect.poll(() => page.evaluate(async () => {
    try {
      const root = await navigator.storage.getDirectory();
      const host = await root.getDirectoryHandle(".lmdj-host");
      return (await (await host.getFileHandle("test-fault-reached")).getFile()).text();
    } catch (_) { return ""; }
  }), {timeout: FAULT_REACHED_OBSERVATION_TIMEOUT_MS}).toBe(point);
}

async function clearFaultControl(page) {
  await page.evaluate(async () => {
    const root = await navigator.storage.getDirectory();
    const host = await root.getDirectoryHandle(".lmdj-host");
    await host.removeEntry("test-fault.json").catch(() => {});
    await host.removeEntry("test-fault-reached").catch(() => {});
  });
}

async function snapshotLeaseEntries(page) {
  await page.evaluate(async () => {
    const root = await navigator.storage.getDirectory();
    const host = await root.getDirectoryHandle(".lmdj-host", {create: true});
    const leases = await host.getDirectoryHandle("leases", {create: true});
    window.__lmdjLeaseEntriesBefore = new Set();
    for await (const entry of leases.values()) {
      if (entry.kind === "file") window.__lmdjLeaseEntriesBefore.add(entry.name);
    }
  });
}

async function captureNewLeaseEntry(page) {
  return page.evaluate(async () => {
    const root = await navigator.storage.getDirectory();
    const host = await root.getDirectoryHandle(".lmdj-host");
    const leases = await host.getDirectoryHandle("leases");
    for await (const entry of leases.values()) {
      if (entry.kind === "file" && !window.__lmdjLeaseEntriesBefore.has(entry.name)) {
        window.__lmdjHeldLeaseEntry = entry;
        window.__lmdjHeldLeaseName = entry.name;
        return entry.name;
      }
    }
    return "";
  });
}

async function compareReacquiredLeaseEntry(page) {
  return page.evaluate(async () => {
    const root = await navigator.storage.getDirectory();
    const host = await root.getDirectoryHandle(".lmdj-host");
    const leases = await host.getDirectoryHandle("leases");
    const current = await leases.getFileHandle(window.__lmdjHeldLeaseName);
    return window.__lmdjHeldLeaseEntry.isSameEntry(current);
  });
}

test("Web Project I/O runs common parity and interruption recovery", async ({page, context, browserName}, testInfo) => {
  test.setTimeout(120_000);
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
  expect(result.mountFailure).toBe("pass");
  expect(result.idempotentRemove).toBe("pass");
  expect(result.immutableShortWrites).toBe("pass");
  const directoryMoveSupported = await page.evaluate(
      () => typeof FileSystemDirectoryHandle.prototype.move === "function");
  expect(result.directoryTransfer).toBe(
      directoryMoveSupported ? "pass" : "unsupported");
  expect(result.directoryBarrier).toBe("absent");
  expect(result.replacementFaultPoints).toEqual(REPLACEMENT_FAULT_POINTS);

  const leaseInspector = await context.newPage();
  const firstLeasePage = await context.newPage();
  const competingLeasePage = await context.newPage();
  await leaseInspector.goto("/preflight.html");
  await snapshotLeaseEntries(leaseInspector);
  const leasePath = `lease-${Date.now()}.lmdj`;
  await firstLeasePage.goto(
      `/project_io/project_io_web_test.html?action=hold_lease&bundle=${leasePath.slice(0, -5)}`);
  expect((await waitForResult(firstLeasePage)).lease).toBe("held");
  expect(await captureNewLeaseEntry(leaseInspector)).not.toBe("");
  await competingLeasePage.goto(
      `/project_io/project_io_web_test.html?action=hold_lease&bundle=${leasePath.slice(0, -5)}`);
  expect(await waitForResult(competingLeasePage)).toEqual({
    lease: "failed",
    errorCode: "IO_ERROR",
    storageCondition: "project_busy",
  });
  await firstLeasePage.close();
  await expect.poll(async () => {
    await competingLeasePage.reload();
    return (await waitForResult(competingLeasePage)).lease;
  }).toBe("held");
  expect(await compareReacquiredLeaseEntry(leaseInspector)).toBe(true);
  await competingLeasePage.close();
  await leaseInspector.close();

  for (const [index, point] of REPLACEMENT_FAULT_POINTS.entries()) {
    const bundle = `fault-${index}-${Date.now()}`;
    const prepare = await context.newPage();
    await prepare.goto(`/project_io/project_io_web_test.html?action=prepare&bundle=${bundle}`);
    expect((await waitForResult(prepare)).revision).toBe(0);
    await writeFaultControl(
        prepare, `/lmdj-workspace/${bundle}.lmdj/manifest.json`, point);

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

  for (const [index, point] of REPLACEMENT_FAULT_POINTS.entries()) {
    const bundle = `absent-fault-${index}-${Date.now()}`;
    const prepare = await context.newPage();
    await prepare.goto(
        `/project_io/project_io_web_test.html?action=prepare_replacement&scenario=absent&bundle=${bundle}`);
    expect((await waitForResult(prepare)).state).toBe("absent");
    await writeFaultControl(
        prepare, `/lmdj-workspace/${bundle}.lmdj/replacement.bin`, point);

    const interrupted = await context.newPage();
    await interrupted.goto(
        `/project_io/project_io_web_test.html?action=replace&scenario=absent&bundle=${bundle}`);
    await waitForFault(prepare, point);
    await interrupted.close();
    await clearFaultControl(prepare);

    const restarted = await context.newPage();
    await restarted.goto(
        `/project_io/project_io_web_test.html?action=reopen_replacement&scenario=absent&bundle=${bundle}`);
    const expectedState = ["after_close", "before_cleanup"].includes(point)
      ? "new"
      : "absent";
    expect((await waitForResult(restarted)).state).toBe(expectedState);
    await restarted.close();
    await prepare.close();
  }

  const corruptBundle = `corrupt-existing-${Date.now()}`;
  const corruptController = await context.newPage();
  await corruptController.goto(
      `/project_io/project_io_web_test.html?action=prepare_replacement&scenario=existing&bundle=${corruptBundle}`);
  expect((await waitForResult(corruptController)).state).toBe("existing");
  const corruptDestination =
      `/lmdj-workspace/${corruptBundle}.lmdj/replacement.bin`;
  await writeFaultControl(corruptController, corruptDestination, "before_write");
  const corruptWriter = await context.newPage();
  await corruptWriter.goto(
      `/project_io/project_io_web_test.html?action=replace&scenario=existing&bundle=${corruptBundle}`);
  await waitForFault(corruptController, "before_write");
  await corruptController.evaluate(async ({bundle}) => {
    const root = await navigator.storage.getDirectory();
    const directory = await root.getDirectoryHandle(`${bundle}.lmdj`);
    const file = await directory.getFileHandle("replacement.bin");
    const writable = await file.createWritable({keepExistingData: false});
    await writable.write("partial");
    await writable.close();
  }, {bundle: corruptBundle});
  await corruptWriter.close();
  await clearFaultControl(corruptController);

  const recovery = await context.newPage();
  await recovery.goto(
      `/project_io/project_io_web_test.html?action=recover&scenario=existing&bundle=${corruptBundle}`);
  expect(await waitForResult(recovery)).toEqual({
    recovery: "failed",
    errorCode: "IO_ERROR",
    storageCondition: "",
  });
  const preservedEvidence = await corruptController.evaluate(async ({bundle}) => {
    const root = await navigator.storage.getDirectory();
    const destination = await (await (
      await root.getDirectoryHandle(`${bundle}.lmdj`)
    ).getFileHandle("replacement.bin")).getFile();
    const intents = await root.getDirectoryHandle(".lmdj-host")
        .then((host) => host.getDirectoryHandle("storage-intents"));
    let count = 0;
    for await (const projectDirectory of intents.values()) {
      if (projectDirectory.kind !== "directory") continue;
      for await (const entry of projectDirectory.values()) {
        if (entry.kind === "file") count += 1;
      }
    }
    return {destination: await destination.text(), intentCount: count};
  }, {bundle: corruptBundle});
  expect(preservedEvidence.destination).toBe("partial");
  expect(preservedEvidence.intentCount).toBeGreaterThan(0);
  await recovery.close();
  await corruptController.close();

  const immutableBundle = `immutable-partial-${Date.now()}`;
  const immutableController = await context.newPage();
  await immutableController.goto(
      `/project_io/project_io_web_test.html?action=prepare_immutable&bundle=${immutableBundle}`);
  expect((await waitForResult(immutableController)).state).toBe("absent");
  await writeFaultControl(
      immutableController,
      `/lmdj-workspace/${immutableBundle}.lmdj/immutable.bin`,
      "during_write");
  const immutableWriter = await context.newPage();
  await immutableWriter.goto(
      `/project_io/project_io_web_test.html?action=create_immutable_fault&bundle=${immutableBundle}`);
  await waitForFault(immutableController, "during_write");
  await immutableWriter.close();
  await clearFaultControl(immutableController);
  const immutableRestarted = await context.newPage();
  await immutableRestarted.goto(
      `/project_io/project_io_web_test.html?action=reopen_immutable&bundle=${immutableBundle}`);
  expect((await waitForResult(immutableRestarted)).state).toBe("immutable-retry");
  await immutableRestarted.close();
  await immutableController.close();
});
