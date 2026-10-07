import {selectedSequencePatternId} from "./fixtures/creator_navigation.mjs";
import {expect, test} from "./fixtures/refusal_diagnostics.mjs";
import {openProjectPageAfterBoot, waitForProjectReopen} from "./fixtures/creator_boot.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";

const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

// Records the app's edit and transport traffic: every pattern.events.edit
// payload and result, and every pattern.transport.request payload. The
// wrapper sits on the same transport object the session sends through, so a
// refused gesture provably never sends a command.
async function installGridProofRecorder(page) {
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
          async send(...arguments_) {
            const [request] = arguments_;
            const operation = request?.operation;
            const response = await nativeTransport.send(...arguments_);
            if (operation === "pattern.events.edit") {
              window.__patternEventsEditProof ??= [];
              window.__patternEventsEditProof.push({
                payload: structuredClone(request.payload),
                ok: response?.ok ?? null,
                error: response?.error ?? null,
                result: response?.result ?? null,
              });
            }
            if (operation === "pattern.transport.request") {
              window.__patternTransportRequests ??= [];
              window.__patternTransportRequests.push({
                payload: structuredClone(request.payload),
                ok: response?.ok ?? null,
              });
            }
            return response;
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

async function importProject(page) {
  await openProjectPageAfterBoot(page);
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(bundle);
  // Boot already shows its own Project; wait for the imported one by name.
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
}

async function reopenProject(page) {
  await page.reload();
  // The imported Project is the remembered one, so the reload reopens it.
  await waitForProjectReopen(page, "00000000", {timeout: 120_000});
  await page.getByRole("button", {name: "Project", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
}

// Play/Stop and Record are the console's physical keys, addressed by prefix
// inside the physical column as in the Sequence transport journey.
const physicalKey = (page, name) =>
  page.getByTestId("physical-controls").getByRole("button", {name});
const playStopKey = (page) => physicalKey(page, /^Play\/Stop/);
const recordKey = (page) => physicalKey(page, /^Record\b/);

async function inspectTruth(page) {
  const response = await page.evaluate(() =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "project.inspect",
      payload: {},
    }));
  expect(response.ok).toBe(true);
  return response.result.project;
}

async function inspectTransport(page, sessionId) {
  const response = await page.evaluate(async (session) =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "pattern.transport.inspect",
      payload: {session_id: session},
    }), sessionId);
  expect(response.ok).toBe(true);
  return response.result;
}

const transportStatus = (page, text) =>
  expect(page.getByRole("status").filter({
    has: page.getByTestId("creator-phase"), hasText: text,
  }))
    .toBeVisible({timeout: 30_000});

// Pattern truth orders events canonically, not by Pad; compare the set by
// (bank, pad, onset) so the fact is the events, not their storage order.
function canonical(events) {
  return [...events].sort((left, right) =>
    left.slot.bank - right.slot.bank || left.slot.pad - right.slot.pad ||
    left.onset_tick - right.onset_tick);
}

async function awaitTruthEvents(page, patternId, expected) {
  await expect.poll(async () =>
    canonical((await inspectTruth(page)).patterns[patternId].events),
    {timeout: 30_000}).toEqual(expected);
  // Truth settles before the projection refresh that re-renders the grid; a
  // follow-up gesture fired into that window would hit-test a stale model.
  // The far side of every gesture is Truth above; this only paces the UI.
  await expect(page.getByTestId("sequence-grid")
    .getByTestId("sequence-grid-note"))
    .toHaveCount(expected.length, {timeout: 30_000});
}

async function enterSequenceAndPlay(page) {
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state"))
    .toHaveText("Audio running", {timeout: 30_000});
}

// Grid geometry helpers: one bar is 3840 ticks across the lane's pixel width,
// so a snap cell's tap point is its middle pixel. The hardware shell is taller
// than the default viewport, so every measurement scrolls the target into
// view first — raw mouse coordinates are viewport coordinates. Any scrollable
// ancestor is then pinned to its left origin before measuring: a scrolled
// port would put the computed point outside the lane's visible clip.
async function resetHorizontalScroll(page, locator) {
  await locator.evaluate((element) => {
    let node = element.parentElement;
    while (node !== null) {
      if (node.scrollLeft > 0) node.scrollLeft = 0;
      node = node.parentElement;
    }
  });
}

async function laneBox(page, pad) {
  const lane = page
    .locator(`.sequence-grid-row[data-pad='${pad}'] .sequence-grid-lane`);
  await lane.scrollIntoViewIfNeeded();
  await resetHorizontalScroll(page, lane);
  const box = await lane.boundingBox();
  expect(box).not.toBeNull();
  return box;
}

const tickX = (box, tick, lengthTicks) =>
  box.x + tick / lengthTicks * box.width;

async function tapEmptyCell(page, pad, tick, lengthTicks) {
  const box = await laneBox(page, pad);
  await page.mouse.click(
    tickX(box, tick + 120, lengthTicks), box.y + box.height / 2);
}

async function dragNoteBody(page, fromTick, toTick, lengthTicks) {
  const note = page.getByTestId("sequence-grid-note").first();
  await note.scrollIntoViewIfNeeded();
  await resetHorizontalScroll(page, note);
  const row = await note.evaluateHandle((element) =>
    element.closest(".sequence-grid-lane"));
  const box = await row.asElement().boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(
    tickX(box, fromTick, lengthTicks), box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    tickX(box, toTick, lengthTicks), box.y + box.height / 2, {steps: 6});
  await page.mouse.up();
}

const overviewFact = (page, name) =>
  page.getByTestId("sequence-overview")
    .locator("dt", {hasText: name})
    .locator("xpath=following-sibling::dd[1]");

// Session history is the rail's SHIFT chord (#1770): SHIFT engages the
// Undo/Redo layer, then ← / → run it. The direction key only enables when
// that direction is available, so the enabled key is the availability gate —
// the status line prefers "Undo:" whenever the undo stack is non-empty and
// cannot speak for Redo. The history controls hold the console frame inert
// while the mutation's refresh tail runs; a gesture fired into that window
// hits the page root instead of the grid, so every Undo/Redo also waits for
// the frame to become interactive again.
// The 752×176 upper display clips its overflow and the touch workspace is a
// fixed 368 px column, so a fact pushed outside either is simply invisible —
// jsdom has no layout and `toBeVisible` ignores ancestor clipping.
async function expectSequenceLayoutFits(page) {
  const layout = await page.evaluate(() => {
    const display = document.querySelector('[data-testid="overview-display"]');
    const box = display.getBoundingClientRect();
    // Sequence keeps the phase and Project facts for assistive technology
    // only (visually hidden); every drawn fact, the status line and the
    // eight track rows must fit the display.
    const clipped = [...display.querySelectorAll([
      "dt", "dd", ".sequence-overview-status", ".sequence-overview-position",
      ".overview-swing", "[data-testid='sequence-pattern-overview']",
    ].join(", "))]
      .filter((element) => element.closest(".visually-hidden") === null)
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 &&
          (rect.bottom > box.bottom + 0.5 || rect.right > box.right + 0.5);
      })
      .map((element) => element.textContent.trim());
    const touch = document.querySelector('[data-testid="touch-workspace"]');
    return {clipped, touchOverflow: touch.scrollWidth - touch.clientWidth};
  });
  expect(layout.clipped, "every overview fact sits inside the upper display").toEqual([]);
  expect(layout.touchOverflow, "the touch workspace never scrolls sideways")
    .toBeLessThanOrEqual(0);
}

async function awaitConsoleInteractive(page) {
  await page.waitForFunction(() =>
    document.querySelector(".creator-console-frame")?.inert !== true,
    {timeout: 30_000});
}

async function shiftAndPress(page, name) {
  await page.getByRole("button", {name: "SHIFT — engage the Undo/Redo layer"})
    .click();
  const key = page.getByRole("button", {name, exact: true});
  await expect(key).toBeEnabled({timeout: 30_000});
  await key.click();
  await awaitConsoleInteractive(page);
}

async function undo(page) {
  await shiftAndPress(page, "Undo — SHIFT + ←");
}

async function redo(page) {
  await shiftAndPress(page, "Redo — SHIFT + →");
}

test("grid gestures edit Truth one command at a time, with Undo/Redo, refusal while recording, in-place playback swaps and reopen", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(360_000);
  await installGridProofRecorder(page);
  await page.goto("/index.html");
  await importProject(page);
  const baseline = await inspectTruth(page);
  await enterSequenceAndPlay(page);
  const patternId = await selectedSequencePatternId(page);
  const bars = baseline.patterns[patternId].bars;
  const lengthTicks = bars * 3840;
  expect(baseline.patterns[patternId].events).toHaveLength(0);
  const event = (pad, onset, duration, velocity) => ({
    slot: {bank: 0, pad},
    onset_tick: onset,
    duration_tick: duration,
    velocity,
  });

  // Leg 1+2 — every gesture lands exactly in Truth, and Undo/Redo restore it.
  // Add: a tap on an empty cell adds one snapped note at the grid default.
  await tapEmptyCell(page, 2, 480, lengthTicks);
  await awaitTruthEvents(page, patternId, [event(2, 480, 240, 100)]);
  await undo(page);
  await awaitTruthEvents(page, patternId, []);
  await redo(page);
  await awaitTruthEvents(page, patternId, [event(2, 480, 240, 100)]);

  // Move: dragging the note's body moves it, snapped to the grid.
  await dragNoteBody(page, 600, 1080, lengthTicks);
  await awaitTruthEvents(page, patternId, [event(2, 960, 240, 100)]);
  await undo(page);
  await awaitTruthEvents(page, patternId, [event(2, 480, 240, 100)]);
  await redo(page);
  await awaitTruthEvents(page, patternId, [event(2, 960, 240, 100)]);

  // Resize: dragging the note's end changes its length.
  {
    const box = await laneBox(page, 2);
    const handle = page.getByTestId("sequence-grid-note").first()
      .getByTestId("sequence-grid-note-end");
    const handleBox = await handle.boundingBox();
    expect(handleBox).not.toBeNull();
    await page.mouse.move(
      handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(tickX(box, 1920, lengthTicks),
      handleBox.y + handleBox.height / 2, {steps: 6});
    await page.mouse.up();
  }
  await awaitTruthEvents(page, patternId, [event(2, 960, 960, 100)]);
  await undo(page);
  await awaitTruthEvents(page, patternId, [event(2, 960, 240, 100)]);
  await redo(page);
  await awaitTruthEvents(page, patternId, [event(2, 960, 960, 100)]);

  // Velocity: a vertical drag in VEL mode sets velocity; a later note takes
  // the last velocity the grid set.
  await page.getByRole("button", {name: "Velocity mode"}).click();
  {
    const box = await laneBox(page, 2);
    await page.mouse.move(tickX(box, 1200, lengthTicks), box.y + 3);
    await page.mouse.down();
    await page.mouse.move(tickX(box, 1200, lengthTicks),
      box.y + box.height / 2, {steps: 4});
    await page.mouse.up();
  }
  await page.getByRole("button", {name: "Note mode"}).click();
  await awaitTruthEvents(page, patternId, [event(2, 960, 960, 64)]);
  await undo(page);
  await awaitTruthEvents(page, patternId, [event(2, 960, 960, 100)]);
  await redo(page);
  await awaitTruthEvents(page, patternId, [event(2, 960, 960, 64)]);

  await tapEmptyCell(page, 3, 1920, lengthTicks);
  await awaitTruthEvents(page, patternId, [
    event(2, 960, 960, 64), event(3, 1920, 240, 64),
  ]);

  // Box-select, then batch delete as one command.
  {
    const from = await laneBox(page, 1);
    const to = await laneBox(page, 4);
    await page.mouse.move(tickX(from, 500, lengthTicks), from.y + 2);
    await page.mouse.down();
    await page.mouse.move(tickX(to, 2100, lengthTicks), to.y + to.height / 2,
      {steps: 8});
    await page.mouse.up();
  }
  await expect(overviewFact(page, "Selected")).toHaveText("2", {timeout: 30_000});
  await expectSequenceLayoutFits(page);
  const selection = page.getByRole("group", {name: "Note selection"});
  await expect(selection).toContainText("2 selected");
  await selection.getByRole("button", {name: "Delete"}).click();
  await awaitTruthEvents(page, patternId, []);
  await undo(page);
  await awaitTruthEvents(page, patternId, [
    event(2, 960, 960, 64), event(3, 1920, 240, 64),
  ]);
  await redo(page);
  await awaitTruthEvents(page, patternId, []);

  // Batch move: the box-selected pair moves by one rigid snapped delta.
  await undo(page);
  await awaitTruthEvents(page, patternId, [
    event(2, 960, 960, 64), event(3, 1920, 240, 64),
  ]);
  {
    const from = await laneBox(page, 1);
    const to = await laneBox(page, 4);
    await page.mouse.move(tickX(from, 500, lengthTicks), from.y + 2);
    await page.mouse.down();
    await page.mouse.move(tickX(to, 2100, lengthTicks), to.y + to.height / 2,
      {steps: 8});
    await page.mouse.up();
  }
  await expect(selection).toContainText("2 selected", {timeout: 30_000});
  await dragNoteBody(page, 1100, 1580, lengthTicks);
  await awaitTruthEvents(page, patternId, [
    event(2, 1440, 960, 64), event(3, 2400, 240, 64),
  ]);
  await undo(page);
  await awaitTruthEvents(page, patternId, [
    event(2, 960, 960, 64), event(3, 1920, 240, 64),
  ]);
  await redo(page);
  await awaitTruthEvents(page, patternId, [
    event(2, 1440, 960, 64), event(3, 2400, 240, 64),
  ]);
  const edited = await inspectTruth(page);

  // Leg 3 — recording refuses editing: the grid names why, no command leaves,
  // and Truth stays exactly as committed.
  await recordKey(page).click();
  await transportStatus(page, "recording");
  await expect(page.getByTestId("sequence-grid"))
    .toHaveAttribute("data-editing-disabled", "true");
  await expect(page.getByText("Recording — stop recording to edit the grid."))
    .toBeVisible();
  const editsBeforeRecording = await page.evaluate(() =>
    (window.__patternEventsEditProof ?? []).length);
  await tapEmptyCell(page, 6, 480, lengthTicks);
  await page.waitForTimeout(500);
  expect(await page.evaluate(() =>
    (window.__patternEventsEditProof ?? []).length)).toBe(editsBeforeRecording);
  expect(canonical((await inspectTruth(page)).patterns[patternId].events))
    .toEqual(canonical(edited.patterns[patternId].events));
  await recordKey(page).click();
  await transportStatus(page, "playing");

  // Leg 4 — an edit while playing swaps in place without restarting playback:
  // the response reports the live publication, the transport's origin frame
  // (and so the play position) never changes, and the edit is in Truth.
  const requests = await page.evaluate(() => window.__patternTransportRequests ?? []);
  const sessionId = requests[0].payload.session_id;
  const before = await inspectTransport(page, sessionId);
  expect(before.playing).toBe(true);
  await tapEmptyCell(page, 5, 0, lengthTicks);
  await expect.poll(async () =>
    (await inspectTruth(page)).patterns[patternId].events.length,
    {timeout: 30_000}).toBe(3);
  const edits = await page.evaluate(() => window.__patternEventsEditProof ?? []);
  const liveEdit = edits.at(-1);
  expect(liveEdit.ok).toBe(true);
  expect(liveEdit.result.publication).toBe("live");
  const after = await inspectTransport(page, sessionId);
  expect(after.playing).toBe(true);
  expect(after.origin_frame).toBe(before.origin_frame);
  await expect(page.getByText("applies from next bar")).toHaveCount(0);
  await playStopKey(page).click();
  await transportStatus(page, "stopped");
  const final = await inspectTruth(page);

  // Leg 5 — reopen: identical Truth and an empty history.
  await reopenProject(page);
  const reopened = await inspectTruth(page);
  expect(reopened.revision).toBe(final.revision);
  expect(reopened.patterns[patternId].events)
    .toEqual(final.patterns[patternId].events);
  await expect(page.getByRole("button", {name: "Undo — SHIFT + ←", exact: true}))
    .toBeDisabled();
  await expect(page.getByTestId("authoring-history-status"))
    .toContainText("No changes in this session");
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  await expect(page.getByTestId("sequence-grid")
    .getByTestId("sequence-grid-note"))
    .toHaveCount(3, {timeout: 30_000});
});
