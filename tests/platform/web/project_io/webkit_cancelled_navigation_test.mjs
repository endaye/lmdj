import assert from "node:assert/strict";
import {existsSync} from "node:fs";
import {readFile} from "node:fs/promises";
import {dirname, join} from "node:path";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import {webkit} from "playwright-core";
import {clientBundle, isPatched} from "../toolchain/playwright_webkit_abort_patch.mjs";
import {ENGINE_CANCELLED_LOAD, gotoRetryingCancelledFirstLoad, pageEngine} from "./webkit_cancelled_navigation.mjs";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const fakeBrowser = join(webRoot, "toolchain", "fake_webkit_pipe_browser.mjs");
const cancelled = () => new Error(`page.goto: ${ENGINE_CANCELLED_LOAD}\nCall log: navigating`);

// Like a Playwright Page, the engine is only reachable through its Browser; a
// persistent context (`engine: null`) has none.
function fakePage(outcomes, {url = "about:blank", closed = false, engine = "webkit"} = {}) {
  const calls = [];
  const browser = engine === null ? null : {browserType: () => ({name: () => engine})};
  return {
    calls,
    context: () => ({browser: () => browser}),
    isClosed: () => closed,
    url: () => url,
    goto: async (...args) => {
      calls.push(args);
      const outcome = outcomes.shift();
      if (outcome instanceof Error) throw outcome;
      return outcome;
    },
  };
}

async function navigate(page) {
  const retries = [];
  const result = await gotoRetryingCancelledFirstLoad(page, "/step", {waitUntil: "load"},
    {onRetry: error => retries.push(error)}).then(value => ({value}), error => ({error}));
  return {...result, retries};
}

// The spec passed `test.info().project.use.browserName`, which is undefined for
// `devices["Desktop Safari"]`, so a real WebKit run never retried (batch gen 553,
// job 108941563228). The engine now comes from the page; no caller names it.
test("a WebKit fresh page repeats an engine-cancelled first load once, with no caller-supplied engine", async () => {
  const page = fakePage([cancelled(), "response"]);
  const {value, retries} = await navigate(page);
  assert.equal(value, "response");
  assert.equal(retries.length, 1);
  assert.deepEqual(page.calls, [["/step", {waitUntil: "load"}], ["/step", {waitUntil: "load"}]]);
});

test("a second cancellation fails instead of retrying again", async () => {
  const second = cancelled();
  const page = fakePage([cancelled(), second]);
  const {error, retries} = await navigate(page);
  assert.equal(error, second);
  assert.equal(retries.length, 1);
  assert.equal(page.calls.length, 2);
});

test("a page this helper already navigated never retries, even back at about:blank", async () => {
  const page = fakePage(["response", cancelled()]);
  assert.equal((await navigate(page)).value, "response");
  const {error, retries} = await navigate(page);
  assert.ok(error instanceof Error);
  assert.equal(retries.length, 0);
  assert.equal(page.calls.length, 2);
});

test("every other navigation failure propagates without retry", async () => {
  const cases = [
    fakePage([cancelled()], {engine: "chromium"}),
    fakePage([cancelled()], {engine: null}),
    fakePage([cancelled()], {url: "http://127.0.0.1/preflight.html"}),
    fakePage([cancelled()], {closed: true}),
    fakePage([new Error("page.goto: Timeout 600000ms exceeded.")]),
  ];
  for (const page of cases) {
    const {error, retries} = await navigate(page);
    assert.ok(error instanceof Error);
    assert.equal(retries.length, 0);
    assert.equal(page.calls.length, 1);
  }
});

// End to end on the locked (postinstall-patched) client: a real Playwright
// Page over the recorded #1570 exchange. Every fake navigation is cancelled,
// so the first load is retried exactly once and the second cancellation fails.
test("a real Playwright WebKit page reports its engine and retries the cancelled first load once", async (t) => {
  // Preconditions fail with their own cause, never as a launch error or a
  // wrong retry count.
  assert.ok(existsSync(fakeBrowser),
    `why: the recorded #1570 fake browser is missing at ${fakeBrowser}; remedy: restore it or update this path`);
  assert.ok(isPatched(await readFile(await clientBundle(webRoot), "utf8")),
    "why: the installed Playwright client lacks the #1570 abort patch, so goto never rejects; " +
    "remedy: run `npm --prefix tests/platform/web ci`");
  const priorOrder = process.env.FAKE_WEBKIT_ORDER;
  t.after(() => {
    if (priorOrder === undefined) delete process.env.FAKE_WEBKIT_ORDER;
    else process.env.FAKE_WEBKIT_ORDER = priorOrder;
  });
  process.env.FAKE_WEBKIT_ORDER = "early";
  const browser = await webkit.launch({executablePath: fakeBrowser, timeout: 10_000});
  try {
    const page = await (await browser.newContext()).newPage();
    assert.equal(pageEngine(page), "webkit");
    const retries = [];
    const error = await gotoRetryingCancelledFirstLoad(page, "http://127.0.0.1:9/project_io_web_test.html",
      {timeout: 3_000}, {onRetry: failure => retries.push(failure)}).then(() => null, failure => failure);
    assert.equal(retries.length, 1);
    assert.match(error?.message ?? "", new RegExp(ENGINE_CANCELLED_LOAD.replace(/[.?;]/g, "\\$&")));
  } finally {
    await browser.close();
  }
});
