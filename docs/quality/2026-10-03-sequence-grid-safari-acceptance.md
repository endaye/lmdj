# Sequence grid: macOS and real iPad Safari acceptance

Date: 2026-10-03 (Asia/Shanghai; observations on 2026-10-02 UTC).
Relates to [#1671](https://github.com/endaye/lmdj/issues/1671).
Authority: [the Sequence grid plan](../plans/2026-10-02-creator-sequence-grid.md),
including its T3 journey and separate physical-input and hearing rows.

**Status: partial acceptance. Physical drag, listening and device-lifecycle
rows remain open.** This record ships observations, not a product change or
an Issue-completion claim. It allocates no Build and authorizes no release.

## Candidate and instruments

The tested source was `9b2740a12ebbdcbc147235ffc00768d47084578c`:
Product Build `2.0.76.0`, Creator Web `4.8.0`. Identities were read from the
packaged manifest, retained in the
[machine-readable evidence](2026-10-03-sequence-grid-safari-evidence.json).
Later integration changes were not retested by this session.

- macOS Safari `27.0.1`: computer-use observations of the visible product,
  including revision, rendered note fields and transport state. These rows
  did not directly query complete Project Truth.
- Physical iPad, Safari/iPadOS `27.0`, system build `24A437`:
  Mac `/usr/bin/safaridriver`; returned `safari:useSimulator=false`.
  Complete Truth was read through the public `project.inspect` Facade.
- The iPad logical grid journey used JavaScript DOM clicks and
  `PointerEvent` with `isTrusted=false`, actual Safari and actual packaged
  Wasm. It did not prove native pointer capture, browser gesture arbitration,
  finger accuracy, scrolling during a drag or physical ergonomics.
- One native tap completed with a driver workaround. Trusted keyboard Enter
  activated audio. Neither proves native dragging or hearing.

The public mono WAV fixture was 48 kHz, 21,600 frames, 43,244 bytes, SHA-256
`41b96b009edde0ce0ceb125f7d18f6fe5cabc53500a9fd9de0650a20082f71a2`.
The iPad fixture used File/DataTransfer injection; the native file picker was
not accepted. No physical microphone capture was tested.

The distribution manifest SHA-256 was
`a2b91682d1603bbfae7d73c7bfbb13be6d8352ab27fd2a68c9af4139606a7a6b`.
All six running assets were byte-verified (8,998,611 bytes total; Wasm
8,140,306 bytes). The temporary public tunnel did not finish the initial Wasm
load. A private LAN HTTPS server then served the same unmodified bytes;
secure context and cross-origin isolation were true. Its one-day self-signed
certificate was accepted only through the isolated session's
`acceptInsecureCerts`; nothing was installed in device trust stores.
`webkit:alwaysAllowAutoplay` remained false.

## iPad journey and far-side assertions

The main logical session used Project
`7ac1259d-a40e-46e8-9ece-76ef922bbbac`, Pattern
`50120b91-ad02-4e7a-83b7-388a350f3e81`. Fixture assignment made revision 1.
Each row below is scoped to the instrument named above. Undo/Redo waits for
enabled controls and exact rendered fields, rather than note count alone.

| Transition | Observable result |
| --- | --- |
| Add | A1 onset 480, duration 240, velocity 100; revision 2; one edit request |
| Move → Undo → Redo | A1 480 → 960; revisions 3 → 4 → 5; exact Truth event and UI fields restored in each direction |
| Resize → Undo → Redo | Duration 240 → 960 at onset 960; revisions 6 → 7 → 8; exact fields restored |
| Velocity → Undo → Redo | Velocity 100 → 64; revisions 9 → 10 → 11; exact fields restored |
| Cancel move | Preview reached onset 1440, then pointercancel; full Truth remained revision 11, zero edit requests |
| Snapped no-op / VEL tap | Full Truth remained revision 11; zero edit requests |
| Add second note | A2 onset 1920, duration 240, inherited velocity 64; revision 12 |
| Box selection | Two notes selected; Truth and revision unchanged |
| Batch move → Undo → Redo | A1/A2 onsets 1440/2400; revisions 13 → 14 → 15; one command with two removals and two puts; exact restoration |
| Batch delete → Undo → Redo → Undo | Two notes deleted in one command; revisions 16 → 17 → 18 → 19; final two-note Truth restored |
| Conflict refusal | Controlled expected_revision 19 → 18; actual Core returned REVISION_CONFLICT with actual_revision 19; complete Truth unchanged and conflict reason shown |
| Failure before dispatch | Controlled Host send rejection, before forwarding to Core; zero Core edits, complete Truth/revision 19 unchanged and failure reason shown |

The two fault injections were removed afterwards. A failure before dispatch
does **not** cover an edit committed before `publication: failed`.
Standalone add/delete Undo/Redo and collision/seam/snap variants are not
claimed as independently covered by this iPad session's table.

Twenty-three of the original 24 logical snapshots matched the exact UI
projection at capture time. `logical-batch-move.json` captured committed
Truth before equal-count UI fields refreshed. The original discrepancy is
retained in the evidence. An early Undo attempt also encountered a disabled
control. The harness was corrected to wait for every note field and enabled
history controls; subsequent batch Undo/Redo snapshots matched exactly.
These observations do not establish a product defect or erase the transient
negative evidence.

## Recovered session: reload, live edit and recording fence

After the native driver wedge described below, the operator force-quit and
reopened Safari. The old driver session became invalid; the new isolated
automation session started with a fresh Project. Safari documents this
[isolation from earlier sessions](https://developer.apple.com/documentation/safari-developer-tools/webdriver).
An empty new session is not evidence that the previous Project was lost.
No read of the previous Project after its native drag was obtained.

The new Project was `299d14bd-9522-4395-8b9b-70c731c538e1`:

| Transition | Observable result |
| --- | --- |
| Fixture → two notes → refresh | Revision 3 with A1 onsets 0/960, duration 240, velocity 100; after native WebDriver refresh the **complete** Project object was equal to before, including identity, revision, assets and events; exact UI fields matched |
| Fresh history after refresh | SHIFT engaged; Undo and Redo both disabled; No changes in this session shown |
| Activate audio | Element Send Keys Enter produced trusted keydown, click and keyup on Activate audio; user activation became true, then Audio running; programmatic activation in the earlier session had stayed inactive |
| Play → edit while playing | Add A1 onset 1920; one edit, revision 3 → 4, exact Truth/UI; Core returned publication=live, generation 3, activation_frame 2616320 |
| Phase preservation | Before and after the live edit, playing=true and origin_frame=2585856; no transport restart was observed; this is protocol/state evidence, not audible continuity |
| Record → attempted grid tap | Real Sequence transport recording=true; grid disabled with Recording — stop recording to edit the grid; full Truth unchanged and edit count remained 1 |
| Record off → Play off → Suspend | Recording and playback stopped, grid enabled again; audio suspended; WebDriver session successfully deleted |

The reload row covers one retained isolated automation session only. It does
not cover force-quit retention, a new WebDriver session, background audio
interruption or cross-device persistence. The candidate's transport status
does not expose runtime_frame; no frame-progress assertion is claimed.
The initial harness tried that unavailable field and was corrected to use the
actual live receipt and unchanged origin. Exact Undo/Redo labels and dynamic
Record/Play labels were also corrected without changing product code.

## Native driver observations

On an independent button probe, native Element Click and W3C Actions returned
success but produced no completed click (counter 0), with missing timely
pointerup. Repeating the same grid tap flushed the first trusted down/up and
added A1 onset 0, duration 240, velocity 64: revision 19 → 20, one edit.
The surplus second pointerdown was cleaned with an explicitly untrusted
pointercancel. This is a partial trusted-tap observation with a workaround,
not reliable native input acceptance.

Native drag protocol request 1227, `Automation.performInteractionSequence`,
returned success. The next request 1228, `Automation.resolveBrowsingContext`,
received no reply; subsequent Truth inspection and session deletion timed
out. Last confirmed Truth was revision 20. The drag's committed result is
unknown. The retained protocol is consistent with
[WebKit bug 322937](https://bugs.webkit.org/show_bug.cgi?id=322937), but this
session did not establish a product or driver root cause.

The related operational pitfall is
[action receipt without input completion](../../.agents/pitfalls/safari-webdriver-action-without-input-completion.md).
Owned driver, LAN HTTPS server and public tunnel were stopped after testing;
their temporary links have expired.

## macOS observations and outstanding rows

Mac Project prefix `6705d3fa`: A1 fixture assignment at revision 1; add/delete/add
at revisions 2/3/4; a second note at onset 960 at revision 5, Undo/Redo at 6/7;
playing add at onset 1920 at revision 8. UI stayed playing, and two screenshots
showed different playhead positions. SHIFT Undo/Redo was disabled while playing.
Recording disabled edits; an empty-cell click kept revision 8 and three notes.
After stopping and reloading, the same Project prefix, revision 8 and all three
rendered note fields survived, with empty history. These are UI observations;
full Truth and phase were not measured on Mac. Native automation drags made no
observable edit and were not accepted as product failures or passes.

| Open row | Evidence needed to complete it |
| --- | --- |
| Physical drag/resize/velocity/box selection on iPad and Mac | Real finger/trackpad actions on an identified candidate; exact resulting Truth and UI; one command per gesture and Undo/Redo restoration |
| Hearing, including live swaps | Listener, output route and level; regular sample playback and whether live edits sound in place without interruption or restart |
| Committed publication failure | Actual committed revision plus failed publication and typed snapshot_error; retained Truth, UI reconciliation and recovery; pre-send rejection is insufficient |
| Device lifecycle | Same-origin retained Project identity and complete Truth across physical force-quit/background/interruption and reopen, with audio and ownership state recorded |
| Additional iPad edit variants | Independently observe standalone add/delete history, occupied-key replacement, seam clamp and relevant snap modes |

All these rows remain tracked by #1671. Merging this record leaves that Issue
open and does not convert earlier automated implementation proof into physical
acceptance.

## Retained evidence and change scope

The adjacent JSON retains the packaged manifest and byte verification, logical
row summaries, complete Truth for refusal/cancel/reload/live/recording witnesses,
actual command receipts, native probe events, protocol excerpt and shutdown
receipt. Device name and UDID were redacted. Original local JSON, screenshots,
scripts and command logs remain in `/tmp/lmdj-1671-acceptance`; the JSON includes
their byte lengths and SHA-256 inventory. Those temporary paths are ancillary;
the committed JSON is the durable evidence used by this record. Mac screenshots
and accessibility trees remain local and are described as observations only.

Version impact: none — this Task preserves evidence of an existing candidate.

Documentation impact: none — quality evidence and a tool-boundary pitfall only;
no Architecture Portal routes, projected identities or product behavior change.

Declared files: this ledger, its adjacent evidence JSON and the linked pitfall.
Task verification: parse the JSON; compare complete cancellation/refusal/reload
Truth, UI projections and live/recording receipts; staged new-file ownership
preflight; applicable documentation checks. No new product test or gate.
