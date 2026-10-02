import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {expect, test} from "./fixtures/refusal_diagnostics.mjs";
import {openProjectPageAfterBoot, waitForProjectReopen} from "./fixtures/creator_boot.mjs";

const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

// Records the app's own transport traffic: every pattern.transport.request
// payload and ticket, every snapshot.reload publication, and every
// sequence.settings.update command with its resolved pattern_publication. The wrapper sits on the same transport
// object the session sends through, so it can also drop one ticket response
// (the bridge-timeout class) while the native side still executes the
// command, or fail one settings update before the native side executes it.
async function installTransportProofRecorder(page) {
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
            if (operation === "sequence.settings.update" &&
                window.__failNextSettingsUpdate === true) {
              window.__failNextSettingsUpdate = false;
              window.__sequenceSettingsUpdateProof ??= [];
              window.__sequenceSettingsUpdateProof.push({
                payload: structuredClone(request.payload),
                ok: null,
                failed: true,
              });
              // The bridge-class failure rejects before the native side
              // executes, so Truth cannot move; the Creator surfaces the
              // error code and keeps the committed readout.
              throw Object.assign(
                new Error("sequence settings update failed"),
                {code: "HOST_TIMEOUT"},
              );
            }
            const response = await nativeTransport.send(...arguments_);
            if (operation === "sequence.settings.update") {
              window.__sequenceSettingsUpdateProof ??= [];
              window.__sequenceSettingsUpdateProof.push({
                payload: structuredClone(request.payload),
                ok: response?.ok ?? null,
                failed: false,
                patternPublication:
                  response?.result?.pattern_publication === null ||
                  response?.result?.pattern_publication === undefined
                    ? null
                    : structuredClone(response.result.pattern_publication),
              });
            }
            if (operation === "pattern.transport.request") {
              window.__patternTransportRequests ??= [];
              const entry = {
                payload: structuredClone(request.payload),
                ok: response?.ok ?? null,
                submit: response?.result?.submit ?? null,
                error: response?.error ?? null,
                dropped: false,
              };
              window.__patternTransportRequests.push(entry);
              if (window.__dropNextTransportTicket === true &&
                  request.payload?.intent === "record") {
                window.__dropNextTransportTicket = false;
                entry.dropped = true;
                // The native side accepted and executed the command; only the
                // ticket response is lost. The Creator must reconcile this
                // through inspection, never through a new inverse toggle.
                throw Object.assign(
                  new Error("transport ticket response dropped"),
                  {code: "HOST_TIMEOUT"},
                );
              }
            }
            if (operation === "trigger") {
              // A trigger response returns only after its admission append is
              // durable, so the journeys gate Record-off on these — never on a
              // bare key dispatch.
              window.__patternTransportTriggerProof ??= [];
              window.__patternTransportTriggerProof.push({
                payload: structuredClone(request.payload),
                ok: response?.ok ?? null,
                status: response?.result?.status ?? null,
                accepted: response?.result?.accepted ?? null,
              });
            }
            if (operation === "snapshot.reload") {
              window.__snapshotReloadProof ??= [];
              window.__snapshotReloadProof.push({
                patternId: request.payload?.pattern_id ?? null,
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

// Play/Stop and Record are the console's physical keys. Their accessible
// names carry their state ("Play/Stop — Pattern is playing", "Record — stop
// recording …"), so they are addressed by prefix inside the physical column,
// which also keeps "Record Sample" and "Record Performance" out of reach.
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

async function transportRequests(page) {
  return page.evaluate(() => window.__patternTransportRequests ?? []);
}

// Wait until the Runtime has durably admitted `count` Pad presses. The
// trigger response is the far side of the journal append; pressing keys never
// proves admission on its own. One-shot Pads send no release operation, so
// only presses are gated here.
async function awaitAdmittedPresses(page, count) {
  const wakeAdmissions = await page.evaluate(() => window.__wakeAudioAdmissionCount ?? 0);
  await expect.poll(() => page.evaluate(() =>
    (window.__patternTransportTriggerProof ?? [])
      .filter(({payload, ok}) => ok === true && payload?.velocity !== undefined)
      .length), {timeout: 30_000}).toBe(count + wakeAdmissions);
}

async function enterSequenceAndPlay(page) {
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  // The Sequence editor is one component in both layouts and names itself
  // "Sequence editor"; that region is the destination, whichever shell
  // mounts it.
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state"))
    .toHaveText("Audio running", {timeout: 30_000});
}

const transportStatus = (page, text) =>
  expect(page.getByRole("status").filter({
    has: page.getByTestId("creator-phase"), hasText: text,
  }))
    .toBeVisible({timeout: 30_000});

test("global Pattern transport plays, overdubs, survives navigation, stops, and reopens with exact truth", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installTransportProofRecorder(page);
  await page.goto("/index.html");
  await importProject(page);
  const baseline = await inspectTruth(page);
  await enterSequenceAndPlay(page);
  const pattern = page.getByRole("combobox", {name: "Pattern"});
  const patternId = await pattern.inputValue();
  expect(baseline.patterns[patternId].events).toHaveLength(0);

  // stopped → Play: playback only, no journal.
  await playStopKey(page).click();
  await transportStatus(page, "playing");
  expect((await inspectTruth(page)).patterns[patternId].events).toHaveLength(0);
  expect((await inspectTruth(page)).revision).toBe(baseline.revision);

  // playing → Record: overdub admission of live Pad input.
  await recordKey(page).click();
  await transportStatus(page, "recording");
  await page.keyboard.press("KeyQ");
  await page.keyboard.press("KeyW");
  await awaitAdmittedPresses(page, 2);
  // Nothing is committed while recording is open.
  expect((await inspectTruth(page)).patterns[patternId].events).toHaveLength(0);

  // Record-off: durable commit, playback continues without restart.
  await recordKey(page).click();
  await transportStatus(page, "playing");
  const committed = await inspectTruth(page);
  expect(committed.revision).toBe(baseline.revision + 1);
  // Pattern truth orders events by position, not by the order the keys were
  // pressed: when the two presses straddle the loop boundary the Pad 1 event
  // sits earlier in the loop than the Pad 0 event. The fact is the set — both
  // presses committed, each to its own Pad at full velocity — so compare the
  // events by Pad, not by index (#1562).
  const committedEvents = committed.patterns[patternId].events;
  const events = [...committedEvents]
      .sort((left, right) => left.slot.pad - right.slot.pad);
  expect(events).toHaveLength(2);
  expect(events[0]).toMatchObject({slot: {bank: 0, pad: 0}, velocity: 100});
  expect(events[1]).toMatchObject({slot: {bank: 0, pad: 1}, velocity: 100});

  // Navigation is presentation-only: entering Sample must not touch the
  // transport, and playback continues underneath.
  const requestsBeforeNavigation = await transportRequests(page);
  const sessionId = requestsBeforeNavigation[0].payload.session_id;
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  expect(await inspectTransport(page, sessionId))
    .toMatchObject({engaged: true, playing: true, recording: false});
  expect(await transportRequests(page)).toHaveLength(requestsBeforeNavigation.length);
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await transportStatus(page, "playing");

  // Play/Stop stops scheduling; the committed truth is untouched.
  await playStopKey(page).click();
  await transportStatus(page, "stopped");
  const stopped = await inspectTruth(page);
  expect(stopped.revision).toBe(baseline.revision + 1);
  // Stop leaves truth untouched: compare it with the committed truth in its
  // own position order, not with the Pad-sorted copy above.
  expect(stopped.patterns[patternId].events).toEqual(committedEvents);

  // Reopen: identical bytes, revision and events; one session identity drove
  // the whole journey. The proof lives on the window, so read it before the
  // reload wipes it.
  const requests = await transportRequests(page);
  expect(requests.map(({payload}) => payload.intent))
    .toEqual(["play_stop", "record", "record", "play_stop"]);
  expect(requests.map(({payload}) => payload.expected_epoch)).toEqual([1, 2, 3, 4]);
  expect(new Set(requests.map(({payload}) => payload.session_id)).size).toBe(1);
  expect(new Set(requests.map(({payload}) => payload.project_id)).size).toBe(1);
  expect(requests.every(({ok, dropped}) => ok === true && dropped === false))
    .toBe(true);

  await reopenProject(page);
  const reopened = await inspectTruth(page);
  expect(reopened.revision).toBe(baseline.revision + 1);
  expect(reopened.patterns[patternId].events).toEqual(committedEvents);
});

test("Record-off ticket loss reconciles the same command; Pattern switch and stopped Record survive reopen", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installTransportProofRecorder(page);
  await page.goto("/index.html");
  await importProject(page);
  const imported = await inspectTruth(page);
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  const pattern = page.getByRole("combobox", {name: "Pattern"});
  const patternId = await pattern.inputValue();

  // Author a second Pattern and reselect the first BEFORE audio starts: a
  // quiescent Engine applies each publication immediately, so the later
  // transport commands never race a scheduled publication.
  // U2 turned Bars into a segmented control shared by both layouts, so the
  // bar count is chosen by pressing its segment rather than selecting an
  // option. The pressed state is the same committed choice selectOption made.
  const bars = page.getByRole("group", {name: "Bars"})
    .getByRole("button", {name: "2 bars"});
  await bars.click();
  await expect(bars).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", {name: "Create Pattern"}).click();
  await expect(pattern.locator("option")).toHaveCount(2, {timeout: 30_000});
  const alternatePattern = await pattern.locator("option").nth(1)
    .getAttribute("value");
  expect(alternatePattern).not.toBeNull();
  await pattern.selectOption(patternId);
  await expect(pattern).toHaveValue(patternId);
  const authored = await inspectTruth(page);
  expect(authored.revision).toBe(imported.revision + 1);

  // The first Record click must wake audio and start this same intent once.
  await expect(page.getByRole("button", {name: "Activate audio"})).toHaveCount(0);
  await recordKey(page).click();
  await expect(page.getByTestId("audio-state"))
    .toHaveText("Audio running", {timeout: 30_000});
  await transportStatus(page, "recording");
  await page.keyboard.press("KeyQ");
  await awaitAdmittedPresses(page, 1);

  // The Record-off ticket response is lost after the native side accepted
  // the command. The Creator shows the failure, keeps the command identity
  // and reconciles by inspection; the commit lands exactly once.
  const beforeLoss = await transportRequests(page);
  await page.evaluate(() => {
    window.__dropNextTransportTicket = true;
  });
  await recordKey(page).click();
  await transportStatus(page, "playing");
  const afterReconcile = await transportRequests(page);
  const droppedIndex = afterReconcile.findIndex((entry) => entry.dropped);
  expect(droppedIndex).toBeGreaterThanOrEqual(beforeLoss.length - 1);
  const droppedCommand = afterReconcile[droppedIndex].payload;
  // Every later transport request reconciles the retained command verbatim —
  // never a new inverse toggle.
  for (const entry of afterReconcile.slice(droppedIndex + 1)) {
    expect(entry.payload).toEqual(droppedCommand);
    expect(entry.submit).toBe("replayed");
  }
  const committed = await inspectTruth(page);
  expect(committed.revision).toBe(authored.revision + 1);
  expect(committed.patterns[patternId].events).toHaveLength(1);
  expect(committed.patterns[patternId].events[0])
    .toMatchObject({slot: {bank: 0, pad: 0}, velocity: 100});

  // A Pattern switch while playing is honestly refused: the Runtime keeps the
  // live engagement on the playing Pattern and the selection stays put.
  const sessionId = afterReconcile[0].payload.session_id;
  await expect.poll(async () =>
    (await inspectTransport(page, sessionId)).publication_pending,
    {timeout: 30_000}).toBe(false);
  await page.evaluate(() => {
    window.__snapshotReloadProof = [];
  });
  await pattern.selectOption(alternatePattern);
  // The refused selection is retried verbatim (same Pattern, never
  // substituted) and then surfaced as an honest error; the UI selection
  // remains the playing Pattern.
  await expect(page.getByRole("alert")).toBeVisible({timeout: 30_000});
  await expect(pattern).toHaveValue(patternId);
  const refusedReloads = await page.evaluate(() =>
    window.__snapshotReloadProof ?? []);
  expect(refusedReloads.length).toBeGreaterThanOrEqual(1);
  expect(new Set(refusedReloads.map((entry) => entry.patternId)))
    .toEqual(new Set([alternatePattern]));
  expect(refusedReloads.every((entry) => entry.ok === false)).toBe(true);
  await transportStatus(page, "playing");

  // Stop first; the stopped engagement is retired by the reload, so the
  // switch now lands and the next command re-engages against the new Pattern.
  await playStopKey(page).click();
  await transportStatus(page, "stopped");
  await page.evaluate(() => {
    window.__snapshotReloadProof = [];
  });
  await pattern.selectOption(alternatePattern);
  await expect(pattern).toHaveValue(alternatePattern);
  await expect.poll(() => page.evaluate(() =>
    (window.__snapshotReloadProof ?? []).at(-1) ?? null), {timeout: 30_000})
    .toEqual({patternId: alternatePattern, ok: true});

  // Record into the switched Pattern: stopped Record starts it from its
  // beginning, and the overdub lands in the new Pattern.
  await recordKey(page).click();
  try {
    await transportStatus(page, "recording");
  } catch (error) {
    console.log("DEBUG requests:", JSON.stringify(await transportRequests(page)));
    console.log("DEBUG alerts:", await page.locator("[role=alert]").allTextContents());
    throw error;
  }
  await page.keyboard.press("KeyW");
  await awaitAdmittedPresses(page, 2);
  await recordKey(page).click();
  await transportStatus(page, "playing");
  const overdubbed = await inspectTruth(page);
  expect(overdubbed.revision).toBe(authored.revision + 2);
  expect(overdubbed.patterns[patternId].events).toHaveLength(1);
  expect(overdubbed.patterns[alternatePattern].events).toHaveLength(1);
  expect(overdubbed.patterns[alternatePattern].events[0])
    .toMatchObject({slot: {bank: 0, pad: 1}, velocity: 100});

  await playStopKey(page).click();
  await transportStatus(page, "stopped");
  const stopped = await inspectTruth(page);
  expect(stopped.revision).toBe(authored.revision + 2);
  expect(stopped.patterns[patternId].events).toHaveLength(1);
  expect(stopped.patterns[alternatePattern].events).toHaveLength(1);

  // Grouped by command identity: Record-on, the dropped Record-off (plus its
  // same-identity replays), the switched Record-on (plus its same-identity
  // transient refusals), and two Play/Stops. The switch itself never produced
  // a transport command, and no identity ever changed payload. The proof
  // lives on the window, so read it before the reload wipes it.
  const requests = await transportRequests(page);
  const byCommand = new Map();
  for (const entry of requests) {
    const group = byCommand.get(entry.payload.command_id) ?? [];
    group.push(entry);
    byCommand.set(entry.payload.command_id, group);
  }
  const groups = [...byCommand.values()];
  expect(groups.filter((group) => group[0].payload.intent === "play_stop"))
    .toHaveLength(2);
  const recordGroups = groups.filter((group) =>
    group[0].payload.intent === "record");
  // Record-on and Record-off for each of the two Patterns.
  expect(recordGroups).toHaveLength(4);
  for (const group of groups) {
    for (const entry of group) {
      expect(entry.payload).toEqual(group[0].payload);
    }
  }
  // Every command identity was eventually accepted; the dropped Record-off
  // only ever replays.
  for (const group of groups) {
    expect(group.some((entry) => entry.ok === true)).toBe(true);
  }
  const droppedGroup = byCommand.get(requests[droppedIndex].payload.command_id);
  expect(droppedGroup.every((entry) =>
    entry.dropped || entry.submit === "replayed")).toBe(true);

  await reopenProject(page);
  const reopened = await inspectTruth(page);
  expect(reopened.revision).toBe(authored.revision + 2);
  expect(reopened.patterns[patternId].events)
    .toEqual(committed.patterns[patternId].events);
  expect(reopened.patterns[alternatePattern].events)
    .toEqual(overdubbed.patterns[alternatePattern].events);
});


// Owner loss: the reload kills the Runtime Worker without a completed Close,
// so the recorded admission stays unresolved. On reopen the recovery surface
// seals it as owner_lost (#1367). No terminal transfer can arrive any more, so
// Apply recovers the heard take into the Pattern (#1515), and a fresh
// recording then opens a new journal.
test("reopening after owner loss asks once and keeps the heard take", async ({page, browserName}) => {
  // #1680: the reopen prompt over the same recovery candidate the Sequence
  // list shows; Keep restores it to its original Pattern.
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installTransportProofRecorder(page);
  await page.goto("/index.html");
  await importProject(page);
  const imported = await inspectTruth(page);
  await enterSequenceAndPlay(page);
  const patternId = await page.getByRole("combobox", {name: "Pattern"}).inputValue();
  await recordKey(page).click();
  await transportStatus(page, "recording");
  await page.keyboard.down("KeyQ");
  await awaitAdmittedPresses(page, 1);

  await reopenProject(page);
  await page.keyboard.up("KeyQ");
  const prompt = page.getByRole("region", {name: "Interrupted recording"});
  await expect(prompt).toContainText("A recording stopped before it was saved (1 in Sequence)",
    {timeout: 60_000});
  const lostTruth = await inspectTruth(page);
  expect(lostTruth.revision).toBe(imported.revision);
  expect(lostTruth.patterns[patternId].events).toHaveLength(0);

  await prompt.getByRole("button", {name: "Keep recording"}).click();
  await expect(prompt).toContainText("The interrupted recording is back in this Project.",
    {timeout: 60_000});
  const kept = await inspectTruth(page);
  expect(kept.revision).toBe(imported.revision + 1);
  expect(kept.patterns[patternId].events).toHaveLength(1);
  expect(kept.patterns[patternId].events[0])
    .toMatchObject({slot: {bank: 0, pad: 0}, velocity: 100, duration_tick: 240});
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("region", {name: "Sequence recovery"})).toHaveCount(0);

  // Nothing is left to ask about, and the kept take is persisted.
  await reopenProject(page);
  expect(await inspectTruth(page)).toEqual(kept);
  const remaining = await page.evaluate(() => window.lmdjWebRuntimeHost.transport.send({
    protocol_version: 1, request_id: crypto.randomUUID(),
    operation: "sequence.recovery.list", payload: {},
  }));
  expect(remaining).toMatchObject({ok: true, result: {candidates: []}});
  await expect(page.getByRole("region", {name: "Interrupted recording"})).toHaveCount(0);
});

test("owner loss surfaces the interrupted recording and recovers the heard take", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installTransportProofRecorder(page);
  await page.goto("/index.html");
  await importProject(page);
  const imported = await inspectTruth(page);
  await enterSequenceAndPlay(page);
  const pattern = page.getByRole("combobox", {name: "Pattern"});
  const patternId = await pattern.inputValue();

  await recordKey(page).click();
  await transportStatus(page, "recording");
  // Leave the press open: owner-loss recovery finalizes an interrupted held
  // one-shot with its attack tail. A completed press/release records its real
  // duration and cannot establish this precondition.
  await page.keyboard.down("KeyQ");
  // The admission must be durable before the reload, or the recovery
  // assertion would be testing an empty journal instead of owner loss.
  await awaitAdmittedPresses(page, 1);

  await reopenProject(page);
  await page.keyboard.up("KeyQ");
  const lostTruth = await inspectTruth(page);
  // Nothing was committed: the unresolved admission never reaches truth.
  expect(lostTruth.revision).toBe(imported.revision);
  expect(lostTruth.patterns[patternId].events).toHaveLength(0);

  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  const recoveryRegion = page.getByRole("region", {name: "Sequence recovery"});
  await expect(recoveryRegion).toBeVisible({timeout: 60_000});
  await expect(recoveryRegion).toContainText("owner_lost");

  // Apply finalizes the owned one-shot press after its attack tail and
  // commits it: the take the performer heard survives owner loss (#1515).
  await recoveryRegion.getByRole("button", {name: "Recover original Pattern"})
    .click();
  await expect(page.getByRole("region", {name: "Sequence recovery"}))
    .toHaveCount(0, {timeout: 60_000});
  const appliedTruth = await inspectTruth(page);
  expect(appliedTruth.revision).toBe(imported.revision + 1);
  expect(appliedTruth.patterns[patternId].events).toHaveLength(1);
  // The one-shot press is finalized with the default 240-tick attack tail.
  expect(appliedTruth.patterns[patternId].events[0])
    .toMatchObject({slot: {bank: 0, pad: 0}, velocity: 100, duration_tick: 240});

  // A fresh recording on the same session opens a new journal and commits.
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state"))
    .toHaveText("Audio running", {timeout: 30_000});
  await recordKey(page).click();
  await transportStatus(page, "recording");
  await page.keyboard.press("KeyW");
  await awaitAdmittedPresses(page, 1);
  await recordKey(page).click();
  await transportStatus(page, "playing");
  const recovered = await inspectTruth(page);
  expect(recovered.revision).toBe(imported.revision + 2);
  expect(recovered.patterns[patternId].events).toHaveLength(2);
  expect(recovered.patterns[patternId].events)
    .toContainEqual(expect.objectContaining({slot: {bank: 0, pad: 1}, velocity: 100}));
});

// Direct Tempo/Swing controls (#1672): a drag previews locally and commits
// once on release, step buttons and TAP commit immediately, Escape cancels,
// a failed commit surfaces honestly, a playing commit activates at the next
// bar boundary, and recording locks the controls at two layers — the
// disabled UI and the control layer's HOST_STATE_INVALID.
test("direct Tempo and Swing controls commit once, cancel, fail honestly, and stay locked while recording", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installTransportProofRecorder(page);
  // TAP converts tap intervals, so the journey controls the clock it reads.
  await page.addInitScript(() => {
    window.__tapNow = null;
    const realNow = performance.now.bind(performance);
    performance.now = () => window.__tapNow ?? realNow();
  });
  await page.goto("/index.html");
  await importProject(page);
  const baseline = await inspectTruth(page);
  await enterSequenceAndPlay(page);
  const bpmFader = page.getByRole("slider", {name: "BPM"});
  const swingFader = page.getByRole("slider", {name: "Swing"});
  await expect(bpmFader).toBeVisible();
  await expect(page.getByRole("button", {name: /Apply/})).toHaveCount(0);
  const settingsUpdates = () =>
    page.evaluate(() => window.__sequenceSettingsUpdateProof ?? []);

  // Leg 1 — a drag previews locally and commits exactly once on release: one
  // settings command, one revision, Truth carries the dragged tempo.
  const direction = baseline.bpm <= 230 ? 1 : -1;
  const dragged = baseline.bpm + 10 * direction;
  await bpmFader.fill(String(dragged));
  expect((await inspectTruth(page)).bpm).toBe(baseline.bpm);
  expect(await settingsUpdates()).toHaveLength(0);
  await bpmFader.dispatchEvent("pointerup");
  await expect.poll(async () => (await inspectTruth(page)).bpm).toBe(dragged);
  let truth = await inspectTruth(page);
  expect(truth.revision).toBe(baseline.revision + 1);
  let updates = await settingsUpdates();
  expect(updates).toHaveLength(1);
  expect(updates[0]).toMatchObject({ok: true, failed: false});
  expect(updates[0].payload).toMatchObject({
    bpm: dragged,
    quantize_enabled: null,
    swing_percent: null,
  });

  // Leg 2 — a step button commits immediately: one click, one command, one
  // revision.
  const stepped = dragged + direction;
  await page.getByRole("button", {
    name: direction > 0 ? "Increase BPM" : "Decrease BPM",
  }).click();
  await expect.poll(async () => (await inspectTruth(page)).bpm).toBe(stepped);
  expect((await inspectTruth(page)).revision).toBe(baseline.revision + 2);
  updates = await settingsUpdates();
  expect(updates).toHaveLength(2);
  expect(updates[1].payload).toMatchObject({bpm: stepped});

  // Leg 3 — TAP: the first tap of a chain commits nothing; the second
  // converts the synthetic 500 ms interval to 120 BPM and commits it.
  await page.evaluate(() => {
    window.__tapNow = 1_000;
  });
  await page.getByRole("button", {name: "Tap Tempo"}).click();
  expect(await settingsUpdates()).toHaveLength(2);
  await page.evaluate(() => {
    window.__tapNow = 1_500;
  });
  await page.getByRole("button", {name: "Tap Tempo"}).click();
  await page.evaluate(() => {
    window.__tapNow = null;
  });
  await expect.poll(async () => (await inspectTruth(page)).bpm).toBe(120);
  expect((await inspectTruth(page)).revision).toBe(baseline.revision + 3);
  updates = await settingsUpdates();
  expect(updates).toHaveLength(3);
  expect(updates[2].payload).toMatchObject({bpm: 120});

  // Leg 4 — Escape cancels a Swing draft: no command, no revision, and the
  // control falls back to the committed value.
  const baseSwing = baseline.sequence_settings.swing_percent;
  const swung = baseSwing <= 65 ? baseSwing + 10 : baseSwing - 10;
  await swingFader.fill(String(swung));
  expect((await inspectTruth(page)).sequence_settings.swing_percent)
    .toBe(baseSwing);
  await swingFader.press("Escape");
  await expect(swingFader).toHaveValue(String(baseSwing));
  truth = await inspectTruth(page);
  expect(truth.sequence_settings.swing_percent).toBe(baseSwing);
  expect(truth.revision).toBe(baseline.revision + 3);
  expect(await settingsUpdates()).toHaveLength(3);

  // Leg 5 — a failed commit surfaces the failure and changes nothing:
  // Truth keeps the committed value and the readout never adopted the draft.
  // The alert speaks user language and the code is in Developer diagnostics
  // (#1680).
  await page.evaluate(() => {
    window.__failNextSettingsUpdate = true;
  });
  await page.getByRole("button", {name: "Increase Swing"}).click();
  const failure = page.getByRole("alert")
    .filter({hasText: "The audio engine stopped responding."});
  await expect(failure).toBeVisible({timeout: 30_000});
  await expect(failure).not.toContainText("HOST_TIMEOUT");
  await page.getByText(/^Developer diagnostics \(\d+\)$/).click();
  const log = page.getByRole("region", {name: "Developer diagnostics"});
  await expect(log).toContainText("Update Sequence settings");
  await expect(log).toContainText("HOST_TIMEOUT");
  await page.getByText(/^Developer diagnostics \(\d+\)$/).click();
  truth = await inspectTruth(page);
  expect(truth.sequence_settings.swing_percent).toBe(baseSwing);
  expect(truth.revision).toBe(baseline.revision + 3);
  await expect(swingFader).toHaveValue(String(baseSwing));
  updates = await settingsUpdates();
  expect(updates).toHaveLength(4);
  expect(updates[3]).toMatchObject({ok: null, failed: true});

  // Leg 6 — a playing commit republishes the current Pattern from the next
  // bar boundary: the response's pattern_publication.activation_frame sits a
  // whole number of old-tempo bars after the transport's origin_frame. The
  // engine's bar math is fixed at 48 kHz transport frames
  // (kBarTicks4x4/kTickDenominator/kTransportPpq in prepared_sample_bank).
  const playingBpm = (await inspectTruth(page)).bpm;
  await playStopKey(page).click();
  await transportStatus(page, "playing");
  const requests = await transportRequests(page);
  const sessionId = requests[0].payload.session_id;
  await expect.poll(async () =>
    (await inspectTransport(page, sessionId)).playing, {timeout: 30_000})
    .toBe(true);
  const originFrame = (await inspectTransport(page, sessionId)).origin_frame;
  expect(Number.isInteger(originFrame)).toBe(true);
  expect(originFrame).toBeGreaterThanOrEqual(0);
  const shifted = playingBpm >= 240 ? playingBpm - 1 : playingBpm + 1;
  await bpmFader.fill(String(shifted));
  await bpmFader.dispatchEvent("pointerup");
  await expect.poll(async () => (await inspectTruth(page)).bpm).toBe(shifted);
  updates = await settingsUpdates();
  expect(updates).toHaveLength(5);
  expect(updates[4].ok).toBe(true);
  const publication = updates[4].patternPublication;
  expect(publication).not.toBeNull();
  expect(Number.isInteger(publication.activation_frame)).toBe(true);
  expect(publication.activation_frame).toBeGreaterThan(originFrame);
  // One 4/4 bar at the OLD tempo: ceil(3840 * 2_880_000 / (bpm * 960)).
  const barFrames = Math.ceil(3_840 * 2_880_000 / (playingBpm * 960));
  expect((publication.activation_frame - originFrame) % barFrames).toBe(0);
  await playStopKey(page).click();
  await transportStatus(page, "stopped");

  // Leg 7 — recording locks every Tempo/Swing control and says why; the
  // control layer itself refuses a direct settings write, so the refusal
  // does not depend on the UI's pre-refusal.
  await recordKey(page).click();
  await transportStatus(page, "recording");
  await expect(bpmFader).toBeDisabled();
  await expect(swingFader).toBeDisabled();
  for (const name of [
    "Decrease BPM", "Increase BPM", "Tap Tempo",
    "Decrease Swing", "Increase Swing",
  ]) {
    await expect(page.getByRole("button", {name, exact: true})).toBeDisabled();
  }
  await expect(page.getByText("Tempo and Swing are locked while recording"))
    .toBeVisible();
  truth = await inspectTruth(page);
  const refused = await page.evaluate(async ({session, revision}) =>
    window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      operation: "sequence.settings.update",
      payload: {
        command_id: crypto.randomUUID(),
        expected_revision: revision,
        session_id: session,
        bpm: 133,
        quantize_enabled: null,
        swing_percent: null,
      },
    }), {session: sessionId, revision: truth.revision});
  expect(refused.ok).toBe(false);
  expect(refused.error?.code).toBe("HOST_STATE_INVALID");
  truth = await inspectTruth(page);
  expect(truth.bpm).toBe(shifted);
  expect(truth.revision).toBe(baseline.revision + 4);
  updates = await settingsUpdates();
  expect(updates).toHaveLength(6);
  expect(updates[5]).toMatchObject({ok: false, failed: false});
  expect(updates[5].payload).toMatchObject({bpm: 133});

  await recordKey(page).click();
  await transportStatus(page, "playing");
  await playStopKey(page).click();
  await transportStatus(page, "stopped");
});
