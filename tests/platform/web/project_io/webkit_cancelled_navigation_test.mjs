import assert from "node:assert/strict";
import {test} from "node:test";
import {ENGINE_CANCELLED_LOAD, gotoRetryingCancelledFirstLoad} from "./webkit_cancelled_navigation.mjs";

const cancelled = () => new Error(`page.goto: ${ENGINE_CANCELLED_LOAD}\nCall log: navigating`);

function fakePage(outcomes, {url = "about:blank", closed = false} = {}) {
  const calls = [];
  return {
    calls,
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

async function navigate(page, browserName = "webkit") {
  const retries = [];
  const result = await gotoRetryingCancelledFirstLoad(page, "/step", {waitUntil: "load"},
    {browserName, onRetry: error => retries.push(error)}).then(value => ({value}), error => ({error}));
  return {...result, retries};
}

test("a WebKit fresh page repeats an engine-cancelled first load once", async () => {
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
    {page: fakePage([cancelled()]), browserName: "chromium"},
    {page: fakePage([cancelled()], {url: "http://127.0.0.1/preflight.html"}), browserName: "webkit"},
    {page: fakePage([cancelled()], {closed: true}), browserName: "webkit"},
    {page: fakePage([new Error("page.goto: Timeout 600000ms exceeded.")]), browserName: "webkit"},
  ];
  for (const {page, browserName} of cases) {
    const {error, retries} = await navigate(page, browserName);
    assert.ok(error instanceof Error);
    assert.equal(retries.length, 0);
    assert.equal(page.calls.length, 1);
  }
});
