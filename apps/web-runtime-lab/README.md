# Web Realtime Audio Lab

This product-neutral experimental Host measures whether a browser can run the
realtime primitives needed for a later Web Host. It does not use Product
Assembly or the Application Facade, and it does not change Core behavior.

The Touch-to-Sound threshold is **Approved**, while the physical gate remains
**Unverified**. Browser event-to-render acknowledgements are not physical
Touch-to-Sound evidence, and the browser report never reports a physical gate
result. Physical acoustic onset is collected with the separate protocol in
[`docs/quality/web-runtime-lab-acceptance.md`](../../docs/quality/web-runtime-lab-acceptance.md).

## Local operation

From the repository root, run the automated gate:

```bash
scripts/web-runtime-lab.sh test
```

Start the loopback-only server:

```bash
scripts/web-runtime-lab.sh serve --port 4173
```

Open <http://127.0.0.1:4173> and choose **Built-in** or **Wired** before
selecting **Start audio**; Start remains disabled for Unknown, USB, and
Bluetooth. Audio creation and resume are intentionally tied to explicit
buttons. **Trigger pad** uses the same bounded shared ring as MIDI note-on
events. **Export report** downloads one local JSON report.

Browser reports use local `reportVersion: 2`. Pointer Events with
`pointerType: "touch"` are retained as `touch`; desktop mouse/pen input remains
`pointer`, and MIDI remains `midi`. The report retains every privacy-bounded
dispatch separately from acknowledgement estimates, so a missing
acknowledgement does not erase the original trigger.

The server sets COOP, COEP, CORP, and `no-store` headers. A visible page or a
successful automated browser smoke is not physical Touch-to-Sound evidence.

## Guided physical browser run

The **Physical run guidance** card starts only after AudioContext reaches
`running` and displays exact progress toward 500 dispatches and 10:00 of
uninterrupted visible foreground time. At 500 Pointer/Touch dispatches the pad
button disables, and the enqueue path independently rejects every attempt after
dispatch 500; HTML disabled state is not the authoritative boundary. MIDI
remains under the physical controller's control.

The card shows `restart-required` after an acknowledgement remains missing
beyond a one-second grace window, duplicate acknowledgement, ring-full drop,
processor error, more than 500 dispatches,
AudioContext suspension, page hiding/freezing/pagehide, or a route-category
change after start. Reload the page before retaining another run; recovery does
not turn an interrupted performance run back into a valid foreground run.

`browser-target-ready` means only that the browser-side 500/10-minute target
was observed. It is ephemeral, is not exported in report v2, and is not a
physical pass. Retained 240 fps-or-faster high-speed video or calibrated wired
loopback evidence is still required. Export the report before leaving Safari;
switching applications before export records a foreground interruption.

## Evaluate retained physical evidence

### Prepare one run from an exported browser report

After a browser run, convert its local report into one physical-dossier draft:

```bash
scripts/web-runtime-lab.sh prepare \
  macos-safari-pointer-performance \
  /absolute/path/to/browser-report.json \
  --os-version "macOS exact installed version" \
  --browser-version "Safari exact installed version" \
  > /absolute/path/to/physical-run-draft.json
```

The command accepts only report v2 with an approved decision, built-in/wired
route, retained running AudioContext state, and complete runtime evidence. A
performance report must contain exactly 500 dispatches from the required
source. Missing acknowledgements remain explicit `null` values and retain
their loss count; they are not removed or synthesized. A MIDI row additionally
requires supported, granted, non-empty physical MIDI input evidence.

The preparer copies only the random session/time, fixed row identity, the two
explicit version strings, route/sample rate, runtime state, diagnostics, and
privacy-bounded trigger fields. It never copies user-agent, raw platform,
language, MIDI name/manufacturer/ID, arbitrary report fields, or local paths.
It writes JSON only to stdout; file redirection above is an explicit operator
choice.

Physical method, capture rate, calibration, physical percentiles, foreground
duration/underrun observations, and lifecycle recovery actions remain
`null`/empty. Therefore every prepared draft is `unverified` until retained
real-device observations are added. Old report v1 is rejected because it
cannot distinguish iPad touch from desktop pointer.

### Evaluate the completed five-row matrix

After all physical runs have been recorded, create a local JSON file with
`evidenceVersion: 1` and one entry in `runs` for each required key:

- `macos-safari-pointer-performance`;
- `macos-chrome-pointer-performance`;
- `macos-chrome-midi-performance`;
- `ipados-safari-touch-performance`;
- `ipados-safari-touch-lifecycle`.

Every run is a complete dossier, not only a threshold summary. It contains:

- a distinct random v4 `sessionId` and UTC `recordedAt`;
- `environment` with exact `platform`, `browser`, `osVersion`,
  `browserVersion`, broad `deviceClass`, `inputSource`, eligible
  `routeCategory` (`built-in` or `wired`), and positive `sampleRate`;
- `runtime` with `audioContextStateHistory`, nullable exposed latency values,
  non-empty `observedQuantumSizes`, and positive `processorCallbackCount`;
- explicit `errors` and `unsupportedCapabilities` arrays, both empty for a
  passing row.

Every performance row contains exactly 500 privacy-bounded `triggerRecords`.
Each record has a unique positive `sequence`, the required `source`, finite
non-negative `eventAtMs`, and either a non-negative `acknowledgementAtMs` plus
positive observed `quantumSize`, or explicit `null` values for both when the
acknowledgement was lost. It retains no MIDI device identity or raw message
bytes.

The `physical` object contains `method` (`high-speed-video` or
`wired-loopback`), `captureRateHz`, finite `calibrationOffsetMs`,
`triggerCount`, `p50Ms`, `p95Ms`, `p99Ms`, `missedOnsets`, and
`duplicateOnsets`. High-speed video must be at least 240 fps. The aggregate
trigger count must match the 500 retained trigger records.

Pointer/Touch performance rows also include a `foreground` object with
`durationMs`, `underruns`, `processorErrors`, `lostAcknowledgements`, and
`duplicateAcknowledgements`. The MIDI row instead adds `acknowledgements` with
trigger/acknowledgement counts plus lost and duplicate counts.

The lifecycle row contains all five actions (`background`, `foreground`,
`lock`, `unlock`, and `route-interruption`), a non-empty
`recoverySamplesMs` array, `maxExplicitActivations`, and post-recovery missed
and duplicate onset counts. Evaluate the file with:

```bash
scripts/web-runtime-lab.sh evaluate /absolute/path/to/evidence.json
```

The command prints deterministic JSON and exits `0` for `passed`, `1` for
`failed`, `2` for `unverified`, or `64` for invalid command/file/JSON input.
Only all five passing rows produce `passed`. A measured threshold violation
produces `failed`; missing, duplicate, ineligible-route, unsupported, or
invalid evidence remains `unverified`. Aggregate-only threshold values without
the retained dossier also remain `unverified`. Bluetooth rows may be retained
outside the required keys as informational evidence but cannot satisfy a
required row.

The evaluation JSON is a privacy-bounded index and summary of the retained
run. Keep original high-speed-video frames or wired-loopback captures and the
source browser report separately under operator control; the evaluator does
not persist or upload them and a hash/path is not treated as proof of content.

## Trusted HTTPS for a physical device

LAN binding is rejected unless both trusted TLS files are supplied:

```bash
scripts/web-runtime-lab.sh serve-lan \
  --bind 0.0.0.0 \
  --port 4173 \
  --cert-file /absolute/path/to/trusted-cert.pem \
  --key-file /absolute/path/to/key.pem
```

The certificate must be trusted by the physical device and valid for the host
used in its HTTPS URL. The server rejects symlinked certificate/key files. Do
not use an untrusted-certificate bypass as acceptance evidence.

## Evidence and privacy boundary

The report contains capability flags, browser environment strings, selected
route category, AudioContext metadata, observed render quantum sizes,
privacy-bounded trigger acknowledgements, aggregate MIDI counts, lifecycle
events, and diagnostics. `physicalMeasurement` remains `null`.

The browser report and prepared draft exclude:

- MIDI input names, manufacturers, serials, and stable IDs;
- SysEx data and raw MIDI messages;
- physical device serials and acoustic measurements;
- physical gate result fields;
- persistent browser storage: the lab uses no local, session, or database
  storage.

Downloaded reports remain local until the operator deliberately shares them.
Use the acceptance protocol for macOS Safari/Chrome, physical MIDI, iPadOS
Safari, lifecycle, and acoustic evidence.
