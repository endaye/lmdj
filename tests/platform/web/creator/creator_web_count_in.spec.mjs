import {expect, test} from "@playwright/test";
import {decodeLegacyPatternTransportStatus} from
  "../../../../packages/web-runtime-platform/test/fixtures/legacy_pattern_transport_status.mjs";
import {waitForProjectReopen} from "./fixtures/creator_boot.mjs";
import {PROJECT_TRANSITION_TIMEOUT_MS} from "./fixtures/perform_helpers.mjs";
import {
  armCountInPcm, attachCountInPcmObserver,
  cancelCountIn, countInProjectInventory, expectForcedCountInPcm,
  inspectCountIn, installCountInAudioObserver, prepareCountInProject,
  readCountInPcm, requestCountIn, requestCountInInput, sendCountInHost,
  settleCountInInput, startCountInMasterCapture, stopCountInMasterCapture,
  waitForCountInBoundary, waitForObservedFrame, countInPattern, ensureCountInClock,
  expectCountInClock, setCountInMonitor, stallCountInObserver, waitForCountInOpening,
  readCountInJournal, expectedCountInHeldEvent, expectCountInProductMonitor,
  expectCountInMixedCapture, resampleCountInMasterCapture,
  pauseCountInOpeningObserver, resumeCountInOpeningObserver,
} from "./fixtures/count_in_helpers.mjs";

test.beforeEach(async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  await installCountInAudioObserver(page);
});

test.afterEach(async ({page}, testInfo) => {
  // Keep original RPC identities, actual Native dispatch deadlines and stall
  // intervals in the private test result even when the musical proof fails.
  const proof = await page.evaluate(() => window.__countInRpcProof ?? null).catch(() => null);
  if (proof !== null) await testInfo.attach("count-in-original-rpc-and-stall-proof", {
    body: Buffer.from(JSON.stringify(proof, null, 2)), contentType: "application/json",
  });
});

async function inspectOrdinary(page, sessionId) {
  const raw = await sendCountInHost(page, "pattern.transport.inspect", {session_id: sessionId});
  // Feed the actual production Host response into the retained old SDK decoder.
  // No current decoder manufactures or adds an ordinary response field here.
  return {raw, legacy: decodeLegacyPatternTransportStatus(raw)};
}

async function finishCountIn(page, setup, ticket, intent = "play_stop") {
  await cancelCountIn(page, setup, ticket, intent);
  let status, ordinary;
  await expect.poll(async () => {
    status = await inspectCountIn(page, ticket);
    ordinary = (await inspectOrdinary(page, setup.sessionId)).legacy;
    return status.cancelReceipt?.result === "applied" && ordinary.phase === "idle" &&
      !ordinary.recording && ordinary.playing === (intent === "record");
  }, {timeout: 5_000, intervals: [10]}).toBe(true);
  expect(status.error).toBeNull();
  expect(ordinary.error).toBeNull();
  expect(status.cancelReceipt.transportEpoch).toBe("2");
  expect(status.cancelReceipt.originFrame).toBe(status.startReceipt.originFrame);
  expect(status.cancelReceipt.effectiveFrame).toBeGreaterThan(status.startReceipt.effectiveFrame);
  const consumed = await inspectCountIn(page, ticket, true);
  expect(consumed.cancelReceipt).toEqual(status.cancelReceipt);
  return status;
}

for (const scenario of [
  {bpm: 120, bars: 1, barFrames: 96_000, monitor: 100, stall: false},
  {bpm: 129, bars: 2, barFrames: 89_303, monitor: 0, stall: false},
  {bpm: 40, bars: 2, barFrames: 288_000, monitor: 60, stall: true},
  {bpm: 120, bars: 1, barFrames: 96_000, monitor: 100, stall: false, metronome: true},
]) {
  test(`packaged count-in ${scenario.bpm} BPM/${scenario.bars} bar uses native PCM boundaries and excludes cues from Master${scenario.metronome ? " with native S downbeat" : ""}`,
    async ({page}) => {
      // This includes the existing bounded Project import, a real 12-second
      // count-in at 40 BPM, and the original 5-second opening/closure budgets.
      test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS + 30_000);
      const errors = [];
      page.on("pageerror", error => errors.push(String(error.message)));
      const setup = await prepareCountInProject(page, scenario.bpm);
      await attachCountInPcmObserver(page);
      const clock = await ensureCountInClock(page);
      // Public synchronous capability; the optional ordinary downbeat at S
      // comes from Native, not the observing page's clock or JS oscillator.
      await page.evaluate(enabled =>
        window.lmdjWebRuntimeHost.session.setCountInMetronome(enabled),
      scenario.metronome === true);
      await setCountInMonitor(page, scenario.monitor);
      await startCountInMasterCapture(page);
      await armCountInPcm(page);
      const admitted = await requestCountIn(page, setup, scenario.bars);
      expect(admitted.ticket.scheduleSerial).toBe("9007199254740993");
      expectCountInClock(admitted.ticket, clock);
      const armed = await waitForCountInBoundary(page, admitted.ticket);
      const count = armed.countIn;
      expect(count.bpm).toBe(scenario.bpm);
      expect(count.barFrames).toBe(scenario.barFrames);
      expect(count.startFrame).toBe(count.countInFrame + scenario.bars * scenario.barFrames);
      expect(armed.startReceipt).toBeNull();
      expect(armed.openingPending).toBe(false);
      expect(armed.openingComplete).toBe(false);
      const offsets = Array.from({length: scenario.bars * 4}, (_, beat) =>
        Math.floor(beat / 4) * scenario.barFrames +
        Math.floor(((beat % 4) * scenario.barFrames + 2) / 4));
      // Retain the independent design's literal C=1000 witness. Its last
      // two values are absolute frames, not relative offsets from actual C.
      if (scenario.bpm === 129) expect(offsets.map(offset => 1000 + offset)).toEqual([
        1000, 23_326, 45_652, 67_977, 90_303, 112_629, 134_955, 157_280,
      ]);
      const markers = offsets.map(offset => count.countInFrame + clock.offset + offset);
      const start = count.startFrame + clock.offset;
      if (scenario.stall) {
        await pauseCountInOpeningObserver(page, admitted.ticket, "cue");
        const observed = await stallCountInObserver(page, markers[1]);
        await resumeCountInOpeningObserver(page, admitted.ticket, observed);
      }
      await waitForObservedFrame(page, markers.at(-1) + 1920,
        scenario.bars * scenario.barFrames / 48 + 1_000);
      const capture = await stopCountInMasterCapture(page);
      expect(capture.stopRequestedFrame).toBeLessThan(start);
      expect(capture.ack.observedFrame, "real stop ACK arrives before S").toBeLessThan(start);
      const beforeStart = await inspectCountIn(page, admitted.ticket);
      expect(beforeStart.startReceipt, "capture seals before the actual native S").toBeNull();
      expect(beforeStart.openingPending).toBe(false);
      if (scenario.stall) {
        await pauseCountInOpeningObserver(page, admitted.ticket, "S");
        const stalled = await page.evaluate(start => {
          const context = window.__countInPcm.context;
          const stallBeganAt = performance.now();
          const before = Math.round(context.currentTime * 48_000);
          // Block only the observing main thread. The production Wasm audio
          // processor, Native clock and I/O worker keep their actual owners.
          const deadline = performance.now() + 2_000;
          while (context.currentTime * 48_000 < start + 9_600)
            if (performance.now() >= deadline) throw new Error("AudioContext stopped during bounded S stall");
          return {before, after: Math.round(context.currentTime * 48_000),
            stallBeganAt, stallEndedAt: performance.now()};
        }, start);
        await resumeCountInOpeningObserver(page, admitted.ticket, stalled);
        expect(stalled.before).toBeLessThan(start);
        expect(stalled.after).toBeGreaterThanOrEqual(start + 9_600);
      } else await waitForObservedFrame(page, start + 9_600, 2_000);
      // Freeze the fixed 16-second cell as soon as the required post-S PCM
      // exists. I/O opening may use its original remaining five seconds.
      const expectedCues = scenario.metronome ? [...markers, start] : markers;
      const pcm = await readCountInPcm(page, [...markers, start], {cueMarkers: expectedCues});
      const applied = await waitForCountInOpening(page, admitted.ticket, clock, count.startFrame);
      if (scenario.stall) {
        const proof = await page.evaluate(() => window.__countInRpcProof);
        expect(proof.instrumentationErrors).toEqual([]);
        expect(proof.stalls.map(fence => fence.label)).toEqual(["cue", "S"]);
        for (const fence of proof.stalls) {
          expect(fence.drainedAt).toBeLessThanOrEqual(fence.stallBeganAt);
          expect(fence.stallEndedAt).toBeLessThanOrEqual(fence.resumedAt);
          expect(proof.requests.filter(entry => entry.payload.command_id === admitted.ticket.commandId &&
            entry.dispatchAt < fence.stallEndedAt && entry.settledAt > fence.stallBeganAt),
          "no original short inspect crosses a deliberate observer stall").toEqual([]);
        }
        const originalRequests = proof.requests.filter(entry =>
          entry.payload.command_id === admitted.ticket.commandId);
        expect(originalRequests.length).toBeGreaterThan(0);
        for (const entry of originalRequests) {
          expect(entry.deadlineMs, "original short RPC budget stays unchanged").toBe(1_000);
          expect(entry.submitResult, "actual Native submit receipt").toBe(0);
          expect(entry.nativeRequestId).toBe(entry.requestId);
          expect(entry.responseRequestId).toBe(entry.requestId);
          expect(entry.nativeDeadlineAtEpoch).not.toBeNull();
          expect(entry.nativeDeadlineAt).toBeGreaterThan(entry.dispatchAt);
          expect(entry.ok).toBe(true);
          expect(entry.error).toBeNull();
        }
      }
      expect(applied.startReceipt.patternId).toBe(setup.patternId);
      // The independent analytic envelope/absolute onset oracle covers all
      // forced cues and, when enabled, exactly one additional accented S cue.
      // Its aligned monitor assertion includes product + cue at that S.
      expectForcedCountInPcm(pcm, expectedCues, {monitorLevel: scenario.monitor / 100});
      expect(pcm.planes[0].onsets).toEqual([start + 1]);
      expect(pcm.planes[1].onsets).toEqual([start + 1]);
      expect(pcm.planes[0].energy).toBeGreaterThan(0);
      if (!scenario.metronome)
        expectCountInProductMonitor(pcm, start, scenario.monitor / 100);
      if (scenario.monitor === 0) {
        expect(pcm.planes[4].energy).toBe(0);
        expect(pcm.planes[5].energy).toBe(0);
      }
      const ordinary = (await inspectOrdinary(page, setup.sessionId)).legacy;
      expect(ordinary.originFrame).toBe(count.startFrame);
      expect(ordinary.recording).toBe(true);
      await finishCountIn(page, setup, admitted.ticket);
      expect(errors, "the complete packaged journey does not trap").toEqual([]);
    });
}

test("winning packaged count-in cancellation has no origin and changes no Project bytes", async ({page}) => {
  test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS + 10_000);
  const setup = await prepareCountInProject(page, 40, {silentPattern: true});
  await attachCountInPcmObserver(page);
  const clock = await ensureCountInClock(page);
  const before = await countInProjectInventory(page, setup.projectId);
  await armCountInPcm(page);
  const admitted = await requestCountIn(page, setup, 2);
  expectCountInClock(admitted.ticket, clock);
  const armed = await waitForCountInBoundary(page, admitted.ticket);
  await waitForObservedFrame(page, armed.countIn.countInFrame + clock.offset + 1920, 1_000);
  expect(await countInProjectInventory(page, setup.projectId), "Armed does not open or prepare a Journal")
    .toEqual(before);
  await cancelCountIn(page, setup, admitted.ticket);
  let cancelled;
  await expect.poll(async () => {
    cancelled = await inspectCountIn(page, admitted.ticket);
    return cancelled.startReceipt?.result === "cancelled" && cancelled.cancelReceipt?.result === "cancelled";
  }, {timeout: 1_000, intervals: [10]}).toBe(true);
  expect(cancelled.error).toBeNull();
  for (const receipt of [cancelled.startReceipt, cancelled.cancelReceipt]) {
    expect(receipt.effectiveFrame).toBeNull();
    expect(receipt.originFrame).toBeNull();
    expect(receipt.playing).toBe(false);
  }
  expect(cancelled.openingPending).toBe(false);
  expect(cancelled.openingComplete).toBe(false);
  const ordinary = (await inspectOrdinary(page, setup.sessionId)).legacy;
  expect(ordinary.phase).toBe("idle");
  expect(ordinary.playing).toBe(false);
  expect(ordinary.recording).toBe(false);
  await inspectCountIn(page, admitted.ticket, true);
  expect(await countInProjectInventory(page, setup.projectId)).toEqual(before);
  const pcm = await readCountInPcm(page);
  expect(pcm.planes[2].energy).toBeGreaterThan(0);
  expect(pcm.planes[0].energy).toBe(0);
  await page.reload();
  await waitForProjectReopen(page, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  expect(await countInProjectInventory(page, setup.projectId), "reopen retains the complete byte inventory")
    .toEqual(before);
});

test("packaged silent held input retains its real release duration through Record-off and reopen", async ({page}) => {
  test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS + 20_000);
  const setup = await prepareCountInProject(page, 120, {silentPattern: true});
  await attachCountInPcmObserver(page);
  let clock = await ensureCountInClock(page);
  const before = (await sendCountInHost(page, "project.inspect", {})).project;
  const sample = await sendCountInHost(page, "sample.inspect", {slot: {bank: 0, pad: 1}});
  expect(sample.asset_id).toBe(before.banks[0].pads[1].asset_id);
  expect(sample.asset_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(sample.project_revision).toBe(before.revision);
  const playback = sample.playback;
  expect(Object.keys(playback)).toEqual(expect.arrayContaining([
    "trim_start_frame", "trim_end_frame", "trigger_mode", "gain_millidb", "muted",
  ]));
  await sendCountInHost(page, "sample.update_pad", {command_id: crypto.randomUUID(),
    expected_revision: before.revision, slot: {bank: 0, pad: 1}, playback: {...playback, muted: true}});
  await sendCountInHost(page, "snapshot.reload", {pattern_id: setup.patternId});
  const baseline = (await sendCountInHost(page, "project.inspect", {})).project;
  clock = await ensureCountInClock(page, clock);
  await armCountInPcm(page);
  const admitted = await requestCountIn(page, setup, 1);
  const armed = await waitForCountInBoundary(page, admitted.ticket);
  expectCountInClock(admitted.ticket, clock);
  const opened = await waitForCountInOpening(page, admitted.ticket, clock, armed.countIn.startFrame);
  // Choose a real calibrated Native phase early in the Bar. Leave ample
  // queue/hold room, then prove the stored duration itself exceeds 240 ticks.
  const press = await requestCountInInput(page, {slot: 1, held: true, velocity: 90,
    phaseWindow: {startFrame: armed.countIn.startFrame, offset: clock.offset}});
  const pressed = await settleCountInInput(page, press.ticket);
  expect(pressed.disposition).toBe("muted_no_voice");
  const nativePhase = Math.floor((pressed.runtimeFrame - armed.countIn.startFrame) / 25) % 3840;
  expect(3840 - nativePhase, "actual Native phase leaves more than the fallback duration").toBeGreaterThan(240);
  expect(pressed.authority).toEqual({recording: true,
    scheduleSerial: admitted.ticket.scheduleSerial, transportEpoch: "1"});
  await waitForObservedFrame(page, pressed.runtimeFrame + clock.offset + 12_000, 1_000);
  const release = await requestCountInInput(page, {kind: "release", slot: 1,
    heldPressSequence: pressed.sequence});
  const released = await settleCountInInput(page, release.ticket);
  expect(released.disposition).toBe("release_no_voice");
  expect(released.heldPressSequence).toBe(pressed.sequence);
  expect(released.runtimeFrame).toBeGreaterThanOrEqual(pressed.runtimeFrame + 12_000);
  const journal = await readCountInJournal(page, setup);
  const expected = expectedCountInHeldEvent(journal, setup, admitted.ticket,
    armed.countIn.startFrame, pressed, released, 90, opened.startReceipt);
  await readCountInPcm(page); // Stop observation before the independent closure wait.
  const closed = await finishCountIn(page, setup, admitted.ticket, "record");
  expect(closed.cancelReceipt.playing).toBe(true);
  const truth = (await sendCountInHost(page, "project.inspect", {})).project;
  expect(countInPattern(truth, setup.patternId).events).toEqual([expected]);
  const completeExpected = structuredClone(baseline);
  completeExpected.revision = baseline.revision + 1;
  countInPattern(completeExpected, setup.patternId).events = [expected];
  expect(truth, "only the retained actual event changes complete Project Truth").toEqual(completeExpected);
  await page.evaluate(({setup}) => window.lmdjWebRuntimeHost.session.requestPatternTransport({
    sessionId: setup.sessionId, projectId: setup.projectId, commandId: crypto.randomUUID(),
    expectedEpoch: 3, intent: "play_stop", expectedRevision: null,
  }), {setup});
  await expect.poll(async () => {
    const stopped = (await inspectOrdinary(page, setup.sessionId)).legacy;
    return stopped.phase === "idle" && !stopped.playing && !stopped.recording && stopped.error === null;
  }, {timeout: 1_000, intervals: [10]}).toBe(true);
  await page.reload();
  await waitForProjectReopen(page, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  expect((await sendCountInHost(page, "project.inspect", {})).project).toEqual(truth);
});


test("pre-S live Bank audio overlaps a forced cue without recording its later real release", async ({page}) => {
  test.setTimeout(PROJECT_TRANSITION_TIMEOUT_MS + 20_000);
  const setup = await prepareCountInProject(page, 40, {silentPattern: true});
  await attachCountInPcmObserver(page);
  const clock = await ensureCountInClock(page);
  await setCountInMonitor(page, 60);
  const baseline = (await sendCountInHost(page, "project.inspect", {})).project;
  await armCountInPcm(page);
  await startCountInMasterCapture(page);
  const admitted = await requestCountIn(page, setup, 1);
  expectCountInClock(admitted.ticket, clock);
  const armed = await waitForCountInBoundary(page, admitted.ticket);
  const count = armed.countIn;
  expect(count.barFrames).toBe(288_000);
  const markers = [0, 72_000, 144_000, 216_000].map(offset =>
    count.countInFrame + clock.offset + offset);
  const start = count.startFrame + clock.offset;
  // The real 100-ms Bank fixture spans this normal cue. Position only the
  // observer/request; Native alone consumes the input and renders the cue.
  await waitForObservedFrame(page, markers[1] - 1920, 2_000);
  const press = await requestCountInInput(page, {held: true});
  const pressed = await settleCountInInput(page, press.ticket);
  expect(pressed.disposition).toBe("voice_started");
  expect(pressed.runtimeGeneration).toBe(clock.runtimeGeneration);
  expect(pressed.frameEpoch).toBe(clock.frameEpoch);
  expect(pressed.runtimeFrame).toBeLessThan(count.startFrame);
  expect(pressed.authority).toEqual({recording: false, scheduleSerial: null, transportEpoch: null});
  await waitForObservedFrame(page, markers.at(-1) + 2016, 5_000);
  const capture = await stopCountInMasterCapture(page, {silent: false});
  expect(capture.nonzero).toBeGreaterThan(0);
  expect(capture.stopRequestedFrame).toBeLessThan(start);
  expect(capture.ack.observedFrame).toBeLessThan(start);
  const beforeS = await inspectCountIn(page, admitted.ticket);
  expect(beforeS.startReceipt).toBeNull();
  expect(beforeS.openingPending).toBe(false);
  await waitForObservedFrame(page, start + 9600, 2_000);
  const pcm = await readCountInPcm(page, [...markers, start], {cueMarkers: markers});
  expectForcedCountInPcm(pcm, markers, {monitorLevel: 0.6});
  expect(pcm.planes[0].onsets).toEqual([pressed.runtimeFrame + clock.offset + 1]);
  expect(pcm.planes[1].onsets).toEqual(pcm.planes[0].onsets);
  expectCountInProductMonitor(pcm, start, 0.6);
  await expectCountInMixedCapture(page, pcm.planes[0].onsets[0], markers);
  await waitForCountInOpening(page, admitted.ticket, clock, count.startFrame);
  const release = await requestCountInInput(page, {kind: "release", heldPressSequence: pressed.sequence});
  const released = await settleCountInInput(page, release.ticket);
  expect(released.heldPressSequence).toBe(pressed.sequence);
  expect(released.runtimeFrame).toBeGreaterThanOrEqual(count.startFrame);
  expect(released.disposition).toBe("release_no_voice");
  expect(released.authority).toEqual(pressed.authority);
  const journal = await readCountInJournal(page, setup);
  expect(journal.filter(record => record.kind === "admission-candidate"),
    "an early live hold and its actual later release never fabricate a recorded press").toEqual([]);
  await finishCountIn(page, setup, admitted.ticket);
  expect((await sendCountInHost(page, "project.inspect", {})).project).toEqual(baseline);
  // Only after real e2/F and durable owner settlement, install the same actual
  // captured PCM through the existing importer and public Performance path.
  const resampledTruth = await resampleCountInMasterCapture(page, setup, markers);
  await page.reload();
  await waitForProjectReopen(page, "00000000", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  expect((await sendCountInHost(page, "project.inspect", {})).project).toEqual(resampledTruth);
});
