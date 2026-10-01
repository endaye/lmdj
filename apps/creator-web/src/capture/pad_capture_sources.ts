import {browserCaptureDeps, CaptureController} from "./capture_controller";
import type {PadCaptureSource, PadCaptureHandle} from "./pad_capture";
import type {CreatorPerformanceRuntimeSession} from "../runtime/runtime_types";

export function createPadCaptureSources() {
  let granted = false;
  void navigator.permissions?.query({name: "microphone" as PermissionName}).then(permission => {
    granted = permission.state === "granted";
    permission.onchange = () => {granted = permission.state === "granted";};
  }).catch(() => {});
  return {
    microphoneGranted: () => granted,
    async prepareMicrophone() {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      for (const track of stream.getTracks()) track.stop();
      granted = true;
    },
    start(source: PadCaptureSource, session: CreatorPerformanceRuntimeSession | null,
      activation: Promise<boolean> | null, batch: (channels: Float32Array[]) => void,
      failed: (message: string) => void): Promise<PadCaptureHandle> {
      if (source === "master") return (async () => {
        if (activation !== null && !await activation) throw new Error("Playback audio is unavailable. Try again.");
        if (session === null) throw new Error("Internal recording is unavailable.");
        return session.startPerformanceMasterCapture({onBatch: channels => batch([...channels]),
          onFailure: () => failed("Internal recording interrupted. Save or discard this take."),
          onStopped: () => {},});
      })();
      // Create and resume within the native press, before the permission await.
      const context = new AudioContext({sampleRate: 48_000});
      const resumed = context.resume();
      const controller = new CaptureController({...browserCaptureDeps(), createContext: () => context}, {
        onBatch: channels => batch([channels[0]!]),
        onEnded: () => failed("Microphone disconnected. Save or discard this take."),
      });
      return (async () => {
        try {await Promise.all([resumed, controller.start()]); return {stop: () => controller.stop()};}
        catch (error) {
          await controller.stop().catch(() => {});
          await context.close().catch(() => {});
          throw error;
        }
      })();
    },
  };
}
