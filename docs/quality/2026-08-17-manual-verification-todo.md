# Manual and Physical Verification TODO — 2026-08-17

Every verification in this repository that a human being has to perform,
gathered in one place. Automation cannot convert any of them.

Companion to [`2026-08-16-outstanding-work-before-stage9.md`](2026-08-16-outstanding-work-before-stage9.md),
which lists everything outstanding before Stage 9; this document expands its
item A1 into an executable checklist and adds the `web-runtime-lab` physical
gate, which A1 does not cover.

Verified against `main` at `801fa450` on 2026-08-17. Status values are copied
from the acceptance records named in each row, not re-derived.

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
| M2 | Human hearing and subjective audio quality | 1.0.22.0 ([Stage 8](2026-08-09-stage8-sample-editor-acceptance.md)) | open; see P1 |
| M3 | Pointer input | inherited from Stage 6/7 | open |
| M4 | *(optional)* record past 60 s and observe the buffer cap in a browser | E1 in the triage doc; unit coverage only today | open |

### Session M-B — macOS Chrome with external hardware

| ID | Journey | Origin |
| --- | --- | --- |
| M5 | External audio interface input | 1.0.23.0 |
| M6 | Physical MIDI controller | 1.0.22.0 |

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

## Open policy question

**P1. Does a physical pass carry forward across Product Builds?**

The three passes above are bound to `1.0.11.0`, `1.0.20.0` and `1.0.21.0`. The
current Build is `1.0.23.0`. No governance document states when a physical pass
expires or what kind of change invalidates it. Until this is settled, whether
M2 and M6 are re-runs or already-satisfied rows has no answer, and the question
will recur at every Build.

Settling it belongs in `docs/prd/decision-log.md` or the version policy, not
inside an implementation Task.

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

1. ~~**M1**~~ — done 2026-08-17, `PASS`, four findings. **M2 + M3 (+ M4)**
   remain and still need only one Mac and no extra hardware.
2. **P1** — a short decision that determines whether the remaining list is
   thirteen rows or six.
3. **M7 + M8**, then **M9 + M10 + M11** — one session each, before any external
   distribution.
4. **M5 + M6** — when the external interface and controller are on hand.
5. **L1 through L5** — most expensive, needs instrumentation and five runs of
   500 triggers plus ten minutes. Schedule when the Web/PWA launch-platform
   conclusion actually has to land.
