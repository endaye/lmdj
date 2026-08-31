# Web Runtime L3 macOS Chrome Physical MIDI Evidence — 1.0.40.0

## Evidence boundary

This record converts exactly Family L row L3, **macOS Chrome physical MIDI
performance**, from `deferred / unverified` to `PASS` for the exact tested
source identity below. It does not pass the five-row Web physical matrix:
L4–L5 remain `unverified`. It does not claim a tag, Release, deployment,
publication, or Channel promotion.

The run used the product-neutral Web Runtime Lab from a local source checkout.
The Product manifest identity was `1.0.40.0`; the run was not performed from a
promoted Channel artifact, so its Channel is recorded as `none (local source)`.

| Field | Value |
| --- | --- |
| Product Build / Channel | `1.0.40.0` / `none (local source)` |
| Tested source revision | `1869a925399a61d135ef16ae0b17926a4b5212b6` |
| Web Runtime Lab | unversioned experimental Host under `apps/web-runtime-lab/` |
| Related Assembly identities | Web Runtime Platform `2.0.1`; Audio Runtime `2.0.1`; Formal Web Runtime Host `2.1.1` |
| Assembly SHA-256 | `c36a0ee7565f8ebb8152c4274b7cb47c3824e2232c9a7b059ae766bbcb436e7c` |
| Host OS | macOS `26.6.2` (`25G83`) |
| Browser | Chrome `151.0.7922.174` (`7922.174`) |
| Device class | MacBook Pro; no serial or stable device identifier retained |
| Input | physical Akai MPD218 USB MIDI pad; device identifiers not retained |
| Output | built-in, 48 kHz |
| Session | `444f33ee-19ac-45d5-b34a-db7e74484c36` |
| Observer | endaye, physical run on 2026-08-31 |

## Retained evidence

The raw browser report and high-speed capture remain under operator control.
The video is not committed because it is 1.75 GB and contains private
QuickTime device and location metadata. Only privacy-bounded derived
observations and the cumulative evaluator dossier are retained in Git.

| Artifact | Retention | SHA-256 |
| --- | --- | --- |
| Browser report `web-runtime-lab-444f33ee-19ac-45d5-b34a-db7e74484c36.json` | operator-local | `bf5cbf174d51fc0da1089311e0f6328ba6aab1a53d9d33a7788759e169907708` |
| High-speed capture `IMG_4360.mov` | operator-local | `89ca9e8257339fe700eaa4b2013e8312ad6796a4c8f9457fef73cc340d1ed876` |
| [Derived 500-trigger timing observations](2026-08-31-web-runtime-l3-macos-chrome-midi-1.0.40.0.timing.json) | repository | `cb2849a0b9474ea93595e19b977c4e6a0e92bfd443d35dacbb0da87a3f281915` |
| [Cumulative evaluator dossier](2026-08-31-web-runtime-l3-macos-chrome-midi-1.0.40.0.evidence.json) | repository | `e5dc390e76ca54f610d5a1af2f12052f2e749bf5ee87bd18979cfe1924657cb3` |

## Physical timing method

The iPhone capture contains 39,262 HEVC frames at 1920×1080. Its approximately
30 fps slow-motion presentation preserves the 240 fps capture frames at an
eight-times expanded timeline. Fitting all 500 JSON MIDI dispatch intervals to
the MPD218 LED edges gives a slow-motion scale of `8.0001593091`; every event
matched.

The first visible red LED frame on the physical MPD218 is the input marker.
Six independent fixed red-channel thresholds (`160`, `170`, `175`, `180`,
`185`, and `190`) each found exactly 500 distinct LED pulses. The externally
recorded output marker is the first sustained 110 Hz slow-motion spectral
onset corresponding to the Lab's 880 Hz probe tone. The primary detector uses
a fixed amplitude threshold of `60`, backtracked from the dominant local tone
peak. A lower independent threshold of `40` also yields a passing p95 and p99.

The capture's video and audio tracks have a fixed alignment delay. The
co-captured mechanical pad-impact transient falls a median seven 240 fps
frames (`29.166667 ms`) after the visible LED edge at each of three independent
absolute-sample thresholds (`100`, `120`, and `150`). The applied signed
calibration is only six frames (`-25.000000 ms`), retaining one full 240 fps
frame as conservative A/V and marker-quantization uncertainty. No trigger or
timing record was excluded. The timing record retains all 500 LED regions,
tone-onset positions, raw intervals, calibrated intervals, and marker peaks.

| Metric | Raw LED marker → tone onset | Calibrated MIDI-to-Sound | Approved gate |
| --- | ---: | ---: | ---: |
| p50 | `67.187500 ms` | `42.187500 ms` | informational |
| p95 | `75.000000 ms` | `50.000000 ms` | `<= 50 ms` |
| p99 | `78.125000 ms` | `53.125000 ms` | `<= 80 ms` |
| maximum | `79.166667 ms` | `54.166667 ms` | informational |
| triggers / missed / duplicate | `500 / 0 / 0` | `500 / 0 / 0` | `500 / 0 / 0` |

Percentiles use the repository evaluator's nearest-rank convention. The p95
result is exactly on, and therefore passes, the inclusive `<= 50 ms` gate.
With the lower independent onset threshold, calibrated p50/p95/p99 are
`41.145833 / 45.312500 / 48.958333 ms`; the conclusion is unchanged.

## Browser and foreground observations

The browser report retains 500 physical MIDI events, 500 dispatch records, and
500 acknowledgements. Every dispatch source is `midi`; sequences `1` through
`500` are unique, and all 500 acknowledgement records retain exact note and
velocity parity with their dispatch. There were zero lost or duplicate
acknowledgements, zero ring-full drops, zero processor errors, AudioContext
`running`, render quantum `128`, and 253,020 processor callbacks.

Audio first reached `running` at `972205.440 ms`. The 500th MIDI dispatch
occurred `154857.480 ms` (`2:34.857`) later. Although L3 does not require the
ten-minute foreground field, the last output timestamp remained `running`
`674805.395 ms` (`11:14.805`) after activation. There was no hidden, pagehide,
route-change, or non-running transition after audio activation.

## Discarded diagnostics and Lab follow-up

A pre-run diagnostic session was invalid: one physical pad press produced four
browser events after MIDI had been enabled repeatedly. Repeated
`requestMIDIAccess()` calls can expose new input object identities, so the
current object-identity guard does not make repeated Enable actions idempotent.
That diagnostic session was discarded in full. The formal run used a fresh
reload, exactly one Enable MIDI action, and a one-pad-press-to-one-counter
preflight before recording; its 500 source MIDI events map one-to-one to 500
dispatches and acknowledgements. This evidence does not claim the Lab
robustness defect is fixed; it remains separate follow-up work.

## Evaluator result

The cumulative retained dossier was evaluated with:

```bash
scripts/web-runtime-lab.sh evaluate \
  docs/release-evidence/2026-08-31-web-runtime-l3-macos-chrome-midi-1.0.40.0.evidence.json
```

The evaluator returns exit `2` and overall `unverified`, as required while two
rows are missing. Its L1, L2, and L3 row results are `passed` with empty reason
lists; L4–L5 are each `unverified: physical-run-missing`. There are no failed
rows.

## Version and documentation impact

Version impact: none — this is validation evidence and changes no Product,
Module, Host, Provider, or Contract identity.

Documentation impact: required. Affected current portal routes are
`/hosts/overview/`, `/hosts/web-runtime/`, `/platform/input/`,
`/platform/web-runtime/`, and `/operations/testing-and-proof/`.

## External state

| Transition | Status |
| --- | --- |
| Local commit | pending at the time this record was authored |
| Push | not authorised / not performed |
| Pull Request | not authorised / not created |
| Merge | not authorised / not performed |
| Issue closure | not performed |
| Release, deployment, publication, Channel promotion | not authorised / not performed |
