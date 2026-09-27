import assert from "node:assert/strict";
import {cp, mkdtemp, readFile, rm, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {after, before, test} from "node:test";
import {fileURLToPath, pathToFileURL} from "node:url";
import {clientBundle, isPatched, patchBundle, unpatchBundle} from "./playwright_webkit_abort_patch.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");
const fakeBrowser = join(here, "fake_webkit_pipe_browser.mjs");
const ENGINE_CANCELLED = "Load request cancelled; maybe frame was detached?";
const NAVIGATION_TIMEOUT_MS = 3_000;
let scratch;
let originalSource;
const clients = {};

// Load the locked client twice from scratch copies: once as npm shipped it,
// once with the patch. The installed copy is patched by postinstall.
before(async () => {
  scratch = await mkdtemp(join(tmpdir(), "lmdj-playwright-abort-"));
  const installed = await readFile(await clientBundle(webRoot), "utf8");
  originalSource = unpatchBundle(installed);
  for (const [name, source] of [["original", originalSource], ["patched", patchBundle(originalSource)]]) {
    const root = join(scratch, name, "playwright-core");
    await cp(join(webRoot, "node_modules", "playwright-core"), root, {recursive: true});
    await writeFile(join(root, "lib", "coreBundle.js"), source);
    clients[name] = (await import(pathToFileURL(join(root, "index.mjs")).href)).webkit;
  }
});

after(async () => {
  await rm(scratch, {recursive: true, force: true});
});

async function replayNavigation(client, order) {
  process.env.FAKE_WEBKIT_ORDER = order;
  const browser = await client.launch({executablePath: fakeBrowser, timeout: 10_000});
  try {
    const page = await (await browser.newContext()).newPage();
    const started = Date.now();
    const error = await page.goto("http://127.0.0.1:9/project_io_web_test.html",
      {timeout: NAVIGATION_TIMEOUT_MS}).then(() => null, failure => failure);
    return {error, elapsed: Date.now() - started, url: page.url()};
  } finally {
    await browser.close();
  }
}

test("the locked client waits out a cancelled load reported before its document request", async () => {
  const {error, url} = await replayNavigation(clients.original, "early");
  assert.equal(error?.name, "TimeoutError");
  assert.equal(url, "about:blank");
});

test("the patched client rejects that navigation with the engine's cancellation", async () => {
  const {error, elapsed, url} = await replayNavigation(clients.patched, "early");
  assert.match(error?.message ?? "", new RegExp(ENGINE_CANCELLED.replace(/[.?;]/g, "\\$&")));
  assert.ok(elapsed < NAVIGATION_TIMEOUT_MS, `rejected after ${elapsed} ms`);
  assert.equal(url, "about:blank");
});

test("the patched client keeps the locked rejection when the document request comes first", async () => {
  const {error, elapsed} = await replayNavigation(clients.patched, "late");
  assert.match(error?.message ?? "", new RegExp(ENGINE_CANCELLED.replace(/[.?;]/g, "\\$&")));
  assert.ok(elapsed < NAVIGATION_TIMEOUT_MS, `rejected after ${elapsed} ms`);
});

test("patching is idempotent and reversible on the locked bundle", () => {
  const patched = patchBundle(originalSource);
  assert.notEqual(patched, originalSource);
  assert.equal(isPatched(patched), true);
  assert.equal(isPatched(originalSource), false);
  assert.equal(patchBundle(patched), patched);
  assert.equal(unpatchBundle(patched), originalSource);
});

test("a bundle without exactly one edit site fails closed with why and remedy", () => {
  for (const source of ["", originalSource + originalSource]) {
    assert.throws(() => patchBundle(source), error =>
      /^why: .*exactly one.*; remedy: /.test(error.message));
  }
});
