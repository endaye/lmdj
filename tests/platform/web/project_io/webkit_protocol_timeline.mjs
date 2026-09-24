import {spawn} from "node:child_process";
import {mkdir, rm, writeFile} from "node:fs/promises";
import {constants as osConstants} from "node:os";
import {dirname, resolve} from "node:path";
import {createInterface} from "node:readline";
import {pathToFileURL} from "node:url";

// Playwright's raw pw:protocol log is about 2 GiB for this one suite. Keep
// only the browser exchange that can locate a stuck navigation (#1570): the
// command and reply, page/target lifecycle, policy decision, document request,
// and frame commit. A failing run retains this bounded timeline beside its
// trace and Linux process snapshot; a passing run discards it.
const BROWSER_EVENTS = new Set([
  "Playwright.pageProxyCreated", "Playwright.pageProxyDestroyed",
  "Playwright.provisionalLoadFailed", "Target.targetCreated",
  "Target.targetDestroyed", "Target.targetCrashed",
]);
const PAGE_EVENTS = new Set([
  "Page.willCheckNavigationPolicy", "Page.didCheckNavigationPolicy",
  "Page.frameNavigated", "Page.domContentEventFired", "Page.loadEventFired",
  "Network.requestWillBeSent", "Network.responseReceived",
  "Network.loadingFailed",
]);
// The complete 40-case suite currently emits about 3,000 selected events.
// Leave enough headroom that a failure near either end survives later cases.
const MAX_EVENTS = 32768;

function protocolPacket(line) {
  const marker = "pw:protocol ";
  const start = line.indexOf(marker);
  if (start < 0) return null;
  const encoded = line.indexOf("{", start + marker.length);
  const end = line.lastIndexOf("}");
  if (encoded < 0 || end < encoded) return null;
  const direction = line.slice(start + marker.length, encoded).includes("SEND") ? "send" : "recv";
  try {
    return {time: line.slice(0, start).trim() || new Date().toISOString(),
      direction, packet: JSON.parse(line.slice(encoded, end + 1))};
  } catch {
    return {time: line.slice(0, start).trim() || new Date().toISOString(),
      direction, malformed: true};
  }
}

export class WebkitProtocolTimeline {
  constructor() {
    this.navigationIds = new Map();
  }

  record(line) {
    // Most lines contain large screencast frames, Wasm payloads or injected
    // scripts. Reject them before JSON.parse so the diagnostic cannot echo
    // those bytes into the failure artifact.
    if (!line.includes("pw:protocol ")) return null;
    // Multiple browser connections can interleave on stderr and reuse outer
    // command ids. An overlapping send makes the pending reply ambiguous;
    // a lower id alone says nothing about worker or connection identity.
    const command = line.match(/pw:protocol SEND[^\{]*\{"id":(\d+),"method":"([^"]+)"/);
    if (command && command[2] !== "Playwright.navigate") {
      const pending = this.navigationIds.get(Number(command[1]));
      if (pending) {
        pending.ambiguous = true;
        return {time: new Date().toISOString(), event: "navigation-id-reused",
          id: Number(command[1]), pageProxyId: pending.pageProxyId};
      }
    }
    const namedEvent = line.includes("Playwright.navigate") ||
      line.includes("Playwright.pageProxyCreated") ||
      line.includes("Playwright.pageProxyDestroyed") ||
      line.includes("Playwright.provisionalLoadFailed") ||
      line.includes("Target.targetCreated") ||
      line.includes("Target.targetDestroyed") ||
      line.includes("Target.targetCrashed") ||
      line.includes("NavigationPolicy") || line.includes("frameNavigated") ||
      line.includes("EventFired") || line.includes("Network.requestWillBeSent") ||
      line.includes("Network.responseReceived") || line.includes("Network.loadingFailed");
    if (!namedEvent && ![...this.navigationIds.keys()].some(id =>
      line.includes(`"id":${id}`))) return null;

    const decoded = protocolPacket(line);
    if (!decoded) return null;
    const {time, direction, packet} = decoded;
    if (decoded.malformed) return {time, event: "protocol-parse-error"};

    if (direction === "send" && packet.method === "Playwright.navigate") {
      const ambiguous = this.navigationIds.has(packet.id);
      const result = {time, event: "navigate-send", id: packet.id,
        pageProxyId: packet.params?.pageProxyId, ...(ambiguous ? {idAmbiguous: true} : {}),
        frameId: packet.params?.frameId, url: packet.params?.url};
      this.navigationIds.set(packet.id, {...result, ambiguous});
      return result;
    }
    if (direction === "recv" && !packet.method && this.navigationIds.has(packet.id)) {
      const sent = this.navigationIds.get(packet.id);
      if (!sent.ambiguous) this.navigationIds.delete(packet.id);
      return {time, event: sent.ambiguous ? "navigate-reply-ambiguous" : "navigate-reply",
        id: packet.id,
        ...(sent.ambiguous ? {candidatePageProxyId: sent.pageProxyId} :
          {pageProxyId: sent.pageProxyId}),
        loaderId: packet.result?.loaderId, error: packet.error?.message};
    }
    if (direction !== "recv") return null;

    if (BROWSER_EVENTS.has(packet.method)) {
      const params = packet.params ?? {};
      if (packet.method === "Playwright.pageProxyDestroyed") {
        const destroyed = params.pageProxyId ?? packet.pageProxyId;
        for (const [id, sent] of this.navigationIds) {
          if (sent.pageProxyId === destroyed) this.navigationIds.delete(id);
        }
      }
      return {time, event: packet.method, pageProxyId: params.pageProxyId ?? packet.pageProxyId,
        targetId: params.targetInfo?.targetId ?? params.targetId,
        loaderId: params.loaderId, error: params.error,
        crashed: params.crashed};
    }
    if (packet.method !== "Target.dispatchMessageFromTarget" ||
        typeof packet.params?.message !== "string") return null;
    let inner;
    try { inner = JSON.parse(packet.params.message); } catch { return null; }
    if (!PAGE_EVENTS.has(inner.method)) return null;
    const params = inner.params ?? {};
    if (inner.method.startsWith("Network.") &&
        params.type !== "Document" && inner.method !== "Network.loadingFailed") return null;
    return {time, event: inner.method, pageProxyId: packet.pageProxyId,
      targetId: packet.params.targetId, frameId: params.frameId ?? params.frame?.id,
      loaderId: params.loaderId ?? params.frame?.loaderId,
      requestId: params.requestId, url: params.request?.url ?? params.response?.url ?? params.frame?.url,
      status: params.response?.status, cancel: params.cancel,
      error: params.errorText};
  }
}

async function closesWithin(promise, milliseconds) {
  let timer;
  try {
    return await Promise.race([promise.then(() => true),
      new Promise(resolve => { timer = setTimeout(() => resolve(false), milliseconds); })]);
  } finally {
    clearTimeout(timer);
  }
}

function reportDiagnostic(message) {
  try { process.stderr.write(`${message}\n`); } catch { /* preserve proof status */ }
}

export async function runWithProtocolTimeline(outputPath, command, args) {
  const timeline = new WebkitProtocolTimeline();
  const events = [];
  let droppedEvents = 0;
  let diagnosticError = null;
  let child;
  let childClosed;
  let hasClosed = false;
  let streamError = null;
  try {
    const environment = {...process.env,
      DEBUG: [process.env.DEBUG, "pw:protocol"].filter(Boolean).join(",")};
    // The debug package already writes to stderr. Reopening /dev/stderr as a
    // DEBUG_FILE fails with ENXIO when the child inherits a captured pipe.
    delete environment.DEBUG_FILE;
    child = spawn(command, args, {stdio: ["inherit", "inherit", "pipe"],
      env: environment});
    childClosed = new Promise(resolveClose => child.once("close", (code, signal) => {
      hasClosed = true;
      resolveClose({code, signal});
    }));
    child.on("error", error => { diagnosticError = error; });
    try {
      for await (const line of createInterface({input: child.stderr})) {
        if (!line.includes("pw:protocol ")) {
          if (line.trim()) reportDiagnostic(line);
          continue;
        }
        const event = timeline.record(line);
        if (event) {
          events.push(event);
          if (events.length > MAX_EVENTS) {
            events.shift();
            droppedEvents++;
          }
        }
      }
    } catch (error) {
      streamError = error;
    }
    // If readline ended early, keep draining the pipe while the proof exits.
    child.stderr.resume();
    const result = await childClosed;
    if (diagnosticError) reportDiagnostic(`protocol diagnostic unavailable: ${diagnosticError.message}`);
    if (streamError) reportDiagnostic(`protocol diagnostic stream unavailable: ${streamError.message}`);
    if (result.code !== 0 || result.signal) {
      try {
        await mkdir(dirname(outputPath), {recursive: true});
        const retained = droppedEvents ?
          [{time: new Date().toISOString(), event: "timeline-truncated", droppedEvents}, ...events] :
          events;
        await writeFile(outputPath, retained.map(event => JSON.stringify(event)).join("\n") + "\n");
        reportDiagnostic(`WebKit navigation protocol timeline: ${outputPath} (${events.length} events retained)`);
      } catch (error) {
        reportDiagnostic(`protocol diagnostic unavailable: ${error.message}`);
      }
    } else {
      try {
        await rm(outputPath, {force: true});
      } catch (error) {
        reportDiagnostic(`protocol diagnostic cleanup unavailable: ${error.message}`);
      }
    }
    return result.code ?? (result.signal ? 128 + (osConstants.signals[result.signal] ?? 0) : 127);
  } finally {
    if (child && !hasClosed) {
      if (child.exitCode === null && child.signalCode === null) child.kill();
      if (!await closesWithin(childClosed, 5_000)) {
        child.stderr?.destroy();
        if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
        await childClosed;
      }
    }
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const [outputPath, command, ...args] = process.argv.slice(2);
  if (!outputPath || !command) {
    console.error("usage: node webkit_protocol_timeline.mjs OUTPUT COMMAND [ARGS...]\n" +
      "why: no proof command or output path was supplied; remedy: pass both through the Web Toolchain proof");
    process.exitCode = 64;
  } else {
    process.exitCode = await runWithProtocolTimeline(outputPath, command, args);
  }
}
