import {showSampleDetails, showSamplePage} from "./fixtures/creator_navigation.mjs";
import {clickCreatorSystemAction, selectedSequencePatternId} from "./fixtures/creator_navigation.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {readFile, writeFile} from "node:fs/promises";

import {expect, test} from "./fixtures/refusal_diagnostics.mjs";

import {CAPTURE_FIXTURE_SAMPLE_RATE, CAPTURE_FIXTURE_SECONDS} from "./fixtures/make_capture_fixture.mjs";
import {openProjectPageAfterBoot, waitForProjectReopen} from "./fixtures/creator_boot.mjs";

// Play/Stop and Record are the console's physical keys. Their accessible
// names carry their state ("Play/Stop — Pattern is playing", "Record — stop
// recording …"), so they are addressed by prefix inside the physical column,
// which also keeps "Record Sample" and "Record Performance" out of reach.
const physicalKey = (page, name) =>
  page.getByTestId("physical-controls").getByRole("button", {name});
const playStopKey = (page) => physicalKey(page, /^Play\/Stop/);
const recordKey = (page) => physicalKey(page, /^Record\b/);

const sampleBundle = process.env.LMDJ_CREATOR_WEB_SAMPLE_BUNDLE;
const GRANTED = "creator-capture-chromium";
const DENIED = "creator-capture-denied-chromium";

// Read the revision from the exported report, the same way the Sample Editor
// spec does: System's persistent .creator-details-facts carries Rev in every mode, so a DOM probe
// cannot verify a commit made from the Sample surface.
async function expectProjectRevision(page, expectedRevision) {
  const downloadPromise = page.waitForEvent("download");
  await clickCreatorSystemAction(page, "Export report");
  const report = JSON.parse(await readFile(await (await downloadPromise).path(), "utf8"));
  expect(report.sample.project_revision).toBe(expectedRevision);
}

async function report(page, options = {}) {
  const downloadPromise = page.waitForEvent("download");
  if (options.force === true) {
    // While the capture dialog is modal the rest of the shell is inert, so a
    // role query cannot see the button; a CSS locator still can, and a
    // programmatic click is exactly what `force` means here.
    // System is entered from the brand mark on the physical column.
    await page.getByTestId("physical-controls").locator("button.physical-brand")
      .evaluate(element => element.click());
    await page.getByTestId("touch-workspace").locator("button")
      .filter({hasText: "Export report"})
      .evaluate((element) => element.click());
    await page.getByTestId("touch-workspace").locator("button").filter({hasText: "Back to music"})
      .evaluate(element => element.click());
  } else {
    await clickCreatorSystemAction(page, "Export report");
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
            if (arguments_[0]?.operation === "pattern.transport.request") {
              window.__captureTransportSession = arguments_[0].payload.session_id;
            }
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
  // The console's Pad matrix is the trigger surface in every mode; its pads
  // append a key hint to the name, so the caller's name is matched as a prefix.
  const pad = page.getByTestId("pad-matrix").getByRole("button", {
    name: new RegExp("^" + accessibleName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  });
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
  await openProjectPageAfterBoot(page);
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(sampleBundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await expect(page.locator(".creator-details-facts"))
    .toContainText("Rev46", {timeout: 120_000});
}

async function inspectTransportProjection(page) {
  await expect.poll(() => page.evaluate(() => window.__captureTransportSession))
    .toMatch(/^[0-9a-f-]{36}$/);
  const response = await page.evaluate(() =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "pattern.transport.inspect",
      payload: {session_id: window.__captureTransportSession},
    }));
  expect(response.ok).toBe(true);
  return response.result;
}

async function enterSampleEditor(page) {
  await page.getByRole("button", {name: "Sample"}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
}

async function selectPadWithoutPress(page, label) {
  await page.getByRole("button", {name: label, exact: true}).evaluate((element) => element.click());
}

// Record until the panel reports at least `seconds` of buffered audio. The
// fixture is CAPTURE_FIXTURE_SECONDS long and Chromium loops it, so waiting on
// delivered frame count is the duration authority, independent of the timer's
// display format and without sleeping for a wall-clock duration.
async function recordAtLeast(page, padLabel, seconds) {
  await showSamplePage(page, "Pad");
  await page.getByRole("button", {name: "Record Sample"}).click();
  const panel = page.getByRole("dialog", {name: `${padLabel} Pad Capture`});
  await expect(panel).toBeVisible();
  await panel.getByRole("button", {name: `Record into ${padLabel}`}).click();
  await expect(panel.getByRole("button", {name: "Stop"}))
    .toBeVisible({timeout: 30_000});
  const waveform = panel.getByRole("img", {name: `${padLabel} capture waveform`});
  await expect.poll(async () => Number(await waveform.getAttribute("data-frame-count")),
    {timeout: 60_000},
  ).toBeGreaterThanOrEqual(Math.ceil(seconds * CAPTURE_FIXTURE_SAMPLE_RATE));
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

const captureViewports = [
  {width: 1440, height: 900}, {width: 1280, height: 720},
  {width: 1280, height: 600}, {width: 1024, height: 768},
  {width: 768, height: 600}, {width: 768, height: 1024},
];

// Playwright's setViewportSize resolves once Chromium accepts the new
// metrics, not after the page handles the resulting `resize` event. The
// console refits only in that handler (main.tsx fitStage), and the panel
// re-anchors from it (ModalDialog placement="touch-workspace"). Reading
// geometry straight after the call measured the previous viewport's layout on
// the CI hosts: batch 38776156275 recorded trim-1280x720 with the 1440x900
// panel (bottom 809.7 in a 720 px viewport), so every Commit/Discard hit point
// below y=720 missed. The same race was fixed for the Project list in #2299.
// Wait for the new inner size, then for one rendering frame: HTML's resize
// steps run before animation-frame callbacks in the same update, so the next
// measurement sees the refitted console and the re-anchored panel.
async function resizeViewport(page, viewport) {
  await page.setViewportSize(viewport);
  await page.waitForFunction(({width, height}) =>
    window.innerWidth === width && window.innerHeight === height, viewport);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => resolve())));
}

async function expectCaptureGeometry(page, panel, testInfo, name) {
  await expect.poll(() => panel.evaluate((dialog) => {
    const a = dialog.getBoundingClientRect();
    const b = document.querySelector('[data-testid="touch-workspace"]').getBoundingClientRect();
    return Math.max(...["x", "y", "width", "height"].map((key) => Math.abs(a[key] - b[key])));
  })).toBeLessThanOrEqual(1);
  const geometry = await panel.evaluate((dialog) => {
    const box = (element) => {
      const r = element.getBoundingClientRect();
      return {x: r.x, y: r.y, width: r.width, height: r.height,
        right: r.right, bottom: r.bottom};
    };
    const controls = Array.from(dialog.querySelectorAll("button")).map((button) => {
      const r = box(button);
      const points = [[0.5, 0.5], [0.05, 0.5], [0.95, 0.5], [0.5, 0.05], [0.5, 0.95]];
      return {...r, label: button.textContent.trim(), disabled: button.disabled,
        hits: points.map(([x, y]) => {
          const hit = document.elementFromPoint(r.x + r.width * x, r.y + r.height * y);
          return hit !== null && (hit === button || button.contains(hit));
        })};
    });
    const overlaps = controls.flatMap((a, index) => controls.slice(index + 1).filter((b) =>
      Math.min(a.right, b.right) - Math.max(a.x, b.x) > 0.5 &&
      Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y) > 0.5,
    ).map((b) => [a.label, b.label]));
    return {dialog: box(dialog), anchor: box(document.querySelector('[data-testid="touch-workspace"]')),
      controls, overlaps, transform: getComputedStyle(dialog).transform,
      contentOverflow: dialog.querySelector(".capture-panel-content").scrollWidth -
        dialog.querySelector(".capture-panel-content").clientWidth,
      documentOverflow: document.documentElement.scrollWidth - innerWidth};
  });
  const path = testInfo.outputPath(`${name}-geometry.json`);
  await writeFile(path, JSON.stringify(geometry, null, 2));
  await testInfo.attach(`${name} geometry`, {path, contentType: "application/json"});
  const screenshot = testInfo.outputPath(`${name}.png`);
  await page.screenshot({path: screenshot});
  await testInfo.attach(name, {path: screenshot, contentType: "image/png"});
  for (const key of ["x", "y", "width", "height"]) {
    expect(Math.abs(geometry.dialog[key] - geometry.anchor[key]), key).toBeLessThanOrEqual(1);
  }
  expect(geometry.controls.length).toBeGreaterThanOrEqual(2);
  expect(geometry.overlaps).toEqual([]);
  expect(geometry.contentOverflow).toBeLessThanOrEqual(1);
  expect(geometry.documentOverflow).toBeLessThanOrEqual(0);
  for (const control of geometry.controls) {
    expect(control.width, control.label).toBeGreaterThanOrEqual(44 - 0.1);
    expect(control.height, control.label).toBeGreaterThanOrEqual(44 - 0.1);
    expect(control.hits, control.label).toEqual([true, true, true, true, true]);
  }
  await expectWithinViewport(page, panel);
}

async function expectFocusedTrimHandleGeometry(page, handle, testInfo, name) {
  await handle.focus();
  await expect(handle).toBeFocused();
  const geometry = await handle.evaluate((input) => {
    const box = (element) => {
      const r = element.getBoundingClientRect();
      return {x: r.x, y: r.y, width: r.width, height: r.height,
        right: r.right, bottom: r.bottom};
    };
    const content = input.closest(".capture-panel-content");
    return {handle: box(input), content: box(content),
      focused: document.activeElement === input,
      opacity: getComputedStyle(input).opacity,
      value: input.value,
      contentOverflow: content.scrollWidth - content.clientWidth};
  });
  const path = testInfo.outputPath(`${name}-geometry.json`);
  await writeFile(path, JSON.stringify(geometry, null, 2));
  await testInfo.attach(`${name} geometry`, {path, contentType: "application/json"});
  const screenshot = testInfo.outputPath(`${name}.png`);
  await page.screenshot({path: screenshot});
  await testInfo.attach(name, {path: screenshot, contentType: "image/png"});
  expect(geometry.focused).toBe(true);
  expect(geometry.opacity).toBe("1");
  expect(geometry.handle.width).toBeGreaterThanOrEqual(44 - 0.1);
  expect(geometry.handle.height).toBeGreaterThanOrEqual(44 - 0.1);
  expect(geometry.handle.x).toBeGreaterThanOrEqual(geometry.content.x - 0.1);
  expect(geometry.handle.y).toBeGreaterThanOrEqual(geometry.content.y - 0.1);
  expect(geometry.handle.right).toBeLessThanOrEqual(geometry.content.right + 0.1);
  expect(geometry.handle.bottom).toBeLessThanOrEqual(geometry.content.bottom + 0.1);
  expect(geometry.contentOverflow).toBeLessThanOrEqual(1);
  await expectWithinViewport(page, handle);
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

  await selectPadWithoutPress(page, "Pad A01 — empty — Key Z");
  await showSamplePage(page, "Pad");
  await page.getByRole("button", {name: "Record Sample"}).click();
  const panel = page.getByRole("dialog", {name: "Pad A01 Pad Capture"});
  await expect(panel).toBeVisible();

  // idle: the panel and its primary action are inside the viewport.
  await expectWithinViewport(page, panel);
  await expectWithinViewport(
    page, panel.getByRole("button", {name: "Record into Pad A01"}),
  );
  for (const viewport of captureViewports) {
    await resizeViewport(page, viewport);
    await expectCaptureGeometry(page, panel, testInfo, `idle-${viewport.width}x${viewport.height}`);
  }
  await resizeViewport(page, {width: 1280, height: 720});

  // recording: entering the phase must not change the outer geometry, and
  // Stop must sit inside the viewport without any scrolling.
  await panel.getByRole("button", {name: "Record into Pad A01"}).click();
  const stop = panel.getByRole("button", {name: "Stop"});
  await expect(stop).toBeVisible({timeout: 30_000});
  await expectWithinViewport(page, panel);
  await expectWithinViewport(page, stop);
  for (const viewport of captureViewports) {
    await resizeViewport(page, viewport);
    await expectCaptureGeometry(page, panel, testInfo, `recording-${viewport.width}x${viewport.height}`);
    await expect(stop).toBeFocused();
  }
  await resizeViewport(page, {width: 1280, height: 720});

  await panel.getByRole("button", {name: "Close"}).click();
  await expect(panel).toBeHidden();
});

test("records, trims and commits a capture onto an empty Pad", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(600_000);
  // The console rotates here; Capture stays upright and its original complete
  // horizontal pointer-trim/commit journey must still produce exact frames.
  await page.setViewportSize({width: 768, height: 1024});
  await installProjectInspectProbe(page);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);

  await selectPadWithoutPress(page, "Pad A01 — empty — Key Z");
  const panel = await recordAtLeast(page, "Pad A01", 1);
  await panel.getByRole("button", {name: "Stop"}).click();

  // Reaching the trim view means a non-empty buffer survived the stop
  // (S8B-D5); the growing-waveform image proves batches actually landed
  // rather than the fake device yielding silence.
  await expect(panel.getByRole("img", {name: "Pad A01 capture waveform"}))
    .toBeVisible();
  const start = panel.getByRole("slider", {name: /^Pad A01 Start —/});
  const end = panel.getByRole("slider", {name: /^Pad A01 End —/});
  await expect(start).toBeEnabled();
  await expect(end).toBeEnabled();
  await expectCaptureGeometry(page, panel, testInfo, "portrait-trim");
  const commitAction = panel.getByRole("button", {name: "Commit"});
  await expect(commitAction).toBeFocused();
  const discardAction = panel.getByRole("button", {name: "Discard"});
  await discardAction.focus();
  await page.keyboard.press("Tab");
  await expect(panel.getByRole("button", {name: "Close"})).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(discardAction).toBeFocused();

  // Both native keyboard inputs must keep their complete 44px box inside
  // the scrolling content at the unchanged full-range selection. The small
  // pointer grip zones have separate, pre-existing geometry; these assertions
  // do not claim that their pointer targets are 44px.
  const retainedSelection = {start: await start.inputValue(), end: await end.inputValue()};
  for (const viewport of captureViewports) {
    await resizeViewport(page, viewport);
    const size = `${viewport.width}x${viewport.height}`;
    await expectCaptureGeometry(page, panel, testInfo, `trim-${size}`);
    await expectFocusedTrimHandleGeometry(page, start, testInfo, `trim-start-focused-${size}`);
    await expectFocusedTrimHandleGeometry(page, end, testInfo, `trim-end-focused-${size}`);
    await expect(start).toHaveValue(retainedSelection.start);
    await expect(end).toHaveValue(retainedSelection.end);
  }
  // Restore the original portrait/focus context before every original real
  // pointer trim, inert-middle, commit, saved-waveform, frame/byte and revision leg below.
  await resizeViewport(page, {width: 768, height: 1024});
  await discardAction.focus();
  await expect(discardAction).toBeFocused();
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
  await expect(panel.getByLabel("Pad A01 Start value")).toBeVisible();
  await expect(panel.getByLabel("Pad A01 End value")).toBeVisible();
  await expect(panel.getByLabel("Pad A01 Duration")).toBeVisible();

  await panel.getByRole("button", {name: "Commit"}).click();
  // Commit returns the modal panel to idle. Close it before asserting the
  // background Project surface: native modal semantics make that surface
  // intentionally inert while the dialog remains open.
  await expect(panel.getByRole("button", {name: "Record into Pad A01"}))
    .toBeVisible({timeout: 180_000});
  // The panel reaches idle as soon as the commit returns, but the committed
  // Project projection settles later (sample pendingAction). Until then the
  // opener stays disabled after Close, and P2-D2 (2026-08-24 capture-panel
  // decision) restores focus to the opener only while it is a valid target,
  // otherwise to the first focusable element outside the backdrop. Batch
  // 38800878861 clicked Close inside that window: Record Sample was still
  // disabled and focus took the decided fallback. The sibling "Replace
  // Sample" is disabled by the same session, Project and pendingAction
  // conditions but not by the open panel, and its label proves Pad A01 is now
  // assigned. It sits behind the modal (inert and aria-hidden, hence
  // includeHidden). Once it is enabled, this leg proves the restore to the
  // opener rather than the fallback.
  await expect(page.getByRole("button", {name: "Replace Sample", exact: true, includeHidden: true}))
    .toBeEnabled({timeout: 30_000});
  await panel.getByRole("button", {name: "Close"}).click();
  await expect(panel).toBeHidden();
  await expect(page.getByRole("button", {name: "Record Sample"})).toBeFocused();
  await expect(page.getByRole("button", {name: "Pad A01 — assigned — Key Z", exact: true}))
    .toBeVisible();
  // The committed capture flows through the ordinary post-import behaviour:
  // the Pad reads assigned; Trim exposes the saved waveform after returning
  // from the Pad management page that opened capture.
  await showSamplePage(page, "Trim");
  await expect(page.getByRole("img", {name: "Pad A01 mirrored waveform"}))
    .toBeVisible({timeout: 120_000});
  const truth = await inspectProjectTruth(page);
  const assignedAsset = truth.project.banks[0].pads[0].asset_id;
  const selectedFrames = movedEnd - movedStart;
  // Chromium exposes the deterministic mono fake-capture file to the
  // AudioWorklet as a stereo MediaStream. Assert that far-side observation
  // before using the resulting two-channel PCM width in the artifact check.
  await expect(await showSampleDetails(page))
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
  await selectPadWithoutPress(page, "Pad A01 — empty — Key Z");
  const panel = await recordAtLeast(page, "Pad A01", 1);

  await page.evaluate(() => window.dispatchEvent(new Event("blur")));

  await expect(panel).toContainText("Recording stopped: the window lost focus.");
  await expect(panel.getByRole("img", {name: "Pad A01 capture waveform"})).toBeVisible();
  await expect(panel.getByRole("slider", {name: /^Pad A01 Start —/})).toBeVisible();
  await expect(panel.getByRole("slider", {name: /^Pad A01 End —/})).toBeVisible();
  await expect(panel.getByRole("button", {name: "Commit"})).toBeVisible();
  await expect(panel.getByRole("button", {name: "Discard"})).toBeVisible();
  await expect(panel.getByRole("button", {name: "Close"})).toBeVisible();
  await expect(page.locator(".sample-overlay-host")).toHaveCount(0);

  const evidence = await report(page, {force: true});
  expect(evidence.sequence.semantic_state).toBe("stopped");
  expect(evidence.sequence.session_id).toBeNull();

  await panel.getByRole("button", {name: "Discard"}).click();
  await expect(panel.getByRole("button", {name: "Record into Pad A01"})).toBeVisible();
});

test("armed Pad capture excludes the transport journal and never stops playback", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  // Two full capture cycles (the refused take and the committed replacement)
  // plus two Record cycles: the budget grows with the journey, not to hide a
  // hang.
  test.setTimeout(900_000);
  await installProjectInspectProbe(page);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  const initialTruth = await inspectProjectTruth(page);
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: 30_000,
  });
  await enterSampleEditor(page);
  await selectPadWithoutPress(page, "Pad A01 — empty — Key Z");
  const panel = await recordAtLeast(page, "Pad A01", 1);

  await panel.getByRole("button", {name: "Continue in Sequence"}).click();
  // The Sequence editor is one component in both layouts and names itself
  // "Sequence editor"; that region is the destination, whichever shell
  // mounts it.
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  // Capture and Pattern recording have exclusive owners in P1. Playback
  // remains available, while a recording attempt is refused before a journal.
  await expect(recordKey(page)).toBeDisabled();
  await playStopKey(page).click();
  await expect.poll(async () => (await inspectTransportProjection(page)).playing).toBe(true);
  const patternId = await selectedSequencePatternId(page);
  const initialEvents = structuredClone(initialTruth.project.patterns[patternId].events);
  await page.keyboard.press("KeyZ");
  await expect(panel.getByRole("slider", {name: /^Pad A01 End —/})).toBeVisible({timeout: 30_000});
  // Trimming returns the retained take to a native modal. Its background
  // controls are hidden from the accessibility tree; the actual Record
  // element must still be disabled by capture ownership, independently of
  // the dialog's inert background.
  await expect(page.getByTestId("physical-controls").getByRole("button", {
    name: /^Record\b/, includeHidden: true,
  })).toBeDisabled();
  await panel.getByRole("button", {name: "Discard"}).click();
  await expect(page.getByTestId("pad-matrix").getByRole("button", {name: /^Pad A01 — empty/}))
    .toBeVisible({timeout: 30_000});
  await expect(recordKey(page)).toBeEnabled();
  await recordKey(page).click();
  await expect(page.getByRole("status").filter({has: page.getByTestId("creator-phase"), hasText: "recording"})).toBeVisible();
  await pressRecordedPad(page, "Pad A02 — assigned — Key X", "KeyX");
  await recordKey(page).click();
  await expect.poll(async () => (await inspectTransportProjection(page)).playing).toBe(true);

  // The replacement take commits at the legal point: no open journal, and
  // playback never stopped. Sample mode mounts no transport widget, so the
  // continuity assertion reads the Runtime's own projection.
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  const whileSampling = await inspectTransportProjection(page);
  expect(whileSampling).toMatchObject({engaged: true, playing: true});
  await selectPadWithoutPress(page, "Pad A01 — empty — Key Z");
  const replacement = await recordAtLeast(page, "Pad A01", 1);
  await replacement.getByRole("button", {name: "Stop"}).click();
  await expect(replacement.getByRole("slider", {name: /^Pad A01 End —/}))
    .toBeVisible({timeout: 30_000});
  await replacement.getByRole("button", {name: "Commit"}).click();
  // In Sample mode the panel intentionally stays open after a commit and
  // returns to its idle state; while it is open its modal hides the Pad grid
  // from the accessibility tree, so Close it (the take is already committed)
  // before reading the grid.
  await expect(replacement)
    .toContainText("Ready to record into Pad A01", {timeout: 180_000});
  await replacement.getByRole("button", {name: "Close"}).click();
  await expect(replacement).toBeHidden({timeout: 30_000});
  await expect(page.getByRole("button", {name: "Pad A01 — assigned — Key Z", exact: true}))
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
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  await recordKey(page).click();
  await expect(page.getByRole("status").filter({
    has: page.getByTestId("creator-phase"), hasText: "recording",
  }))
    .toBeVisible({timeout: 30_000});
  await pressRecordedPad(page, "Pad A01 — assigned — Key Z", "KeyZ");
  await recordKey(page).click();
  await expect(page.getByRole("status").filter({
    has: page.getByTestId("creator-phase"), hasText: "playing",
  }))
    .toBeVisible({timeout: 30_000});
  await playStopKey(page).click();
  await expect(page.getByRole("status").filter({
    has: page.getByTestId("creator-phase"), hasText: "stopped",
  }))
    .toBeVisible({timeout: 30_000});

  // The report's revision pair settles once the Stop's authority refresh has
  // landed; System details' Rev is that refresh's far side.
  const settledTruth = await inspectProjectTruth(page);
  await expect(page.locator(".creator-details-facts")).toContainText(
    `Rev${settledTruth.project_revision}`, {timeout: 30_000});

  const evidence = await report(page);
  expect(evidence.sequence.semantic_state).toBe("stopped");
  expect(evidence.sequence.project_revision)
    .toBe(evidence.sequence.expected_revision);
  expect(evidence.sequence.pending_event_count).toBe(0);

  await page.reload();
  // The imported Project is remembered, so the reload reopens it by itself.
  await waitForProjectReopen(page, "00000000");
  await page.getByRole("button", {name: "Project", exact: true}).click();
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
  await expect(page.getByRole("button", {name: "Pad A01 — assigned — Key Z", exact: true}))
    .toBeVisible({timeout: 30_000});
});

test("uses queried Bank quota instead of the retired per-Pad capture cap", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(600_000);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);

  await selectPadWithoutPress(page, "Pad A01 — empty — Key Z");
  // Task #346 removes the old five-second per-Pad commit cap. Record past that
  // boundary and prove the entire buffered take remains selectable while the
  // queried Bank/Project quota is the only commit ceiling.
  const panel = await recordAtLeast(page, "Pad A01", CAPTURE_FIXTURE_SECONDS * 3);
  await panel.getByRole("button", {name: "Stop"}).click();

  const end = panel.getByRole("slider", {name: /^Pad A01 End —/});
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

  await selectPadWithoutPress(page, "Pad A01 — empty — Key Z");
  const panel = await recordAtLeast(page, "Pad A01", 1);
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));

  // S8B-D5: the interruption stops capture, states its reason, and the take
  // is still there to trim rather than being silently discarded.
  await expect(panel).toContainText("Recording stopped: the window lost focus.");
  await expect(panel.getByRole("slider", {name: /^Pad A01 End —/}))
    .toBeVisible();
  await expect(panel.getByRole("button", {name: "Commit"})).toBeVisible();
});

test("a denied microphone permission is explicit and retryable", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== DENIED);
  test.setTimeout(600_000);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);

  await selectPadWithoutPress(page, "Pad A01 — empty — Key Z");
  await showSamplePage(page, "Pad");
  await page.getByRole("button", {name: "Record Sample"}).click();
  const panel = page.getByRole("dialog", {name: "Pad A01 Pad Capture"});
  await expect(panel).toBeVisible();
  await panel.getByRole("button", {name: "Record into Pad A01"}).click();

  // S8B-D2: denial is a visible, explained, retryable state — not a silent
  // no-op and not a dead panel.
  await expect(panel.getByRole("alert")).toBeVisible({timeout: 60_000});
  // #1680: the explanation says what to do and never names the exception.
  await expect(panel.getByRole("alert")).toContainText(
    "Creator is not allowed to use the microphone. Allow microphone access for this site, then record again.");
  await expect(panel.getByRole("alert")).not.toContainText("NotAllowedError");
  await expect(panel.getByRole("button", {name: "Record into Pad A01"})).toBeEnabled();
});

test("capture never leaks device identity or filesystem paths", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(600_000);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);

  await selectPadWithoutPress(page, "Pad A01 — empty — Key Z");
  const panel = await recordAtLeast(page, "Pad A01", 1);
  await panel.getByRole("button", {name: "Stop"}).click();
  await panel.getByRole("button", {name: "Commit"}).click();
  await expect(panel.getByRole("button", {name: "Record into Pad A01"}))
    .toBeVisible({timeout: 180_000});
  await panel.getByRole("button", {name: "Close"}).click();
  await expect(panel).toBeHidden();
  await expect(page.getByRole("button", {name: "Pad A01 — assigned — Key Z", exact: true}))
    .toBeVisible();

  // Only the Artifact bytes and their SHA-256 identity persist: no device
  // label, no device id, no host path (design §8).
  const text = await page.locator("body").innerText();
  expect(text).not.toContain("file://");
  expect(text).not.toContain("/Users/");
  expect(text).not.toContain("/home/");
  expect(text).not.toMatch(/deviceId|groupId|Default - |Fake Audio/i);
});

test("empty Pad microphone press commits one Artifact on release and reopens exact bytes", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== GRANTED);
  test.setTimeout(180_000);
  await page.goto("/index.html");
  await importV1SampleProject(page);
  const before = await inspectProjectTruth(page);
  // The Pad recording source is a System setting (brand mark entry).
  await page.getByRole("button", {name: "System", exact: true}).click();
  await page.getByRole("group", {name: "Pad recording source"}).getByRole("button", {name: "Microphone", exact: true}).click();
  await page.getByRole("button", {name: "Back to music", exact: true}).click();
  const pad = page.getByRole("button", {name: /^Pad A01 — empty/});
  const status = page.getByRole("region", {name: "Pad recording"});
  await pad.focus();await page.keyboard.down("KeyZ");
  // Safari permission-query support varies. A preparation press has no take;
  // the next native press is the sole recording owner.
  if ((await status.textContent()).includes("permission")) {
    await page.keyboard.up("KeyZ");
    await expect(status).toContainText("Microphone ready");
    await pad.focus();await page.keyboard.down("KeyZ");
  }
  await expect(status).toContainText("recording");
  await expect.poll(async () => Number(/· ([\d.]+) s/.exec(await status.textContent())?.[1] ?? 0)).toBeGreaterThan(.2);
  await expect(recordKey(page)).toBeDisabled();
  await page.keyboard.up("KeyZ");
  await expect(page.getByRole("button", {name: /^Pad A01 — assigned/})).toBeVisible({timeout:120_000});
  const after = await inspectProjectTruth(page);
  expect(after.project.revision).toBe(before.project.revision + 1);
  const assetId = after.project.banks[0].pads[0].asset_id;
  const artifact = after.project.assets[assetId].artifact;
  expect(artifact).toEqual({byte_length:expect.any(Number),media_type:"audio/wav",sha256:expect.stringMatching(/^[0-9a-f]{64}$/)});
  expect(artifact.byte_length).toBeGreaterThan(44);
  await page.reload();await waitForProjectReopen(page,"00000000");
  const reopened = await inspectProjectTruth(page);
  expect(reopened.project.project_id).toBe(before.project.project_id);
  expect(reopened.project.assets[assetId].artifact).toEqual(artifact);
  expect(reopened.project.banks[0].pads[0].asset_id).toBe(assetId);
});
