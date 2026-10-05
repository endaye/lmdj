import {expect, test, vi} from "vitest";
import {claimDefaultSeed, readDefaultSeed, type SeedStorage} from "../src/state/default_seed";
import {createDefaultSeedController} from "../src/runtime/default_seed_controller";
import type {CreatorSlotSoundSetRuntimeSession, ProjectView} from "../src/runtime/runtime_types";
const identity = {setId: "11111111-1111-4111-8111-111111111111", version: "1.0.0", manifestSha256: "a".repeat(64)};
const projectId = "22222222-2222-4222-8222-222222222222";
function deferred() {let resolve!: () => void; const promise=new Promise<void>(yes => {resolve=yes;}); return {promise,resolve};}
function fixture() {
  let raw: string|null = null;
  const storage: SeedStorage = {getItem: () => raw, setItem: (_key,value) => {raw=value;}};
  const seed = claimDefaultSeed(storage, identity, projectId)!;
  let project: ProjectView = {projectId, patternId: projectId, revision: 0, bpm: 120, assetCount: 0, assignedPadCount: 0, bundleDigest: "a".repeat(64), key: "—",
    patterns: [{patternId: projectId, bars: 1, events: []}], patternSlots: Array<string|null>(16).fill(null),
    sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
    pads: Array.from({length:64},(_,slot) => ({slot,assetId:null}))};
  let nextId = 0;
  const acquire = vi.fn(async (_request: {slotIndex: number}) => ({}));
  const commit = vi.fn(async (slot: number, _request?: {commandId: string; expectedRevision: number}, admit?: () => boolean) => {
    if (admit?.() === false) return null;
    project = {...project, revision: project.revision + 1, pads: project.pads.map(pad =>
      pad.slot === slot ? {...pad,assetId: "asset"} : pad)};
    return {committedRevision: project.revision, runtimeRevision: project.revision, published: true};
  });
  const options = {seed, storage, session: {acquireSoundSetSlot: acquire} as unknown as CreatorSlotSoundSetRuntimeSession,
    current: () => project, commit, refresh: vi.fn(async () => {}), changed: vi.fn(),
    uuid: () => `00000000-0000-4000-8000-${String(++nextId).padStart(12,"0")}`,
    pause: () => new Promise<void>(resolve => setTimeout(resolve, 100))};
  return {seed, options, acquire, commit, setProject: (value: ProjectView) => {project=value;}, getProject: () => project};
}
test("one slot is Ready while three other downloads remain blocked, with at most four workers", async () => {
  const f = fixture(); const gate = deferred(); let active=0; let maximum=0;
  f.acquire.mockImplementation(async request => {
    active++; maximum=Math.max(maximum,active);
    if ((request as {slotIndex:number}).slotIndex !== 0) await gate.promise;
    active--; return {};
  });
  const controller = createDefaultSeedController(f.options); const finished=controller.start();
  await vi.waitFor(() => expect(f.seed.slots[0]?.phase).toBe("ready"));
  expect(f.seed.slots[1]?.phase).toBe("loading"); expect(maximum).toBe(4);
  controller.cancel(); gate.resolve(); await finished;
});
test("a failed object leaves earlier ready slots intact and retry installs only the failed slot", async () => {
  const f = fixture(); let fail = true;
  f.acquire.mockImplementation(async request => {if ((request as {slotIndex:number}).slotIndex===2 && fail) throw new Error("offline");return {};});
  const controller=createDefaultSeedController(f.options); await controller.start();
  expect(f.seed.slots[2]?.phase).toBe("failed"); expect(f.seed.slots[1]?.phase).toBe("ready");
  const before=f.commit.mock.calls.length; fail=false; await controller.retry(2);
  expect(f.commit.mock.calls.length).toBe(before+1); expect(f.seed.slots[2]?.phase).toBe("ready");
});
test("ready slots are never reacquired when deleted or undone before reload", async () => {
  const f=fixture(); await createDefaultSeedController(f.options).start();
  f.setProject({...f.getProject(),pads:f.getProject().pads.map(pad=>({...pad,assetId:null}))});
  f.acquire.mockClear();f.commit.mockClear(); await createDefaultSeedController(f.options).start();
  expect(f.acquire).not.toHaveBeenCalled();expect(f.commit).not.toHaveBeenCalled();
});
test("a revision conflict retires a target filled by a competing edit", async () => {
  const f=fixture();
  f.commit.mockImplementationOnce(async (slot, _request, admit) => {
    if (admit?.() === false) return null;
    f.setProject({...f.getProject(), revision:1,pads:f.getProject().pads.map(pad => pad.slot===slot?{...pad,assetId:"user"}:pad)});
    throw Object.assign(new Error("changed"),{code:"REVISION_CONFLICT"});
  });
  await createDefaultSeedController(f.options).start();
  expect(f.seed.slots[0]?.phase).toBe("retired");
  expect(f.commit.mock.calls.filter(([slot])=>slot===0)).toHaveLength(1);
});
test("Project replacement after acquisition cancels late installations", async () => {
  const f=fixture();const gate=deferred();f.acquire.mockImplementation(async()=>{await gate.promise;return {};});
  const controller=createDefaultSeedController(f.options); const finished=controller.start();
  await vi.waitFor(()=>expect(f.acquire).toHaveBeenCalledTimes(4));
  f.setProject({...f.getProject(),projectId:"33333333-3333-4333-8333-333333333333"});gate.resolve();await finished;
  expect(f.commit).not.toHaveBeenCalled();
});
test("durable commit without Runtime publication cannot be Ready", async () => {
  const f=fixture();f.commit.mockImplementation(async(_slot, _request, admit)=>{
    if (admit?.() === false) return null;
    return {committedRevision:1,runtimeRevision:0,published:false};
  });
  await createDefaultSeedController(f.options).start();
  expect(f.seed.slots.every(slot=>slot.phase==="saved-unavailable")).toBe(true);
  f.acquire.mockClear();await createDefaultSeedController(f.options).start();expect(f.acquire).not.toHaveBeenCalled();
});


test("resume reuses the persisted command identity after a commit response was lost", async () => {
  const f=fixture();
  keepOnlyFirstSlot(f);
  const request={commandId:"44444444-4444-4444-8444-444444444444",expectedRevision:0};
  f.seed.slots[0]!.phase="processing";f.seed.slots[0]!.request=request;
  f.setProject({...f.getProject(),revision:1,pads:f.getProject().pads.map(pad=>pad.slot===0?{...pad,assetId:"committed"}:pad)});
  const before = structuredClone(f.getProject());
  f.commit.mockImplementation(async (_slot, received, admit) => {
    expect(received).toBe(request);
    if (admit?.() === false) return null;
    return {committedRevision:1,runtimeRevision:1,published:true};
  });
  const controller = createDefaultSeedController(f.options);
  controller.observeProject(f.getProject());
  expect(f.seed.slots[0]?.phase).toBe("processing");
  await controller.start();
  expect(f.commit).toHaveBeenCalledExactlyOnceWith(0, request, expect.any(Function));
  expect(f.getProject()).toEqual(before);
  expect(request.expectedRevision).toBe(0);
  expect(f.seed.slots[0]?.assignmentObserved).toBe(true);
  expect(f.seed.slots[0]?.phase).toBe("ready");
});

test("explicit publication recovery readies saved slots without another install", async () => {
  const f=fixture();f.commit.mockImplementation(async(_slot, _request, admit)=>{
    if (admit?.() === false) return null;
    return {committedRevision:1,runtimeRevision:0,published:false};
  });
  const controller=createDefaultSeedController(f.options);await controller.start();f.commit.mockClear();
  controller.acceptPublication({projectId,patternId:projectId,projectRevision:1,runtimeRevision:1,
    generation:2,runtimeReady:true,snapshotError:null});
  expect(f.seed.slots.every(slot=>slot.phase==="ready")).toBe(true);
  expect(f.commit).not.toHaveBeenCalled();
});


test("a manual assignment retires a failed bootstrap reservation through Undo", async () => {
  const f = fixture();
  f.acquire.mockRejectedValue(new Error("offline"));
  const controller = createDefaultSeedController(f.options);
  await controller.start();
  expect(f.seed.slots[0]?.phase).toBe("failed");
  f.setProject({...f.getProject(), revision: 1, pads: f.getProject().pads.map(pad =>
    pad.slot === 0 ? {...pad, assetId: "user"} : pad)});
  controller.observeProject(f.getProject());
  expect(f.seed.slots[0]?.phase).toBe("retired");
  expect(JSON.parse(f.options.storage.getItem("")!).slots[0].phase).toBe("retired");
  f.setProject({...f.getProject(), revision: 2, pads: f.getProject().pads.map(pad =>
    pad.slot === 0 ? {...pad, assetId: null} : pad)});
  controller.observeProject(f.getProject());
  f.acquire.mockClear(); f.commit.mockClear();
  await controller.retry(0);
  expect(f.acquire).not.toHaveBeenCalled();
  expect(f.commit).not.toHaveBeenCalled();
});

test("a download completing after a manual assignment cannot reclaim its retired slot", async () => {
  const f = fixture(); const gate = deferred();
  f.acquire.mockImplementation(async request => {
    if (request.slotIndex !== 0) throw new Error("offline");
    await gate.promise; return {};
  });
  const controller = createDefaultSeedController(f.options);
  const finished = controller.start();
  await vi.waitFor(() => expect(f.seed.slots[0]?.phase).toBe("loading"));
  f.setProject({...f.getProject(), revision: 1, pads: f.getProject().pads.map(pad =>
    pad.slot === 0 ? {...pad, assetId: "user"} : pad)});
  controller.observeProject(f.getProject()); gate.resolve(); await finished;
  expect(f.seed.slots[0]?.phase).toBe("retired");
  expect(f.commit).not.toHaveBeenCalled();
  expect(f.getProject().pads[0]?.assetId).toBe("user");
});

function keepOnlyFirstSlot(f: ReturnType<typeof fixture>) {
  for (const slot of f.seed.slots.slice(1)) slot.phase = "retired";
}

function assignThenUndo(f: ReturnType<typeof fixture>, controller: ReturnType<typeof createDefaultSeedController>) {
  f.setProject({...f.getProject(), revision: f.getProject().revision + 1,
    pads: f.getProject().pads.map(pad => pad.slot === 0
      ? {...pad, assetId: "33333333-3333-4333-8333-333333333333"} : pad)});
  controller.observeProject(f.getProject());
  f.setProject({...f.getProject(), revision: f.getProject().revision + 1,
    pads: f.getProject().pads.map(pad => pad.slot === 0 ? {...pad, assetId: null} : pad)});
  controller.observeProject(f.getProject());
}

test("a busy authoring lane cannot reserve a Pad through manual assignment and Undo", async () => {
  const f = fixture(); keepOnlyFirstSlot(f);
  const entered = deferred(); const resume = deferred();
  let installed = 0;
  f.options.pause = async () => {entered.resolve(); await resume.promise;};
  f.commit.mockImplementationOnce(async () => null);
  f.commit.mockImplementation(async (slot, request, admit) => {
    if (admit?.() === false) return null;
    if (request!.expectedRevision !== f.getProject().revision) {
      throw Object.assign(new Error("unknown stale command"), {code: "REVISION_CONFLICT"});
    }
    installed++;
    return {committedRevision: f.getProject().revision + 1,
      runtimeRevision: f.getProject().revision + 1, published: true};
  });
  const controller = createDefaultSeedController(f.options);
  const finished = controller.start(); await entered.promise;
  assignThenUndo(f, controller); resume.resolve(); await finished;
  expect(installed).toBe(0);
  expect(f.getProject().pads[0]?.assetId).toBeNull();
  expect(f.seed.slots[0]?.phase).toBe("retired");
  expect(JSON.parse(f.options.storage.getItem("")!).slots[0].phase).toBe("retired");
  f.acquire.mockClear(); f.commit.mockClear();
  await createDefaultSeedController(f.options).start();
  expect(f.acquire).not.toHaveBeenCalled();
  expect(f.commit).not.toHaveBeenCalled();
});

test("a queued authoring admission checks retirement before its Facade dispatch", async () => {
  const f = fixture(); keepOnlyFirstSlot(f);
  const entered = deferred(); const resume = deferred();
  let installed = 0;
  f.commit.mockImplementation(async (_slot, request, admit) => {
    entered.resolve(); await resume.promise;
    if (admit?.() === false) return null;
    if (request!.expectedRevision !== f.getProject().revision) {
      throw Object.assign(new Error("unknown stale command"), {code: "REVISION_CONFLICT"});
    }
    installed++;
    return {committedRevision: f.getProject().revision + 1,
      runtimeRevision: f.getProject().revision + 1, published: true};
  });
  const controller = createDefaultSeedController(f.options);
  const finished = controller.start(); await entered.promise;
  assignThenUndo(f, controller); resume.resolve(); await finished;
  expect(installed).toBe(0);
  expect(f.seed.slots[0]?.phase).toBe("retired");
  expect(f.getProject().pads[0]?.assetId).toBeNull();
});

test("an old journal request cannot rebase across an observed assignment and Undo", async () => {
  const f = fixture(); keepOnlyFirstSlot(f);
  const request = {commandId: "44444444-4444-4444-8444-444444444444", expectedRevision: 0};
  f.seed.slots[0]!.request = request;
  const entered = deferred(); const resume = deferred();
  let installed = 0;
  f.options.pause = async () => {entered.resolve(); await resume.promise;};
  f.commit.mockImplementationOnce(async () => null);
  f.commit.mockImplementation(async (_slot, received, admit) => {
    if (admit?.() === false) return null;
    if (received!.expectedRevision !== f.getProject().revision) {
      throw Object.assign(new Error("unknown stale command"), {code: "REVISION_CONFLICT"});
    }
    installed++;
    return {committedRevision: f.getProject().revision + 1,
      runtimeRevision: f.getProject().revision + 1, published: true};
  });
  const controller = createDefaultSeedController(f.options);
  const finished = controller.start(); await entered.promise;
  assignThenUndo(f, controller); resume.resolve(); await finished;
  expect(installed).toBe(0);
  expect(request.expectedRevision).toBe(0);
  expect(f.seed.slots[0]?.phase).toBe("retired");
});

test("a receipt committed before Undo replays without refilling the now-empty Pad", async () => {
  const f = fixture(); keepOnlyFirstSlot(f);
  const request = {commandId: "44444444-4444-4444-8444-444444444444", expectedRevision: 0};
  f.seed.slots[0]!.request = request;
  const controller = createDefaultSeedController(f.options);
  assignThenUndo(f, controller);
  const before = structuredClone(f.getProject());
  f.commit.mockImplementation(async (_slot, received, admit) => {
    expect(received).toBe(request);
    if (admit?.() === false) return null;
    return {committedRevision:1,runtimeRevision:2,published:true};
  });
  await controller.start();
  expect(f.commit).toHaveBeenCalledExactlyOnceWith(0, request, expect.any(Function));
  expect(f.seed.slots[0]?.phase).toBe("ready");
  expect(f.getProject()).toEqual(before);
  expect(f.getProject().pads[0]?.assetId).toBeNull();
  expect(request.expectedRevision).toBe(0);
});

test("an observed assignment survives journal reload and refuses an unknown stale request", async () => {
  const f = fixture(); keepOnlyFirstSlot(f);
  const request = {commandId: "44444444-4444-4444-8444-444444444444", expectedRevision: 0};
  f.seed.slots[0]!.request = request;
  assignThenUndo(f, createDefaultSeedController(f.options));
  const retained = readDefaultSeed(f.options.storage, identity)!;
  expect(retained.slots[0]?.assignmentObserved).toBe(true);
  f.commit.mockImplementation(async (_slot, received, admit) => {
    if (admit?.() === false) return null;
    expect(received?.expectedRevision).toBe(0);
    throw Object.assign(new Error("unknown stale command"), {code: "REVISION_CONFLICT"});
  });
  await createDefaultSeedController({...f.options, seed: retained}).start();
  expect(f.commit).toHaveBeenCalledTimes(1);
  expect(retained.slots[0]?.phase).toBe("retired");
  expect(retained.slots[0]?.request?.expectedRevision).toBe(0);
  expect(readDefaultSeed(f.options.storage, identity)?.slots[0]?.phase).toBe("retired");
  expect(f.getProject().revision).toBe(2);
  expect(f.getProject().pads[0]?.assetId).toBeNull();
});

test("a journal write failure prevents the Facade dispatch and releases the unissued request", async () => {
  const f = fixture(); keepOnlyFirstSlot(f);
  const write = f.options.storage.setItem;
  f.options.storage.setItem = (key, raw) => {
    if (JSON.parse(raw).slots[0].request !== null) throw new Error("storage unavailable");
    write(key, raw);
  };
  let installed = 0;
  f.commit.mockImplementation(async (_slot, _request, admit) => {
    if (admit?.() === false) return null;
    installed++;
    return {committedRevision:1,runtimeRevision:1,published:true};
  });
  await createDefaultSeedController(f.options).start();
  expect(installed).toBe(0);
  expect(f.seed.slots[0]?.request).toBeNull();
  expect(f.seed.slots[0]?.phase).toBe("failed");
  expect(readDefaultSeed(f.options.storage, identity)?.slots[0]?.request).toBeNull();
  expect(f.getProject().revision).toBe(0);
  expect(f.getProject().pads[0]?.assetId).toBeNull();
});

test("an older journal without assignment history cannot rebase an unknown stale command after reload", async () => {
  const f = fixture(); keepOnlyFirstSlot(f);
  f.seed.slots[0]!.request = {commandId: "44444444-4444-4444-8444-444444444444", expectedRevision: 0};
  f.options.storage.setItem("", JSON.stringify(f.seed));
  const retained = readDefaultSeed(f.options.storage, identity)!;
  expect(retained.slots[0]?.assignmentObserved).toBeUndefined();
  // An old Host observed assignment and Undo before this Host started; its
  // journal cannot supply that history. Native can still recognize a receipt.
  f.setProject({...f.getProject(), revision: 2});
  let installed = 0;
  f.commit.mockImplementation(async (_slot, request, admit) => {
    if (admit?.() === false) return null;
    if (request!.expectedRevision !== f.getProject().revision) {
      throw Object.assign(new Error("unknown stale command"), {code: "REVISION_CONFLICT"});
    }
    installed++;
    f.setProject({...f.getProject(), revision: 3, pads: f.getProject().pads.map(pad =>
      pad.slot === 0 ? {...pad, assetId: "33333333-3333-4333-8333-333333333333"} : pad)});
    return {committedRevision:3,runtimeRevision:3,published:true};
  });
  await createDefaultSeedController({...f.options, seed: retained}).start();
  expect(installed).toBe(0);
  expect(f.commit).toHaveBeenCalledTimes(1);
  expect(retained.slots[0]?.request?.expectedRevision).toBe(0);
  expect(retained.slots[0]?.phase).toBe("retired");
  expect(f.getProject().revision).toBe(2);
  expect(f.getProject().pads[0]?.assetId).toBeNull();
  f.commit.mockClear(); f.acquire.mockClear();
  await createDefaultSeedController({...f.options, seed: readDefaultSeed(f.options.storage, identity)!}).start();
  expect(f.commit).not.toHaveBeenCalled();
  expect(f.acquire).not.toHaveBeenCalled();
});

test("a newly admitted request can rebase after another Pad's edit without installing twice", async () => {
  const f = fixture(); keepOnlyFirstSlot(f);
  const sent: Array<{commandId:string;expectedRevision:number}> = [];
  let installed = 0;
  f.commit.mockImplementation(async (_slot, request, admit) => {
    if (admit?.() === false) return null;
    expect(f.seed.slots[0]?.assignmentObserved).toBe(false);
    expect(readDefaultSeed(f.options.storage, identity)?.slots[0]?.assignmentObserved).toBe(false);
    sent.push(structuredClone(request!));
    if (sent.length === 1) {
      f.setProject({...f.getProject(), revision: 1, pads: f.getProject().pads.map(pad =>
        pad.slot === 1 ? {...pad, assetId: "33333333-3333-4333-8333-333333333333"} : pad)});
      throw Object.assign(new Error("another slot committed"), {code: "REVISION_CONFLICT"});
    }
    expect(request?.expectedRevision).toBe(1);
    installed++;
    f.setProject({...f.getProject(), revision: 2, pads: f.getProject().pads.map(pad =>
      pad.slot === 0 ? {...pad, assetId: "44444444-4444-4444-8444-444444444444"} : pad)});
    return {committedRevision:2,runtimeRevision:2,published:true};
  });
  await createDefaultSeedController(f.options).start();
  expect(sent).toEqual([{commandId:sent[0]!.commandId,expectedRevision:0},
    {commandId:sent[0]!.commandId,expectedRevision:1}]);
  expect(installed).toBe(1);
  expect(f.seed.slots[0]?.phase).toBe("ready");
  expect(f.getProject().revision).toBe(2);
  expect(f.getProject().pads[0]?.assetId).toBe("44444444-4444-4444-8444-444444444444");
  expect(f.getProject().pads[1]?.assetId).toBe("33333333-3333-4333-8333-333333333333");
});

test("a restored unobserved request cannot rebase across assignment and Undo during owner absence", async () => {
  const f = fixture(); keepOnlyFirstSlot(f);
  f.commit.mockImplementationOnce(async (_slot, _request, admit) => {
    expect(admit?.()).toBe(true);
    expect(readDefaultSeed(f.options.storage, identity)?.slots[0]?.assignmentObserved).toBe(false);
    throw Object.assign(new Error("owner lost before receipt"), {code: "HOST_TIMEOUT"});
  });
  const first = createDefaultSeedController(f.options);
  await first.start(); first.cancel();
  expect(f.seed.slots[0]?.phase).toBe("failed");
  const request = structuredClone(f.seed.slots[0]!.request!);
  expect(request.expectedRevision).toBe(0);
  f.setProject({...f.getProject(), revision: 1, pads: f.getProject().pads.map(pad =>
    pad.slot === 0 ? {...pad, assetId: "33333333-3333-4333-8333-333333333333"} : pad)});
  f.setProject({...f.getProject(), revision: 2, pads: f.getProject().pads.map(pad =>
    pad.slot === 0 ? {...pad, assetId: null} : pad)});
  const before = structuredClone(f.getProject());
  const retained = readDefaultSeed(f.options.storage, identity)!;
  expect(retained.slots[0]?.assignmentObserved).toBe(false);
  expect(retained.slots[0]?.request).toEqual(request);
  let installed = 0;
  f.commit.mockClear();
  f.commit.mockImplementation(async (slot, received, admit) => {
    if (admit?.() === false) return null;
    if (received!.expectedRevision !== f.getProject().revision) {
      throw Object.assign(new Error("unknown stale command"), {code: "REVISION_CONFLICT"});
    }
    installed++;
    f.setProject({...f.getProject(), revision: 3, pads: f.getProject().pads.map(pad =>
      pad.slot === slot ? {...pad, assetId: "44444444-4444-4444-8444-444444444444"} : pad)});
    return {committedRevision:3,runtimeRevision:3,published:true};
  });
  await createDefaultSeedController({...f.options, seed: retained}).start();
  expect(installed).toBe(0);
  expect(f.commit).toHaveBeenCalledExactlyOnceWith(0, request, expect.any(Function));
  expect(f.getProject()).toEqual(before);
  expect(retained.slots[0]?.request).toEqual(request);
  expect(readDefaultSeed(f.options.storage, identity)?.slots[0]?.phase).toBe("retired");
});

test("a restored unobserved request replays a known receipt after Undo during owner absence", async () => {
  const f = fixture(); keepOnlyFirstSlot(f);
  f.commit.mockImplementationOnce(async (slot, _request, admit) => {
    expect(admit?.()).toBe(true);
    f.setProject({...f.getProject(), revision: 1, pads: f.getProject().pads.map(pad =>
      pad.slot === slot ? {...pad, assetId: "44444444-4444-4444-8444-444444444444"} : pad)});
    throw Object.assign(new Error("receipt response lost"), {code: "HOST_TIMEOUT"});
  });
  const first = createDefaultSeedController(f.options);
  await first.start(); first.cancel();
  const request = structuredClone(f.seed.slots[0]!.request!);
  expect(request.expectedRevision).toBe(0);
  f.setProject({...f.getProject(), revision: 2, pads: f.getProject().pads.map(pad =>
    pad.slot === 0 ? {...pad, assetId: null} : pad)});
  const before = structuredClone(f.getProject());
  const retained = readDefaultSeed(f.options.storage, identity)!;
  expect(retained.slots[0]?.assignmentObserved).toBe(false);
  f.commit.mockClear();
  f.commit.mockImplementation(async (_slot, received, admit) => {
    expect(admit?.()).toBe(true);
    expect(received).toEqual(request);
    return {committedRevision:1,runtimeRevision:2,published:true};
  });
  await createDefaultSeedController({...f.options, seed: retained}).start();
  expect(f.commit).toHaveBeenCalledExactlyOnceWith(0, request, expect.any(Function));
  expect(f.getProject()).toEqual(before);
  expect(retained.slots[0]?.request).toEqual(request);
  expect(readDefaultSeed(f.options.storage, identity)?.slots[0]?.phase).toBe("ready");
});
