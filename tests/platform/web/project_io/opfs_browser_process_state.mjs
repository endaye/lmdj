import {execFileSync} from "node:child_process";
import {readFileSync, readdirSync} from "node:fs";
import {dirname} from "node:path";

// What the WebKit browser looked like at the moment a test timed out, read
// from /proc on the machine that ran it. A `page.goto` that hangs until the
// test timeout on the CI runners (#1570) leaves nothing behind but the URL it
// was loading, and that URL names the victim, not the cause; the process,
// thread, descriptor and shared-memory state of the browser at that moment is
// what says whether the browser was wedged, starved, or waiting on something.
// Linux only: the runners are Linux and /proc is the only source that needs
// no elevated access.

function read(path) {
  try {
    return readFileSync(path, "utf8");
  } catch (_) {
    return "";
  }
}

function count(path) {
  try {
    return readdirSync(path).length;
  } catch (_) {
    return -1;
  }
}

function field(status, name) {
  // A plain prefix scan, so a field name is never read as a pattern.
  for (const line of status.split("\n")) {
    if (line.startsWith(`${name}:`)) return line.slice(name.length + 1).trim();
  }
  return "?";
}

function command(args) {
  try {
    return execFileSync(args[0], args.slice(1), {encoding: "utf8", timeout: 5_000}).trim();
  } catch (error) {
    return `(${args[0]} failed: ${error.message.split("\n")[0]})`;
  }
}

// The browser is its own executable plus the helper processes it launches
// from its own install directory, each of which names a path under that
// directory as its own argv[0]. Matching argv[0] alone keeps an unrelated
// process that merely mentions the directory — a shell, an installer, the
// test runner — out of the report.
export function browserProcesses(executablePath) {
  const marker = `${dirname(executablePath)}/`;
  const processes = [];
  for (const entry of readdirSync("/proc")) {
    if (!/^\d+$/.test(entry)) continue;
    const cmdline = read(`/proc/${entry}/cmdline`).split("\0").filter(Boolean);
    const image = cmdline[0];
    if (!image || !(image === executablePath || image.startsWith(marker))) continue;
    processes.push({pid: Number(entry), cmdline});
  }
  return processes;
}

export function collectBrowserProcessState(executablePath, pageUrls = []) {
  if (process.platform !== "linux") {
    return `browser process state: unsupported platform ${process.platform}\n`;
  }
  const lines = [];
  lines.push(`pages: ${pageUrls.length}`);
  for (const url of pageUrls) lines.push(`  ${url}`);
  lines.push(`loadavg: ${read("/proc/loadavg").trim()}`);
  lines.push(`threads-max: ${read("/proc/sys/kernel/threads-max").trim()}`);
  lines.push(`pid_max: ${read("/proc/sys/kernel/pid_max").trim()}`);
  lines.push(`max_map_count: ${read("/proc/sys/vm/max_map_count").trim()}`);
  lines.push(`MemAvailable: ${field(read("/proc/meminfo"), "MemAvailable")}`);
  lines.push(`self limits:\n${read("/proc/self/limits").split("\n")
      .filter((line) => /processes|open files|locked memory|pending signals/.test(line))
      .map((line) => `  ${line}`).join("\n")}`);
  lines.push(`df /dev/shm:\n  ${command(["df", "-h", "/dev/shm"]).replace(/\n/g, "\n  ")}`);
  lines.push(`total threads: ${command(["sh", "-c", "ls -d /proc/[0-9]*/task/* 2>/dev/null | wc -l"])}`);
  for (const {pid, cmdline} of browserProcesses(executablePath)) {
    const status = read(`/proc/${pid}/status`);
    lines.push("");
    lines.push(`pid ${pid} ${cmdline[0].split("/").pop()} ${cmdline.slice(1, 3).join(" ").slice(0, 80)}`);
    lines.push(`  State ${field(status, "State")} Threads ${field(status, "Threads")} ` +
        `VmRSS ${field(status, "VmRSS")} fds ${count(`/proc/${pid}/fd`)} ` +
        `voluntary_ctxt_switches ${field(status, "voluntary_ctxt_switches")}`);
    const tasks = [];
    let taskIds = [];
    try {
      taskIds = readdirSync(`/proc/${pid}/task`);
    } catch (_) {
      taskIds = [];
    }
    for (const tid of taskIds) {
      const taskStatus = read(`/proc/${pid}/task/${tid}/status`);
      tasks.push(`${field(taskStatus, "Name")}|${field(taskStatus, "State").split(" ")[0]}|` +
          `${read(`/proc/${pid}/task/${tid}/wchan`).trim() || "-"}`);
    }
    const histogram = new Map();
    for (const task of tasks) histogram.set(task, (histogram.get(task) ?? 0) + 1);
    for (const [task, n] of [...histogram.entries()].sort((a, b) => b[1] - a[1])) {
      lines.push(`  ${String(n).padStart(4)} ${task}`);
    }
  }
  return `${lines.join("\n")}\n`;
}
