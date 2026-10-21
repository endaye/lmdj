import {createSequencePattern, selectSequencePattern, sequencePattern,
  showSamplePage, showPerformPage, showPatternLaunchGroup, showSequenceLayer} from "./fixtures/creator_navigation.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {createHash} from "node:crypto";
import {spawn} from "node:child_process";
import {once} from "node:events";
import {mkdtemp, readFile, rm, writeFile} from "node:fs/promises";
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

async function observeReplayTraffic(page) {
  await page.addInitScript(() => {
    let exposed;
    window.__replayWire = [];
    window.__replayCaptureLoss = 0;
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get: () => exposed,
      set(host) {
        const native = host.transport;
        host.transport = Object.freeze({
          async send(...args) {
            const response = await native.send(...args);
            if (args[0]?.operation?.startsWith("performance.replay.") ||
                args[0]?.operation === "performance.inspect") {
              try {
                window.__replayWire.push({request: structuredClone(args[0]), response: structuredClone(response)});
              } catch {window.__replayCaptureLoss += 1;}
            }
            return response;
          },
          subscribe: (...args) => native.subscribe(...args),
          subscribeFailure: (...args) => native.subscribeFailure(...args),
          terminate: (...args) => native.terminate(...args),
          get terminated() {return native.terminated;},
          get terminalOwnerReleased() {return native.terminalOwnerReleased;},
        });
        exposed = host;
      },
    });
  });
}

async function replayEventWitness(page) {
  return page.evaluate(() => {
    const card = document.querySelector('[aria-label="Replay event readout"]');
    const output = card?.querySelector('[aria-label="Replay events"]');
    const ui = card === null || output == null ? null : {
      replayId: card.dataset.replayId, state: card.dataset.replayState,
      revision: Number(card.dataset.resolvedRevision), neutral: card.dataset.neutralConfirmed === "true",
      cursor: Number(output.dataset.eventCursor), count: Number(output.dataset.eventCount), text: output.textContent,
    };
    const wire = structuredClone(window.__replayWire);
    const source = ui === null ? null : wire.findLast(({response}) => response.ok &&
      response.result.replay_id === ui.replayId && response.result.state === ui.state &&
      response.result.resolved_revision === ui.revision && response.result.event_cursor === ui.cursor &&
      response.result.event_count === ui.count) ?? null;
    return {ui, source, wire, captureLoss: window.__replayCaptureLoss};
  });
}

async function expectReplayEvents(page, state, count) {
  await expect.poll(async () => {
    const read = await replayEventWitness(page);
    return {state: read.ui?.state, count: read.ui?.count, matched: read.source !== null,
      neutral: read.ui?.neutral, captureLoss: read.captureLoss};
  }, {timeout: PROJECT_TRANSITION_TIMEOUT_MS}).toEqual({state, count, matched: true,
    neutral: state !== "playing", captureLoss: 0});
  const read = await replayEventWitness(page);
  expect(read.ui.cursor).toBeGreaterThanOrEqual(0);expect(read.ui.cursor).toBeLessThanOrEqual(count);
  expect(read.ui.text).toBe(`${read.ui.cursor} / ${count} events`);
  return read;
}

async function expectLocalAudioFrames(page, frames, sampleRate = 48_000) {
  const output = page.getByRole("status", {name: "Local WAV audio", exact: true});
  await expect(output).toHaveAttribute("data-frames", String(frames));
  await expect(output).toHaveAttribute("data-rate", String(sampleRate));
  await expect(output).toHaveAttribute("data-settled", "true");
  await expect(output).not.toHaveText("Unavailable");
}

async function expectNightSetAudio(page, bytes) {
  await showPerformPage(page, "Takes");
  await page.getByRole("button", {name:/^Select Take \d+: Night Set$/}).click();
  const output=page.getByRole("status", {name:"Take WAV audio",exact:true});
  const frames=(bytes.byteLength-44)/4, rate=bytes.readUInt32LE(24), digest=sha256(bytes);
  await expect(output).toHaveAttribute("data-frames",String(frames),{timeout:AUDIO_TRANSITION_TIMEOUT_MS});
  await expect(output).toHaveAttribute("data-rate",String(rate));
  await expect(output).toHaveAttribute("data-sha256",digest);
  await expect(output).toHaveAttribute("data-byte-length",String(bytes.byteLength));
  // Frames/rate come from the actual exported WAV. Literal component
  // expectations independently cover this shared integer arithmetic assumption.
  const ms=BigInt(frames)*1000n/BigInt(rate);
  const time=`${String(ms/60000n).padStart(2,'0')}:${String(ms/1000n%60n).padStart(2,'0')}.${String(ms%1000n).padStart(3,'0')}`;
  await expect(output).toHaveText(time);
  const truth=await inspectProjectTruth(page);
  const [performanceId,performance]=Object.entries(truth.project.performances).find(([,value])=>value.name==="Night Set");
  expect(performance.recording_artifact).toEqual({sha256:digest,media_type:"audio/wav",byte_length:bytes.byteLength});
  await expect(output).toHaveAttribute("data-performance-id",performanceId);
  await expect(output).toHaveAttribute("data-project-revision",String(truth.project_revision));
  return {frames,rate,sha256:digest,byteLength:bytes.byteLength,time,performanceId,projectRevision:truth.project_revision,
    ui:await output.evaluate(node=>({...node.dataset,text:node.textContent}))};
}

async function inspectProjectTruth(page) {
  return page.evaluate(() =>
    window.lmdjWebRuntimeHost.inspection.inspectProject());
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

// Read the persistent System details projection without leaving a live gesture.
// The hardware journey separately opens the disclosure and verifies visibility.
function projectRevisionLocator(page) {
  return page.locator(".creator-details-facts div").filter({
    has: page.getByText("Rev", {exact: true}),
  }).getByRole("definition", {includeHidden: true});
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

async function savePerformanceWithBusyRetry(page, name, {allowPendingWavBind = false} = {}) {
  await showPerformPage(page, "Takes");
  const nameField = page.getByRole("textbox", {name: "Performance name"});
  const save = page.getByRole("button", {name: "Save Performance"});
  const saved = page.getByText(name, {exact: true});
  const alert = page.getByRole("alert");
  const busy = alert.filter({
    hasText: /Project is busy.*retry Save Performance/i,
  });
  const before = allowPendingWavBind ? await projectRevision(page) : null;
  const pendingRecording = allowPendingWavBind ? await page.evaluate(() =>
    window.lmdjWebRuntimeHost.session.queryPerformanceRecordingStatus()) : null;
  if (pendingRecording !== null) {
    expect(pendingRecording.state).toBe("stopped");expect(pendingRecording.performanceId).not.toBeNull();
  }
  await nameField.fill(name);
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await expect(save).toBeEnabled();
    await save.click();
    await page.evaluate(() => new Promise((resolveFrame) => {
      requestAnimationFrame(() => requestAnimationFrame(resolveFrame));
    }));
    const outcome = async () => {
      if (await saved.isVisible()) return "saved";
      if (allowPendingWavBind) {
        const confirmed = page.getByRole("status", {name: "Performance save confirmation"});
        if (await confirmed.isVisible() && await page.getByRole("button", {name: "Retry WAV bind"}).isVisible() &&
            await page.getByRole("status", {name: "WAV binding status"}).textContent() === "retry") {
          expect(await confirmed.getAttribute("data-performance-id")).toBe(pendingRecording.performanceId);
          expect(await confirmed.getAttribute("data-confirmation-source")).toBe("save");
          expect(Number(await confirmed.getAttribute("data-project-revision"))).toBeGreaterThan(before);
          await expect(confirmed).toHaveText("Performance saved");
          return "saved-pending-bind";
        }
      }
      const stopped = await save.count() > 0 && await save.isEnabled();
      const idle = await page.getByRole("button", {name: "Record Performance", exact: true}).count() === 1;
      if (stopped || idle) {
        // A persisted Performance may still be stopped with Retry WAV bind.
        // Preserve the original saved-row oracle before classifying its alert.
        await showPerformPage(page, "Replay");
        if (await saved.isVisible()) return "saved";
        await showPerformPage(page, "Takes");
      }
      if (await busy.isVisible() && await save.isEnabled()) return "busy";
      if (await alert.isVisible()) return `error:${await alert.textContent()}`;
      return "pending";
    };
    await expect.poll(outcome, {timeout: PROJECT_TRANSITION_TIMEOUT_MS})
      .not.toBe("pending");
    const settled = await outcome();
    if (settled === "saved-pending-bind") return;
    if (settled === "saved") {
      await expect(saved).toBeVisible();
      return;
    }
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
    await showPatternLaunchGroup(page, index + 1);
    await expect(page.getByRole("button", {name: `Launch Pattern ${index + 1}`, exact: true}))
      .not.toHaveAttribute("data-pattern-id", /.+/);
  }

  await showPatternLaunchGroup(page, 1);
  await showPerformPage(page, "Slots");
  await page.getByRole("combobox", {name: "Pattern assignment"})
    .selectOption(PATTERN_ID);
  await page.getByRole("combobox", {name: "Pattern slot", exact: true})
    .selectOption("0");
  await page.getByRole("button", {name: "Assign Pattern"}).click();
  const assignedRevision = await expectRevisionAfter(page, before);
  await showPerformPage(page, "Live");
  await expect(slots.nth(0)).toHaveAttribute("data-pattern-id", PATTERN_ID);

  await showPerformPage(page, "Slots");
  await page.getByRole("combobox", {name: "Move Pattern from"})
    .selectOption({value: "0"});
  const moveTo = page.getByRole("combobox", {name: "Move Pattern to"});
  await moveTo.selectOption({value: "1"});
  await expect(moveTo).toHaveValue("1");
  await page.getByRole("button", {name: "Move Pattern"}).click();
  const movedRevision = await expectRevisionAfter(page, assignedRevision);
  await showPerformPage(page, "Live");
  await expect(slots.nth(0)).not.toHaveAttribute("data-pattern-id", /.+/);
  await expect(slots.nth(1)).toHaveAttribute("data-pattern-id", PATTERN_ID);
  return movedRevision;
}

async function beginFaultingRecording(page) {
  await showPerformPage(page, "Live");
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
  await showPerformPage(page, "Replay");
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
  const pad = page.getByRole("button", {name: /^Pad A01 — assigned — Key Z$/});
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
  {name = "Night Set", withFx = false, tailMs = 0, allowPendingWavBind = false} = {},
) {
  const recordingStatus = await beginRecording(page);
  const pad = page.getByRole("button", {name: /^Pad A01\b/});
  await pad.dispatchEvent("pointerdown", {
    button: 0,
    isPrimary: true,
    pointerId: 71,
  });
  await expect(recordingStatus).toContainText(/open Pads\s*[:·]\s*1/i,
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await page.waitForTimeout(120);
  await pad.dispatchEvent("pointerup", {
    button: 0,
    isPrimary: true,
    pointerId: 71,
  });
  await expect(recordingStatus).toContainText(/open Pads\s*[:·]\s*0/i,
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  if (withFx) {
    await page.getByRole("button", {name: "FILTER", exact: true}).click();
    const filter = page.getByRole("slider", {name: "Cutoff", exact: true});
    const filterStatus = page.getByRole("status", {name: "Filter status"});
    await filter.dispatchEvent("pointerdown", {pointerId: 72});
    await expect(filterStatus).toHaveAttribute("data-provenance", "core");
  await expect(filterStatus).toHaveText("Filter · Engaged",
      {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    await filter.fill("630");
    await expect(filterStatus).toHaveAttribute("data-provenance", "core");
  await expect(filterStatus).toHaveText("Filter · Engaged",
      {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    await expect(filter).toHaveValue("630");
    await filter.dispatchEvent("pointerup", {pointerId: 72});
    await expect(filterStatus).toHaveAttribute("data-provenance", "core");
    await expect(filterStatus).toHaveText("Filter · Off",
      {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    await page.getByRole("button", {name: "FILTER", exact: true}).click();
    await page.getByRole("button", {name: "HOLD"}).click();
    await expect(recordingStatus).toContainText(/hold\s*[:·]\s*on/i,
      {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
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
  await savePerformanceWithBusyRetry(page, name, {allowPendingWavBind});
}

test("Perform Launch selects while stopped and queues, withdraws and applies without Performance recording", async ({page, browserName}, testInfo) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  // Observe the real app traffic without replacing responses or the engine.
  await page.addInitScript(() => {
    let exposed;
    const diagnostics = [];
    const captureLosses = [];
    let captureLossCount = 0;
    window.__readLaunchTransportDiagnostics = () => {
      const events = structuredClone(diagnostics);
      const settled = new Set(events.filter(({phase}) => phase !== "entered")
        .map(({request}) => request.request_id));
      return {
        capture_status: captureLossCount === 0 ? "available" : "incomplete",
        time_origin_ms: performance.timeOrigin,
        events,
        // No recorded outcome is unknown, not proof of a refused request.
        unobserved_outcomes: events.filter(({phase, request}) =>
          phase === "entered" && !settled.has(request.request_id))
          .map(({request}) => ({request_id: request.request_id, status: "unknown"})),
        capture_loss: {count: captureLossCount, details: structuredClone(captureLosses)},
      };
    };
    const recordDiagnostic = (phase, args, value) => {
      try {
        const [request, options] = args;
        if (!["pattern.transport.switch", "pattern.transport.inspect"]
          .includes(request.operation)) return;
        const deadlineMs = options?.deadlineMs;
        const entry = {
          phase, monotonic_ms: performance.now(),
          request: structuredClone(request),
          options: {
            argumentPresent: args.length > 1,
            deadlineMsPresent: options != null && Object.hasOwn(options, "deadlineMs"),
            deadlineMs: typeof deadlineMs === "number" && !Number.isFinite(deadlineMs)
              ? String(deadlineMs) : deadlineMs,
            deadlineMsType: typeof deadlineMs,
          },
        };
        if (phase === "settled") entry.response = structuredClone(value);
        if (phase === "rejected") entry.rejection = {
          type: typeof value, value: structuredClone(value),
          name: value?.name, code: value?.code, message: value?.message,
          details: structuredClone(value?.details),
        };
        diagnostics.push(entry);
      } catch (error) {
        // Evidence capture must not change the real transport's outcome.
        captureLossCount += 1;
        try {
          captureLosses.push({phase, monotonic_ms: performance.now(),
            request_id: args[0]?.request_id, operation: args[0]?.operation,
            reason: String(error), name: error?.name, code: error?.code});
        } catch {
          // The loss count remains even if its detail cannot be recorded.
        }
      }
    };
    window.__launchTransportProof = [];
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get: () => exposed,
      set(host) {
        const native = host.transport;
        host.transport = Object.freeze({
          async send(...args) {
            recordDiagnostic("entered", args);
            let response;
            try {
              response = await native.send(...args);
            } catch (error) {
              recordDiagnostic("rejected", args, error);
              throw error;
            }
            recordDiagnostic("settled", args, response);
            const [request] = args;
            if (["snapshot.reload", "pattern.transport.request", "pattern.transport.switch",
              "performance.record.begin", "performance.record.launch-request"]
              .includes(request.operation)) {
              window.__launchTransportProof.push({
                operation: request.operation, payload: structuredClone(request.payload),
                ok: response.ok,
              });
            }
            return response;
          },
          subscribe: (...args) => native.subscribe(...args),
          subscribeFailure: (...args) => native.subscribeFailure(...args),
          terminate: (...args) => native.terminate(...args),
          get terminated() { return native.terminated; },
          get terminalOwnerReleased() { return native.terminalOwnerReleased; },
        });
        exposed = host;
      },
    });
  });
  try {
    await importActivateAndPerform(page);
    await page.getByRole("button", {name: "Sequence", exact: true}).click();
    await createSequencePattern(page, 2);
    await expect(sequencePattern(page)).toHaveAttribute("data-pattern-count", "2");
    const secondPattern = Object.keys((await inspectProjectTruth(page)).project.patterns)
      .find((id) => id !== PATTERN_ID);
    expect(secondPattern).toBeTruthy();
    await expect(sequencePattern(page)).toHaveAttribute("data-pattern-id", secondPattern);
    await selectSequencePattern(page, PATTERN_ID);
    // The queued and withdrawal legs must act before the next Bar boundary.
    // At the default 120 BPM an early-bar start leaves only 1.6 s, which a
    // loaded CI host spent between the early-bar sample and the queued
    // inspect (run 39061188678). The slowest musical tempo leaves 4.8 s;
    // no deadline or phase window is widened.
    await showSequenceLayer(page, "SETUP");
    await page.getByRole("slider", {name: "BPM", exact: true}).press("Home");
    await expect.poll(async () => (await inspectProjectTruth(page)).project.bpm).toBe(40);
    await showSequenceLayer(page, "EDIT");
    await openPerform(page);
    await showPerformPage(page, "Slots");
    for (const [slot, patternId] of [[0, PATTERN_ID], [1, secondPattern]]) {
      const revision = await projectRevision(page);
      await page.getByRole("combobox", {name: "Pattern assignment"}).selectOption(patternId);
      await page.getByRole("combobox", {name: "Pattern slot", exact: true})
        .selectOption({value: String(slot)});
      await expect(page.getByRole("combobox", {name: "Pattern slot", exact: true}))
        .toHaveValue(String(slot));
      await page.getByRole("button", {name: "Assign Pattern"}).click();
      await expectRevisionAfter(page, revision);
    }
    await showPerformPage(page, "Live");
    const first = page.getByRole("button", {name: "Launch Pattern 1", exact: true});
    const second = page.getByRole("button", {name: "Launch Pattern 2", exact: true});
    const empty = page.getByRole("button", {name: "Launch Pattern 3", exact: true});
    const cue = page.getByRole("status", {name: "Pattern launch cue"});
    const playStop = page.getByTestId("physical-controls")
      .getByRole("button", {name: /^Play\/Stop/});
    const proof = () => page.evaluate(() => window.__launchTransportProof);
    await expect(second).toHaveAttribute("data-pattern-id", secondPattern);
    await expect(second).toBeEnabled();
    const beforeEmpty = await proof();
    await empty.click();
    expect(await proof()).toEqual(beforeEmpty);
    // Stopped slots select through the app's snapshot reload path.
    await second.click();
    await expect.poll(async () => (await proof()).filter(({operation, ok}) =>
      operation === "snapshot.reload" && ok).at(-1)?.payload.pattern_id)
      .toBe(secondPattern);
    await expect(page.getByTestId("perform-counter")).toContainText("/ 02 · BEAT");
    await first.click();
    await expect.poll(async () => (await proof()).filter(({operation, ok}) =>
      operation === "snapshot.reload" && ok).at(-1)?.payload.pattern_id)
      .toBe(PATTERN_ID);
    await expect(page.getByTestId("perform-counter")).toContainText("/ 01 · BEAT");
    const truth = (await inspectProjectTruth(page)).project;
    await page.evaluate(() => { window.__launchTransportProof = []; });
    await playStop.click();
    await expect(first).toHaveAttribute("data-launch", "acknowledged", {
      timeout: LAUNCH_TRANSITION_TIMEOUT_MS,
    });
    const sessionId = (await proof()).find(({operation}) =>
      operation === "pattern.transport.request").payload.session_id;
    const inspect = async () => {
      const response = await page.evaluate((session) =>
        window.lmdjWebRuntimeHost.transport.send({protocol_version: 1,
          request_id: crypto.randomUUID(), operation: "pattern.transport.inspect",
          payload: {session_id: session}}), sessionId);
      expect(response.ok).toBe(true);
      return response.result;
    };
    const earlyBar = async () => {
      const barFrames = 48_000 * 4 * 60 / truth.bpm;
      // Default polling settles at 1 s and can keep missing a 400 ms bar window.
      // Sample more often without widening the phase window or its deadline.
      await expect.poll(async () => {
        const status = await inspect();
        const position = (status.runtime_frame - status.origin_frame) % barFrames;
        return status.playing && !status.publication_pending && status.pending_switch == null &&
          position >= 0 && position < barFrames / 5;
      }, {timeout: LAUNCH_TRANSITION_TIMEOUT_MS, intervals: [50]}).toBe(true);
    };
    await earlyBar();
    await second.click();
    await expect.poll(() => second.evaluateAll((elements) =>
      elements.length === 1 ? elements[0].getAttribute("data-launch") : null),
      {timeout: 5_000, intervals: [50]}).toBe("pending");
    await expect(cue).toHaveText("LAST LAUNCH — → QUEUED SLOT 02");
    const queuedSwitch = await inspect();
    expect(queuedSwitch.current_pattern_id).toBe(PATTERN_ID);
    expect(queuedSwitch.pending_switch.pattern_id).toBe(secondPattern);
    const withdrawnApplyFrame = queuedSwitch.pending_switch.activation_frame;
    await expect(first).toHaveAttribute("data-launch", "acknowledged");
    await expect(page.getByTestId("perform-counter")).toContainText("/ 01 · BEAT");
    // Pressing the currently playing slot withdraws the unclaimed target.
    await first.click();
    await expect.poll(async () => (await inspect()).pending_switch).toBe(null);
    await expect(second).toHaveAttribute("data-launch", "idle");
    expect((await inspect()).current_pattern_id).toBe(PATTERN_ID);
    // An audio-owned withdrawn slot retires at its old apply point. Logical
    // pending=null alone cannot admit another publication before that fence.
    await expect.poll(async () => (await inspect()).runtime_frame,
      {timeout: LAUNCH_TRANSITION_TIMEOUT_MS, intervals: [50]})
      .toBeGreaterThanOrEqual(withdrawnApplyFrame);
    const afterWithdrawal = await inspect();
    expect(afterWithdrawal.pending_switch).toBe(null);
    expect(afterWithdrawal.current_pattern_id).toBe(PATTERN_ID);
    await earlyBar();
    await second.click();
    await expect.poll(() => second.evaluateAll((elements) =>
      elements.length === 1 ? elements[0].getAttribute("data-launch") : null),
      {timeout: 5_000, intervals: [50]}).toBe("pending");
    await expect.poll(async () => {
      const status = await inspect();
      return status.playing && !status.recording && status.pending_switch == null &&
        status.current_pattern_id === secondPattern;
    }, {timeout: LAUNCH_TRANSITION_TIMEOUT_MS}).toBe(true);
    await expect(second).toHaveAttribute("data-launch", "acknowledged");
    await expect(first).toHaveAttribute("data-launch", "idle");
    await expect(cue).toHaveText("LAST LAUNCH — · NOTHING QUEUED");
    await expect(page.getByTestId("perform-counter")).toContainText("/ 02 · BEAT");
    await playStop.click();
    await expect.poll(async () => (await inspect()).playing).toBe(false);
    await expect(second).toHaveAttribute("data-launch", "idle");
    const traffic = await proof();
    expect(traffic.filter(({operation}) => operation === "pattern.transport.switch")
      .map(({payload, ok}) => ({patternId: payload.pattern_id, ok}))).toEqual([
      {patternId: secondPattern, ok: true}, {patternId: PATTERN_ID, ok: true},
      {patternId: secondPattern, ok: true},
    ]);
    expect(traffic.filter(({operation}) => operation === "snapshot.reload" ||
      operation.startsWith("performance.record."))).toEqual([]);
    expect((await inspectProjectTruth(page)).project).toEqual(truth);
    await expect(page.getByRole("status", {name: "Performance recording status"}))
      .toContainText("idle");
  } finally {
    try {
      const diagnostics = JSON.stringify(await page.evaluate(() =>
        window.__readLaunchTransportDiagnostics()), null, 2);
      const diagnosticsPath = testInfo.outputPath("launch-transport-diagnostics.json");
      await writeFile(diagnosticsPath, diagnostics);
      await testInfo.attach("launch-transport-diagnostics.json", {
        path: diagnosticsPath,
        contentType: "application/json",
      });
    } catch (error) {
      // A missing attachment must not mask the original assertion failure.
      try {
        console.warn("launch-transport-diagnostics unavailable", {
          reason: String(error), name: error?.name, code: error?.code,
        });
      } catch {
        // Reporting an unavailable artifact is also best effort.
      }
    }
  }
});

// Records the real transport traffic without replacing responses or the
// engine: the five operations the launch journeys reason about, with full
// payloads (the switch payload carries the device's SEQ SNAP).
async function installLaunchTransportProof(page) {
  await page.addInitScript(() => {
    let exposed;
    window.__launchTransportProof = [];
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get: () => exposed,
      set(host) {
        const native = host.transport;
        host.transport = Object.freeze({
          async send(...args) {
            const response = await native.send(...args);
            const [request] = args;
            if (["snapshot.reload", "pattern.transport.request", "pattern.transport.switch",
              "performance.record.begin", "performance.record.launch-request"]
              .includes(request.operation)) {
              window.__launchTransportProof.push({
                operation: request.operation, payload: structuredClone(request.payload),
                ok: response.ok,
              });
            }
            return response;
          },
          subscribe: (...args) => native.subscribe(...args),
          subscribeFailure: (...args) => native.subscribeFailure(...args),
          terminate: (...args) => native.terminate(...args),
          get terminated() { return native.terminated; },
          get terminalOwnerReleased() { return native.terminalOwnerReleased; },
        });
        exposed = host;
      },
    });
  });
}

// Writes the SEQ SNAP preference into the device's Host settings store the
// way a previous visit's choice would sit there, bypassing this page's UI.
async function seedSeqSnapPreference(page, snap) {
  await page.evaluate(async (value) => {
    const database = await new Promise((resolve, reject) => {
      const request = indexedDB.open("lmdj.creator.host", 1);
      request.onupgradeneeded = () => {
        request.result.createObjectStore("settings");
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    try {
      await new Promise((resolve, reject) => {
        const transaction = database.transaction("settings", "readwrite");
        transaction.objectStore("settings").put(value, "seq-snap.v1");
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error);
      });
    } finally {
      database.close();
    }
  }, snap);
}

// #1958 S4: SEQ SNAP is the device boundary a Perform Launch queues at.
// A stored 1 BEAT choice is restored at boot and carried by the launch's
// transport switch, a SETUP change to SEQ END re-aims the next launch, and
// the choice persists across a reload — without a Performance recording and
// without entering Project Truth. Exact boundary frames stay with the Host
// regression; this journey proves the device wiring, slot feedback and the
// Truth far side.
test("Perform Launch carries the device SEQ SNAP while playing and the choice persists across reload", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  await installLaunchTransportProof(page);
  await openCandidate(page);
  await importProject(page);
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await createSequencePattern(page, 2);
  await expect(sequencePattern(page)).toHaveAttribute("data-pattern-count", "2");
  const secondPattern = Object.keys((await inspectProjectTruth(page)).project.patterns)
    .find((id) => id !== PATTERN_ID);
  expect(secondPattern).toBeTruthy();
  await selectSequencePattern(page, PATTERN_ID);
  await openPerform(page);
  await showPerformPage(page, "Slots");
  for (const [slot, patternId] of [[0, PATTERN_ID], [1, secondPattern]]) {
    const revision = await projectRevision(page);
    await page.getByRole("combobox", {name: "Pattern assignment"}).selectOption(patternId);
    await page.getByRole("combobox", {name: "Pattern slot", exact: true})
      .selectOption({value: String(slot)});
    await page.getByRole("button", {name: "Assign Pattern"}).click();
    await expectRevisionAfter(page, revision);
  }
  const truthAtRest = (await inspectProjectTruth(page)).project;
  const proof = () => page.evaluate(() => window.__launchTransportProof);
  const first = page.getByRole("button", {name: "Launch Pattern 1", exact: true});
  const second = page.getByRole("button", {name: "Launch Pattern 2", exact: true});
  const playStop = page.getByTestId("physical-controls")
    .getByRole("button", {name: /^Play\/Stop/});

  // A stored 1 BEAT choice is seeded the way a previous visit left it; the
  // reload restores it at boot (a launch then carries 1 BEAT, not the 1 BAR
  // default).
  await seedSeqSnapPreference(page, "beat");
  await page.reload();
  await waitForProjectReopen(page, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state"))
    .toHaveText("Audio running", {timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await openPerform(page);
  await playStop.click();
  await expect(first).toHaveAttribute("data-launch", "acknowledged", {
    timeout: LAUNCH_TRANSITION_TIMEOUT_MS,
  });
  const sessionId = (await proof()).find(({operation}) =>
    operation === "pattern.transport.request").payload.session_id;
  const inspect = async () => {
    const response = await page.evaluate((session) =>
      window.lmdjWebRuntimeHost.transport.send({protocol_version: 1,
        request_id: crypto.randomUUID(), operation: "pattern.transport.inspect",
        payload: {session_id: session}}), sessionId);
    expect(response.ok).toBe(true);
    return response.result;
  };
  await expect.poll(async () => (await inspect()).playing,
    {timeout: LAUNCH_TRANSITION_TIMEOUT_MS}).toBe(true);

  // Leg 1 — Launch slot 2 queues the transport switch with the boot-restored
  // 1 BEAT choice; the slot acknowledges once the switch applies.
  await second.click();
  await expect.poll(async () => (await proof()).filter(({operation}) =>
    operation === "pattern.transport.switch").at(-1)?.payload,
  {timeout: LAUNCH_TRANSITION_TIMEOUT_MS})
    .toMatchObject({pattern_id: secondPattern, snap: "beat"});
  await expect.poll(async () => {
    const status = await inspect();
    return status.playing && !status.recording && status.pending_switch == null &&
      status.current_pattern_id === secondPattern;
  }, {timeout: LAUNCH_TRANSITION_TIMEOUT_MS}).toBe(true);
  await expect(second).toHaveAttribute("data-launch", "acknowledged", {
    timeout: LAUNCH_TRANSITION_TIMEOUT_MS,
  });
  await expect(page.getByTestId("perform-counter")).toContainText("/ 02 · BEAT");

  // Leg 2 — SEQ END chosen on Sequence's SETUP re-aims the next launch; slot
  // 1 acknowledges once the switch applies at the end of the playing 2-bar
  // Pattern.
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await showSequenceLayer(page, "SETUP");
  await page.getByRole("group", {name: "Sequence snap"})
    .getByRole("button", {name: "SEQ END", exact: true}).click();
  await expect(page.getByRole("group", {name: "Sequence snap"})
    .getByRole("button", {name: "SEQ END", exact: true}))
    .toHaveAttribute("aria-pressed", "true");
  await openPerform(page);
  await first.click();
  await expect.poll(async () => (await proof()).filter(({operation}) =>
    operation === "pattern.transport.switch").at(-1)?.payload,
  {timeout: LAUNCH_TRANSITION_TIMEOUT_MS})
    .toMatchObject({pattern_id: PATTERN_ID, snap: "pattern_end"});
  await expect.poll(async () => {
    const status = await inspect();
    return status.playing && !status.recording && status.pending_switch == null &&
      status.current_pattern_id === PATTERN_ID;
  }, {timeout: LAUNCH_TRANSITION_TIMEOUT_MS}).toBe(true);
  await expect(first).toHaveAttribute("data-launch", "acknowledged", {
    timeout: LAUNCH_TRANSITION_TIMEOUT_MS,
  });
  await expect(page.getByTestId("perform-counter")).toContainText("/ 01 · BEAT");

  // Leg 3 — Stop; the launches and the preference never entered Project
  // Truth, and no Performance recording was ever opened.
  await playStop.click();
  await expect.poll(async () => (await inspect()).playing,
    {timeout: LAUNCH_TRANSITION_TIMEOUT_MS}).toBe(false);
  expect((await inspectProjectTruth(page)).project).toEqual(truthAtRest);
  expect((await proof()).filter(({operation}) =>
    operation.startsWith("performance.record."))).toEqual([]);

  // Leg 4 — the explicit choice persists across a reload; Truth still equal.
  await page.reload();
  await waitForProjectReopen(page, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await showSequenceLayer(page, "SETUP");
  await expect(page.getByRole("group", {name: "Sequence snap"})
    .getByRole("button", {name: "SEQ END", exact: true}))
    .toHaveAttribute("aria-pressed", "true", {timeout: 30_000});
  expect((await inspectProjectTruth(page)).project).toEqual(truthAtRest);
});


test("complete Perform journey persists projection, gestures, WAV, save, replay and empty Pad master capture", async ({page, browserName}, info) => {
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
  // The actual Creator Press reaches Pattern and the Performance journal with
  // one opaque identity. Probe only local preparation via the same packaged
  // Session: exactly 63 places remain, not 62 or 64. No wire/Truth injection.
  const remainingWhileHeld = await page.evaluate(() => {
    const session = window.lmdjWebRuntimeHost.session;
    const leases = Array.from({length: 64}, () =>
      session.reserveInputGesture({}, 0, "pointer"));
    const count = leases.filter(lease => lease !== null).length;
    for (const lease of leases) lease?.cancelUnsubmittedPattern();
    return count;
  });
  expect(remainingWhileHeld).toBe(63);
  await page.waitForTimeout(120);
  await pad.dispatchEvent("pointerup", {
    button: 0,
    isPrimary: true,
    pointerId: 21,
  });
  await expect(recordingStatus).toContainText(/open pads?\s*[:·]\s*0/i);
  await expect.poll(() => page.evaluate(() => {
    const session = window.lmdjWebRuntimeHost.session;
    const leases = Array.from({length: 64}, () =>
      session.reserveInputGesture({}, 0, "pointer"));
    const count = leases.filter(lease => lease !== null).length;
    for (const lease of leases) lease?.cancelUnsubmittedPattern();
    return count;
  }), {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBe(64);

  const launch = page.getByRole("button", {name: "Launch Pattern 2"});
  await armAttributeObservation(launch, "data-launch", "pending");
  const launchCue = page.getByRole("status", {name: "Pattern launch cue"});
  await launchCue.evaluate(element => {
    const observer = new MutationObserver(() => {
      if (element.textContent.includes("QUEUED SLOT 02")) {
        element.setAttribute("data-proof-saw-queued", "02");
        observer.disconnect();
      }
    });
    observer.observe(element, {childList: true, subtree: true, characterData: true});
  });
  await launch.click();
  await expect(launch).toHaveAttribute("data-proof-saw-launch", "pending",
    {timeout: LAUNCH_TRANSITION_TIMEOUT_MS});
  await expect(launch).toHaveAttribute("data-launch", "acknowledged", {
    timeout: LAUNCH_TRANSITION_TIMEOUT_MS,
  });
  await expect(launchCue).toHaveAttribute("data-proof-saw-queued", "02");
  await expect(launchCue).toHaveText("ACKNOWLEDGED SLOT 02 · NOTHING QUEUED");

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

  const filter = page.getByRole("slider", {name: "Filter", exact: true});
  await filter.dispatchEvent("pointerdown", {pointerId: 22});
  // Core status counts the independent Filter alongside ordinary FX (#2124).
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
  // The rail is now the sole Bank owner; changing it must keep the same
  // recorded Project revision and update the actual playable Pad bank.
  await expect(page.getByRole("group", {name: "Perform Bank"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Bank B", exact: true})).toHaveCount(1);
  const performBanks = page.getByTestId("physical-controls");
  await performBanks.getByRole("button", {name: "Bank B", exact: true}).click();
  await expect(performBanks.getByRole("button", {name: "Bank B", exact: true}))
    .toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("button", {name: /^Pad B/})).toHaveCount(16);
  expect(await projectRevision(page)).toBe(bankRevision);

  await showPerformPage(page, "Takes");
  const pendingTake = await page.evaluate(async () => {
    const session = window.lmdjWebRuntimeHost.session;
    return {status: await session.queryPerformanceRecordingStatus(),
      performances: await session.listPerformances(), recovery: await session.listPerformanceRecovery()};
  });
  expect(pendingTake.status.state).toBe("active");
  expect(pendingTake.performances.some(value => value.performanceId === pendingTake.status.performanceId)).toBe(true);
  expect(pendingTake.recovery.some(value => value.performanceId === pendingTake.status.performanceId)).toBe(true);
  // The authoritative list really contains begin's unsaved draft. Saved Takes
  // must exclude it while the original recording remains active.
  await expect(page.getByRole("region", {name:"Saved Takes", exact:true})
    .getByText("No saved Takes", {exact:true})).toBeVisible();
  await page.getByRole("button", {name: "Flush Performance"}).click();
  revision = await expectRevisionAfter(page, revision);
  await expect(recordingStatus).toContainText(/flushed/i);
  await page.getByRole("button", {name: "System", exact: true}).click();
  const notice = page.getByRole("region", {name: "Performance recording notice"});
  await expect(notice.getByRole("status")).toContainText("recording");
  await expect(page.getByRole("main", {name: "Perform", exact: true})).toHaveCount(0);
  await notice.getByRole("button", {name: "Stop Performance", exact: true}).click();
  await expect(notice.getByRole("status")).toContainText("Ready to save or discard",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await notice.getByRole("button", {name: "Review Performance recording", exact: true}).click();
  await expect(page.getByRole("button", {name: "Save Performance", exact: true})).toBeVisible();
  await expect(page.getByRole("button", {name: "Discard Performance", exact: true})).toBeVisible();
  await expect(page.getByRole("status", {name: "WAV recording status"}))
    .toContainText("sealed", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  const encodedWav = await exportPerformanceWav(page);
  const wav = parsePcm16StereoWav(encodedWav);
  expect(wav.frames).toBeGreaterThan(0);
  verifyDeterministicMasterOutput(wav);

  await savePerformanceWithBusyRetry(page, "Night Set");
  revision = await expectRevisionAfter(page, revision);
  await expect(page.getByRole("status", {name: "WAV binding status"}))
    .toContainText("bound");
  const savedAudio=await expectNightSetAudio(page,encodedWav);

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
  const reopenedAudio=await expectNightSetAudio(page,encodedWav);
  expect(reopenedAudio.frames).toBe(savedAudio.frames);
  expect(reopenedAudio.sha256).toBe(savedAudio.sha256);
  await showPerformPage(page, "Replay");
  await expect(page.getByText("Night Set", {exact: true})).toBeVisible();

  await page.getByRole("button", {name: "Replay Night Set"}).click();
  const replayStatus = page.getByRole("status", {name: "Replay status"});
  await expect(replayStatus).toContainText("playing", {timeout: 30_000});
  await expect(replayStatus).toContainText(
    new RegExp(`resolved revision\\s*[:·]\\s*${revision}`, "i"),
  );
  // The Pad recording source is a System setting (brand mark entry).
  await page.getByRole("button", {name: "System", exact: true}).click();
  await page.getByRole("group", {name: "Pad recording source"}).getByRole("button", {name: "Internal playback", exact: true}).click();
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
  // A Bank key no longer retargets the Sample edit object (#1961): striking
  // the Pad itself makes B01 the one current Pad.
  await page.getByRole("button", {name: /^Pad B01 — assigned/}).click();
  await showSamplePage(page, "Pad");
  await page.getByRole("button", {name: "Delete Pad B01", exact: true}).click();
  revision = await expectRevisionAfter(page, revision);
  const afterDelete = await inspectProjectTruth(page);
  expect(afterDelete.project.banks[1].pads[0].asset_id).toBeNull();
  expect(afterDelete.project.assets).toEqual(beforeDelete.project.assets);
  expect(afterDelete.project.patterns).toEqual(beforeDelete.project.patterns);
  await openPerform(page);
  await page.getByRole("button", {name: "Bank B", exact: true}).first().click();
  await showPerformPage(page, "Replay");
  const empty = page.getByRole("button", {name: /^Pad B01 — empty/});
  await empty.focus();
  const beforeCaptureBatches = await page.evaluate(() =>
    window.__performMasterBatchProof.length);
  await page.keyboard.down("KeyZ");
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
  await page.keyboard.up("KeyZ");
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
  const audioPath=info.outputPath("recorded-take-saved-reopened-audio.json");
  await writeFile(audioPath,JSON.stringify({savedAudio,reopenedAudio},null,2));
  await info.attach("recorded Take audio before and after reopen",{path:audioPath,contentType:"application/json"});
});

test("a recorded rotary FX survives touch takeover and closes the same Core gesture on leaving Perform", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(420_000);
  await importActivateAndPerform(page);
  await beginRecording(page);
  const authority = async () => {
    const response = await page.evaluate(() => window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1, request_id: crypto.randomUUID(),
      operation: "performance.record.status", payload: {},
    }));
    expect(response.ok).toBe(true);
    return response.result;
  };
  await expect(page.getByRole("slider", {name: "Reverb", exact: true})).toHaveValue("0");
  const knob = page.getByRole("button", {name: "Encoder 3 — Reverb", exact: true});
  await knob.focus();
  await page.keyboard.press("ArrowUp");
  await expect.poll(async () => (await authority()).open_fx_gestures).toBe(1);
  await page.getByRole("button", {name: "MORE"}).click();
  await expect(page.getByRole("button", {name: "Encoder 3 — Gate", exact: true})).toBeEnabled();
  expect((await authority()).open_fx_gestures).toBe(1);
  await page.getByRole("button", {name: "MORE"}).click();
  const reverb = page.getByRole("slider", {name: "Reverb", exact: true});
  await expect(reverb).toHaveValue("10");
  await reverb.dispatchEvent("pointerdown", {pointerId: 91});
  await reverb.fill("651");
  await reverb.dispatchEvent("pointerup", {pointerId: 91});
  await expect(reverb).toHaveValue("651");
  expect((await authority()).open_fx_gestures).toBe(1);
  // System leaves the music surface while retaining the recording. Its
  // release therefore has a far-side Core count before stop can close it.
  await page.getByRole("button", {name: "System", exact: true}).click();
  await expect.poll(async () => (await authority()).open_fx_gestures).toBe(0);
  const stoppedFx = await authority();
  expect(stoppedFx.state).toBe("active");
  expect(stoppedFx.hold).toBe(false);
  await page.getByRole("button", {name: "Back to music", exact: true}).click();
  await expect(reverb).toHaveValue("0");
  await stopRecording(page);
  await savePerformanceWithBusyRetry(page, "Rotary touch");
  await expect(page.getByRole("status", {name: "WAV binding status"})).toContainText("bound");
  const inspect = async () => {
    const response = await page.evaluate((id) => window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1, request_id: crypto.randomUUID(),
      operation: "performance.inspect", payload: {performance_id: id},
    }), stoppedFx.performance_id);
    expect(response.ok).toBe(true);
    return response.result.performance;
  };
  const saved = await inspect();
  expect(saved.name).toBe("Rotary touch");
  expect(saved.recording_artifact).toMatchObject({
    byte_length: expect.any(Number), sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
    media_type: "audio/wav",
  });
  expect(saved.recording_artifact.byte_length).toBeGreaterThan(44);
  await page.reload();
  await openLocalProject(page);
  expect(await inspect()).toEqual(saved);
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
    await showPerformPage(ownerPage, "Takes");
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
    await showPerformPage(applyingPage, "Replay");
    await expect(applyingPage.getByRole("button", {name: "Apply recovery"})).toBeVisible();
    const beforeApply = await projectRevision(applyingPage);
    await applyRecoveryAfterOwnerRelease(applyingPage);
    await expectRevisionAfter(applyingPage, beforeApply);
    await expect(applyingPage.getByRole("status", {name: "Performance recovery status"}))
      .toContainText(/applied.*closed.*Pad/i);
    await expect(applyingPage.getByRole("button", {name: "Replay Untitled Performance"}))
      .toBeVisible();
    const stoppedDraft = applyingPage.getByRole("region", {name: "Stopped Performance draft"});
    await expect(stoppedDraft).toContainText("Not saved yet");
    const recoveredId = await stoppedDraft.getAttribute("data-performance-id");
    const recovered = await applyingPage.evaluate(id =>
      window.lmdjWebRuntimeHost.session.inspectPerformance(id), recoveredId);
    expect(recovered.events.length).toBeGreaterThan(0);expect(recovered.recordingArtifact).toBeNull();
    // A fresh Session reconstructs readiness from Core's stopped Journal,
    // rather than remembering that this Host previously clicked Apply.
    await applyingPage.reload();await openLocalProject(applyingPage);await activateAudio(applyingPage);
    await openPerform(applyingPage);await showPerformPage(applyingPage, "Replay");
    await expect(stoppedDraft).toBeVisible();
    const reopenedDraft = await applyingPage.evaluate(id =>
      window.lmdjWebRuntimeHost.session.inspectPerformance(id), recoveredId);
    expect(reopenedDraft.events).toEqual(recovered.events);
    expect(reopenedDraft.recordingArtifact).toEqual(recovered.recordingArtifact);
    await stoppedDraft.getByRole("button", {name: "Replay Untitled Performance"}).click();
    await expect(applyingPage.getByRole("status", {name: "Replay status"}))
      .toContainText(/complete.*neutral/, {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    await stoppedDraft.getByRole("button", {name: "Save stopped recording"}).click();
    await expect(stoppedDraft).toHaveCount(0);
    await expect(applyingPage.getByRole("button", {name: "Replay Untitled Performance"})).toBeVisible();
    const savedRecovered = await applyingPage.evaluate(async id => {
      const session = window.lmdjWebRuntimeHost.session;
      return {inspected: await session.inspectPerformance(id), recovery: await session.listPerformanceRecovery(),
        status: await session.queryPerformanceRecordingStatus()};
    }, recoveredId);
    expect(savedRecovered.inspected.events).toEqual(recovered.events);
    expect(savedRecovered.inspected.recordingArtifact).toBeNull();
    expect(savedRecovered.recovery).toEqual([]);expect(savedRecovered.status.state).toBe("idle");
    await applyingPage.reload();await openLocalProject(applyingPage);await activateAudio(applyingPage);
    await openPerform(applyingPage);await showPerformPage(applyingPage, "Replay");
    await expect(stoppedDraft).toHaveCount(0);
    await expect(applyingPage.getByRole("button", {name: "Replay Untitled Performance"})).toBeVisible();
    expect((await applyingPage.evaluate(id => window.lmdjWebRuntimeHost.session.inspectPerformance(id), recoveredId)).events)
      .toEqual(recovered.events);
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
    await showPerformPage(discardingPage, "Replay");
    await discardingPage.getByRole("button", {name: "Discard recovery"}).click();
    await expect(discardingPage.getByRole("status", {name: "Performance recovery status"}))
      .toContainText("discarded");
    expect(await projectRevision(discardingPage)).toBe(beforeDiscard);
    const draft = discardingPage.getByRole("region", {name: "Stopped Performance draft"});
    await expect(draft).toBeVisible();
    const draftId = await draft.getAttribute("data-performance-id");
    await draft.getByRole("button", {name: "Discard stopped recording"}).click();
    await expect(draft).toHaveCount(0);
    const discarded = await discardingPage.evaluate(async () => {
      const session = window.lmdjWebRuntimeHost.session;
      return {performances: await session.listPerformances(), recovery: await session.listPerformanceRecovery(),
        status: await session.queryPerformanceRecordingStatus()};
    });
    expect(discarded.performances.some(value => value.performanceId === draftId)).toBe(false);
    expect(discarded.recovery).toEqual([]);expect(discarded.status.state).toBe("idle");
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
    const prefix = parsePcm16StereoWav(await exportPerformanceWav(page));
    await expectLocalAudioFrames(page, prefix.frames);
    await expect(page.getByRole("status", {name: "Local WAV audio", exact: true}))
      .toHaveAttribute("data-reason", failure.reason);
  });
}

test("a retryable WAV bind keeps the real Store receipt path and removes the temporary file after retry", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await importActivateAndPerform(page, "bind-retry");
  const baselineWavs = await opfsWavFiles(page);
  await recordShortPerformance(page, {name: "Retry Set", allowPendingWavBind: true});

  await expect(page.getByRole("alert")).toContainText("The recording could not be saved into the Project. Choose Retry WAV bind.");
  expect((await opfsWavFiles(page)).length).toBeGreaterThan(baselineWavs.length);
  const revision = await projectRevision(page);
  await showPerformPage(page, "Takes");
  const confirmedId = await page.getByRole("status", {name: "Performance save confirmation"})
    .getAttribute("data-performance-id");
  const retainedBytes = await exportPerformanceWav(page);
  const retainedWav = parsePcm16StereoWav(retainedBytes);
  await expectLocalAudioFrames(page, retainedWav.frames);
  await page.getByRole("button", {name: "Retry WAV bind"}).click();
  await expect(page.getByRole("status", {name: "WAV binding status"}))
    .toContainText("bound", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(page.getByRole("status", {name: "Local WAV audio", exact: true})).toHaveCount(0);
  await expectRevisionAfter(page, revision);
  await expect.poll(async () => (await opfsWavFiles(page)).filter(
    ({path}) => !/[0-9a-f]{64}\.wav$/.test(path),
  )).toEqual([]);
  await showPerformPage(page, "Replay");
  await expect(page.getByRole("button", {name: "Replay Retry Set", exact: true})).toBeVisible();
  const bound = await page.evaluate(id => window.lmdjWebRuntimeHost.session.inspectPerformance(id), confirmedId);
  expect(bound.recordingArtifact).toEqual({sha256: sha256(retainedBytes), mediaType: "audio/wav",
    byteLength: retainedBytes.byteLength});
  await page.reload();await openLocalProject(page);await activateAudio(page);await openPerform(page);
  await showPerformPage(page, "Replay");
  await expect(page.getByRole("button", {name: "Replay Retry Set", exact: true})).toBeVisible();
  const reopened = await page.evaluate(id => window.lmdjWebRuntimeHost.session.inspectPerformance(id), confirmedId);
  expect(reopened.events).toEqual(bound.events);
  expect(reopened.recordingArtifact).toEqual(bound.recordingArtifact);
});

test("an active recording receives an empty-slot acknowledgement and interruption closes the same capture", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await importActivateAndPerform(page);
  const status = await beginRecording(page);
  await showPatternLaunchGroup(page, 16);
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
  await expect(status).toContainText(/open Pads?\s*[:·]\s*0/i);
  await expect(page.getByRole("status", {name: "Pattern launch cue"}))
    .toHaveText("ACKNOWLEDGED SLOT 16 · NOTHING QUEUED");

  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.getByRole("status", {name: "WAV recording status"}))
    .toContainText("sealed", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(status).toContainText("stopped");
  await expect(page.getByRole("button", {name: "Stop Performance"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Review recording"})).toBeEnabled();
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
    await showPerformPage(successor, "Replay");
    await expect(successor.getByRole("button", {name: "Apply recovery"}))
      .toHaveCount(1);
    await expect(successor.getByRole("status", {name: "Performance recovery status"}))
      .toContainText("active");
    await showPerformPage(successor, "Live");
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
  const master = page.getByRole("slider", {name: "MASTER", exact: true});
  await expect(master).toBeEnabled({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await master.fill("37");
  await expect(master).toHaveValue("37");
  await assignThenMovePattern(page);
  // The replay must still be playing when Stop Replay is clicked, otherwise
  // the run races natural completion and observes "complete · neutral"
  // instead of the abort path this test owns.
  await recordShortPerformance(page, {
    name: "Neutral Reset",
    withFx: true,
    tailMs: 6_000,
  });

  await showPerformPage(page, "Replay");
  await page.getByRole("button", {name: "Replay Neutral Reset"}).click();
  const replayStatus = page.getByRole("status", {name: "Replay status"});
  await expect(replayStatus).toContainText("playing", {timeout: 30_000});
  await page.getByRole("button", {name: "Stop Replay"}).click();
  await expect(replayStatus).toContainText("stopped · neutral", {
    timeout: 30_000,
  });
  await showPerformPage(page, "Live");
  // Replay releases the independent Filter while retaining its last tuple;
  // OFF is a Core readback, and device monitoring keeps its own
  // 0–100 range rather than resetting with FX.
  await expect(page.getByRole("slider", {name: "Filter", exact: true}))
    .toHaveValue("630");
  await page.getByRole("button", {name: "FILTER", exact: true}).click();
  await expect(page.getByRole("status", {name: "Filter status"}))
    .toHaveText("Filter · Off");
  await expect(page.getByRole("status", {name: "Filter status"})).toHaveAttribute("data-provenance", "core");
  await page.getByRole("button", {name: "FILTER", exact: true}).click();
  for (const name of ["Delay", "Reverb"]) {
    await expect(page.getByRole("slider", {name, exact: true})).toHaveValue("0");
  }
  await expect(master).toHaveValue("37");
  await expect(page.getByRole("button", {name: "HOLD"}))
    .toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", {name: "Launch Pattern 2"}))
    .toHaveAttribute("data-launch", "idle");
});

async function inspectedPadA1Pan(page) {
  return page.evaluate(async () => {
    const inspected = await window.lmdjWebRuntimeHost.inspection.inspectSample(0);
    return inspected.playback.pan;
  });
}

test("a hard-left Pad pan silences the right channel of the recorded master output", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  await importActivateAndPerform(page);
  await installPerformWitnessSample(page);
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  await page.getByRole("button", {name: /^Pad A01 — assigned — Key Z$/})
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
async function installWitnessOn(page, padName, key, buffer = pcm16Wav({channels: 2})) {
  const pad = page.getByRole("button", {name: new RegExp(`^${padName} — assigned — Key ${key}$`)});
  await expect(pad).toBeVisible({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await pad.evaluate((element) => element.click());
  await showSamplePage(page, "Pad");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Replace Sample"}).click();
  await (await chooser).setFiles({
    name: "tone-witness-stereo.wav",
    mimeType: "audio/wav",
    buffer,
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
  await installWitnessOn(page, "Pad A01", "Z");
  await installWitnessOn(page, "Pad A02", "X");
  await showSamplePage(page, "Tone / EQ");
  const tone = page.getByRole("slider", {name: "Pad A02 Tone"});
  await tone.dispatchEvent("pointerdown", {pointerId: 91, isPrimary: true, button: 0});
  await tone.fill("-100");
  await tone.dispatchEvent("pointerup", {pointerId: 91, isPrimary: true, button: 0});
  await expect.poll(() => page.evaluate(async () => {
    const inspected = await window.lmdjWebRuntimeHost.inspection.inspectSample(1);
    return inspected.playback.tone;
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


test("native FX drag-off releases before paging without stopping the recording", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  await importActivateAndPerform(page);
  const status = await beginRecording(page);
  // A typed seven-FX fader: its engage counts as an open_fx gesture far-side
  // (an engaged independent Filter would be the separate open_filter).
  const fader = page.getByRole("slider", {name: "Delay", exact: true});
  // Record lives below the live panel. Scroll back with native input before
  // aiming the pointer, including the sticky page bar's occlusion.
  const touch = page.getByTestId("touch-workspace");
  await touch.hover();
  await page.mouse.wheel(0, -1200);
  await expect.poll(() => touch.evaluate(element => element.scrollTop)).toBe(0);
  await fader.evaluate(element => {
    // Chromium's native range thumb owns capture in its UA shadow tree.
    // The public input receives retargeted events, but hasPointerCapture on
    // that outer element is false. Observe the native capture-phase events
    // and the authoritative gesture lifecycle, not outer-element ownership.
    for (const [type, attribute] of [["gotpointercapture", "data-proof-captured"],
      ["lostpointercapture", "data-proof-released"]]) {
      window.addEventListener(type, event => {
        if (event.target === element) element.setAttribute(attribute, "true");
      }, {capture: true, once: true});
    }
  });
  const box = await fader.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 2 / 3, box.y + box.height / 2);
  await expect(fader).toHaveAttribute("data-proof-captured", "true");
  const pages = page.getByRole("navigation", {name: "Perform pages"});
  for (const button of await pages.getByRole("button").all()) await expect(button).toBeDisabled();
  await expect(status).toContainText("open FX: 1", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await page.mouse.move(box.x - 40, box.y - 10);
  await page.mouse.up();
  await expect(status).toContainText("open FX: 0", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(fader).toHaveAttribute("data-proof-released", "true");
  for (const button of await pages.getByRole("button").all()) await expect(button).toBeEnabled();
  for (const name of ["Slots", "Takes", "Replay", "Live"]) {
    await showPerformPage(page, name);
    await expect(status).toContainText("recording");
    await expect(status).not.toContainText("stopped");
  }
  await stopRecording(page);
  await page.getByRole("button", {name: "Review recording", exact: true}).click();
  await expect(page.getByRole("textbox", {name: "Performance name"})).toBeVisible();
  await expect(page.getByRole("button", {name: "Save Performance"})).toBeEnabled();
});

// C1 typed independent Filter journey (D04/D0/W1 consumer). Every leg keeps a
// far-side assertion: Control→PCM against the exported master capture, HOLD
// freeze and page exit inside one recording, then Stop/Save/reopen/Replay.
// Read both the gesture count and the independent Filter's applied state.
test("typed Filter journey proves Control→PCM, HOLD freeze, page exit, save and replay", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(420_000);
  await observeMasterCaptureBatches(page);
  await importActivateAndPerform(page);
  await installPerformWitnessSample(page);
  await assignThenMovePattern(page);

  // The main group's first fader is the typed Filter with a Core Hz readback.
  const primaryCutoff = page.getByRole("slider", {name: "Filter", exact: true});
  await expect(primaryCutoff).toBeVisible();
  await expect(primaryCutoff).toHaveValue("1000");
  const cutoff = page.getByRole("slider", {name: "Cutoff", exact: true});
  await expect(page.getByTestId("touch-workspace")
    .getByText("20.0 kHz", {exact: true})).toBeVisible();
  await expect(page.getByRole("button",
    {name: "Encoder 1 — Cutoff", exact: true})).toBeEnabled();

  // Entering the FILTER group is pure UI: still OFF, no enable.
  await page.getByRole("button", {name: "FILTER", exact: true}).click();
  const filterStatus = page.getByRole("status", {name: "Filter status"});
  await expect(filterStatus).toContainText("Off");
  await expect(filterStatus).toHaveAttribute("data-provenance", "core");
  await expect(page.getByRole("button", {name: "LP", exact: true}))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("slider", {name: "Resonance", exact: true}))
    .toHaveValue("0");
  // FILTER-group encoders remap while the open Filter gesture stays untouched.
  await expect(page.getByRole("button",
    {name: "Encoder 1 — Type", exact: true})).toBeEnabled();
  await expect(page.getByRole("button",
    {name: "Encoder 3 — Resonance", exact: true})).toBeEnabled();
  // A type segment change is an actual control: engage + readback.
  await page.getByRole("button", {name: "HP", exact: true}).click();
  await expect(filterStatus).toContainText("Engaged");
  await expect(filterStatus).toHaveAttribute("data-provenance", "core");
  await page.getByRole("button", {name: "LP", exact: true}).click();
  await expect(filterStatus).toHaveAttribute("data-provenance", "core");
  await expect(filterStatus).toHaveText("Filter · Engaged",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  // Leaving the group must not release the gesture (D04 rest semantics).
  await page.getByRole("button", {name: "FILTER", exact: true}).click();
  await expect(page.getByRole("group", {name: "Filter", exact: true})).toHaveCount(0);
  await expect(filterStatus).toHaveText("Filter · Engaged");
  await expect(filterStatus).toHaveAttribute("data-provenance", "core");

  const recordingStatus = await beginRecording(page);
  const pad = page.getByRole("button", {name: /^Pad A01\b/});
  const strike = async (pointerId) => {
    await pad.dispatchEvent("pointerdown", {
      button: 0, isPrimary: true, pointerId,
    });
    await expect(recordingStatus).toContainText(/open Pads\s*[:·]\s*1/i,
      {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    await page.waitForTimeout(120);
    await pad.dispatchEvent("pointerup", {
      button: 0, isPrimary: true, pointerId,
    });
    await expect(recordingStatus).toContainText(/open Pads\s*[:·]\s*0/i,
      {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  };
  // Hit 1 dry: the segment leg left the Filter engaged at LP with a fully
  // open 20 kHz cutoff, so the sawtooth passes untouched.
  await strike(31);

  // Engage the cutoff touch at the current value (no audible change), sweep
  // low, and hold it over hit 2.
  await page.getByRole("button", {name: "FILTER", exact: true}).click();
  await cutoff.dispatchEvent("pointerdown", {pointerId: 32});
  await expect(filterStatus).toHaveAttribute("data-provenance", "core");
  await expect(filterStatus).toHaveText("Filter · Engaged",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await cutoff.fill("100");
  // The next audible Pad witnesses the applied tuple. Core readback also
  // keeps this journey within the bounded ordinary-input admission window.
  await expect(filterStatus).toHaveAttribute("data-provenance", "core");
  await expect(filterStatus).toHaveText("Filter · Engaged",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(cutoff).toHaveValue("100");
  await strike(33);
  await cutoff.dispatchEvent("pointerup", {pointerId: 32});
  // Complete the first gesture far-side before a new ordinary input uses the
  // bounded 1+1 admission window. UI pointer-up alone is not an ACK.
  await expect(recordingStatus).toContainText(/open FX\s*[:·]\s*0/i,
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});

  // HOLD leg: an engaged-then-released Filter freezes far-side under HOLD.
  await page.getByRole("button", {name: "HOLD"}).click();
  await expect(page.getByRole("button", {name: "HOLD"}))
    .toHaveAttribute("aria-pressed", "true");
  await expect(recordingStatus).toContainText(/hold\s*[:·]\s*on/i,
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await cutoff.dispatchEvent("pointerdown", {pointerId: 34});
  await expect(filterStatus).toHaveAttribute("data-provenance", "core");
  await expect(filterStatus).toHaveText("Filter · Engaged",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await cutoff.fill("300");
  await expect(filterStatus).toHaveAttribute("data-provenance", "core");
  await expect(filterStatus).toHaveText("Filter · Engaged",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(cutoff).toHaveValue("300");
  await cutoff.dispatchEvent("pointerup", {pointerId: 34});
  // HOLD is a journaled far-side fact while the recording runs.
  await expect(recordingStatus).toContainText(/hold\s*[:·]\s*on/i,
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(filterStatus).toContainText("Frozen",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await page.getByRole("button", {name: "FILTER", exact: true}).click();
  // A last hit while frozen keeps the recording span long enough for the
  // replay leg to still be playing after save and reopen.
  await page.waitForTimeout(1_500);
  await strike(35);

  // Page-exit leg: System retains the recording; the notice owns Stop.
  await page.getByRole("button", {name: "System", exact: true}).click();
  const notice = page.getByRole("region", {name: "Performance recording notice"});
  await expect(notice.getByRole("status")).toContainText("recording");
  await expect(page.getByRole("main", {name: "Perform", exact: true})).toHaveCount(0);
  await notice.getByRole("button", {name: "Stop Performance", exact: true}).click();
  await expect(notice.getByRole("status")).toContainText("Ready to save or discard",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await notice.getByRole("button", {name: "Review Performance recording", exact: true}).click();
  await expect(page.getByRole("status", {name: "WAV recording status"}))
    .toContainText("sealed", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});

  // Control→PCM from the exported master capture: the dry hit carries the
  // sawtooth; the swept hit keeps only a residue at least 20 dB below.
  const wav = parsePcm16StereoWav(await exportPerformanceWav(page));
  const first = firstSignalFrame(wav.left);
  const open = wav.left.slice(first, first + 4_800);
  const secondStart = firstSignalFrame(wav.left, first + 4_800 + 2_400);
  const filtered = wav.left.slice(secondStart, secondStart + 4_800);
  expect(rms(open)).toBeGreaterThan(4_000);
  expect(rms(filtered)).toBeLessThan(rms(open) / 10);
  expect(rms(filtered)).toBeGreaterThan(0);

  await savePerformanceWithBusyRetry(page, "Filtered Set");
  const savedRevision = await projectRevision(page);
  await expect(page.getByRole("status", {name: "WAV binding status"}))
    .toContainText("bound");

  // Reopen from the far side, then replay the journaled typed Filter moves.
  await page.reload();
  await openLocalProject(page);
  expect(await projectRevision(page)).toBe(savedRevision);
  await activateAudio(page);
  await openPerform(page);
  await showPerformPage(page, "Replay");
  await expect(page.getByText("Filtered Set", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Replay Filtered Set"}).click();
  const replayStatus = page.getByRole("status", {name: "Replay status"});
  await expect(replayStatus).toContainText("playing", {timeout: 30_000});
  await expect(replayStatus).toContainText(
    new RegExp(`resolved revision\\s*[:·]\\s*${savedRevision}`, "i"),
  );
  await page.getByRole("button", {name: "Stop Replay"}).click();
  await expect(replayStatus).toContainText("stopped", {timeout: 30_000});

  // The replay neutral reset includes the independent Filter: the readback
  // returns to OFF from Core, never from a Host default.
  await showPerformPage(page, "Live");
  await page.getByRole("button", {name: "FILTER", exact: true}).click();
  await expect(filterStatus).toContainText("Off",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(filterStatus).toHaveAttribute("data-provenance", "core");
  await expect(page.getByRole("button", {name: "HOLD"}))
    .toHaveAttribute("aria-pressed", "false");
});


// C2 observes real Core output and the real Master tap. No audio implementation,
// request, input sequence or capture acknowledgement is replaced by this observer.
test("live Pad masks prove two-Pad PCM, all-64 identity, recording, leave and reopened replay", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(420_000);
  await page.addInitScript(() => {
    const NativeNode = window.AudioWorkletNode;
    window.__gateReplayPcm = [];
    window.__gateCaptureEnabled = false;
    window.AudioWorkletNode = class extends NativeNode {
      constructor(context, name, options) {
        super(context, name, options);
        if (name === "lmdj-perform-master-tap") this.port.addEventListener("message", ({data}) => {
          if (window.__gateCaptureEnabled && data?.type === "batch") {
            window.__gateReplayPcm.push(Array.from(data.channels[0]));
          }
        });
      }
    };
  });
  await importActivateAndPerform(page);
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  const quietWitness = pcm16Wav({channels: 2});
  for (let offset = 44; offset < quietWitness.length; offset += 2) {
    quietWitness.writeInt16LE(Math.round(quietWitness.readInt16LE(offset) / 2), offset);
  }
  await installWitnessOn(page, "Pad A01", "Z", quietWitness);
  await page.getByRole("button", {name: "Bank D", exact: true}).click();
  await installWitnessOn(page, "Pad D16", "4");
  await openPerform(page);
  await assignThenMovePattern(page);
  const selectPad = async (slot) => {
    const entry = page.getByRole("button", {name: "Live Mute / Solo", exact: true});
    if (await entry.count()) await entry.click();
    // A Bank change may hide the current Pad. The explicit control label still
    // names the one current selection and is the navigation starting point.
    const label = await page.getByRole("region", {name: "Current Pad live controls"}).locator("strong").textContent();
    const address = /([A-D])(\d{2})/.exec(label);
    let selected = (address[1].charCodeAt(0) - 65) * 16 + Number(address[2]) - 1;
    while (selected !== slot) {
      const step = selected < slot ? 1 : -1;
      await page.getByRole("button", {name: step > 0 ? "Next Pad — ↓" : "Previous Pad — ↑"}).click();
      selected += step;
    }
    await page.getByRole("button", {name: `Bank ${String.fromCharCode(65 + Math.floor(slot / 16))}`, exact: true}).click();
    await expect(page.getByRole("button", {name: `Mute ${String.fromCharCode(65 + Math.floor(slot / 16))}${String(slot % 16 + 1).padStart(2, "0")}`})).toBeVisible();
  };
  const gate = async (kind, slot, enabled) => {
    await selectPad(slot);
    const name = `${kind} ${String.fromCharCode(65 + Math.floor(slot / 16))}${String(slot % 16 + 1).padStart(2, "0")}`;
    const button = page.getByRole("button", {name, exact: true});
    await expect(button).toBeEnabled({timeout: LAUNCH_TRANSITION_TIMEOUT_MS});
    await button.click();
    await expect(button).toHaveAttribute("aria-pressed", String(enabled), {timeout: LAUNCH_TRANSITION_TIMEOUT_MS});
    await expect(button).toBeEnabled();
  };
  const before = await inspectProjectTruth(page);
  await gate("Solo", 0, true);
  await gate("Mute", 63, true);
  await expect(page.getByRole("status", {name: "Live Pad status"})).toHaveText("Silenced · Mute");
  expect(await inspectProjectTruth(page)).toEqual(before);
  const recording = await beginRecording(page);
  let pointer = 60;
  const strike = async (slot) => {
    await selectPad(slot);
    const address = `${String.fromCharCode(65 + Math.floor(slot / 16))}${String(slot % 16 + 1).padStart(2, "0")}`;
    const pad = page.getByRole("button", {name: new RegExp(`^Pad ${address} —`)});
    const pointerId = pointer++;
    await pad.dispatchEvent("pointerdown", {button: 0, isPrimary: true, pointerId});
    await expect(recording).toContainText(/open Pads\s*[:·]\s*1/i, {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    await page.waitForTimeout(180);
    await pad.dispatchEvent("pointerup", {button: 0, isPrimary: true, pointerId});
    await expect(recording).toContainText(/open Pads\s*[:·]\s*0/i, {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    await page.waitForTimeout(200);
  };
  await strike(63); // initial mute + initial other Solo: silence before any event change
  await strike(0);  // A, half amplitude
  const launch = page.getByRole("button", {name: "Launch Pattern 2"});
  await launch.click();
  await expect(launch).toHaveAttribute("data-launch", "acknowledged", {timeout: LAUNCH_TRANSITION_TIMEOUT_MS});
  await expect(page.getByRole("button", {name: "Solo A01"})).toHaveAttribute("aria-pressed", "true");
  await gate("Solo", 63, true);
  await gate("Mute", 63, false);
  await strike(63); // B, full amplitude; both A and D are Solo
  await gate("Mute", 0, true);
  await strike(0);  // mute wins over A's Solo
  await gate("Mute", 63, true);
  await strike(63); // mute wins over D's Solo
  await gate("Mute", 63, false);
  await strike(63); // B again
  await gate("Mute", 0, false);
  await strike(0);  // A again
  await stopRecording(page);
  const recorded = parsePcm16StereoWav(await exportPerformanceWav(page));
  const signature = (channel) => {
    const values = [];
    let from = 0;
    for (;;) {
      const start = channel.findIndex((value, index) => index >= from && Math.abs(value) > 256);
      if (start < 0) break;
      values.push(rms(channel.slice(start, start + 4_800)));
      from = start + 4_800 + 128;
    }
    return values;
  };
  const captured = signature(recorded.left);
  expect(captured).toHaveLength(4);
  expect(captured[0]).toBeGreaterThan(2_000);
  expect(captured[1] / captured[0]).toBeCloseTo(2, 1);
  expect(captured[2] / captured[0]).toBeCloseTo(2, 1);
  expect(captured[3] / captured[0]).toBeCloseTo(1, 1);
  await savePerformanceWithBusyRetry(page, "Gate Set");
  await expect(page.getByRole("status", {name: "WAV binding status"})).toContainText("bound");
  const savedRevision = await projectRevision(page);

  // Live exit owns an acknowledged clear, even when HOLD would preserve FX.
  await showPerformPage(page, "Live");
  await selectPad(63);
  const mute = page.getByRole("button", {name: "Mute D16"});
  if (await mute.getAttribute("aria-pressed") === "false") await gate("Mute", 63, true);
  await page.getByRole("button", {name: "Back to Filter", exact: true}).click();
  const hold = page.getByRole("button", {name: "HOLD", exact: true});
  if (await hold.getAttribute("aria-pressed") === "false") await hold.click();
  await expect(hold).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("main", {name: "Perform", exact: true})).toHaveCount(0);
  await openPerform(page);
  await page.getByRole("button", {name: "Live Mute / Solo", exact: true}).click();
  await expect(page.getByRole("button", {name: "Mute D16"})).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", {name: "Solo D16"})).toHaveAttribute("aria-pressed", "false");
  await selectPad(0);
  await expect(page.getByRole("button", {name: "Solo A01"})).toHaveAttribute("aria-pressed", "false");
  expect(await projectRevision(page)).toBe(savedRevision);
  const after = await inspectProjectTruth(page);
  expect(after.project.banks).toEqual(before.project.banks);

  // Reopen before replay; record that replay into an empty Pad using the real
  // Internal playback source. The PCM observer sees only the actual tap batches.
  await page.reload();
  await openLocalProject(page);
  expect(await projectRevision(page)).toBe(savedRevision);
  await activateAudio(page);
  await openPerform(page);
  await page.getByRole("button", {name: "System", exact: true}).click();
  await page.getByRole("group", {name: "Pad recording source"}).getByRole("button", {name: "Internal playback", exact: true}).click();
  await page.getByRole("button", {name: "Back to music", exact: true}).click();
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await page.getByRole("button", {name: "Bank B", exact: true}).click();
  await page.getByRole("button", {name: /^Pad B01 — assigned/}).click();
  await showSamplePage(page, "Pad");
  await page.getByRole("button", {name: "Delete Pad B01", exact: true}).click();
  await expect(page.getByRole("button", {name: /^Pad B01 — empty/})).toBeVisible();
  await openPerform(page);
  await showPerformPage(page, "Replay");
  await page.getByRole("button", {name: /^Pad B01 — empty/}).focus();
  await page.evaluate(() => { window.__gateReplayPcm = []; window.__gateCaptureEnabled = true; });
  await page.keyboard.down("KeyZ");
  await expect(page.getByRole("region", {name: "Pad recording"})).toContainText("recording");
  await page.getByRole("button", {name: "Replay Gate Set"}).click();
  const replay = page.getByRole("status", {name: "Replay status"});
  await expect(replay).toContainText("playing", {timeout: LAUNCH_TRANSITION_TIMEOUT_MS});
  await expect(replay).toContainText("complete", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await page.keyboard.up("KeyZ");
  await expect(page.getByRole("button", {name: /^Pad B01 — assigned/})).toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  const replayed = signature(await page.evaluate(() => window.__gateReplayPcm.flat().map(value => value * 32768)));
  expect(replayed).toHaveLength(4);
  for (let index = 0; index < 4; index += 1) expect(replayed[index] / captured[index]).toBeCloseTo(1, 1);
});


test("real capture progress counts silent PCM, final WAV frames and only its current Session identity", async ({page,browserName},info) => {
  test.skip(browserName!=="chromium");
  test.setTimeout(180_000);
  await observeMasterCaptureBatches(page);
  await page.addInitScript(() => {
    window.__captureProgressStarts=[];window.__captureProgressStops=[];
    const NativeNode=window.AudioWorkletNode;
    window.AudioWorkletNode=class extends NativeNode {
      constructor(...args){
        super(...args);
        if(args[1]!=="lmdj-perform-master-tap")return;
        this.port.addEventListener("message",({data})=>{
          if(data?.type==="started")window.__captureProgressStarts.push(structuredClone(data));
          if(data?.type==="stopped")window.__captureProgressStops.push(structuredClone(data));
        });
      }
    };
    const NativeContext=window.AudioContext;
    window.AudioContext=class extends NativeContext {
      constructor(...args){super(...args);window.__captureProgressContext=this;}
    };
  });
  await importActivateAndPerform(page);
  const read=()=>page.evaluate(()=>{
    const value=window.lmdjWebRuntimeHost.session.performanceMasterCaptureProgress();
    const ui=document.querySelector('[aria-label="Captured audio"]');
    const host=ui?{frames:Number(ui.dataset.frames),rate:Number(ui.dataset.rate),captureId:ui.dataset.captureId,text:ui.textContent}:null;
    return {value,host,sampleRate:window.__captureProgressContext.sampleRate,
      starts:window.__captureProgressStarts.filter(event=>event.generation===value.generation),
      stops:window.__captureProgressStops.filter(event=>event.generation===value.generation),
      batches:window.__performMasterBatchProof.filter(batch=>batch.generation===value.generation)};
  });
  const observations=[];
  for(let index=0;index<2;index++) {
    await beginRecording(page);
    await expect.poll(async()=>{
      const r=await read();return r.value.state==="available" && r.batches.filter(batch=>batch.peak===0).length>=2;
    },{timeout:AUDIO_TRANSITION_TIMEOUT_MS,intervals:[20]}).toBe(true);
    const target=(await read()).value.receivedFrames;
    const capturedUI=page.getByRole("status",{name:"Captured audio",exact:true});
    await expect.poll(async()=>Number(await capturedUI.getAttribute("data-frames")),
      {timeout:AUDIO_TRANSITION_TIMEOUT_MS,intervals:[20]}).toBeGreaterThanOrEqual(target);
    const active=await read();
    expect(active.host.captureId).toBe(active.value.captureId);
    expect(active.host.rate).toBe(active.sampleRate);
    let prefixFrames=0;const deliveredPrefixes=active.batches.map(batch=>(prefixFrames+=batch.frames));
    expect(deliveredPrefixes).toContain(active.host.frames);
    expect(active.host.text).not.toBe("Unavailable");
    expect(active.value.phase).toBe("recording");
    expect(active.value.sampleRate).toBe(active.sampleRate);
    expect(active.value.receivedFrames).toBe(active.batches.reduce((sum,batch)=>sum+batch.frames,0));
    expect(active.starts).toHaveLength(1);
    const actualBinding=active.starts[0].binding;
    expect(active.value.binding).toEqual(actualBinding===null?null:{
      controlEpoch:actualBinding.control_epoch,sessionId:actualBinding.session_id,
      beginCommandId:actualBinding.begin_command_id});
    if(actualBinding!==null){
      for(const id of Object.values(active.value.binding))expect(id).toMatch(/^[0-9a-f-]{36}$/);
    }
    if(index)expect(active.value.captureId).not.toBe(observations[0].stopped.value.captureId);
    await stopRecording(page);
    const stopped=await read();
    expect(stopped.value.state).toBe("available");
    expect(stopped.value.phase).toBe("stopped");
    expect(stopped.value.captureId).toBe(active.value.captureId);
    expect(stopped.value.binding).toEqual(active.value.binding);
    expect(stopped.value.droppedFrames).toBe(0);
    expect(stopped.value.failure).toBeNull();
    expect(stopped.value.receivedFrames).toBe(stopped.batches.reduce((sum,batch)=>sum+batch.frames,0));
    expect(stopped.stops).toHaveLength(1);
    expect(stopped.stops[0].finalSequence).toBe(stopped.batches.at(-1).sequence);
    const wav=await exportPerformanceWav(page);const pcm=parsePcm16StereoWav(wav);
    expect(stopped.value.receivedFrames).toBe(pcm.frames);
    expect(stopped.value.sampleRate).toBe(wav.readUInt32LE(24));
    expect(stopped.batches.filter(batch=>batch.peak===0).reduce((sum,batch)=>sum+batch.frames,0)).toBeGreaterThanOrEqual(9600);
    await expectLocalAudioFrames(page,pcm.frames,wav.readUInt32LE(24));
    await expect(capturedUI).toHaveAttribute("data-frames",String(stopped.value.receivedFrames));
    const geometry=[];
    const journeyViewport=page.viewportSize();
    if(index===0)for(const viewport of [{width:1440,height:900},{width:1280,height:720},
      {width:1024,height:768},{width:820,height:1180},{width:768,height:1024},{width:390,height:844}]) {
      await page.setViewportSize(viewport);
      await page.waitForFunction(({width,height})=>innerWidth===width&&innerHeight===height,viewport);
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));
      for(const name of ["Live","Takes"]) {
        await showPerformPage(page,name);
        const card=page.getByRole("region",{name:"Recording audio readout",exact:true});
        await card.scrollIntoViewIfNeeded();
        const measurement=await card.evaluate(root=>{
          const rect=node=>{const b=node.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height,right:b.right,bottom:b.bottom};};
          const touch=rect(root.closest('[data-testid="touch-workspace"]'));
          return {outer:rect(root),touch,
            rows:[...root.querySelectorAll('dl>div')].map(node=>({label:rect(node.firstElementChild),value:rect(node.lastElementChild)})),
            text:[...root.querySelectorAll('dt,dd')].map(node=>({text:node.textContent,width:node.clientWidth,scroll:node.scrollWidth})),
            scrollers:[...root.querySelectorAll('*')].filter(node=>['auto','scroll'].includes(getComputedStyle(node).overflowY)&&node.scrollHeight>node.clientHeight+1).length};
        });
        expect(measurement.outer.x).toBeGreaterThanOrEqual(measurement.touch.x-1);
        expect(measurement.outer.right).toBeLessThanOrEqual(measurement.touch.right+1);
        expect(measurement.outer.y).toBeGreaterThanOrEqual(measurement.touch.y-1);
        expect(measurement.outer.bottom).toBeLessThanOrEqual(measurement.touch.bottom+1);
        expect(measurement.scrollers).toBe(0);
        // Portrait tablet consoles rotate -90deg: separation may be on either
        // viewport axis. Both projections overlapping is the actual defect.
        for(const row of measurement.rows)expect(
          row.label.right<=row.value.x || row.value.right<=row.label.x ||
          row.label.bottom<=row.value.y || row.value.bottom<=row.label.y,
          JSON.stringify({viewport,name,row}),
        ).toBe(true);
        for(const text of measurement.text)expect(text.scroll,JSON.stringify({viewport,name,text})).toBeLessThanOrEqual(text.width+1);
        const controls=[];
        if(name==="Takes") {
          const panel=page.getByRole("region",{name:"Performance recording",exact:true});
          const targets=panel.locator('button,input,summary');
          for(let n=0;n<await targets.count();n++) {
            const target=targets.nth(n);if(!await target.isVisible())continue;
            await target.scrollIntoViewIfNeeded();
            const hit=await target.evaluate(node=>{
              const b=node.getBoundingClientRect(),touch=node.closest('[data-testid="touch-workspace"]').getBoundingClientRect();
              return {name:node.getAttribute('aria-label')??node.textContent,width:b.width,height:b.height,
                contained:b.x>=touch.x-1&&b.y>=touch.y-1&&b.right<=touch.right+1&&b.bottom<=touch.bottom+1,
                hit:node.contains(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2))};
            });
            expect(hit.width).toBeGreaterThanOrEqual(43.5);expect(hit.height).toBeGreaterThanOrEqual(43.5);
            expect(hit.contained,JSON.stringify({viewport,hit})).toBe(true);expect(hit.hit).toBe(true);controls.push(hit);
          }
          await card.scrollIntoViewIfNeeded();
        }
        geometry.push({viewport,page:name,...measurement,controls});
        const path=info.outputPath(`audio-${viewport.width}x${viewport.height}-${name}.png`);
        await page.screenshot({path});await info.attach(`audio ${viewport.width} ${name}`,{path,contentType:"image/png"});
      }
    }
    if(index===0) {
      // Geometry probes must restore the original journey's viewport before
      // continuing its discard/new-capture/Project reopen acceptance legs.
      await page.setViewportSize(journeyViewport);
      await page.waitForFunction(({width,height})=>innerWidth===width&&innerHeight===height,journeyViewport);
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));
    }
    observations.push({active,stopped,geometry,wav:{frames:pcm.frames,sampleRate:wav.readUInt32LE(24),byteLength:wav.byteLength,sha256:sha256(wav)}});
    await page.getByRole("button",{name:"Discard Performance",exact:true}).click();
    await expect(page.getByRole("status",{name:"Performance recording status"})).toContainText("idle",{timeout:PROJECT_TRANSITION_TIMEOUT_MS});
    await showPerformPage(page,"Live");
    await expect(page.getByRole("status",{name:"Captured audio",exact:true})).toHaveCount(0);
  }
  const retired=await page.evaluate(async()=>{
    const session=window.lmdjWebRuntimeHost.session;
    await session.close();
    return {cleanup:await session.waitForTerminalCleanup(),progress:session.performanceMasterCaptureProgress()};
  });
  expect(retired.cleanup).toBe(true);
  expect(retired.progress).toEqual({state:"unavailable",reason:"closed"});
  await page.reload();await openLocalProject(page);await activateAudio(page);await openPerform(page);
  const reopened=await page.evaluate(()=>window.lmdjWebRuntimeHost.session.performanceMasterCaptureProgress());
  expect(reopened).toEqual({state:"unavailable",reason:"idle"});
  await expect(page.getByRole("status",{name:"Local WAV audio",exact:true})).toHaveCount(0);
  const path=info.outputPath("capture-progress-frames.json");
  await writeFile(path,JSON.stringify({observations,retired,reopened},null,2));
  await info.attach("real capture frames and Session identity",{path,contentType:"application/json"});
});

test("Perform groups, four slots and horizontal controls fit six viewports with real readbacks", async ({page, browserName}, info) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await importActivateAndPerform(page);
  const truth = await inspectProjectTruth(page);
  const surface = page.getByRole("main", {name: "Perform", exact: true});
  const measureHeader = () => page.getByTestId("overview-display").evaluate(root => {
        const rect=node=>{const b=node.getBoundingClientRect(); return {x:b.x,y:b.y,width:b.width,height:b.height};};
        const context=root.querySelector('.overview-context'), transport=root.querySelector('.overview-transport');
        const a=rect(context), b=rect(transport), outer=rect(root);
        return {context:a,transport:b,outer,primary:rect(root.querySelector(".overview-primary")),contextScroll:context.scrollWidth,contextWidth:context.clientWidth,
          transportScroll:transport.scrollWidth,transportWidth:transport.clientWidth,
          overlap:Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x)>0.5 && Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y)>0.5};
      });
  const measureConsole = () => page.getByTestId("hardware-console").evaluate(root => {
    const rect=node=>{const b=node.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height};};
    const overlaps=(a,b)=>Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x)>0.5 && Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y)>0.5;
    const regions=[...root.children].filter(node=>node.matches('aside,section')).map(node=>({name:node.getAttribute('aria-label'),...rect(node)}));
    const conflicts=[];
    for(let i=0;i<regions.length;i++)for(let j=i+1;j<regions.length;j++)if(overlaps(regions[i],regions[j]))conflicts.push([regions[i].name,regions[j].name]);
    const keys=[...root.querySelectorAll('[data-testid="physical-controls"] button,[data-testid="pad-matrix"] button')].map(node=>({name:node.getAttribute('aria-label'),...rect(node)}));
    return {regions,conflicts,keys,outer:rect(root),viewport:{width:innerWidth,height:innerHeight},workspaceLocalHeight:root.parentElement.offsetHeight,scale:root.parentElement.style.getPropertyValue('--creator-stage-scale')};
  });
  const observations = [];
  for (const viewport of [{width:1440,height:900}, {width:1280,height:720},
    {width:1024,height:768}, {width:820,height:1180}, {width:768,height:1024}, {width:390,height:844}]) {
    await page.setViewportSize(viewport);
    for (const group of ["PRIMARY", "FILTER", "MORE"]) {
      const button = surface.getByRole("button", {name:group, exact:true});
      if (await button.getAttribute("aria-pressed") !== "true") await button.click();
      await expect(button).toHaveAttribute("aria-pressed", "true");
      const firstBinding={PRIMARY:"Cutoff",FILTER:"Type",MORE:"Crush"}[group];
      await expect(page.getByTestId("physical-controls").getByRole("button",{
        name:`Encoder 1 — ${firstBinding}`,exact:true})).toBeVisible();
      await expect(page.getByTestId("overview-display").locator('.encoder-readbacks dt').first()).toHaveText(`ENC1 ${firstBinding}`);
      const controls = await surface.locator("button,input,select,summary").evaluateAll(nodes => nodes.map(node => {
        const box = node.getBoundingClientRect();
        return {name:node.getAttribute("aria-label") || node.textContent.trim(),
          width:box.width, height:box.height, scroll:node.scrollWidth, client:node.clientWidth};
      }));
      for (const control of controls) {
        expect(control.width, JSON.stringify({viewport,group,control})).toBeGreaterThanOrEqual(44);
        expect(control.height, JSON.stringify({viewport,group,control})).toBeGreaterThanOrEqual(44);
        expect(control.scroll, JSON.stringify({viewport,group,control})).toBeLessThanOrEqual(control.client + 1);
      }
      const rails = await surface.locator('input[type="range"]').evaluateAll(nodes => nodes.map(node => {
        const box=node.getBoundingClientRect(); return {name:node.getAttribute("aria-label"), width:box.width, height:box.height,localWidth:node.offsetWidth,localHeight:node.offsetHeight,writingMode:getComputedStyle(node).writingMode};
      }));
      for (const rail of rails) {
        expect(rail.writingMode).toBe("horizontal-tb");
        expect(rail.localWidth, JSON.stringify({viewport,group,rail})).toBeGreaterThan(rail.localHeight);
      }
      await expect(surface.getByRole("slider", {name:"MASTER",exact:true})).toHaveCount(1);
      await expect(surface.getByRole("button", {name:"HOLD",exact:true})).toHaveCount(1);
      const slots = await surface.getByRole("button", {name:/^Launch Pattern /}).evaluateAll(nodes => nodes.map(node => {
        const b=node.getBoundingClientRect(); return {x:b.x,y:b.y,width:b.width,height:b.height,localX:node.offsetLeft,localY:node.offsetTop,localWidth:node.offsetWidth,id:node.dataset.patternId,state:node.dataset.launch};
      }));
      expect(slots).toHaveLength(4);
      expect(new Set(slots.map(slot => slot.localY)).size).toBe(1);
      for (let index=1;index<4;index++) expect(slots[index-1].localX + slots[index-1].localWidth).toBeLessThanOrEqual(slots[index].localX + 0.5);
      const text = await surface.locator('button,output,.perform-fader-name,.perform-fader-value,.perform-slot-state').evaluateAll(nodes => nodes
        .filter(node => !node.closest('.visually-hidden') && node.clientWidth > 0)
        .map(node => ({text:node.textContent.trim(),width:node.clientWidth,scroll:node.scrollWidth})));
      for (const value of text) expect(value.scroll, JSON.stringify({viewport,group,value})).toBeLessThanOrEqual(value.width+1);
      const encoderGeometry=await page.getByTestId("overview-display").locator('.encoder-readbacks > div').evaluateAll(nodes=>nodes.map(node=>({
        text:node.textContent,scroll:node.scrollWidth,width:node.clientWidth,
        children:[...node.children].map(child=>({text:child.textContent,scroll:child.scrollWidth,width:child.clientWidth}))
      })));
      expect(encoderGeometry).toHaveLength(4);
      for(const cell of encoderGeometry){
        expect(cell.scroll,JSON.stringify({viewport,group,cell})).toBeLessThanOrEqual(cell.width+1);
        for(const child of cell.children)expect(child.scroll,JSON.stringify({viewport,group,child})).toBeLessThanOrEqual(child.width+1);
      }
      const header = await measureHeader();
      expect(header.overlap, JSON.stringify({viewport,header})).toBe(false);
      expect(header.contextScroll, JSON.stringify({viewport,header})).toBeLessThanOrEqual(header.contextWidth+1);
      expect(header.transportScroll, JSON.stringify({viewport,header})).toBeLessThanOrEqual(header.transportWidth+1);
      expect(header.transport.y+header.transport.height).toBeLessThanOrEqual(header.primary.y+header.primary.height+1);
      const touch = page.getByTestId("touch-workspace");
      await expect.poll(() => touch.evaluate(node=>node.scrollWidth-node.clientWidth)).toBeLessThanOrEqual(1);
      const consoleGeometry = await measureConsole();
      expect(consoleGeometry.conflicts,JSON.stringify({viewport,consoleGeometry})).toEqual([]);
      for (const key of consoleGeometry.keys) {
        expect(key.width,JSON.stringify({viewport,key})).toBeGreaterThanOrEqual(44);
        expect(key.height,JSON.stringify({viewport,key})).toBeGreaterThanOrEqual(44);
      }
      for (const region of consoleGeometry.regions) {
        expect(region.x,JSON.stringify({viewport,region})).toBeGreaterThanOrEqual(0);
        expect(region.y,JSON.stringify({viewport,region})).toBeGreaterThanOrEqual(0);
        expect(region.x+region.width,JSON.stringify({viewport,region})).toBeLessThanOrEqual(viewport.width+0.5);
        expect(region.y+region.height,JSON.stringify({viewport,region})).toBeLessThanOrEqual(viewport.height+0.5);
      }
      observations.push({viewport,group,controls,rails,slots,text,header,encoderGeometry,consoleGeometry});
    }
    await surface.getByRole("button", {name:"PRIMARY",exact:true}).click();
    await expect(page.getByTestId("physical-controls").getByRole("button",{name:"Encoder 1 — Cutoff",exact:true})).toBeVisible();
    await expect(page.getByTestId("overview-display").locator('.encoder-readbacks dt').first()).toHaveText('ENC1 Cutoff');
    await expect(page.getByRole("button",{name:"Previous FX group — ←",exact:true})).toBeDisabled();
    await page.getByTestId("touch-workspace").evaluate(node=>{node.scrollTop=0;});
    const screenshot=info.outputPath(`perform-${viewport.width}x${viewport.height}.png`);
    await page.screenshot({path:screenshot});
    await info.attach(`perform-${viewport.width}x${viewport.height}`,{path:screenshot,contentType:"image/png"});
  }
  // Navigation above does not engage a producer, change masks or author Truth.
  const before = await page.evaluate(()=>window.lmdjWebRuntimeHost.session.queryPerformanceLiveStatus());
  expect(before.available).toBe(true);
  expect(before.applied.filter.engaged).toBe(false);
  expect(before.applied.mutedSlots).toEqual([]); expect(before.applied.soloSlots).toEqual([]);
  await surface.getByRole("button", {name:"FILTER",exact:true}).click();
  const cutoff=surface.getByRole("slider", {name:"Cutoff",exact:true});
  await cutoff.dispatchEvent("pointerdown",{pointerId:111});
  await cutoff.fill("700");
  await expect(cutoff).toHaveValue("700");
  await expect.poll(async()=>{
    const status=await page.evaluate(()=>window.lmdjWebRuntimeHost.session.queryPerformanceLiveStatus());
    return status.available && status.applied.filter.engaged && status.applied.filter.cutoffHz < 20000;
  },{timeout:LAUNCH_TRANSITION_TIMEOUT_MS}).toBe(true);
  await surface.getByRole("button", {name:"MORE",exact:true}).click();
  await expect.poll(async()=>{
    const status=await page.evaluate(()=>window.lmdjWebRuntimeHost.session.queryPerformanceLiveStatus());
    return status.available && !status.applied.filter.engaged && !status.applied.filter.frozen;
  },{timeout:LAUNCH_TRANSITION_TIMEOUT_MS}).toBe(true);
  await surface.getByRole("button", {name:"Live Mute / Solo",exact:true}).click();
  await expect(page.getByTestId("physical-controls").getByRole("button",{name:"Encoder 1 — Crush",exact:true})).toBeVisible();
  await expect(page.getByTestId("overview-display").locator('.encoder-readbacks dt').first()).toHaveText('ENC1 Crush');
  await surface.getByRole("button", {name:"Solo A01",exact:true}).click();
  await expect(surface.locator('.perform-pad-gate-summary')).toHaveAttribute('data-provenance','core', {timeout:LAUNCH_TRANSITION_TIMEOUT_MS});
  await expect(surface.locator('.perform-pad-gate-summary dd').nth(1)).toHaveText('A01');
  const masks=await page.evaluate(()=>window.lmdjWebRuntimeHost.session.queryPerformanceLiveStatus());
  expect(masks.applied.soloSlots).toEqual([0]);
  await surface.getByRole("button", {name:"Back to Filter",exact:true}).click();
  await expect(surface.getByRole("button", {name:"FILTER",exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByTestId("physical-controls").getByRole("button",{name:"Encoder 1 — Type",exact:true})).toBeVisible();
  await expect(page.getByTestId("overview-display").locator('.encoder-readbacks dt').first()).toHaveText('ENC1 Type');
  expect(await inspectProjectTruth(page)).toEqual(truth);
  // System retains the mounted Perform composition; returning without a
  // resize must preserve every region and the one current parameter group.
  await page.getByTestId("physical-controls").getByRole("button",{name:"System",exact:true}).click();
  await page.getByRole("button",{name:"Back to music",exact:true}).click();
  await expect(surface).toBeVisible();
  const remountedConsole=await measureConsole();
  expect(remountedConsole.conflicts).toEqual([]);
  for(const region of remountedConsole.regions) expect(region.y+region.height).toBeLessThanOrEqual(844+0.5);
  // Every mode now shares the same390px shell. COUNT-IN UI and its proof
  // remain withdrawn by #2396; retain the current mode-exit/re-entry legs.
  await page.getByTestId("physical-controls").getByRole("button", {name:"Sequence",exact:true}).click();
  await expect(surface).toHaveCount(0);
  const afterModeExit=await measureConsole();
  expect(afterModeExit.workspaceLocalHeight).toBe(remountedConsole.workspaceLocalHeight);
  expect(afterModeExit.conflicts).toEqual([]);
  // Pointer reentry must work from the common Sequence shell. Keep the
  // original keyboard entry as a separate leg after this added round trip.
  await page.getByTestId("physical-controls").getByRole("button",{name:"Perform",exact:true}).click();
  await expect(surface).toBeVisible();
  const pointerReentryConsole=await measureConsole();
  expect(pointerReentryConsole.workspaceLocalHeight).toBe(afterModeExit.workspaceLocalHeight);
  expect(pointerReentryConsole.conflicts).toEqual([]);
  await page.getByTestId("physical-controls").getByRole("button",{name:"Sequence",exact:true}).click();
  await expect(surface).toHaveCount(0);
  await page.getByTestId("physical-controls").getByRole("button",{name:"Perform",exact:true}).focus();
  await page.keyboard.press("Enter");
  await expect(surface).toBeVisible();
  const modeReentryConsole=await measureConsole();
  expect(modeReentryConsole.workspaceLocalHeight).toBe(afterModeExit.workspaceLocalHeight);
  expect(modeReentryConsole.conflicts).toEqual([]);
  for(const region of modeReentryConsole.regions) expect(region.y+region.height).toBeLessThanOrEqual(844+0.5);
  await page.getByTestId("physical-controls").getByRole("button",{name:"Sequence",exact:true}).click();
  await expect(surface).toHaveCount(0);
  await page.setViewportSize({width:1440,height:900});
  expect(await inspectProjectTruth(page)).toEqual(truth);
  const receipt=info.outputPath('perform-layout-and-native-readback.json');
  await writeFile(receipt,JSON.stringify({observations,before,masks,remountedConsole,afterModeExit,pointerReentryConsole,modeReentryConsole},null,2));
  await info.attach('perform-layout-and-native-readback',{path:receipt,contentType:'application/json'});
});


test("Slots explicit Assign Move Clear and return preserve real Truth across reopen", async ({page, browserName}, info) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  await importActivateAndPerform(page);
  const before = await inspectProjectTruth(page);
  let revision = await projectRevision(page);
  expect(before.project.pattern_slots).toEqual(Array(16).fill(null));
  const transport = page.getByTestId("overview-display").locator(".overview-transport");
  const beforeTransport = await transport.textContent();
  await showPerformPage(page, "Slots");
  const assignment = page.getByRole("combobox", {name: "Pattern assignment", exact: true});
  const target = page.getByRole("combobox", {name: "Pattern slot", exact: true});
  const readback = page.getByRole("status", {name: "Selected Pattern slot", exact: true});
  await assignment.selectOption(PATTERN_ID);
  await target.selectOption({value: "15"});
  await page.getByRole("combobox", {name: "Move Pattern from"}).selectOption({value: "15"});
  await page.getByRole("combobox", {name: "Move Pattern to"}).selectOption({value: "14"});
  await page.getByRole("combobox", {name: "Clear Pattern slot"}).selectOption({value: "14"});
  await target.focus();
  await page.keyboard.press("Escape");
  await showPerformPage(page, "Live");
  expect(await inspectProjectTruth(page)).toEqual(before);
  expect(await projectRevision(page)).toBe(revision);
  expect(await transport.textContent()).toBe(beforeTransport);
  await showPerformPage(page, "Slots");
  await expect(target).toHaveValue("15");
  await expect(readback).toHaveText("Slot 16 · Empty");
  await page.getByRole("button", {name: "Assign Pattern", exact: true}).click();
  revision = await expectRevisionAfter(page, revision);
  const assigned = await inspectProjectTruth(page);
  expect(assigned.project.pattern_slots).toEqual([...Array(15).fill(null), PATTERN_ID]);
  await expect(readback).toHaveText("Slot 16 · Pattern 01");
  await page.getByRole("button", {name: "Move Pattern", exact: true}).click();
  revision = await expectRevisionAfter(page, revision);
  const moved = await inspectProjectTruth(page);
  expect(moved.project.pattern_slots).toEqual([...Array(14).fill(null), PATTERN_ID, null]);
  await expect(readback).toHaveText("Slot 16 · Empty");
  await page.getByRole("button", {name: "Clear Pattern", exact: true}).click();
  revision = await expectRevisionAfter(page, revision);
  const cleared = await inspectProjectTruth(page);
  expect(cleared.project.pattern_slots).toEqual(Array(16).fill(null));
  await page.getByRole("button", {name: "Assign Pattern", exact: true}).click();
  revision = await expectRevisionAfter(page, revision);
  const committed = await inspectProjectTruth(page);
  expect(committed.project.pattern_slots).toEqual(assigned.project.pattern_slots);
  await showPerformPage(page, "Live");
  await showPatternLaunchGroup(page, 16);
  await expect(page.getByRole("button", {name: "Launch Pattern 16", exact: true}))
    .toHaveAttribute("data-pattern-id", PATTERN_ID);
  await page.reload();
  await openLocalProject(page);
  expect(await projectRevision(page)).toBe(revision);
  const reopened = await inspectProjectTruth(page);
  expect(reopened).toEqual(committed);
  await activateAudio(page);
  await openPerform(page);
  await showPerformPage(page, "Slots");
  await page.getByRole("combobox", {name: "Pattern slot", exact: true}).selectOption({value: "15"});
  await expect(page.getByRole("status", {name: "Selected Pattern slot", exact: true}))
    .toHaveText("Slot 16 · Pattern 01");
  const evidence = info.outputPath("slots-truth-reopen.json");
  await writeFile(evidence, JSON.stringify({before, assigned, moved, cleared, committed, reopened}, null, 2));
  await info.attach("Slots committed Truth and reopen", {path: evidence, contentType: "application/json"});
});

test("Takes verifies saved WAV audio including thirty minutes across two reopens", async ({page, browserName}, info) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(420_000);
  const fixtures = [
    {kind: "valid", name: "Duration Silent", frames: 48017, rate: 48000},
    {kind: "unsupported", name: "Duration Unsupported", frames: 48017, rate: 32000},
    {kind: "damaged", name: "Duration Damaged", frames: 48017, rate: 48000},
    {kind: "none", name: "Duration No WAV", frames: 0, rate: 48000},
    {kind: "long", name: "Duration Thirty Minutes", frames: 86400000, rate: 48000},
  ].map(value => {
    if (value.kind === "none") return {...value, artifact: null, header: null, physicalSha: null};
    const dataBytes = value.frames * 4;
    const header = Buffer.alloc(56);
    header.write("RIFF", 0);header.writeUInt32LE(dataBytes + 48, 4);header.write("WAVEfmt ", 8);
    header.writeUInt32LE(16, 16);header.writeUInt16LE(1, 20);header.writeUInt16LE(2, 22);
    header.writeUInt32LE(value.rate, 24);header.writeUInt32LE(value.rate * 4, 28);
    header.writeUInt16LE(4, 32);header.writeUInt16LE(16, 34);
    header.write("JUNK", 36);header.writeUInt32LE(3, 40);header.set([1, 2, value.kind === "damaged" ? 4 : 3, 171], 44);
    header.write("data", 48);header.writeUInt32LE(dataBytes, 52);
    const digest = (corrupt = false) => {
      const hash = createHash("sha256").update(header), zeros = Buffer.alloc(65536);
      for (let remaining = dataBytes - (corrupt ? 1 : 0); remaining > 0;) {
        const count = Math.min(remaining, zeros.byteLength);hash.update(zeros.subarray(0, count));remaining -= count;
      }
      if (corrupt) hash.update(Buffer.from([1]));
      return hash.digest("hex");
    };
    const sha256 = digest();
    return {...value, artifact: {sha256, media_type: "audio/wav", byte_length: dataBytes + 56},
      header: Array.from(header), physicalSha: value.kind === "damaged" ? digest(true) : sha256};
  });
  // Absolute witnesses distinguish a shared fixture-encoding mistake from
  // producer/consumer agreement. Long audio is physically hashed, not decoded.
  expect(fixtures[0].artifact.sha256).toBe("985ee1bbde8458eeb675cff7bb99b6bd61278b9646a127c7c39b1fb7634cb2d5");
  expect(fixtures[1].artifact.sha256).toBe("62aedd330eea859b7e3725d842cf089a97177d8a0f2918ad0d151212230c9d19");
  expect(fixtures[2].artifact.sha256).toBe("1c9584570dd5f2571c47180409b0e222f30667fafa5f6f72ec0eb858b1b1c345");
  expect(fixtures[2].physicalSha).toBe("f1ca5248d62d3cd2710a15dbfaab7d990bc2471bf58362ee85204a078671f895");
  // Corrupt one content-addressed file without corrupting the valid control.
  expect(new Set(fixtures.filter(value => value.artifact !== null).map(value => value.artifact.sha256)).size).toBe(4);
  expect(fixtures[4].artifact.byte_length).toBe(345600056);
  await importActivateAndPerform(page);
  const seeded = await page.evaluate(async fixtures => {
    const send = async (operation, payload) => {
      const response = await window.lmdjWebRuntimeHost.transport.send({protocol_version: 1,
        request_id: crypto.randomUUID(), operation, payload});
      if (!response.ok) throw new Error(operation + ": " + JSON.stringify(response));
      return response.result;
    };
    const inspected = await window.lmdjWebRuntimeHost.inspection.inspectProject();
    const projectId = inspected.project.project_id;
    let revision = inspected.project_revision;
    const root = await navigator.storage.getDirectory();
    const projects = await root.getDirectoryHandle("projects");
    const bundle = await projects.getDirectoryHandle(projectId + ".lmdj");
    const assets = await bundle.getDirectoryHandle("assets");
    const takes = [];
    for (const fixture of fixtures) {
      const performanceId = crypto.randomUUID(), recordingRevision = revision;
      const begin = await send("performance.record.begin", {command_id: crypto.randomUUID(),
        expected_revision: revision, session_id: performanceId, performance_id: performanceId});
      if (begin.project_revision !== revision + 1) throw new Error("begin revision changed");
      revision = begin.project_revision;
      await send("performance.record.stop", {session_id: performanceId, request_id: crypto.randomUUID()});
      let file;
      if (fixture.artifact !== null) {
        file = await assets.getFileHandle(fixture.artifact.sha256 + ".wav", {create: true});
        const writable = await file.createWritable();
        await writable.truncate(fixture.artifact.byte_length);
        await writable.write({type: "write", position: 0, data: new Uint8Array(fixture.header)});
        await writable.close();
      }
      const saved = await send("performance.save", {command_id: crypto.randomUUID(), expected_revision: revision,
        performance_id: performanceId, name: fixture.name, recording_artifact: fixture.artifact});
      if (saved.project_revision !== revision + 1) throw new Error("save revision changed");
      revision = saved.project_revision;
      if (fixture.kind === "damaged") {
        const writable = await file.createWritable({keepExistingData: true});
        await writable.write({type: "write", position: fixture.artifact.byte_length - 1, data: new Uint8Array([1])});
        await writable.close();
      }
      takes.push({...fixture, performanceId, recordingRevision});
    }
    await window.lmdjWebRuntimeHost.session.close();
    return {projectId, revision, takes, cleanup: await window.lmdjWebRuntimeHost.session.waitForTerminalCleanup()};
  }, fixtures);
  expect(seeded.cleanup).toBe(true);
  const reports = [], geometry = [];
  for (let reopen = 1; reopen <= 2; reopen++) {
    await page.reload();await openLocalProject(page);await activateAudio(page);await openPerform(page);
    await showPerformPage(page, "Takes");
    for (const take of seeded.takes) {
      await page.getByRole("button", {name: new RegExp(`^Select Take \\d+: ${take.name}$`)}).click();
      const output = page.getByRole("status", {name: "Take WAV audio", exact: true});
      const expectedState = {valid: "verified", unsupported: "unsupported", damaged: "damaged", none: "no-wav", long: "verified"}[take.kind];
      await expect(output).toHaveAttribute("data-state", expectedState, {timeout: AUDIO_TRANSITION_TIMEOUT_MS});
      await expect(output).toHaveText({valid: "00:01.000", unsupported: "WAV format unsupported",
        damaged: "WAV integrity check failed", none: "No WAV attached", long: "30:00.000"}[take.kind]);
      const ui = await output.evaluate(node => ({text: node.textContent, data: {...node.dataset}}));
      const evidence = await page.evaluate(async ({take, projectId, revision}) => {
        const session = window.lmdjWebRuntimeHost.session;
        const inspected = await session.inspectPerformance(take.performanceId);
        let receipt = null, physical = null;
        if (take.artifact !== null) {
          const start = performance.now();
          try {
            receipt = {ok: true, value: await session.queryPerformanceRecordingMetadata({projectId,
              performanceId: take.performanceId, expectedRevision: revision, recordingArtifact: {
                sha256: take.artifact.sha256, mediaType: "audio/wav", byteLength: take.artifact.byte_length}})};
          } catch (error) {receipt = {ok: false, code: error.code, details: error.details};}
          receipt.elapsedMs = performance.now() - start;
          const projects = await (await navigator.storage.getDirectory()).getDirectoryHandle("projects");
          const assets = await (await projects.getDirectoryHandle(projectId + ".lmdj")).getDirectoryHandle("assets");
          const file = await (await assets.getFileHandle(take.artifact.sha256 + ".wav")).getFile();
          const prefix = new Uint8Array(await file.slice(0, 56).arrayBuffer());
          const tail = Array.from(new Uint8Array(await file.slice(-4).arrayBuffer()));
          const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer())),
            value => value.toString(16).padStart(2, "0")).join("");
          const header = new DataView(prefix.buffer);
          physical = {sha256: hash, byteLength: file.size, prefix: Array.from(prefix), tail,
            rate: header.getUint32(24, true), channels: header.getUint16(22, true),
            frames: header.getUint32(52, true) / header.getUint16(32, true)};
        }
        return {inspected, receipt, physical};
      }, {take, projectId: seeded.projectId, revision: seeded.revision});
      expect(evidence.inspected).toMatchObject({id: take.performanceId, name: take.name,
        recordingArtifact: take.artifact === null ? null : {
          sha256: take.artifact.sha256, mediaType: "audio/wav", byteLength: take.artifact.byte_length},
        events: [], projectRevision: seeded.revision});
      if (take.artifact !== null) {
        expect(evidence.physical).toEqual({sha256: take.physicalSha, byteLength: take.artifact.byte_length,
          prefix: take.header, tail: take.kind === "damaged" ? [0, 0, 0, 1] : [0, 0, 0, 0],
          rate: take.rate, channels: 2, frames: take.frames});
        if (take.kind === "damaged") expect(evidence.receipt).toMatchObject({ok: false,
          code: "COOK_FAILED", details: {storage_condition: "artifact_mismatch"}});
        else {
          expect(evidence.receipt).toMatchObject({ok: true, value: {projectId: seeded.projectId,
            performanceId: take.performanceId, projectRevision: seeded.revision,
            recordingRevision: take.recordingRevision, recordingArtifact: {
              sha256: take.artifact.sha256, mediaType: "audio/wav", byteLength: take.artifact.byte_length},
            audioMetadata: take.kind === "unsupported" ? null : {sampleRate: take.rate, channels: 2, sourceFrames: take.frames},
            audioError: take.kind === "unsupported" ? {code:"UNSUPPORTED_AUDIO"} : null}});
          expect(ui.data.sha256).toBe(take.artifact.sha256);
          expect(ui.data.byteLength).toBe(String(take.artifact.byte_length));
          expect(ui.data.projectRevision).toBe(String(seeded.revision));
          expect(ui.data.recordingRevision).toBe(String(take.recordingRevision));
        }
      }
      if (take.kind === "valid" || take.kind === "long") {
        expect(ui.data.frames).toBe(String(take.frames));expect(ui.data.rate).toBe(String(take.rate));
        await expect(page.getByText("Recording completeness unknown", {exact: true})).toBeVisible();
      } else expect(ui.data.frames).toBeUndefined();
      reports.push({reopen, take, ui, ...evidence});
    }
    if (reopen === 1) {
      await page.getByRole("button", {name: /^Select Take \d+: Duration Silent$/}).click();
      const output = page.getByRole("status", {name: "Take WAV audio", exact: true});
      await expect(output).toHaveText("00:01.000", {timeout: AUDIO_TRANSITION_TIMEOUT_MS});
      const originalViewport = page.viewportSize();
      for (const viewport of [{width:1440,height:900},{width:1280,height:720},{width:1024,height:768},
        {width:820,height:1180},{width:768,height:1024},{width:390,height:844}]) {
        await page.setViewportSize(viewport);
        await page.waitForFunction(({width,height}) => innerWidth === width && innerHeight === height, viewport);
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
        const panel = page.getByRole("region", {name: "Saved Takes", exact: true});
        const controls = panel.getByRole("button"), hits = [];
        for (let i = 0; i < await controls.count(); i++) {
          const button = controls.nth(i);await button.scrollIntoViewIfNeeded();
          const hit = await button.evaluate(node => {
            const b = node.getBoundingClientRect(), touch = node.closest('[data-testid="touch-workspace"]').getBoundingClientRect();
            return {name: node.textContent, width: b.width, height: b.height,
              contained: b.x >= touch.x - 1 && b.y >= touch.y - 1 && b.right <= touch.right + 1 && b.bottom <= touch.bottom + 1,
              hit: node.contains(document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2))};
          });
          expect(hit.width).toBeGreaterThanOrEqual(43.5);expect(hit.height).toBeGreaterThanOrEqual(43.5);
          expect(hit.contained, JSON.stringify({viewport, hit})).toBe(true);expect(hit.hit).toBe(true);hits.push(hit);
        }
        const card = page.getByRole("region", {name: "Saved Take audio", exact: true});
        await card.scrollIntoViewIfNeeded();
        const measurement = await panel.evaluate(node => ({
          text: [...node.querySelectorAll('dt,dd,button span')].map(item => ({text:item.textContent, width:item.clientWidth, scroll:item.scrollWidth})),
          scrollers: [...node.querySelectorAll('*')].filter(item => ['auto','scroll'].includes(getComputedStyle(item).overflowY) && item.scrollHeight > item.clientHeight + 1).length,
        }));
        expect(measurement.scrollers).toBe(0);
        for (const text of measurement.text) expect(text.scroll, JSON.stringify({viewport,text})).toBeLessThanOrEqual(text.width + 1);
        geometry.push({viewport, hits, ...measurement});
        const image = info.outputPath(`saved-take-${viewport.width}x${viewport.height}.png`);
        await page.screenshot({path:image});await info.attach(`saved Take ${viewport.width}`, {path:image,contentType:"image/png"});
      }
      await page.setViewportSize(originalViewport);
      await page.waitForFunction(({width,height}) => innerWidth === width && innerHeight === height, originalViewport);
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
    }
    const retired = await page.evaluate(async () => {
      await window.lmdjWebRuntimeHost.session.close();
      return window.lmdjWebRuntimeHost.session.waitForTerminalCleanup();
    });
    expect(retired).toBe(true);
  }
  const path = info.outputPath("saved-take-audio-two-reopens.json");
  await writeFile(path, JSON.stringify({seeded, reports, geometry}, null, 2));
  await info.attach("saved Take WAV audio and physical readback", {path, contentType: "application/json"});
});

test("Replay event progress follows real receipts, completion, reopen and Stop across six viewports", async ({page, browserName}, info) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  await observeReplayTraffic(page);
  const candidate = await importActivateAndPerform(page);
  const name = "Evening take - live pads, Filter and HOLD ".padEnd(64, "x");
  expect(Array.from(name)).toHaveLength(64);
  await recordShortPerformance(page, {name, withFx: true, tailMs: 6_000});
  let saved;
  try {
    saved = await page.evaluate(async name => {
      const session = window.lmdjWebRuntimeHost.session;
      const summary = (await session.listPerformances()).find(value => value.name === name);
      if (summary === undefined) throw new Error("The real saved Take is missing");
      return {summary, inspected: await session.inspectPerformance(summary.performanceId)};
    }, name);
  } catch (error) {
    const diagnostic = info.outputPath("replay-performance-inspect-failure.json");
    await writeFile(diagnostic, JSON.stringify(await page.evaluate(() => ({
      wire: window.__replayWire, captureLoss: window.__replayCaptureLoss,
    })), null, 2));
    await info.attach("actual Performance inspect failure", {path: diagnostic, contentType: "application/json"});
    throw error;
  }
  expect(saved.summary.eventCount).toBeGreaterThan(4);
  expect(saved.inspected.events).toHaveLength(saved.summary.eventCount);
  expect(saved.summary.recordingArtifact.mediaType).toBe("audio/wav");
  await showPerformPage(page, "Replay");
  const replayButton = page.getByRole("button", {name: `Replay ${name}`, exact: true});
  await expect(replayButton).toBeEnabled();
  await expect(page.getByRole("status", {name: "Take WAV audio"})).toHaveCount(0);
  await replayButton.click();
  const playing = await expectReplayEvents(page, "playing", saved.summary.eventCount);
  await expect(replayButton).toBeDisabled();
  const begin = playing.wire.find(({request}) => request.operation === "performance.replay.begin");
  expect(begin.response.ok).toBe(true);
  expect(begin.response.result.event_cursor).toBe(0);
  expect(begin.response.result.event_count).toBe(saved.summary.eventCount);
  let progressing;
  await expect.poll(async () => {
    progressing = await replayEventWitness(page);
    return {state: progressing.ui?.state,
      advancing: progressing.ui?.cursor > 0 && progressing.ui.cursor < saved.summary.eventCount,
      matched: progressing.source !== null, neutral: progressing.ui?.neutral,
      captureLoss: progressing.captureLoss};
  }, {timeout: PROJECT_TRANSITION_TIMEOUT_MS}).toEqual({state: "playing", advancing: true,
    matched: true, neutral: false, captureLoss: 0});
  expect(progressing.ui.replayId).toBe(playing.ui.replayId);
  const completed = await expectReplayEvents(page, "complete", saved.summary.eventCount);
  expect(completed.ui.cursor).toBe(saved.summary.eventCount);
  expect(completed.wire.filter(({request}) => request.operation === "performance.replay.stop")).toEqual([]);
  await expect(page.getByRole("button", {name: "Stop Replay"})).toBeDisabled();

  const journeyViewport = page.viewportSize(), geometry = [];
  for (const viewport of [{width: 1440, height: 900}, {width: 1280, height: 720},
    {width: 1024, height: 768}, {width: 820, height: 1180}, {width: 768, height: 1024}, {width: 390, height: 844}]) {
    await page.setViewportSize(viewport);
    await page.waitForFunction(({width, height}) => innerWidth === width && innerHeight === height, viewport);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
    const surface = page.locator('.perform-surface[data-page="replay"]');
    const targets = surface.locator('button,input,select,summary');
    const hits = [];
    for (let n = 0; n < await targets.count(); n++) {
      const target = targets.nth(n);if (!await target.isVisible()) continue;
      await target.scrollIntoViewIfNeeded();
      const hit = await target.evaluate(node => {
        const b = node.getBoundingClientRect(), touch = node.closest('[data-testid="touch-workspace"]').getBoundingClientRect();
        return {name: node.getAttribute("aria-label") ?? node.textContent,
          width: b.width, height: b.height,
          contained: b.x >= touch.x-1 && b.y >= touch.y-1 && b.right <= touch.right+1 && b.bottom <= touch.bottom+1,
          hit: node.contains(document.elementFromPoint(b.x+b.width/2, b.y+b.height/2))};
      });
      expect(hit.width, JSON.stringify({viewport, hit})).toBeGreaterThanOrEqual(43.5);
      expect(hit.height, JSON.stringify({viewport, hit})).toBeGreaterThanOrEqual(43.5);
      expect(hit.contained, JSON.stringify({viewport, hit})).toBe(true);expect(hit.hit).toBe(true);
      hits.push(hit);
    }
    const text = await surface.evaluate(root => [...root.querySelectorAll('h2,h3,dt,dd,[aria-label="Replay events"],.perform-replay-status-card p')]
      .map(node => ({text: node.textContent, width: node.clientWidth, scroll: node.scrollWidth})));
    for (const value of text) expect(value.scroll, JSON.stringify({viewport, value})).toBeLessThanOrEqual(value.width+1);
    const scrollers = await surface.evaluate(root => [...root.querySelectorAll('*')].filter(node =>
      ['auto', 'scroll'].includes(getComputedStyle(node).overflowY) && node.scrollHeight > node.clientHeight+1).length);
    expect(scrollers).toBe(0);
    geometry.push({viewport, hits, text, scrollers});
    for (const [kind, locator] of [["take", replayButton], ["status", page.getByRole("region", {name: "Replay event readout"})]]) {
      if (kind === "take") {
        await surface.evaluate(node => {node.closest('[data-testid="touch-workspace"]').scrollTop = 0;});
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
        const heading = surface.locator('.perform-replay-take h3');
        const frame = await heading.evaluate(async node => {
          const b = node.getBoundingClientRect();
          const touch = node.closest('[data-testid="touch-workspace"]').getBoundingClientRect();
          const observer = await new Promise(resolve => {
            const observer = new IntersectionObserver(([entry]) => {
              observer.disconnect();resolve({ratio: entry.intersectionRatio,
                bounds: entry.boundingClientRect.toJSON(), intersection: entry.intersectionRect.toJSON()});
            });
            observer.observe(node);
          });
          const dx = Math.min(.5, b.width / 2), dy = Math.min(.5, b.height / 2);
          const points = [[b.left+dx,b.top+dy], [b.right-dx,b.top+dy],
            [b.left+dx,b.bottom-dy], [b.right-dx,b.bottom-dy], [b.x+b.width/2,b.y+b.height/2]];
          return {bounds: b.toJSON(), touch: touch.toJSON(), observer,
            contained: b.width > 0 && b.height > 0 && b.left >= Math.max(0,touch.left) &&
              b.top >= Math.max(0,touch.top) && b.right <= Math.min(innerWidth,touch.right) &&
              b.bottom <= Math.min(innerHeight,touch.bottom),
            unobscured: points.every(([x,y]) => node.contains(document.elementFromPoint(x,y)))};
        });
        expect(frame.contained, JSON.stringify({viewport,frame})).toBe(true);
        expect(frame.unobscured, JSON.stringify({viewport,frame})).toBe(true);
        geometry.at(-1).takeHeading = frame;
      } else await locator.scrollIntoViewIfNeeded();
      const path = info.outputPath(`replay-${kind}-${viewport.width}x${viewport.height}.png`);
      await page.screenshot({path});await info.attach(`Replay ${kind} ${viewport.width}`, {path, contentType: "image/png"});
    }
  }
  await page.setViewportSize(journeyViewport);
  await page.waitForFunction(({width, height}) => innerWidth === width && innerHeight === height, journeyViewport);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));

  await page.reload();await openLocalProject(page);await activateAudio(page);await openPerform(page);
  await showPerformPage(page, "Replay");
  const reopened = await page.evaluate(async id => window.lmdjWebRuntimeHost.session.inspectPerformance(id), saved.summary.performanceId);
  expect(reopened.events).toEqual(saved.inspected.events);
  expect(reopened.recordingArtifact).toEqual(saved.inspected.recordingArtifact);
  await page.getByRole("button", {name: `Replay ${name}`, exact: true}).click();
  const reopenedPlaying = await expectReplayEvents(page, "playing", saved.summary.eventCount);
  await page.getByRole("button", {name: "Stop Replay"}).click();
  const stopped = await expectReplayEvents(page, "stopped", saved.summary.eventCount);
  expect(stopped.ui.replayId).toBe(reopenedPlaying.ui.replayId);
  expect(stopped.wire.some(({request, response}) => request.operation === "performance.replay.stop" &&
    response.ok && response.result.state === "stopped")).toBe(true);

  // A genuine empty Performance goes through public begin/stop/save, then a
  // fresh session. It has no Host capture/WAV and cannot supply an audio clock.
  const empty = await page.evaluate(async () => {
    const {session, inspection} = window.lmdjWebRuntimeHost;
    const before = await inspection.inspectProject();
    const live = await session.queryPerformanceLiveStatus();
    if (!live.available) throw new Error("Current live-control owner is unavailable");
    const sessionId = crypto.randomUUID(), performanceId = crypto.randomUUID();
    await session.beginPerformanceRecording({sessionId, performanceId,
      expectedRevision: before.project_revision, controlEpoch: live.controlEpoch});
    await session.stopPerformanceRecording({sessionId, requestId: crypto.randomUUID()});
    const current = await inspection.inspectProject();
    await session.savePerformance({performanceId, expectedRevision: current.project_revision,
      name: "Empty event Take", recordingArtifact: null});
    const inspected = await session.inspectPerformance(performanceId);
    await session.close();
    return {inspected, retired: await session.waitForTerminalCleanup()};
  });
  expect(empty.retired).toBe(true);expect(empty.inspected.events).toEqual([]);
  expect(empty.inspected.recordingArtifact).toBeNull();
  await page.reload();await openLocalProject(page);await activateAudio(page);await openPerform(page);
  await showPerformPage(page, "Replay");
  await page.getByRole("button", {name: "Replay Empty event Take", exact: true}).click();
  const emptyComplete = await expectReplayEvents(page, "complete", 0);
  await expect(page.getByRole("progressbar", {name: "Replay event progress"})).toHaveCount(0);
  await expect(page.getByRole("status", {name: "Replay events"})).toHaveText("0 / 0 events");
  const path = info.outputPath("replay-event-progress-receipts.json");
  await writeFile(path, JSON.stringify({distribution: candidate.candidateManifest, saved, playing, progressing, completed,
    geometry, reopened, reopenedPlaying, stopped, empty, emptyComplete}, null, 2));
  await info.attach("Replay actual receipts and six viewport readback", {path, contentType: "application/json"});
});
