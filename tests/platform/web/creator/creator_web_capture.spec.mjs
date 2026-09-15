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

async function report(page, options = {}) {
  const downloadPromise = page.waitForEvent("download");
  if (options.force === true) {
    await page.locator(".status-actions button")
      .filter({hasText: "Export report"})
      .evaluate((element) => element.click());
  } else {
    await page.getByRole("button", {name: "Export report"}).click();
  }
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

async function inspectTransportProjection(page) {
  const response = await page.evaluate(() =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "host.status",
      payload: {},
    }));
  expect(response.ok).toBe(true);
  return response.result.pattern_transport;
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
  await installProjectInspectProbe(page);
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
  const start = panel.getByRole("slider", {name: /^Pad A1 Start —/});
  const end = panel.getByRole("slider", {name: /^Pad A1 End —/});
  await expect(start).toBeEnabled();
  await expect(end).toBeEnabled();
  const initialStart = Number(await start.inputValue());
  const initialEnd = Number(await end.inputValue());
  expect(initialStart).toBe(0);
  expect(initialEnd).toBeGreaterThan(1);

  const waveform = panel.locator("[data-capture-trim-waveform]");
  const waveformBox = await waveform.boundingBox();
  expect(waveformBox).not.toBeNull();
  const startGrip = panel.locator("[data-capture-grip-zone=start]");
  const endGrip = panel.locator("[data-capture-grip-zone=end]");
  await expect(panel.locator("[data-capture-grip=start]")).toBeVisible();
  await expect(panel.locator("[data-capture-grip=end]")).toBeVisible();

  const startGripBox = await startGrip.boundingBox();
  expect(startGripBox).not.toBeNull();
  await page.mouse.move(
    startGripBox.x + startGripBox.width / 2,
    startGripBox.y + startGripBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    waveformBox.x + waveformBox.width * 0.25,
    waveformBox.y + waveformBox.height / 2,
  );
  await page.mouse.up();
  const movedStart = Number(await start.inputValue());
  expect(movedStart).toBeGreaterThan(initialStart);
  expect(Number(await end.inputValue())).toBe(initialEnd);

  const endGripBox = await endGrip.boundingBox();
  expect(endGripBox).not.toBeNull();
  await page.mouse.move(
    endGripBox.x + endGripBox.width / 2,
    endGripBox.y + endGripBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    waveformBox.x + waveformBox.width * 0.75,
    waveformBox.y + waveformBox.height / 2,
  );
  await page.mouse.up();
  const movedEnd = Number(await end.inputValue());
  expect(movedEnd).toBeLessThan(initialEnd);
  expect(movedEnd).toBeGreaterThan(movedStart);

  // The middle is deliberately inert: it must not jump either endpoint.
  await waveform.click({position: {
    x: waveformBox.width / 2,
    y: waveformBox.height / 2,
  }});
  expect(Number(await start.inputValue())).toBe(movedStart);
  expect(Number(await end.inputValue())).toBe(movedEnd);
  await expect(panel.getByLabel("Pad A1 Start value")).toBeVisible();
  await expect(panel.getByLabel("Pad A1 End value")).toBeVisible();
  await expect(panel.getByLabel("Pad A1 Duration")).toBeVisible();

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
  const truth = await inspectProjectTruth(page);
  const assignedAsset = truth.project.banks[0].pads[0].asset_id;
  const selectedFrames = movedEnd - movedStart;
  // Chromium exposes the deterministic mono fake-capture file to the
  // AudioWorklet as a stereo MediaStream. Assert that far-side observation
  // before using the resulting two-channel PCM width in the artifact check.
  await expect(page.locator(".selected-sample"))
    .toContainText(`48 kHz · Stereo · ${selectedFrames.toLocaleString("en-US")} frames`);
  expect(truth.project.assets[assignedAsset].artifact.byte_length)
    .toBe(44 + selectedFrames * 2 * 2);
  await expectProjectRevision(page, 47);
});

// Boundary: this journey dispatches a synthetic `blur`, which exercises the
// panel's own stop path but leaves the AudioContext running. A real macOS
// Safari focus loss also interrupts the context, so the Runtime reports audio
// recovery in the same moment — and that second half is what discarded the
// take in #738 while this journey stayed green on `1.0.41.0` and `1.0.42.0`.
// Driving recovery needs a Runtime state seam that must not exist in the
// packaged app, so the recovery half is gated by
// `apps/creator-web/test/workspace_shell.test.tsx`, "audio recovery keeps an
// open capture panel instead of discarding it". Neither gate replaces the
// physical #244 rerun.
test("ordinary Sample focus loss keeps the retained trim dialog visible", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(600_000);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);
  await selectPadWithoutPress(page, "Pad A1 — empty");
  const panel = await recordAtLeast(page, "Pad A1", 1);

  await page.evaluate(() => window.dispatchEvent(new Event("blur")));

  await expect(panel).toContainText("Recording stopped: the window lost focus.");
  await expect(panel.getByRole("img", {name: "Pad A1 capture waveform"})).toBeVisible();
  await expect(panel.getByRole("slider", {name: /^Pad A1 Start —/})).toBeVisible();
  await expect(panel.getByRole("slider", {name: /^Pad A1 End —/})).toBeVisible();
  await expect(panel.getByRole("button", {name: "Commit"})).toBeVisible();
  await expect(panel.getByRole("button", {name: "Discard"})).toBeVisible();
  await expect(panel.getByRole("button", {name: "Close"})).toBeVisible();
  await expect(page.locator(".sample-overlay-host")).toHaveCount(0);

  const evidence = await report(page, {force: true});
  expect(evidence.sequence.semantic_state).toBe("stopped");
  expect(evidence.sequence.session_id).toBeNull();

  await panel.getByRole("button", {name: "Discard"}).click();
  await expect(panel.getByRole("button", {name: "Record into Pad A1"})).toBeVisible();
});

test("armed Pad capture commit is guarded by the open transport journal and never stops playback", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  // Two full capture cycles (the refused take and the committed replacement)
  // plus two Record cycles: the budget grows with the journey, not to hide a
  // hang.
  test.setTimeout(900_000);
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
  // stop gesture. This event must survive the Capture commit boundary.
  await pressRecordedPad(page, "Pad A2 — assigned", "KeyW");

  // The armed Pad stops only its capture. The global Pattern transport keeps
  // playing beneath the trim overlay and the armed hit itself is not recorded.
  await page.keyboard.press("KeyQ");
  await expect(panel.getByRole("slider", {name: /^Pad A1 End —/}))
    .toBeVisible({timeout: 30_000});

  // While the transport journal is open, the Sample-class commit keeps the
  // legacy busy guard (#1363): the refusal is honest, the take is retained,
  // and the panel keeps its controls.
  await panel.getByRole("button", {name: "Commit"}).click();
  await expect(panel.getByRole("alert"))
    .toContainText("Sample operation failed", {timeout: 30_000});
  await expect(panel.getByRole("button", {name: "Commit"})).toBeVisible();
  await expect(panel.getByRole("slider", {name: /^Pad A1 End —/}))
    .toBeVisible();

  // The take cannot commit while the journal is open; Discard is the explicit
  // user escape, and Record-off then settles the journal without stopping
  // playback.
  await panel.getByRole("button", {name: "Discard"}).click();
  await expect(page.getByRole("button", {name: "Pad A1 — empty"}))
    .toBeVisible({timeout: 30_000});
  await page.getByRole("button", {name: "Record off", exact: true}).click();
  await expect(page.getByRole("status").filter({hasText: "playing"}))
    .toBeVisible({timeout: 30_000});

  // The replacement take commits at the legal point: no open journal, and
  // playback never stopped. Sample mode mounts no transport widget, so the
  // continuity assertion reads the Runtime's own projection.
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  const whileSampling = await inspectTransportProjection(page);
  expect(whileSampling).toMatchObject({engaged: true, playing: true});
  await selectPadWithoutPress(page, "Pad A1 — empty");
  const replacement = await recordAtLeast(page, "Pad A1", 1);
  await replacement.getByRole("button", {name: "Stop"}).click();
  await expect(replacement.getByRole("slider", {name: /^Pad A1 End —/}))
    .toBeVisible({timeout: 30_000});
  await replacement.getByRole("button", {name: "Commit"}).click();
  // In Sample mode the panel intentionally stays open after a commit and
  // returns to its idle state; while it is open its modal hides the Pad grid
  // from the accessibility tree, so Close it (the take is already committed)
  // before reading the grid.
  await expect(replacement)
    .toContainText("Ready to record into Pad A1", {timeout: 180_000});
  await replacement.getByRole("button", {name: "Close"}).click();
  await expect(replacement).toBeHidden({timeout: 30_000});
  await expect(page.getByRole("button", {name: "Pad A1 — assigned"}))
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
  // The Pattern kept playing through the commit.
  const afterCommit = await inspectTransportProjection(page);
  expect(afterCommit).toMatchObject({engaged: true, playing: true});

  // The transport still plays; back in Sequence mode, a fresh Record makes
  // the committed Pad ordinary recordable input for the same Pattern.
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sequence"})).toBeVisible();
  await page.getByRole("button", {name: "Record", exact: true}).click();
  await expect(page.getByRole("status").filter({hasText: "recording"}))
    .toBeVisible({timeout: 30_000});
  await pressRecordedPad(page, "Pad A1 — assigned", "KeyQ");
  await page.getByRole("button", {name: "Record off", exact: true}).click();
  await expect(page.getByRole("status").filter({hasText: "playing"}))
    .toBeVisible({timeout: 30_000});
  await page.getByRole("button", {name: "Stop", exact: true}).click();
  await expect(page.getByRole("status").filter({hasText: "stopped"}))
    .toBeVisible({timeout: 30_000});

  // The report's revision pair settles once the Stop's authority refresh has
  // landed; the status bar's Rev is that refresh's far side.
  const settledTruth = await inspectProjectTruth(page);
  await expect(page.locator(".status-facts")).toContainText(
    `Rev${settledTruth.project_revision}`, {timeout: 30_000});

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
    lineage: null,
  });

  const expectedFinalRevision = initialTruth.project_revision + 3;
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
  // Capture trim/commit can cross the loop boundary. Persisted Pattern order
  // is canonical onset-first, so assert that order independently from the two
  // exact Pad identities recorded on opposite sides of the Capture commit.
  expect(addedEvents.map(({slot}) => slot).sort((left, right) =>
    left.pad - right.pad)).toEqual([
    {bank: 0, pad: 0},
    {bank: 0, pad: 1},
  ]);
  expect(addedEvents.map(({onset_tick: onsetTick}) => onsetTick)).toEqual(
    addedEvents.map(({onset_tick: onsetTick}) => onsetTick)
      .sort((left, right) => left - right),
  );
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

  const end = panel.getByRole("slider", {name: /^Pad A1 End —/});
  const maximum = Number(await end.getAttribute("max"));
  expect(maximum).toBeGreaterThan(240_000);
  expect(Number(await end.inputValue())).toBe(maximum);
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
  await expect(panel.getByRole("slider", {name: /^Pad A1 End —/}))
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
