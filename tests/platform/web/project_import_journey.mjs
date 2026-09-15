import {createHash, randomUUID} from "node:crypto";
import {readFileSync} from "node:fs";
import {expect, test} from "@playwright/test";

const digest = bytes => createHash("sha256").update(bytes).digest("hex");

// The Bundle container version the importer accepts. Read from the versioned
// schema for the same reason project_contract is read from the persisted head
// checkpoint: a hardcoded level silently stops describing the Contract when
// the writer moves (#1364 retired container 1.x and the journey went red
// without a single Host code change).
const bundleContractVersion = JSON.parse(readFileSync(
  new URL("../../../contracts/project/lmdj.project-bundle.v1.schema.json",
    import.meta.url), "utf8")).properties.contract_version.const;

async function start(page) {
  await page.goto("/index.html");
  // The packaged page's own readiness barrier: the Host answers project.*
  // only after the runtime has initialized into its quiescent state. Each
  // journey boots several 512 MiB-heap contexts back to back, so this needs
  // more headroom than the default expect timeout.
  await expect(page.locator("#host-state")).toHaveText("audio-suspended",
    {timeout: 60_000});
  await page.waitForFunction(() => Boolean(window.lmdjWebRuntimeHost?.transport));
}
async function send(page, operation, payload = {}, bytes) {
  return page.evaluate(async ({operation, payload, bytes}) =>
    window.lmdjWebRuntimeHost.transport.send({protocol_version: 1,
      request_id: crypto.randomUUID(), operation, payload},
    bytes ? {sidecar: new Uint8Array(bytes)} : undefined),
  {operation, payload, bytes: bytes ? [...bytes] : undefined});
}
function success(response, label) {
  expect(response, label ?? JSON.stringify(response)).toHaveProperty("ok", true);
  return response.result;
}
async function opfsInventory(page) {
  return page.evaluate(async () => {
    async function visit(directory, prefix = "") {
      const entries = [];
      for await (const [name, handle] of directory.entries()) {
        const relative = `${prefix}${name}`;
        entries.push(`${handle.kind}:${relative}`);
        if (handle.kind === "directory") {
          entries.push(...await visit(handle, `${relative}/`));
        }
      }
      return entries;
    }
    return (await visit(await navigator.storage.getDirectory())).sort();
  });
}
// The OPFS mount drops the leading `lmdj-workspace` segment
// (pathParts, packages/project-io/src/web/library_opfs_storage.js), so the
// persisted tree is rooted at `projects/`; Bundle entry paths are relative to
// the Project directory itself.
async function readProjectTree(page, projectId) {
  return page.evaluate(async (projectId) => {
    const root = await navigator.storage.getDirectory();
    const projects = await root.getDirectoryHandle("projects");
    const project = await projects.getDirectoryHandle(`${projectId}.lmdj`);
    const entries = [];
    async function visit(directory, prefix = "") {
      for await (const [name, handle] of directory.entries()) {
        const path = `${prefix}${name}`;
        if (handle.kind === "directory") {
          await visit(handle, `${path}/`);
          continue;
        }
        const bytes = new Uint8Array(await (await handle.getFile()).arrayBuffer());
        entries.push([path, [...bytes]]);
      }
    }
    await visit(project);
    return entries;
  }, projectId);
}
// Mirrors lmdj::foundation::canonical_json and project_bundle.py: object keys
// in unsigned UTF-8 byte order, no whitespace. Every key and string value in a
// Bundle index is ASCII, for which JSON.stringify is already the canonical
// escaping.
function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const keys = Object.keys(value).sort((left, right) =>
      Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8")));
    return `{${keys.map(key =>
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}
// Mirrors build_fixture in tests/core/project_io/project_bundle_transfer_test.cpp
// and tools/project-bundle/project_bundle.py: entries sorted by unsigned UTF-8
// path bytes, per-entry sha256, contiguous offsets, and bundle_digest over the
// canonical index with bundle_digest omitted. project_contract is read from the
// head checkpoint the Store actually persisted, never hardcoded — a hardcoded
// level silently stops describing the Project when the writer moves (#784/#900).
function buildBundle(files, projectId) {
  const sorted = [...files].sort(([left], [right]) =>
    Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8")));
  const text = (path) => {
    const found = sorted.find(([entryPath]) => entryPath === path);
    expect(found, `bundle fixture entry is missing: ${path}`).toBeDefined();
    return Buffer.from(found[1]).toString("utf8");
  };
  const manifest = JSON.parse(text("manifest.json"));
  const head = JSON.parse(text(manifest.head_checkpoint));
  const entries = [];
  let offset = 0;
  for (const [path, bytes] of sorted) {
    entries.push({
      bytes: bytes.length,
      offset,
      path,
      sha256: digest(Buffer.from(bytes)),
    });
    offset += bytes.length;
  }
  const index = {
    bundle_digest: "0".repeat(64),
    compression: "none",
    contract: "lmdj.project-bundle.v1",
    contract_version: bundleContractVersion,
    entries,
    project_contract: head.contract,
    project_id: projectId,
    uncompressed_bytes: offset,
  };
  const {bundle_digest, ...digestSource} = index;
  index.bundle_digest = digest(canonicalJson(digestSource));
  const indexBytes = Buffer.from(canonicalJson(index), "utf8");
  return {
    digest: index.bundle_digest,
    indexBytes,
    indexSha256: digest(indexBytes),
    paths: sorted.map(([path]) => path),
    payloads: sorted.map(([, bytes]) => Buffer.from(bytes)),
  };
}
// Context 1 of every journey: author a real Project through the public Host
// transport so the Bundle payload is real persisted bytes, then close the
// context so its writer lease and origin partition are gone. Booting the
// packaged Host is the expensive part of these journeys (a 512 MiB fixed-heap
// runtime per page), and the authored bytes are read-only evidence, so the
// bundle is authored once per worker and shared; each journey still imports
// into its own fresh origin partition.
let authored = null;
function authorBundle(browser) {
  // A rejected authoring attempt must not be cached: one transient boot
  // failure would otherwise fail every later journey in this worker with the
  // original error and hide its own cause.
  authored ??= authorBundleOnce(browser).catch(error => {
    authored = null;
    throw error;
  });
  return authored;
}
async function authorBundleOnce(browser) {
  const projectId = randomUUID();
  const patternId = randomUUID();
  const context = await browser.newContext();
  const page = await context.newPage();
  await start(page);
  success(await send(page, "project.create", {project_id: projectId, bpm: 120,
    initial_pattern: {pattern_id: patternId, bars: 1, events: []}}),
    "author project.create");
  const truth = success(await send(page, "project.inspect"), "author project.inspect");
  const files = await readProjectTree(page, projectId);
  await context.close();
  return {projectId, patternId, truth, files, bundle: buildBundle(files, projectId)};
}
async function openFreshHost(browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await start(page);
  return {context, page};
}
// begin → index → entry×N; commit and abort stay with the caller because each
// journey asserts a different terminal fact.
async function stageImport(page, bundle, importToken) {
  const begun = success(await send(page, "project.import.begin", {
    import_token: importToken,
    index_bytes: bundle.indexBytes.length,
    index_sha256: bundle.indexSha256,
  }), "project.import.begin");
  expect(begun).toEqual({
    import_token: importToken,
    expected_index_bytes: bundle.indexBytes.length,
  });
  const identity = success(await send(page, "project.import.index", {
    import_token: importToken, offset: 0, final: true,
    sidecar: {
      sidecar_bytes: bundle.indexBytes.length,
      sidecar_sha256: bundle.indexSha256,
    },
  }, bundle.indexBytes), "project.import.index");
  for (const [entryIndex, payload] of bundle.payloads.entries()) {
    const received = success(await send(page, "project.import.entry", {
      import_token: importToken, entry_index: entryIndex, offset: 0, final: true,
      sidecar: {sidecar_bytes: payload.length, sidecar_sha256: digest(payload)},
    }, payload), `project.import.entry ${entryIndex}`);
    expect(received).toEqual({
      entry_index: entryIndex,
      received_entry_bytes: payload.length,
      final: true,
    });
  }
  return identity;
}

export function registerProjectImportJourneys(host) {
  // Every journey boots two packaged-Host pages (a 512 MiB fixed-heap runtime
  // each) back to back; on a loaded machine instantiation alone can exceed
  // Playwright's 30s default. The barrier still fails a Host that never boots.
  test.setTimeout(120_000);
  test(`${host}: an imported Project Bundle is published, listed, opened and inspected`, async ({browser}) => {
    const {projectId, patternId, truth, bundle} = await authorBundle(browser);
    const {context, page} = await openFreshHost(browser);
    // A fresh context is a fresh origin partition: the publish below must be a
    // first-time write, not the idempotent same-digest path in commit.
    expect((await opfsInventory(page)).some(entry => entry.includes(projectId))).toBe(false);
    expect(success(await send(page, "project.list", {})), "project.list before import")
      .toEqual({projects: []});
    const importToken = randomUUID();
    const identity = await stageImport(page, bundle, importToken);
    expect(identity).toEqual({
      project_id: projectId,
      bundle_digest: bundle.digest,
      entry_count: bundle.payloads.length,
    });
    const committed = success(await send(page, "project.import.commit",
      {import_token: importToken}), "project.import.commit");
    expect(committed).toMatchObject({
      project_id: projectId,
      bundle_digest: bundle.digest,
    });
    // The receipt is worth nothing unless the bytes are where it says they are
    // and the staging area is gone.
    const inventory = await opfsInventory(page);
    for (const path of bundle.paths) {
      expect(inventory).toContain(`file:projects/${projectId}.lmdj/${path}`);
    }
    expect(inventory.some(entry => entry.includes(importToken))).toBe(false);
    const listed = success(await send(page, "project.list", {}), "project.list");
    expect(listed.projects.map(project => project.project_id)).toEqual([projectId]);
    const opened = success(await send(page, "project.open",
      {project_id: projectId, pattern_id: patternId}), "project.open");
    expect(opened.runtime_ready).toBe(true);
    // project.inspect answers the session's open Project — it cannot be
    // addressed by Project ID, so the open above is part of the journey.
    expect(success(await send(page, "project.inspect", {}), "project.inspect"))
      .toEqual(truth);
    await context.close();
  });
  test(`${host}: project.import.abort discards the staged Bundle and its token`, async ({browser}) => {
    const {projectId, bundle} = await authorBundle(browser);
    const {context, page} = await openFreshHost(browser);
    const importToken = randomUUID();
    await stageImport(page, bundle, importToken);
    expect(success(await send(page, "project.import.abort",
      {import_token: importToken}), "project.import.abort")).toEqual({aborted: true});
    const inventory = await opfsInventory(page);
    // Scoped to the library and the staging token: `.lmdj-host/` lease and
    // intent metadata may legitimately mention the staged Project ID (the
    // same carve-out the collision journey makes), so an abort is proven by
    // the absence of the published tree and the staging area, not by a
    // global name search.
    expect(inventory.some(entry =>
      entry.startsWith("file:projects/") ||
      entry.startsWith("directory:projects/"))).toBe(false);
    expect(inventory.some(entry => entry.includes(importToken))).toBe(false);
    expect(success(await send(page, "project.list", {})), "project.list after abort")
      .toEqual({projects: []});
    // The aborted token is retired: a late commit must not resurrect it.
    const committed = await send(page, "project.import.commit", {import_token: importToken});
    expect(committed.ok).toBe(false);
    expect(committed.error.code).toBe("NOT_FOUND");
    await context.close();
  });
  test(`${host}: a changed Bundle with the same Project ID is refused and the library is untouched`, async ({browser}) => {
    const {projectId, files, bundle} = await authorBundle(browser);
    const {context, page} = await openFreshHost(browser);
    const firstToken = randomUUID();
    await stageImport(page, bundle, firstToken);
    success(await send(page, "project.import.commit",
      {import_token: firstToken}), "first project.import.commit");
    const published = await opfsInventory(page);
    // The library is the `projects/` subtree. `.lmdj-host/` lease locks and
    // storage intents legitimately accumulate on a refused commit — the native
    // platform keeps that metadata outside the workspace, OPFS keeps it inside
    // — so the untouched fact is scoped to the library and the staging area.
    const library = inventory =>
      inventory.filter(entry => entry.startsWith("directory:projects") ||
        entry.startsWith("file:projects"));
    // Same Project ID, different bytes: like the native collision fixture, add
    // a file the Store never reads so the staged Project still validates and
    // only the digest differs.
    const changed = buildBundle(
      [...files, ["local-note.bin", [...Buffer.from("changed", "utf8")]]],
      projectId);
    expect(changed.digest).not.toBe(bundle.digest);
    const secondToken = randomUUID();
    await stageImport(page, changed, secondToken);
    const collision = await send(page, "project.import.commit",
      {import_token: secondToken});
    expect(collision.ok).toBe(false);
    expect(collision.error.code).toBe("DUPLICATE_ID");
    const listed = success(await send(page, "project.list", {}), "project.list after collision");
    expect(listed.projects.map(project => project.project_id)).toEqual([projectId]);
    expect(listed.projects[0].bundle_digest).toBe(bundle.digest);
    const inventory = await opfsInventory(page);
    expect(library(inventory)).toEqual(library(published));
    expect(inventory.some(entry => entry.includes(secondToken))).toBe(false);
    await context.close();
  });
}
