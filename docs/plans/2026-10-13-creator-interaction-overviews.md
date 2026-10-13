# Creator Interaction UI — U03 upper displays

Date: 2026-10-13. Tracking: #2112. Owner: Codex `/root/capability_audit`.

## Premises and scope

Task worktree and initial `origin/main` were both
`9fb83ce0f70de1bc9114711bf9e854dfa6bb7081`. Live #2112 and its comments were
read before editing. The existing five overview components already own real
Project, Sample, Pattern transport, Performance and encoder projections. They
must be reused; no new audio producer belongs to this Task. Recent #2109/#2110
deliver Perform navigation/accessibility, not the upper display arrangement.

The 2026-10-13 refresh is `fe6f30bbf3897d3b09e25e4e85f4b1b22df7db23`.
Intervening D0 #2114, B01 #2115, retained-assignment producer #2107 and Replay
regression #2116 do not change the owned overview components or tests. B01's
GROOVE paragraphs in `creator-interactions.mdx` must survive integration; this
Task edits only its upper-display paragraphs. The outstanding dispositions
remain the same; no unrelated reimplementation or rebase is required.

Still outstanding at the Task base: readbacks precede the body; Project uses the
older Project/Content/Workspace columns; System changes only the heading and
leaves the underlying mode's body visible; Sample/Sequence/Perform spacing is
the older layout. These are positively observable in `overview_display.tsx`,
its four child overviews and the existing owning tests.

U03a is one Task/commit: arrange the existing read-only data into the new
heading/body/readbacks layout and give System its own Project/Audio/MIDI
context. Do not change App, physical controls, touch controls, shared CSS,
Performance controllers, transport, editing, focus or storage behavior.

U03b remains a separate integration task: Slice's selected source, provider
job and result live inside `CandidateSurface`; the upper display has no such
projection. Do not call the selected Sample Pad the analysis source or display
the example “4 slices”. Sound Set catalog/install state is likewise owned by
its surface. U03a shows Project facts and workflow guidance, not synthetic
catalog/install progress. Root coordinates future source-to-display wiring.

## Figma context and state coverage

Authority: file `GPFarNiZNsjLQzfG9kR8DO`, page `400:67`. Metadata mapped all
35 upper displays; high-fidelity design context and screenshot were read for
the seven distinct display bodies below plus the empty Pad frame `407:6909`.
The page itself is a canvas and did
not return design context; its actual upper frame IDs did. No image assets are
needed: waveform/grid/progress are data projections, and remaining layers are
text, backgrounds and layout.

| Screens | Upper frame reference | Current source and retained facts |
| --- | --- | --- |
| Project, Recovery | `401:3731` | Open Project identity, storage qualifier, content counts, BPM/Banks, Audio/MIDI, failure state; selection is never opening. |
| Sample Trim/Playback/Tone/Pad, capture/capture-trim/import/empty/capture-ready/replace-confirm/prepare-failed, future-assign/numeric | `401:3954` | Selected Pad category, actual metadata/whole waveform/trim, pending target, loading and last-action error; stale Pad/revision must not leak. |
| Sequence Edit/Setup, queue/grid-tools/capture-sequence, future-sequence | `403:1224` | Eight real tracks, actual playing identity, edit window, transport/playhead, BPM/swing previews, pending/queued/error/recovery facts. Count-in is a separate producer/consumer Task. |
| Perform Live/More/Slots/Takes/Replay, perform-recording, future-filter/mute | `404:1613` | Explicit global PATTERN PLAYING/QUEUED/POSITION, bar/beat/progress, separate Performance pending/acknowledged launch, Bank/Quantize/assigned slots/recording phase. Meter remains F04, owned by its original machine/owner. |
| Sound Sets Browse/Details/Target/Review | `405:1563` | Actual Project/storage and static catalog/target guidance; do not invent installation state. |
| Slice | `406:2216` | Actual Project/storage; source/result guidance points to the owning touch workspace until U03b supplies their real projection. |
| System | `406:2461` | Project/Audio/MIDI facts regardless of underlying mode; retain global transport and actual encoder bindings. |

The common Figma frame is 752×176 with 16 padding, 22 heading, 68–74 body
and 24 readbacks. Reuse existing offline fonts and colour tokens. Preserve
supported facts the examples omit, including no Project/Pad, publication
pending, Sample saved/audio pending, unknown/unavailable and queued versus
playing. Figma data is not a runtime value oracle. Small-screen scaling is a
separate pending decision; this read-only Task adds no hit targets or scaling
policy and does not weaken the approved 44 minimum actual hit area.

## Declared files

- `apps/creator-web/src/components/overview_display.tsx`
- `apps/creator-web/src/components/overview_display.css` (new, locally scoped)
- `apps/creator-web/src/components/project_overview.tsx`
- `apps/creator-web/src/components/sample_overview.tsx`
- `apps/creator-web/src/components/sequence_overview.tsx`
- `apps/creator-web/src/components/perform_overview.tsx`
- `apps/creator-web/test/overview_display.test.tsx` (new)
- `apps/creator-web/test/project_overview.test.tsx`
- `apps/creator-web/test/sequence_pattern_overview.test.tsx`
- `apps/creator-web/test/perform_overview.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx` (only the Bank/Quantize
  assertion; Root assigned this exact edit after the first whole-file run)
- `apps/docs-site/docs/hosts/creator-web.mdx` (upper-display sections)
- `apps/docs-site/docs/hosts/creator-interactions.mdx` (upper-display sections)
- This plan.

## Verification

Lowest layer: whole `overview_display`, `project_overview`, `sample_overview`,
`sequence_pattern_overview`, `perform_overview`, `overview_context`,
`workspace_shell` and `monitor_output_controls` Vitest files, then whole
Creator `tsc --noEmit`. Defects: wrong object, stale/hidden System context,
lost pending/failure/readback facts, conflating queued/acknowledged with
playing, and read-only content triggering commands. Existing waveform draft,
Pad identity, transport tick and unsubscription assertions remain intact.
New files also require `tests/build/ci_change_scope_test.py` before push.

Browser/computed geometry and the original hardware-layout/accessibility
journeys run only in Root's shared window. They check
visible heading/body/readbacks, all eight tracks, long qualified status text,
no overlap, and actual dynamic state; component assertions do not prove pixels.
Root serializes heavy verification. Whole Portal check has completed. Root
subsequently admitted the clean-checkpoint, fresh normal build/package and
whole owning hardware-layout/accessibility journeys. Their completed receipts
are recorded separately below.

Pitfall review: open creator/product entries were read. No new recurrence is
claimed merely for discovering a pre-existing UI gap. Per-transition assertions
must be read before a later transition can overwrite their evidence.

## Version Management

Version impact: none to version identities in this source Task — Creator
presentation only, no Contract/Module API or Product Build allocation. Host
version bookkeeping follows Root's integration plan; no release or
deployed-build claim is made by this source Task.

## Documentation Impact

Documentation impact: required — `/hosts/creator-web/` and
`/hosts/creator-interactions/` must describe the new upper-screen arrangement
and System precedence. Root assigned the upper-display sections to this Task
after U02a/U04 froze adjacent work. Complete Portal checks before shipping.
This plan is not a substitute for those current-page updates.

## Transport domain review

D04/T11 requires actual playback facts. `PerformanceRecordStatus` exposes
`pendingLaunch` and `lastLaunchAck`, but no current Pattern/position clock;
`PerformanceReplayStatus` exposes replay state and event cursor, not that clock.
Therefore the first three Perform columns explicitly say PATTERN and use only
the global Pattern transport. The existing separate launch cue keeps its
Performance pending/acknowledged receipt and fallback Pattern-switch behavior.
A coexistence test supplies different pending targets in both domains and
checks the labels and values independently. No new product decision or producer
is introduced. Long labels are at most 16 characters at 9 px in 162 px columns;
the real-page geometry check below confirmed them without truncation.

## Result

Source and current-Portal prose prepared. First whole eight-file component
run: 248 passed, 2 failed, exit 1 (`/tmp/lmdj-u03a-components.log`). The failures
identified loss of the Project's existing assistive BPM projection and a
workspace assertion tied to the old Bank/Quantize text order. Restored the
projection without changing that assertion. Root granted only the other
assertion's edit: it now checks independently labelled Bank and Quantize
outputs, rather than a loose textual-order regex.

After these fixes and two additional empty/failed-Sample cases, the same eight
whole files passed 252/252, exit 0
(`/tmp/lmdj-u03a-components-second.log`, 74.80 seconds). Whole `tsc --noEmit`
also exited 0 (`/tmp/lmdj-u03a-tsc-second.log`). Restoring the standard
`visually-hidden` treatment for duplicated Perform state and disabling live
announcements for the transport-position output retained 252/252, exit 0
(`/tmp/lmdj-u03a-components-final.log`, 70.70 seconds) and full typecheck.
After the transport-domain clarification and coexistence case above, the same
eight whole files passed 253/253, exit 0
(`/tmp/lmdj-u03a-components-domain.log`, 73.09 seconds), and whole typecheck
exited 0 (`/tmp/lmdj-u03a-tsc-domain.log`). No deadline, skip or selection was
loosened; the two original failures remain preserved.

First whole Portal check exited 1 during collection because this new worktree
had no docs-site dependencies (`/tmp/lmdj-u03a-portal.log`); no product build
ran in that attempt. The six tracked Portal links were confirmed as real
symlinks with existing targets. Locked `npm ci --prefix apps/docs-site` exited
0 (`/tmp/lmdj-u03a-portal-install.log`), without lockfile changes. The exact
same whole Portal check then exited 0 (`/tmp/lmdj-u03a-portal-second.log`):
177 tests, 52 pages, 10 diagram sources/20 outputs, 50 routes and internal
links. Root's heavy window was released immediately after the terminal result.

Staged scope verification passed 77 tests, exit 0
(`/tmp/lmdj-u03a-scope-final.log`, 9.372 seconds). The exact 14-file staged
inventory and whitespace check passed. Root authorized clean checkpoint
`15580c74e4faa64a30d978ca902e917c56873052` solely to satisfy the normal
packager's clean-source requirement; it was not itself a browser-pass claim.

Fresh `scripts/creator-web.sh build` used this worktree's source, pinned
Emscripten 6.0.5, Node 26 and two build workers. It and the normal
`scripts/creator-web.sh package` both exited 0
(`/tmp/lmdj-u03a-build.log`, `/tmp/lmdj-u03a-package.log`). Browser dependencies
came from the locked `tests/platform/web` installation. The tracked
`deployment/creator_project_fixture.mjs` was decoded independently in this
worktree: source SHA-256 `df718fc7b0dc08b6f806767a31ee55e0628b0e03c571ad79483310276f5facd1`,
bundle SHA-256 `66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`,
767554 bytes. Normal bundle verification passed. The original overview
journey used its supported all-Pad fixture fallback; no foreign native binary
or handwritten Project archive was used.

Against an owned normal packaged server, the complete unmodified
`creator_web_hardware_layout.spec.mjs` and `creator_web_accessibility.spec.mjs`
Chromium selection exited 0: 15 passed and the existing WebKit-only case
skipped, 1.3 minutes (`/tmp/lmdj-u03a-browser.log`). It retained all viewport,
keyboard, real-Wasm loading/failure/recovery, Truth-unchanged, empty Pad,
Undo, System and reopen assertions. The three-viewport mode geometry checks
passed without changing their oracle, deadlines or selection.

Supplementary Playwright CLI checks used that same packaged server and actual
boot-created Project. Perform and System at 1440×900 and 768×600, plus Sound
Sets and Slice at 768×600, produced six geometry receipts: zero out-of-bounds
text, zero intersecting text rectangles, and matching scroll/client dimensions
of 752×176. The four captured upper-screen PNGs were visually inspected;
`PATTERN PLAYING / QUEUED / POSITION` remains complete. Evidence is under
`/tmp/lmdj-u03a-visual/output/playwright/`, including `geometry-summary.json`.
The local proof server has no catalog upstream; its catalog 404 diagnostics
were observed, not represented as catalog/install success. This supplemental
pass does not replace the complete original browser journeys.

The owned browser was closed and server PID 5356 terminated after checking
its command identity; its shutdown exit 143 is not a test result. Root's heavy
window was then released. Only this plan's verification receipts changed
after the tested checkpoint; product source, CSS, tests and both Portal pages
are unchanged. Current-head independent review and integration remain Root's
responsibility. Device, listening/PCM, complete Creator proof and the
35-screen acceptance ledger remain unverified; this Task does not close U03b,
F04 or F05–F08.


## Review repair — assigned Sample inspect pending

Current PR head `123f111bb940fd6565231b381badd1d436d00e17` received an eligible
automated review. Finding 3 is confirmed: an assigned Pad waiting for inspect
has a LOADING title but the new overlay says “Sample details unavailable”.
The overlay remains required for loading/empty/error feedback; only its actual
LOADING subtitle changes to “Loading Sample details…”. No error attribution,
controller, state Contract or unavailable/no-Project/no-Pad policy changes.
Latest inspected main is `45c8f479aa350cd490a100044a4723428976e2be`; the rail
merge does not deliver this subtitle repair.

Root authorized a separate review-repair commit over exactly four files:

- `apps/creator-web/src/components/sample_overview.tsx` — the subtitle branch.
- `apps/creator-web/test/overview_display.test.tsx` — assigned/loading text,
  followed by inspect resolution and overlay removal/format readback.
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs` — extend
  the existing real hold-inspect leg with subtitle assertions and the far-side
  removal/format check. This is the one additional owning path; no other
  browser case, selection, timeout, failure/retry, Undo or reopen leg changes.
- This plan — scope and repair evidence.

First add the component and browser assertions while source still has the
defect, then run the whole owning overview-display component file for RED.
Fix the subtitle and rerun the same eight complete component files plus whole
Creator typecheck. Heavy build/package and both complete original browser
files wait for Root's resource window. Original empty/error cases remain.
The tested defect is pending loading being represented as unavailable, not
whether all metadata-null states should be called loading.

Documentation impact: none for this repair — the two frozen current Portal
pages already describe loading versus empty/error feedback and remain correct;
the repair aligns source text with that contract. Version impact: none — no
manifest, API or Product Build allocation. No qualifying pitfall: the owning
regression assertions express this product defect. Repair verification is
UNRUN at this scope declaration; the earlier U03a receipts remain historical.


Repair source verification: before the source fix, the complete
`overview_display.test.tsx` file returned 15 passed/1 failed, exit 1, at the
new “Loading Sample details…” assertion on line 118
(`/tmp/lmdj-u03a-review-repair-red.log`). After the narrow subtitle fix, the
same eight complete component files returned 254/254 passed, exit 0, 75.08 s
(`/tmp/lmdj-u03a-review-repair-components.log`); whole Creator typecheck also
exited 0 (`/tmp/lmdj-u03a-review-repair-tsc.log`). No Portal page changed.
The subsequent clean-source repair commit is the normal product packager's
input; its browser result will be recorded in PR Verification after the
authorized heavy window, without amending an already pushed head.
