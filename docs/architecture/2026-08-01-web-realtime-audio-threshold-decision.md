# Web Realtime Audio Touch-to-Sound Threshold Decision

Status: Proposed - awaiting Product Owner approval

Date: 2026-08-01

Decision owner: Product Owner

Implementation owner: Core / Host engineering

## Decision Needed

The Web realtime-audio Spike needs a physical Touch-to-Sound threshold before
device measurements begin. The threshold decides whether Web/PWA remains a
credible launch platform or returns to product and architecture review. It
must not be derived retrospectively from observed results.

This document is a proposal. It does not update the product decision log and
must not be used to report the Spike as passed.

## Recommended Gate

### Physical non-Bluetooth Touch-to-Sound

- p95 at or below 50 ms;
- p99 at or below 80 ms;
- 500 triggers with zero missed onsets and zero duplicate onsets.

The physical interval starts at observable pad contact and ends at acoustic
onset or a calibrated wired loopback onset. Bluetooth results are reported as
informational evidence only and never pass or fail the launch-platform gate.

### Foreground stability

- 10 continuous foreground minutes;
- zero detected audio underruns;
- zero `processorerror` events;
- zero lost or duplicate SharedArrayBuffer trigger acknowledgements.

### Lifecycle recovery

- after a route, visibility, lock, or system interruption, the UI must show the
  real `AudioContext` state;
- recovery may require one explicit user activation and must never claim silent
  automatic recovery;
- p95 from that activation to `AudioContext.state === "running"` at or below
  500 ms;
- the first post-recovery trigger must produce exactly one onset.

## Evidence Layers

These layers are deliberately non-substitutable:

1. Capability and runtime telemetry proves secure context, cross-origin
   isolation, SharedArrayBuffer, AudioWorklet, WebAssembly, context state,
   observed render quantum sizes, and processor acknowledgements.
2. Browser-estimated timing records pointer or MIDI event time, render-frame
   acknowledgement, `baseLatency`, `outputLatency` when exposed, and
   `getOutputTimestamp()` when exposed. It is diagnostic evidence, not physical
   Touch-to-Sound.
3. Physical timing uses high-speed video with an audible/acoustic marker or a
   calibrated wired loopback. Only this layer can evaluate the proposed
   Touch-to-Sound gate.

The Web Audio specification explicitly separates graph processing latency from
additional output-device latency, so `baseLatency` alone cannot establish the
physical interval. AudioWorklet processing also uses an implementation-owned
render quantum; the lab records the observed size instead of assuming 128
frames.

## Required Device Matrix

| Platform | Browser | Input | Output | Required evidence |
| --- | --- | --- | --- | --- |
| macOS | Safari current | Pointer | Built-in or wired | 500-trigger physical run and foreground stability |
| macOS | Chrome current | Pointer | Built-in or wired | 500-trigger physical run and foreground stability |
| macOS | Chrome current | One physical MIDI controller | Built-in or wired | 500 MIDI events, trigger/ack parity, physical timing sample |
| iPadOS | Safari current | Touch | Built-in or wired | 500-trigger physical run and foreground stability |
| iPadOS | Safari current | Touch | Built-in or wired | Background/foreground, screen lock/unlock, and route interruption recovery |

“Current” means the exact installed version recorded on the evidence date. No
desktop emulation may be reported as iPad evidence.

## Measurement Record

Each run records:

- UTC timestamp and random per-run session ID;
- OS and browser version;
- broad device class, without serial number or stable device identifier;
- output route category: built-in, wired, USB, or Bluetooth;
- sample rate, context state history, `baseLatency`, and `outputLatency` when
  exposed;
- observed render quantum sizes and processor callback count;
- 500 trigger and acknowledgement records;
- physical method, capture rate, calibration offset, p50, p95, p99, misses, and
  duplicates;
- lifecycle actions and recovery observations;
- errors and unsupported capabilities without silent omission.

MIDI input names, manufacturers, IDs, serials, SysEx bytes, and raw messages are
not retained.

## Outcomes After Approval

- All required runs satisfy the approved gate: Web/PWA remains eligible for the
  next design stage.
- A required run exceeds the approved gate or loses/duplicates a trigger:
  return to product and architecture review before Creator UI or formal Web
  Host implementation.
- Evidence is missing, unsupported, or not physically measured: status remains
  unverified, not passed or failed.

## Approval Record

The proposal becomes effective only after the Product Owner explicitly
approves it. At that point a separate change will:

1. add the decision to `docs/prd/decision-log.md`;
2. change the matching row in `docs/prd/open-questions.md` from `待决`;
3. add approved threshold configuration and pass/fail evaluation to the lab;
4. allocate Product or Host version impact only if that later change affects a
   shipped product surface.

## Primary References

- [Web Audio API 1.1](https://webaudio.github.io/web-audio-api/)
- [Emscripten Wasm Audio Worklets](https://emscripten.org/docs/api_reference/wasm_audio_worklets.html)
- [Cross-Origin-Opener-Policy and isolation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy)
- [WebKit issue 273511: interrupted AudioContext on iPhone/iPad](https://bugs.webkit.org/show_bug.cgi?id=273511)
