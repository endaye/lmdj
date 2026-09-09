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
// ALL THREE DEFECTS THAT BLOCKED THIS JOURNEY ARE FIXED, and both cases now
// run unaided. The `test.fail()` annotations they carried are gone:
//
//   #900  FIXED (f1293997). The browser Bundle reader allowlisted only
//         container 1.0.0/1.1.0 and lmdj.project.v1..v3, so no Project this
//         Build creates could be imported at all. This was the first wall and
//         the only one the journey ever reached unaided.
//   #901  FIXED (043623b0). The packaged Creator's `connect-src 'self'`
//         blocked every cross-origin Catalog, and every real Catalog is
//         cross-origin. The Creator now reaches its Catalog through a
//         same-origin prefix that the Host forwards, so that directive -- the
//         exfiltration barrier around the Projects and audio held in OPFS --
//         was left untouched.
//   #902  FIXED (694b983b). The Workspace Set Store refused to publish every
//         eligible Set with a bare IO_ERROR, because publication needs a
//         writer lease on the destination and the Store leased only its
//         staging directory.
//
// WHAT CHANGED IN THIS FILE when the journey first executed end to end, since
// legs 2 to 5 had until then only been checked by hand against
// `apps/creator-web/src/components/soundset_surface.tsx` and the 64-Pad proof
// fixture. Two expectations were wrong about the product rather than the
// product being wrong, and both were corrected upwards rather than removed:
//
//   * leg 1 expected one `/catalog/index.json`. There are two, because the
//     surface lists on mount and this leg then clicks Refresh Catalog. The
//     assertion now pins two, and pins that the second listing re-fetched no
//     object at all -- which proves the Workspace Set Store answered it.
//   * the last leg expected Bank B to hold 11 occupied Pads after installing
//     an 11-slot Set into it. The proof fixture fills all 64 Pads, so Bank B
//     holds 16 before and after; 11 move and 5 are left alone. The assertion
//     now pins that, which is the S11-D12 statement the leg was reaching for
//     and is stronger than the count it replaced.
//
// A `keep` leg was also missing and is now leg 4. Because the proof fixture
// fills every Bank, every occupied Set slot collides and `keep` can only ever
// write zero Pads here; that degenerate case is asserted for what it is -- the
// Host accepts the policy, answers, and moves neither a Pad nor the revision.
// A `keep` that writes some Pads and spares others needs a Bank with a free
// Pad under an occupied Set slot, which this Bundle does not contain, and is
// proved natively in `tests/host/cli_test.py::soundset_acceptance_journey`.
import {spawn} from "node:child_process";
import {readFileSync, writeFileSync} from "node:fs";
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
// The one expectation every Host is measured against for this Catalog. The
// Native and CLI Hosts assert the same file in
// `tests/host/soundset_catalog_partition_test.py`, so a Web Host that
// disagrees with them now fails here rather than passing its own suite. Before
// this, the browser only checked that the two reason strings appeared
// *somewhere* in a list of four -- two refusals could swap their tokens and
// nothing noticed.
const CATALOG_PARTITION = JSON.parse(
  readFileSync(resolve(fixtureRoot, "catalog-partition.json"), "utf8"),
);

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

// Idempotent, because leg 6 stops the Catalog on purpose and `afterEach` then
// stops it again. A child killed by a signal reports `exitCode === null` and
// names the signal in `signalCode`, so testing `exitCode` alone reads an
// already-dead server as still running -- and the second `once("exit")` waits
// forever on an event that has already been emitted.
async function stopCatalogServer(server) {
  if (
    server === null || server.child.exitCode !== null ||
    server.child.signalCode !== null
  ) {
    return;
  }
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
  // Written after the fixture has a port and before the page is opened. Leg 6
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
            // #799. Every Sound Set operation, in order, so the audition leg
            // can read the Host's own reply rather than inferring it from the
            // surface -- an audition changes nothing visible on success, which
            // is the defect that leg exists for.
            if (typeof request?.operation === "string" &&
                request.operation.startsWith("soundset.")) {
              window.__soundsetOperations ??= [];
              window.__soundsetOperations.push({
                operation: request.operation,
                payload: request.payload,
                ok: response?.ok ?? null,
                result: response?.result ?? null,
                error: response?.error ?? null,
              });
            }
            if (request?.operation === "project.inspect" && response?.ok) {
              window.__lastProjectTruth = response.result?.project ?? null;
              // Counted so a leg can wait for a Project read that is newer
              // than the commit it just made. Without it, an install that
              // writes nothing is indistinguishable from reading the snapshot
              // taken before it.
              window.__projectTruthReads = (window.__projectTruthReads ?? 0) + 1;
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
      `"${(await alert.innerText()).replace(/\s+/g, " ").trim()}". No leg of ` +
      "this journey can run without a Project, so everything below is " +
      "unmeasured rather than passing. remedy: compare the container " +
      "`contract_version` and `project_contract` the packer " +
      "(tools/project-bundle/project_bundle.py) writes against the two lists " +
      "the browser-side reader admits in packages/web-runtime-platform/web/" +
      "project_bundle_reader.mjs, and against the enum in " +
      "contracts/project/lmdj.project-bundle.v1.schema.json. Issue #900 was " +
      "exactly that drift once already, so check it before looking further.",
    );
  }
  await expect(heading).toBeVisible();
}

async function openSoundSets(page) {
  await page.getByRole("button", {name: "Sound Sets"}).click();
  await expect(page.getByRole("heading", {name: "Sound Sets", level: 2}))
    .toBeVisible();
}

// The Host's own last answer for one Sound Set operation. `null` until the
// operation has crossed the tap, which is what the polls below wait for.
async function lastSoundsetOperation(page, operation) {
  return page.evaluate(
    (name) =>
      (window.__soundsetOperations ?? [])
        .filter((entry) => entry.operation === name)
        .at(-1) ?? null,
    operation,
  );
}

async function soundsetOperationCount(page, operation) {
  return page.evaluate(
    (name) =>
      (window.__soundsetOperations ?? [])
        .filter((entry) => entry.operation === name).length,
    operation,
  );
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
  const expectedRefusals = CATALOG_PARTITION.refused;
  const expectedSetIds = Object.keys(expectedRefusals).sort();
  await expect(refusals.getByRole("listitem"))
    .toHaveCount(expectedSetIds.length);
  // Which Set carries which locked token, not just that the tokens appear.
  // Each row renders `<setId> <version> — <CODE> (<reason>)`, so the surface
  // can be read back into the same shape the Native and CLI Hosts answer with
  // and compared as one object: a swap between two refusals, a changed code,
  // or a Set moving across the eligible line all fail here.
  const observedRefusals = Object.fromEntries(
    (await refusals.getByRole("listitem").allInnerTexts()).map((row) => {
      const match = row.match(
        /^(\S+)\s+\S+\s+—\s+([A-Z_]+)\s+\(([a-z_]+)\)$/u,
      );
      expect(match, `unreadable refusal row: ${row}`).not.toBeNull();
      return [match[1], {code: match[2], reason: match[3]}];
    }),
  );
  expect(Object.keys(observedRefusals).sort()).toEqual(expectedSetIds);
  for (const setId of expectedSetIds) {
    expect(observedRefusals[setId], `refusal for ${setId}`).toEqual({
      code: expectedRefusals[setId].code,
      reason: expectedRefusals[setId].reason,
    });
  }
  // The CC-BY-4.0 credit comes from the verified manifest and reaches listing.
  await expect(listing.locator(".soundset-attribution")).toHaveText(
    "Fixture Attribution Kit by Bea Waveform (CC BY 4.0)",
  );

  // Two index reads, because there are two listings: the surface lists on
  // mount and this leg clicks Refresh Catalog. What the second listing must
  // not do is fetch one object again -- every manifest and blob below appears
  // exactly once across both listings, which is how this leg proves the
  // Workspace Set Store answered the second one rather than the Catalog.
  expect(targets.filter((target) => target === "/catalog/index.json"))
    .toHaveLength(2);
  const objects = targets.filter((target) => target !== "/catalog/index.json");
  for (const target of objects) {
    expect(target).toMatch(/^\/object\/(manifest|blob)\/[0-9a-f]{64}$/);
  }
  // One manifest per Catalog entry, eligible or not: eligibility is decided
  // from the verified manifest, so all seven are fetched and only the three
  // that pass go on to have their Artifacts acquired.
  expect(objects.filter((target) => target.startsWith("/object/manifest/")))
    .toHaveLength(7);
  expect(objects.filter((target) => target.startsWith("/object/blob/")))
    .toHaveLength(19);
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

  const before = await occupancyOf(page, 0);
  expect(
    before,
    "the Creator refreshes its Pad projection on open, so a null here means " +
    "no project.inspect reached the tap -- fix that before reading the rest",
  ).not.toBeNull();
  expect(Object.keys(before.pads)).toHaveLength(16);

  // Leg 3b -- audition and stop. Until this leg existed, Web audition had
  // never run in a browser at all: this file contained no occurrence of the
  // word, and the only proof of `soundset.audition` was in-process.
  //
  // Far side: the Host's own reply, read off the transport rather than off the
  // surface, because a successful audition changes nothing the surface shows.
  // That is exactly the defect `played` fixes -- before it, "the preview
  // played" and "the preview silently did not" were the same reply -- so the
  // assertion is on `played` being present and boolean, and on the geometry
  // that says which bytes it was.
  const revisionBeforeAudition = (await lastSoundsetOperation(
    page, "soundset.map.preview")).result.project_revision;
  expect(typeof revisionBeforeAudition).toBe("number");
  const previewsBeforeAudition = await soundsetOperationCount(
    page, "soundset.map.preview");

  await page.getByRole("button", {name: "Audition set demo"}).click();
  await expect.poll(
    async () => await lastSoundsetOperation(page, "soundset.audition"),
    {timeout: REQUEST_TIMEOUT_MS},
  ).not.toBeNull();
  const auditioned = await lastSoundsetOperation(page, "soundset.audition");
  expect(auditioned.ok).toBe(true);
  // The set-level demo is addressed by identity alone; a `slot_index` here
  // would mean the surface auditioned slot 0's Artifact instead.
  expect(auditioned.payload.slot_index).toBeUndefined();
  expect(auditioned.result.slot_index).toBeNull();
  // The Attribution Kit's demo declares its slot 0 Artifact, so the bytes the
  // Host reports playing are the ones this journey already fetched once.
  expect(auditioned.result.artifact.sha256).toBe(ATTRIBUTION_SHARED_ARTIFACT);
  expect(auditioned.result.audio.prepared_frames).toBeGreaterThan(0);
  expect(auditioned.result.audio.sample_rate).toBe(48_000);
  // The field this leg exists for, pinned to the state every Creator session
  // starts in: a Project is open and its snapshot is published, but audio has
  // never been activated, so the engine is stopped, `enqueue_control` refuses
  // the voice, and nothing sounds. Before `played`, this reply was byte for
  // byte the reply of an audition that did sound.
  expect(auditioned.result.played).toBe(false);
  // ACCEPTANCE GAP, and a live defect rather than a missing test. The other
  // half of this field -- `played === true` after "Activate audio" -- is not
  // exercised here because it terminates the Web Host. Driving it produces
  // `{"ok":true,"result":{...,"played":true}}` and then, inside one second and
  // with no page error, `creator-phase` goes to `failed`, the surface shows
  // "formal Web Host transport is terminated", and every later leg is
  // unmeasurable. Activating audio alone does not do it: a probe that
  // activated, idled four seconds and read the phase found `running` with no
  // alert, and only the audition that followed killed it.
  //
  // That is #799's byte path, not this field: `play_audition` is unchanged
  // apart from returning its outcome, and the same sequence passes natively in
  // `test_soundset_audition_reports_whether_a_voice_started`, which starts a
  // voice and renders it. Closing this gap costs a fix to the Web audition
  // path, after which the two lines below become `true` and this comment goes.
  // Until then, do not weaken the assertion above to `typeof … === "boolean"`:
  // that would pass either way and hide both halves.
  // Auditioning is Workspace-scoped: the operation never learns a Project, so
  // the Host reports no revision for it. This is the structural half of "the
  // Project did not move" -- an operation with no Project cannot write one.
  expect(auditioned.result.project_revision).toBeNull();

  await page.getByRole("button", {name: "Stop audition"}).click();
  await expect.poll(
    async () => await lastSoundsetOperation(page, "soundset.audition.stop"),
    {timeout: REQUEST_TIMEOUT_MS},
  ).not.toBeNull();
  const auditionStopped = await lastSoundsetOperation(
    page, "soundset.audition.stop");
  expect(auditionStopped.ok).toBe(true);
  expect(auditionStopped.result.accepted).toBe(true);
  // Stopping addresses this Host's engine and no Set, so it carries no
  // identity at all.
  expect(auditionStopped.payload).toEqual({});

  // The measured half of "the Project did not move": a fresh Host read of the
  // Project after the audition, not the projection cached before it. A second
  // `soundset.map.preview` is Project-scoped, so its `project_revision` comes
  // from Project Truth as it stands now.
  await page.getByRole("button", {name: "Preview mapping into Bank A"})
    .click();
  // Wait for a *newer* preview than the one that produced the number above.
  // Reading the revision straight away would read that same reply back and
  // pass on the first tick without ever asking the Host anything.
  await expect.poll(async () =>
    await soundsetOperationCount(page, "soundset.map.preview"),
  {timeout: REQUEST_TIMEOUT_MS}).toBeGreaterThan(previewsBeforeAudition);
  const afterAudition = await lastSoundsetOperation(
    page, "soundset.map.preview");
  expect(afterAudition.ok).toBe(true);
  expect(afterAudition.result.project_revision).toBe(revisionBeforeAudition);

  // Leg 4 -- install `keep`. The 64-Pad proof fixture fills every Bank, so
  // every one of this Set's four occupied slots collides and `keep` has
  // nothing left to write. That degenerate shape is the only `keep` this
  // fixture can produce -- a Bank with a free Pad under an occupied Set slot
  // does not exist in it -- and it is worth a leg anyway, because it is the
  // strongest possible statement of what `keep` means: the Host accepts the
  // policy, answers, and changes nothing at all. A non-degenerate `keep`,
  // where some Pads are written and the occupied ones are spared, is proved
  // natively in `tests/host/cli_test.py::soundset_acceptance_journey` and is
  // not reachable here without a second Bundle fixture.
  await page.getByRole("radio", {name: "Keep the Pads I already have"})
    .check();
  await expect(install).toBeEnabled();
  await expect(install).toHaveText("Install 0 of 16 into Bank A");
  const readsBeforeKeep = await page.evaluate(() =>
    window.__projectTruthReads ?? 0);
  await install.click();
  const receipt = page.locator(".soundset-receipt");
  await expect(receipt).toBeVisible({timeout: REQUEST_TIMEOUT_MS});
  await expect(receipt).toContainText("Installed 0 Pads into Bank A");
  const kept = await page.evaluate(() =>
    window.__soundsetInstalls?.at(-1) ?? null);
  expect(
    kept,
    "no soundset.install reached the transport tap, so nothing below is " +
    "measuring the Host -- fix the tap before reading the rest",
  ).not.toBeNull();
  expect(kept.ok).toBe(true);
  expect(kept.payload.occupied_pad_policy).toBe("keep");
  expect(kept.result.installed).toEqual([]);
  expect(kept.result.collisions).toEqual([0, 1, 2, 3]);
  expect(kept.result.kept).toEqual([
    4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
  ]);
  // The far side that matters: Project Truth did not move. A commit that
  // writes nothing must not advance the revision, and no Pad may change.
  expect(kept.result.project_revision).toBe(kept.payload.expected_revision);
  // Read a Project the Host produced *after* the commit, not the snapshot
  // taken before it. The Creator refreshes its Pad projection on every
  // install, zero-write ones included, so this always advances -- and without
  // waiting for it, "no Pad changed" would be satisfied by a stale read.
  await expect.poll(async () =>
    await page.evaluate(() => window.__projectTruthReads ?? 0),
  {timeout: REQUEST_TIMEOUT_MS}).toBeGreaterThan(readsBeforeKeep);
  const afterKeep = await occupancyOf(page, 0);
  for (let pad = 0; pad < 16; pad += 1) {
    expect(afterKeep.pads[pad]).toBe(before.pads[pad]);
  }

  // Leg 5 -- install replace, over the same collisions `keep` just spared.
  // Far side: the receipt names the committed revision, and the Project the
  // Host reads back afterwards shows the four Pads replaced with typed
  // `soundset` Lineage while the twelve Pads under empty Set slots still hold
  // the Asset they held before (S11-D12), and the Assets the install replaced
  // are still Project Truth (S8-D5).
  await page.getByRole("button", {name: "Preview mapping into Bank A"})
    .click();
  await expect(preview).toBeVisible({timeout: REQUEST_TIMEOUT_MS});
  await expect(install).toBeDisabled();
  await page.getByRole("radio", {name: "Replace them with this Set"}).check();
  await expect(install).toBeEnabled();
  await install.click();
  await expect(receipt).toBeVisible({timeout: REQUEST_TIMEOUT_MS});
  await expect(receipt).toContainText("Installed 4 Pads into Bank A");

  const committed = await page.evaluate(() =>
    window.__soundsetInstalls?.at(-1) ?? null);
  expect(
    committed,
    "no soundset.install reached the transport tap, so nothing below is " +
    "measuring the Host -- fix the tap before reading the rest",
  ).not.toBeNull();
  expect(committed.ok).toBe(true);
  expect(committed.payload.occupied_pad_policy).toBe("replace");
  expect(committed.result.installed.map((entry) => entry.pad))
    .toEqual([0, 1, 2, 3]);
  expect(committed.result.kept).toEqual([
    4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
  ]);
  // Unlike `keep` above, this one really committed.
  expect(committed.result.project_revision)
    .toBe(committed.payload.expected_revision + 1);

  // Yield the pre-install Asset id, not `null`, while no Project has been read
  // back: `null` is never equal to an Asset id, so a `null` here would satisfy
  // `.not.toBe(...)` on the first tick and the poll would not wait at all.
  await expect.poll(async () => {
    const truth = await occupancyOf(page, 0);
    return truth === null ? before.pads[0] : truth.pads[0];
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

  // Leg 6 -- the Catalog goes away. Far side: the cached Sets are still
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
  const beforeB = await occupancyOf(page, 1);
  expect(Object.keys(beforeB.pads)).toHaveLength(16);
  await page.getByRole("radio", {name: "Replace them with this Set"}).check();
  await page.getByRole("button", {name: /^Install /}).click();
  await expect(receipt).toContainText("Installed 11 Pads into Bank B", {
    timeout: REQUEST_TIMEOUT_MS,
  });
  await expect.poll(async () => {
    const truth = await occupancyOf(page, 1);
    return truth === null ? beforeB.pads[0] : truth.pads[0];
  }, {timeout: REQUEST_TIMEOUT_MS}).not.toBe(beforeB.pads[0]);
  const offlineTruth = await occupancyOf(page, 1);
  // The Foundry Set occupies eleven of its sixteen slots, and the proof
  // fixture fills all 64 Pads, so Bank B holds sixteen Pads before and after:
  // eleven move and five are left alone. Counting occupancy would therefore
  // prove nothing -- which Pad each Asset came from is the S11-D12 statement.
  expect(Object.keys(offlineTruth.pads)).toHaveLength(16);
  for (const pad of [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12]) {
    expect(offlineTruth.pads[pad]).not.toBe(beforeB.pads[pad]);
    const lineage = offlineTruth.assets[offlineTruth.pads[pad]].lineage;
    expect(lineage.source.kind).toBe("soundset");
    expect(lineage.derivation.kind).toBe("soundset_install");
    expect(lineage.source.slot_index).toBe(pad);
  }
  // S11-D12 offline as well as online: the Set's five empty slots left their
  // Pads exactly as they were, under the most destructive policy there is.
  for (const pad of [10, 11, 13, 14, 15]) {
    expect(offlineTruth.pads[pad]).toBe(beforeB.pads[pad]);
  }
});

// This case was originally titled so that the Creator gate's webkit slot
// (`--grep "capability boundary"`) would select it, on the belief that it
// would prove the transport on the WebKit engine. It cannot, and the title no
// longer says it does. Playwright's headless WebKit fails the Creator's
// preflight outright: `navigator.storage.getDirectory()` resolves but
// `getFileHandle(..., {create: true})` throws `UnknownError`, so `opfs` is
// missing, the session raises `UNSUPPORTED_WEB_RUNTIME`, and the Creator never
// leaves the `unsupported` phase -- there is no Sound Sets surface to drive.
// That boundary is pre-existing, is nothing to do with Sound Sets, and is
// already owned by `creator_web_accessibility.spec.mjs:239`; asserting it a
// second time here would add no signal. It also says nothing about Safari on
// macOS or a real iPad, which support OPFS sync access handles and stay human
// verification.
//
// What survives is a chromium case worth keeping on its own: the same-origin
// forward and the once-only accounting, proved without the install legs.
test("Sound Set listing reaches a Catalog through the same-origin forward", async ({page, browserName, baseURL}) => {
  test.skip(browserName !== "chromium");
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
  // Two listings, one on mount and one on the Refresh click, and still exactly
  // one fetch of the hash the Attribution Kit names twice.
  expect(targets.filter((target) => target === "/catalog/index.json"))
    .toHaveLength(2);
  expect(
    targets.filter((target) =>
      target === `/object/blob/${ATTRIBUTION_SHARED_ARTIFACT}`),
  ).toHaveLength(1);
});
