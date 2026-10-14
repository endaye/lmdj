import {expect, test} from "@playwright/test";
import {
  JOURNAL_PATH, beginPublicInput, cancelCountIn, checkedDeadlineOpeningJournal, checkedWholeJournal, checkpoint, collectProof,
  expectNativeOwner, expectRejectedCountInConsume, expectSameRuntimeOwner, failedOpeningGate, gate, inputEvidence, inspectCountIn, inspectOrdinary, inspectTruth,
  installNativeNodeWitness, prepareProductionProject, projectInventory, releaseGateFinally,
  reopenDeadlineRecovery, reopenExact, requestCountIn, restoreTrace,
} from "./fixtures/production_io.mjs";

const pageFailures = new WeakMap();
test.beforeEach(async ({page}) => {
  const failures = [];
  pageFailures.set(page, failures);
  page.on("pageerror", error => failures.push({message: error.message, stack: error.stack}));
  await installNativeNodeWitness(page);
});
test.afterEach(async ({page}) => {expect(pageFailures.get(page), "actual packaged Runtime does not trap").toEqual([]);});

async function acquireS(page, setup) {
  const admitted = await requestCountIn(page, setup);
  expect(admitted.submit).toBe("accepted");
  let armed;
  await expect.poll(async () => {
    armed = await inspectCountIn(page, admitted.ticket);
    return Number.isSafeInteger(armed.countIn?.startFrame);
  }, {timeout: 1_000, intervals: [10]}).toBe(true);
  expect(armed.countIn).toMatchObject({bpm: 120, bars: 1, barFrames: 96_000});
  expect(armed.countIn.startFrame).toBe(armed.countIn.countInFrame + 96_000);
  expect(armed.startReceipt, "arming has no Applied e1 and cannot open a Journal").toBeNull();
  const beforeS = await projectInventory(page, setup.projectId);
  expect(beforeS.files.some(file => file.path === JOURNAL_PATH)).toBe(false);
  let applied;
  await expect.poll(async () => {
    applied = await inspectCountIn(page, admitted.ticket);
    return applied.startReceipt?.result === "applied";
  }, {timeout: 3_000, intervals: [10]}).toBe(true);
  expect(applied.startReceipt).toMatchObject({effectiveFrame: armed.countIn.startFrame,
    originFrame: armed.countIn.startFrame, patternId: setup.patternId,
    transportEpoch: "1", runtimeGeneration: admitted.ticket.runtimeGeneration,
    frameEpoch: admitted.ticket.frameEpoch, scheduleSerial: admitted.ticket.scheduleSerial, playing: true});
  await checkpoint(page, "actual-e1-at-S-acquired", applied);
  return {admitted, armed, applied, beforeS};
}

async function waitNative(page, kind) {
  let input;
  await expect.poll(async () => {
    input = await inputEvidence(page, kind);
    return input.latest?.native_result !== null && input.latest?.native_result !== undefined;
  }, {timeout: 1_000, intervals: [10]}).toBe(true);
  return input;
}

async function waitConsumed(page, kind) {
  let input;
  await expect.poll(async () => {
    input = await inputEvidence(page, kind);
    return input.consumed.length === 1 && input.call?.state !== "pending";
  }, {timeout: 1_000, intervals: [10]}).toBe(true);
  expect(input.consumed[0]).toMatchObject({complete: true, durable_settled: true, retained: true,
    error: null});
  // Only the original SDK's own await loop consumes its exact accepted ticket.
  expect(input.consumed[0].ticket).toEqual(input.ticket);
  expect(input.requests).toBe(1);
  return input;
}

async function waitObserverExpiry(page, kind) {
  let input;
  await expect.poll(async () => {
    input = await inputEvidence(page, kind);
    return input.call?.state === "rejected" && input.latest?.expired === true;
  }, {timeout: 1_000, intervals: [10]}).toBe(true);
  expect(input.call.error).toMatchObject({code: "HOST_TIMEOUT", details: {pending: true}});
  expect(input.call.ended - input.call.began, "original one-second observer is not restarted").toBeGreaterThanOrEqual(1_000);
  expect(input.latest).toMatchObject({expired: true, complete: false, durable_settled: false, retained: false});
  expect(input.consumed, "observer timeout cannot reclaim or consume an accepted physical owner").toEqual([]);
  return input;
}

async function responsiveStop(page) {
  const result = await page.evaluate(async () => {
    const began = performance.now();
    const accepted = await window.lmdjWebRuntimeHost.session.stopAll();
    return {accepted, elapsed: performance.now() - began};
  });
  expect(result.accepted).toBe(true);
  expect(result.elapsed, "sample Stop retains its ordinary one-second control budget").toBeLessThan(1_000);
  await checkpoint(page, "actual-responsive-sample-Stop", result);
}

function bindWholeJournal(inventory, setup, start, press, release) {
  const records = checkedWholeJournal(inventory);
  expect(records[0]).toMatchObject({kind: "begin", session_id: setup.sessionId,
    pattern_id: setup.patternId, expected_revision: setup.baseline.revision});
  const identity = {operation_id: start.admitted.ticket.commandId,
    runtime_generation: Number(start.admitted.ticket.runtimeGeneration), transport_epoch: 1};
  expect(Number.isSafeInteger(identity.runtime_generation)).toBe(true);
  const prepared = records.filter(record => record.kind === "admission-prepare");
  expect(prepared).toHaveLength(1);
  expect(prepared[0]).toMatchObject({session_id: setup.sessionId, identity,
    data: {identity, project_id: setup.projectId, pattern_id: setup.patternId}});
  const admission = records.filter(record => record.kind === "admission-fence" && record.data.kind === 0);
  expect(admission).toHaveLength(1);
  expect(admission[0]).toMatchObject({identity, session_id: setup.sessionId,
    data: {command_id: start.admitted.ticket.commandId, transport_epoch: 1,
      effective_frame: start.armed.countIn.startFrame, origin_frame: start.armed.countIn.startFrame,
      pattern_id: setup.patternId, bpm: 120, playing: true}});
  const candidates = records.filter(record => record.kind === "admission-candidate");
  expect(candidates, "complete Journal contains exactly both physical edges").toHaveLength(2);
  const nativePress = press.latest.native_result;
  const nativeRelease = release.latest.native_result;
  expect(BigInt(nativeRelease.acceptance_ordinal)).toBe(BigInt(nativePress.acceptance_ordinal) + 1n);
  for (const [index, native] of [nativePress, nativeRelease].entries()) {
    const input = index === 0 ? press : release;
    const expectedWatermark = BigInt(native.acceptance_ordinal) + 9n;
    expect(expectedWatermark <= BigInt(Number.MAX_SAFE_INTEGER)).toBe(true);
    expect(BigInt(nativePress.sequence) <= BigInt(Number.MAX_SAFE_INTEGER)).toBe(true);
    expect(candidates[index]).toMatchObject({identity, session_id: setup.sessionId, data: {
      watermark: Number(expectedWatermark), slot: {bank: 0, pad: 0}, kind: index,
      velocity: index === 0 ? 90 : 0, press_sequence: Number(nativePress.sequence),
    }});
    // The producer journals its actual Native telemetry frame at admission.
    // The later Native consumption frame is independent evidence, not a timer offset.
    expect(Number.isSafeInteger(candidates[index].data.runtime_frame)).toBe(true);
    expect(candidates[index].data.runtime_frame).toBeGreaterThanOrEqual(start.armed.countIn.startFrame);
    expect(candidates[index].data.runtime_frame).toBeGreaterThanOrEqual(input.call.nativeBefore.runtimeFrame);
    expect(candidates[index].data.runtime_frame).toBeLessThanOrEqual(native.runtime_frame);
  }
  const onsetTick = Math.floor((candidates[0].data.runtime_frame - start.armed.countIn.startFrame) / 25);
  const releaseTick = Math.floor((candidates[1].data.runtime_frame - start.armed.countIn.startFrame) / 25);
  const loop = setup.baseline.patterns[setup.patternId].bars * 3840;
  const event = {slot: {bank: 0, pad: 0}, onset_tick: onsetTick % loop,
    duration_tick: Math.min(releaseTick - onsetTick, loop - onsetTick % loop), velocity: 90};
  expect(event.duration_tick, "a genuine correlated Release replaces the short default duration").toBeGreaterThan(240);
  return {records, candidates, event};
}

async function finishAndReopen(page, setup, start, event, {alreadyCancelled = false, report} = {}) {
  await expectSameRuntimeOwner(page, start.admitted.ticket);
  if (!alreadyCancelled) await cancelCountIn(page, setup, start.admitted.ticket);
  let closed, ordinary;
  await expect.poll(async () => {
    closed = await inspectCountIn(page, start.admitted.ticket);
    ordinary = (await inspectOrdinary(page, setup.sessionId)).legacy;
    return closed.cancelReceipt?.result === "applied" && ordinary.phase === "idle" && !ordinary.recording;
  }, {timeout: 5_000, intervals: [10]}).toBe(true);
  expect(closed.error).toBeNull();
  expect(closed.cancelReceipt).toMatchObject({transportEpoch: "2", originFrame: start.armed.countIn.startFrame,
    playing: true, patternId: setup.patternId, runtimeGeneration: start.admitted.ticket.runtimeGeneration,
    frameEpoch: start.admitted.ticket.frameEpoch, scheduleSerial: start.admitted.ticket.scheduleSerial});
  expect(closed.cancelReceipt.effectiveFrame).toBeGreaterThan(start.armed.countIn.startFrame);
  const truth = await inspectTruth(page);
  const expected = structuredClone(setup.baseline);
  expected.revision += 1;
  expected.patterns[setup.patternId].events = [event];
  expect(truth, "whole Truth changes exactly one event and one revision").toEqual(expected);
  await checkpoint(page, "genuine-e2-Record-off-and-exact-Truth", {closed, ordinary, truth});
  const consumed = await inspectCountIn(page, start.admitted.ticket, true);
  expect(consumed.startReceipt).toEqual(closed.startReceipt);
  expect(consumed.cancelReceipt).toEqual(closed.cancelReceipt);
  await page.evaluate(setup => window.lmdjWebRuntimeHost.session.requestPatternTransport({
    sessionId: setup.sessionId, projectId: setup.projectId, commandId: crypto.randomUUID(),
    expectedEpoch: 3, intent: "play_stop", expectedRevision: null,
  }), setup);
  await expect.poll(async () => (await inspectOrdinary(page, setup.sessionId)).legacy.playing,
    {timeout: 1_000, intervals: [10]}).toBe(false);
  expect(await gate(page)).toBe(8);
  const inventory = await projectInventory(page, setup.projectId);
  expect(inventory.files.some(file => file.path === JOURNAL_PATH), "actual flush/reconcile removes the active Journal").toBe(false);
  expect(inventory.files.length).toBeGreaterThan(0);
  return reopenExact(page, setup, truth, inventory, report);
}

async function attachEvidence(page, testInfo, report) {
  report.pageErrors = pageFailures.get(page);
  report.actualResponses = report.reopen?.before ?? report.proofBeforeReload ??
    await collectProof(page).catch(error => ({collectionError: String(error)}));
  await testInfo.attach("actual-production-controller-opfs.json", {
    body: Buffer.from(JSON.stringify(report, null, 2)), contentType: "application/json",
  });
}

test("actual production owner held-open preserves silent press/release through original observer expiry and full reopen", async ({page}, testInfo) => {
  const report = {scope: "actual Creator public frozen Session; production owner held-open"};
  try {
    const setup = report.setup = await prepareProductionProject(page, {muted: true});
    expect(await gate(page, 1)).toBe(1);
    const start = report.start = await acquireS(page, setup);
    await expect.poll(() => gate(page), {timeout: 1_000, intervals: [10]}).toBe(4);
    expect((await inspectCountIn(page, start.admitted.ticket))).toMatchObject({openingPending: true, openingComplete: false, error: null});
    await beginPublicInput(page, "press", "press");
    const press = await waitNative(page, "press");
    const native = expectNativeOwner(press, start.admitted.ticket, {disposition: "muted_no_voice"});
    await page.waitForTimeout(300); // Real held time; no Native clock substitution.
    await beginPublicInput(page, "release", "release");
    const release = await waitNative(page, "release");
    expectNativeOwner(release, start.admitted.ticket, {releaseOf: native.sequence, disposition: "release_no_voice"});
    expect(release.latest.native_result.runtime_frame).toBeGreaterThan(native.runtime_frame + 6000);
    const ordinary = await inspectOrdinary(page, setup.sessionId);
    expect(ordinary.legacy.originFrame).toBe(start.armed.countIn.startFrame);
    await responsiveStop(page);
    report.heldPress = await waitObserverExpiry(page, "press");
    report.heldRelease = await waitObserverExpiry(page, "release");
    expect(await gate(page)).toBe(4);
    expect((await inspectCountIn(page, start.admitted.ticket)).error, "one-second expiry does not spend five-second opening").toBeNull();
    expect(await gate(page, 3)).toBe(1); // Only permits original real flush to run.
    await expect.poll(() => gate(page), {timeout: 1_000, intervals: [10]}).toBe(8);
    report.durablePress = await waitConsumed(page, "press");
    report.durableRelease = await waitConsumed(page, "release");
    report.completeJournal = await projectInventory(page, setup.projectId);
    const bound = report.journalBindings = bindWholeJournal(report.completeJournal, setup, start,
      report.durablePress, report.durableRelease);
    await checkpoint(page, "complete-real-flushed-Journal", report.completeJournal);
    report.reopen = await finishAndReopen(page, setup, start, bound.event, {report});
  } finally {
    report.gateCleanup = await releaseGateFinally(page);
    await attachEvidence(page, testInfo, report);
    await restoreTrace(page);
  }
});

test("actual production owner held-append keeps real Release pending while inspect/cancel/Stop remain responsive", async ({page}, testInfo) => {
  const report = {scope: "actual Creator public frozen Session; production owner held release append"};
  try {
    const setup = report.setup = await prepareProductionProject(page);
    const start = report.start = await acquireS(page, setup);
    await expect.poll(async () => (await inspectCountIn(page, start.admitted.ticket)).openingComplete,
      {timeout: 5_000, intervals: [10]}).toBe(true);
    await beginPublicInput(page, "press", "press");
    report.durablePress = await waitConsumed(page, "press");
    const native = expectNativeOwner(report.durablePress, start.admitted.ticket, {disposition: "voice_started"});
    expect(report.durablePress.call).toMatchObject({state: "resolved", value: {sequence: Number(native.sequence)}});
    await page.waitForTimeout(300);
    expect(await gate(page, 2)).toBe(1);
    await beginPublicInput(page, "release", "release");
    await expect.poll(() => gate(page), {timeout: 1_000, intervals: [10]}).toBe(5);
    report.heldRelease = await waitNative(page, "release");
    expectNativeOwner(report.heldRelease, start.admitted.ticket, {releaseOf: native.sequence, disposition: "release_no_voice"});
    expect(report.heldRelease.latest).toMatchObject({complete: false, durable_settled: false, retained: false});
    // These are whole written bytes under the held flush, not durability proof.
    report.writtenJournalBeforeFlush = await projectInventory(page, setup.projectId);
    const bound = report.journalBindings = bindWholeJournal(report.writtenJournalBeforeFlush, setup, start,
      report.durablePress, report.heldRelease);
    const before = await inspectOrdinary(page, setup.sessionId);
    await responsiveStop(page);
    const began = await page.evaluate(() => performance.now());
    const cancel = report.heldCancel = await cancelCountIn(page, setup, start.admitted.ticket);
    expect(cancel.submit).toBe("accepted");
    expect(await page.evaluate(() => performance.now()) - began).toBeLessThan(1_000);
    let cutoff;
    await expect.poll(async () => {
      cutoff = await inspectCountIn(page, start.admitted.ticket);
      return cutoff.cancelReceipt?.result === "applied";
    }, {timeout: 1_000, intervals: [10]}).toBe(true);
    expect(cutoff.startReceipt).toEqual(start.applied.startReceipt);
    expect(cutoff.cancelReceipt).toMatchObject({transportEpoch: "2", originFrame: start.armed.countIn.startFrame, playing: true});
    expect(cutoff.cancelReceipt.effectiveFrame).toBeGreaterThan(report.heldRelease.latest.native_result.runtime_frame);
    expect(before.legacy.recording).toBe(true);
    report.expiredRelease = await waitObserverExpiry(page, "release");
    expect(await gate(page)).toBe(5);
    expect(await gate(page, 3)).toBe(1);
    await expect.poll(() => gate(page), {timeout: 1_000, intervals: [10]}).toBe(8);
    report.durableRelease = await waitConsumed(page, "release");
    expect(report.durableRelease.latest.native_result).toEqual(report.heldRelease.latest.native_result);
    report.reopen = await finishAndReopen(page, setup, start, bound.event, {alreadyCancelled: true, report});
  } finally {
    report.gateCleanup = await releaseGateFinally(page);
    await attachEvidence(page, testInfo, report);
    await restoreTrace(page);
  }
});

test("original five-second held opening expiry preserves e1 and real Stop F until late actual owner flush/reconcile", async ({page}, testInfo) => {
  const report = {scope: "actual Creator five-second opening expiry; no deadline replacement"};
  try {
    const setup = report.setup = await prepareProductionProject(page);
    expect(await gate(page, 1)).toBe(1);
    const start = report.start = await acquireS(page, setup);
    await expect.poll(() => gate(page), {timeout: 1_000, intervals: [10]}).toBe(4);
    report.writtenBeginBeforeFlush = await projectInventory(page, setup.projectId);
    expect(checkedWholeJournal(report.writtenBeginBeforeFlush)).toHaveLength(1);
    expect((await inspectCountIn(page, start.admitted.ticket)).error).toBeNull();
    await responsiveStop(page);
    await page.waitForTimeout(5_010); // Observe the producer's original real wall-clock deadline.
    let expired;
    await expect.poll(async () => {
      expired = await inspectCountIn(page, start.admitted.ticket);
      return expired.error?.details?.reason;
    }, {timeout: 1_000, intervals: [10]}).toBe("pattern_transport_opening_expired");
    expect(expired.startReceipt).toEqual(start.applied.startReceipt);
    expect(expired).toMatchObject({openingPending: true, openingComplete: false});
    await expect.poll(async () => {
      expired = await inspectCountIn(page, start.admitted.ticket);
      return expired.cancelReceipt?.result;
    }, {timeout: 1_000, intervals: [10]}).toBe("applied");
    expect(expired.cancelReceipt).toMatchObject({transportEpoch: "2", originFrame: start.armed.countIn.startFrame, playing: false});
    expect(expired.cancelReceipt.effectiveFrame).toBeGreaterThan(start.armed.countIn.startFrame);
    expect((await inspectOrdinary(page, setup.sessionId)).legacy.playing).toBe(false);
    expect(await gate(page)).toBe(4);
    report.expired = expired;
    report.heldConsume = await expectRejectedCountInConsume(page, start.admitted.ticket);
    expect(await gate(page, 3)).toBe(1);
    // Failed work is expected here. Gate 7 alone proves neither a flushed
    // closure nor a consumable owner; the independent evidence below does.
    await expect.poll(() => failedOpeningGate(page), {timeout: 1_000, intervals: [10]}).toBe(7);
    await expect.poll(async () => {
      const count = await inspectCountIn(page, start.admitted.ticket);
      const ordinary = (await inspectOrdinary(page, setup.sessionId)).legacy;
      report.late = {count, ordinary};
      return !count.openingPending && !count.openingComplete &&
        count.error?.details?.reason === "admission_opening_deadline_elapsed" &&
        ordinary.phase === "error" && !ordinary.recording && !ordinary.playing;
    }, {timeout: 5_000, intervals: [10]}).toBe(true);
    expect(report.late.count.error).toEqual({code: "INVALID_ARGUMENT", message: "request is invalid",
      details: {reason: "admission_opening_deadline_elapsed", journal_retained: true}});
    expect(report.late.ordinary.error).toEqual({code: "INVALID_ARGUMENT", message: "request is invalid", details: {}});
    expect(report.late.count.startReceipt).toEqual(expired.startReceipt);
    expect(report.late.count.cancelReceipt).toEqual(expired.cancelReceipt);
    await expectSameRuntimeOwner(page, start.admitted.ticket);
    const truth = report.truthBeforeConsume = await inspectTruth(page);
    expect(truth, "no event or new revision is invented by expiry/reconcile").toEqual(setup.baseline);
    const inventory = report.inventoryBeforeConsume = await projectInventory(page, setup.projectId);
    const bound = report.journalBindings = checkedDeadlineOpeningJournal(inventory,
      report.writtenBeginBeforeFlush, setup, start);
    report.foreignConsume = await expectRejectedCountInConsume(page, {...start.admitted.ticket,
      commandId: await page.evaluate(() => crypto.randomUUID())});
    const consumed = report.consumed = await inspectCountIn(page, start.admitted.ticket, true);
    const evidence = ({observedAtMilliseconds: _observedAt, ...fields}) => fields;
    expect(evidence(consumed), "caller ACK returns the entire same failed evidence").toEqual(evidence(report.late.count));
    report.repeatedConsume = await expectRejectedCountInConsume(page, start.admitted.ticket);
    expect(await inspectTruth(page), "caller ACK cannot change any Truth field or revision").toEqual(truth);
    report.inventoryAfterConsume = await projectInventory(page, setup.projectId);
    expect(report.inventoryAfterConsume, "caller ACK retains the entire active Journal and every OPFS byte").toEqual(inventory);
    const proof = await collectProof(page);
    expect(proof.calls, "this first-opening failure has no unresolved public input Promise").toEqual({});
    expect(proof.trace.filter(row => row.request.operation === "pattern.transport.input.request")).toEqual([]);
    expect(proof.trace.filter(row => row.request.operation === "pattern.transport.count-in.request")).toHaveLength(1);
    const successfulConsumers = proof.trace.filter(row => row.request.operation === "pattern.transport.count-in.inspect" &&
      row.request.payload.consume && row.response?.ok === true);
    expect(successfulConsumers, "only the exact original caller ticket is acknowledged once").toHaveLength(1);
    expect(successfulConsumers[0].request.payload).toEqual({session_id: start.admitted.ticket.sessionId,
      command_id: start.admitted.ticket.commandId, runtime_generation: start.admitted.ticket.runtimeGeneration,
      frame_epoch: start.admitted.ticket.frameEpoch, schedule_serial: start.admitted.ticket.scheduleSerial, consume: true});
    expect(successfulConsumers[0].response.result.error).toEqual(report.late.count.error);
    await checkpoint(page, "late-actual-owner-final-refusal-and-caller-ACK", {late: report.late, consumed, truth, inventory});
    report.reopen = await reopenDeadlineRecovery(page, setup,
      {truth, inventory, journal: bound.expectedJournal}, report);
  } finally {
    report.gateCleanup = await releaseGateFinally(page);
    await attachEvidence(page, testInfo, report);
    await restoreTrace(page);
  }
});
