import {expect, test} from "./fixtures/refusal_diagnostics.mjs";

const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");

// Records the app's own transport traffic: every pattern.transport.request
// payload and ticket, and every snapshot.reload publication. The wrapper sits
// on the same transport object the session sends through, so it can also drop
// one ticket response (the bridge-timeout class) while the native side still
// executes the command.
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
            const response = await nativeTransport.send(...arguments_);
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
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {timeout: 30_000});
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(bundle);
  await expect(page.getByRole("heading", {name: /^Project /}))
    .toBeVisible({timeout: 120_000});
}

async function reopenProject(page) {
  await page.reload();
  await expect(page.getByRole("button", {name: "Open Project 00000000"}))
    .toBeVisible({timeout: 60_000});
  await page.getByRole("button", {name: "Open Project 00000000"}).click();
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
  await expect.poll(() => page.evaluate(() =>
    (window.__patternTransportTriggerProof ?? [])
      .filter(({payload, ok}) => ok === true && payload?.velocity !== undefined)
      .length), {timeout: 30_000}).toBe(count);
}

async function enterSequenceAndPlay(page) {
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  // The Sequence editor is one component in both layouts and names itself
  // "Sequence editor"; that region is the destination, whichever shell
  // mounts it.
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state"))
    .toHaveText("Audio running", {timeout: 30_000});
}

const transportStatus = (page, text) =>
  expect(page.getByRole("status").filter({hasText: text}))
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
  const events = committed.patterns[patternId].events;
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
  expect(stopped.patterns[patternId].events).toEqual(events);

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
  expect(reopened.patterns[patternId].events).toEqual(events);
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

  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state"))
    .toHaveText("Audio running", {timeout: 30_000});

  // stopped → Record: start at the Pattern beginning, playing and recording.
  await recordKey(page).click();
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
// seals it as owner_lost (#1367): Apply is honestly refused (the fence outcome
// is unknowable), Discard releases it, and a fresh recording opens a new
// journal.
test("owner loss surfaces the interrupted recording for honest refusal and discard", async ({page, browserName}) => {
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
  await page.keyboard.press("KeyQ");
  // The admission must be durable before the reload, or the recovery
  // assertion would be testing an empty journal instead of owner loss.
  await awaitAdmittedPresses(page, 1);

  await reopenProject(page);
  const lostTruth = await inspectTruth(page);
  // Nothing was committed: the unresolved admission never reaches truth.
  expect(lostTruth.revision).toBe(imported.revision);
  expect(lostTruth.patterns[patternId].events).toHaveLength(0);

  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(page.getByRole("region", {name: "Sequence editor"})).toBeVisible();
  const recoveryRegion = page.getByRole("region", {name: "Sequence recovery"});
  await expect(recoveryRegion).toBeVisible({timeout: 60_000});
  // The one-shot Pad press is an admitted candidate but not a complete event
  // (no release exists for one-shot material), so the sealed candidate
  // honestly reports zero events.
  await expect(recoveryRegion).toContainText("owner_lost");

  // Apply is honestly refused: the cutoff fence outcome is unknowable, so the
  // admission is never guessed into a Pattern.
  await recoveryRegion.getByRole("button", {name: "Recover original Pattern"})
    .click();
  await expect(page.getByRole("alert")).toBeVisible({timeout: 30_000});
  await expect(recoveryRegion).toBeVisible();

  // Discard releases the unresolved admission; truth stays untouched.
  await recoveryRegion.getByRole("button", {name: "Discard"}).click();
  await expect(page.getByRole("region", {name: "Sequence recovery"}))
    .toHaveCount(0, {timeout: 60_000});
  const discardedTruth = await inspectTruth(page);
  expect(discardedTruth.revision).toBe(imported.revision);
  expect(discardedTruth.patterns[patternId].events).toHaveLength(0);

  // A fresh recording on the same session opens a new journal and commits.
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state"))
    .toHaveText("Audio running", {timeout: 30_000});
  await recordKey(page).click();
  await transportStatus(page, "recording");
  await page.keyboard.press("KeyW");
  await awaitAdmittedPresses(page, 1);
  await recordKey(page).click();
  await transportStatus(page, "playing");
  const recovered = await inspectTruth(page);
  expect(recovered.revision).toBe(imported.revision + 1);
  expect(recovered.patterns[patternId].events).toHaveLength(1);
  expect(recovered.patterns[patternId].events[0])
    .toMatchObject({slot: {bank: 0, pad: 1}, velocity: 100});
});
