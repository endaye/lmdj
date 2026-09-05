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


const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

const repoRoot = resolve(import.meta.dirname, "../../../..");
const masterTapSource = resolve(
  repoRoot,
  "packages/web-runtime-platform/web/performance_master_tap_worklet.js",
);
const RECORDING_FRAMES = 86_400_000;
const RECORDING_QUEUE_BATCHES = 32;
const AUDIO_TRANSITION_TIMEOUT_MS = 35_000;
const PROJECT_TRANSITION_TIMEOUT_MS = 125_000;
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
  await page.goto(candidate.routed ? `${candidate.origin}/index.html` : "/index.html");
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  expect(candidate.candidateManifest.resource_limits).toMatchObject({
    perform_recording_frames: RECORDING_FRAMES,
    perform_recording_queue_batches: RECORDING_QUEUE_BATCHES,
  });
  expect(candidate.candidateManifest.assets.at(-1)).toEqual(candidate.tapEntry);
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
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

async function openLocalProject(page) {
  const heading = page.getByRole("heading", {name: "Project 00000000"});
  if (await heading.isVisible()) return;
  const open = page.getByRole("button", {name: "Open Project 00000000"});
  const retry = page.getByRole("button", {name: "Retry project"});
  await expect.poll(async () =>
    await heading.isVisible() ? "ready" :
      await open.isVisible() ? "open" : await retry.isVisible() ? "retry" : "",
  {timeout: PROJECT_TRANSITION_TIMEOUT_MS}).not.toBe("");
  if (await heading.isVisible()) return;
  if (await retry.isVisible()) {
    await retry.click();
    await expect(open).toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  }
  await open.click();
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

async function activateAudio(page) {
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
}

async function openPerform(page) {
  const perform = page.getByRole("button", {name: "Perform"});
  await expect(perform).toBeEnabled({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await perform.click();
  await expect(page.getByRole("main", {name: "Perform"})).toBeVisible();
  await expect(page.getByRole("button", {name: /^Launch Pattern /}))
    .toHaveCount(16);
}

async function importActivateAndPerform(page, scenario = "none") {
  const candidate = await openCandidate(page, scenario);
  await importProject(page);
  await activateAudio(page);
  await openPerform(page);
  return candidate;
}

async function openProjectSuccessor(context, url) {
  const successor = await context.newPage();
  await installDependencyScenario(successor);
  await routeCandidateIdentity(successor);
  await successor.goto(url);
  await openLocalProject(successor);
  await activateAudio(successor);
  await openPerform(successor);
  return successor;
}

async function launchCrashableCreatorContext(userDataDir) {
  const activePortPath = join(userDataDir, "DevToolsActivePort");
  await rm(activePortPath, {force: true});
  const child = spawn(chromium.executablePath(), [
    "--headless",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    `--user-data-dir=${userDataDir}`,
    "--remote-debugging-port=0",
    "about:blank",
  ], {stdio: "ignore"});
  let endpoint = null;
  for (let attempt = 0; attempt < 100 && endpoint === null; attempt += 1) {
    try {
      const [port] = (await readFile(activePortPath, "utf8")).trim().split(/\s+/);
      endpoint = `http://127.0.0.1:${port}`;
    } catch {
      await new Promise((resolveWait) => setTimeout(resolveWait, 50));
    }
  }
  if (endpoint === null) {
    child.kill("SIGKILL");
    throw new Error("Crashable Chromium did not publish its DevTools endpoint");
  }
  let browser = null;
  for (let attempt = 0; attempt < 20 && browser === null; attempt += 1) {
    try {
      browser = await chromium.connectOverCDP(endpoint);
    } catch {
      await new Promise((resolveWait) => setTimeout(resolveWait, 50));
    }
  }
  if (browser === null) {
    child.kill("SIGKILL");
    throw new Error("Crashable Chromium DevTools endpoint was unreachable");
  }
  const context = browser.contexts()[0];
  if (context === undefined) {
    child.kill("SIGKILL");
    throw new Error("Crashable Chromium default context is unavailable");
  }
  const page = context.pages()[0] ?? await context.newPage();
  return Object.freeze({
    browser,
    context,
    page,
    async kill() {
      if (child.exitCode === null) {
        const exited = once(child, "exit");
        child.kill("SIGKILL");
        await exited;
      }
      await browser.close().catch(() => {});
    },
  });
}

function projectRevisionLocator(page) {
  return page.locator(".status-facts div").filter({
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

async function beginRecording(page) {
  await page.getByRole("button", {name: "Record Performance"}).click();
  const status = page.getByRole("status", {name: "Performance recording status"});
  await expect(status).toContainText("recording", {
    timeout: PROJECT_TRANSITION_TIMEOUT_MS,
  });
  return status;
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

async function stopRecording(page) {
  await page.getByRole("button", {name: "Stop Performance"}).click();
  await expect(page.getByRole("status", {name: "WAV recording status"}))
    .toContainText("sealed", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
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

function deterministicPcm16Sample(frame, channel) {
  return Math.round((((frame + channel * 17) % 97) / 96 * 2 - 1) * 24_000);
}

function pcm16Wav({frames = 4_800, sampleRate = 48_000, channels = 1} = {}) {
  const bytes = Buffer.alloc(44 + frames * channels * 2);
  bytes.write("RIFF", 0, "ascii");
  bytes.writeUInt32LE(bytes.length - 8, 4);
  bytes.write("WAVE", 8, "ascii");
  bytes.write("fmt ", 12, "ascii");
  bytes.writeUInt32LE(16, 16);
  bytes.writeUInt16LE(1, 20);
  bytes.writeUInt16LE(channels, 22);
  bytes.writeUInt32LE(sampleRate, 24);
  bytes.writeUInt32LE(sampleRate * channels * 2, 28);
  bytes.writeUInt16LE(channels * 2, 32);
  bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36, "ascii");
  bytes.writeUInt32LE(frames * channels * 2, 40);
  for (let frame = 0; frame < frames; frame += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      const value = deterministicPcm16Sample(frame, channel);
      bytes.writeInt16LE(value, 44 + (frame * channels + channel) * 2);
    }
  }
  return bytes;
}

function parsePcm16StereoWav(bytes) {
  expect(bytes.subarray(0, 4).toString("ascii")).toBe("RIFF");
  expect(bytes.readUInt32LE(4)).toBe(bytes.byteLength - 8);
  expect(bytes.subarray(8, 12).toString("ascii")).toBe("WAVE");
  expect(bytes.subarray(12, 16).toString("ascii")).toBe("fmt ");
  expect(bytes.readUInt32LE(16)).toBe(16);
  expect(bytes.readUInt16LE(20)).toBe(1);
  expect(bytes.readUInt16LE(22)).toBe(2);
  expect(bytes.readUInt32LE(24)).toBe(48_000);
  expect(bytes.readUInt32LE(28)).toBe(192_000);
  expect(bytes.readUInt16LE(32)).toBe(4);
  expect(bytes.readUInt16LE(34)).toBe(16);
  expect(bytes.subarray(36, 40).toString("ascii")).toBe("data");
  expect(bytes.readUInt32LE(40)).toBe(bytes.byteLength - 44);
  expect((bytes.byteLength - 44) % 4).toBe(0);
  return {
    frames: (bytes.byteLength - 44) / 4,
    left: Array.from({length: (bytes.byteLength - 44) / 4}, (_, frame) =>
      bytes.readInt16LE(44 + frame * 4)),
    right: Array.from({length: (bytes.byteLength - 44) / 4}, (_, frame) =>
      bytes.readInt16LE(46 + frame * 4)),
  };
}

function firstSignalFrame(channel, from = 0) {
  const frame = channel.findIndex((sample, index) =>
    index >= from && Math.abs(sample) > 256);
  if (frame < 0) throw new Error(`No master-output signal after frame ${from}`);
  return frame;
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

async function exportPerformanceWav(page) {
  const pending = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export Performance WAV"}).click();
  return readFile(await (await pending).path());
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

async function installPerformWitnessSample(page) {
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  await page.getByRole("button", {name: "Bank A"}).click();
  const pad = page.getByRole("button", {name: /^Pad A1 — assigned/});
  await expect(pad).toBeVisible({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await pad.evaluate((element) => element.click());
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Replace Sample"}).click();
  await (await chooser).setFiles({
    name: "perform-master-witness-stereo.wav",
    mimeType: "audio/wav",
    buffer: pcm16Wav({channels: 2}),
  });
  await expect(page.getByRole("dialog", {name: "Replace Pad A1?"})).toBeVisible();
  await page.getByRole("button", {name: "Confirm replace"}).click();
  await expect(page.getByRole("button", {name: "Replace Sample"}))
    .toBeEnabled({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(page.locator(".selected-sample"))
    .toContainText("48 kHz · Mono · 4,800 frames");
  await openPerform(page);
}

async function replacePadSample(page) {
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  await page.getByRole("button", {name: "Bank A"}).click();
  const pad = page.getByRole("button", {name: /^Pad A1 — assigned/});
  await expect(pad).toBeVisible({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await pad.evaluate((element) => element.click());
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Replace Sample"}).click();
  await (await chooser).setFiles({
    name: "replacement-4801-frames.wav",
    mimeType: "audio/wav",
    buffer: pcm16Wav({frames: 4_801}),
  });
  await expect(page.getByRole("dialog", {name: "Replace Pad A1?"})).toBeVisible();
  await page.getByRole("button", {name: "Confirm replace"}).click();
  const longSource = page.getByRole("dialog", {name: "Pad A1 Long Source"});
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
  const pad = page.getByRole("button", {name: /^Pad A1\b/});
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

test("complete Perform journey persists projection, gestures, WAV, save, replay and resample", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(420_000);
  await importActivateAndPerform(page);
  await installPerformWitnessSample(page);

  let revision = await assignThenMovePattern(page);
  const recordingStatus = await beginRecording(page);
  revision = await expectRevisionAfter(page, revision);

  const pad = page.getByRole("button", {name: /^Pad A1\b/});
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
  await expect(launch).toHaveAttribute("data-proof-saw-launch", "pending");
  await expect(launch).toHaveAttribute("data-launch", "acknowledged", {
    timeout: 30_000,
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
  await page.getByRole("button", {name: "Bank B"}).click();
  await expect(page.getByRole("button", {name: "Bank B"}))
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
  await page.getByRole("spinbutton", {name: "Resample start frame"}).fill("0");
  await page.getByRole("spinbutton", {name: "Resample end frame"}).fill("4800");
  await page.getByRole("spinbutton", {name: "Resample target Pad"}).fill("16");
  await page.getByRole("button", {name: "Resample selection"}).click();
  await expectRevisionAfter(page, revision);
  await expect(page.getByRole("status", {name: "Resample status"}))
    .toContainText(/committed.*Pad B1/i);
});

test("discard deletes its temporary WAV and owner-loss recovery applies or discards durable truth", async ({browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(420_000);
  const applyProfile = await mkdtemp(join(tmpdir(), "lmdj-perform-owner-loss-apply-"));
  let ownerProcess = null;
  let applyingProcess = null;
  try {
    ownerProcess = await launchCrashableCreatorContext(applyProfile);
    const ownerPage = ownerProcess.page;
    const candidate = await importActivateAndPerform(ownerPage);
    const candidateUrl = candidate.routed
      ? `${candidate.origin}/index.html`
      : ownerPage.url();
    const baselineWavs = await opfsWavFiles(ownerPage);

    await beginRecording(ownerPage);
    await ownerPage.getByRole("button", {name: /^Pad A1\b/}).click();
    await stopRecording(ownerPage);
    expect((await opfsWavFiles(ownerPage)).length).toBeGreaterThan(baselineWavs.length);
    await ownerPage.getByRole("button", {name: "Discard Performance"}).click();
    await expect(ownerPage.getByRole("status", {name: "WAV recording status"}))
      .toContainText("temporary removed");
    await expect.poll(() => opfsWavFiles(ownerPage)).toEqual(baselineWavs);

    await beginRecording(ownerPage);
    await ownerPage.getByRole("button", {name: /^Pad A1\b/}).dispatchEvent("pointerdown", {
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
    await rm(applyProfile, {recursive: true, force: true});
  }

  const discardProfile = await mkdtemp(join(tmpdir(), "lmdj-perform-owner-loss-discard-"));
  let discardOwnerProcess = null;
  let discardingProcess = null;
  try {
    discardOwnerProcess = await launchCrashableCreatorContext(discardProfile);
    const discardOwnerPage = discardOwnerProcess.page;
    const candidate = await importActivateAndPerform(discardOwnerPage);
    const candidateUrl = candidate.routed
      ? `${candidate.origin}/index.html`
      : discardOwnerPage.url();
    await beginRecording(discardOwnerPage);
    await discardOwnerPage.getByRole("button", {name: /^Pad A2\b/}).dispatchEvent(
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
    await rm(discardProfile, {recursive: true, force: true});
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

  await expect(page.getByRole("alert")).toContainText(/WAV.*bind.*retry/i);
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
  await expect(emptySlot).toHaveAttribute("data-proof-saw-launch", "pending");
  await emptySlot.evaluate((element) => new Promise((resolve, reject) => {
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
    }, 30_000);
    observer.observe(element, {attributes: true, attributeFilter: ["data-launch"]});
    if (element.getAttribute("data-launch") === "acknowledged") finish();
  }));
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

test("owner process loss leaves one recoverable recording and no second capture owner", async ({browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(300_000);
  const profile = await mkdtemp(join(tmpdir(), "lmdj-perform-owner-candidate-"));
  let ownerProcess = null;
  let successorProcess = null;
  try {
    ownerProcess = await launchCrashableCreatorContext(profile);
    const ownerPage = ownerProcess.page;
    const candidate = await importActivateAndPerform(ownerPage);
    const candidateUrl = candidate.routed
      ? `${candidate.origin}/index.html`
      : ownerPage.url();
    await beginRecording(ownerPage);
    await ownerPage.getByRole("button", {name: /^Pad A1\b/}).dispatchEvent(
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
    await rm(profile, {recursive: true, force: true});
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
