# Web Runtime L4 iPadOS Safari Touch Evidence — 1.0.40.0

## Evidence boundary

This record converts exactly Family L row L4, **iPadOS Safari touch
performance**, from `deferred / unverified` to `PASS` for the exact tested
source and named physical device below. It does not pass the five-row Web
physical matrix: L5 lifecycle and route recovery remains `unverified`. It does
not claim a tag, Release, deployment, publication, or Channel promotion.

The run used the product-neutral Web Runtime Lab from a local source checkout.
The Product manifest identity was `1.0.40.0`; the run was not performed from a
promoted Channel artifact, so its Channel is recorded as `none (local source)`.

| Field | Value |
| --- | --- |
| Product Build / Channel | `1.0.40.0` / `none (local source)` |
| Tested source revision | `e2cd0cf9b1c74c05f66a9cd43675e0048e1711e4` |
| Web Runtime Lab | unversioned experimental Host under `apps/web-runtime-lab/` |
| Related Assembly identities | Web Runtime Platform `2.0.1`; Audio Runtime `2.0.1`; Formal Web Runtime Host `2.1.1` |
| Assembly SHA-256 | `c36a0ee7565f8ebb8152c4274b7cb47c3824e2232c9a7b059ae766bbcb436e7c` |
| Host OS | iPadOS `26.6` |
| Browser | Safari `26.6` (system Safari bundled with iPadOS 26.6) |
| Device | iPad Air 13-inch (M3), model `A3268` |
| Input / output | physical touchscreen / built-in output, 48 kHz |
| Session | `89ee01d2-f08d-4025-8815-5902418d7269` |
| Observer | endaye, physical run on 2026-09-01 local time |

Safari requested desktop presentation, so the exported browser report carries
the compatibility values `MacIntel` and a macOS-shaped user agent. Those
values do not identify the physical device; the named iPad model and installed
OS above were read from the physical device during the run.

## Retained evidence

The raw browser report and high-speed capture remain under operator control.
The video is not committed because it is 1.30 GiB and contains private
QuickTime device and location metadata. Only privacy-bounded derived
observations and the cumulative evaluator dossier are retained in Git.

| Artifact | Retention | SHA-256 |
| --- | --- | --- |
| Browser report `web-runtime-lab-89ee01d2-f08d-4025-8815-5902418d7269.json` (253,458 bytes) | operator-local | `1cc3e159379c655e27ee908e04ef961c4aa353db8362f6df5c9a9a4de7567d6c` |
| High-speed capture `IMG_4363.mov` (1,391,092,384 bytes) | operator-local | `6f7da4a074b76535fd10b9e80cd367a907b4e1706fae955f0418c5bad7e5efea` |
| [Derived 500-trigger timing observations](2026-09-01-web-runtime-l4-ipados-safari-touch-1.0.40.0.timing.json) | repository | `9b58bf425c658ff1721fdf01c3845e54385440b6b5c90ad7ddefe5ed216f1afd` |
| [Cumulative evaluator dossier](2026-09-01-web-runtime-l4-ipados-safari-touch-1.0.40.0.evidence.json) | repository | `993be81bbd4c7098b92c4921e9ad515f257ddd2cd6612f8118348c59b4ecda4f` |

## Physical timing method

The iPhone capture contains 39,336 HEVC frames at 1920×1080. Its approximately
30 fps slow-motion presentation preserves the 240 fps capture frames on an
eight-times expanded timeline. The video track is variable-frame-rate around
periodic gaps, so every marker was mapped through its retained per-frame
presentation timestamp rather than assuming `frame / 30`. Fitting all 500
browser dispatch intervals to the visible Safari counter edges gives a
slow-motion scale of `8.000352`; all 500 strictly increasing counter markers
matched one-to-one.

The first visible Safari `triggers: N / 500` counter transition is the input
marker synchronously initiated by the touch `pointerdown` handler. The output
marker is the first sustained 110 Hz slow-motion spectral onset corresponding
to the Lab's 880 Hz probe tone, backtracked from one of 500 independently
detected high-amplitude tone regions. Nine independent region thresholds from
`180` through `300` each found exactly 500 tone regions. The primary onset
threshold is `60`; lower `40` and upper `80` sensitivity analyses also pass.

Because display paint may follow the audio onset, negative same-frame
marker/onset order is clipped to zero. A conservative positive calibration of
`20.833333 ms`—one 60 Hz display refresh interval plus one 240 fps capture
frame—is then applied to every observation. No trigger or timing record was
excluded. The timing record retains all 500 marker and onset positions, raw
intervals, calibrated intervals, clock-fit observations, and sensitivity
summaries.

| Metric | Raw visible marker → tone onset | Calibrated Touch-to-Sound | Approved gate |
| --- | ---: | ---: | ---: |
| p50 | `0.000000 ms` | `20.833333 ms` | informational |
| p95 | `0.395796 ms` | `21.229129 ms` | `<= 50 ms` |
| p99 | `10.750024 ms` | `31.583358 ms` | `<= 80 ms` |
| maximum | `12.708294 ms` | `33.541627 ms` | informational |
| triggers / missed / duplicate | `500 / 0 / 0` | `500 / 0 / 0` | `500 / 0 / 0` |

Percentiles use the repository evaluator's nearest-rank convention. With onset
thresholds `40` and `80`, calibrated p95/p99 are respectively
`20.895792 / 31.395856 ms` and `21.374964 / 31.875027 ms`; the conclusion is
unchanged.

## Browser and foreground observations

The report retains exactly 500 physical touch dispatches and 500
acknowledgements. Sequences `1` through `500` are unique; there were zero lost
or duplicate acknowledgements, zero ring-full drops, zero processor errors,
AudioContext `running`, render quantum `128`, and 322,811 processor callbacks.

Audio first reached `running` at `34180.480 ms`; the last retained output
timestamp was `895001.100 ms`. The resulting uninterrupted visible/running
foreground duration is `860820.620 ms` (`14:20.821`), above the required ten
minutes. The report contains no hidden, frozen, pagehide, route-change,
non-running, or error event after activation. This absence is valid for L4's
foreground performance run only; it does not exercise or pass the deliberate
background, lock, unlock, and route-interruption journey required by L5.

## Evaluator result

The cumulative retained dossier was evaluated with:

```bash
scripts/web-runtime-lab.sh evaluate \
  docs/release-evidence/2026-09-01-web-runtime-l4-ipados-safari-touch-1.0.40.0.evidence.json
```

The evaluator returns exit `2` and overall `unverified`, as required while one
row is missing. Its L1, L2, L3, and L4 row results are `passed` with empty
reason lists; L5 is `unverified: physical-run-missing`. There are no failed
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
