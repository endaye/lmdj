// Stage 11 Task 7, the Browser leg of the Sound Set acceptance journey.
//
// Everything below runs against the real Web Host: the Creator distribution
// served cross-origin isolated, a real Emscripten Runtime, the real
// `createFetchCatalogClient` transport, and a real Catalog fixture server on a
// second origin. No network request is stubbed, routed or rewritten: the
// network log is read, and the Facade transport is tapped by a passthrough
// that records and returns responses unchanged. The whole point of this leg is
// the one chain Task 5 could not prove -- browser fetch -> Host transport ->
// Core acquisition -> Set Store -> install -> Project Truth.
//
// The Catalog fixture server runs WITHOUT `--cross-origin`, and that is
// load-bearing rather than an omission. Since #901 the page never reaches a
// Catalog directly: it fetches the same-origin `/soundset-catalog/` prefix and
// the Host forwards. A fixture answering with no CORS header is unreadable by
// any direct browser fetch, so if this journey were ever rewired back to one,
// these legs would fail rather than quietly prove a topology the deployment
// does not use.
//
// BOTH CASES STILL CARRY `test.fail()`. Of the three pre-existing defects
// measured during the #674 acceptance run and filed rather than shortened
// away, two are fixed and #900 still stops this journey at its first wall:
//
//   #900  OPEN. The browser Bundle reader allowlists only container
//         1.0.0/1.1.0 and lmdj.project.v1..v3, so no Project this Build
//         creates can be imported at all. This is the first wall, and the only
//         one the journey has actually reached unaided.
//   #901  FIXED. The packaged Creator's `connect-src 'self'` blocked every
//         cross-origin Catalog, and every real Catalog is cross-origin. The
//         Creator now reaches its Catalog through a same-origin prefix that
//         the Host forwards, so that directive -- the exfiltration barrier
//         around the Projects and audio held in OPFS -- was left untouched.
//   #902  FIXED. With #900 and #901 patched locally the transport fetched the
//         whole fixture corpus correctly -- 1 index, 7 manifests, 19 blobs,
//         all 200, one request per unique hash -- and the Workspace Set Store
//         then refused to publish every eligible Set with a bare IO_ERROR.
//
// `test.fail()` rather than `skip` or `fixme` on purpose. The journey still
// runs in full, every leg and every far-side assertion stays exactly as
// strict as it is written, and Playwright turns the lane RED the moment the
// journey starts passing -- so the annotation cannot outlive the defects.
// Removing a leg to make this green would be the `acceptance-journey-
// truncation` pitfall. **Whoever lands #900 removes both annotations**, and
// should expect to debug legs 2 to 5 rather than watch them pass.
//
// HOW FAR THIS HAS ACTUALLY RUN, so nobody reads more into it than was
// measured: unaided, leg 1 stops at the Bundle import (#900). With #900 and
// #901 patched locally it reached leg 1's listing assertion and stopped
// there (#902). **Legs 2 to 5 have never executed.** Their selectors and
// expected counts were checked by hand against
// `apps/creator-web/src/components/soundset_surface.tsx` and the 64-Pad proof
// fixture, not by running them; expect to debug them when #900 lands.
import {spawn} from "node:child_process";
import {writeFileSync} from "node:fs";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

import {expect, test} from "@playwright/test";

const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

// #901: the Creator reaches its Catalog through a same-origin prefix the Host
// forwards, so this lane tells the proof server which Catalog to forward to.
// The lane owns the server it drives; without this path there is nothing to
// point at, and the run fails closed rather than proving itself against
// whatever the server was last told.
const upstreamFile = process.env.LMDJ_SOUNDSET_CATALOG_UPSTREAM_FILE;
if (!upstreamFile) {
  throw new Error("LMDJ_SOUNDSET_CATALOG_UPSTREAM_FILE is required");
}

// The page's endpoint, and the prefix every recorded target is relative to.
const CATALOG_PREFIX = "/soundset-catalog";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const fixtureRoot = resolve(repoRoot, "tests/fixtures/soundset");
const serverPath = resolve(
  repoRoot,
  "tools/soundset-fixtures/catalog_fixture_server.py",
);

const FOUNDRY = "Fixture Foundry CC0";
const ATTRIBUTION = "Fixture Attribution Kit";
const UNSUPPORTED = "Fixture Unsupported Audio Kit";
// The Attribution Kit's set-level `demo` declares its slot 0 Artifact hash, so
// four occupied slots and a demo are four objects on the wire, not five.
const ATTRIBUTION_SHARED_ARTIFACT =
  "e51f446a04207989eea06f7206befd4306362d8a9bcd34b5638100062e2af29c";
const IMPORT_TIMEOUT_MS = 120_000;
const REQUEST_TIMEOUT_MS = 30_000 + 5_000;

let catalog = null;

// The Creator lane owns the servers it drives, on kernel-assigned ports, so a
// second lane on the same host cannot collide with this one and a leaked
// server cannot make a later run pass against the wrong corpus.
async function startCatalogServer() {
  const child = spawn(
    "python3",
    [serverPath, "--root", fixtureRoot, "--port", "0"],
    {stdio: ["ignore", "pipe", "pipe"]},
  );
  const baseUrl = await new Promise((resolveUrl, rejectUrl) => {
    const timer = setTimeout(
      () => rejectUrl(new Error("Catalog fixture server did not start")),
      30_000,
    );
    let buffered = "";
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      buffered += chunk;
      const match = buffered.match(/at (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) {
        clearTimeout(timer);
        resolveUrl(match[1]);
      }
    });
    child.once("error", (error) => {
      clearTimeout(timer);
      rejectUrl(error);
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      rejectUrl(new Error(`Catalog fixture server exited with ${code}`));
    });
  });
  return {child, baseUrl};
}

async function stopCatalogServer(server) {
  if (server === null || server.child.exitCode !== null) return;
  const exited = new Promise((resolveExit) =>
    server.child.once("exit", resolveExit));
  server.child.kill("SIGTERM");
  await exited;
}

// One server per test: the last leg of the first case stops the Catalog on
// purpose, so a server shared across cases would leave the second one reading
// a corpse and calling it a pass.
test.beforeEach(async () => {
  catalog = await startCatalogServer();
  // Written after the fixture has a port and before the page is opened. Leg 5
  // stops the fixture and deliberately leaves this pointing at the dead port:
  // a Catalog that goes away is exactly what that leg is about, and the
  // forward then fails the way a real outage would.
  writeFileSync(upstreamFile, `${catalog.baseUrl}/`, {encoding: "utf8"});
});

test.afterEach(async () => {
  await stopCatalogServer(catalog);
  catalog = null;
  writeFileSync(upstreamFile, "", {encoding: "utf8"});
});

// Every Catalog request the page makes, recorded rather than intercepted.
// The page's Catalog traffic is same-origin now, so this watches the forwarding
// prefix. Slicing the origin and the prefix leaves the two S11-D6 shapes --
// `/catalog/index.json` and `/object/<kind>/<hash>` -- which is what the wire
// assertions below are written against and what the Host forwards upstream.
function recordCatalogTraffic(page, origin) {
  const prefix = `${origin}${CATALOG_PREFIX}`;
  const targets = [];
  page.on("request", (request) => {
    if (request.url().startsWith(prefix)) {
      targets.push(request.url().slice(prefix.length));
    }
  });
  return targets;
}

// The far side of an install: the Project the Host itself reads back. The
// Creator refreshes its Pad projection after a commit, so this is the app's
// own `project.inspect`, not a probe this test invented.
async function installProjectTap(page, catalogEndpoint) {
  await page.addInitScript((endpoint) => {
    window.__LMDJ_SOUNDSET_CATALOG__ = endpoint;
    let exposed;
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get() {
        return exposed;
      },
      set(nativeHost) {
        const nativeTransport = nativeHost.transport;
        nativeHost.transport = Object.freeze({
          async send(...parameters) {
            const [request] = parameters;
            const response = await nativeTransport.send(...parameters);
            if (request?.operation === "soundset.install") {
              window.__soundsetInstalls ??= [];
              window.__soundsetInstalls.push({
                payload: request.payload,
                ok: response?.ok ?? null,
                result: response?.result ?? null,
                error: response?.error ?? null,
              });
            }
            if (request?.operation === "project.inspect" && response?.ok) {
              window.__lastProjectTruth = response.result?.project ?? null;
            }
            return response;
          },
          subscribe: (...rest) => nativeTransport.subscribe(...rest),
          subscribeFailure: (...rest) =>
            nativeTransport.subscribeFailure(...rest),
          terminate: (...rest) => nativeTransport.terminate(...rest),
          get terminated() {
            return nativeTransport.terminated;
          },
          get terminalOwnerReleased() {
            return nativeTransport.terminalOwnerReleased;
          },
        });
        exposed = nativeHost;
      },
    });
  }, catalogEndpoint);
}

// Importing a Bundle is the only way a browser gets a Project, so a refusal
// here has to say what refused rather than time out on a heading that will
// never appear.
async function importProject(page) {
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  const heading = page.getByRole("heading", {name: /^Project /});
  const alert = page.getByRole("alert");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(bundle);
  await expect.poll(
    async () =>
      await heading.isVisible() ? "open"
        : await alert.isVisible() ? "refused" : "pending",
    {timeout: IMPORT_TIMEOUT_MS},
  ).not.toBe("pending");
  if (await alert.isVisible()) {
    throw new Error(
      "why: the Creator refused the acceptance Project Bundle -- " +
      `"${(await alert.innerText()).replace(/\s+/g, " ").trim()}". The ` +
      "browser-side reader in packages/web-runtime-platform/web/" +
      "project_bundle_reader.mjs still allowlists only contract_version " +
      "1.0.0/1.1.0 and lmdj.project.v1..v3, while the packer this Build " +
      "ships writes 1.2.0 and lmdj.project.v4, so no Project this Build " +
      "creates can be imported into a browser at all. remedy: fix issue " +
      "#900 -- widen both lists to the versions lmdj.project-bundle.v1 now " +
      "declares and give project_bundle_reader.test.mjs a case at the level " +
      "the packer actually writes. Issues #901 and #902 block the legs after " +
      "this one.",
    );
  }
  await expect(heading).toBeVisible();
}

async function openSoundSets(page) {
  await page.getByRole("button", {name: "Sound Sets"}).click();
  await expect(page.getByRole("heading", {name: "Sound Sets", level: 2}))
    .toBeVisible();
}

async function occupancyOf(page, bank) {
  return page.evaluate((index) => {
    const truth = window.__lastProjectTruth;
    if (truth === null || truth === undefined) return null;
    const pads = {};
    for (const pad of truth.banks[index].pads) {
      if (pad.asset_id) pads[pad.pad] = pad.asset_id;
    }
    return {pads, assets: truth.assets};
  }, bank);
}

test("Sound Sets browse, inspect, preview and install through the Web fetch transport", async ({page, browserName, baseURL}) => {
  test.skip(browserName !== "chromium");
  // Remove together with the `test.fail()` in the case below, once #900 is
  // fixed. Playwright fails the run if this ever passes.
  test.fail();
  test.setTimeout(300_000);
  const origin = new URL(baseURL).origin;
  const targets = recordCatalogTraffic(page, origin);
  await installProjectTap(page, `${origin}${CATALOG_PREFIX}/`);
  await page.goto("/index.html");
  await importProject(page);
  await openSoundSets(page);

  // Leg 1 -- list. Far side: the eligible Sets are published, the ineligible
  // ones are named with their locked reason, and the wire carries exactly the
  // two S11-D6 shapes.
  await page.getByRole("button", {name: "Refresh Catalog"}).click();
  const listing = page.getByRole("list", {name: "Catalog Sound Sets"});
  await expect(listing.getByRole("heading", {name: FOUNDRY}))
    .toBeVisible({timeout: REQUEST_TIMEOUT_MS});
  await expect(listing.getByRole("heading", {name: ATTRIBUTION}))
    .toBeVisible();
  await expect(listing.getByRole("heading", {name: UNSUPPORTED})).toBeVisible();
  await expect(listing.getByRole("listitem")).toHaveCount(3);
  const refusals = page.getByRole("list", {name: "Unavailable Sound Sets"});
  await expect(refusals.getByRole("listitem")).toHaveCount(4);
  await expect(refusals).toContainText("soundset_content_mismatch");
  await expect(refusals).toContainText("soundset_license_ineligible");
  // The CC-BY-4.0 credit comes from the verified manifest and reaches listing.
  await expect(listing.locator(".soundset-attribution")).toHaveText(
    "Fixture Attribution Kit by Bea Waveform (CC BY 4.0)",
  );

  expect(targets.filter((target) => target === "/catalog/index.json"))
    .toHaveLength(1);
  const objects = targets.filter((target) => target !== "/catalog/index.json");
  for (const target of objects) {
    expect(target).toMatch(/^\/object\/(manifest|blob)\/[0-9a-f]{64}$/);
  }
  // S11-D7: one hash is one download. The Attribution Kit names its slot 0
  // Artifact twice -- once as a slot, once as the set-level demo -- and the
  // Host must fetch it once.
  expect(
    objects.filter((target) =>
      target === `/object/blob/${ATTRIBUTION_SHARED_ARTIFACT}`),
  ).toHaveLength(1);
  expect(new Set(objects).size).toBe(objects.length);

  // Leg 2 -- inspect. Far side: the full 16-slot layout, with the empty slots
  // marked and carrying no control (S11-D12 starts in the surface).
  await listing.getByRole("button", {name: `Inspect ${ATTRIBUTION}`}).click();
  const inspect = page.getByRole("region", {
    name: `Sound Set ${ATTRIBUTION}`,
  });
  await expect(inspect).toBeVisible({timeout: REQUEST_TIMEOUT_MS});
  const slots = inspect.getByRole("list", {name: "Sound Set slots"})
    .getByRole("listitem");
  await expect(slots).toHaveCount(16);
  await expect(
    inspect.locator("li[data-empty='true'] .soundset-slot-empty"),
  ).toHaveCount(12);
  await expect(inspect.locator("li[data-empty='false']")).toHaveCount(4);

  // Leg 3 -- map.preview into a Bank whose every Pad is occupied. Far side:
  // four collisions, twelve Pads left alone under the Set's empty slots, and
  // a policy choice that the surface requires before it will install.
  await page.getByRole("button", {name: "Preview mapping into Bank A"})
    .click();
  const preview = page.locator(".soundset-preview");
  await expect(preview).toBeVisible({timeout: REQUEST_TIMEOUT_MS});
  await expect(preview.locator("[data-plan='collision']")).toHaveCount(4);
  await expect(preview.locator("[data-plan='empty-in-set']")).toHaveCount(12);
  await expect(preview.locator("[data-plan='install']")).toHaveCount(0);
  const install = page.getByRole("button", {name: /^Install /});
  await expect(install).toBeDisabled();

  // Leg 4 -- install replace. Far side: the receipt names the committed
  // revision, and the Project the Host reads back afterwards shows the four
  // Pads replaced with typed `soundset` Lineage while the twelve Pads under
  // empty Set slots still hold the Asset they held before (S11-D12), and the
  // Assets the install replaced are still Project Truth (S8-D5).
  const before = await occupancyOf(page, 0);
  expect(
    before,
    "the Creator refreshes its Pad projection on open, so a null here means " +
    "no project.inspect reached the tap -- fix that before reading the rest",
  ).not.toBeNull();
  expect(Object.keys(before.pads)).toHaveLength(16);
  await page.getByRole("radio", {name: "Replace them with this Set"}).check();
  await expect(install).toBeEnabled();
  await install.click();
  const receipt = page.locator(".soundset-receipt");
  await expect(receipt).toBeVisible({timeout: REQUEST_TIMEOUT_MS});
  await expect(receipt).toContainText("Installed 4 Pads into Bank A");

  const committed = await page.evaluate(() =>
    window.__soundsetInstalls?.at(-1) ?? null);
  expect(committed.ok).toBe(true);
  expect(committed.payload.occupied_pad_policy).toBe("replace");
  expect(committed.result.installed.map((entry) => entry.pad))
    .toEqual([0, 1, 2, 3]);
  expect(committed.result.kept).toEqual([
    4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
  ]);

  await expect.poll(async () => {
    const truth = await occupancyOf(page, 0);
    return truth === null ? null : truth.pads[0];
  }, {timeout: REQUEST_TIMEOUT_MS}).not.toBe(before.pads[0]);
  const after = await occupancyOf(page, 0);
  for (const pad of [0, 1, 2, 3]) {
    expect(after.pads[pad]).not.toBe(before.pads[pad]);
    const lineage = after.assets[after.pads[pad]].lineage;
    expect(lineage.derivation.kind).toBe("soundset_install");
    expect(lineage.source.kind).toBe("soundset");
    expect(lineage.source.slot_index).toBe(pad);
    // S8-D5: the Asset this Pad used to hold was not deleted.
    expect(after.assets[before.pads[pad]]).toBeDefined();
  }
  for (let pad = 4; pad < 16; pad += 1) {
    expect(after.pads[pad]).toBe(before.pads[pad]);
  }

  // Leg 5 -- the Catalog goes away. Far side: the cached Sets are still
  // listed and still installable, and the surface says so rather than
  // emptying itself.
  await stopCatalogServer(catalog);
  await page.getByRole("button", {name: "Refresh Catalog"}).click();
  await expect(page.locator(".soundset-offline")).toContainText(
    "Catalog unreachable — showing 3 cached Sets from this Workspace",
    {timeout: REQUEST_TIMEOUT_MS},
  );
  await expect(listing.getByRole("listitem")).toHaveCount(3);

  await listing.getByRole("button", {name: `Inspect ${FOUNDRY}`}).click();
  const offlineInspect = page.getByRole("region", {
    name: `Sound Set ${FOUNDRY}`,
  });
  await expect(offlineInspect).toBeVisible({timeout: REQUEST_TIMEOUT_MS});
  await expect(
    offlineInspect.getByRole("list", {name: "Sound Set slots"})
      .getByRole("listitem"),
  ).toHaveCount(16);

  await page.getByRole("button", {name: "Bank B"}).click();
  await page.getByRole("button", {name: "Preview mapping into Bank B"})
    .click();
  await expect(preview).toBeVisible({timeout: REQUEST_TIMEOUT_MS});
  await page.getByRole("radio", {name: "Replace them with this Set"}).check();
  await page.getByRole("button", {name: /^Install /}).click();
  await expect(receipt).toContainText("Installed 11 Pads into Bank B", {
    timeout: REQUEST_TIMEOUT_MS,
  });
  await expect.poll(async () => {
    const truth = await occupancyOf(page, 1);
    return truth === null ? 0 : Object.keys(truth.pads).length;
  }, {timeout: REQUEST_TIMEOUT_MS}).toBe(11);
  const offlineTruth = await occupancyOf(page, 1);
  for (const pad of [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12]) {
    expect(offlineTruth.assets[offlineTruth.pads[pad]].lineage.source.kind)
      .toBe("soundset");
  }
});

// The webkit slot runs only this case. It is a headless WebKit engine, not
// Safari on macOS or iPadOS: it proves the fetch transport and the surface
// work on the WebKit engine, and it says nothing about a real Safari or a real
// iPad, which stay human verification.
test("Sound Set capability boundary: the fetch transport reaches a Catalog through the same-origin forward", async ({page, baseURL}) => {
  // Blocked by the same #900 import wall. See the `test.fail()` note above.
  test.fail();
  test.setTimeout(300_000);
  const origin = new URL(baseURL).origin;
  const targets = recordCatalogTraffic(page, origin);
  await installProjectTap(page, `${origin}${CATALOG_PREFIX}/`);
  await page.goto("/index.html");
  await importProject(page);
  await openSoundSets(page);
  await page.getByRole("button", {name: "Refresh Catalog"}).click();
  const listing = page.getByRole("list", {name: "Catalog Sound Sets"});
  await expect(listing.getByRole("heading", {name: FOUNDRY}))
    .toBeVisible({timeout: REQUEST_TIMEOUT_MS});
  await expect(listing.getByRole("listitem")).toHaveCount(3);
  expect(targets.filter((target) => target === "/catalog/index.json"))
    .toHaveLength(1);
  expect(
    targets.filter((target) =>
      target === `/object/blob/${ATTRIBUTION_SHARED_ARTIFACT}`),
  ).toHaveLength(1);
});
