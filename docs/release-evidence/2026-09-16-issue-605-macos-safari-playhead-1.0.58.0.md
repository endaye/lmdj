# Issue #605 macOS Safari Sample playhead physical acceptance — 1.0.58.0

## Evidence boundary

Status: **PASS** for the #605 playhead acceptance legs, with two adjacent
findings filed separately ([#1438](https://github.com/endaye/lmdj/issues/1438),
[#1440](https://github.com/endaye/lmdj/issues/1440)) that do not change the
playhead verdict.

This record retains the physical Safari acceptance of the #605 fix ("Sample
waveform playhead does not advance", fixed by
[#1417](https://github.com/endaye/lmdj/pull/1417), merge commit `cf0de6f4`).
The named operator performed the Pad triggers, mode toggles, trim edits and tab
switches in real macOS Safari and supplied the audible observations. The agent
prepared the environment, verified the fixture, recorded the screen, extracted
playhead trajectories from the recording and probed live DOM state; none of
that substituted for the operator's physical results.

| Field | Value |
| --- | --- |
| Product Build | `1.0.58.0` |
| Fix under test | `cf0de6f4` — `fix(creator): advance Sample waveform playhead (fixes #605) (#1417)` |
| Creator / Platform / compatible Formal Host | `4.3.1` / `5.3.0` / `web-runtime-host 4.3.0` |
| Protocol version | `1` |
| Creator host manifest SHA-256 | `b45ce0716c138384ac5702c57822a298a71ec3c32f1a3c48cf0878ccc34c626e` |
| Host machine | MacBook Pro `MacBookPro17,1`; Apple M1 |
| Host OS | macOS `27.0` (`26A428`), arm64 |
| Browser | Safari `27.0` |
| Operator | `endaye` |
| Surface under test | local proof server `tools/web-runtime/serve_distribution.py` at `http://127.0.0.1:8765/` |
| Execution date | 2026-09-16, Asia/Shanghai |

Served asset identity (from the tested `host-manifest.json`):

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| Creator main JavaScript | 616,444 | `18c01b25b8cffe72bd84a5a1332ce1cb4d3dafda30aa90366a461abd915f0e39` |
| Runtime JavaScript | 141,298 | `23d9825b3e44f7af934435e5333cf2e8523d0e0cf4bf485de8c9d2e8bb1f8c06` |
| Runtime Wasm | 7,571,066 | `9864a48bdea35185d51141d93eacca24cdb414066db397a769f71602d2f036bb` |
| Creator styles | 25,724 | `e788cc7a2f41eb8c6fe010203bf6208c3b472b08bb53af854fc05d6fc400bddb` |
| Capture worklet | 2,490 | `17f658199d7f2142aa922cd2ab2cdf50699834157167d6cb8dbbae20a93a7e68` |
| Perform master tap worklet | 3,048 | `93193d732e882bcaa19b7c6ed143e6d747e0e610439bab92f988a600b4a6d3da` |

## Fixture identity

The temporary portable Bundle was verified by
`tools/project-bundle/project_bundle.py verify`; its content digest is
`64c48089daf285e9def5ec2b5b551c92f5428f229e98a51a57544bda9dab8664`.
It was not added to the repository.

| Fixture field | Value |
| --- | --- |
| Portable Bundle | `creator-sample-proof-bundle.lmdj`; 995,873 bytes; SHA-256 `66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f` |
| Project | `00000000-0000-4000-8000-000000000002`; revision `46`; 120 BPM; 44/64 assigned Pads (B1–B16, A2–A16, C1–C13); 1 Asset |
| Source | 5.44 s mono 44.1 kHz PCM16 (240,000 frames); 480,044 bytes; SHA-256 `5b81dbcbc1f0da233b780d220df3fb1d6b020236855c5e9f2f6741bec47fc766` |

A multi-second source was chosen deliberately: the 0.05 s proof fixture's
playhead sweep is too fast to judge by eye, while this source sweeps for
roughly 5.4 s per pass.

## Pre-existing blocker found and cleared before the run

The first import attempts (both an old operator Bundle and the verified
fixture) were refused with `INVALID_PROJECT` / "The Project Bundle is
invalid." on every launch and every import. Diagnosis (live OPFS inspection)
found a pre-`lmdj.project.v5` local Project persisted by an older Build under
the same deterministic Project ID; `ProjectBundleTransfer::commit`
(`packages/project-io/src/project_bundle_transfer.cpp:865-872`) summarizes the
**existing local copy** to decide duplicate handling, and its load failure was
misreported as an invalid **incoming Bundle**. The stale copy was removed from
OPFS, after which startup was clean and the fixture imported successfully on
the first attempt. This defect is browser-independent (a fresh Chromium
profile only masked it) and is filed as
[#1438](https://github.com/endaye/lmdj/issues/1438). It is not a #605
regression.

## Authoritative operator checklist

A prefix of this table is not a pass. Audible results were reported by the
operator after the physical action; playhead-geometry results were extracted
by the agent from a continuous 5-minute screen recording (playhead x-position
tracked per frame) and are marked accordingly.

| Step | Physical exercise and far-side observation | Result |
| ---: | --- | --- |
| 1 | Reload the surface; no error panel appears. Import the fixture through the real file picker; import completes and the Project opens. | **PASS** |
| 2 | Activate audio, select Bank B, trigger B1 (One Shot, full range). The operator heard the complete ~5.4 s sample from start to finish and judged the playhead position consistent with the heard progress; the playhead vanished when playback ended. Video: playhead x advanced monotonically left-to-right over ~3.7 s of tracked frames at ≈84 px/s; the waveform viewport spans ≈460 px for 5.44 s, i.e. the sweep advances at real-time playback rate; zero detections after the pass. | **PASS** |
| 3 | Re-trigger B1 and switch to B2 mid-play. B1's waveform kept no playhead; B2's playhead started from its own Start. | **PASS** |
| 4 | Enable Loop on B1, trigger, listen, then stop. The operator heard repeated looping and a clean stop. Video: sawtooth trajectory — repeated left-to-right sweeps with wrap-backs to the region's left edge (x 464→134, 436→80), never outside the region; no playhead after stop. | **PASS** |
| 5 | Narrow the selection to ≈0.54–1.65 s and trigger. The operator heard only the middle section; the playhead stayed inside the selection. | **PASS** |
| 6 | During loop playback, switch to another tab for several seconds and return. No phantom (frozen) playhead existed after return — the #605 criterion holds. Two adjacent divergences were observed and are filed as [#1440](https://github.com/endaye/lmdj/issues/1440): loop audio kept sounding while hidden (the interruption design suspends audio on `visibilitychange`), and the still-sounding loop showed no playhead after return until re-triggered. | **PASS** (criterion) / finding filed |
| 7 | Re-trigger after the tab-switch episode (B3). Playhead appeared and swept normally and vanished at end of the one-shot; recovery needs no reload. | **PASS** |
| 8 | Reduced-motion and assistive-technology leg by code inspection: `apps/creator-web` contains no `prefers-reduced-motion` dependency, so the rAF-driven playhead cannot be suppressed by the OS setting; the playhead element is `aria-hidden="true"` (`apps/creator-web/src/components/waveform_editor.tsx:422-431`), an SVG `<line>` that is neither focusable nor draggable. Automated vitest and packaged-journey legs cover the same contract. | **PASS** (code-inspected) |

## Outcome and next gate

Status: **PASS**. Every #605 playhead leg — sweep aligned with hearing,
one-shot disappearance, loop wrap inside the selection, manual stop clearing,
pad-switch residue, suspend/resume phantom-freedom, and the reduced-motion /
assistive-technology contract — has a retained observation on the exact Build
above. The run surfaced two non-#605 defects, both filed:
[#1438](https://github.com/endaye/lmdj/issues/1438) (unreadable existing local
Project blocks import with a misleading message) and
[#1440](https://github.com/endaye/lmdj/issues/1440) (Safari tab-switch
suspension and playhead recovery divergences).

This pass upgrades only the macOS Safari physical acceptance of #605 on the
local proof-server Build above. Deployed-surface acceptance, other devices and
every release/deployment/Channel boundary remain separate.

## Version and documentation impact

- Version impact: none — validation-only work does not change product behavior
  or identity.
- Documentation impact: required — this retained evidence record.
- Pitfall impact: none — the findings were filed as issues; no process
  invariant or recurrence requiring a ledger change was exposed beyond them.
