import {expect, test} from "@playwright/test";
import {createHash} from "node:crypto";
import {readFile} from "node:fs/promises";

import {
  PUBLICATION_CLEANUP_FAULT,
  PUBLICATION_FAULT_POINTS,
  REPLACEMENT_FAULT_POINTS,
  SEQUENCE_FLUSH_FAULT_POINTS,
  STORAGE_CONDITION_FAULTS,
  replacementReachedCommit,
} from "./project_io_web_faults.mjs";

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const keys = Object.keys(value).sort((left, right) =>
      Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8")));
    return `{${keys.map((key) =>
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

test("SR-D22 fingerprint vectors are byte-exact in JavaScript", async () => {
  const vectorUrl = new URL(
    "../../../fixtures/golden/sequence-pattern-fingerprint-v1.json",
    import.meta.url);
  const document = JSON.parse(await readFile(vectorUrl, "utf8"));
  expect(document.contract).toBe("lmdj.sequence-pattern-fingerprint-v1");
  for (const vector of document.vectors) {
    const bytes = Buffer.from(vector.canonical_json, "utf8");
    expect(bytes.subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf]))).toBe(false);
    expect(bytes.at(-1)).not.toBe(0x0a);
    expect(canonicalJson(JSON.parse(vector.canonical_json))).toBe(
      vector.canonical_json);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(vector.sha256);
  }
  expect(SEQUENCE_FLUSH_FAULT_POINTS).toEqual([
    "journal_write",
    "transaction_write",
    "checkpoint_write",
    "manifest_publish",
    "receipt_reload",
    "journal_completion",
    "journal_deletion",
  ]);
});

const STORAGE_CAPABILITY_ORDER = Object.freeze([
  "opfs",
  "opfsSyncAccessHandle",
  "opfsWritableReplace",
]);
const FAULT_REACHED_OBSERVATION_TIMEOUT_MS = 60_000;
const TERMINAL_REPORT_TIMEOUT_MS = 180_000;
const PROJECT_IO_CONFORMANCE_TIMEOUT_MS = 600_000;
const RUNTIME_ERROR_OBSERVERS = new WeakMap();

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


function runtimeFailure(error) {
  return new Error(
      `Web Project I/O runtime failed: ${error?.message ?? String(error)}`,
      {cause: error});
}

function trackRuntimeErrors(page) {
  if (RUNTIME_ERROR_OBSERVERS.has(page)) return page;
  const observer = {error: null, waiters: new Set()};
  const onPageError = (error) => {
    observer.error ??= error;
    const failure = runtimeFailure(observer.error);
    for (const reject of observer.waiters) reject(failure);
    observer.waiters.clear();
  };
  page.on("pageerror", onPageError);
  page.once("close", () => {
    page.off("pageerror", onPageError);
    RUNTIME_ERROR_OBSERVERS.delete(page);
  });
  RUNTIME_ERROR_OBSERVERS.set(page, observer);
  return page;
}

async function trackedPage(context) {
  return trackRuntimeErrors(await context.newPage());
}

async function waitForResult(page) {
  const observer = RUNTIME_ERROR_OBSERVERS.get(page);
  if (!observer) {
    throw new Error("Project I/O page was not tracked before navigation");
  }
  const awaitTerminalReport = async () => {
    try {
      await page.waitForFunction(
          () => window.lmdjProjectIoWeb?.complete === true,
          undefined,
          {timeout: 250});
      return true;
    } catch (_) {
      return false;
    }
  };
  if (observer.error && !(await awaitTerminalReport())) {
    throw runtimeFailure(observer.error);
  }

  let rejectRuntimeError;
  const runtimeError = new Promise((_, reject) => {
    rejectRuntimeError = reject;
    observer.waiters.add(reject);
  });
  try {
    try {
      await Promise.race([
        page.waitForFunction(
            () => window.lmdjProjectIoWeb?.complete === true,
            undefined,
            {timeout: TERMINAL_REPORT_TIMEOUT_MS}),
        runtimeError,
      ]);
    } catch (error) {
      // PROXY_TO_PTHREAD teardown in pinned Emscripten can surface after the
      // native suite has synchronously published its terminal report. Keep
      // pre-terminal runtime failures fail-closed, but let the report remain
      // authoritative once publication is complete.
      if (!(await awaitTerminalReport())) {
        const progress = await page.evaluate(
            () => window.lmdjProjectIoWebProgress ?? "unreported").catch(
            () => "unavailable");
        throw new Error(`${error.message}; last native stage: ${progress}`, {
          cause: error,
        });
      }
    }
    if (observer.error && !(await awaitTerminalReport())) {
      throw runtimeFailure(observer.error);
    }
    const result = await page.evaluate(() => window.lmdjProjectIoWeb.result);
    if (result?.error) {
      throw new Error(`Web Project I/O native runtime failed: ${result.error}`);
    }
    return result;
  } finally {
    observer.waiters.delete(rejectRuntimeError);
  }
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

// Every checkpoint this Build writes carries the lmdj.project.v4 shape,
// including the Pattern Slot and Performance carriers v3 has no room for.
const CHECKPOINT_V4_KEYS = [
  "assets",
  "banks",
  "bpm",
  "contract",
  "pattern_slots",
  "patterns",
  "performances",
  "project_id",
  "revision",
  "sequence_settings",
];

async function readCheckpointShape(page, bundle, revision) {
  return page.evaluate(async ({bundle, revision}) => {
    const root = await navigator.storage.getDirectory();
    const project = await root.getDirectoryHandle(`${bundle}.lmdj`);
    const history = await project.getDirectoryHandle("history");
    const checkpoints = await history.getDirectoryHandle("checkpoints");
    const file = await (await checkpoints.getFileHandle(`${revision}.json`)).getFile();
    const checkpoint = JSON.parse(await file.text());
    const pad = checkpoint.banks[0].pads[0];
    return {
      contract: checkpoint.contract,
      checkpointKeys: Object.keys(checkpoint).sort(),
      padKeys: Object.keys(pad).sort(),
      playbackKeys: pad.playback ? Object.keys(pad.playback).sort() : [],
    };
  }, {bundle, revision});
}

async function preparePublicationFixture(page, bundle) {
  await page.evaluate(async ({bundle}) => {
    const root = await navigator.storage.getDirectory();
    await root.removeEntry(`${bundle}.lmdj`, {recursive: true}).catch(() => {});
    const host = await root.getDirectoryHandle(".lmdj-host", {create: true});
    const fixtures = await host.getDirectoryHandle(
        "publication-fixtures", {create: true});
    await fixtures.removeEntry(bundle, {recursive: true}).catch(() => {});
    const source = await fixtures.getDirectoryHandle(bundle, {create: true});
    const nested = await source.getDirectoryHandle("nested", {create: true});
    const payload = await nested.getFileHandle("payload.bin", {create: true});
    const bytes = new Uint8Array(1_048_593);
    for (let index = 0; index < bytes.length; ++index) {
      bytes[index] = index % 251;
    }
    const writable = await payload.createWritable({keepExistingData: false});
    await writable.write(bytes);
    await writable.close();
  }, {bundle});
}

async function writeMalformedPublicationIntent(page, bundle) {
  await page.evaluate(async ({bundle}) => {
    const destination = `/lmdj-workspace/${bundle}.lmdj`;
    const digest = new Uint8Array(await crypto.subtle.digest(
        "SHA-256", new TextEncoder().encode(destination)));
    const scope = [...digest]
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
    const root = await navigator.storage.getDirectory();
    const partial = await root.getDirectoryHandle(
        `${bundle}.lmdj`, {create: true});
    const partialFile = await partial.getFileHandle("partial.bin", {create: true});
    const partialWritable = await partialFile.createWritable();
    await partialWritable.write("partial");
    await partialWritable.close();
    const host = await root.getDirectoryHandle(".lmdj-host", {create: true});
    const intents = await host.getDirectoryHandle("storage-intents", {create: true});
    const directory = await intents.getDirectoryHandle(scope, {create: true});
    const marker = await directory.getFileHandle(
        "directory-publication.json", {create: true});
    const writable = await marker.createWritable({keepExistingData: false});
    await writable.write("{");
    await writable.close();
  }, {bundle});
}

async function intentScopeKeys(page, bundle) {
  return page.evaluate(async ({bundle}) => {
    const hex = async (input) => {
      const digest = new Uint8Array(await crypto.subtle.digest(
          "SHA-256", new TextEncoder().encode(input)));
      return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    };
    const project = `/lmdj-workspace/${bundle}.lmdj`;
    return {
      scope: await hex(project),
      replacement: `${await hex(`${project}/replacement.bin`)}.json`,
    };
  }, {bundle});
}

async function readPublicationIntentState(page, bundle) {
  const {scope} = await intentScopeKeys(page, bundle);
  return page.evaluate(async ({scope}) => {
    try {
      const root = await navigator.storage.getDirectory();
      const host = await root.getDirectoryHandle(".lmdj-host");
      const intents = await host.getDirectoryHandle("storage-intents");
      const directory = await intents.getDirectoryHandle(scope);
      const file = await (await directory.getFileHandle(
          "directory-publication.json")).getFile();
      return JSON.parse(await file.text()).state;
    } catch (_) {
      return "absent";
    }
  }, {scope});
}

async function storageIntentPresent(page, bundle) {
  const {scope, replacement} = await intentScopeKeys(page, bundle);
  return page.evaluate(async ({scope, replacement}) => {
    try {
      const root = await navigator.storage.getDirectory();
      const host = await root.getDirectoryHandle(".lmdj-host");
      const intents = await host.getDirectoryHandle("storage-intents");
      const directory = await intents.getDirectoryHandle(scope);
      await directory.getFileHandle(replacement);
      return true;
    } catch (_) {
      return false;
    }
  }, {scope, replacement});
}

async function writeStorageIntentBody(page, bundle, body) {
  const {scope, replacement} = await intentScopeKeys(page, bundle);
  await page.evaluate(async ({scope, replacement, body}) => {
    const root = await navigator.storage.getDirectory();
    const host = await root.getDirectoryHandle(".lmdj-host", {create: true});
    const intents = await host.getDirectoryHandle(
        "storage-intents", {create: true});
    const directory = await intents.getDirectoryHandle(scope, {create: true});
    const handle = await directory.getFileHandle(replacement, {create: true});
    const writable = await handle.createWritable({keepExistingData: false});
    await writable.write(body);
    await writable.close();
  }, {scope, replacement, body});
}

// The bytes a published Sound Set actually holds, read straight out of OPFS
// so the content address the Set Store chose can be checked against them
// rather than against another number the same report produced.
async function readPublishedSoundSetManifest(page, manifestSha256) {
  return page.evaluate(async ({manifestSha256}) => {
    const root = await navigator.storage.getDirectory();
    const host = await root.getDirectoryHandle(".lmdj-host");
    const sets = await host.getDirectoryHandle("soundsets");
    const set = await sets.getDirectoryHandle(manifestSha256);
    return (await (await set.getFileHandle("manifest.json")).getFile()).text();
  }, {manifestSha256});
}

// What an interrupted directory publication leaves behind at one of the fault
// points `PUBLICATION_FAULT_POINTS` enumerates: the staging source (only
// removed after the commit), a destination that exists, and a pending
// `lmdj.storage.directory-publication.v1` intent hiding it from enumeration.
// `during_directory_copy` leaves the destination incomplete;
// `after_directory_copy` leaves it complete and still uncommitted, which reads
// perfectly and is not published. Only acquiring the destination writer lease
// clears either.
async function wedgeInterruptedSoundSetPublication(page, manifestSha256, point) {
  return page.evaluate(async ({manifestSha256, point}) => {
    const destination =
        `/lmdj-workspace/.lmdj-host/soundsets/${manifestSha256}`;
    const source =
        `/lmdj-workspace/.lmdj-host/soundset-staging/${manifestSha256}`;
    const digest = new Uint8Array(await crypto.subtle.digest(
        "SHA-256", new TextEncoder().encode(destination)));
    const scope = [...digest]
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
    const root = await navigator.storage.getDirectory();
    const host = await root.getDirectoryHandle(".lmdj-host");
    const sets = await host.getDirectoryHandle("soundsets");
    const set = await sets.getDirectoryHandle(manifestSha256);
    // The staging source a real interruption always leaves, copied out of the
    // published Set so its bytes are the Set's own.
    const staging = await host.getDirectoryHandle(
        "soundset-staging", {create: true});
    const orphan = await staging.getDirectoryHandle(
        manifestSha256, {create: true});
    for await (const entry of set.values()) {
      const copy = await orphan.getFileHandle(entry.name, {create: true});
      const writable = await copy.createWritable({keepExistingData: false});
      await writable.write(await (await entry.getFile()).arrayBuffer());
      await writable.close();
    }
    if (point === "during_directory_copy") {
      await set.removeEntry("manifest.json");
    }
    const intents = await host.getDirectoryHandle(
        "storage-intents", {create: true});
    const directory = await intents.getDirectoryHandle(scope, {create: true});
    const marker = await directory.getFileHandle(
        "directory-publication.json", {create: true});
    const writable = await marker.createWritable({keepExistingData: false});
    await writable.write(JSON.stringify({
      contract: "lmdj.storage.directory-publication.v1",
      destination,
      source,
      state: "pending",
    }));
    await writable.close();
    const remaining = [];
    for await (const entry of set.values()) {
      remaining.push(entry.name);
    }
    const staged = [];
    for await (const entry of orphan.values()) {
      staged.push(entry.name);
    }
    return {remaining: remaining.length, staged: staged.length};
  }, {manifestSha256, point});
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

test("Web Project I/O reports page runtime failures without waiting for the suite timeout", async ({page}) => {
  trackRuntimeErrors(page);
  await page.goto("/preflight.html");
  const startedAt = Date.now();
  const failure = expect(waitForResult(page)).rejects.toThrow(
      "Web Project I/O runtime failed: project-io-pageerror-proof");
  await page.evaluate(() => {
    setTimeout(() => {
      throw new Error("project-io-pageerror-proof");
    }, 0);
  });
  await failure;
  expect(Date.now() - startedAt).toBeLessThan(5_000);
});

test("Web Project I/O preserves a terminal native report across worker teardown", async ({page}) => {
  trackRuntimeErrors(page);
  await page.goto("/preflight.html");
  const result = {terminal: "pass"};
  const pending = waitForResult(page);
  await page.evaluate(() => {
    setTimeout(() => {
      throw new Error("project-io-post-terminal-teardown-proof");
    }, 0);
    setTimeout(() => {
      window.lmdjProjectIoWeb = {complete: true, result: {terminal: "pass"}};
    }, 25);
  });
  expect(await pending).toEqual(result);
});

test("Web Project I/O binds every mutation to its same-page platform owner", async ({page, browserName}) => {
  test.skip(
      browserName !== "chromium",
      "owner-binding conformance requires OPFS sync access handles");
  trackRuntimeErrors(page);
  const bundle = `distinct-platform-owner-${Date.now()}`;
  await page.goto(
      `/project_io/project_io_web_test.html?action=distinct_platform_mutation_ownership&bundle=${bundle}`);
  const result = await waitForResult(page);

  const projectBusy = {
    status: "failed",
    errorCode: "IO_ERROR",
    storageCondition: "project_busy",
  };
  expect(result.acquisition).toEqual(projectBusy);
  expect(result.append).toEqual(projectBusy);
  expect(result.replace).toEqual(projectBusy);
  expect(result.create).toEqual(projectBusy);
  expect(result.existingCreate).toEqual({
    status: "failed",
    errorCode: "IO_ERROR",
    storageCondition: "already_exists",
  });
  expect(result.publish).toEqual(projectBusy);
  expect(result.afterAppend).toEqual({length: 4, content: "seed"});
  expect(result.afterReplace).toEqual({length: 4, content: "seed"});
  expect(result.absentAfterCreate).toBe(true);
  expect(result.publicationSourceAfter).toBe(true);
  expect(result.publicationDestinationAfter).toBe(false);
  expect(result.intentEntriesAfter).toBe(result.intentEntriesBefore);
  expect(result.intentInventoryUnchanged).toBe(true);
  expect(result.ownerContent).toBe("seed-owner");
  expect(result.postReleaseAcquisition).toBe("pass");
});

test("Web Project I/O creates and opens an untouched v4 Project", async ({context, browserName}) => {
  test.skip(browserName !== "chromium", "Chromium owns the positive OPFS contract");
  const project = await trackedPage(context);
  const bundle = `v4-round-trip-${Date.now()}`;
  await project.goto(
      `/project_io/project_io_web_test.html?action=prepare&bundle=${bundle}`);
  expect((await waitForResult(project)).revision).toBe(0);
  expect(await readCheckpointShape(project, bundle, 0)).toEqual({
    contract: "lmdj.project.v4",
    checkpointKeys: CHECKPOINT_V4_KEYS,
    padKeys: ["asset_id", "pad", "playback"],
    playbackKeys: [
      "gain_millidb",
      "muted",
      "trigger_mode",
      "trim_end_frame",
      "trim_start_frame",
    ],
  });
  await project.close();
});

test("Web Project I/O persists Sample staging and Workspace cache behavior", async ({context, browserName}) => {
  test.skip(browserName !== "chromium", "Chromium owns the positive OPFS contract");
  const bundle = `sample-cache-${Date.now()}`;
  const oldStagingToken = "00000000-0000-4000-8000-000000000020";
  const assetId = "00000000-0000-4000-8000-000000000022";
  const artifactSha256 =
      "2cb46aea89409885d9e92b8c106daa39f364b1b5bda845c5e62b0276581fdb17";
  const padPlayback = {
    trimStartFrame: 0,
    trimEndFrame: null,
    triggerMode: "one_shot",
    gainMillidb: 0,
    muted: false,
  };

  const prepare = await trackedPage(context);
  await prepare.goto(
      `/project_io/project_io_web_test.html?action=prepare_sample_cache&bundle=${bundle}`);
  expect(await waitForResult(prepare)).toEqual({
    revision: 0,
    contract: "lmdj.project.v4",
    oldStagingPresent: true,
    stagingDirectories: [oldStagingToken],
  });
  await prepare.close();

  const mutate = await trackedPage(context);
  await mutate.goto(
      `/project_io/project_io_web_test.html?action=mutate_sample_cache&bundle=${bundle}`);
  expect(await waitForResult(mutate)).toEqual({
    revision: 1,
    contract: "lmdj.project.v4",
    replayed: true,
    padAssetId: assetId,
    padPlayback,
    assetCount: 1,
    artifactSha256,
    artifactByteLength: 15,
    artifactBytes: "RIFF-web-sample",
    oldStagingPresent: false,
    completedStagingPresent: false,
    stagingDirectories: [],
    cacheFirst: "cache-first",
    cacheLatest: "cache-latest",
    corruptCacheMiss: true,
    corruptCachePresent: false,
  });
  await mutate.close();

  const reopen = await trackedPage(context);
  await reopen.goto(
      `/project_io/project_io_web_test.html?action=reopen_sample_cache&bundle=${bundle}`);
  expect(await waitForResult(reopen)).toEqual({
    revision: 1,
    contract: "lmdj.project.v4",
    padAssetId: assetId,
    padPlayback,
    assetCount: 1,
    artifactSha256,
    artifactByteLength: 15,
    artifactBytes: "RIFF-web-sample",
    oldStagingPresent: false,
    completedStagingPresent: false,
    stagingDirectories: [],
    cacheLatest: "cache-latest",
    corruptCacheMiss: true,
    corruptCachePresent: false,
  });
  await reopen.close();
});

// #902: with the Catalog half working, every eligible Set still failed to
// install in the browser with a bare IO_ERROR. The Set Store publishes by
// handing the storage platform a staged directory; on OPFS that publish is a
// bounded copy that only a writer lease held on the destination may perform,
// and the Set Store took its lease on the staging directory alone.
// `publish_directory_if_absent` requires the lease on the destination path
// itself. Every real call site satisfies that, so without a negative case the
// guard enforcing it could be deleted and every suite would stay green.
test("Web Project I/O refuses a directory publication leased on an ancestor", async ({page, browserName}) => {
  test.skip(browserName !== "chromium", "Chromium owns the positive OPFS contract");
  trackRuntimeErrors(page);
  await page.goto(
      "/project_io/project_io_web_test.html?action=publication_lease_scope");
  const result = await waitForResult(page);

  expect(result.ancestorLease).toEqual({
    status: "failed",
    errorCode: "IO_ERROR",
    storageCondition: "invalid_state",
  });
  expect(result.destinationAfterRefusal).toBe(false);
  expect(result.exactLease).toEqual({
    status: "succeeded",
    errorCode: "",
    storageCondition: "",
  });
  expect(result.destinationAfterPublish).toBe(true);
});

const SOUNDSET_PUBLISHED = Object.freeze({
  status: "succeeded",
  errorCode: "",
  storageCondition: "",
});

test("Web Project I/O publishes a verified Sound Set into the Workspace Set Store", async ({page, browserName}) => {
  test.skip(browserName !== "chromium", "Chromium owns the positive OPFS contract");
  trackRuntimeErrors(page);
  await page.goto(
      "/project_io/project_io_web_test.html?action=soundset_store_publish");
  const result = await waitForResult(page);

  expect(result.acquire).toEqual(SOUNDSET_PUBLISHED);
  // Idempotent, and answered without touching the Catalog again.
  expect(result.secondAcquire).toEqual(SOUNDSET_PUBLISHED);
  expect(result.catalogReadsAfterAcquire).toBe(2);
  expect(result.catalogReadsAfterSecondAcquire).toBe(2);
  expect(result.publishedSets).toEqual([result.expectedManifestSha256]);
  expect(result.listedCount).toBe(1);
  expect(result.listedSetId).toBe("10000000-0000-4000-8000-000000000001");
  expect(result.artifactBytes).toBe("RIFF-web-soundset-blob");
  // The Set directory is named by the hash of the bytes it holds.
  const manifest = await readPublishedSoundSetManifest(
      page, result.expectedManifestSha256);
  expect(createHash("sha256").update(manifest, "utf8").digest("hex"))
      .toBe(result.publishedSets[0]);
  expect(result.acquireTotalBytes).toBe(
      Buffer.byteLength(manifest, "utf8") + "RIFF-web-soundset-blob".length);
  // A publication that ran to the end cleans up after itself.
  expect(result.publicationIntentPresent).toBe(false);
  expect(result.stagingRootPresent).toBe(true);
  expect(result.stagingDirectories).toEqual([]);
});

// Recovery is what makes the destination lease worth acquiring before the
// store decides whether the Set is already there. Both interruptions below
// leave a destination the store must not accept: the first unreadable, the
// second complete but uncommitted and therefore invisible to `list`.
for (const point of ["during_directory_copy", "after_directory_copy"]) {
  test(`Web Project I/O recovers a Sound Set publication interrupted at ${point}`, async ({context, browserName}) => {
    test.skip(browserName !== "chromium", "Chromium owns the positive OPFS contract");
    const first = await trackedPage(context);
    await first.goto(
        "/project_io/project_io_web_test.html?action=soundset_store_publish");
    const published = await waitForResult(first);
    expect(published.acquire).toEqual(SOUNDSET_PUBLISHED);
    const manifestSha256 = published.expectedManifestSha256;
    expect(await wedgeInterruptedSoundSetPublication(
        first, manifestSha256, point)).toEqual({
      remaining: point === "during_directory_copy" ? 1 : 2,
      staged: 2,
    });
    await first.close();

    const retry = await trackedPage(context);
    await retry.goto(
        "/project_io/project_io_web_test.html?action=soundset_store_publish");
    const recovered = await waitForResult(retry);
    expect(recovered.acquire).toEqual(SOUNDSET_PUBLISHED);
    // The leftovers were cleared and the Set was fetched and published again,
    // so it is enumerated rather than merely present on disk.
    expect(recovered.catalogReadsAfterAcquire).toBe(2);
    expect(recovered.publishedSets).toEqual([manifestSha256]);
    expect(recovered.listedCount).toBe(1);
    expect(recovered.artifactBytes).toBe("RIFF-web-soundset-blob");
    expect(recovered.publicationIntentPresent).toBe(false);
    expect(recovered.stagingDirectories).toEqual([]);
    await retry.close();
  });
}

test("Web Project I/O runs common parity and interruption recovery", async ({page, context, browserName}, testInfo) => {
  test.setTimeout(PROJECT_IO_CONFORMANCE_TIMEOUT_MS);
  trackRuntimeErrors(page);
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
  expect(result.sequenceJournal).toBe("pass");
  expect(result.replay).toBe("pass");
  expect(result.recovery).toBe("pass");
  expect(result.appendContracts).toBe("pass");
  expect(result.lease).toBe("pass");
  expect(result.mountFailure).toBe("pass");
  expect(result.idempotentRemove).toBe("pass");
  expect(result.immutableShortWrites).toBe("pass");
  expect(result.directoryTransfer).toBe("pass");
  expect(result.directoryBarrier).toBe("absent");
  expect(result.replacementFaultPoints).toEqual(REPLACEMENT_FAULT_POINTS);
  expect(result.publicationFaultPoints).toEqual(PUBLICATION_FAULT_POINTS);

  const unleasedAppend = await trackedPage(context);
  await unleasedAppend.goto(
      `/project_io/project_io_web_test.html?action=append_without_lease&bundle=unleased-append-${Date.now()}`);
  expect(await waitForResult(unleasedAppend)).toEqual({
    append: "failed",
    errorCode: "IO_ERROR",
    storageCondition: "invalid_state",
    length: 4,
    content: "seed",
  });
  await unleasedAppend.close();

  const leaseInspector = await trackedPage(context);
  const firstLeasePage = await trackedPage(context);
  const competingLeasePage = await trackedPage(context);
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

  const storageConditionResults = [];
  for (const point of STORAGE_CONDITION_FAULTS) {
    const bundle = `storage-condition-${point}-${Date.now()}`;
    const controller = await trackedPage(context);
    await controller.goto("/preflight.html");
    await writeFaultControl(
        controller,
        `/lmdj-workspace/${bundle}.lmdj/replacement.bin`,
        point);

    const writer = await trackedPage(context);
    await writer.goto(
        `/project_io/project_io_web_test.html?action=storage_condition_failure&bundle=${bundle}`);
    await waitForFault(controller, point);
    storageConditionResults.push({
      point,
      result: await waitForResult(writer),
    });
    await clearFaultControl(controller);
    await writer.close();
    await controller.close();
  }
  expect(storageConditionResults).toEqual([
    {
      point: "QuotaExceededError",
      result: {
        storage: "failed",
        errorCode: "IO_ERROR",
        storageCondition: "quota_exceeded",
      },
    },
    {
      point: "InvalidStateError",
      result: {
        storage: "failed",
        errorCode: "IO_ERROR",
        storageCondition: "invalid_state",
      },
    },
  ]);

  for (const [index, point] of REPLACEMENT_FAULT_POINTS.entries()) {
    const bundle = `fault-${index}-${Date.now()}`;
    const prepare = await trackedPage(context);
    await prepare.goto(`/project_io/project_io_web_test.html?action=prepare&bundle=${bundle}`);
    expect((await waitForResult(prepare)).revision).toBe(0);
    expect(await readCheckpointShape(prepare, bundle, 0)).toEqual({
      contract: "lmdj.project.v4",
      checkpointKeys: CHECKPOINT_V4_KEYS,
      padKeys: ["asset_id", "pad", "playback"],
      playbackKeys: [
        "gain_millidb",
        "muted",
        "trigger_mode",
        "trim_end_frame",
        "trim_start_frame",
      ],
    });
    await writeFaultControl(
        prepare, `/lmdj-workspace/${bundle}.lmdj/manifest.json`, point);

    const interrupted = await trackedPage(context);
    await interrupted.goto(`/project_io/project_io_web_test.html?action=advance&bundle=${bundle}`);
    await waitForFault(prepare, point);
    await interrupted.close();
    await clearFaultControl(prepare);

    const restarted = await trackedPage(context);
    await restarted.goto(`/project_io/project_io_web_test.html?action=reopen&bundle=${bundle}`);
    const expectedRevision = replacementReachedCommit(point) ? 1 : 0;
    expect((await waitForResult(restarted)).revision).toBe(expectedRevision);
    expect(await readCheckpointShape(restarted, bundle, expectedRevision)).toEqual({
      contract: "lmdj.project.v4",
      checkpointKeys: CHECKPOINT_V4_KEYS,
      padKeys: ["asset_id", "pad", "playback"],
      playbackKeys: [
        "gain_millidb",
        "muted",
        "trigger_mode",
        "trim_end_frame",
        "trim_start_frame",
      ],
    });
    await restarted.close();
    await prepare.close();
  }

  for (const [index, point] of REPLACEMENT_FAULT_POINTS.entries()) {
    const bundle = `absent-fault-${index}-${Date.now()}`;
    const prepare = await trackedPage(context);
    await prepare.goto(
        `/project_io/project_io_web_test.html?action=prepare_replacement&scenario=absent&bundle=${bundle}`);
    expect((await waitForResult(prepare)).state).toBe("absent");
    await writeFaultControl(
        prepare, `/lmdj-workspace/${bundle}.lmdj/replacement.bin`, point);

    const interrupted = await trackedPage(context);
    await interrupted.goto(
        `/project_io/project_io_web_test.html?action=replace&scenario=absent&bundle=${bundle}`);
    await waitForFault(prepare, point);
    await interrupted.close();
    await clearFaultControl(prepare);

    const restarted = await trackedPage(context);
    await restarted.goto(
        `/project_io/project_io_web_test.html?action=reopen_replacement&scenario=absent&bundle=${bundle}`);
    const expectedState = replacementReachedCommit(point)
      ? "new"
      : "absent";
    expect((await waitForResult(restarted)).state).toBe(expectedState);
    await restarted.close();
    await prepare.close();
  }

  const corruptBundle = `corrupt-existing-${Date.now()}`;
  const corruptController = await trackedPage(context);
  await corruptController.goto(
      `/project_io/project_io_web_test.html?action=prepare_replacement&scenario=existing&bundle=${corruptBundle}`);
  expect((await waitForResult(corruptController)).state).toBe("existing");
  const corruptDestination =
      `/lmdj-workspace/${corruptBundle}.lmdj/replacement.bin`;
  await writeFaultControl(corruptController, corruptDestination, "before_write");
  const corruptWriter = await trackedPage(context);
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

  const recovery = await trackedPage(context);
  await recovery.goto(
      `/project_io/project_io_web_test.html?action=recover&scenario=existing&bundle=${corruptBundle}`);
  expect(await waitForResult(recovery)).toEqual({
    recovery: "failed",
    errorCode: "IO_ERROR",
    storageCondition: "invalid_state",
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
  const immutableController = await trackedPage(context);
  await immutableController.goto(
      `/project_io/project_io_web_test.html?action=prepare_immutable&bundle=${immutableBundle}`);
  expect((await waitForResult(immutableController)).state).toBe("absent");
  await writeFaultControl(
      immutableController,
      `/lmdj-workspace/${immutableBundle}.lmdj/immutable.bin`,
      "during_write");
  const immutableWriter = await trackedPage(context);
  await immutableWriter.goto(
      `/project_io/project_io_web_test.html?action=create_immutable_fault&bundle=${immutableBundle}`);
  await waitForFault(immutableController, "during_write");
  await immutableWriter.close();
  await clearFaultControl(immutableController);
  const immutableRestarted = await trackedPage(context);
  await immutableRestarted.goto(
      `/project_io/project_io_web_test.html?action=reopen_immutable&bundle=${immutableBundle}`);
  expect((await waitForResult(immutableRestarted)).state).toBe("immutable-retry");
  await immutableRestarted.close();
  await immutableController.close();

  const cleanPublicationBundle = `publication-clean-${Date.now()}`;
  const cleanPublicationController = await trackedPage(context);
  await cleanPublicationController.goto("/preflight.html");
  await preparePublicationFixture(cleanPublicationController, cleanPublicationBundle);
  const cleanPublication = await trackedPage(context);
  await cleanPublication.goto(
      `/project_io/project_io_web_test.html?action=publish_publication&bundle=${cleanPublicationBundle}`);
  expect(await waitForResult(cleanPublication)).toEqual({
    state: "published",
    maxChunkBytes: 1_048_576,
  });
  await cleanPublication.close();
  await cleanPublicationController.close();

  for (const [index, point] of PUBLICATION_FAULT_POINTS.entries()) {
    const bundle = `publication-fault-${index}-${Date.now()}`;
    const controller = await trackedPage(context);
    await controller.goto("/preflight.html");
    await preparePublicationFixture(controller, bundle);
    await writeFaultControl(
        controller, `/lmdj-workspace/${bundle}.lmdj`, point);

    const interrupted = await trackedPage(context);
    await interrupted.goto(
        `/project_io/project_io_web_test.html?action=publish_publication&bundle=${bundle}`);
    await waitForFault(controller, point);
    await interrupted.close();
    await clearFaultControl(controller);

    const inspector = await trackedPage(context);
    await inspector.goto(
        `/project_io/project_io_web_test.html?action=inspect_publication&bundle=${bundle}`);
    const beforeRecovery = await waitForResult(inspector);
    const committed = index >= 7;
    expect(beforeRecovery.visible).toBe(committed);
    if (committed) expect(beforeRecovery.complete).toBe(true);

    const recovery = await trackedPage(context);
    const recoveryAction = committed
      ? "recover_publication"
      : "recover_and_publish";
    await recovery.goto(
        `/project_io/project_io_web_test.html?action=${recoveryAction}&bundle=${bundle}`);
    expect(await waitForResult(recovery)).toEqual({
      visible: true,
      physical: true,
      complete: true,
      source: false,
    });
    await recovery.close();
    await inspector.close();
    await controller.close();
  }

  const malformedBundle = `publication-malformed-${Date.now()}`;
  const malformedController = await trackedPage(context);
  await malformedController.goto("/preflight.html");
  await preparePublicationFixture(malformedController, malformedBundle);
  await writeMalformedPublicationIntent(malformedController, malformedBundle);
  const malformedInspector = await trackedPage(context);
  await malformedInspector.goto(
      `/project_io/project_io_web_test.html?action=inspect_publication&bundle=${malformedBundle}`);
  expect(await waitForResult(malformedInspector)).toEqual({
    visible: false,
    physical: true,
    complete: false,
    source: true,
  });
  const malformedRecovery = await trackedPage(context);
  await malformedRecovery.goto(
      `/project_io/project_io_web_test.html?action=recover_and_publish&bundle=${malformedBundle}`);
  expect(await waitForResult(malformedRecovery)).toEqual({
    visible: true,
    physical: true,
    complete: true,
    source: false,
  });
  await malformedRecovery.close();
  await malformedInspector.close();
  await malformedController.close();

  const legacyBundle = `publication-legacy-${Date.now()}`;
  const legacyController = await trackedPage(context);
  await legacyController.goto("/preflight.html");
  await legacyController.evaluate(async ({bundle}) => {
    const root = await navigator.storage.getDirectory();
    await root.getDirectoryHandle(`${bundle}.lmdj`, {create: true});
  }, {bundle: legacyBundle});
  const legacyInspector = await trackedPage(context);
  await legacyInspector.goto(
      `/project_io/project_io_web_test.html?action=inspect_publication&bundle=${legacyBundle}`);
  expect((await waitForResult(legacyInspector)).visible).toBe(true);
  await legacyInspector.close();
  await legacyController.close();

  const cleanupBundle = `publication-cleanup-${Date.now()}`;
  const cleanupController = await trackedPage(context);
  await cleanupController.goto("/preflight.html");
  await preparePublicationFixture(cleanupController, cleanupBundle);
  await writeFaultControl(
      cleanupController,
      `/lmdj-workspace/${cleanupBundle}.lmdj`,
      PUBLICATION_CLEANUP_FAULT);
  const cleanupWriter = await trackedPage(context);
  await cleanupWriter.goto(
      `/project_io/project_io_web_test.html?action=publish_publication_failure&bundle=${cleanupBundle}`);
  expect((await waitForResult(cleanupWriter)).publish).toBe("failed");
  await cleanupWriter.close();
  await clearFaultControl(cleanupController);
  // The destination copy survives a failed cleanup, so the pending intent must
  // survive with it; deleting the intent would expose an uncommitted tree and
  // leave no recovery path.
  expect(await readPublicationIntentState(cleanupController, cleanupBundle))
      .toBe("pending");
  const cleanupInspector = await trackedPage(context);
  await cleanupInspector.goto(
      `/project_io/project_io_web_test.html?action=inspect_publication&bundle=${cleanupBundle}`);
  expect(await waitForResult(cleanupInspector)).toEqual({
    visible: false,
    physical: true,
    complete: true,
    source: true,
  });
  const cleanupRecovery = await trackedPage(context);
  await cleanupRecovery.goto(
      `/project_io/project_io_web_test.html?action=recover_and_publish&bundle=${cleanupBundle}`);
  expect(await waitForResult(cleanupRecovery)).toEqual({
    visible: true,
    physical: true,
    complete: true,
    source: false,
  });
  await cleanupRecovery.close();
  await cleanupInspector.close();
  await cleanupController.close();

  const tornBundle = `storage-intent-torn-${Date.now()}`;
  const tornController = await trackedPage(context);
  await tornController.goto("/preflight.html");
  const tornPrepare = await trackedPage(context);
  await tornPrepare.goto(
      `/project_io/project_io_web_test.html?action=prepare_replacement&bundle=${tornBundle}&scenario=existing`);
  await waitForResult(tornPrepare);
  await tornPrepare.close();
  // A torn intent can only be produced before the destination is touched, so
  // recovery clears it instead of locking every later writer out.
  await writeStorageIntentBody(
      tornController, tornBundle, "{\"contract\":\"lmdj.storage");
  const tornRecovery = await trackedPage(context);
  await tornRecovery.goto(
      `/project_io/project_io_web_test.html?action=acquire_after_intent&bundle=${tornBundle}`);
  expect(await waitForResult(tornRecovery)).toEqual({
    acquire: "ok",
    content: "old",
  });
  // Recovery must consume exactly this Project's torn record; intents left by
  // earlier phases of this suite are deliberately not counted.
  expect(await storageIntentPresent(tornController, tornBundle)).toBe(false);
  await tornRecovery.close();
  // A record that parses but fails validation may carry rollback state from a
  // newer Contract revision, so it stays fail-closed.
  await writeStorageIntentBody(
      tornController,
      tornBundle,
      JSON.stringify({contract: "lmdj.storage.intent.v2", destination: "x"}));
  const tornGuard = await trackedPage(context);
  await tornGuard.goto(
      `/project_io/project_io_web_test.html?action=acquire_after_intent&bundle=${tornBundle}`);
  expect((await waitForResult(tornGuard)).acquire).toBe("failed");
  await tornGuard.close();
  await tornController.close();
});
