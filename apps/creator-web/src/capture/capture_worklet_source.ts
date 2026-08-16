// The processor itself lives in capture_worklet.js as a real same-origin
// distribution asset: the hardened distribution CSP (`script-src 'self'`)
// governs AudioWorklet module loading and rejects blob:/data: URLs, so an
// inlined source string cannot load in the packaged Creator. The raw re-export
// below lets unit tests evaluate the exact shipped bytes, and the constants
// here are the TypeScript-side mirror, pinned to the file by a unit test.
import workletSource from "./capture_worklet.js?raw";

export const CAPTURE_WORKLET_NAME = "lmdj-capture-recorder";
export const CAPTURE_BATCH_FRAMES = 4_800;
export const CAPTURE_WORKLET_SOURCE: string = workletSource;
