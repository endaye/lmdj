# Stage 8B M7 macOS Safari capture — failed on 1.0.41.0

## Outcome

**FAIL — #244 remains open.** On 2026-09-04, the normal microphone capture,
commit and playback round succeeded, but the required focus-loss round left the
Sample surface blank and removed every capture recovery control. The session
could not commit or discard the retained recording. The defect is tracked by
[#625](https://github.com/endaye/lmdj/issues/625).

No passing prefix from this attempt carries forward. After a fixed Product
Build is deployed, #244 must restart the complete M7 journey from the beginning.

## Exact test identity

| Field | Value |
| --- | --- |
| Date / operator | 2026-09-04 / endaye |
| Deployed surface | `https://lmdj-creator.netlify.app/` |
| Product Build | `1.0.41.0` |
| Packaged Creator revision | `98ffec723cc88ecaacc733c4682d17df9a014bfc` |
| Creator / platform / web runtime host | `2.1.1` / `2.0.1` / `2.1.1` |
| Host manifest SHA-256 | `f47c017edf82b0511b176f8fb8f13d034821d02b1aa0b5ddb29304b100e925b1` |
| Project | `00000000-0000-4000-8000-000000000245` |
| Device | MacBook Pro `Mac16,8`, Apple M4 Pro, 48 GB |
| OS / browser | macOS `26.6.2 (25G83)` / Safari `26.6.2 (21624.5.1.11.3)` |
| Input / output | MacBook Pro Microphone, 48 kHz / MacBook Pro Speakers, stereo, 48 kHz |

## Observations

### Normal round

The operator recorded speech into A16 with the built-in microphone, observed a
live non-zero level and waveform, stopped, committed, and played the result.
The committed asset reported `48 kHz · Stereo · 451,200 frames` (about 9.4 s),
and Project revision advanced from 83 to 84. The operator confirmed clear
playback with the expected pitch and duration and no clipping, stereo anomaly,
click, gap or dropout.

### Focus-loss round

The operator began another non-zero recording on A15, spoke, switched away with
Command-Tab for about two seconds, and returned. The expected trim dialog,
focus-loss explanation, waveform, and commit/discard controls were absent.
Safari showed only the application header, a `recovering` / `Audio recovering`
status, the narrow mode rail, and an otherwise blank Sample surface. The
accessibility state retained values `0` and `96000`, consistent with roughly two
seconds of captured frames, but exposed no usable capture dialog or recovery
action.

The operator-supplied screenshot is 1720 × 1904 pixels with SHA-256
`78402b5af22bd24675d62e4d737a37f8674b7906a0244d991951a3f8e653e1cb`.
The screenshot remained external to the repository; this record retains its
hash, dimensions, and the independently exported acceptance report.

## Exported report

The downloaded report is retained byte-for-byte as
[`2026-09-04-stage8b-m7-macos-safari-capture-1.0.41.0.report.json`](2026-09-04-stage8b-m7-macos-safari-capture-1.0.41.0.report.json),
SHA-256 `dcda976fa6de325eac2c18c203db75fd93e1643edb784453530a649af913bd6e`.
It records:

- application state `recovering`;
- Project and Runtime revision 84;
- Sequence semantic state `trim-overlay` with `session_id: null`;
- 6 admitted triggers, 6 outcomes, 0 rejections, and no top-level error code;
- `secure_context`, `cross_origin_isolated`, `shared_array_buffer`,
  `audio_worklet`, OPFS and sync-access capabilities available.

## Defect evidence and boundary

The report and source inspection point to a presentation/state integration
defect, not a microphone-permission or AudioWorklet capability failure. Capture
correctly retains frames and enters trimming after `blur`, while the application
also applies the Sequence `trim-overlay` state. The overlay CSS hides every
direct Sample-surface child except a direct `.capture-panel-dialog`, but the
actual dialog is nested inside `.sample-modal-backdrop`; the backdrop and dialog
therefore disappear together. #625 owns the product fix and an integrated
Chromium/WebKit regression that preserves the armed-Pad Sequence behavior.

This evidence task changes no Product Build, Module, Provider or Contract
identity. Version impact: none. Documentation impact: required for the Stage 8B
M7 ledger, consolidated manual TODO, outstanding-work record, and the current
`/hosts/creator-web` and `/operations/testing-and-proof` Portal routes. Pitfall
impact: none; this is a product defect whose invariant belongs in regression
tests.
