import {expect, test, vi} from "vitest";
import {CaptureBuffer, CAPTURE_MAX_FRAMES} from "../src/capture/capture_buffer";
import {audibleSelection, createPadCapture, type PadCaptureDeps} from "../src/capture/pad_capture";

const target = {projectId: "original", slot: 17, revision: 4};
function fixture(overrides: Partial<PadCaptureDeps> = {}) {
  let batch: (channels: Float32Array[]) => void = () => {};
  const stop = vi.fn(async () => {});
  const commit = vi.fn<PadCaptureDeps["commit"]>(async () => {});
  const start = vi.fn<PadCaptureDeps["start"]>(async (_source, receive) => {batch = receive; return {stop};});
  const deps: PadCaptureDeps = {microphoneGranted: () => true,
    prepareMicrophone: vi.fn(async () => {}), start, canStart: () => true,
    commit, changed: vi.fn(), ...overrides};
  const controller = createPadCapture(deps, "microphone");
  return {controller, deps, start, stop, commit, batch: (values = [0, 0, .01, .2]) => batch([new Float32Array(values)])};
}
const settle = async () => {for (let i=0;i<20;i++) await Promise.resolve();};

test("first microphone permission prepares only and requires a new press", async () => {
  let granted = false;
  const f = fixture({microphoneGranted: () => granted,
    prepareMicrophone: async () => {granted = true;}});
  const first = {};
  expect(f.controller.press(target, first)).toBe(true);
  f.controller.release(first); await settle();
  expect(f.start).not.toHaveBeenCalled(); expect(f.commit).not.toHaveBeenCalled();
  expect(f.controller.getState().phase).toBe("idle");
  f.controller.press(target, {}); expect(f.start).toHaveBeenCalledOnce(); await f.controller.cancel();
});
test("press starts immediately and release stops before one trimmed commit", async () => {
  const f = fixture(); const key = {};
  f.controller.press(target, key); expect(f.start).toHaveBeenCalledOnce();
  f.batch(); f.controller.release(key); f.controller.release(key); await settle();
  expect(f.stop).toHaveBeenCalledOnce(); expect(f.commit).toHaveBeenCalledOnce();
  expect(f.commit.mock.calls[0]?.[2]).toEqual({startFrame: 2, frameCount: 2});
  expect(f.commit.mock.calls[0]?.[3]).toBe(false);
  expect(f.controller.getState().phase).toBe("idle");
});
test("release while starting waits for and stops the acquired resource", async () => {
  let ready!: (handle: {stop(): Promise<void>}) => void;
  const f = fixture({start: () => new Promise(resolve => {ready = resolve;})});
  const key = {}; f.controller.press(target,key); f.controller.release(key);
  ready({stop: f.stop}); await settle();
  expect(f.stop).toHaveBeenCalledOnce(); expect(f.commit).not.toHaveBeenCalled();
  expect(f.controller.getState().phase).toBe("review");
});
test("cancellation defeats a release in flight and retains the take for explicit save", async () => {
  let finish!: () => void;
  const stopped = new Promise<void>(resolve => {finish = resolve;});
  const f = fixture({start: async (_source, batch) => {
    batch([new Float32Array([.1])]); return {stop: () => stopped};
  }});
  const key = {};f.controller.press(target,key);f.controller.release(key);
  const cancelling = f.controller.cancel(); finish(); await cancelling;
  expect(f.commit).not.toHaveBeenCalled(); expect(f.controller.getState().phase).toBe("review");
  await f.controller.save(); expect(f.commit).toHaveBeenCalledOnce();
  expect(f.commit.mock.calls[0]?.[3]).toBe(true);
});
test("strict silence refuses commitment and keeps even a very quiet stereo attack", () => {
  const quiet = new CaptureBuffer(2); quiet.append([new Float32Array([0,0,0]), new Float32Array([0,1e-12,0])]);
  expect(audibleSelection(quiet)).toEqual({startFrame:1,frameCount:2});
  const silent = new CaptureBuffer(1);silent.append([new Float32Array(10)]);
  expect(audibleSelection(silent)).toBeNull();
});
test("capacity seals without automatic commit and requires Save or Discard", async () => {
  const f = fixture(); const key = {}; f.controller.press(target,key);
  const full = new Float32Array(CAPTURE_MAX_FRAMES + 10);full[0] = .1;
  f.batch(Array.from(full)); await settle();f.controller.release(key);
  expect(f.controller.getState().frames).toBe(CAPTURE_MAX_FRAMES);
  expect(f.controller.getState().phase).toBe("review");expect(f.commit).not.toHaveBeenCalled();
  f.controller.discard();expect(f.controller.getState().phase).toBe("idle");
});
test("another recording owner refuses the press before acquiring any resource", () => {
  const f = fixture({canStart: () => false});
  expect(f.controller.press(target,{})).toBe(false);expect(f.start).not.toHaveBeenCalled();
});
test("revision refusal preserves exact take and explicit retry", async () => {
  const f = fixture(); f.commit.mockRejectedValueOnce(new Error("Project changed"));
  const key = {};f.controller.press(target,key);f.batch();f.controller.release(key);await settle();
  expect(f.controller.getState()).toMatchObject({phase:"review",target,message:"Project changed"});
  const original = f.commit.mock.calls[0]?.[1];await f.controller.save();
  expect(f.commit.mock.calls[1]?.[1]).toBe(original);
  expect(f.commit.mock.calls[1]?.[3]).toBe(true);
});
