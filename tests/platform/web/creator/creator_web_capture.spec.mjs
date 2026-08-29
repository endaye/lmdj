import {readFile} from "node:fs/promises";

import {expect, test} from "@playwright/test";

import {CAPTURE_FIXTURE_SECONDS} from "./fixtures/make_capture_fixture.mjs";

const sampleBundle = process.env.LMDJ_CREATOR_WEB_SAMPLE_BUNDLE;
const GRANTED = "creator-capture-chromium";
const DENIED = "creator-capture-denied-chromium";

// Read the revision from the exported report, the same way the Sample Editor
// spec does: .project-summary renders only in Project mode, so a DOM probe
// cannot verify a commit made from the Sample surface.
async function expectProjectRevision(page, expectedRevision) {
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export report"}).click();
  const report = JSON.parse(await readFile(await (await downloadPromise).path(), "utf8"));
  expect(report.sample.project_revision).toBe(expectedRevision);
}

async function report(page) {
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export report"}).click();
  return JSON.parse(await readFile(await (await downloadPromise).path(), "utf8"));
}

async function installProjectInspectProbe(page) {
  await page.addInitScript(() => {
    let exposed;
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get() {
        return exposed;
      },
      set(nativeHost) {
        const nativeTransport = nativeHost.transport;
        nativeHost.transport = Object.freeze({
          send(...arguments_) {
            return nativeTransport.send(...arguments_);
          },
          subscribe(...arguments_) {
            return nativeTransport.subscribe(...arguments_);
          },
          subscribeFailure(...arguments_) {
            return nativeTransport.subscribeFailure(...arguments_);
          },
          terminate(...arguments_) {
            return nativeTransport.terminate(...arguments_);
          },
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
  });
}

async function inspectProjectTruth(page) {
  const response = await page.evaluate(() =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "project.inspect",
      payload: {},
    }));
  expect(response.ok).toBe(true);
  return response.result;
}

async function pressRecordedPad(page, accessibleName, code) {
  const pad = page.getByRole("button", {name: accessibleName});
  await expect(pad).toHaveAttribute("data-outcome", "idle", {timeout: 30_000});
  await pad.evaluate((element) => {
    element.removeAttribute("data-proof-outcome-observed");
    const observeOutcome = () => {
      const outcome = element.getAttribute("data-outcome");
      if (outcome !== null && outcome !== "idle") {
        element.setAttribute("data-proof-outcome-observed", outcome);
        return true;
      }
      return false;
    };
    if (observeOutcome()) return;
    const observer = new MutationObserver(() => {
      if (observeOutcome()) observer.disconnect();
    });
    observer.observe(element, {attributes: true, attributeFilter: ["data-outcome"]});
  });
  await page.keyboard.down(code);
  await expect(pad).toHaveAttribute("data-proof-outcome-observed", /.+/, {
    timeout: 30_000,
  });
  await page.keyboard.up(code);
}

async function importV1SampleProject(page) {
  if (!sampleBundle) {
    throw new Error("LMDJ_CREATOR_WEB_SAMPLE_BUNDLE is required");
  }
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(sampleBundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.locator(".project-summary"))
    .toContainText("Revision46", {timeout: 120_000});
}

async function enterSampleEditor(page) {
  await page.getByRole("button", {name: "Sample"}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
}

async function selectPadWithoutPress(page, label) {
  await page.getByRole("button", {name: label}).evaluate((element) => element.click());
}

// Record until the panel reports at least `seconds` of buffered audio. The
// fixture is CAPTURE_FIXTURE_SECONDS long and Chromium loops it, so waiting on
// the panel's own elapsed readout is what makes this deterministic rather than
// sleeping for a wall-clock duration.
async function recordAtLeast(page, padLabel, seconds) {
  await page.getByRole("button", {name: "Record Sample"}).click();
  const panel = page.getByRole("dialog", {name: `${padLabel} Pad Capture`});
  await expect(panel).toBeVisible();
  await panel.getByRole("button", {name: `Record into ${padLabel}`}).click();
  await expect(panel.getByRole("button", {name: "Stop"}))
    .toBeVisible({timeout: 30_000});
  await expect(panel).toContainText(
    new RegExp(`${seconds}\\.\\d s|${seconds + 1}\\.\\d s`),
    {timeout: 60_000},
  );
  return panel;
}

// F1/F2: the panel is a viewport-anchored modal, so its primary action must be
// geometrically inside the viewport — a boundingBox check, not isVisible(),
// which never requires the element to be on screen.
async function expectWithinViewport(page, locator) {
  const viewport = page.viewportSize();
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
}

test("the capture panel and its primary actions stay within the viewport (F1/F2)", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(600_000);
  // Short enough that the old in-flow panel failed: at 1440×900 it rendered at
  // y ≈ 790 and grew to 277 px on recording, all below the fold.
  await page.setViewportSize({width: 1280, height: 720});
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);

  await selectPadWithoutPress(page, "Pad A1 — empty");
  await page.getByRole("button", {name: "Record Sample"}).click();
  const panel = page.getByRole("dialog", {name: "Pad A1 Pad Capture"});
  await expect(panel).toBeVisible();

  // idle: the panel and its primary action are inside the viewport.
  await expectWithinViewport(page, panel);
  await expectWithinViewport(
    page, panel.getByRole("button", {name: "Record into Pad A1"}),
  );

  // recording: entering the phase must not change the outer geometry, and
  // Stop must sit inside the viewport without any scrolling.
  await panel.getByRole("button", {name: "Record into Pad A1"}).click();
  const stop = panel.getByRole("button", {name: "Stop"});
  await expect(stop).toBeVisible({timeout: 30_000});
  await expectWithinViewport(page, panel);
  await expectWithinViewport(page, stop);

  await panel.getByRole("button", {name: "Close"}).click();
  await expect(panel).toBeHidden();
});

test("records, trims and commits a capture onto an empty Pad", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(600_000);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);

  await selectPadWithoutPress(page, "Pad A1 — empty");
  const panel = await recordAtLeast(page, "Pad A1", 1);
  await panel.getByRole("button", {name: "Stop"}).click();

  // Reaching the trim view means a non-empty buffer survived the stop
  // (S8B-D5); the growing-waveform image proves batches actually landed
  // rather than the fake device yielding silence.
  await expect(panel.getByRole("img", {name: "Pad A1 capture waveform"}))
    .toBeVisible();
  await expect(panel.getByRole("slider", {name: "Pad A1 Selection length"}))
    .toBeVisible();

  await panel.getByRole("button", {name: "Commit"}).click();
  // Commit returns the modal panel to idle. Close it before asserting the
  // background Project surface: native modal semantics make that surface
  // intentionally inert while the dialog remains open.
  await expect(panel.getByRole("button", {name: "Record into Pad A1"}))
    .toBeVisible({timeout: 180_000});
  await panel.getByRole("button", {name: "Close"}).click();
  await expect(panel).toBeHidden();
  await expect(page.getByRole("button", {name: "Pad A1 — assigned"}))
    .toBeVisible();
  // The committed capture flows through the ordinary post-import behaviour:
  // the Pad reads assigned and the Sample Editor renders its waveform.
  await expect(page.getByRole("img", {name: "Pad A1 mirrored waveform"}))
    .toBeVisible({timeout: 120_000});
  await expectProjectRevision(page, 47);
});

test("armed Pad capture commits without stopping the active Sequence", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(600_000);
  await installProjectInspectProbe(page);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  const initialTruth = await inspectProjectTruth(page);
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: 30_000,
  });
  await enterSampleEditor(page);
  await selectPadWithoutPress(page, "Pad A1 — empty");
  const panel = await recordAtLeast(page, "Pad A1", 1);

  await panel.getByRole("button", {name: "Continue in Sequence"}).click();
  await expect(page.getByRole("heading", {name: "Sequence"})).toBeVisible();
  await page.getByRole("button", {name: "Record"}).click();
  await expect(page.getByRole("status").filter({hasText: "recording"}))
    .toBeVisible();

  const patternId = await page.getByRole("combobox", {name: "Pattern"})
    .inputValue();
  const initialEvents = structuredClone(
    initialTruth.project.patterns[patternId].events,
  );

  // A distinct non-armed Pad is ordinary Sequence input before the Capture
  // stop gesture. This event must survive the Capture commit/rebase boundary.
  await pressRecordedPad(page, "Pad A2 — assigned", "KeyW");

  // The armed Pad stops only its capture. The Sequence session stays beneath
  // the trim overlay and the armed hit itself is not recorded.
  await page.keyboard.press("KeyQ");
  await expect(panel.getByRole("slider", {name: "Pad A1 Selection length"}))
    .toBeVisible({timeout: 30_000});
  await panel.getByRole("button", {name: "Commit"}).click();
  await expect(panel).toBeHidden({timeout: 180_000});
  await expect(page.getByRole("status").filter({hasText: "recording"}))
    .toBeVisible({timeout: 30_000});
  const committedTruth = await inspectProjectTruth(page);
  const committedAsset = committedTruth.project.banks[0].pads[0].asset_id;
  const committedArtifact = structuredClone(
    committedTruth.project.assets[committedAsset].artifact,
  );
  expect(committedArtifact).toEqual({
    byte_length: expect.any(Number),
    media_type: "audio/wav",
    sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
  });
  expect(committedArtifact.byte_length).toBeGreaterThan(44);

  // Once committed and rebased, the same Pad is a normal playable/recordable
  // input for the still-active session.
  await pressRecordedPad(page, "Pad A1 — assigned", "KeyQ");
  await page.getByRole("button", {name: "Stop"}).click();
  await expect(page.getByRole("status").filter({hasText: "stopped"}))
    .toBeVisible({timeout: 30_000});

  const evidence = await report(page);
  expect(evidence.sequence.semantic_state).toBe("stopped");
  expect(evidence.sequence.project_revision)
    .toBe(evidence.sequence.expected_revision);
  expect(evidence.sequence.pending_event_count).toBe(0);

  await page.reload();
  await expect(page.getByRole("button", {name: "Open Project 00000000"}))
    .toBeVisible({timeout: 60_000});
  await page.getByRole("button", {name: "Open Project 00000000"}).click();
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  const persisted = await inspectProjectTruth(page);

  // Prove the full committed artifact identity survives the actual
  // close/reload/reopen boundary before checking the known shared publication
  // assertions below.
  const assignedAsset = persisted.project.banks[0].pads[0].asset_id;
  expect(assignedAsset).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
  expect(assignedAsset).toBe(committedAsset);
  expect(persisted.project.assets[assignedAsset]).toEqual({
    artifact: committedArtifact,
  });

  const expectedFinalRevision = initialTruth.project_revision + 2;
  expect(persisted.project_revision).toBe(expectedFinalRevision);
  expect(persisted.project.revision).toBe(expectedFinalRevision);

  const persistedEvents = persisted.project.patterns[patternId].events;
  expect(persistedEvents).toHaveLength(initialEvents.length + 2);
  const addedEvents = structuredClone(persistedEvents);
  for (const initialEvent of initialEvents) {
    const exact = JSON.stringify(initialEvent);
    const index = addedEvents.findIndex((event) => JSON.stringify(event) === exact);
    expect(index).toBeGreaterThanOrEqual(0);
    addedEvents.splice(index, 1);
  }
  expect(addedEvents).toHaveLength(2);
  expect(addedEvents.map(({slot}) => slot)).toEqual([
    {bank: 0, pad: 1},
    {bank: 0, pad: 0},
  ]);
  expect(addedEvents.every((event) =>
    Object.keys(event).sort().join(",") ===
      "duration_tick,onset_tick,slot,velocity" &&
    event.duration_tick > 0 && event.velocity > 0)).toBe(true);

  await page.getByRole("button", {name: "Sample"}).click();
  await expect(page.getByRole("button", {name: "Pad A1 — assigned"}))
    .toBeVisible({timeout: 30_000});
});

test("uses queried Bank quota instead of the retired per-Pad capture cap", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(600_000);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);

  await selectPadWithoutPress(page, "Pad A1 — empty");
  // Task #346 removes the old five-second per-Pad commit cap. Record past that
  // boundary and prove the entire buffered take remains selectable while the
  // queried Bank/Project quota is the only commit ceiling.
  const panel = await recordAtLeast(page, "Pad A1", CAPTURE_FIXTURE_SECONDS * 3);
  await panel.getByRole("button", {name: "Stop"}).click();

  const length = panel.getByRole("slider", {name: "Pad A1 Selection length"});
  const maximum = Number(await length.getAttribute("max"));
  expect(maximum).toBeGreaterThan(240_000);
  expect(Number(await length.inputValue())).toBe(maximum);
});

test("blur during recording stops capture and keeps the buffer", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(600_000);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);

  await selectPadWithoutPress(page, "Pad A1 — empty");
  const panel = await recordAtLeast(page, "Pad A1", 1);
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));

  // S8B-D5: the interruption stops capture, states its reason, and the take
  // is still there to trim rather than being silently discarded.
  await expect(panel).toContainText("Recording stopped: the window lost focus.");
  await expect(panel.getByRole("slider", {name: "Pad A1 Selection length"}))
    .toBeVisible();
  await expect(panel.getByRole("button", {name: "Commit"})).toBeVisible();
});

test("a denied microphone permission is explicit and retryable", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== DENIED);
  test.setTimeout(600_000);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);

  await selectPadWithoutPress(page, "Pad A1 — empty");
  await page.getByRole("button", {name: "Record Sample"}).click();
  const panel = page.getByRole("dialog", {name: "Pad A1 Pad Capture"});
  await expect(panel).toBeVisible();
  await panel.getByRole("button", {name: "Record into Pad A1"}).click();

  // S8B-D2: denial is a visible, explained, retryable state — not a silent
  // no-op and not a dead panel.
  await expect(panel.getByRole("alert")).toBeVisible({timeout: 60_000});
  await expect(panel.getByRole("button", {name: "Record into Pad A1"})).toBeEnabled();
});

test("capture never leaks device identity or filesystem paths", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(600_000);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);

  await selectPadWithoutPress(page, "Pad A1 — empty");
  const panel = await recordAtLeast(page, "Pad A1", 1);
  await panel.getByRole("button", {name: "Stop"}).click();
  await panel.getByRole("button", {name: "Commit"}).click();
  await expect(panel.getByRole("button", {name: "Record into Pad A1"}))
    .toBeVisible({timeout: 180_000});
  await panel.getByRole("button", {name: "Close"}).click();
  await expect(panel).toBeHidden();
  await expect(page.getByRole("button", {name: "Pad A1 — assigned"}))
    .toBeVisible();

  // Only the Artifact bytes and their SHA-256 identity persist: no device
  // label, no device id, no host path (design §8).
  const text = await page.locator("body").innerText();
  expect(text).not.toContain("file://");
  expect(text).not.toContain("/Users/");
  expect(text).not.toContain("/home/");
  expect(text).not.toMatch(/deviceId|groupId|Default - |Fake Audio/i);
});
