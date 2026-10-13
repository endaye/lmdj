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
playing. Figma data is not a runtime value oracle. At the initial Task base,
small-screen scaling was a separate pending decision. The later approved
adaptive policy and U01 implementation are now included by the committed-main
integration below. This read-only display Task adds no hit targets or scaling
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
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs` (six
  previously admitted loading/inspect assertions; all other main journeys
  and budgets are retained).
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

## Current-main integration after review repair

Repair commit `26d68df71e23850c69c728d924c4449b2f90cb95` passed fresh normal
build/package and both complete Chromium browser files: 15 passed, one
existing WebKit-only skip, terminal exit 0, 1.2 minutes. The component suite
passed 254 tests, typecheck passed and final scope suite passed 77 tests.
Those receipts are retained under `/tmp/lmdj-u03a-review-repair-*.log`.
The commit was pushed and PR #2119 read back the exact head. No new review
workflow ran because the PR had actual merge conflicts (`mergeable=false`);
this was not successful or eligible current-head review.

Root admitted merging current main `50ecc7107a3347878e1d5aa7f72b031d7d58eb98`
without rewriting the pushed history. `git merge --no-commit --no-ff` returned
exit 1 with two Portal content conflicts, retained in
`/tmp/lmdj-u03a-main-merge.log`. They were adjacent facts in
`creator-interactions.mdx` and the shared historical paragraph in
`creator-web.mdx`. Resolution retains main's U02a text rail, SHIFT-after-Bank
and native Tab order, together with U03's current upper-display layout and
explicit historical T9/T10/T11 attribution. No new behavior was added.

The automatic merges were inspected against main: `workspace_shell.test.tsx`
keeps all U04 single-column navigation cases and adds only U03's independent
Bank/Quantize fact assertions; the complete hardware-layout browser file
keeps U02a rail and U04 Project journeys plus the six repair loading/inspect
far-side assertions. Imported main product/producer changes are unchanged
from their merged source. The staged diff against main remains the declared
U03 files plus the previously admitted browser repair path.

The combined input must rerun all eight whole component files, Creator
typecheck, Portal, scope ownership, fresh normal build/package and both full
browser files. Previous receipts remain evidence only for their original
inputs. At this integration declaration, typecheck passed; component tests
are running and Portal/build/package/browser remain UNRUN, awaiting Root's
heavy window. A clean merge checkpoint for the normal packager may be created
only after source/Portal checks and staged inspection pass. Do not push before
the combined artifact browser checks pass; real review finding 3 remains for
the automated final-head repair review.

Integrated source results: the same eight whole component files passed
256/256 tests, exit 0, 69.82 seconds
(`/tmp/lmdj-u03a-main-merge-components.log`); whole Creator typecheck exited 0
(`/tmp/lmdj-u03a-main-merge-tsc.log`); scope ownership passed 77 tests, exit 0,
8.674 seconds (`/tmp/lmdj-u03a-main-merge-scope.log`). The staged diff against
main has exactly the 15 admitted U03/repair paths, no unmerged entries and no
unstaged files. Staged whitespace check passed. Portal and artifact/browser
verification remain UNRUN for this merged input until their actual terminals
finish in Root's heavy window.

The integrated whole Portal check subsequently exited 0
(`/tmp/lmdj-u03a-main-merge-portal.log`): 177 tests, 52 pages, 10 diagram
sources/20 outputs and 50 routes with internal links. Root admitted the
clean-source merge checkpoint after this result, solely as the input to the
normal packager. Fresh build/package and the two complete browser files will
bind to that merge head; their final receipts will be handed to Root for PR
Verification without another source or plan amend.


## Committed-main integration after C1 and Recovery

Root admitted a source-only merge from the pushed head
`12f3ec5834274ce9fc5aacd901e056d2627953af` to captured fresh main
`35455f7576fc96ad253f2d5a523ba457e1df9321`, retaining the pushed history.
The complete original 15-file Task diff and a hash inventory of 50 existing
receipt/artifact files were preserved under
`build/verification/u03a-integrate-35455f75/` before the merge. Live #2112 was
read again; its older integration status is historical, not current source
proof. Main includes U01 actual-target/adaptive layout, U05a Playback, U06a
Grid Tools, U09 Sound Sets, U11 System, U12a Recovery and C1 typed Filter.
The last advancement from `0909a301` to `35455f75` changes only release/version
inputs; none of the Creator or owning Host Portal inputs changed in that step.

The original `12f3ec` input completed its normal build/package and both full
Chromium hardware-layout/accessibility files, with 15 passes and the existing
WebKit-only skip. Those results remain bound to the old input. They do not
verify the newly integrated C1, Recovery or compact 152px upper display.

`git merge --no-commit --no-ff` reported exactly two content conflicts, both
inside the declared Host Portal files. The System table combines U03's
independent upper Project/Audio/MIDI display with U11's actual touch groups.
The shared historical paragraph keeps U01's adaptive geometry and U03's
explicit historical T9/T10/T11 attribution. Its former statement that all
remaining V4 capabilities are absent is now explicitly historical, pointing
to main's existing C1 Filter section. All separate Project, Playback, Grid
Tools, Sound Set, System, Recovery and C1 sections are retained. No producer,
controller, interface or lifecycle decision is changed by the resolution.

The automatically merged `workspace_shell.test.tsx` differs from captured main
only in U03's independent Bank and Quantize assertions. All incoming System,
Sound Set, Recovery and Project cases remain byte-for-byte present. The whole
hardware-layout browser file differs from captured main only by the six
loading/inspect assertions from the earlier U03 repair. Main's complete
adaptive/44px geometry and C1 Cutoff/HOLD/MASTER journey remain intact,
including every request/readback, silent Pad traversal and Truth assertion.
The overview production components are unchanged from `12f3ec`.

The later automated review's proposed assigned-Pad `UNAVAILABLE` trigger does
not match the current source: `padContent` returns a real category or SAMPLE
for assigned Pads, EMPTY for an unassigned existing Pad, and UNAVAILABLE only
when the selected slot is absent from Project projection. The existing
LOADING repair, assigned-loading-to-inspect component case and actual held
inspect browser leg are retained; no production branch is changed to conflate
missing authority with a pending request. Root owns review-thread disposition.

This integration remains source-only at this declaration: all eight whole
owning component files, Creator typecheck, scope ownership, whole Portal,
fresh normal build/package and both complete browser files are UNRUN for the
combined input. Their full selections, deadlines and journey legs are retained.
Root must release the shared resource window before execution; S6 currently
owns the Portal window. No clean merge checkpoint, push or PR transition is
claimed by static conflict resolution. Device, audible output and the full
35-screen acceptance remain separate from these Task checks.


Root then admitted one complete low-tier sequence on the frozen integration
index tree `a4bf312925e6765090c9f550bafdb4c309659ce4`. It ran from
2026-10-13 08:03:36.418 UTC to 08:05:09.761 UTC, without test filtering,
retries, source edits or deadline changes. The same eight whole component
files passed 258/258 (Vitest 80.90 seconds); full `tsc --noEmit`, syntax checks
of both complete owning browser files, the full 77-test scope suite (8.988
seconds), and staged/unstaged whitespace checks each exited 0. The component
log retains the non-failing jsdom stylesheet and Node localStorage warnings.
No product or test source was changed in response to them.

All 15 source hashes and the entire index tree matched before and after the
sequence. Raw logs and exact commands, timestamps, exit codes, log SHA-256s
and observed owned process groups are in
`build/verification/u03a-integrate-35455f75/low-tier-run-receipt.json` and its
sibling logs. `low-tier-after-release.json` records the natural terminal exit
0 and confirms that runner PID 20016 and all seven command groups are absent.
The low-tier window is explicitly released. Only this plan's result record
changes afterward; all product, CSS, tests and both Portal pages retain the
tested bytes. Whole Portal, normal fresh build/package and both full browser
journeys remain UNRUN for this integrated candidate, awaiting Root's heavy
admission. The merge is still uncommitted and no PR action has been taken.


## Integrated verification completion — 2026-10-13

Root transferred the sole heavy window to Codex `/root/control_kit` at
10:04:42 UTC after the preceding owner's actual release. The frozen 15-file
packet remained SHA-256
`059e6014f21a6a04f7e2eb4197caa3ffb803738cbc9894dda10a150555a7541e`.
The earlier 258 whole-component cases, full Creator typecheck, two browser
syntax checks and 77 scope cases remain bound to the same non-plan bytes.
No product, stylesheet, test, Portal or deadline changed during this window.

Whole `bash scripts/docs-site.sh check` ran 10:06:18–10:06:58 UTC, exit 0:
179 tests, 52 pages, 10 diagram sources/20 outputs, all 50 routes and links.
The clean two-parent checkpoint
`7dbe2e26cbd37912e31131ff96619dcd98aa6683` preserves published parent
`12f3ec5834274ce9fc5aacd901e056d2627953af` and integrated main parent
`35455f7576fc96ad253f2d5a523ba457e1df9321`; its tree is
`9210026d32c0d56e5ea56935d5dc35ce2b3d6ee1`. No published history was rewritten.

The retained official all-64-Pad fixture was independently verified again:
767554 bytes, SHA-256
`66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`.
No fixture regeneration or foreign product binary was used. Normal
`bash scripts/creator-web.sh build` at 10:08:44–10:09:15 UTC and
`bash scripts/creator-web.sh package` at 10:09:47–10:09:48 UTC both exited 0,
using pinned Emscripten 6.0.5, Node 26.7.0 and two build workers. The build
recompiled the Runtime Bridge and built this worktree's Creator assets.
Existing dynamic-import/chunk-size warnings remain in the raw log.

The original complete command then ran 10:09:52–10:11:10 UTC:

```sh
npm --prefix tests/platform/web test -- --project=chromium \
  creator/creator_web_hardware_layout.spec.mjs \
  creator/creator_web_accessibility.spec.mjs
```

It naturally exited 0: **15 passed, one existing WebKit-only skip**, one
worker, all 16 selections and original budgets. The original Project
selection/Open/keyboard/reopen, all-Bank traversal, actual scaled targets,
local font/CSP, Tempo release/reload, Sample held inspect/failure/retry/empty/
Undo/System/reopen, and Perform silent Pad/SHIFT/HOLD/MASTER legs remain.
The C1 owning case waits for the typed Cutoff binding and its applied value
before turning it; its request and unchanged-Truth assertions passed.
`LMDJ_CREATOR_WEB_OVERVIEW_BUNDLE` was unset, retaining the documented
all-Pad fallback. No grep, retry, test edit or budget override occurred.

### Supplementary geometry and the retained diagnostic

A separate ignored Playwright script inspected the actual package at
768×600, 1280×600 and 1440×900 in all seven modes: Project, Sample, Sequence,
Perform, System, Sound Sets and Slice. All 21 records and 28 PNGs were written
10:15:35–10:15:44 UTC. This supplements geometry only, and does not establish
catalog, Slice-job or audio success or replace an original behavior journey.

The supplementary command's original **exit 1 remains retained**. Its strict
pairwise Range predicate found seven fragment-pair intersections between
Perform's BAR and BEAT lines at each viewport: one logical pixel (1.256
screen pixels at the wide scale). Root and the executor viewed all three
exact PNGs: painted glyphs are visibly separated. The 13-pixel font rectangle
exceeds the 12-pixel line spacing; this is a font-box diagnostic, not
demonstrated painted overlap. Root accepted that evidence with this explicit
disposition. The threshold, source and raw result were not changed; the
command was not rerun or relabelled PASS. The helper's `painted` field names
a clipping-adjusted Range rectangle, not measured glyph-ink bounds.

Across these 21 states, all 723 text rectangles remain within the outer
display, with no clipping (raw and clipping-adjusted edges match even below
the predicate tolerance), text/encoder or text/grid overlap, grid/header/
encoder overlap, or horizontal/vertical overflow. The only pairwise
intersections are the font rectangles above. The executor inspected all seven
768px mode PNGs and wide Perform; Root independently inspected all 21 JSONs
and three Perform PNGs. This is not every error/long-label state or a physical
device check.

The first 768px Perform screenshot shows Filter/Delay/Reverb at 50%; later
1280px/wide screenshots show Cutoff 20.0 kHz and Delay/Reverb 0%. The geometry
helper waits for the mode and two animation frames, not authoritative live
readback. Existing `initialPerformState` starts its legacy FX mirror at 500
with `liveControl.available=false`; `PerformSurface` publishes those
contextual encoder bindings while `connect()` asynchronously starts
`refreshLiveStatus()`. The applied live-status reducer later supplies typed
Cutoff and other FX values. The first screenshot proves layout of the early
state, not that Core applied 50%. File-write times and source support this
explanation; no transport trace identifies the exact response timing. The
helper sends no FX gesture. App, PerformSurface and the controller are
unchanged from integrated main; the original C1 browser leg independently
provides applied-readback behavior evidence.

### Receipts, current-main scope and remaining boundaries

Commands, timestamps, natural exits, raw log hashes, own-server records,
fixture/source/distribution identities and results are retained under
`build/verification/u03a-corrected-main-final/`.
`retained-artifact-manifest.json` binds 98 files, SHA-256
`e359687e5da60fe67e00077fa4fd24e86f5ee559d089383a5d8f8c34fb6ce531`.
`final-release-and-retention.json` records explicit release at 10:17:26 UTC:
all 200 observed owned PIDs were absent; both browser commands ended naturally
and both own servers were terminated and waited only afterward. All 15 source
and distribution hashes matched their pre-run values; the worktree was clean.
Root independently verified all 98 hashes, both source manifests and the
absent process inventory at 10:23:02 UTC. The readback/clipping analysis is
retained at `/tmp/lmdj-u03a-readback-clipping-audit.json`.

The final read-only refresh is main
`28ff18c5c1f3790157193e900b5c7980cc595026`. The pre-edit guard caught the
concurrent advancement beyond `0c873e67` and stopped before tracked writes;
the new committed inputs were then read. Since integrated `35455f75`, main
adds Build 2.0.96.0/snapshot evidence, U02b Pad palette/category presentation,
the headered FX TypeScript correction, U12b Capture and U05b1 Trim. The only
Task-path intersections are the two Portal files, whose new hunks concern
Pad, Capture and Trim paragraphs. Shared palette tokens affect Sequence
colors, but the latest Capture/Modal and Trim/Waveform changes do not change
an overview component, controller, App wiring or either owning browser spec.
No rebase or integration of those later changes is claimed. The verified
package remains Build 2.0.95.0 with the earlier palette, Capture and Trim.
There is no full-current-main, new-palette, complete Creator, final 35-screen,
physical-device, audible/PCM, release or deployment acceptance claim.

Only this plan changes after `7dbe2e26`; all 14 non-plan Task files retain
their verified bytes. The final record is a separate atomic commit, not an
amendment of a published head. Root retains final source review, push,
current-head authenticated review, conversation/protection checks and merge.
Older dependency failures, the Sample loading RED, review collection failures
and previous proof remain history. #2118's merged preparation fix is separate
from authentic review eligibility for the next U03 head; no owner attestation
or review bypass is inferred. U03b source/catalog/job projections, F04 meters
and the broader full-candidate/device acceptance remain separate.

Documentation impact for this final record: none — both current Host pages
are byte-identical to the completed Portal input. Version impact: none.
No Portal/build/browser repetition is claimed for this plan-only record.
The transient legacy readback and CSS font-box metrics are derivable from
source; this supplemental diagnosis introduces no new pitfall recurrence or
control-plane gate.

Final source-only checks ran after the one-file plan staging: the full scope
suite passed 77 tests at 10:32:10–10:32:19 UTC, and PR-body closing-directive
lint exited 0. `local-ci.sh --list --pr-body` selected exactly Creator,
docs_static and Portal without running lanes; its declaration state was
planned. The separate `--declaration-only --pr-body` then actually validated
the declaration, exit 0 at 10:33:09 UTC. Exact staged-path, non-plan hash and
whitespace checks passed. These light receipts are under
`build/verification/u03a-finalization/`; no heavy suite was repeated.
