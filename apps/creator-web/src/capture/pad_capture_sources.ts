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
      failed: (message: string) => void, signal?: AbortSignal,
      waitForActivation = false): Promise<PadCaptureHandle> {
      return (async () => {
        let context: AudioContext | null = null;
        let controller: CaptureController | null = null;
        let contextOwnedByController = false;
        let master: PadCaptureHandle | null = null;
        let cleanup: Promise<void> | null = null;
        const stopOwned = () => cleanup ??= (async () => {
          await controller?.stop().catch(() => {});
          if (!contextOwnedByController) await context?.close().catch(() => {});
          await master?.stop().catch(() => {});
        })();
        let rejectAbort!: (reason: Error) => void;
        const aborted = new Promise<never>((_resolve, reject) => {rejectAbort = reject;});
        // Master acquisition retains its cleanup barrier instead of racing
        // abort. An already-running source can therefore have no race waiter.
        void aborted.catch(() => {});
        const onAbort = () => {
          rejectAbort(new DOMException("Recording cancelled.", "AbortError"));
        };
        signal?.addEventListener("abort", onAbort, {once: true});
        try {
          if (signal?.aborted) throw new DOMException("Recording cancelled.", "AbortError");
          // Cold touch waits for its owned, legal release activation. No second
          // microphone context is created under a non-activating pointerdown.
          if ((source === "master" || waitForActivation) && activation !== null &&
              !await Promise.race([activation, aborted])) {
            throw new Error("Playback audio is unavailable. Try again.");
          }
          if (signal?.aborted) throw new DOMException("Recording cancelled.", "AbortError");
          if (source === "master") {
            if (session === null) throw new Error("Internal recording is unavailable.");
            master = await session.startPerformanceMasterCapture({
              onBatch: channels => batch([...channels]),
              onFailure: () => failed("Internal recording interrupted. Save or discard this take."),
              onStopped: () => {},
            });
            // Acquisition has no cancellation API. Retain this startup until
            // its late handle is owned and fully stopped; review must not
            // permit another take while the old Runtime capture is still live.
            if (signal?.aborted) throw new DOMException("Recording cancelled.", "AbortError");
            return master;
          }
          context = new AudioContext({sampleRate: 48_000});
          const resumed = context.resume();
          const ownedContext = context;
          controller = new CaptureController({...browserCaptureDeps(), createContext: () => {
            if (signal?.aborted) throw new DOMException("Recording cancelled.", "AbortError");
            contextOwnedByController = true;
            return ownedContext;
          }}, {
            onBatch: channels => batch([channels[0]!]),
            onEnded: () => failed("Microphone disconnected. Save or discard this take."),
          });
          await Promise.race([Promise.all([resumed, controller.start()]), aborted]);
          const ownedController = controller;
          return {stop: () => ownedController.stop()};
        }
        catch (error) {
          await stopOwned();
          throw error;
        }
        finally {signal?.removeEventListener("abort", onAbort);}
      })();
    },
  };
}
