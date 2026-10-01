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
    failed: (message: string) => void): Promise<PadCaptureHandle>;
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
  let stopping: Promise<void> | null = null;
  let automatic = false;
  let generation = 0;
  const publish = (patch: Partial<PadCaptureState>) => {
    state = {...state, ...patch}; deps.changed({...state});
  };
  async function save(retry = true) {
    if (state.phase !== "review" || buffer === null || state.target === null) return;
    const selection = audibleSelection(buffer);
    if (selection === null) {publish({message: "No sound recorded. Discard this take and try again."}); return;}
    publish({phase: "saving", message: null});
    try {
      await deps.commit(state.target, buffer, selection, retry);
      buffer = null; publish({phase: "idle", target: null, frames: 0});
    } catch (error) {
      publish({phase: "review", message: error instanceof Error ? error.message : "Unable to save this take."});
    }
  }
  function seal(commit: boolean, message: string | null = null) {
    if (!["starting", "recording", "stopping"].includes(state.phase)) return Promise.resolve();
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
      finally {startup = null; stopping = null; publish({phase: "review"});}
      if (automatic) await save(false);
    })();
    return stopping;
  }
  return {
    getState: () => ({...state}),
    setSource(next: PadCaptureSource) {
      if (state.phase !== "idle") return;
      publish({source: next});
    },
    press(target: PadCaptureTarget, gesture: object) {
      if (state.phase !== "idle" || !deps.canStart(target)) return false;
      if (state.source === "microphone" && !deps.microphoneGranted()) {
        const token = ++generation;
        publish({phase: "permission", message: "Allow microphone access, then press an empty Pad again."});
        void deps.prepareMicrophone().then(() => {
          if (token === generation) publish({phase: "idle", message: "Microphone ready. Press an empty Pad to record."});
        }, error => {
          if (token === generation) publish({phase: "idle", message: error instanceof Error ? error.message : "Microphone unavailable."});
        });
        return true;
      }
      owner = gesture; automatic = false;
      buffer = new CaptureBuffer(state.source === "master" ? 2 : 1);
      publish({phase: "starting", target: {...target}, frames: 0, message: null});
      try {
        startup = deps.start(state.source, channels => {
          if (buffer === null || !["starting", "recording", "stopping"].includes(state.phase)) return;
          try {
            buffer.append(channels); publish({frames: buffer.frameCount});
            if (buffer.atCapacity) void seal(false, "60-second limit reached. Save or discard this take.");
          } catch {void seal(false, "Recording input changed. Save or discard this take.");}
        }, message => {void seal(false, message);});
        void startup.then(() => {
          if (state.phase === "starting") publish({phase: "recording"});
        }, error => {void seal(false, error instanceof Error ? error.message : "Recording unavailable.");});
      } catch (error) {
        startup = null; owner = null;
        publish({phase: "review", message: error instanceof Error ? error.message : "Recording unavailable."});
      }
      return true;
    },
    release(gesture: object) {if (owner === gesture) void seal(true);},
    cancel() {
      if (state.phase === "permission") {generation++; publish({phase: "idle"});}
      return seal(false, "Recording interrupted. Save or discard this take.");
    },
    save,
    discard() {
      if (state.phase !== "review") return;
      buffer = null; publish({phase: "idle", target: null, frames: 0, message: null});
    },
  };
}
