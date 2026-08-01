# Web Runtime Lab Acceptance and Evidence Policy

## Purpose

`apps/web-runtime-lab/` is a product-neutral feasibility Host. It measures
browser realtime-audio capability and prepares physical device evidence. It
does not implement Creator UI, use Product Assembly, or change Core behavior.

The approved Touch-to-Sound threshold is documented in
[`2026-08-01-web-realtime-audio-threshold-decision.md`](../architecture/2026-08-01-web-realtime-audio-threshold-decision.md).
Approval freezes the threshold but does not pass the Spike. The physical gate
remains unverified until retained evidence for all five required rows is
evaluated by the separate local evaluator.

## Automated Gate

The repository gate proves:

- pure capability, percentile, and report behavior;
- stable browser-report fields with `decisionStatus: "threshold-approved"`;
- absence of a physical result field in the browser report;
- exact approved thresholds and five required physical-evidence rows;
- deterministic `passed`, `failed`, and `unverified` evaluator outcomes;
- Bluetooth, browser estimates, invalid data, and incomplete evidence cannot
  produce `passed`;
- loopback-only default serving;
- COOP, COEP, CORP, and no-store response headers;
- explicit and complete TLS arguments for LAN mode;
- presence of AudioWorklet, WebAssembly, SharedArrayBuffer/Atomics, Web MIDI,
  lifecycle, dynamic render-quantum, and privacy guards in the active lab;
- no dependency on retired Contracts, Product Assembly, Facade, or Core source.

It does not prove a browser can acquire a physical audio route, that an iPad
can recover from interruption, that a MIDI controller works, or that acoustic
latency is acceptable.

## Desktop Browser Smoke

The desktop Chromium smoke must start the loopback server, open the page in a
real browser, activate audio through the Start button, trigger the pad, and
export a report. The visible result must show:

- secure context and `crossOriginIsolated === true`;
- `AudioContext.state === "running"`;
- WebAssembly initialized inside the AudioWorklet;
- SharedArrayBuffer trigger and acknowledgement counts increase together;
- at least one non-zero observed render quantum size;
- physical measurement not recorded;
- decision threshold approved and physical gate unverified.

This smoke is current Chromium evidence only. It is not Safari, iPad, physical
MIDI, underrun, or acoustic evidence.

## Physical Matrix

Run all rows before making a Web/PWA launch-platform conclusion:

| Platform | Browser | Input | Output | Runs |
| --- | --- | --- | --- | --- |
| macOS | Safari | Pointer | Built-in or wired | 500 triggers plus 10-minute foreground run |
| macOS | Chrome | Pointer | Built-in or wired | 500 triggers plus 10-minute foreground run |
| macOS | Chrome | Physical MIDI | Built-in or wired | 500 MIDI events plus physical timing sample |
| iPadOS | Safari | Touch | Built-in or wired | 500 triggers plus 10-minute foreground run |
| iPadOS | Safari | Touch | Built-in or wired | background, foreground, lock, unlock, and route interruption |

Bluetooth may be measured in a separate row but is never substituted for a
required built-in or wired result.

## Physical Measurement Method

Use one of:

1. high-speed video at 240 fps or faster, with pad contact and acoustic onset
   visible/audible in the same recording; or
2. a calibrated wired electrical/loopback rig whose trigger marker and output
   onset share one clock.

For high-speed video, retain frame rate, frame index of contact, frame index of
onset, and any calibration offset. For loopback, retain sample rate, marker
sample, onset sample, and calibration offset. Record every excluded sample and
reason; do not remove slow observations merely to satisfy a percentile.

## Lifecycle Protocol

For each Safari/iPad run:

1. start audio with one explicit tap;
2. trigger one audible onset;
3. send Safari to background for 30 seconds and return;
4. lock the screen for 30 seconds and unlock;
5. perform one available route interruption, such as connecting/disconnecting
   a wired route or another system audio session;
6. record every `AudioContext` and document lifecycle transition;
7. if needed, use exactly one explicit recovery activation;
8. trigger once and require exactly one onset.

Unsupported or unreproducible interruption steps remain unverified; they are
not silently omitted or called passed.

## Physical Evidence Evaluation

Use `scripts/web-runtime-lab.sh evaluate EVIDENCE.json` only after retaining
the raw physical measurement record. The input is a local lab format with
`evidenceVersion: 1`; it is not a product or cross-language Contract and is not
Project Truth. The evaluator never reads a browser report as physical evidence.

Each required row must carry a distinct random v4 session ID, UTC timestamp,
exact OS/browser versions, fixed platform/browser/device/input identity,
built-in or wired route, sample rate, AudioContext state history, exposed
latency values, observed render quantum sizes, processor callback count, and
explicit error/unsupported-capability arrays. A performance row additionally
requires exactly 500 unique privacy-bounded trigger/acknowledgement records
whose input source and quantum size match the required row and runtime record.

Physical summaries require p50/p95/p99, trigger/miss/duplicate counts,
calibration offset, and either a high-speed-video method at 240 fps or faster,
or a positive-rate calibrated wired-loopback method. Aggregate threshold values
without the complete dossier remain `unverified`; a file path or hash does not
substitute for retained source frames/captures.

The command exits `0` only when all five required rows pass. A threshold
violation in any eligible required row exits `1` and returns `failed`, even if
other evidence is missing. Missing, duplicated, invalid, unsupported, or
ineligible-route evidence exits `2` and returns `unverified` when no measured
failure exists. Invalid command, file, or JSON input exits `64`.

## Report Privacy

Allowed:

- random per-session UUID;
- OS/browser version and broad device class;
- route category;
- sample rate and exposed latency estimates;
- note and velocity values;
- relative timing, lifecycle, counts, and errors.

Forbidden:

- persistent local identity;
- device serials or stable hardware identifiers;
- MIDI input name, manufacturer, or browser device ID;
- SysEx or raw MIDI message bytes;
- automatic upload or persistence;
- a physical result derived automatically from browser estimates or telemetry.

## Evidence States

- `automated-pass`: repository-only checks passed.
- `browser-smoke-pass`: one named browser completed the live smoke.
- `physical-measured`: a matrix row has retained physical observations.
- `unverified`: required evidence is absent or unsupported.
- `decision-approved`: the Product Owner approved the threshold before the
  physical runs.
- `physical-gate-passed`: all five required rows passed the approved gate.
- `physical-gate-failed`: at least one eligible required row violated the
  approved gate and requires product and architecture review.

These states are cumulative and non-substitutable. In particular,
`automated-pass` plus `browser-smoke-pass` is still not physical acceptance.
