# Creator Interaction UI Sequence SETUP — U06b

## Premises and ownership

Related issue: #2112, screen 07. Fresh `origin/main` and this Task's base are
`692d2ac18397190f71a54ce0297e5e0a54cee5ab`. Worktree:
`lmdj-goal-sequence-setup`, branch `feat/creator-sequence-setup-layout`, created
with `--no-track` and command-local `core.symlinks=true`; all ten tracked links
are actual links. The live issue and its comments were refreshed before edits.

Figma `404:765` / SETUP child `404:1465` was read as full design context and
screenshot. Current main already provides Tempo/Swing previews and commits,
steps, TAP, current Pattern length, Double Up, Copy, New, three SEQ SNAP choices,
Quantize, Metronome and Playback details. The remaining work is presentation:
the two parameter cards share a narrow row, TAP is separated from Tempo, and
the settings lack the new vertical grouping and visible toggle readbacks.
U06a's Grid Tools and B01's queued-current cancellation are already delivered;
do not repeat or alter them. The shared GROOVE/EDIT/SETUP header, all sixteen
EDIT lanes and grid coordinate geometry remain outside this Task.

Root confirmed SequenceTouchWorkspace has no S6 delta between the inspected
S6 base and frozen candidate. U12a owns Recovery/App and the Sequence browser
file, but not SequenceTouchWorkspace product source. This Task owns SETUP JSX,
one local stylesheet, its existing component tests and the two Portal SETUP
paragraphs. The Sequence browser file was initially held until Root confirmed U12a's
writer release; the current source-only admission is recorded below. C1, S6, U05 and all other
worktrees are untouched. No App, global styles, controller, SDK or producer edit.

## Declared files

- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/sequence_setup_layout.css` (new)
- `apps/creator-web/test/sequence_surface.test.tsx`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs` (append three SETUP cases only)
- `apps/docs-site/docs/hosts/creator-web.mdx` (SETUP only)
- `apps/docs-site/docs/hosts/creator-interactions.mdx` (SETUP only)
- `docs/plans/2026-10-13-creator-sequence-setup-layout.md`

## Implementation

Stack Tempo and Swing at full available width, retaining ValueSlider and every
existing gesture callback. Place decrement/TAP/increment together for Tempo;
retain ENC3's hint and Swing's existing step controls. TAP remains hidden while
the New Pattern length form is open, exactly as before; its clock and refs do
not change. Put BARS above its four choices, then Double Up/Copy/New together;
the New form keeps its existing length, Cancel/Create, visibility and locks.
Place the three SEQ SNAP choices under their own label before Quantize and
Metronome, whose On/Off text reads only their existing controlled props.

Keep all accessible names, callbacks, requested-value refs, selection, preview
and cancellation behavior. Playback details, recording locks, recovery and
errors remain reachable. The root touch workspace owns vertical scrolling;
do not add another scroller, absolute hit overlays or smaller hit areas. Reuse
U01's 32-face/44-hit controls and test actual geometry on the final package.
Visual BPM preview remains distinct from the separately owned audible preview.

## Verification

Lowest tier: complete `sequence_surface.test.tsx`,
`sequence_pattern_structure.test.tsx` and `value_slider.test.tsx`, then full
TypeScript. New focused assertions cover the Tempo/TAP grouping, New-form TAP
visibility and cancel/create lifecycle, and visible toggle text following the
actual props rather than optimistic local state. Existing tests retain all
preview/cancel/refusal, rapid steps, recording/playing locks, structure, device
preference and recovery expectations. These component checks do not prove
rendered CSS geometry or real native input.

After the browser writer and sole heavy window are explicitly released:

1. Append three viewport (1440×900, 1024×768, 768×600) layout/native-keyboard
   checks to the existing Sequence spec, preserving its entire original body,
   every leg and deadline. Verify normal vertical flow, horizontal fit, full
   labels, actual control bounds at least 44 CSS px and center/edge hit points.
   Each mutation must cross to inspected Truth or the owning device preference;
   screenshots and geometry JSON supplement those assertions.
2. Whole Portal, declared-file/scope and whitespace checks; then a clean source
   checkpoint for fresh normal Creator build/package, never a foreign binary.
3. Complete original Sequence (10 cases) and Metronome (5 cases) specs plus the
   three new layout cases. Preserve all original sequence transport, exact
   notes/revision/reopen, Record-off lost-ticket reconcile, owner-loss
   Keep/Apply and restart paths. Preserve the complete Tempo/Swing journey:
   preview→single commit, step, two TAPs, Escape cancel, failed commit with
   unchanged Truth, playing activation boundary, recording UI+Core lock and
   reopened readbacks. Preserve all seven length/Double/shorten/Undo/Copy/Undo/
   reopen legs and B01's full queued cancel→Stop→reopen journey. Preserve all
   five SEQ SNAP restore/switch/change/Stop/reload legs.
4. Metronome retains beat interval/accent/Stop, recording without Pattern
   mutation, digital silence in Perform capture plus the non-silent witness,
   mid-play cancel and preference reload/default-off proof. Do not replace
   PCM evidence with a visible toggle or omit the capture leg.

Portal/build/browser are UNRUN until admitted. A failure retains its original
raw receipt; no timeout extension, skipped test, weakened assertion or shortened
journey. No commit/push before the required verification and Root's checkpoint
coordination; no release, deployment or cleanup is included.

## Version Management

Version impact: none — layout and existing state readbacks only; no stored
state, Contract, Product Build or manifest changes.

## Documentation Impact

Documentation impact: required — `/hosts/creator-web/` and
`/hosts/creator-interactions/`, SETUP paragraphs only. Describe the grouping
and visible states without changing the existing behavioral contract.

## Pitfall Impact

Pitfall impact: none — no new process invariant. Existing journey-completeness,
native-event and worktree-symlink guidance was read; no qualifying recurrence
has occurred. Source-only results do not discharge final packaged verification.

## Evidence status

Premises and Figma were refreshed before implementation. The complete three
component files first produced the expected RED result: 58 passed and 2 failed
on the old source (TAP outside the Tempo group and missing visible toggle
readbacks). The New-form visibility/cancel/create assertion already passed.
After the source change, the same complete files passed 60/60 with terminal
exit 0; TypeScript also exited 0. Raw receipts are
`/tmp/lmdj-u06b-components-red.log`,
`/tmp/lmdj-u06b-components-green.log` and `/tmp/lmdj-u06b-tsc.log`.

Portal, scope tests, normal build/package and every browser case remain UNRUN.
Browser-file edits remain held by U12a, and CI #2118 owns the heavy window.
Component success does not establish rendered geometry, hit targets or audio
behavior. This source Task does not alter the frozen U05 candidate or its
receipts; no commit, push or PR has been made for U06b.


## Browser writer release and current-main source preparation

Root confirmed U12a #2142 merged as `dad44c45` and released the Sequence
browser writer. The Task preserved all six original source files (including
the two new files), its full patch and eight prior receipt hashes under
`build/verification/u06b-restore-692d2ac/`. Fresh main is
`8a5142efd9a86f207fade75661ed0f4a225c56e0`, including Pad #2145. The clean
Task branch fast-forwarded to that exact commit and the original SETUP patch
applied without conflicts. Product JSX, its local CSS and component tests are
byte-identical to the earlier reviewed source; only their main context changed.
Live #2112 was read again. Main still has the older horizontal SETUP grouping,
so this presentation Task remains outstanding; U12a Recovery, C1 typed Filter,
U01 adaptive controls, U06a Grid Tools and the new Pad presentation are already
delivered and remain intact. No new capability belongs to this Task.

This source-only admission appends three cases at 1440×900, 1024×768 and
768×600 to the exact current-main Sequence file. Its original ten cases,
helpers, Recovery additions and deadlines remain an unchanged byte prefix;
the complete five-case Metronome file remains unchanged. The new cases measure
all visible SETUP buttons/sliders after scrolling each into view: actual 44px
minimum dimensions, five independent elementFromPoint hits, no target overlap,
full button text bounds and no horizontal scrolling. Separate row/group
coordinates establish the intended vertical flow. Screenshots and geometry
JSON are written for the normal state, New form and final toggle readbacks.

Native keyboard activation proves TAP reaches inspected Project Truth after
an independently specified two-tap interval, the first tap writes nothing,
New/length/Cancel writes nothing, Create authors exactly one four-bar Pattern,
Quantize reaches inspected Truth, and Metronome reaches the existing readonly
IndexedDB preference without changing Truth. Reopen retains the resulting
Project and device preference. The new clock arrangement follows the existing
TAP journey; it changes no product clock, transport or audio implementation.
All existing timing, PCM/capture, owner-loss, restart and recovery journeys
remain required in the eventual complete owning browser invocation.

All verification on this refreshed input is UNRUN: no component tests,
typecheck, syntax check, Portal, build, package or browser execution is admitted
in this source preparation. Earlier 60/60 and typecheck receipts retain their
original input identity. No commit, push or PR action is taken. Root will
review the complete seven-file packet before granting execution.


## Source review correction — visible versus enabled inventory

Independent full seven-file review identified one P2 in the added browser
helper before any browser execution: it filtered disabled buttons but required
at least 19 controls. The official fixture has BPM 120, Swing 50 and a one-bar
Pattern; Decrease Swing is correctly disabled at the lower bound. Therefore
the initial view has 19 visible controls but only 18 enabled controls. No
runtime failure is claimed; the original 40840-byte reviewed packet remains
preserved at `build/verification/u06b-source-8a5142ef/`.

Root admitted only this browser helper and this plan for correction. The
helper now enumerates exact accessible names and availability for each phase:
initial/readbacks have 19 visible controls and 18 enabled; New form hides TAP
and New, then adds four length options and Cancel/Create, yielding 23 visible
and 22 enabled controls. All three phases retain the actual lower-bound Swing
50 fact in inspected Truth and the slider. Decrease Swing must be disabled;
all other declared controls must be enabled in these stopped, settled states.
The exact enabled-name list is checked separately from visible inventory, so
a disappearing control or an unexpected lock cannot pass by reducing a count.

Every visible control, including the disabled decrement, retains actual 44px
bounds, text containment, individual scroll visibility and pairwise nonoverlap
checks. All enabled controls retain all five elementFromPoint hit assertions;
the disabled control is recorded as unavailable for input, with no fictitious
hit pass. All TAP/New/Cancel/Create/Quantize/Metronome/reopen legs and deadlines
are unchanged. The other five declared source files and original ten Sequence
plus five Metronome journeys retain their reviewed bytes. No fixture, product
lock, handler or layout changes are made. All checks remain UNRUN; no syntax
check, tests, heavy work, commit or push is executed in this correction.

## Current-main lowest-tier verification

After Root and the independent reviewer accepted the inventory correction,
Root admitted one complete lowest-tier sequence on main base
`8a5142efd9a86f207fade75661ed0f4a225c56e0`. The seven reviewed file hashes
were checked before each command and remained identical after execution.
The original three component files passed all 60 tests (Vitest 1.78 seconds);
full Creator TypeScript and syntax checks of the complete Sequence and
Metronome browser files exited 0. Exactly the seven declared files were then
staged. The complete change-scope suite passed 77 tests in 8.786 seconds;
staged and unstaged whitespace checks also exited 0. No command failed or
was retried.

The eight sequential commands ran from 2026-10-13 08:42:18.108729 UTC to
08:42:31.390338 UTC and all naturally exited 0. Their exact argv, working
directories, start/end times, exits, raw log hashes and observed process groups
are in `build/verification/u06b-light-8a5142ef/run-receipt.json`.
`before.json` and `after-release.json` in that directory bind the unchanged
seven-file input. The 08:46:04 UTC census found wrapper PID 6969, all eight
owned process groups and every observed child PID absent; the lightweight
window was explicitly released. Only this plan's result section changed after
these checks; the six product, test and Portal inputs remain unchanged.

This supersedes the earlier UNRUN status only for these lowest-tier checks.
The original ten Sequence cases, five Metronome cases, all existing budgets
and the three appended viewport journeys retain their source. Whole Portal,
fresh normal Creator build/package and the complete owning browser invocation
remain UNRUN on this candidate. Actual geometry, 44px targets, native input and
audio/PCM behavior are not established by the component or syntax results.
No commit or push is made while the remaining verification window is pending.

## Admitted final verification — Portal and build checkpoint

Root admitted the sole U06b heavy window after the prior owner’s natural exit
and process release. A fresh main read found `28ff18c5c1f3790157193e900b5c7980cc595026`.
Relative to this Task’s `8a5142ef` base, its B1 type closure, Capture and Trim
changes do not alter SETUP, Sequence, Metronome, global styles, or build inputs.
The ModalDialog addition is opt-in for Capture and does not change the default
Sequence consumer. Shared Portal changes occupy separate Capture/Trim sections.
The current frozen Task therefore retains its reviewed base without a forced
rebase; this is Task evidence for that candidate, not integrated latest-main proof.

All seven frozen file hashes matched before each admitted command. Missing
docs-site and browser-test dependencies were installed from their existing lock
files (`npm@10.9.3 ci` for docs-site, `npm ci` for browser tests); both naturally
exited 0. The three Creator/docs/browser lock files remain byte-identical to
their committed inputs. No packages were updated or shared dependencies changed.
The complete `scripts/docs-site.sh check` ran from 10:36:43.168545 to
10:37:37.948491 UTC on 2026-10-13 and naturally exited 0 in 54.825 seconds,
including all 50 routes. No command was retried; all owned command process
groups were absent afterward. Raw commands, output, source bindings and exits
are retained in `build/verification/u06b-heavy-first/`.

A clean local source checkpoint is now required by the normal Creator packager.
The existing complete 60 component tests, TypeScript, syntax and 77 scope tests
retain their unchanged source inputs and prior passed receipts. Only this plan
records the new Portal result. Normal configure/build/package and all original
10 Sequence plus five Metronome cases and three new viewport cases remain
UNRUN at this checkpoint; no actual geometry, audio or browser success is claimed.
No push, PR or publication occurs at this boundary.

## First complete browser result and bounded collector correction

The clean source checkpoint was `9cec52b638a0867710e265309896b38158d46a86`.
Normal pinned configure, Creator build and package each naturally exited 0,
ending at 10:42:54.839977 UTC on 2026-10-13. The official checked-in project
fixture was decoded locally (767554 bytes, SHA256
`66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`).
The original complete 18-case Chromium invocation used one worker and every
original deadline. It ran from 10:43:14.646671 to 10:46:44.568206 UTC and
naturally exited 1: all ten original Sequence and five Metronome cases passed;
the three added viewport cases failed at the same initial inventory assertion.
The original logs, traces, packaged inputs and seven source hashes remain in
`build/verification/u06b-heavy-first/`. No failed run was retried or overwritten.
The server exited -15 after the completed command; the 10:47:45 UTC census
found all 292 recorded process identities and the browser wrapper absent.
The heavy window was explicitly released to the next owner.

Each failure showed exactly one additional raw-DOM item, Refresh playback,
after the strict Playwright visible inventory (19 total, 18 enabled) had passed.
All three original DOM traces show its existing closed details ancestor. The
new helper had used client-rect existence to collect geometry, whereas the
locked Playwright visible locator also checks native visibility and computed
style. Exact Refresh bounds, computed styles and clipping were not retained
before that assertion, so those measurements remain unverified. This evidence
does not prove a visible product overlap or complete layout correctness. The
three new journeys stopped before their later geometry, keyboard, authoring,
preference and reopen assertions. Their remaining legs are not passed.

Root admitted only this plan and the Sequence browser spec for a bounded
collector correction. Geometry now comes from the same strictly checked
`controls` visible locator through `evaluateAll`; no control is excluded by
its label. Before the inventory assertions, an independent raw-DOM diagnostic
is written and attached with every candidate's rectangles, native
`checkVisibility`, computed visibility/display/opacity/content-visibility,
overflow/clip styles, all ancestor bounds/styles and closed details ancestry.
This records future observations; it does not turn the first run's missing
measurements into evidence.

The exact initial/readback 19-visible/18-enabled and New-form
23-visible/22-enabled inventories remain. Disabled Swing still receives actual
44px and text/containment/nonoverlap checks; every enabled control retains all
five hit points. All other geometry assertions, native TAP/New/Cancel/Create/
Quantize/Metronome/reopen legs, original ten-case byte prefix, complete five
Metronome cases and every timeout remain unchanged. The other five Task files
are byte-identical to the checkpoint; no product handler or layout is changed.

Only browser syntax, the complete 77-test change-scope suite and whitespace
checks are admitted for this correction. They are UNRUN when this paragraph
is written. No commit, Portal, build/package or browser rerun is admitted here.
The corrected complete 18-case result remains pending a separately assigned
heavy window; this Task is not ready to ship.

The admitted correction checks subsequently ran from 10:54:11.589438 to
10:54:21.269306 UTC on 2026-10-13. Sequence browser syntax, all 77 change-scope
tests and whitespace each naturally exited 0. Seven-file hashes matched before
each command; raw logs and process receipts are retained under
`build/verification/u06b-collector-correction/`. Only this plan records those
results afterward. The other five Task files, original Sequence prefix,
complete Metronome file and all three added journey bodies remain unchanged.
The correction is frozen for independent source review; no corrected browser
execution or actual new geometry result is claimed, and no commit was made.

## Corrected complete browser result

After independent review of the two-file collector correction, Root admitted
one complete original Sequence + Metronome invocation. It ran from
11:28:52.067076 to 11:32:32.487618 UTC on 2026-10-13 and naturally exited 0:
**18 passed, 0 failed, 0 skipped**. This includes all ten original Sequence
journeys, all five Metronome journeys, and all three SETUP viewport journeys,
with one worker and the original deadlines, assertions and far-side legs.
No test was filtered or retried.

This run reused the original normally configured, built and packaged
`9cec52b638a0867710e265309896b38158d46a86` product. Before and after the run,
the corrected seven-file manifest, exact two dirty paths (this plan and the
Sequence browser spec), all ten distribution files, three dependency locks,
Playwright configuration, toolchain identity and official fixture matched their
frozen hashes. All 47 original failure artifacts also remained unchanged.
There was no Portal, product rebuild, installation or Native/full-Creator run.
This is evidence for the unchanged original product plus corrected acceptance
collector; it does not claim a new build or an integrated latest-main artifact.

Retained raw JSON now measures all initial/readback 19-visible/18-enabled and
New-form 23-visible/22-enabled inventories at 1440x900, 1024x768 and 768x600.
The minimum actual control height across those phases is 55.27, 46.19 and
44 CSS pixels respectively; the minimum width is 97.98, 81.90 and 78 pixels.
The disabled Swing decrement remains in those measurements. Every enabled
control passed its five hit points after scrolling into view; text containment,
pairwise nonoverlap and no horizontal overflow assertions passed. TAP, native
keys, New/Cancel/Create, Quantize, Metronome and reopened Truth/device-preference
far sides completed. These measurements cover the declared SETUP scope;
shared-header stacking, 16-lane EDIT, picker redesign and physical-device
acceptance remain outside it.

The new pre-assertion raw diagnostics show that Refresh playback has a positive
client rectangle inside the closed details element while native
`checkVisibility()` is false. This is a new observation from the corrected
run, not a retroactive claim about the first run's unrecorded geometry.

Raw logs, before/after input records, all 68 run artifacts and the subsequent
render summary are under `build/verification/u06b-corrected-browser/`.
The full log SHA256 is
`7c92515b7db84480d4163950f6eeca9e2b9fbadaf2fbaa84bb446dc329b8373e`.
The original `15 passed / 3 failed` result, log and traces remain in
`build/verification/u06b-heavy-first/`. The owned server naturally remained
available until the browser command ended, then was terminated and reaped
with exit -15 at 11:32:32.492577 UTC. A fresh census found all 52 observed owned
process identities and the wrapper absent. The heavy window was explicitly
released. Only this plan is updated after the tested source freeze. No commit,
amend, push or PR is performed pending Root's raw-render evidence review.

The precommit shipping refresh fetched committed main
`c4bde2ffa4390eb83e5ccc1e0313f933732bf88a`. Since this Task's `8a5142ef`
base, main added Capture, Trim, Slice, overviews and headered-FX SDK type
closure. The SETUP component, its owning component tests, original Sequence
plus Metronome acceptance files and shared SETUP style inputs have no
intervening changes. This Task's SETUP behavior remains outstanding; unrelated
Portal sections and other UI work must be retained on any future conflict
integration. The reviewed Task keeps its tested base without claiming the
newer main as its artifact. Root has read all nine geometry phases, 870 hit
points and representative screenshots and admitted final atomic shipping.
The browser runner's actual exit 0 is retained; the outer unified-exec session
exit was not retained and is not inferred from it. The original `9cec52b6`
checkpoint has not been pushed by this Task, the remote topic branch is absent,
and no remote-tracking ref contains it. The unpublished checkpoint may be
amended into this single seven-file Task; review and guarded merge belong
to Root, with no cleanup or release authorization.
