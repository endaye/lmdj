import {CAPTURE_WORKLET_NAME, CAPTURE_WORKLET_SOURCE} from "./capture_worklet_source";

export class CapturePermissionError extends Error {}

export interface CaptureListener {
  onBatch(channels: Float32Array[], peak: number): void;
  onEnded(reason: "device-lost" | "permission-revoked"): void;
}

export interface CaptureControllerDeps {
  getUserMedia(constraints: MediaStreamConstraints): Promise<MediaStream>;
  createContext(): AudioContext;
  createNode(context: AudioContext, name: string): AudioWorkletNode;
  createModuleUrl(source: string): string;
  revokeModuleUrl(url: string): void;
}

interface CaptureResources {
  track: MediaStreamTrack;
  node: AudioWorkletNode;
  source: MediaStreamAudioSourceNode;
  context: AudioContext;
  moduleUrl: string;
  onended: () => void;
}

export class CaptureController {
  readonly #deps: CaptureControllerDeps;
  readonly #listener: CaptureListener;
  #resources: CaptureResources | null = null;
  channelCount = 0;

  constructor(deps: CaptureControllerDeps, listener: CaptureListener) {
    this.#deps = deps;
    this.#listener = listener;
  }

  async start(): Promise<void> {
    if (this.#resources !== null) { throw new Error("Capture is already active"); }
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
    this.channelCount = track.getSettings().channelCount === 2 ? 2 : 1;
    const context = this.#deps.createContext();
    const moduleUrl = this.#deps.createModuleUrl(CAPTURE_WORKLET_SOURCE);
    await context.audioWorklet.addModule(moduleUrl);
    const source = context.createMediaStreamSource(stream);
    const node = this.#deps.createNode(context, CAPTURE_WORKLET_NAME);
    node.port.onmessage = (event: MessageEvent) => {
      this.#listener.onBatch(event.data.channels, event.data.peak);
    };
    source.connect(node);
    const onended = () => this.#listener.onEnded("device-lost");
    track.addEventListener("ended", onended);
    this.#resources = {track, node, source, context, moduleUrl, onended};
  }

  async stop(): Promise<void> {
    const resources = this.#resources;
    if (resources === null) { return; }
    this.#resources = null;
    resources.track.removeEventListener("ended", resources.onended);
    resources.track.stop(); // microphone indicator goes dark here
    resources.node.port.onmessage = null;
    resources.node.disconnect();
    resources.source.disconnect();
    await resources.context.close();
    this.#deps.revokeModuleUrl(resources.moduleUrl);
  }
}

export function browserCaptureDeps(): CaptureControllerDeps {
  return {
    getUserMedia: (constraints) => navigator.mediaDevices.getUserMedia(constraints),
    createContext: () => new AudioContext({sampleRate: 48_000}),
    createNode: (context, name) => new AudioWorkletNode(context, name),
    createModuleUrl: (source) =>
      URL.createObjectURL(new Blob([source], {type: "text/javascript"})),
    revokeModuleUrl: (url) => URL.revokeObjectURL(url),
  };
}
