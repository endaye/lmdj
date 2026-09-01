# Stage 8 M2 macOS Chrome human-hearing evidence — 1.0.40.0

## Evidence boundary

This record covers the macOS Chrome M2 human-hearing and subjective
audio-quality row requested by
[#239](https://github.com/endaye/lmdj/issues/239). The row is
**failed / unverified**: trim boundaries and every non-loop behavior exercised
cleanly, but both Loop Gate and Loop Toggle produced an audible click at every
repeat seam. The loop defect is tracked separately by
[#511](https://github.com/endaye/lmdj/issues/511); #239 and M2 must remain open
until a corrected candidate is rerun.

This result says nothing about Chrome physical MIDI, macOS Safari, iPadOS,
external audio interfaces, acoustic latency, a release transition, deployment,
or Channel promotion.

| Field | Value |
| --- | --- |
| Product Build | `1.0.40.0` |
| Tested Git revision | `bb0544c46d4b3fc3a7c96cb848e10cdecb4be040` |
| Creator / Platform / compatible Formal Host | `2.1.1` / `2.0.1` / `web-runtime-host 2.1.1` |
| Protocol version | `1` |
| Creator host manifest SHA-256 | `e934f7a3b452db3476fd722637be1c9a16761bbd10db08e534bc98268fc64310` |
| Host machine | MacBook Pro `MacBookPro17,1`; Apple M1; 16 GB |
| Host OS | macOS `26.6.2` (`25G83`), arm64 |
| Browser | Google Chrome `152.0.7977.65` |
| Output route | built-in `MacBook Pro Speakers`; stereo; 48 kHz; default system output |
| Operator | `endaye`, providing interactive hearing confirmations |
| Surface under test | exact packaged Creator distribution served locally at `http://127.0.0.1:4177` |
| Execution date | 2026-09-01, Asia/Shanghai |

## Fixture and package identity

The source fixture was `tests/fixtures/golden/one_bar_120bpm.wav`: 384044
bytes, 2.0 seconds, stereo, 48 kHz, signed 16-bit PCM, SHA-256
`d276060107ab2479126c4f66919b799593a852fe624720f03e7be3b70bcfe867`.
The portable Project fixture used for the run was 1133396 bytes, contained 64
assigned Pads backed by that source, and had SHA-256
`6ffa7240094328799865fd7d3cb5e859395ddaca5c91061a9e7d60d26472daee`.
Its content digest was
`3f0b9b0c2572eb26a43b87e6501712d45ee2b7c2164e31d6fbb4745f2ed912dd`.

The replacement fixture was `tests/fixtures/audio/kick.wav`: 9644 bytes,
0.1 seconds, mono, 48 kHz, signed 16-bit PCM, SHA-256
`43ab266faaaddc590b75ea49921574f795c8c7535d28453fda0b48b3f620bfb7`.

| Packaged file | SHA-256 |
| --- | --- |
| `index.html` | `0a75e485ae5347421332a1070b8e5e61ab3641d299f0a8f4a5d2148924395b2b` |
| Creator main JavaScript | `8ff45885fbf64814c3e042ca2b4e2a5c420ae4a5eb22c928bdbee770d55869b3` |
| Runtime JavaScript | `16d28888b606598dc0e45bf60a5582fc824b3b63831dd39cd45924425d694dc0` |
| Runtime Wasm | `169a5a07132b48c8bc93e92ab1394d16112576a2e379c3161dabd7f85c0d193d` |
| Creator styles | `3730bc44e66e7877b6ebce0e674e34101b41ef02a2cfc2ae0cd5d0c2ff8d3cb8` |
| Capture worklet | `17f658199d7f2142aa922cd2ab2cdf50699834157167d6cb8dbbae20a93a7e68` |

## Authoritative hearing checklist

The baseline comparison played the tracked source through macOS and then Pad
A1 through the packaged Creator. The operator heard both, judged them
consistent, and reported no anomaly. Outside the loop seams below, the
operator reported no click, gap, dropout, unintended silence, clipping,
pitch/duration error, or stereo-placement anomaly.

| Check | Exercise and far-side observation | Result |
| ---: | --- | --- |
| 1 | Commit a broad crop, then select and audition the strict non-zero-boundary region `0.505–0.545 s` (about 40 ms). The crop was audible and both non-zero endpoints were clean. This is the physical rerun of the prior F5/F6 trim failure. | **PASS** |
| 2 | Loop off, One Shot on: press and release A1. The voice played the selected content without release truncation or an audible anomaly. | **PASS** |
| 3 | Loop off, One Shot off (Gate): hold A1 for about 1.2 seconds, then release. Playback stopped on release without an audible release click. | **PASS** |
| 4 | Loop on, Hold off (Loop Gate): hold the approximately 40 ms non-zero selection for about one second, then release. Release stopped cleanly, but each loop repeat had an audible click. | **FAIL** — loop seam |
| 5 | Loop on, Hold on (Loop Toggle): press once, wait about one second, then press again. The second press stopped the latched voice correctly, but each loop repeat again had an audible click. | **FAIL** — loop seam reproduced |
| 6 | Compare default `0.0 dB` with `-11.7 dB`, then enable Mute. The lower level was clearly audible as lower, and Mute produced silence without an unintended residual voice. | **PASS** |
| 7 | Trigger Bank A Pads A1 through A16 sequentially while Audio remained `running`. All 16 produced their expected audible response; no Pad was silent or stuck. | **PASS** |
| 8 | Replace A16 with the short mono kick, compare A15 and A16, reload, reopen, reactivate Audio, and compare them again. A16 remained the distinct short kick, A15 retained the original stereo source, and both played after reload. | **PASS** |

After check 8, the reopened Project reported revision `81`, 64 of 64 assigned
Pads, and 2 Assets. A16 retained the replacement metadata `48 kHz · Mono ·
4,800 frames`; A15 retained `48 kHz · Stereo · 96,000 frames`. These are the
far-side observables for Replace and reload persistence, not merely UI action
acknowledgements.

## Blocking failure

The strict 40 ms selection deliberately placed both loop endpoints away from
zero. Its clean one-shot/trim playback shows that the 96-frame attack/release
ramp repaired the earlier trim-boundary click. Repeating the same selection in
both loop modes exposed the remaining discontinuity at the wrap boundary. Gate
release and Toggle stop were clean, localizing the audible failure to the loop
seam rather than stop behavior.

This is the behavior that the 2026-08-24 render-path decision explicitly
deferred pending M2 evaluation. It is now a measured physical failure, not an
expected-but-unperformed risk. #511 owns the implementation and deterministic
regression coverage; a fresh applicable Product Build must rerun check 5 before
M2 can pass.

## Report limitation

The Creator's `Export report` action did not yield a captured download during
this session, so there is no exported acceptance-report artifact or report
SHA-256 to claim. The retained evidence is the exact revision and package,
fixture and portable-bundle hashes above together with the operator's ordered
interactive observations. The missing report does not turn the measured loop
failure into an unperformed step.

## Outcome and next gate

Status: **FAILED / UNVERIFIED**. Six of eight checklist groups passed; Loop
Gate and Loop Toggle both reproduced the same blocking seam click. #239
remains open, and no physical-pass, Beta, or Stable claim may derive from this
run.

The next candidate must resolve #511, preserve the passing non-loop behavior,
and rerun the complete M2 checklist on one exact Product Build. The historical
2026-08-17 trim failure and this `1.0.40.0` loop failure both remain retained.

## Version and documentation impact

- Version impact: none — this Task records validation evidence only; #511 owns
  the implementation version cascade.
- Documentation impact: required — this evidence record, the Stage 8
  acceptance and manual-verification ledgers, and the current Creator/testing
  Portal routes retain the failed/unverified result.
