# Stage 7 MIDI Channel Compatibility Canary Evidence — 1.0.21.0

## Evidence boundary

This record binds the branch-local automated candidate Proof for generic MIDI
channel compatibility to clean committed revision
`1a7e84e94fd00030c44b48cd9f597cc42d5ca37a`. It does not claim that this branch
has been pushed or merged into `main`, and it does not claim a tag, Release,
deployment, publication, or Channel promotion.

Synthetic Channel-10 coverage and raw CoreMIDI capture are diagnostic evidence;
they do not replace the separate Chrome physical-MIDI UI retest. Safari Pointer
and iPadOS Touch/lifecycle also remain separate acceptance rows.

| Field | Value |
| --- | --- |
| Candidate branch | `fix/stage7-review-remediation` (unpublished) |
| Tested source revision | `1a7e84e94fd00030c44b48cd9f597cc42d5ca37a` |
| MIDI implementation revision | `5e59e11a132e3ba001beec85b85e3b817e3dcc9e` |
| Candidate identity revision | `5939c82d18864bc16c0bcf90b907c61da1357f5b` |
| Snapshot commit / source revision | `1a7e84e94fd00030c44b48cd9f597cc42d5ca37a` / `5939c82d18864bc16c0bcf90b907c61da1357f5b` |
| Product / Platform / Creator / Formal Host | `1.0.21.0` / `0.2.1` / `1.1.3` / `1.2.8` |
| Channel | `canary` |
| Assembly Lock SHA-256 | `4c76d77560de4c3975fa7114ad3c05736ef2406dab775aff7cce0d62ee50f26b` |
| Snapshot metadata SHA-256 | `c9fa38bf5fb40385683926a8e20a918e78e7d781f73dd1a999b616d7da2d1bb9` |
| Creator host manifest SHA-256 | `6aaee215848537f9b2358be82b474ec846138f5f51abe23a43b4999ee8c6d65e` |
| Host OS | macOS `26.6.1` (`25G76`), Darwin `25.6.0`, arm64 |
| Browser prepared for physical retest | Google Chrome `151.0.7922.110` |
| Physical Project fixture | `stage7-canary.lmdj`; SHA-256 `d5e17c74777cbf05cef239f79e16cce04ae0e3a380c3c00a93b553a17739aa4c` |

The immutable Portal snapshot records the clean candidate-identity revision.
The tested revision is its snapshot-commit descendant and contains no product
implementation change beyond that recorded source revision.

## Defect reproduction and corrected contract

On Product `1.0.20.0`, Chrome granted MIDI permission but physical Pad input did
not reach Creator. A raw macOS CoreMIDI capture from `MPD218 Port A` established
the actual device input independently of the browser:

| Device control | Raw Note On / Note Off | Interpreted input |
| --- | --- | --- |
| PAD BANK A, PAD1 | `99 24 <velocity>` / `89 24 00` | Channel 10, Note 36 |
| PAD BANK A, PAD16 | `99 33 <velocity>` / `89 33 00` | Channel 10, Note 51 |
| PAD BANK B, PAD1 | `99 34 <velocity>` / `89 34 00` | Channel 10, Note 52; outside Stage 7 Pad range |
| PAD BANK B, PAD16 | `99 43 <velocity>` / `89 43 00` | Channel 10, Note 67; outside Stage 7 Pad range |

The old Creator explicitly selected MIDI channel 1 even though the shared
Platform adapter already supports an all-channel default. The corrected Creator
contract is device-neutral:

- listen only after the user authorizes MIDI input;
- accept Note On `36..51`, velocity `1..127`, on channels 1–16;
- treat Note On velocity `0` and Note Off as release;
- map the bounded local note to the currently selected Creator Bank;
- ignore notes outside `36..51`, including the tested device's PAD BANK B
  program, without adding an AKAI-specific profile.

## Automated candidate gates

All final commands below passed from the clean committed candidate ending at
`1a7e84e94fd00030c44b48cd9f597cc42d5ca37a`.

| Command / gate | Result |
| --- | --- |
| Focused Creator / Platform input tests | PASS; Creator 7/7 and Platform 19/19, including Creator Channel-10 admission plus the Platform's explicit single-channel filter |
| `scripts/creator-web.sh proof` | PASS; fixture/distribution reproducibility; Vitest 62/62; package 7/7; server 3/3; Platform 88/88; packaged Chromium 13 passed/1 designed physical-MIDI skip; WebKit capability boundary 1/1 |
| `scripts/web-runtime-host.sh proof` | PASS; AudioWorklet/failure 21/21; package/distribution reproducibility; packaged Chromium 15 passed/1 designed skip; WebKit 1 passed/10 capability skips |
| `scripts/core.sh proof` | PASS; Release CTests 37/37; schema 9 positive/11 negative/17 Product artifacts; CLI 11/11; MCP 10/10; Golden audio match; Product `1.0.21.0`; Channel `canary`; Assembly Lock `MATCH` |
| `bash scripts/verify-core-dependencies.sh` | PASS; vendored and offline |
| `bash tests/build/test_active_tree.sh` | PASS |
| Product version / generated identity / module graph / version lock | PASS |
| `scripts/architecture-portal.sh check` | PASS; 47/47 tests, 37 pages, 10 diagram sources/20 outputs, optimized build, 42 routes/internal links |

The Emscripten identity is tag `6.0.5`, emsdk revision
`dfb9d1a46c3bb8f52e1e6324be23123b9d73c190`, releases revision
`dbd755b5da399329c2576f6e3dfa7f419f5d8409`, Node `22`, Playwright `1.62.1`,
fixed heap `536870912`, and protocol `1`.

The Creator Proof's deterministic fixture lived in its owned temporary
directory, was packed twice byte-for-byte, and was removed by successful
cleanup. The durable human fixture named above is independently hashed. No
physical acceptance-report digest is claimed until the candidate UI run exports
that report.

## Physical acceptance matrix

| Platform | Browser / surface | Input / journey | Current result |
| --- | --- | --- | --- |
| macOS | Chrome `151.0.7922.110` | Physical MIDI on Product `1.0.20.0` | `FAIL — permission granted, but old Creator filtered MPD218 Channel 10` |
| macOS | CoreMIDI raw capture | MPD218 PAD BANK A | `PASS diagnostic — Channel 10 Note 36/51 Note On/Off observed` |
| macOS | Chrome `151.0.7922.110` | Physical MIDI on Product `1.0.21.0` | `IN PROGRESS — exact candidate loaded; final UI observations/report not yet recorded` |
| macOS | Safari | Bundle import | `PASS manual observation — import did not remain in importing for more than 20 seconds` |
| macOS | Safari | Pointer | `deferred / unverified` |
| iPadOS | Safari | Touch | `deferred / unverified` |
| iPadOS | Safari | Lifecycle | `deferred / unverified` |

The Safari import observation does not imply Safari Pointer acceptance. Neither
automation nor the macOS result implies iPadOS acceptance.

## Candidate physical-MIDI checklist

Use the exact candidate and fixture recorded above, keep the controller in
**PAD BANK A**, then record only actually observed results:

1. Activate Audio and confirm `Audio running`.
2. Enable MIDI and grant Chrome access to `MPD218 Port A`.
3. Press physical Pads 1–16 once each; confirm 16 audible/visible admissions,
   correct velocity response, and no duplicate, missing, or stuck Pad.
4. Switch Creator Banks B, C, and D while leaving the device in PAD BANK A;
   confirm the same physical notes address the selected Creator Bank.
5. Disconnect/reconnect the device, explicitly enable MIDI again if required,
   and confirm input resumes without a duplicate listener.
6. Suspend and reactivate Audio; confirm physical input stops and resumes under
   the existing lifecycle contract.
7. Reload/reopen the Project, explicitly activate Audio and MIDI, and repeat a
   representative Pad trigger.
8. Export the privacy-safe acceptance report and record its SHA-256, operator,
   exact time/timezone, observations, and final pass/fail.

This task has not pushed, created a Pull Request, merged, tagged, released,
deployed, published, or promoted a Channel.
