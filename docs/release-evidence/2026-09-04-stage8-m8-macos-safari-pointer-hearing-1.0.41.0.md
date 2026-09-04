# Stage 8 M8 macOS Safari Pointer plus physical-hearing evidence — 1.0.41.0

## Evidence boundary

Status: **PASS**.

This record retains the completed Creator M8 physical Pointer and hearing row
requested by [#245](https://github.com/endaye/lmdj/issues/245). The named
operator completed every counted control, Pad, Sample Editor and lifecycle
action with the built-in MacBook trackpad in real macOS Safari and supplied the
far-side visible and audible observations. Agent preparation, Bundle
verification, import setup, source inspection and read-only desktop observation
were not substituted for any physical result.

The run used the deployed Creator surface and exact released Build below. It
does not close or replace Web Runtime Lab L1, macOS Safari capture M7, Stage 9
Safari Sequence acceptance, iPadOS, MIDI, Release publication, deployment or
Channel-promotion evidence.

| Field | Value |
| --- | --- |
| Product Build | `1.0.41.0` |
| Tested Git revision | `98ffec723cc88ecaacc733c4682d17df9a014bfc` |
| Creator / Platform / compatible Formal Host | `2.1.1` / `2.0.1` / `web-runtime-host 2.1.1` |
| Protocol version | `1` |
| Creator host manifest SHA-256 | `f47c017edf82b0511b176f8fb8f13d034821d02b1aa0b5ddb29304b100e925b1` |
| Host machine | MacBook Pro `Mac16,8`; Apple M4 Pro; 48 GB |
| Host OS | macOS `26.6.2` (`25G83`), arm64 |
| Browser | Safari `26.6.2` (`21624.5.1.11.3`) |
| Pointer | built-in MacBook trackpad |
| Output route | built-in `MacBook Pro Speakers`; stereo; 48 kHz; default system output |
| Operator | `endaye` |
| Surface under test | deployed Creator at `https://lmdj-creator.netlify.app/` |
| Execution date | 2026-09-04, Asia/Shanghai |

The fresh remote audit at `2026-09-04T02:10:48Z` passed for the immutable
`lmdj-v1.0.41.0` tag, GitHub Release metadata, full CI, six-asset `web-hosts`
profile and `dev` promotion. The published Creator archive is 1,253,121 bytes
with SHA-256
`a2ee506cb8e9237f9685870d15223a09d3a09e04b355fa9936f0a9df7195fbd2`.

## Deployed distribution identity

Each live asset was fetched from the tested route after the physical run and
matched its content-addressed manifest entry.

| Deployed file | Bytes | SHA-256 |
| --- | ---: | --- |
| `index.html` | 1,759 | `366c7896321059aa25d263f6fd4052b437d7d0216f68d11c655410b6cdc2b20b` |
| `host-manifest.json` | 1,924 | `f47c017edf82b0511b176f8fb8f13d034821d02b1aa0b5ddb29304b100e925b1` |
| Creator main JavaScript | 430,796 | `e513ae7a9b7a8c48ea3d575bb9646de30407fbfa40b0687298e339593b56f23a` |
| Runtime JavaScript | 101,858 | `8ae5337b3293c744ca45565bf6b934dd23c382865c4b01bc686b72655aa3bb62` |
| Runtime Wasm | 3,469,924 | `c58f2973a53358675765d7b23bcef5091675424849cfd09e17f52bfda73e5534` |
| Creator styles | 10,170 | `3730bc44e66e7877b6ebce0e674e34101b41ef02a2cfc2ae0cd5d0c2ff8d3cb8` |
| Capture worklet | 2,490 | `17f658199d7f2142aa922cd2ab2cdf50699834157167d6cb8dbbae20a93a7e68` |

## Fixture identity

The temporary portable Bundle was verified by
`tools/project-bundle/project_bundle.py`; its content digest was
`7eef75ed3c432c6185b7fd515e773f53fc3d6edfafd579662881347b22f0bbb7`.
It was not added to the repository.

| Fixture field | Value |
| --- | --- |
| Portable Bundle | `issue-245-m8-safari-fixture.lmdj`; 1,168,474 bytes; SHA-256 `5d0c429149869ca8360ee8acb0200bd320437ac60ac461d8cd7b75e8a60d2dd1` |
| Initial Project | `00000000-0000-4000-8000-000000000245`; revision `68`; 120 BPM; 64/64 assigned Pads; 2 Assets |
| Main source | 2.0 s stereo 48 kHz PCM16; 384,044 bytes; SHA-256 `d276060107ab2479126c4f66919b799593a852fe624720f03e7be3b70bcfe867` |
| A16 source | 0.1 s mono 48 kHz PCM16 kick; 9,644 bytes; SHA-256 `43ab266faaaddc590b75ea49921574f795c8c7535d28453fda0b48b3f620bfb7` |

## Authoritative operator checklist

A prefix of this table is not a pass. Each result below was reported only
after the operator completed the named physical action and observed its visible
or audible far side.

| Step | Physical Pointer/hearing exercise and far-side observation | Result |
| ---: | --- | --- |
| 1 | Open the sole local Project. Exactly one Project opened with the full ID ending `0245`, revision 68, 120 BPM, 64/64 assigned Pads and 2 Assets. | **PASS** |
| 2 | Activate Audio once and trigger A1 once. The surface reached `Audio active`; A1 produced one audible response with no repeat, click, dropout or interruption. | **PASS** |
| 3 | Trigger A2 through A15 once each, then A16 once. A2–A15 each played normally; A16 was the distinct short mono kick. No Pad was silent, duplicated, clipped, interrupted or stuck. | **PASS** |
| 4 | Select Banks B, C and D and trigger Pads 1 and 16 in each. Exactly one Bank was highlighted, Bank selection itself was silent, and all six corner Pads produced one expected response. | **PASS** |
| 5 | Return from a real Safari focus interruption. The surface exposed `recovering / Audio recovering`, disabled both lifecycle buttons and left the armed Pad probe enabled. One physical A16 probe produced one short kick and completed recovery to `Audio running`. Earlier focus-transition observations that could not prove an active foreground state were discarded rather than counted. | **PASS** |
| 6 | On A16, perform ten separated single clicks and one deliberate double-click. The operator counted exactly ten and then exactly two short responses, with no miss, duplicate, stuck voice or audible anomaly. | **PASS** |
| 7 | Press A16, drag outside and release; click a Pad-grid gap; click disabled `Perform`. The press produced only its configured response; release left no stuck state. The gap and disabled control caused no sound, Pad, mode or focus/scroll action. | **PASS** |
| 8 | Select `Sample`, `Project`, `Sequence`, then `Project`. Every target switched once to the expected surface with no unintended scroll, focus trap or extra sound. | **PASS** |
| 9 | From `running`, click `Suspend audio`, then `Activate audio`, then A16 once when enabled. Suspension disabled Pads and left no residual voice; reactivation and the single short-kick probe returned to `Audio running` with no duplicate. | **PASS** |
| 10 | On A1, commit and audition the broad `0.250–1.750 s` selection, then the strict non-zero `0.505–0.545 s` selection. Both were audible with clean endpoints; the approximately 40 ms selection had the expected rapid texture and no distinct seam transient. | **PASS** |
| 11 | Exercise Loop off/One Shot, Loop off/Gate with a roughly 1.2 s hold, Loop on/Hold off with a roughly 1 s hold, and Loop on/Hold on for roughly 1 s and 3 s. Release and toggle stops were clean; no truncation, gap, dropout, stuck voice or obvious loop-seam click was heard. | **PASS** |
| 12 | Restore the broad A1 selection, compare `0.0 dB` with `-11.7 dB`, then enable Mute. The lower setting was clearly quieter but audible; Mute was silent with no residual voice. Mute was then disabled and the final control state matched the requested values. | **PASS** |
| 13 | Compare A15 and A16, reload Safari, reopen the local Project, reactivate Audio and compare again. Revision 83, 64/64 Pads and 2 Assets persisted; A15 remained the roughly 2 s stereo source and A16 remained the short mono kick. | **PASS** |
| 14 | After a fresh reload, reopen revision 83, activate Audio, wait for `running`, trigger A15 and A16 once each and export exactly one report. The retained report is 1,380 bytes with SHA-256 `fb87f54f31196cc01211b9c7da8aec34f5f7659b7f7392bdeffd3f5ba1fcc340`; it reports 2 admissions / 2 outcomes / 0 rejections, matching Project/Runtime revision 83, state `running` and no error. | **PASS** |

## Report selection and retained observations

Two earlier report candidates were inspected and deliberately excluded from
the retained companion:

- `c777617e12a8fb680b5fbcbbcfa229b0ca3442b5f2fff659901854d332964bcf`
  recorded 2 admissions / 2 outcomes / 1 rejection.
- `fe6a14693e6d4339c2db0a542252217ffb727146749060e10fd1b49cef5d70a3`
  was exported before the requested refresh and recorded 5 admissions / 5
  outcomes / 1 rejection.

Neither was used to claim a clean final journey. The operator then refreshed
and repeated the exact reload/open/activate/wait/A15/A16/export suffix. The
result is retained as
`2026-09-04-stage8-m8-macos-safari-pointer-hearing-1.0.41.0.report.json`.
Its `physical` object is the Creator report's static pre-acceptance matrix and
therefore still says `deferred / unverified`; this human evidence record, not a
runtime rewrite of that object, is the authority that upgrades only M8.

The final revision is 83 rather than the single-gesture estimate of 81. The
extra two revisions prove that two additional authoring mutations committed
during the Sample-control work and are consistent with exact-value adjustment;
the revision counter alone cannot identify which controls produced them. The
final reopened Project state, 64/64 Pad assignments, two Assets and A15/A16
content identity all matched the intended truth. A Project revision is an
authoring mutation counter, not a Pad Trigger counter.

## Outcome and next gate

Status: **PASS**. Every M8 Pointer and hearing leg has a retained operator
observation, including focus recovery, explicit suspend/reactivate, strict
trim, all playback modes, gain/mute, reload/reopen persistence and a clean
final report. No reproducible Pointer, recovery or audible defect was found.

This pass upgrades only the macOS Safari Creator M8 row for the exact deployed
Build above. M7 capture, Stage 9 Safari Sequence acceptance, Web Runtime Lab
instrumentation, other devices and every release/deployment/Channel boundary
remain separate.

## Version and documentation impact

- Version impact: none — validation-only work does not change product behavior
  or identity.
- Documentation impact: required — this retained evidence, the Stage 7 and
  Stage 8 physical rows, the human-verification ledger, the outstanding-work
  summary and current Creator/testing Portal routes are updated together.
- Pitfall impact: none — the run applied the existing complete-journey and
  short-loop replay guidance; it did not expose a new process invariant or a
  recurrence requiring a ledger change.
