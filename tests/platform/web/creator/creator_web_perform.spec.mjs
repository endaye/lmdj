import {showSamplePage} from "./fixtures/creator_navigation.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {createHash} from "node:crypto";
import {spawn} from "node:child_process";
import {once} from "node:events";
import {mkdtemp, readFile, rm} from "node:fs/promises";
import {createServer} from "node:http";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";

import {chromium, expect, test} from "@playwright/test";

import {WEB_RUNTIME_IDENTITY} from
  "../../../../products/lmdj/generated/web-runtime-identity.mjs";
import {waitForBootProject, waitForProjectReopen} from "./fixtures/creator_boot.mjs";
import {
  AUDIO_TRANSITION_TIMEOUT_MS,
  PROJECT_TRANSITION_TIMEOUT_MS,
  beginRecording,
  exportPerformanceWav,
  firstSignalFrame,
  installPerformWitnessSample,
  openPerform,
  parsePcm16StereoWav,
  pcm16Wav,
  stopRecording,
} from "./fixtures/perform_helpers.mjs";


const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

const repoRoot = resolve(import.meta.dirname, "../../../..");
const masterTapSource = resolve(
  repoRoot,
  "packages/web-runtime-platform/web/performance_master_tap_worklet.js",
);
const RECORDING_FRAMES = 86_400_000;
const RECORDING_QUEUE_BATCHES = 32;
// A Pattern launch is one bounded 30-second Runtime request, and the pending
// value it renders is visible only while that request is outstanding. Both
// halves of the transition are held to the same budget, because Playwright's
// 5-second default expects the Core to answer faster than the Core promises.
const LAUNCH_TRANSITION_TIMEOUT_MS = 30_000;
const PATTERN_ID = "00000000-0000-4000-8000-000000000010";
const pageErrors = new WeakMap();
const candidateOriginServers = new Map();

test.beforeEach(async ({page}) => {
  const errors = [];
  pageErrors.set(page, errors);
  page.on("pageerror", (error) => {
    errors.push(String(error?.message ?? error));
  });
});

test.afterEach(async ({page}) => {
  for (const server of candidateOriginServers.values()) {
    await new Promise((resolveClose) => {
      server.close(resolveClose);
      server.closeAllConnections();
    });
  }
  candidateOriginServers.clear();
  expect(pageErrors.get(page), "the Wasm runtime must not trap").toEqual([]);
});

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function inspectProjectTruth(page) {
  const response = await page.evaluate(() => window.lmdjWebRuntimeHost.transport.send({
    protocol_version: 1, request_id: crypto.randomUUID(), operation: "project.inspect", payload: {},
  }));
  expect(response.ok).toBe(true);
  return response.result;
}

async function observeMasterCaptureBatches(page) {
  await page.addInitScript(() => {
    const NativeAudioWorkletNode = window.AudioWorkletNode;
    window.__performMasterBatchProof = [];
    window.AudioWorkletNode = class extends NativeAudioWorkletNode {
      constructor(context, name, options) {
        super(context, name, options);
        if (name !== "lmdj-perform-master-tap") return;
        // Read the real tap's delivered PCM. Do not replace its processor,
        // sink, messages or audio graph with a deterministic capture source.
        this.port.addEventListener("message", ({data}) => {
          if (data?.type !== "batch") return;
          let peak = 0;
          for (const channel of data.channels) {
            for (const sample of channel) peak = Math.max(peak, Math.abs(sample));
          }
          window.__performMasterBatchProof.push({
            generation: data.generation,
            sequence: data.sequence,
            frames: data.channels[0].length,
            peak,
          });
        });
      }
    };
  });
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function replaceUnique(source, pattern, replacement, label) {
  const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
  const matches = [...source.matchAll(new RegExp(pattern.source, flags))];
  if (matches.length !== 1) {
    throw new Error(`${label} must occur exactly once; found ${matches.length}`);
  }
  return source.replace(pattern, replacement);
}

function regexEscape(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function patchCandidateMain(source, tapPath) {
  // The minifier may spell an integer as scientific notation, so identify the
  // generated identity object by its complete ordered key set and closing
  // deepFreeze call instead of matching the textual number representation.
  const resourcePattern = /resource_limits:\{(?=[^}]*decoded_float_pcm_bytes_per_bank:)(?=[^}]*decoded_float_pcm_bytes_resident:)(?=[^}]*decoded_float_pcm_bytes_total:)(?=[^}]*imported_wav_bytes:)(?=[^}]*ingest_channels:)(?=[^}]*ingest_decoded_frames:)(?=[^}]*ingest_source_bytes:)([^}]*)\}(?=\}\),)/;
  let candidate = replaceUnique(
    source,
    resourcePattern,
    (match) => `${match.slice(0, -1)},perform_recording_frames:${
      RECORDING_FRAMES},perform_recording_queue_batches:${
      RECORDING_QUEUE_BATCHES}}`,
    "bundled Product resource limits",
  );

  // Vite currently emits quoted strings as backticks, but accepting any JS
  // quote keeps this source-route witness stable across minifier upgrades.
  const captureRole = /\{prefix:([`'"])assets\/capture-worklet\.\1,role:([`'"])capture_worklet\2,suffix:([`'"])\.js\3\}(?=\],id:[`'"]creator-web[`'"],version:)/;
  candidate = replaceUnique(
    candidate,
    captureRole,
    (match) => `${match},{prefix:\`assets/perform-master-tap.\`,role:` +
      "`perform_master_tap_worklet`,suffix:`.js`}",
    "bundled Creator expected asset inventory",
  );

  const workletUrl = /([`'"])\/assets\/performance_master_tap_worklet-[^`'"]+\.js\1/;
  candidate = replaceUnique(
    candidate,
    workletUrl,
    `\`/${tapPath}\``,
    "Vite Perform master-tap URL",
  );
  return candidate;
}

function patchCandidateManifestBridge(source, compatibilityManifestBytes) {
  const compatibilityDigest = sha256(compatibilityManifestBytes);
  const compatibilityBase64 = compatibilityManifestBytes.toString("base64");
  return replaceUnique(
    source,
    /lmdjHostManifestBytes:([A-Za-z_$][\w$]*)\.canonical_bytes,lmdjHostManifestSha256:\1\.manifest_sha256/,
    "lmdjHostManifestBytes:Uint8Array.from(atob(" +
      `${JSON.stringify(compatibilityBase64)}),character=>character.charCodeAt(0)),` +
      `lmdjHostManifestSha256:${JSON.stringify(compatibilityDigest)}`,
    "candidate Host manifest compatibility bridge",
  );
}

async function responseBytes(requestContext, path) {
  const response = await requestContext.get(new URL(
    path,
    process.env.LMDJ_CREATOR_WEB_BASE_URL,
  ).href);
  if (!response.ok()) {
    throw new Error(`candidate route source is unavailable: ${path}`);
  }
  return response.body();
}

async function candidateOrigin(page, tapEntry, tapBytes) {
  const upstream = new URL(process.env.LMDJ_CREATOR_WEB_BASE_URL);
  const tapPath = `/${tapEntry.path}`;
  const server = createServer(async (request, response) => {
    try {
      const requestUrl = new URL(request.url, upstream);
      if (requestUrl.pathname === tapPath) {
        response.writeHead(200, {
          "Cache-Control": "public, max-age=31536000, immutable",
          "Content-Length": String(tapBytes.byteLength),
          "Content-Type": "text/javascript; charset=utf-8",
          "Cross-Origin-Resource-Policy": "same-origin",
          "X-Content-Type-Options": "nosniff",
        });
        if (request.method !== "HEAD") response.end(tapBytes);
        else response.end();
        return;
      }
      const upstreamResponse = await fetch(requestUrl, {
        method: request.method,
        redirect: "manual",
      });
      const payload = request.method === "HEAD"
        ? Buffer.alloc(0)
        : Buffer.from(await upstreamResponse.arrayBuffer());
      const headers = {};
      for (const [name, value] of upstreamResponse.headers) {
        if (!["connection", "content-encoding", "content-length", "transfer-encoding"]
          .includes(name.toLowerCase())) {
          headers[name] = value;
        }
      }
      if (request.method !== "HEAD") {
        headers["content-length"] = String(payload.byteLength);
      }
      response.writeHead(upstreamResponse.status, headers);
      response.end(payload);
    } catch {
      if (!response.headersSent) response.writeHead(502);
      response.end();
    }
  });
  await new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen);
    server.listen(0, "127.0.0.1", resolveListen);
  });
  const address = server.address();
  if (address === null || typeof address === "string") {
    server.closeAllConnections();
    throw new Error("candidate origin did not bind a TCP address");
  }
  candidateOriginServers.set(page, server);
  return `http://127.0.0.1:${address.port}`;
}

async function routeCandidateIdentity(page) {
  const originalManifestBytes = await responseBytes(
    page.request,
    "/host-manifest.json",
  );
  const originalManifest = JSON.parse(originalManifestBytes.toString("utf8"));
  const originalMain = originalManifest.assets.find(
    ({role}) => role === "host_main",
  );
  const originalRuntime = originalManifest.assets.find(
    ({role}) => role === "runtime_script",
  );
  if (!originalMain) throw new Error("packaged Creator host_main is missing");
  if (!originalRuntime) throw new Error("packaged Creator runtime_script is missing");
  const formalTap = originalManifest.assets.find(
    ({role}) => role === "perform_master_tap_worklet",
  );
  if (
    originalManifest.resource_limits.perform_recording_frames ===
      RECORDING_FRAMES &&
    originalManifest.resource_limits.perform_recording_queue_batches ===
      RECORDING_QUEUE_BATCHES &&
    formalTap !== undefined
  ) {
    // Task 10 reruns this exact suite against the formal Build. Once the
    // Assembly owns the capability, the proof must stop routing a candidate.
    return Object.freeze({
      candidateManifest: originalManifest,
      mainEntry: originalMain,
      routed: false,
      tapEntry: formalTap,
    });
  }

  const [indexBytes, mainBytes, tapBytes] = await Promise.all([
    responseBytes(page.request, "/index.html"),
    responseBytes(page.request, `/${originalMain.path}`),
    readFile(masterTapSource),
  ]);
  const tapDigest = sha256(tapBytes);
  const tapEntry = Object.freeze({
    bytes: tapBytes.byteLength,
    path: `assets/perform-master-tap.${tapDigest}.js`,
    role: "perform_master_tap_worklet",
    sha256: tapDigest,
  });

  const bridgeFreeMainBytes = Buffer.from(
    patchCandidateMain(mainBytes.toString("utf8"), tapEntry.path),
    "utf8",
  );
  const bridgeFreeMainDigest = sha256(bridgeFreeMainBytes);
  const bridgeFreeMainEntry = Object.freeze({
    ...originalMain,
    bytes: bridgeFreeMainBytes.byteLength,
    path: `assets/main.${bridgeFreeMainDigest}.js`,
    sha256: bridgeFreeMainDigest,
  });
  // Task 10 owns the C++ manifest-gate migration. Until then this narrowly
  // scoped compatibility manifest removes only the two keys that the old gate
  // cannot parse. It describes the bridge-free candidate main, tap, Wasm, and
  // every other exact asset. The final candidate main differs only by embedding
  // these bytes at Runtime construction, which avoids a content-hash fixed
  // point while leaving runtime_script formal and directly loadable by the
  // Emscripten AudioWorklet. This proves the Task 2 Perform chain, not
  // same-manifest JS/C++ integrity; Task 10 removes routing and owns that formal
  // distribution evidence.
  const compatibilityManifest = {
    ...originalManifest,
    assets: [
      bridgeFreeMainEntry,
      originalRuntime,
      ...originalManifest.assets.filter(({role}) =>
        role !== "host_main" && role !== "runtime_script"),
      tapEntry,
    ],
    resource_limits: {
      ...originalManifest.resource_limits,
    },
  };
  const compatibilityManifestBytes = Buffer.from(
    canonicalJson(compatibilityManifest),
    "utf8",
  );
  const candidateMainBytes = Buffer.from(
    patchCandidateManifestBridge(
      bridgeFreeMainBytes.toString("utf8"),
      compatibilityManifestBytes,
    ),
    "utf8",
  );
  const mainDigest = sha256(candidateMainBytes);
  const mainEntry = Object.freeze({
    ...originalMain,
    bytes: candidateMainBytes.byteLength,
    path: `assets/main.${mainDigest}.js`,
    sha256: mainDigest,
  });
  const candidateManifest = {
    ...originalManifest,
    assets: [
      mainEntry,
      originalRuntime,
      ...originalManifest.assets.filter(({role}) =>
        role !== "host_main" && role !== "runtime_script"),
      tapEntry,
    ],
    resource_limits: {
      ...originalManifest.resource_limits,
      perform_recording_frames: RECORDING_FRAMES,
      perform_recording_queue_batches: RECORDING_QUEUE_BATCHES,
    },
  };
  const candidateManifestBytes = Buffer.from(
    canonicalJson(candidateManifest),
    "utf8",
  );
  const manifestDigest = sha256(candidateManifestBytes);
  let candidateIndex = indexBytes.toString("utf8");
  candidateIndex = replaceUnique(
    candidateIndex,
    /(<meta name="lmdj-host-manifest-sha256" content=")[0-9a-f]{64}("\s*\/?>)/,
    `$1${manifestDigest}$2`,
    "Creator manifest digest metadata",
  );
  candidateIndex = replaceUnique(
    candidateIndex,
    new RegExp(regexEscape(`./${originalMain.path}`)),
    `./${mainEntry.path}`,
    "Creator main asset binding",
  );

  const origin = await candidateOrigin(page, tapEntry, tapBytes);
  const responses = new Map([
    ["/index.html", {body: Buffer.from(candidateIndex), contentType: "text/html"}],
    ["/host-manifest.json", {
      body: candidateManifestBytes,
      contentType: "application/json",
    }],
    [`/${mainEntry.path}`, {
      body: candidateMainBytes,
      contentType: "text/javascript",
    }],
  ]);
  // Identity and main stay route-injected through the production construction
  // path. AudioWorklet fetches bypass Playwright routing, so the candidate
  // origin serves the exact hashed tap bytes while proxying formal assets.
  await page.route("**/*", async (route) => {
    const candidate = responses.get(new URL(route.request().url()).pathname);
    if (candidate === undefined) return route.fallback();
    const response = await route.fetch();
    await route.fulfill({response, status: 200, ...candidate});
  });
  return Object.freeze({
    candidateManifest,
    compatibilityManifest,
    bridgeFreeMainEntry,
    mainEntry,
    originalManifest,
    originalRuntime,
    origin,
    routed: true,
    tapEntry,
  });
}

async function installDependencyScenario(page, scenario = "none") {
  if (scenario === "none") return;
  await page.addInitScript((selected) => {
    const bindMethod = (target, key) => {
      const value = Reflect.get(target, key, target);
      return typeof value === "function" ? value.bind(target) : value;
    };
    const stereoBatch = (frames = 4_800) => [
      Float32Array.from({length: frames}, (_, frame) =>
        frame % 2 === 0 ? 0.25 : -0.25),
      Float32Array.from({length: frames}, (_, frame) =>
        frame % 3 === 0 ? -0.5 : 0.125),
    ];
    const deterministicTap = (mode) => async ({context}) => ({
      // Fault injection preserves the audible fallback path. The normal
      // journey does not install this seam and uses the real platform tap.
      destinationNode: context.destination,
      failProcessor() { return false; },
      async close() {},
      async start(sink) {
        let stopped = false;
        const stop = async () => {
          if (stopped) return;
          stopped = true;
          sink.onStopped();
        };
        setTimeout(() => {
          if (stopped) return;
          if (mode === "tap-failure") {
            sink.onBatch(stereoBatch(128));
            sink.onFailure("tap-failure", 256);
            void stop();
            return;
          }
          for (let batch = 0; batch < 33 && !stopped; batch += 1) {
            sink.onBatch(stereoBatch());
          }
        }, 0);
        return Object.freeze({stop});
      },
    });

    const seams = {...(window.__LMDJ_WEB_HOST_SEAMS__ ?? {})};
    if (selected === "writer-failure") {
      seams.createWavStreamWriter = (realWriter) => {
        let failed = false;
        return new Proxy(realWriter, {
          get(target, key) {
            if (key === "appendChannels" && !failed) {
              return async () => {
                failed = true;
                throw new Error("deterministic writer failure");
              };
            }
            return bindMethod(target, key);
          },
        });
      };
    } else if (selected === "tap-failure") {
      seams.createPerformanceMasterTap = deterministicTap("tap-failure");
    } else if (selected === "batch-33") {
      seams.createPerformanceMasterTap = deterministicTap("batch-33");
    } else if (selected === "bind-retry") {
      seams.createPerformanceRecordingStore = (realStore) => {
        let refused = false;
        return new Proxy(realStore, {
          get(target, key) {
            if (key === "bind" && !refused) {
              return async () => {
                refused = true;
                throw Object.assign(new Error("deterministic bind contention"), {
                  code: "PROJECT_BUSY",
                });
              };
            }
            return bindMethod(target, key);
          },
        });
      };
    } else {
      throw new Error(`unknown Stage 10 dependency scenario: ${selected}`);
    }
    window.__LMDJ_WEB_HOST_SEAMS__ = seams;
  }, scenario);
}

async function openCandidate(page, scenario = "none") {
  await installDependencyScenario(page, scenario);
  const candidate = await routeCandidateIdentity(page);
  // Resolve the formal (non-routed) entry against the proof server explicitly.
  // Crash-recovery journeys drive pages from connectOverCDP contexts, which
  // carry no Playwright baseURL, so a relative path cannot be navigated there.
  await page.goto(candidate.routed
    ? `${candidate.origin}/index.html`
    : new URL("/index.html", process.env.LMDJ_CREATOR_WEB_BASE_URL).href);
  await waitForBootProject(page);
  expect(candidate.candidateManifest.resource_limits).toMatchObject({
    perform_recording_frames: RECORDING_FRAMES,
    perform_recording_queue_batches: RECORDING_QUEUE_BATCHES,
  });
  // host_favicon is the last packaged asset at Host 5.0.0. The tap this
  // journey loads is the perform_master_tap_worklet entry, including the one
  // a routed candidate appends after the formal inventory.
  expect(candidate.candidateManifest.assets.filter(
    ({role}) => role === "perform_master_tap_worklet",
  ).at(-1)).toEqual(candidate.tapEntry);
  if (candidate.routed) {
    const {
      perform_recording_frames: _frames,
      perform_recording_queue_batches: _batches,
      ...legacyLimits
    } = candidate.candidateManifest.resource_limits;
    expect(candidate.compatibilityManifest.resource_limits).toEqual(legacyLimits);
    expect(candidate.compatibilityManifest.assets).toEqual(
      candidate.candidateManifest.assets.map((asset) =>
        asset.role === "host_main" ? candidate.bridgeFreeMainEntry : asset),
    );
    expect(candidate.candidateManifest.assets.find(({role}) =>
      role === "runtime_script")).toEqual(candidate.originalRuntime);
    expect(candidate.candidateManifest.assets.find(({role}) =>
      role === "runtime_wasm")).toEqual(
      candidate.originalManifest.assets.find(({role}) => role === "runtime_wasm"),
    );
  }
  return candidate;
}

async function importProject(page) {
  await page.getByRole("button", {name: "Project", exact: true}).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

async function openLocalProject(page) {
  // The imported Project is remembered, so a successor or reloaded document
  // reopens it by itself; a previous owner's writer release shows as a
  // retryable PROJECT_BUSY.
  await waitForProjectReopen(page, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await page.getByRole("button", {name: "Project", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

async function activateAudio(page) {
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
}

async function importActivateAndPerform(page, scenario = "none") {
  const candidate = await openCandidate(page, scenario);
  await importProject(page);
  await activateAudio(page);
  await openPerform(page);
  return candidate;
}

async function navigateSuccessor(context, url) {
  // Chromium may restore the crashed Project tab alongside about:blank.
  // Keep one successor page so that an unintended restored tab cannot acquire
  // the Project's writer while this recovery journey opens the same bundle.
  const existing = context.pages();
  const successor = existing.find(page => page.url() === "about:blank")
    ?? await context.newPage();
  await Promise.all(existing.filter(page => page !== successor)
    .map(page => page.close()));
  expect(context.pages()).toHaveLength(1);
  expect(context.pages()[0]).toBe(successor);
  await installDependencyScenario(successor);
  await routeCandidateIdentity(successor);
  await successor.goto(url);
  return successor;
}

async function openProjectSuccessor(context, url) {
  const successor = await navigateSuccessor(context, url);
  await openLocalProject(successor);
  await activateAudio(successor);
  await openPerform(successor);
  return successor;
}

// A relaunch on a profile whose previous browser was killed restores that
// session's tabs. A restored Creator tab boots, reopens the remembered Project
// and owns its writer, so the successor this journey drives would be a second
// tab that is correctly refused. Remove the session-restore state so the
// relaunch opens only the page the journey asks for.
async function discardRestorableSession(userDataDir) {
  const profile = join(userDataDir, "Default");
  for (const entry of ["Sessions", "Current Session", "Current Tabs", "Last Session", "Last Tabs"]) {
    await rm(join(profile, entry), {recursive: true, force: true});
  }
}

function killProcessGroup(child) {
  try {
    process.kill(-child.pid, "SIGKILL");
  } catch {
    child.kill("SIGKILL");
  }
}

async function removeProfile(userDataDir) {
  // Second line of defence for the same race: Node retries ENOTEMPTY/EBUSY
  // with linear backoff instead of failing the test in its `finally`.
  await rm(userDataDir, {recursive: true, force: true, maxRetries: 10, retryDelay: 200});
}

class CrashableLaunchError extends Error {}

// One launch of a separate Chromium the journey can SIGKILL. A launch whose
// endpoint never answers is killed and reported, never kept: the caller
// relaunches instead of waiting longer on the same process.
async function launchCrashableChromium(userDataDir) {
  const activePortPath = join(userDataDir, "DevToolsActivePort");
  await rm(activePortPath, {force: true});
  await discardRestorableSession(userDataDir);
  // Own process group: Chromium's renderer, GPU and utility children are
  // separate processes that keep writing `<profile>/Default/` for a moment
  // after the browser process dies. Killing only the parent races the
  // fixture's `rm` against them (#684); killing the group does not.
  const child = spawn(chromium.executablePath(), [
    "--headless",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    `--user-data-dir=${userDataDir}`,
    "--remote-debugging-port=0",
    "about:blank",
  ], {stdio: "ignore", detached: true});
  const abandon = async (message) => {
    if (child.exitCode === null && child.signalCode === null) {
      const exited = once(child, "exit");
      killProcessGroup(child);
      await exited;
    }
    throw new CrashableLaunchError(message);
  };
  let endpoint = null;
  for (let attempt = 0; attempt < 100 && endpoint === null; attempt += 1) {
    try {
      const [port] = (await readFile(activePortPath, "utf8")).trim().split(/\s+/);
      endpoint = `http://127.0.0.1:${port}`;
    } catch {
      await new Promise((resolveWait) => setTimeout(resolveWait, 50));
    }
  }
  if (endpoint === null) await abandon("Crashable Chromium did not publish its DevTools endpoint");
  let browser = null;
  for (let attempt = 0; attempt < 20 && browser === null; attempt += 1) {
    try {
      browser = await chromium.connectOverCDP(endpoint);
    } catch {
      await new Promise((resolveWait) => setTimeout(resolveWait, 50));
    }
  }
  if (browser === null) await abandon("Crashable Chromium DevTools endpoint was unreachable");
  return {child, browser};
}

// #1869: under load a launched Chromium can publish its port before the
// endpoint answers within the connect budget. Relaunch it -- each attempt keeps
// the same budget -- rather than widen the wait; the last failure is reported.
const CRASHABLE_LAUNCH_ATTEMPTS = 3;

async function launchCrashableCreatorContext(userDataDir) {
  let launched = null;
  for (let attempt = 1; launched === null; attempt += 1) {
    try {
      launched = await launchCrashableChromium(userDataDir);
    } catch (error) {
      if (!(error instanceof CrashableLaunchError) || attempt >= CRASHABLE_LAUNCH_ATTEMPTS) throw error;
      console.warn(`crashable Chromium launch ${attempt}/${CRASHABLE_LAUNCH_ATTEMPTS}: ${error.message}; relaunching`);
    }
  }
  const {child, browser} = launched;
  const context = browser.contexts()[0];
  if (context === undefined) {
    killProcessGroup(child);
    throw new Error("Crashable Chromium default context is unavailable");
  }
  const page = context.pages()[0] ?? await context.newPage();
  return Object.freeze({
    browser,
    context,
    page,
    async close() {
      const client = await browser.newBrowserCDPSession();
      await client.send("Browser.close").catch(() => {});
      await expect.poll(() => child.exitCode, {timeout: 30_000}).toBe(0);
      killProcessGroup(child);
      await browser.close().catch(() => {});
    },
    async kill() {
      if (child.exitCode === null) {
        const exited = once(child, "exit");
        killProcessGroup(child);
        await exited;
      }
      await browser.close().catch(() => {});
    },
  });
}

// Confirm the remembered identity on disk before the separate owner-loss leg.
// A clean cross-process reopen is the checkpoint, then SIGKILL still exercises
// an active recording and automatic recovery on a new process.
async function launchPersistedCreatorOwner(profile) {
  let process = await launchCrashableCreatorContext(profile);
  try {
    const candidate = await importActivateAndPerform(process.page);
    const url = candidate.routed ? `${candidate.origin}/index.html` : process.page.url();
    const before = await inspectProjectTruth(process.page);
    await process.close();
    process = await launchCrashableCreatorContext(profile);
    const page = await openProjectSuccessor(process.context, url);
    expect((await inspectProjectTruth(page)).project).toEqual(before.project);
    return {process, page, url};
  } catch (error) {
    await process.kill().catch(() => {});
    throw error;
  }
}

function projectRevisionLocator(page) {
  return page.locator(".overview-facts div").filter({
    has: page.getByText("Rev", {exact: true}),
  }).getByRole("definition");
}

async function projectRevision(page) {
  const value = Number(await projectRevisionLocator(page).textContent());
  if (!Number.isSafeInteger(value)) throw new Error("Project revision is unavailable");
  return value;
}

async function expectRevisionAfter(page, before) {
  await expect.poll(() => projectRevision(page), {
    timeout: PROJECT_TRANSITION_TIMEOUT_MS,
  }).toBeGreaterThan(before);
  return projectRevision(page);
}

async function savePerformanceWithBusyRetry(page, name) {
  const nameField = page.getByRole("textbox", {name: "Performance name"});
  const save = page.getByRole("button", {name: "Save Performance"});
  const saved = page.getByText(name, {exact: true});
  const alert = page.getByRole("alert");
  const busy = alert.filter({
    hasText: /Project is busy.*retry Save Performance/i,
  });
  await nameField.fill(name);
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await expect(save).toBeEnabled();
    await save.click();
    await page.evaluate(() => new Promise((resolveFrame) => {
      requestAnimationFrame(() => requestAnimationFrame(resolveFrame));
    }));
    const outcome = async () => {
      if (await saved.isVisible()) return "saved";
      if (await busy.isVisible() && await save.isEnabled()) return "busy";
      if (await alert.isVisible()) return `error:${await alert.textContent()}`;
      return "pending";
    };
    await expect.poll(outcome, {timeout: PROJECT_TRANSITION_TIMEOUT_MS})
      .not.toBe("pending");
    const settled = await outcome();
    if (settled === "saved") return;
    if (settled !== "busy") {
      throw new Error(`Save Performance failed: ${settled.slice("error:".length)}`);
    }
  }
  throw new Error("Save Performance remained busy after five explicit retries");
}

async function assignThenMovePattern(page) {
  const before = await projectRevision(page);
  const slots = page.getByRole("button", {name: /^Launch Pattern /});
  for (let index = 0; index < 16; index += 1) {
    await expect(slots.nth(index)).not.toHaveAttribute("data-pattern-id", /.+/);
  }

  await page.getByRole("combobox", {name: "Pattern assignment"})
    .selectOption(PATTERN_ID);
  await page.getByRole("combobox", {name: "Pattern slot", exact: true})
    .selectOption("0");
  await page.getByRole("button", {name: "Assign Pattern"}).click();
  const assignedRevision = await expectRevisionAfter(page, before);
  await expect(slots.nth(0)).toHaveAttribute("data-pattern-id", PATTERN_ID);

  await page.getByRole("combobox", {name: "Move Pattern from"})
    .selectOption({value: "0"});
  const moveTo = page.getByRole("combobox", {name: "Move Pattern to"});
  await moveTo.selectOption({value: "1"});
  await expect(moveTo).toHaveValue("1");
  await page.getByRole("button", {name: "Move Pattern"}).click();
  const movedRevision = await expectRevisionAfter(page, assignedRevision);
  await expect(slots.nth(0)).not.toHaveAttribute("data-pattern-id", /.+/);
  await expect(slots.nth(1)).toHaveAttribute("data-pattern-id", PATTERN_ID);
  return movedRevision;
}

async function beginFaultingRecording(page) {
  const before = await projectRevision(page);
  await page.getByRole("button", {name: "Record Performance"}).click();
  const status = page.getByRole("status", {name: "Performance recording status"});
  await expect(status).toContainText("stopped", {
    timeout: PROJECT_TRANSITION_TIMEOUT_MS,
  });
  await expectRevisionAfter(page, before);
  return status;
}

async function applyRecoveryAfterOwnerRelease(page) {
  const status = page.getByRole("status", {name: "Performance recovery status"});
  const apply = page.getByRole("button", {name: "Apply recovery"});
  for (let attempt = 0; attempt < 10; attempt += 1) {
    await apply.click();
    await page.waitForTimeout(250);
    if (/applied.*closed.*Pad/i.test(await status.textContent() ?? "")) return;
  }
  await expect(status).toContainText(/applied.*closed.*Pad/i);
}

async function armAttributeObservation(locator, attribute, value) {
  await locator.evaluate((element, expected) => {
    const proofAttribute = `data-proof-saw-${expected.attribute.replace(/^data-/, "")}`;
    element.removeAttribute(proofAttribute);
    const observe = () => {
      if (element.getAttribute(expected.attribute) !== expected.value) return false;
      element.setAttribute(proofAttribute, expected.value);
      return true;
    };
    if (observe()) return;
    const observer = new MutationObserver(() => {
      if (observe()) observer.disconnect();
    });
    observer.observe(element, {
      attributes: true,
      attributeFilter: [expected.attribute],
    });
  }, {attribute, value});
}

function changedFrameCount(left, right, tolerance = 32) {
  expect(left).toHaveLength(right.length);
  return left.reduce((count, sample, index) =>
    count + (Math.abs(sample - right[index]) > tolerance ? 1 : 0), 0);
}

function verifyDeterministicMasterOutput(wav) {
  const fixtureFrames = 4_800;
  const firstDryStart = firstSignalFrame(wav.left);
  const firstDryLeft = wav.left.slice(firstDryStart, firstDryStart + fixtureFrames);
  const firstDryRight = wav.right.slice(firstDryStart, firstDryStart + fixtureFrames);
  expect(firstDryLeft).toHaveLength(fixtureFrames);
  expect(changedFrameCount(firstDryLeft, firstDryRight)).toBe(0);

  const secondDryStart = firstSignalFrame(
    wav.left,
    firstDryStart + fixtureFrames + 128,
  );
  const secondDryLeft = wav.left.slice(secondDryStart, secondDryStart + fixtureFrames);
  const secondDryRight = wav.right.slice(secondDryStart, secondDryStart + fixtureFrames);
  expect(secondDryStart - (firstDryStart + fixtureFrames)).toBeGreaterThan(2_400);
  expect(changedFrameCount(firstDryLeft, secondDryLeft)).toBeLessThan(64);
  expect(changedFrameCount(firstDryRight, secondDryRight)).toBeLessThan(64);
  expect(changedFrameCount(secondDryLeft, secondDryRight)).toBe(0);

  const wetStart = firstSignalFrame(
    wav.left,
    secondDryStart + fixtureFrames + 128,
  );
  const wetLeft = wav.left.slice(wetStart, wetStart + fixtureFrames);
  const wetRight = wav.right.slice(wetStart, wetStart + fixtureFrames);
  expect(wetLeft).toHaveLength(fixtureFrames);
  expect(wetStart - (secondDryStart + fixtureFrames)).toBeGreaterThan(2_400);
  expect(changedFrameCount(wetLeft, secondDryLeft)).toBeGreaterThan(2_400);
  expect(changedFrameCount(wetRight, secondDryRight)).toBeGreaterThan(2_400);
  expect(changedFrameCount(wetLeft, wetRight)).toBe(0);
}

async function opfsWavFiles(page) {
  return page.evaluate(async () => {
    const root = await navigator.storage.getDirectory();
    const files = [];
    async function walk(directory, prefix) {
      for await (const [name, handle] of directory.entries()) {
        const path = prefix === "" ? name : `${prefix}/${name}`;
        if (handle.kind === "directory") {
          await walk(handle, path);
          continue;
        }
        const file = await handle.getFile();
        if (file.size < 12) continue;
        const header = new Uint8Array(await file.slice(0, 12).arrayBuffer());
        const ascii = String.fromCharCode(...header);
        if (ascii.startsWith("RIFF") && ascii.slice(8, 12) === "WAVE") {
          files.push({path, size: file.size});
        }
      }
    }
    await walk(root, "");
    return files.sort((left, right) => left.path.localeCompare(right.path));
  });
}

async function replacePadSample(page) {
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  await page.getByTestId("physical-controls").getByRole("button", {name: "Bank A", exact: true}).click();
  const pad = page.getByRole("button", {name: /^Pad A01 — assigned — Key Q$/});
  await expect(pad).toBeVisible({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await pad.evaluate((element) => element.click());
  await showSamplePage(page, "Pad");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Replace Sample"}).click();
  await (await chooser).setFiles({
    name: "replacement-4801-frames.wav",
    mimeType: "audio/wav",
    buffer: pcm16Wav({frames: 4_801}),
  });
  await expect(page.getByRole("dialog", {name: "Replace Pad A01?"})).toBeVisible();
  await page.getByRole("button", {name: "Confirm replace"}).click();
  const longSource = page.getByRole("dialog", {name: "Pad A01 Long Source"});
  await expect(longSource).toBeVisible({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await longSource.getByRole("button", {name: "Commit selection"}).click();
  await expect(page.getByRole("button", {name: "Replace Sample"}))
    .toBeEnabled({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

async function recordShortPerformance(
  page,
  {name = "Night Set", withFx = false, tailMs = 0} = {},
) {
  await beginRecording(page);
  const pad = page.getByRole("button", {name: /^Pad A01\b/});
  await pad.dispatchEvent("pointerdown", {
    button: 0,
    isPrimary: true,
    pointerId: 71,
  });
  await page.waitForTimeout(120);
  await pad.dispatchEvent("pointerup", {
    button: 0,
    isPrimary: true,
    pointerId: 71,
  });
  if (withFx) {
    const filter = page.getByRole("slider", {name: "Filter"});
    await filter.dispatchEvent("pointerdown", {pointerId: 72});
    await filter.fill("630");
    await filter.dispatchEvent("pointerup", {pointerId: 72});
    await page.getByRole("button", {name: "HOLD"}).click();
  }
  if (tailMs > 0) {
    // Give the Performance a real musical span so a later replay is still
    // playing when the test acts on it. A trailing wait alone would not
    // extend replay, because the projection ends at the last event tick, so
    // close the span with a second Pad hit.
    await page.waitForTimeout(tailMs);
    await pad.dispatchEvent("pointerdown", {
      button: 0,
      isPrimary: true,
      pointerId: 73,
    });
    await page.waitForTimeout(120);
    await pad.dispatchEvent("pointerup", {
      button: 0,
      isPrimary: true,
      pointerId: 73,
    });
  }
  await stopRecording(page);
  await savePerformanceWithBusyRetry(page, name);
}

test("complete Perform journey persists projection, gestures, WAV, save, replay and empty Pad master capture", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(420_000);
  await observeMasterCaptureBatches(page);
  await importActivateAndPerform(page);
  await installPerformWitnessSample(page);

  let revision = await assignThenMovePattern(page);
  const recordingStatus = await beginRecording(page);
  revision = await expectRevisionAfter(page, revision);

  const pad = page.getByRole("button", {name: /^Pad A01\b/});
  await pad.dispatchEvent("pointerdown", {
    button: 0,
    isPrimary: true,
    pointerId: 21,
  });
  await expect(recordingStatus).toContainText(/open pads?\s*[:·]\s*1/i);
  await page.waitForTimeout(120);
  await pad.dispatchEvent("pointerup", {
    button: 0,
    isPrimary: true,
    pointerId: 21,
  });
  await expect(recordingStatus).toContainText(/open pads?\s*[:·]\s*0/i);

  const launch = page.getByRole("button", {name: "Launch Pattern 2"});
  await armAttributeObservation(launch, "data-launch", "pending");
  await launch.click();
  await expect(launch).toHaveAttribute("data-proof-saw-launch", "pending",
    {timeout: LAUNCH_TRANSITION_TIMEOUT_MS});
  await expect(launch).toHaveAttribute("data-launch", "acknowledged", {
    timeout: LAUNCH_TRANSITION_TIMEOUT_MS,
  });
  await expect(recordingStatus).toContainText(/last launch.*2.*acknowledged/i);

  await pad.dispatchEvent("pointerdown", {
    button: 0,
    isPrimary: true,
    pointerId: 24,
  });
  await page.waitForTimeout(120);
  await pad.dispatchEvent("pointerup", {
    button: 0,
    isPrimary: true,
    pointerId: 24,
  });

  const filter = page.getByRole("slider", {name: "Filter"});
  await filter.dispatchEvent("pointerdown", {pointerId: 22});
  await expect(recordingStatus).toContainText(/open FX\s*[:·]\s*1/i);
  await filter.fill("630");
  await pad.dispatchEvent("pointerdown", {
    button: 0,
    isPrimary: true,
    pointerId: 23,
  });
  await page.waitForTimeout(120);
  await pad.dispatchEvent("pointerup", {
    button: 0,
    isPrimary: true,
    pointerId: 23,
  });
  await filter.fill("631");
  await filter.dispatchEvent("pointerup", {pointerId: 22});
  await expect(recordingStatus).toContainText(/open FX\s*[:·]\s*0/i);
  await expect(filter).toHaveValue("631");

  const hold = page.getByRole("button", {name: "HOLD"});
  await hold.click();
  await expect(hold).toHaveAttribute("aria-pressed", "true");
  await expect(recordingStatus).toContainText(/hold\s*[:·]\s*on/i);
  await hold.click();
  await expect(hold).toHaveAttribute("aria-pressed", "false");
  await expect(recordingStatus).toContainText(/hold\s*[:·]\s*off/i);

  const bankRevision = await projectRevision(page);
  // The Perform strip's own Bank keys, not the physical column's: this leg
  // is about the strip reflecting the switch it made.
  const performBanks = page.getByRole("group", {name: "Perform Bank"});
  await performBanks.getByRole("button", {name: "Bank B", exact: true}).click();
  await expect(performBanks.getByRole("button", {name: "Bank B", exact: true}))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", {name: /^Pad B/})).toHaveCount(16);
  expect(await projectRevision(page)).toBe(bankRevision);

  await page.getByRole("button", {name: "Flush Performance"}).click();
  revision = await expectRevisionAfter(page, revision);
  await expect(recordingStatus).toContainText(/flushed/i);
  await stopRecording(page);
  const wav = parsePcm16StereoWav(await exportPerformanceWav(page));
  expect(wav.frames).toBeGreaterThan(0);
  verifyDeterministicMasterOutput(wav);

  await savePerformanceWithBusyRetry(page, "Night Set");
  revision = await expectRevisionAfter(page, revision);
  await expect(page.getByRole("status", {name: "WAV binding status"}))
    .toContainText("bound");

  const beforeReplace = revision;
  await replacePadSample(page);
  revision = await expectRevisionAfter(page, beforeReplace);
  // Re-open from the far side before replay. This proves the slot mapping,
  // saved Performance and Sample mutation came from Project inspection rather
  // than a surviving receipt or local reducer cache.
  await page.reload();
  await openLocalProject(page);
  expect(await projectRevision(page)).toBe(revision);
  await activateAudio(page);
  await openPerform(page);
  await expect(page.getByRole("button", {name: "Launch Pattern 2"}))
    .toHaveAttribute("data-pattern-id", PATTERN_ID);
  await expect(page.getByText("Night Set", {exact: true})).toBeVisible();

  await page.getByRole("button", {name: "Replay Night Set"}).click();
  const replayStatus = page.getByRole("status", {name: "Replay status"});
  await expect(replayStatus).toContainText("playing", {timeout: 30_000});
  await expect(replayStatus).toContainText(
    new RegExp(`resolved revision\\s*[:·]\\s*${revision}`, "i"),
  );
  // The Pad recording source is a System setting (brand mark entry).
  await page.getByRole("button", {name: "System", exact: true}).click();
  await page.getByRole("combobox", {name: "Pad recording source"}).selectOption("master");
  await page.getByRole("button", {name: "Back to music", exact: true}).click();
  await page.getByRole("button", {name: "Stop Replay"}).click();
  await expect(replayStatus).toContainText("stopped", {timeout: 30_000});
  // The shared Native proof fixture fills all64 Pads. Create the empty target
  // through the ordinary Sample control, then prove its far-side Truth before
  // the original Perform master-capture leg.
  const beforeDelete = await inspectProjectTruth(page);
  expect(beforeDelete.project.banks[1].pads[0].asset_id).not.toBeNull();
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await page.getByRole("button", {name: "Bank B", exact: true}).first().click();
  await page.getByRole("button", {name: /^Pad B01 — assigned/}).focus();
  await showSamplePage(page, "Pad");
  await page.getByRole("button", {name: "Delete Pad B01", exact: true}).click();
  revision = await expectRevisionAfter(page, revision);
  const afterDelete = await inspectProjectTruth(page);
  expect(afterDelete.project.banks[1].pads[0].asset_id).toBeNull();
  expect(afterDelete.project.assets).toEqual(beforeDelete.project.assets);
  expect(afterDelete.project.patterns).toEqual(beforeDelete.project.patterns);
  await openPerform(page);
  await page.getByRole("button", {name: "Bank B", exact: true}).first().click();
  const empty = page.getByRole("button", {name: /^Pad B01 — empty/});
  await empty.focus();
  const beforeCaptureBatches = await page.evaluate(() =>
    window.__performMasterBatchProof.length);
  await page.keyboard.down("KeyQ");
  await expect(page.getByRole("region", {name: "Pad recording"})).toContainText("recording");
  await page.getByRole("button", {name: "Replay Night Set"}).click();
  await expect(replayStatus).toContainText("playing", {
    timeout: LAUNCH_TRANSITION_TIMEOUT_MS,
  });
  // A replay acknowledgement is not a captured audio frame. Release only
  // after this take receives actual non-silent PCM through the real Master tap.
  await expect.poll(() => page.evaluate((after) =>
    window.__performMasterBatchProof.slice(after).some(({frames, peak}) =>
      frames > 0 && Number.isFinite(peak) && peak > 0), beforeCaptureBatches), {
    timeout: LAUNCH_TRANSITION_TIMEOUT_MS,
    message: "Replay must deliver non-silent PCM to the active Master capture",
  }).toBe(true);
  await page.keyboard.up("KeyQ");
  await expectRevisionAfter(page, revision);
  await expect(page.getByRole("button", {name: /^Pad B01 — assigned/})).toBeVisible();
  const captured = await inspectProjectTruth(page);
  const capturedId = captured.project.banks[1].pads[0].asset_id;
  expect(captured.project.assets[capturedId].artifact).toMatchObject({
    byte_length: expect.any(Number), media_type: "audio/wav", sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
  });
  expect(captured.project.assets[capturedId].artifact.byte_length).toBeGreaterThan(44);
  await page.reload(); await openLocalProject(page);
  const reopened = await inspectProjectTruth(page);
  expect(reopened.project.assets[capturedId].artifact).toEqual(captured.project.assets[capturedId].artifact);
});

test("discard deletes its temporary WAV and owner-loss recovery applies or discards durable truth", async ({browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(420_000);
  const applyProfile = await mkdtemp(join(tmpdir(), "lmdj-perform-owner-loss-apply-"));
  let ownerProcess = null;
  let applyingProcess = null;
  try {
    const owner = await launchPersistedCreatorOwner(applyProfile);
    ownerProcess = owner.process;
    const ownerPage = owner.page;
    const candidateUrl = owner.url;
    const baselineWavs = await opfsWavFiles(ownerPage);

    await beginRecording(ownerPage);
    await ownerPage.getByRole("button", {name: /^Pad A01\b/}).click();
    await stopRecording(ownerPage);
    expect((await opfsWavFiles(ownerPage)).length).toBeGreaterThan(baselineWavs.length);
    await ownerPage.getByRole("button", {name: "Discard Performance"}).click();
    await expect(ownerPage.getByRole("status", {name: "WAV recording status"}))
      .toContainText("temporary removed");
    await expect.poll(() => opfsWavFiles(ownerPage)).toEqual(baselineWavs);

    await beginRecording(ownerPage);
    await ownerPage.getByRole("button", {name: /^Pad A01\b/}).dispatchEvent("pointerdown", {
      button: 0,
      isPrimary: true,
      pointerId: 31,
    });
    await expect(ownerPage.getByRole("status", {name: "Performance recording status"}))
      .toContainText("open Pads: 1", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    await ownerProcess.kill();
    ownerProcess = null;

    applyingProcess = await launchCrashableCreatorContext(applyProfile);
    const applyingPage = await openProjectSuccessor(
      applyingProcess.context,
      candidateUrl,
    );
    await expect(applyingPage.getByRole("button", {name: "Apply recovery"})).toBeVisible();
    const beforeApply = await projectRevision(applyingPage);
    await applyRecoveryAfterOwnerRelease(applyingPage);
    await expectRevisionAfter(applyingPage, beforeApply);
    await expect(applyingPage.getByRole("status", {name: "Performance recovery status"}))
      .toContainText(/applied.*closed.*Pad/i);
    await expect(applyingPage.getByRole("button", {name: "Replay Untitled Performance"}))
      .toBeVisible();
  } finally {
    await ownerProcess?.kill().catch(() => {});
    await applyingProcess?.kill().catch(() => {});
    await removeProfile(applyProfile);
  }

  const discardProfile = await mkdtemp(join(tmpdir(), "lmdj-perform-owner-loss-discard-"));
  let discardOwnerProcess = null;
  let discardingProcess = null;
  try {
    const owner = await launchPersistedCreatorOwner(discardProfile);
    discardOwnerProcess = owner.process;
    const discardOwnerPage = owner.page;
    const candidateUrl = owner.url;
    await beginRecording(discardOwnerPage);
    await discardOwnerPage.getByRole("button", {name: /^Pad A02\b/}).dispatchEvent(
      "pointerdown",
      {button: 0, isPrimary: true, pointerId: 32},
    );
    await expect(discardOwnerPage.getByRole("status", {
      name: "Performance recording status",
    })).toContainText("open Pads: 1", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    await discardOwnerProcess.kill();
    discardOwnerProcess = null;

    discardingProcess = await launchCrashableCreatorContext(discardProfile);
    const discardingPage = await openProjectSuccessor(
      discardingProcess.context,
      candidateUrl,
    );
    const beforeDiscard = await projectRevision(discardingPage);
    await discardingPage.getByRole("button", {name: "Discard recovery"}).click();
    await expect(discardingPage.getByRole("status", {name: "Performance recovery status"}))
      .toContainText("discarded");
    expect(await projectRevision(discardingPage)).toBe(beforeDiscard);
  } finally {
    await discardOwnerProcess?.kill().catch(() => {});
    await discardingProcess?.kill().catch(() => {});
    await removeProfile(discardProfile);
  }
});

for (const failure of [
  {
    name: "writer failure",
    scenario: "writer-failure",
    message: /storage failed.*durable WAV prefix/i,
    reason: "writer-error",
  },
  {
    name: "tap failure",
    scenario: "tap-failure",
    message: /audio tap could not deliver.*durable WAV prefix/i,
    reason: "tap-failure",
  },
  {
    name: "the 33rd queued batch",
    scenario: "batch-33",
    message: /storage could not keep up.*durable WAV prefix/i,
    reason: "backpressure",
  },
]) {
  test(`${failure.name} seals only the durable WAV prefix and leaves live audio running`, async ({page, browserName}) => {
    test.skip(browserName !== "chromium");
    test.setTimeout(240_000);
    await importActivateAndPerform(page, failure.scenario);
    await beginFaultingRecording(page);
    await expect(page.getByRole("alert")).toContainText(failure.message, {
      timeout: PROJECT_TRANSITION_TIMEOUT_MS,
    });
    await expect(page.getByRole("status", {name: "WAV recording status"}))
      .toContainText(`sealed · ${failure.reason}`);
    await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
    parsePcm16StereoWav(await exportPerformanceWav(page));
  });
}

test("a retryable WAV bind keeps the real Store receipt path and removes the temporary file after retry", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await importActivateAndPerform(page, "bind-retry");
  const baselineWavs = await opfsWavFiles(page);
  await recordShortPerformance(page, {name: "Retry Set"});

  await expect(page.getByRole("alert")).toContainText("The recording could not be saved into the Project. Choose Retry WAV bind.");
  expect((await opfsWavFiles(page)).length).toBeGreaterThan(baselineWavs.length);
  const revision = await projectRevision(page);
  await page.getByRole("button", {name: "Retry WAV bind"}).click();
  await expect(page.getByRole("status", {name: "WAV binding status"}))
    .toContainText("bound", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expectRevisionAfter(page, revision);
  await expect.poll(async () => (await opfsWavFiles(page)).filter(
    ({path}) => !/[0-9a-f]{64}\.wav$/.test(path),
  )).toEqual([]);
});

test("an active recording receives an empty-slot acknowledgement and interruption closes the same capture", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await importActivateAndPerform(page);
  const status = await beginRecording(page);
  const emptySlot = page.getByRole("button", {name: "Launch Pattern 16"});
  await expect(emptySlot).not.toHaveAttribute("data-pattern-id", /.+/);
  await armAttributeObservation(emptySlot, "data-launch", "pending");
  await emptySlot.click();
  await expect(emptySlot).toHaveAttribute("data-proof-saw-launch", "pending",
    {timeout: LAUNCH_TRANSITION_TIMEOUT_MS});
  // The budget crosses into the page as an argument: this callback is
  // stringified and run in the browser, where a Node-side module constant is
  // an unresolvable identifier. `armAttributeObservation` above passes its
  // arguments the same way for the same reason.
  await emptySlot.evaluate((element, timeoutMs) => new Promise((resolve, reject) => {
    const finish = () => {
      observer.disconnect();
      window.clearTimeout(timeout);
      resolve(undefined);
    };
    const observer = new MutationObserver(() => {
      if (element.getAttribute("data-launch") === "acknowledged") finish();
    });
    const timeout = window.setTimeout(() => {
      observer.disconnect();
      reject(new Error("empty-slot acknowledgement timed out"));
    }, timeoutMs);
    observer.observe(element, {attributes: true, attributeFilter: ["data-launch"]});
    if (element.getAttribute("data-launch") === "acknowledged") finish();
  }), LAUNCH_TRANSITION_TIMEOUT_MS);
  await expect(emptySlot).toHaveAttribute("data-launch", "acknowledged");
  await expect(page.getByRole("status", {name: "Pattern launch status"}))
    .toContainText("silent gap");
  await expect(status).toContainText(
    /open Pads?\s*[:·]\s*0.*last launch.*16.*acknowledged/i,
  );

  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.getByRole("status", {name: "WAV recording status"}))
    .toContainText("sealed", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(page.getByRole("button", {name: "Stop Performance"}))
    .toBeDisabled();
});

// #1726: an opened Project is remembered durably at once. Chromium commits
// localStorage lazily and rate-limits it, so a crash within about a minute of
// an import lost the write and the next boot reopened the boot-created Project.
test("a crash just after an import reopens the imported Project at the next boot", async ({browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  const profile = await mkdtemp(join(tmpdir(), "lmdj-perform-remembered-"));
  let ownerProcess = null;
  let successorProcess = null;
  try {
    ownerProcess = await launchCrashableCreatorContext(profile);
    const ownerPage = ownerProcess.page;
    const candidate = await openCandidate(ownerPage);
    const candidateUrl = candidate.routed
      ? `${candidate.origin}/index.html`
      : ownerPage.url();
    // Let the boot-created Project's write commit first: the import's write
    // then falls in the rate-limited window in which #1726 lost it.
    await ownerPage.waitForTimeout(6_000);
    await importProject(ownerPage);
    // An IndexedDB commit takes milliseconds; two seconds stays far inside
    // the minute that a rate-limited localStorage commit could wait.
    await ownerPage.waitForTimeout(2_000);
    await ownerProcess.kill();
    ownerProcess = null;

    successorProcess = await launchCrashableCreatorContext(profile);
    const successor = await navigateSuccessor(successorProcess.context, candidateUrl);
    await waitForProjectReopen(successor, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  } finally {
    await ownerProcess?.kill().catch(() => {});
    await successorProcess?.kill().catch(() => {});
    await removeProfile(profile);
  }
});

test("owner process loss leaves one recoverable recording and no second capture owner", async ({browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  const profile = await mkdtemp(join(tmpdir(), "lmdj-perform-owner-candidate-"));
  let ownerProcess = null;
  let successorProcess = null;
  try {
    const owner = await launchPersistedCreatorOwner(profile);
    ownerProcess = owner.process;
    const ownerPage = owner.page;
    const candidateUrl = owner.url;
    await beginRecording(ownerPage);
    await ownerPage.getByRole("button", {name: /^Pad A01\b/}).dispatchEvent(
      "pointerdown",
      {button: 0, isPrimary: true, pointerId: 51},
    );
    await expect(ownerPage.getByRole("status", {name: "Performance recording status"}))
      .toContainText("open Pads: 1", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    await ownerProcess.kill();
    ownerProcess = null;

    successorProcess = await launchCrashableCreatorContext(profile);
    const successor = await openProjectSuccessor(successorProcess.context, candidateUrl);
    await expect(successor.getByRole("button", {name: "Apply recovery"}))
      .toHaveCount(1);
    await expect(successor.getByRole("status", {name: "Performance recovery status"}))
      .toContainText("active");
    await expect(successor.getByRole("button", {name: "Record Performance"}))
      .toBeDisabled();
  } finally {
    await ownerProcess?.kill().catch(() => {});
    await successorProcess?.kill().catch(() => {});
    await removeProfile(profile);
  }
});

test("stopping a saved Performance replay restores neutral FX, HOLD and Pattern state", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  await importActivateAndPerform(page);
  await assignThenMovePattern(page);
  // The replay must still be playing when Stop Replay is clicked, otherwise
  // the run races natural completion and observes "complete · neutral"
  // instead of the abort path this test owns.
  await recordShortPerformance(page, {
    name: "Neutral Reset",
    withFx: true,
    tailMs: 6_000,
  });

  await page.getByRole("button", {name: "Replay Neutral Reset"}).click();
  const replayStatus = page.getByRole("status", {name: "Replay status"});
  await expect(replayStatus).toContainText("playing", {timeout: 30_000});
  await page.getByRole("button", {name: "Stop Replay"}).click();
  await expect(replayStatus).toContainText("stopped · neutral", {
    timeout: 30_000,
  });
  for (const slider of await page.getByRole("slider").all()) {
    await expect(slider).toHaveValue("500");
  }
  await expect(page.getByRole("button", {name: "HOLD"}))
    .toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", {name: "Launch Pattern 2"}))
    .toHaveAttribute("data-launch", "idle");
});

async function inspectedPadA1Pan(page) {
  return page.evaluate(async () => {
    const response = await window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "sample.inspect",
      payload: {slot: {bank: 0, pad: 0}},
    });
    return response.ok ? (response.result.playback.pan ?? 0) : response.error.code;
  });
}

test("a hard-left Pad pan silences the right channel of the recorded master output", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  await importActivateAndPerform(page);
  await installPerformWitnessSample(page);
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  await page.getByRole("button", {name: /^Pad A01 — assigned — Key Q$/})
    .evaluate((element) => element.click());
  expect(await inspectedPadA1Pan(page)).toBe(0);
  await showSamplePage(page, "Playback");
  const pan = page.getByRole("slider", {name: "Pad A01 Pan"});
  await pan.dispatchEvent("pointerdown", {pointerId: 81, isPrimary: true, button: 0});
  await pan.fill("-100");
  await pan.dispatchEvent("pointerup", {pointerId: 81, isPrimary: true, button: 0});
  await expect.poll(() => inspectedPadA1Pan(page), {
    timeout: PROJECT_TRANSITION_TIMEOUT_MS,
  }).toBe(-100);
  await expect(pan).toBeEnabled({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await openPerform(page);

  await beginRecording(page);
  const pad = page.getByRole("button", {name: /^Pad A01\b/});
  await pad.dispatchEvent("pointerdown", {button: 0, isPrimary: true, pointerId: 82});
  await page.waitForTimeout(120);
  await pad.dispatchEvent("pointerup", {button: 0, isPrimary: true, pointerId: 82});
  await stopRecording(page);
  const wav = parsePcm16StereoWav(await exportPerformanceWav(page));

  // pan -100 is gL = sqrt(2), gR = sin(0) = 0: the far channel is exact
  // silence across the whole capture, while the near one carries the hit.
  const start = firstSignalFrame(wav.left);
  const hit = wav.left.slice(start, start + 4_800);
  expect(hit.filter((sample) => Math.abs(sample) > 256).length).toBeGreaterThan(2_400);
  expect(wav.right.filter((sample) => sample !== 0)).toEqual([]);
});

// lmdj.project.v5 5.2.0. Replaces an assigned Pad's sample with the stereo
// 4 800-frame witness sawtooth (a ~495 Hz fundamental with every harmonic),
// exactly as installPerformWitnessSample does for Pad A01.
async function installWitnessOn(page, padName, key) {
  const pad = page.getByRole("button", {name: new RegExp(`^${padName} — assigned — Key ${key}$`)});
  await expect(pad).toBeVisible({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await pad.evaluate((element) => element.click());
  await showSamplePage(page, "Pad");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Replace Sample"}).click();
  await (await chooser).setFiles({
    name: "tone-witness-stereo.wav",
    mimeType: "audio/wav",
    buffer: pcm16Wav({channels: 2}),
  });
  await expect(page.getByRole("dialog", {name: `Replace ${padName}?`})).toBeVisible();
  await page.getByRole("button", {name: "Confirm replace"}).click();
  // A replacement is committed through its selection, as replacePadSample's.
  const longSource = page.getByRole("dialog", {name: `${padName} Long Source`});
  await expect(longSource).toBeVisible({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await longSource.getByRole("button", {name: "Commit selection"}).click();
  await expect(longSource).toBeHidden({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(page.getByRole("button", {name: "Replace Sample"}))
    .toBeEnabled({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

function rms(samples) {
  return Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) /
    Math.max(1, samples.length));
}

test("a tone -100 Pad attenuates a bright source in the recorded master output", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  await importActivateAndPerform(page);
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  await page.getByTestId("physical-controls").getByRole("button", {name: "Bank A", exact: true}).click();
  // The same witness on two Pads: A1 untouched, A2 low-passed at 100 Hz.
  await installWitnessOn(page, "Pad A01", "Q");
  await installWitnessOn(page, "Pad A02", "W");
  await showSamplePage(page, "Tone / EQ");
  const tone = page.getByRole("slider", {name: "Pad A02 Tone"});
  await tone.dispatchEvent("pointerdown", {pointerId: 91, isPrimary: true, button: 0});
  await tone.fill("-100");
  await tone.dispatchEvent("pointerup", {pointerId: 91, isPrimary: true, button: 0});
  await expect.poll(() => page.evaluate(async () => {
    const response = await window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "sample.inspect",
      payload: {slot: {bank: 0, pad: 1}},
    });
    return response.ok ? (response.result.playback.tone ?? 0) : response.error.code;
  }), {timeout: PROJECT_TRANSITION_TIMEOUT_MS}).toBe(-100);
  await expect(tone).toBeEnabled({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await openPerform(page);

  await beginRecording(page);
  for (const [name, pointerId] of [["Pad A01", 92], ["Pad A02", 93]]) {
    const pad = page.getByRole("button", {name: new RegExp(`^${name}\\b`)});
    await pad.dispatchEvent("pointerdown", {button: 0, isPrimary: true, pointerId});
    await page.waitForTimeout(150);
    await pad.dispatchEvent("pointerup", {button: 0, isPrimary: true, pointerId});
    await page.waitForTimeout(400);
  }
  await stopRecording(page);
  const wav = parsePcm16StereoWav(await exportPerformanceWav(page));

  // The untouched hit carries the sawtooth; the low-passed one, ~250 ms
  // later, keeps only a residue of its ~495 Hz fundamental: at least 20 dB
  // below, and still sounding.
  const first = firstSignalFrame(wav.left);
  const open = wav.left.slice(first, first + 4_800);
  const later = wav.left.slice(first + 4_800 + 2_400);
  const second = later.findIndex((sample) => Math.abs(sample) > 8);
  expect(second, "the low-passed hit sounded").toBeGreaterThanOrEqual(0);
  const filtered = later.slice(second, second + 4_800);
  expect(rms(open)).toBeGreaterThan(4_000);
  expect(rms(filtered)).toBeLessThan(rms(open) / 10);
  expect(rms(filtered)).toBeGreaterThan(0);
});
