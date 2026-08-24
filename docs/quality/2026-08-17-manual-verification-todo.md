# Human TODO — 2026-08-17

Everything in this repository that **a human being has to do**: verifications
automation cannot convert, and decisions a coding agent must not settle alone.

Its companion is [`2026-08-17-machine-task-todo.md`](2026-08-17-machine-task-todo.md),
which holds the work a coding agent can complete without a human in the loop.
Between them the two lists cover every open item in
[`2026-08-16-outstanding-work-before-stage9.md`](2026-08-16-outstanding-work-before-stage9.md),
which stays the canonical triage record; these two are the working lists.

This document expands triage item A1 into an executable checklist, adds the
`web-runtime-lab` physical gate that A1 does not cover, and carries the
decisions blocking machine work.

Verified against `main` at `801fa450` on 2026-08-17. Status values are copied
from the acceptance records named in each row, not re-derived.

## Contents

| Section | What it holds |
| --- | --- |
| Family L | the five instrumented Web physical rows |
| Family M | Creator product physical rows, grouped by session and hardware |
| Decisions | choices only a person can make; each one blocks machine work |
| Re-verification | rows that must be re-run after a fix lands |

---

## Deferral boundary

These rows **do not** block Stage 9 development. They **do** block:

- any claim of physical acceptance for any Product Build;
- any Product tag, Release publication, deployment or Channel promotion;
- promotion to `beta` or `stable`;
- the Web/PWA launch-platform conclusion, which depends on Family L only.

The cost of deferring is specific, not general: the Chromium fake device
replays a synthetic tone, so silence, clipping, channel swap and sample-rate
error are all structurally invisible to every automated capture gate. The
longer these rows stay deferred, the more code rests on that unverified
assumption.

---

## Family L — the five required Web physical rows

Source: [`web-runtime-lab-acceptance.md`](web-runtime-lab-acceptance.md). This
is the physical gate for the approved Touch-to-Sound threshold
([`2026-08-01-web-realtime-audio-threshold-decision.md`](../architecture/2026-08-01-web-realtime-audio-threshold-decision.md)).
`README.md` and `products/lmdj/README.md` both cite it. It is carried forward
unchanged by every Web acceptance record since Stage 6.

**Equipment required.** One of:

1. high-speed video at 240 fps or faster, with pad contact and acoustic onset
   in the same recording; or
2. a calibrated wired electrical/loopback rig whose trigger marker and output
   onset share one clock.

A browser-reported estimate is never physical evidence. Bluetooth may be
measured separately but never substitutes for a built-in or wired result.

| ID | Platform | Browser | Input | Run | Status |
| --- | --- | --- | --- | --- | --- |
| L1 | macOS | Safari | Pointer | 500 triggers + 10-minute foreground run | `deferred / unverified` |
| L2 | macOS | Chrome | Pointer | 500 triggers + 10-minute foreground run | `deferred / unverified` |
| L3 | macOS | Chrome | Physical MIDI | 500 events + physical timing sample | `deferred / unverified` |
| L4 | iPadOS | Safari | Touch | 500 triggers + 10-minute foreground run | `deferred / unverified` |
| L5 | iPadOS | Safari | Touch | background, foreground, lock, unlock, route interruption | `deferred / unverified` |

**Execution notes.** Reload the lab for a fresh session per row, select
**Built-in** or **Wired** (Start is disabled otherwise), start audio once, and
follow the visible guidance card — it counts exactly 500 dispatches and 600,000
ms of foreground time. A missing acknowledgement after the one-second grace
window, a duplicate acknowledgement, a ring-full drop, a processor error, a
501st dispatch, an AudioContext suspension, a hidden/frozen/pagehide
transition, or a route-category change after start all produce
`restart-required`: reload and repeat the whole row. Do not splice two sessions.

**Then evaluate.** Per row:

```bash
scripts/web-runtime-lab.sh prepare ROW_KEY REPORT.json \
  --os-version "exact installed OS version" \
  --browser-version "exact installed browser version"
```

Preparation alone evaluates as `unverified` by design. After retaining the raw
physical measurement record, run `scripts/web-runtime-lab.sh evaluate
EVIDENCE.json`; it exits `0` only when all five rows pass, `1` on a measured
threshold violation, `2` on missing or ineligible evidence.

---

## Family M — Creator product physical rows

Source: the Stage 6/7, Stage 8 and Stage 8B acceptance records. No instruments
required; these need ears, hands and real devices. Where the same platform
appears in more than one Build's ledger, the row is listed once and should be
run against the current Build.

### Session M-A — macOS Chrome, no extra hardware

| ID | Journey | Origin | Status |
| --- | --- | --- | --- |
| M1 | Real microphone capture → commit → playback hearing | 1.0.23.0 ([Stage 8B](2026-08-16-stage8b-pad-capture-acceptance.md)) | **`PASS` 2026-08-17** ([evidence](../release-evidence/2026-08-17-stage8b-real-microphone-capture-1.0.23.0.md)) |
| M2 | Human hearing and subjective audio quality | 1.0.22.0 ([Stage 8](2026-08-09-stage8-sample-editor-acceptance.md)) | **started 2026-08-17, stopped at check 1** — trimming produces audible clicks at the boundaries (F6); the trim handles could not be aimed (F5). Checks 2–8 not performed. Row stays `unverified`; a measured failure is not a pass and not a silent omission |
| M3 | Pointer input | inherited from Stage 6/7 | not started |
| M4 | *(optional)* record past 60 s and observe the buffer cap in a browser | E1 in the triage doc; unit coverage only today | open |

### Session M-B — macOS Chrome with external hardware

| ID | Journey | Origin |
| --- | --- | --- |
| M5 | External audio interface input | 1.0.23.0 |
| M6 | Physical MIDI controller | 1.0.22.0 |

M6 application of the carry-forward rule (P1, resolved 2026-08-24): the
`1.0.21.0` MIDI canary in "Already passed" is a valid historical pass, but
M6's trigger trees (`input`, `lifecycle`, `audio-path`, `packaging-csp`)
changed between `56131582` and the current Build — Stage 8/8B alone touched
the shared input adapter, the session layer, the Creator runtime and the
packaging tooling. No unchanged-tree derivation is available and no exemption
was recorded, so **M6 is a re-run** on the Build under test; the canary does
not satisfy it.

### Session M-C — macOS Safari

| ID | Journey | Origin |
| --- | --- | --- |
| M7 | `getUserMedia` and AudioWorklet capture behaviour | 1.0.23.0 |
| M8 | Pointer plus physical hearing | 1.0.22.0 + inherited Stage 6/7 pointer row |

### Session M-D — iPadOS Safari

| ID | Journey | Origin |
| --- | --- | --- |
| M9 | Capture behaviour | 1.0.23.0 |
| M10 | Physical touch ergonomics | 1.0.22.0 + inherited Stage 6/7 touch row |
| M11 | Background, lock-screen and recovery lifecycle | 1.0.22.0 + inherited Stage 6/7 lifecycle row |

---

## M1 — real microphone capture round trip

Expanded because it is the cheapest row with the widest reach: one session
validates the entire capture chain, and the four failure classes below are the
ones no automated gate can see.

**Preconditions.** macOS Chrome, a working built-in or wired microphone, a
quiet room, headphones or wired output. Serve the packaged Creator distribution,
not a dev-only path, so the same-origin content-hashed capture worklet and the
distribution CSP are exercised.

**Steps.**

1. Open the Creator, grant the microphone permission when prompted.
2. Arm capture on a Pad and record a short, clearly identifiable source —
   speech counts and beats better than a hum, because pitch and timing errors
   are audible in it.
3. Watch the live level/waveform while recording: it must move with the source.
4. Trim, then commit onto the Pad.
5. Trigger the Pad and listen.
6. Repeat once at a deliberately loud input level.

**What must be true.**

| Check | Failure it catches |
| --- | --- |
| The committed Pad plays back audible sound | silence — a wired-but-dead capture path |
| Playback pitch and duration match the source | sample-rate error between device and the 48 kHz PCM16 encode |
| A loud take is loud but not distorted | clipping in the float→PCM16 conversion |
| The source appears where expected in the stereo field | channel swap or a dropped channel |
| Playback is free of clicks, gaps and dropouts | buffer or worklet boundary defects |

**Record the outcome** as described below. A defect found here is worth more
than every mechanical item in the triage document; it should stop and be
reported before the remaining sessions run.

---

## Already passed — do not re-run

| Gate | Result |
| --- | --- |
| Apple native Host seven-step physical gate — CoreAudio closed loop, two-Pad audible mapping, live reload overlap | `PASS` on `1.0.11.0` ([record](2026-08-03-formal-native-host-acceptance.md)) |
| macOS Chrome physical keyboard plus hearing, ten-step Canary | `PASS` on `1.0.20.0`, report SHA-256 `7e2a2b…333a` ([evidence](../release-evidence/2026-08-13-stage7-keyboard-mapping-canary-1.0.20.0.md)) |
| macOS Chrome physical MIDI, Creator surface — MPD218 Channel 10, all 16 Bank-A Pads, reconnect, suspend/re-authorize, reload/reopen | `PASS` on `1.0.21.0`, report SHA-256 `b0491e…603` ([evidence](../release-evidence/2026-08-13-stage7-midi-channel-canary-1.0.21.0.md)) |
| macOS Chrome real microphone capture → commit → playback hearing, five criteria including a hot take (M1) | `PASS` on `1.0.23.0` ([evidence](../release-evidence/2026-08-17-stage8b-real-microphone-capture-1.0.23.0.md)) |

The Family L Chrome MIDI row (L3) is **not** covered by the `1.0.21.0` pass:
that pass is a Creator product journey, while L3 additionally requires 500
events and an instrumented physical timing sample.

---

## Decisions — only a person can make these

Each one blocks machine work that is otherwise ready. A coding agent must not
settle any of them inside an implementation Task; that is the rule in
`CLAUDE.md`, and every item below is a product or governance choice, not an
implementation detail. Record the outcome in `docs/prd/decision-log.md`, in
`docs/prd/open-questions.md`, or in the governance document it belongs to.

| ID | Decision | What it unblocks | Cost |
| --- | --- | --- | --- |
| ~~P1~~ | ~~Does a physical pass carry forward across Product Builds?~~ **resolved 2026-08-24** — the [physical acceptance carry-forward rule](../prd/decisions/2026-08-24-physical-acceptance-carry-forward.md) ([#236](https://github.com/endaye/lmdj/issues/236)) | answered: M2 has no pass to carry; M6 is a re-run because its trigger trees changed after `1.0.21.0`; every new Build derives its own re-run set per the rule | done |
| P2 | The capture panel's presentation, focus behaviour, and the replacement trim pointer model | Tasks 2–4 of the Creator UI remediation plan (F1, F2, F3, F5) | short, one design gate |
| F4 | Device picker, visible input identity, an input-level gate before commit, or some combination | closing the silent-capture gap; the picker's absence is a declared `1.0.23.0` boundary, so this widens scope | design review |
| F6 | Amplitude ramp policy in the render path — ramp length, zero-crossing snap, crossfade, or a combination | M2 checks 1 and 5, which fail by construction today; needs a realtime-safety review because the render path is allocation-free and lock-free | design review |
| A2 | Is `native-test-host` a product component to be renamed, or does it leave the Assembly and every distribution? | the Assembly cleanup; also needs a written rule for what may enter a distribution package | short |
| A3 | Build Manifest reproducibility — detached manifest, stripped archived copy, or drop the rebuild-and-compare claim | first external distribution (`dev` Channel or above) | short |
| D1 + D2 | Long-material resource model and Loop BPM time-stretch — one review | any long-material work; touches Cooker Bank allocation, the lock-free publication layout, manifest semantics and Facade validation | design review |
| D3 | Provider SDK Artifact byte access, both directions | the first Capability implementation that parses structured Artifact bytes | design review |
| D4 + D5 | Recording concurrency semantics, and Take scope — events only or audio bounce too | **Stage 9 itself** | design review |

P1, resolved 2026-08-24 ([#236](https://github.com/endaye/lmdj/issues/236)):
the [physical acceptance carry-forward rule](../prd/decisions/2026-08-24-physical-acceptance-carry-forward.md)
now states when a physical pass expires and what kind of change invalidates
it. The four passes above remain bound to `1.0.11.0`, `1.0.20.0`, `1.0.21.0`
and `1.0.23.0` as historical evidence; none of them is a current-Build claim,
and any carry to a later Build requires the recorded derivation the rule
defines.

Full statements of A2, A3 and D1–D5 are in
[the triage document](2026-08-16-outstanding-work-before-stage9.md); F4 and F6
are in its section F.

---

## Re-verification triggered by a fix

Rows here are not new work — they are existing rows that a landed fix requires
to be run again, or run for the first time on a surface that was previously
untestable by hand.

| Trigger | Rows to run | Why |
| --- | --- | --- |
| Creator UI remediation lands (F1, F2, F3, F5) | re-walk M1's capture journey far enough to confirm the panel, `Stop` and the recovery path are usable without prior knowledge; then run M2 and M3 | Task 5 of the remediation plan. This does **not** re-open M1's hearing result, which stands on its own |
| F6 ramp policy lands | M2 checks 1 and 5 | both fail by construction today |
| F4 resolution lands | M1's capture journey with the input deliberately switched mid-session | proves the gap is actually closed rather than only mitigated |
| Any new Product Build allocated for team testing or release | every row whose trigger-set diff is non-empty since its last pass, derived per the [carry-forward rule](../prd/decisions/2026-08-24-physical-acceptance-carry-forward.md); the derivation is recorded in the Build's acceptance record | answered 2026-08-24 by P1 ([#236](https://github.com/endaye/lmdj/issues/236)) |

---

## Recording a result

Follow the precedent set by the Stage 7 canaries:

1. write the run into `docs/release-evidence/` with the exact Product Build,
   revisions, Host OS and browser versions, and the SHA-256 of any exported
   report;
2. flip the row's status in the acceptance record it came from, naming the
   evidence file;
3. do not widen the claim — a macOS Chrome pass says nothing about Safari,
   iPadOS or any other row.

An unsupported or unreproducible step stays `unverified`. It is not silently
omitted and not called passed.

---

## Suggested order

1. ~~**M1**~~ — done 2026-08-17, `PASS`, four findings. **M2 stopped at its
   first check** and should not resume until F5 and F6 are resolved: F5 makes
   the trim controls unaimable, so checks 1–2 cannot be performed reliably, and
   F6 makes checks 1 and 5 fail by construction. **M3** is independent of both
   and can run at any time — it is the only verification row available today
   with no blocker.
2. **P2** — the design gate that unblocks four machine Tasks and is the
   shortest path to making the Creator usable by hand. ~~P1~~ resolved
   2026-08-24 ([#236](https://github.com/endaye/lmdj/issues/236)): rows re-run
   unless a recorded unchanged-tree derivation carries them, so M6 stays on
   the list and every future Build derives its own re-run set.
3. **F6**, then **D4 + D5** — F6 unblocks the rest of M2; D4 and D5 are what
   Stage 9 itself waits on.
4. **M7 + M8**, then **M9 + M10 + M11** — one session each, before any external
   distribution.
5. **M5 + M6** — when the external interface and controller are on hand.
6. **F4**, **A2**, **A3**, **D1 + D2**, **D3** — schedule as the work they gate
   comes up; A2 and A3 are due before the first external distribution.
7. **L1 through L5** — most expensive, needs instrumentation and five runs of
   500 triggers plus ten minutes. Schedule when the Web/PWA launch-platform
   conclusion actually has to land.
