# Web Runtime L5 iPadOS Safari Lifecycle Evidence — 1.0.40.0

## Evidence boundary

This record converts exactly Family L row L5, **iPadOS Safari lifecycle and
route recovery**, from `deferred / unverified` to `PASS` for the exact tested
source and named physical device below. Together with the retained L1–L4
records, the repository evaluator now passes all five required Web physical
rows. This result does not claim a tag, Release, deployment, publication, or
Channel promotion.

The run used the product-neutral Web Runtime Lab from a local source checkout.
The Product manifest identity was `1.0.40.0`; the run was not performed from a
promoted Channel artifact, so its Channel is recorded as `none (local source)`.

| Field | Value |
| --- | --- |
| Product Build / Channel | `1.0.40.0` / `none (local source)` |
| Tested source revision | `67a7ac03d16f8a449ea47696779f8d6130b78e35` |
| Web Runtime Lab | unversioned experimental Host under `apps/web-runtime-lab/` |
| Related Assembly identities | Web Runtime Platform `2.0.1`; Audio Runtime `2.0.1`; Formal Web Runtime Host `2.1.1` |
| Assembly SHA-256 | `c36a0ee7565f8ebb8152c4274b7cb47c3824e2232c9a7b059ae766bbcb436e7c` |
| Host OS | iPadOS `26.6` |
| Browser | Safari `26.6` (system Safari bundled with iPadOS 26.6) |
| Device | iPad Air 13-inch (M3), model `A3268` |
| Input / output | physical touchscreen / built-in output, 48 kHz |
| Route interruption | iPadOS Voice Memos recording session |
| Session | `021e2f03-7ebf-427a-b7d4-e754c3fd74e9` |
| Observer | endaye, physical run on 2026-09-01 local time |

Safari requested desktop presentation, so the exported browser report carries
the compatibility values `MacIntel` and a macOS-shaped user agent. Those
values do not identify the physical device; the named iPad model and installed
OS above were read from the physical device during the run.

## Retained evidence

The raw browser report and high-speed capture remain under operator control.
The video is not committed because it is 2.55 GiB and contains private
QuickTime device and location metadata. Only privacy-bounded derived
observations and the cumulative evaluator dossier are retained in Git.

| Artifact | Retention | SHA-256 |
| --- | --- | --- |
| Browser report `web-runtime-lab-021e2f03-7ebf-427a-b7d4-e754c3fd74e9.json` (4,478 bytes) | operator-local | `40776203e551e5ebb1bf9932e4d46ce1a5f1d22cf0c9882bb8fb7f7b8be45b8c` |
| High-speed capture `IMG_4366.mov` (2,736,430,521 bytes) | operator-local | `b6b72b815fb4052c66418168240daf1daa6736857dbe687766856b1301950a31` |
| [Derived lifecycle observations](2026-09-01-web-runtime-l5-ipados-safari-lifecycle-1.0.40.0.timing.json) | repository | `d1b6f2a4416b263e1050d2a1af300f4bfe6a7b1c908c76150f39c789a86f98a6` |
| [Cumulative evaluator dossier](2026-09-01-web-runtime-l5-ipados-safari-lifecycle-1.0.40.0.evidence.json) | repository | `d469395bb7dc5a7b52ef7195a7517c2837f3fd95f6118c4549667e1c6bd30f8c` |

## Lifecycle journey

The fresh session began with one `Start audio` activation. AudioContext reached
`running` at `36459.860 ms`; the first deliberate touch at `40785.580 ms`
produced one acknowledgement and one retained acoustic onset. The operator then
completed the required uninterrupted journey:

| Episode | Browser evidence | Physical evidence | Recovery |
| --- | --- | --- | --- |
| Background → foreground | hidden `47724.280 ms`; visible `103656.380 ms`; hidden for `55932.100 ms` | video shows Safari leaving and returning | one `Resume`; `interrupted → suspended → running` |
| Lock → unlock | hidden `152567.520 ms`; visible `222918.300 ms`; hidden for `70350.780 ms` | video shows physical lock and unlock | one `Resume`; `interrupted → running` |
| Route interruption | hidden `282069.160 ms`; visible `294233.540 ms`; hidden for `12164.380 ms` | video shows a Voice Memos recording session, then Safari return | one `Resume`; `interrupted → suspended → running` |

The formal Host design permits a session to be interrupted and reactivated
multiple times; its limit is **at most one explicit activation for each
interruption**. Each of the three episodes required exactly one activation, so
the retained `maxExplicitActivations` is `1`, not the session-wide sum `3`.

The capture contains 73,662 HEVC frames at 1920×1080. Its approximately 30 fps
slow-motion presentation preserves the 240 fps source frames on an eight-times
expanded timeline. Recovery samples retain conservative frame-quantized upper
bounds. The two `suspended → running` browser deltas are `74.320 ms` and
`80.960 ms`; one 60 Hz display refresh plus one capture frame is included, then
rounded upward to complete capture frames. The direct `interrupted → running`
episode is bounded from the visible activation release to the running control
state.

| Episode | Retained upper-bound frames | Activation → running | Approved gate |
| --- | ---: | ---: | ---: |
| Background → foreground | `23` | `95.833333 ms` | `<= 500 ms` |
| Lock → unlock | `12` | `50.000000 ms` | `<= 500 ms` |
| Route interruption | `25` | `104.166667 ms` | `<= 500 ms` |
| p95 (nearest-rank) | — | `104.166667 ms` | `<= 500 ms` |

No observation was excluded.

## Final onset and runtime observations

After the final recovery, AudioContext reached `running` at `304433.660 ms`.
The operator touched `Trigger pad` once at `316587.140 ms`; the Worklet returned
exactly one acknowledgement at `316592.120 ms`. Across the whole lifecycle run,
the report retains exactly two deliberate touch dispatches and two
acknowledgements, with zero missed or duplicate acknowledgements, zero ring-full
drops, zero processor errors, final AudioContext `running`, render quantum
`128`, and 21,877 processor callbacks.

The co-captured AAC track was checked in separate 30-second slow-motion windows
around the initial and final touches. At `-35 dB` with a `0.15 s` minimum
silence interval, each window contains exactly one non-silent probe-tone region.
Thus the final post-recovery result is zero missed onsets and zero duplicate
onsets.

## Evaluator result

The cumulative retained dossier was evaluated with:

```bash
scripts/web-runtime-lab.sh evaluate \
  docs/release-evidence/2026-09-01-web-runtime-l5-ipados-safari-lifecycle-1.0.40.0.evidence.json
```

The evaluator returns exit `0` and overall `passed`. L1, L2, L3, L4, and L5
all report `passed` with empty reason lists; `missingRows` and `failedRows` are
empty. This closes the Family L physical matrix only for the exact retained
rows and their named local-source revisions.

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
