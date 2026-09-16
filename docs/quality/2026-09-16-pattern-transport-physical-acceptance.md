# Pattern Transport physical acceptance — 2026-09-16

Physical acceptance ledger for the global Pattern Play/Stop and overdub Record
transport ([#1230](https://github.com/endaye/lmdj/issues/1230)). The synthetic
evidence (Facade/engine/Host suites and the three Creator e2e journeys) is
recorded in the issue's acceptance-disposition comment; this ledger holds the
rows only hands and ears can run, per acceptance item 7: *synthetic assertions
do not prove hearing or device behavior*.

This ledger follows the conventions of
[`2026-08-17-manual-verification-todo.md`](2026-08-17-manual-verification-todo.md):
each row is bound to one exact Product Build, records exact OS/browser/device
identities, and is reported as `PASS`, `FAIL` or `unverified` — never silently
omitted. Results land in `docs/release-evidence/` and the row status here is
flipped with the evidence file named. A pass on one platform says nothing
about any other row.

This ledger is consumed by U7 ([#1221](https://github.com/endaye/lmdj/issues/1221))
and complements the Stage 9 Sequence physical rows ([#360](https://github.com/endaye/lmdj/issues/360)):
#360's record → overdub → switch → stop/flush → reload → recover journeys now
run against the global transport shipped in #1386/#1390, and the legs below are
the transport-specific additions those rows do not cover (global keys, page
navigation continuity, live-Pad behavior at stop).

## Equipment and preconditions

- A packaged Product Build whose tree contains #1386 and #1390 (Creator global
  transport adoption and the retired-engagement projection fix), served as the
  packaged Creator distribution — not a dev server — so the distribution CSP
  and the real session path are exercised.
- Headphones or a wired output route, and a quiet enough room to judge clicks,
  gaps and stuck voices.
- A Project with at least one Pattern and several assigned Pads with distinct,
  easily identifiable Samples.
- T3 only: a physical MIDI controller (the MPD218 from L3/M6 suffices).
- T2 only: a named physical iPadOS Safari device (the L4/L5 iPad Air suffices).

No instruments are required; unlike Family L these rows need ears and hands,
not a timing rig. Record the exact Product Build, tested revision, Host OS and
browser versions, input/output route, and the SHA-256 of any exported report.

## Legs — every leg has a far-side assertion per transition

The six state-table cells are legs T-L1 through T-L6. "Authority" means the
visible transport status plus, where named, a reload/reopen of the Project.

| Leg | From → action → To | Far-side assertions |
| --- | --- | --- |
| T-L1 | Stopped → Play/Stop → Playing | Pattern playback is audible; status shows playing. Reload: the Pattern gained **no** events. |
| T-L2 | Playing → Play/Stop → Stopped | Pattern falls silent; an immediate live Pad trigger is audible and a Gate Pad release produces no stuck voice; status shows stopped. |
| T-L3 | Stopped → Record → Playing+Recording | Playback starts audibly in the same gesture; Pad hits land as events. After commit, reload shows the recorded events against the correct Pad Slots with an advanced committed revision. |
| T-L4 | Playing+Recording → Record → Playing | Playback continues with **no audible interruption**; recording stops; the just-recorded events play back on the next pass. |
| T-L5 | Playing+Recording → Play/Stop → Stopped | Both playback and recording end; committed events survive reload (Pattern content, Pad Slot references, committed revision). |
| T-L6 | Playing → Record → Playing+Recording (overdub) | Second-pass Pad hits overlay the first pass; the first-pass events remain audible and intact after commit and reload. |
| T-N1 | Playing+Recording, navigate Project/Sample/Sequence/Perform and back | No implicit stop and no audible gap at any mode transition; on return to Sequence the projection matches authority (playing/recording, no phantom failure banner); exactly one engagement — a second device-visible session or doubled event stream is a failure. |
| T-N2 | Reload the page mid-recording | The recovery surface appears; choosing recover retains the sealed events on reload, choosing discard leaves the Pattern exactly as before the attempt — one outcome, never partial. |
| T-N3 | Stop after a switch with a pending publication (switch Pattern, then immediately Play/Stop) | No ghost switch applies after stop; the audible Pattern and the reloaded Pattern agree. |

## Rows

| ID | Platform | Browser | Input | Legs | Status |
| --- | --- | --- | --- | --- | --- |
| T1 | macOS | Chrome | Pointer + physical keyboard | T-L1…T-L6, T-N1…T-N3 | unverified |
| T2 | iPadOS | Safari | Touch | T-L1…T-L6, T-N1, T-N2; plus background → foreground → lock → unlock during playing+recording, with at most one explicit activation per interruption and the transport authority correct after each recovery | unverified |
| T3 | macOS | Chrome | Physical MIDI | T-L3, T-L4, T-L6 with Pad hits delivered by the controller; recorded events reference the correct Pad Slots | unverified — run together with the M6 re-run |

T2 additionally inherits the L5 lifecycle expectation: a route interruption
during playback must not leave the projection claiming a playing state the
Runtime no longer holds (the #1390 disengage behavior is the thing being
heard/shown here).

## Recording a result

As in the parent ledger: write the run into `docs/release-evidence/` with the
exact Product Build, revisions, OS/browser versions, device and input/output
route, and the SHA-256 of any exported report; flip the row here naming the
evidence file; do not widen the claim across platforms. An unsupported or
unreproducible leg stays `unverified`.

When T1–T3 are `PASS` on one exact Build, acceptance item 7 of #1230 has its
physical evidence and the issue may be closed; U7 (#1221) records the coverage
in the migration ledger.
