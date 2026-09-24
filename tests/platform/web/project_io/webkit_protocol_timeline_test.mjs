import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import {mkdtemp, readFile, rm, writeFile} from "node:fs/promises";
import {constants as osConstants, tmpdir} from "node:os";
import {join} from "node:path";
import test from "node:test";

import {WebkitProtocolTimeline} from "./webkit_protocol_timeline.mjs";

const packet = (direction, value) =>
  `2026-09-24T01:00:00.000Z pw:protocol ${direction} ${JSON.stringify(value)} +4ms`;
const send = value => packet("SEND ►", value);
const recv = value => packet("◀ RECV", value);

test("a cancelled WebKit navigation keeps its exact command, target and failed provisional load", () => {
  const timeline = new WebkitProtocolTimeline();
  const lines = [
    recv({method: "Target.targetCreated", params: {targetInfo: {targetId: "page-53"}}, pageProxyId: "41"}),
    send({id: 338, method: "Playwright.navigate", params: {
      pageProxyId: "41", frameId: "8589934597", url: "http://127.0.0.1:1234/preflight.html"}}),
    recv({result: {loaderId: "50"}, id: 338}),
    recv({method: "Target.dispatchMessageFromTarget", params: {targetId: "page-53",
      message: JSON.stringify({method: "Page.didCheckNavigationPolicy", params: {
        frameId: "8589934597", cancel: false}})}, pageProxyId: "41"}),
    recv({method: "Playwright.provisionalLoadFailed", params: {
      pageProxyId: "41", loaderId: "50", error: "Load request cancelled"}}),
    recv({method: "Target.targetDestroyed", params: {targetId: "page-53", crashed: false},
      pageProxyId: "41"}),
    recv({method: "Screencast.screencastFrame", params: {data: "secret-image-bytes"}}),
  ];
  const events = lines.map(line => timeline.record(line)).filter(Boolean);
  assert.deepEqual(events.map(event => event.event), [
    "Target.targetCreated", "navigate-send", "navigate-reply",
    "Page.didCheckNavigationPolicy", "Playwright.provisionalLoadFailed",
    "Target.targetDestroyed",
  ]);
  assert.deepEqual(events[2], {time: "2026-09-24T01:00:00.000Z", event: "navigate-reply",
    id: 338, pageProxyId: "41", loaderId: "50", error: undefined});
  assert.equal(events[4].error, "Load request cancelled");
  assert.equal(JSON.stringify(events).includes("secret-image-bytes"), false);
});

test("an interleaved lower command id does not erase a pending navigation", () => {
  const timeline = new WebkitProtocolTimeline();
  assert.equal(timeline.record(send({id: 338, method: "Playwright.navigate",
    params: {pageProxyId: "41", url: "http://127.0.0.1/stuck"}}))?.event, "navigate-send");
  timeline.record(send({id: 1, method: "Playwright.createBrowserContext", params: {}}));
  assert.equal(timeline.record(recv({id: 338, result: {loaderId: "50"}}))?.event,
    "navigate-reply");
});

test("an overlapping command id makes a navigation reply explicitly ambiguous", () => {
  const timeline = new WebkitProtocolTimeline();
  timeline.record(send({id: 338, method: "Playwright.navigate",
    params: {pageProxyId: "41", url: "http://127.0.0.1/stuck"}}));
  assert.equal(timeline.record(send({id: 338, method: "Playwright.deleteContext",
    params: {browserContextId: "other"}}))?.event, "navigation-id-reused");
  const reply = timeline.record(recv({id: 338, result: {loaderId: "50"}}));
  assert.equal(reply?.event, "navigate-reply-ambiguous");
  assert.equal(reply?.candidatePageProxyId, "41");
  timeline.record(recv({method: "Playwright.pageProxyDestroyed", params: {pageProxyId: "41"}}));
  assert.equal(timeline.record(recv({id: 338, result: {loaderId: "50"}})), null);
});

test("the sidecar preserves a failing proof status and retains only a protocol timeline", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "lmdj-webkit-timeline-test-"));
  try {
    const output = join(temporary, "results", "webkit-protocol-timeline.jsonl");
    const fixture = join(temporary, "emit.mjs");
    await writeFile(fixture, `
      process.stderr.write(${JSON.stringify(send({id: 7, method: "Playwright.navigate", params: {
        url: "http://127.0.0.1:1/probe", pageProxyId: "5"}}))} + "\\n");
      process.stderr.write("debug=" + process.env.DEBUG + "\\n");
      process.stderr.write("ordinary proof failure\\n");
      process.exitCode = 7;
    `);
    const script = new URL("./webkit_protocol_timeline.mjs", import.meta.url).pathname;
    const result = spawnSync(process.execPath, [script, output, process.execPath, fixture], {
      encoding: "utf8", timeout: 10_000,
      env: {...process.env, DEBUG: "other:namespace"}});
    assert.equal(result.status, 7, result.stderr);
    assert.match(result.stderr, /ordinary proof failure/);
    assert.match(result.stderr, /debug=other:namespace,pw:protocol/);
    assert.match(result.stderr, /WebKit navigation protocol timeline:/);
    const events = (await readFile(output, "utf8")).trim().split("\n").map(JSON.parse);
    assert.equal(events.length, 1);
    assert.equal(events[0].event, "navigate-send");
    assert.equal(events[0].id, 7);
  } finally {
    await rm(temporary, {recursive: true, force: true});
  }
});

test("the sidecar discards protocol evidence after a passing proof", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "lmdj-webkit-timeline-pass-"));
  try {
    const output = join(temporary, "webkit-protocol-timeline.jsonl");
    await writeFile(output, "stale failure evidence\n");
    const fixture = join(temporary, "emit.mjs");
    await writeFile(fixture, `process.stderr.write(${JSON.stringify(send({id: 1,
      method: "Playwright.navigate", params: {url: "http://127.0.0.1/"}}))} + "\\n");`);
    const script = new URL("./webkit_protocol_timeline.mjs", import.meta.url).pathname;
    const result = spawnSync(process.execPath, [script, output, process.execPath, fixture], {
      encoding: "utf8", timeout: 10_000});
    assert.equal(result.status, 0, result.stderr);
    await assert.rejects(readFile(output, "utf8"), {code: "ENOENT"});
  } finally {
    await rm(temporary, {recursive: true, force: true});
  }
});

test("a signalled proof exits without waiting for or re-killing its closed child", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "lmdj-webkit-timeline-signal-"));
  try {
    const output = join(temporary, "webkit-protocol-timeline.jsonl");
    const fixture = join(temporary, "signal.mjs");
    await writeFile(fixture, `process.kill(process.pid, "SIGTERM");`);
    const script = new URL("./webkit_protocol_timeline.mjs", import.meta.url).pathname;
    const result = spawnSync(process.execPath, [script, output, process.execPath, fixture], {
      encoding: "utf8", timeout: 10_000});
    assert.equal(result.status, 128 + osConstants.signals.SIGTERM, result.stderr);
    assert.match(result.stderr, /WebKit navigation protocol timeline:/);
  } finally {
    await rm(temporary, {recursive: true, force: true});
  }
});

test("a diagnostic stderr sink error preserves the proof child result", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "lmdj-webkit-timeline-cleanup-"));
  try {
    const child = join(temporary, "child.mjs");
    const driver = join(temporary, "driver.mjs");
    await writeFile(child, `
      process.stderr.write("ordinary line\\n");
      setTimeout(() => { process.exitCode = 7; }, 100);
    `);
    const script = new URL("./webkit_protocol_timeline.mjs", import.meta.url).href;
    await writeFile(driver, `
      import {runWithProtocolTimeline} from ${JSON.stringify(script)};
      process.stderr.write = () => { throw new Error("diagnostic sink closed"); };
      const status = await runWithProtocolTimeline(${JSON.stringify(join(temporary, "timeline.jsonl"))},
        process.execPath, [${JSON.stringify(child)}]);
      process.stdout.write(String(status));
    `);
    const result = spawnSync(process.execPath, [driver], {encoding: "utf8", timeout: 10_000});
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, "7");
  } finally {
    await rm(temporary, {recursive: true, force: true});
  }
});
