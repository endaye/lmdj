# Web Runtime L2 macOS Chrome Pointer Evidence — 1.0.40.0

## Evidence boundary

This record converts exactly Family L row L2, **macOS Chrome Pointer
performance**, from `deferred / unverified` to `PASS` for the exact tested
source identity below. It does not pass the five-row Web physical matrix:
L3–L5 remain `unverified`. It does not claim a tag, Release, deployment,
publication, or Channel promotion.

The run used the product-neutral Web Runtime Lab from a local source checkout.
The Product manifest identity was `1.0.40.0`; the run was not performed from a
promoted Channel artifact, so its Channel is recorded as `none (local source)`.

| Field | Value |
| --- | --- |
| Product Build / Channel | `1.0.40.0` / `none (local source)` |
| Tested source revision | `5c094c98d0dda26a5c8716758bcb1fb3bfdc0fcc` |
| Web Runtime Lab | unversioned experimental Host under `apps/web-runtime-lab/` |
| Related Assembly identities | Web Runtime Platform `2.0.1`; Audio Runtime `2.0.1`; Formal Web Runtime Host `2.1.1` |
| Assembly Lock SHA-256 | `c36a0ee7565f8ebb8152c4274b7cb47c3824e2232c9a7b059ae766bbcb436e7c` |
| Host OS | macOS `26.6.2` (`25G83`) |
| Browser | Chrome `151.0.7922.174` (`7922.174`) |
| Device class | MacBook Pro; no serial or stable device identifier retained |
| Input | built-in Force Touch trackpad, press-to-click |
| Output | built-in, 48 kHz |
| Session | `93b6a804-2343-48c1-853c-167b19f01eb2` |
| Observer | endaye, physical run on 2026-08-31 |

## Retained evidence

The raw browser report and high-speed capture remain under operator control.
The video is not committed because it is 1.66 GB and contains private
QuickTime device and location metadata. Only privacy-bounded derived
observations and the cumulative evaluator dossier are retained in Git.

| Artifact | Retention | SHA-256 |
| --- | --- | --- |
| Browser report `web-runtime-lab-93b6a804-2343-48c1-853c-167b19f01eb2.json` | operator-local | `031eaf1a65951649fe60e46724c1566db26086ecea8352cbf184b614780a96a6` |
| High-speed capture `IMG_4356.mov` | operator-local | `40a6a28f01628578d25758062eaa3ce367f7471eabf386e06bff0a0f0fd3ac42` |
| [Derived 500-trigger timing observations](2026-08-31-web-runtime-l2-macos-chrome-pointer-1.0.40.0.timing.json) | repository | `34d1aa813998c00a92523291f290f0ccbb8974b800474a48d29e24b7b14cdf2e` |
| [Cumulative evaluator dossier](2026-08-31-web-runtime-l2-macos-chrome-pointer-1.0.40.0.evidence.json) | repository | `13b8d20e2768616d3f92c741483417c13c449fae3b34a5023435f3050fa47083` |

## Physical timing method

The iPhone capture contains 47,133 HEVC frames at 1920×1080. Its approximately
30 fps slow-motion presentation preserves the 240 fps capture frames at an
eight-times expanded timeline. Fitting all 500 JSON dispatch intervals to the
audio gives a slow-motion scale of `8.0001549253`; every event matched.

The Force Touch trackpad requires pressure to create the click while the finger
can remain in contact. As accepted for L1, the visible trigger marker is the
Chrome trigger-count transition produced synchronously by `pointerdown`, not a
new finger-contact edge. The conservative `20.833333 ms` calibration offset is:

- one 60 Hz display-refresh interval: `16.666667 ms`;
- one 240 fps capture frame: `4.166667 ms`.

Negative same-frame marker/onset ordering is clipped to zero before the offset
is added. Acoustic onset is the first externally recorded onset frame. No slow
sample or weak marker was excluded. The timing record retains all 500 marker
frames, onset frames, raw intervals, calibrated intervals, and marker scores.

Two independent fixed acoustic thresholds (`120` and `150`) each found exactly
500 onset regions. All 500 regions matched distinct browser dispatches; there
were no extra, missed, or duplicate onsets. All 500 primary marker frames were
unique. An independent narrower screen region reproduced the same marker frame
for all 20 weakest primary markers; the minimum primary marker score was
`18.8`, and no marker scored below `8`.

| Metric | Raw visible marker → onset | Calibrated Touch-to-Sound | Approved gate |
| --- | ---: | ---: | ---: |
| p50 | `25.000000 ms` | `45.833333 ms` | informational |
| p95 | `29.166667 ms` | `50.000000 ms` | `<= 50 ms` |
| p99 | `33.333333 ms` | `54.166667 ms` | `<= 80 ms` |
| maximum | `33.333333 ms` | `54.166667 ms` | informational |
| triggers / missed / duplicate | `500 / 0 / 0` | `500 / 0 / 0` | `500 / 0 / 0` |

Percentiles use the repository evaluator's nearest-rank convention. The p95
result is exactly on, and therefore passes, the inclusive `<= 50 ms` gate.

## Foreground stability

Audio first reached `running` at `96961.395 ms`. The 500th pointer dispatch
occurred at `285847.655 ms`, or `188886.260 ms` (`3:08.886`) after audio
activation. The retained conservative foreground duration is `700184.605 ms`
(`11:40.185`), exceeding the ten-minute gate by `100.185 s`.

There was no hidden, frozen, pagehide, route-change, or non-running transition
after audio activation. The browser report retains 500 dispatches and 500
acknowledgements, zero lost or duplicate acknowledgements, zero ring-full
drops, zero processor errors, AudioContext `running`, render quantum `128`, and
262,782 processor callbacks. No underrun was detected.

An earlier attempt was interrupted by an operating-system popup after 214 of
500 triggers. The Lab marked it `restart-required`; that entire session was
discarded. This evidence uses one fresh, distinct 500-trigger session and does
not splice any data from the invalid attempt.

## Evaluator result

The cumulative retained dossier was evaluated with:

```bash
scripts/web-runtime-lab.sh evaluate \
  docs/release-evidence/2026-08-31-web-runtime-l2-macos-chrome-pointer-1.0.40.0.evidence.json
```

The evaluator returns exit `2` and overall `unverified`, as required while
three rows are missing. Its L1 and L2 row results are `passed` with empty reason
lists; L3–L5 are each `unverified: physical-run-missing`. There are no failed
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
