# Web Runtime L1 macOS Safari Pointer Evidence — 1.0.36.0

## Evidence boundary

This record converts exactly Family L row L1, **macOS Safari Pointer
performance**, from `deferred / unverified` to `PASS` for the exact tested
source identity below. It does not pass the five-row Web physical matrix:
L2–L5 remain `unverified`. It does not claim a tag, Release, deployment,
publication, or Channel promotion.

The run used the product-neutral Web Runtime Lab from a local source checkout.
The Product manifest identity was `1.0.36.0`; the run was not performed from a
promoted Channel artifact, so its Channel is recorded as `none (local source)`.

| Field | Value |
| --- | --- |
| Product Build / Channel | `1.0.36.0` / `none (local source)` |
| Tested source revision | `703b339f64a727740fa7b609173a9d9918f77388` |
| Web Runtime Lab | unversioned experimental Host under `apps/web-runtime-lab/` |
| Related Assembly identities | Web Runtime Platform `0.3.6`; Audio Runtime `0.5.1`; Formal Web Runtime Host `1.2.15` |
| Assembly Lock SHA-256 | `6011009fd624614cb2198d1c13173f9be2a7bd6e6e901e40c855a633d64948cf` |
| Host OS | macOS `26.6.2` (`25G83`) |
| Browser | Safari `26.6.2` (`21624.5.1.11.3`) |
| Device class | MacBook Pro; no serial or stable device identifier retained |
| Input | built-in Force Touch trackpad, press-to-click |
| Output | built-in, 48 kHz |
| Session | `00e56cbc-5197-4eaf-aed4-376488193188` |
| Observer | endaye, physical run on 2026-08-26; timing-method confirmation on 2026-08-27 |

## Retained evidence

The raw browser report and high-speed capture remain under operator control.
The video is not committed because it is 6.0 GiB and contains private QuickTime
metadata. Only privacy-bounded derived observations and the evaluator dossier
are retained in Git.

| Artifact | Retention | SHA-256 |
| --- | --- | --- |
| Browser report `web-runtime-lab-00e56cbc-5197-4eaf-aed4-376488193188.json` | operator-local | `1b16c88b7985f89d5fa58f694cec4b14185844667522c60565ccf6aad46c4c81` |
| High-speed capture `IMG_4191.mov` | operator-local | `5d7f8839a8a7397cb03365e5fd8ff6f909a46d55554de42d3bfd8060947f7ef8` |
| [Derived 500-trigger timing observations](2026-08-27-web-runtime-l1-macos-safari-pointer-1.0.36.0.timing.json) | repository | `dbf935dc8aa82d55b7b74530d0730000cce16badd0258a8200293da0c15c1d39` |
| [Evaluator dossier](2026-08-27-web-runtime-l1-macos-safari-pointer-1.0.36.0.evidence.json) | repository | `76090225a8439343f7fe5b36b183395912544ccce33fe73ed389dd0b9add44bf` |

## Physical timing method

The iPhone capture contains 135,816 HEVC frames at 1920×1080. Its 30 fps
slow-motion presentation preserves the 240 fps capture frames at an eight-times
expanded timeline. Fitting all 500 JSON dispatch intervals to the audio gives a
slow-motion scale of `8.0001312778`; every event matched.

The Force Touch trackpad requires pressure to create the click while the finger
can remain in contact. The visible trigger marker is therefore the Safari
trigger-count transition produced synchronously by `pointerdown`, not a new
finger-contact edge. Product Owner confirmation on 2026-08-27 accepted this
visible marker with a conservative `20.833333 ms` calibration offset:

- one 60 Hz display-refresh interval: `16.666667 ms`;
- one 240 fps capture frame: `4.166667 ms`.

Negative one-frame marker/onset ordering from same-frame quantization is clipped
to zero before the offset is added. Acoustic onset is the first externally
recorded onset frame. No slow sample or weak marker was excluded. The timing
record retains all 500 marker frames, onset frames, raw intervals, calibrated
intervals, and marker scores.

Two independent acoustic-region thresholds each found exactly 500 onsets. All
500 regions matched distinct browser dispatches; there were no extra, missed,
or duplicate onsets.

| Metric | Raw visible marker → onset | Calibrated Touch-to-Sound | Approved gate |
| --- | ---: | ---: | ---: |
| p50 | `8.333333 ms` | `29.166667 ms` | informational |
| p95 | `16.666667 ms` | `37.500000 ms` | `<= 50 ms` |
| p99 | `33.333333 ms` | `54.166667 ms` | `<= 80 ms` |
| maximum | `45.833333 ms` | `66.666667 ms` | informational |
| triggers / missed / duplicate | `500 / 0 / 0` | `500 / 0 / 0` | `500 / 0 / 0` |

Percentiles use the repository evaluator's nearest-rank convention.

## Foreground stability and accepted post-target transition

Audio reached `running` at `59115.96 ms`. The 500th pointer dispatch occurred
at `617024.12 ms`, or `557908.16 ms` after audio activation. The first hidden
transition occurred at `696244.94 ms`, giving `637128.98 ms` of uninterrupted
visible/running foreground time: `10:37.129`, which exceeds the ten-minute gate
by `37.129 s`.

That hidden transition was an operator application switch after the target had
completed and before the report was exported. The current generic guidance
marks any post-start hiding as `restart-required`; the Product Owner explicitly
accepted this post-target transition as not invalidating the completed
ten-minute observation. This is a run-specific acceptance exception and does
not silently change the generic protocol for L2–L5.

The browser report retains 500 dispatches and 500 acknowledgements, zero lost
or duplicate acknowledgements, zero ring-full drops, zero processor errors,
AudioContext `running`, render quantum `128`, and 242,568 processor callbacks.
No underrun was detected during the accepted foreground interval.

## Evaluator result

The retained dossier was evaluated with:

```bash
scripts/web-runtime-lab.sh evaluate \
  docs/release-evidence/2026-08-27-web-runtime-l1-macos-safari-pointer-1.0.36.0.evidence.json
```

The evaluator returned exit `2` and overall `unverified`, as required while
four rows are missing. Its row result for
`macos-safari-pointer-performance` is `passed` with an empty reason list;
L2–L5 are each `unverified: physical-run-missing`. There are no failed rows.

## Source carry-forward check

The documentation base after the run is `8344992d`. The exact trigger-tree
comparison below is empty between the tested revision and that base; the four
intervening commits modify only documentation or CI outside the L1 trigger
set. This preserves the exact tested behavior while keeping the evidence bound
to its original revision.

```bash
git diff --name-only \
  703b339f64a727740fa7b609173a9d9918f77388..8344992d \
  -- apps/web-runtime-lab packages/audio-runtime packages/project-cooker \
     apps/web-runtime-host/src packages/web-runtime-platform/web/input_adapters.mjs \
     packages/web-runtime-platform/web/runtime_session.mjs \
     packages/web-runtime-platform/web/protocol.mjs \
     packages/web-runtime-platform/web/state_machine.mjs \
     apps/web-runtime-host/deploy apps/web-runtime-host/tools \
     apps/web-runtime-host/index.html tools/web-runtime contracts \
     packages/authoring-domain packages/application-facade packages/project-io
# no output
```

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
