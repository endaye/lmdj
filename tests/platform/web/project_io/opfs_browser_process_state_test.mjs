import assert from "node:assert/strict";
import test from "node:test";
import {spawn} from "node:child_process";

import {browserProcesses, collectBrowserProcessState} from "./opfs_browser_process_state.mjs";

const linuxOnly = {skip: process.platform !== "linux"};

// A child launched by its absolute path stands in for a browser helper: the
// browser's own processes name a path under its install directory as argv[0],
// which is exactly what the matcher reads.
async function withChild(run) {
  const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 30_000)"], {stdio: "ignore"});
  try {
    await new Promise((resolve, reject) => {
      child.once("spawn", resolve);
      child.once("error", reject);
    });
    await run(child);
  } finally {
    child.kill("SIGKILL");
  }
}

test("process state names the platform when /proc is not available", {skip: process.platform === "linux"}, () => {
  const state = collectBrowserProcessState(process.execPath, ["about:blank"]);
  assert.match(state, /unsupported platform/);
});

test("the matcher finds a process launched from the browser's own directory", linuxOnly, async () => {
  await withChild((child) => {
    const found = browserProcesses(process.execPath);
    assert.ok(found.some((entry) => entry.pid === child.pid), "the child is listed");
  });
});

test("the matcher ignores a process that only mentions the directory", linuxOnly, async () => {
  const other = spawn("/bin/sh", ["-c", `: ${process.execPath}; sleep 30`], {stdio: "ignore"});
  try {
    await new Promise((resolve, reject) => {
      other.once("spawn", resolve);
      other.once("error", reject);
    });
    const found = browserProcesses(process.execPath);
    assert.ok(!found.some((entry) => entry.pid === other.pid), "an unrelated process is not listed");
  } finally {
    other.kill("SIGKILL");
  }
});

test("process state reports pages, host limits and a per-process thread histogram", linuxOnly, async () => {
  await withChild((child) => {
    const state = collectBrowserProcessState(process.execPath, ["about:blank", "http://127.0.0.1/x"]);
    assert.match(state, /^pages: 2$/m);
    assert.match(state, /^threads-max: \d+$/m);
    assert.match(state, /^MemAvailable: /m);
    assert.match(state, new RegExp(`^pid ${child.pid} `, "m"));
    assert.match(state, /Threads \d+ VmRSS .* fds \d+/);
  });
});
