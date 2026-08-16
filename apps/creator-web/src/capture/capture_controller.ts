import {CAPTURE_WORKLET_NAME} from "./capture_worklet_source";
// Resolved by the bundler to the same-origin hashed asset URL of the shipped
// worklet file. The distribution CSP (`script-src 'self'`) rejects blob: and
// data: worklet modules, so a same-origin URL is the only loadable form in the
// packaged Creator.
// ?no-inline: Vite would otherwise inline a file this small as a data: URL,
// which the CSP rejects exactly like blob:.
import captureWorkletUrl from "./capture_worklet.js?url&no-inline";

export class CapturePermissionError extends Error {}

export interface CaptureListener {
  onBatch(channels: Float32Array[], peak: number): void;
  onEnded(reason: "device-lost"): void;
}

export interface CaptureControllerDeps {
  getUserMedia(constraints: MediaStreamConstraints): Promise<MediaStream>;
  createContext(): AudioContext;
  createNode(context: AudioContext, name: string): AudioWorkletNode;
  workletModuleUrl(): string;
}

interface CaptureResources {
  track: MediaStreamTrack;
  node: AudioWorkletNode;
  source: MediaStreamAudioSourceNode;
  context: AudioContext;
  onended: () => void;
}

export class CaptureController {
  readonly #deps: CaptureControllerDeps;
  readonly #listener: CaptureListener;
  #resources: CaptureResources | null = null;
  #starting: Promise<void> | null = null;

  constructor(deps: CaptureControllerDeps, listener: CaptureListener) {
    this.#deps = deps;
    this.#listener = listener;
  }

  // start() publishes the in-flight promise so stop() can await it. Without
  // this, a stop() arriving mid-start finds #resources still null, no-ops, and
  // the microphone goes live afterwards with no owner able to release it.
  async start(): Promise<void> {
    if (this.#resources !== null || this.#starting !== null) {
      throw new Error("Capture is already active");
    }
    const startup = this.#startInternal();
    this.#starting = startup;
    try {
      await startup;
    } finally {
      this.#starting = null;
    }
  }

  async #startInternal(): Promise<void> {
    let stream: MediaStream;
    try {
      stream = await this.#deps.getUserMedia({audio: {
        echoCancellation: false, noiseSuppression: false, autoGainControl: false,
      }});
    } catch (error) {
      throw new CapturePermissionError(
        error instanceof DOMException ? error.name : "getUserMedia failed");
    }
    const track = stream.getAudioTracks()[0];
    if (track === undefined) { throw new Error("Capture stream has no audio track"); }
    // The stream is live from here on. Any setup failure below must release it,
    // or the microphone stays on with no owner able to stop it: stop() would
    // find #resources === null and silently no-op (design §7, single owner).
    let context: AudioContext | undefined;
    try {
      context = this.#deps.createContext();
      await context.audioWorklet.addModule(this.#deps.workletModuleUrl());
      const source = context.createMediaStreamSource(stream);
      const node = this.#deps.createNode(context, CAPTURE_WORKLET_NAME);
      node.port.onmessage = (event: MessageEvent) => {
        this.#listener.onBatch(event.data.channels, event.data.peak);
      };
      source.connect(node);
      const onended = () => this.#listener.onEnded("device-lost");
      track.addEventListener("ended", onended);
      this.#resources = {track, node, source, context, onended};
    } catch (error) {
      // Best-effort release: a throw while cleaning up must never replace the
      // original error, or the real cause of the capture failure is lost.
      try { track.stop(); } catch { /* track already dead */ }
      if (context !== undefined) {
        try { await context.close(); } catch { /* already closing */ }
      }
      throw error;
    }
  }

  async stop(): Promise<void> {
    // Wait out an in-flight start() so its resources exist to be released;
    // its own failure is not this call's concern.
    const startup = this.#starting;
    if (startup !== null) { await startup.catch(() => {}); }
    const resources = this.#resources;
    if (resources === null) { return; }
    this.#resources = null;
    resources.track.removeEventListener("ended", resources.onended);
    resources.track.stop(); // microphone indicator goes dark here
    resources.node.port.onmessage = null;
    resources.node.disconnect();
    resources.source.disconnect();
    await resources.context.close();
  }
}

export function browserCaptureDeps(): CaptureControllerDeps {
  return {
    getUserMedia: (constraints) => navigator.mediaDevices.getUserMedia(constraints),
    createContext: () => new AudioContext({sampleRate: 48_000}),
    createNode: (context, name) => new AudioWorkletNode(context, name),
    workletModuleUrl: () => captureWorkletUrl,
  };
}
