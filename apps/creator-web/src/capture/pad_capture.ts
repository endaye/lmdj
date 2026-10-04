import {CaptureBuffer} from "./capture_buffer";

export type PadCaptureSource = "microphone" | "master";
export interface PadCaptureTarget {projectId: string; slot: number; revision: number}
export interface PadCaptureState {
  phase: "idle" | "permission" | "starting" | "recording" | "stopping" | "review" | "saving";
  source: PadCaptureSource;
  target: PadCaptureTarget | null;
  frames: number;
  message: string | null;
}
export interface PadCaptureHandle {stop(): Promise<void>}
export interface PadCaptureDeps {
  microphoneGranted(): boolean;
  prepareMicrophone(): Promise<void>;
  start(source: PadCaptureSource, batch: (channels: Float32Array[]) => void,
    failed: (message: string) => void, signal: AbortSignal): Promise<PadCaptureHandle>;
  canStart(target: PadCaptureTarget): boolean;
  commit(target: PadCaptureTarget, buffer: CaptureBuffer,
    selection: {startFrame: number; frameCount: number}, retry: boolean): Promise<void>;
  changed(state: PadCaptureState): void;
}

// Only strict digital zero is removed; quiet attacks remain part of the take.
export function audibleSelection(buffer: CaptureBuffer) {
  if (buffer.frameCount === 0 || buffer.peak === 0) return null;
  const channels = buffer.slice(0, buffer.frameCount);
  let startFrame = 0;
  while (startFrame < buffer.frameCount && channels.every(channel => channel[startFrame] === 0)) startFrame++;
  return {startFrame, frameCount: buffer.frameCount - startFrame};
}

export function createPadCapture(deps: PadCaptureDeps, source: PadCaptureSource) {
  let state: PadCaptureState = {phase: "idle", source, target: null, frames: 0, message: null};
  let buffer: CaptureBuffer | null = null;
  let owner: object | null = null;
  let startup: Promise<PadCaptureHandle> | null = null;
  let startupAbort: AbortController | null = null;
  let stopping: Promise<void> | null = null;
  let saving: Promise<void> | null = null;
  const preparing = new Set<Promise<void>>();
  let automatic = false;
  let generation = 0;
  const publish = (patch: Partial<PadCaptureState>) => {
    state = {...state, ...patch}; deps.changed({...state});
  };
  function save(retry = true): Promise<void> {
    if (saving !== null) return saving;
    if (state.phase !== "review" || buffer === null || state.target === null) return Promise.resolve();
    const selection = audibleSelection(buffer);
    if (selection === null) {publish({message: "No sound recorded. Discard this take and try again."}); return Promise.resolve();}
    const take = buffer;
    const target = state.target;
    const commit = deps.commit;
    publish({phase: "saving", message: null});
    saving = Promise.resolve().then(async () => {
      try {
        await commit(target, take, selection, retry);
        generation++; buffer = null; publish({phase: "idle", target: null, frames: 0});
      } catch (error) {
        publish({phase: "review", message: error instanceof Error ? error.message : "Unable to save this take."});
      } finally {saving = null;}
    });
    return saving;
  }
  function seal(commit: boolean, message: string | null = null) {
    if (!["starting", "recording", "stopping"].includes(state.phase)) return Promise.resolve();
    if (state.phase === "starting") startupAbort?.abort();
    if (!commit) automatic = false;
    else if (state.phase !== "stopping") automatic = true;
    owner = null;
    if (message !== null) publish({message});
    if (stopping !== null) return stopping;
    publish({phase: "stopping"});
    stopping = (async () => {
      await Promise.resolve(); // A synchronous first batch may seal during start.
      try {await (await startup)?.stop();}
      catch (error) {automatic = false; publish({message: error instanceof Error ? error.message : "Recording stopped."});}
      finally {startup = null; startupAbort = null; stopping = null; publish({phase: "review"});}
      if (automatic) await save(false);
    })();
    return stopping;
  }
  return {
    getState: () => ({...state}),
    // The Workspace retains the take; only its current Facade/Host binding
    // changes after the retiring Runtime's cleanup barrier has completed.
    updateDeps(next: PadCaptureDeps) {deps = next;},
    setSource(next: PadCaptureSource) {
      if (state.phase !== "idle") return;
      publish({source: next});
    },
    press(target: PadCaptureTarget, gesture: object) {
      if (state.phase !== "idle" || !deps.canStart(target)) return false;
      owner = gesture;
      if (state.source === "microphone" && !deps.microphoneGranted()) {
        const token = ++generation;
        publish({phase: "permission", message: "Allow microphone access, then press an empty Pad again."});
        const preparation = deps.prepareMicrophone().then(() => {
          if (token === generation) {
            owner = null;
            publish({phase: "idle", message: "Microphone ready. Press an empty Pad to record."});
          }
        }, error => {
          if (token === generation) {
            owner = null;
            publish({phase: "idle", message: error instanceof Error ? error.message : "Microphone unavailable."});
          }
        });
        preparing.add(preparation);
        void preparation.finally(() => preparing.delete(preparation));
        return true;
      }
      const token = ++generation;
      automatic = false;
      buffer = new CaptureBuffer(state.source === "master" ? 2 : 1);
      publish({phase: "starting", target: {...target}, frames: 0, message: null});
      startupAbort = new AbortController();
      try {
        startup = deps.start(state.source, channels => {
          if (token !== generation || buffer === null || !["starting", "recording", "stopping"].includes(state.phase)) return;
          try {
            buffer.append(channels); publish({frames: buffer.frameCount});
            if (buffer.atCapacity) void seal(false, "60-second limit reached. Save or discard this take.");
          } catch {void seal(false, "Recording input changed. Save or discard this take.");}
        }, message => {if (token === generation) void seal(false, message);}, startupAbort.signal);
        void startup.then(() => {
          if (token === generation && state.phase === "starting") publish({phase: "recording"});
        }, error => {if (token === generation) void seal(false, error instanceof Error ? error.message : "Recording unavailable.");});
      } catch (error) {
        startup = null; owner = null;
        publish({phase: "review", message: error instanceof Error ? error.message : "Recording unavailable."});
      }
      return true;
    },
    release(gesture: object) {if (owner === gesture) void seal(true);},
    cancel(gesture?: object) {
      if (gesture !== undefined && owner !== gesture) return Promise.resolve();
      automatic = false;
      if (state.phase === "permission") {generation++; owner = null; publish({phase: "idle"});}
      const sealed = seal(false, "Recording interrupted. Save or discard this take.");
      return Promise.all([sealed, saving, ...preparing]).then(() => {});
    },
    save,
    discard() {
      if (state.phase !== "review") return;
      generation++; buffer = null; publish({phase: "idle", target: null, frames: 0, message: null});
    },
  };
}
