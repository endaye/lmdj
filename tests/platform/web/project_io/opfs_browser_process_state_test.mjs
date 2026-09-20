import assert from "node:assert/strict";
import test from "node:test";

import {browserProcesses, collectBrowserProcessState} from "./opfs_browser_process_state.mjs";

test("process state names the platform when /proc is not available", {skip: process.platform === "linux"}, () => {
  const state = collectBrowserProcessState(process.execPath, ["about:blank"]);
  assert.match(state, /unsupported platform/);
});

test("process state finds the browser processes by their install directory", {skip: process.platform !== "linux"}, () => {
  // This Node process stands in for the browser: its cmdline carries its own
  // install directory, which is how the WebKit helpers are recognised too.
  const found = browserProcesses(process.execPath);
  assert.ok(found.some((entry) => entry.pid === process.pid), "the calling process is listed");
});

test("process state reports pages, limits and per-process thread histograms", {skip: process.platform !== "linux"}, () => {
  const state = collectBrowserProcessState(process.execPath, ["about:blank", "http://127.0.0.1/x"]);
  assert.match(state, /^pages: 2$/m);
  assert.match(state, /^threads-max: \d+$/m);
  assert.match(state, /^MemAvailable: /m);
  assert.match(state, new RegExp(`^pid ${process.pid} `, "m"));
  assert.match(state, /Threads \d+ VmRSS .* fds \d+/);
});
