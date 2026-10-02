import {expect, test, vi} from "vitest";
import {claimDefaultSeed, type SeedStorage} from "../src/state/default_seed";
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
  const commit = vi.fn(async (slot: number) => {
    project = {...project, revision: project.revision + 1, pads: project.pads.map(pad =>
      pad.slot === slot ? {...pad,assetId: "asset"} : pad)};
    return {committedRevision: project.revision, runtimeRevision: project.revision, published: true};
  });
  const options = {seed, storage, session: {acquireSoundSetSlot: acquire} as unknown as CreatorSlotSoundSetRuntimeSession,
    current: () => project, commit, refresh: vi.fn(async () => {}), changed: vi.fn(),
    uuid: () => `00000000-0000-4000-8000-${String(++nextId).padStart(12,"0")}`};
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
  f.commit.mockImplementationOnce(async slot => {
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
  const f=fixture();f.commit.mockImplementation(async()=>({committedRevision:1,runtimeRevision:0,published:false}));
  await createDefaultSeedController(f.options).start();
  expect(f.seed.slots.every(slot=>slot.phase==="saved-unavailable")).toBe(true);
  f.acquire.mockClear();await createDefaultSeedController(f.options).start();expect(f.acquire).not.toHaveBeenCalled();
});


test("resume reuses the persisted command identity after a commit response was lost", async () => {
  const f=fixture();
  const request={commandId:"44444444-4444-4444-8444-444444444444",expectedRevision:0};
  f.seed.slots[0]!.phase="processing";f.seed.slots[0]!.request=request;
  f.setProject({...f.getProject(),revision:1,pads:f.getProject().pads.map(pad=>pad.slot===0?{...pad,assetId:"committed"}:pad)});
  const controller = createDefaultSeedController(f.options);
  controller.observeProject(f.getProject());
  expect(f.seed.slots[0]?.phase).toBe("processing");
  await controller.start();
  expect(f.commit.mock.calls[0]).toEqual([0,request]);
  expect(f.seed.slots[0]?.phase).toBe("ready");
});

test("explicit publication recovery readies saved slots without another install", async () => {
  const f=fixture();f.commit.mockImplementation(async()=>({committedRevision:1,runtimeRevision:0,published:false}));
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
