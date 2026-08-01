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

Open <http://127.0.0.1:4173>, choose the output route category, and select
**Start audio**. Audio creation and resume are intentionally tied to explicit
buttons. **Trigger pad** uses the same bounded shared ring as MIDI note-on
events. **Export report** downloads one local JSON report.

The server sets COOP, COEP, CORP, and `no-store` headers. A visible page or a
successful automated browser smoke is not physical Touch-to-Sound evidence.

## Evaluate retained physical evidence

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
non-negative `eventAtMs` and `acknowledgementAtMs`, and a positive observed
`quantumSize`. It retains no MIDI device identity or raw message bytes.

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

The browser report excludes:

- MIDI input names, manufacturers, serials, and stable IDs;
- SysEx data and raw MIDI messages;
- physical device serials and acoustic measurements;
- physical gate result fields;
- persistent browser storage: the lab uses no local, session, or database
  storage.

Downloaded reports remain local until the operator deliberately shares them.
Use the acceptance protocol for macOS Safari/Chrome, physical MIDI, iPadOS
Safari, lifecycle, and acoustic evidence.
