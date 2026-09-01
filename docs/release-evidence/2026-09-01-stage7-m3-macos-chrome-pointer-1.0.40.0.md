# Stage 7 M3 macOS Chrome Pointer evidence — 1.0.40.0

## Evidence boundary

Status: **PASS**.

This record retains the completed Creator M3 physical Pointer row requested by
[#240](https://github.com/endaye/lmdj/issues/240). It becomes evidence only
because the named operator completed every ordered step below with the built-in
MacBook trackpad in macOS Chrome, without developer tools, scripted input,
browser automation, MIDI, or keyboard substitution. Automated setup and
regression results were retained only as package-boundary support and were not
substituted for any physical row.

The run is scoped to the exact local packaged Creator distribution named below.
It says nothing about Web Runtime Lab L2, macOS Safari, iPadOS, physical MIDI,
Release state, deployment, or Channel promotion.

| Field | Value |
| --- | --- |
| Product Build | `1.0.40.0` |
| Tested Git revision | `3aeba5c5a41c10ed28d2d9f6bf920907f54bb587` |
| Creator / Platform / compatible Formal Host | `2.1.1` / `2.0.1` / `web-runtime-host 2.1.1` |
| Protocol version | `1` |
| Creator host manifest SHA-256 | `47a97a982a047b1c3aaf6a8996522f318519b1c805449876bfcab637c5a9683b` |
| Host machine | MacBook Pro `MacBookPro17,1`; Apple M1; 16 GB |
| Host OS | macOS `26.6.2` (`25G83`), arm64 |
| Browser | Google Chrome `152.0.7977.65` |
| Pointer | built-in MacBook trackpad |
| Output route | built-in `MacBook Pro Speakers`; stereo; 48 kHz; default system output |
| Operator | `endaye` |
| Surface under test | exact packaged Creator distribution served locally at `http://127.0.0.1:4177` |
| Execution date | 2026-09-01, Asia/Shanghai |

## Package identity

| Packaged file | Bytes | SHA-256 |
| --- | ---: | --- |
| `index.html` | 1,039 | `1c15ba8bb97f389753f50998f0a3b2b14064fdeedee2d06c665af994169b4dd9` |
| `host-manifest.json` | 1,924 | `47a97a982a047b1c3aaf6a8996522f318519b1c805449876bfcab637c5a9683b` |
| Creator main JavaScript | 430,796 | `a47e306382d6f9f73554776b5885ae61c16bad42570909cae5b0f8a6874a9cd6` |
| Runtime JavaScript | 101,580 | `08f1eba0fefdf837387904b62a36fb168e27a2795570a5ebf0d2a7440464d28f` |
| Runtime Wasm | 3,362,560 | `6d245a6cc56c34f75f4bc4f7739cc82a832d6031f9a3305b6d9338e0058a0c66` |
| Creator styles | 10,170 | `3730bc44e66e7877b6ebce0e674e34101b41ef02a2cfc2ae0cd5d0c2ff8d3cb8` |
| Capture worklet | 2,490 | `17f658199d7f2142aa922cd2ab2cdf50699834157167d6cb8dbbae20a93a7e68` |

The distribution was built and packaged from a clean task worktree. The
pre-run Creator baseline passed 21/21 Vitest files with 363/363 assertions,
10/10 package tests, 3/3 server tests, and 141/141 shared Runtime Node tests.
Those results prove only the prepared source/package boundary, not the physical
Pointer row.

## Authoritative operator checklist

Every row remains pending until the operator reports its far-side visible and
audible observation. A prefix of this table is not a pass for the journey.

| Step | Physical Pointer exercise and required far-side observation | Result |
| ---: | --- | --- |
| 1 | Click the sole visible local Project's `Open` control. Exactly one Project opens and reports Project `00000000-0000-4000-8000-000000000239`, revision `88`, 120 BPM, 64/64 assigned Pads, and 2 Assets. The operator reported success, corroborated by the visible Project summary and all 16 Bank-A targets becoming assigned. | **PASS** |
| 2 | Click `Activate audio`. Exactly one transition reaches `running`; no second control or Pad activates. The operator reported success, corroborated by visible `running` / `Audio running` state, disabled activation and enabled suspension. | **PASS** |
| 3 | Exercise Bank A Pads A1 through A16. Each intended target shows one press/release response and produces exactly one configured audible/state outcome, with no miss, duplicate, or adjacent-Pad activation. A1 retained its prior Loop Toggle setting: the first physical click produced one `started` outcome and continuing playback; a second physical click on A1 produced one stop, and its visible outcome returned to `idle`. A2–A15 each admitted one Pointer action and played one complete four-hit source; the four audible hits were content, not four Pointer admissions. A16 consistently produced one short, quiet mono-kick response per click, matching its distinct replacement source. | **PASS** |
| 4 | Select Banks B, C, and D once each and click Pads 1 and 16 in each Bank. Exactly one Bank is visibly active, and each corner Pad produces one response from the displayed Bank. The operator reported every Bank and corner target passed with no unintended sound on Bank selection; the final visible state corroborates that only Bank A is selected after returning. | **PASS** |
| 5 | Use short mono-kick Pad A16 for ten deliberate single clicks, then one deliberate double-click. The operator counted exactly ten short responses from ten separated physical clicks and exactly two responses from the deliberate double-click, with no miss, duplicate, stuck voice or lost release. A16 replaces the original A1 target because A1's retained Loop Toggle alternates start/stop and is not an unambiguous repeated-admission counter. | **PASS** |
| 6 | Press A16, drag outside the Pad, and release; then click a Pad-grid gap and disabled `Perform`. A16 produced only its one short configured response, released without a stuck highlight/voice, and dragging crossed no unintended target. The gap and disabled control produced no Pad, mode, sound, error, scroll or focus action. A16 replaces A1 here because A1's retained Loop Toggle is not a release-bound voice. | **PASS** |
| 7 | Select `Sample`, `Project`, `Sequence`, then `Project`. The operator reported that each named mode target was reachable with no unintended sound, focus trap or scroll. The first far-side audit after that report still showed Sample, so no final Project claim was accepted from intent alone. The operator then made one explicit Project click; the visible surface changed to Project while revision `88`, 64/64 Pads, 2 Assets and Audio `running` were retained. The corrected complete journey passed without reload. | **PASS** |
| 8 | Click `Suspend audio`, then `Activate audio`, then short one-shot A16 once. Suspend reached `suspended`; Activate entered the designed `recovering` state with both lifecycle buttons disabled and real Pad input enabled. One physical A16 recovery-probe click produced its single short audible response, completed recovery to visible `running` / `Audio running`, and returned A16 to `idle` without a reload. A16 replaces A1 because A1 retains Loop Toggle. | **PASS** |
| 9 | Click `Export report` once. Exactly one report downloaded while the visible Creator remained `running`. The retained companion is 1,383 bytes with SHA-256 `80895963d297f304d85db5d2e8726bea1d85726e40231f473872c4acd1f4dc41`; it reports Build/Host/Platform identity, revision 88, 64 Pads, 115 admitted/115 outcome/0 rejected Triggers and no error. | **PASS** |

## Retained observations and artifacts

- Ergonomics and target accessibility: the ordered Bank A pass, B/C/D Bank and
  corner targets, mode rail, lifecycle controls, disabled Perform and Export
  report were all physically reachable; no target was inaccessible.
- Missed or double activation: none in the complete A1–A16 ordered pass, the
  B/C/D Bank and corner-target exercise, ten separated A16 clicks, or the
  intentional A16 double-click. The ten clicks produced ten admissions and the
  double-click produced exactly two.
- Focus surprises: none from Pad targeting, the grid gap, disabled Perform or
  mode controls. The first mode-run report ended with Sample still visible;
  one explicit Project correction reached the intended page without reload,
  retained Audio running, and exposed no focus trap. Suspend, Activate and the
  recovery-probe Pad were each reachable; the deliberately disabled lifecycle
  buttons during `recovering` admitted no unintended action.
- Ordinary mistake and drag-off recovery: A16 drag-off/release returned cleanly
  without an adjacent activation, stuck highlight or voice; the grid gap and
  disabled Perform remained inert. A1's retained Loop Toggle also stopped on
  the next intentional click without reload or Audio suspension. The mode
  run's initially mismatched final surface also recovered with one explicit
  Project click and no state loss. Audio recovery completed from `recovering`
  with the one designed physical A16 probe and no refresh.
- Audible/visible single-outcome agreement: A1 produced one continuing Loop
  Toggle start and one stop from two intentional clicks; A2–A15 each produced
  one complete four-hit source playback, and A16 produced one short quiet mono
  kick per click. B/C/D corner targets, ten single A16 clicks and the A16
  double-click preserved the same one-action/one-configured-outcome agreement.
- Exported report: retained as
  `2026-09-01-stage7-m3-macos-chrome-pointer-1.0.40.0.report.json`, 1,383 bytes,
  SHA-256
  `80895963d297f304d85db5d2e8726bea1d85726e40231f473872c4acd1f4dc41`.
  Its `physical` object remains the Creator report's pre-acceptance static
  matrix and therefore still says `deferred / unverified`; this human evidence
  record, not a runtime mutation of that report, is the authority that upgrades
  only M3.

## Outcome and next gate

Status: **PASS**. Every checklist row has a retained operator observation and
the final far-side state is Project revision `88`, Runtime revision `88`, 64
Pads, Audio `running`, 115 admitted/115 outcome/0 rejected Triggers and no
error. No measured Pointer defect was found. M3, the originating Stage 7 row
and the current Creator/testing Portal routes may now be upgraded for this exact
macOS Chrome packaged surface only.

## Version and documentation impact

- Version impact: none — validation-only work does not change product behavior
  or identity.
- Documentation impact: required — once the physical result exists, update
  this retained evidence, the Stage 7 Creator acceptance, the human-verification
  ledger, and the current Creator/testing Portal routes in the same Task.
