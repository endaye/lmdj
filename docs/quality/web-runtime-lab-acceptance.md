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
- report v2 touch/pointer/MIDI source separation and retained dispatches;
- privacy-bounded report-to-dossier draft preparation;
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

### Performance-run browser guidance

For each performance row, reload the lab to create a fresh session, select the
eligible route, start audio once, and use the visible guidance card. It tracks
exactly 500 dispatches and 600,000 milliseconds of visible/running foreground
time. The Pointer/Touch pad disables after dispatch 500; stop a physical MIDI
source after its 500th dispatch.

Any acknowledgement still missing after a one-second grace window, duplicate
acknowledgement, ring-full drop, processor error, 501st dispatch,
AudioContext suspension, hidden/frozen/pagehide
transition, or route-category change after start produces `restart-required`.
Reload and repeat the complete run; do not splice two sessions together.

`browser-target-ready` is an operator cue only. It is not written to report v2
or evidence v1 and never replaces the retained high-speed-video or wired-
loopback measurement required below.

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

Prepare each run from its exported v2 browser report with:

```bash
scripts/web-runtime-lab.sh prepare \
  ROW_KEY REPORT.json \
  --os-version "exact installed OS version" \
  --browser-version "exact installed browser version"
```

The preparer emits one run to stdout and never writes or uploads it. It rejects
v1 reports, non-approved status, non-null browser physical fields, ineligible
routes, incomplete runtime records, wrong input source, and incomplete
performance dispatch sets. It strips user-agent, raw platform/language, MIDI
identity, local paths, and unknown fields. For a missing acknowledgement it
joins the retained dispatch to explicit `null` acknowledgement/quantum values
and preserves the loss count, so a measured failure is not silently omitted.

Prepared physical, foreground, and lifecycle observations remain incomplete;
preparation alone must evaluate as `unverified`. Exact OS/browser versions are
operator inputs because user-agent parsing is not accepted as exact evidence.

Use `scripts/web-runtime-lab.sh evaluate EVIDENCE.json` only after retaining
the raw physical measurement record. The input is a local lab format with
`evidenceVersion: 1`; it is not a product or cross-language Contract and is not
Project Truth. The evaluator never reads a browser report as physical evidence.

Each required row must carry a distinct random v4 session ID, UTC timestamp,
exact OS/browser versions, fixed platform/browser/device/input identity,
built-in or wired route, sample rate, AudioContext state history, exposed
latency values, observed render quantum sizes, processor callback count, and
explicit error/unsupported-capability arrays. A performance row additionally
requires exactly 500 unique privacy-bounded dispatch records whose input source
matches the required row. A missing acknowledgement retains `null` time and
quantum values and must match the recorded acknowledgement-loss count.

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
