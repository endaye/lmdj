# Capture panel Interaction UI

Date: 2026-10-13
Umbrella: [#2112](https://github.com/endaye/lmdj/issues/2112), U12b
Status: corrected normal build/package and the complete Capture browser
selection PASS: nine passed and nine existing project skips. The original
trim-overflow failure and all its artifacts remain retained. Local verification
is complete; current-head review and integration remain separate.

## Premises and dispositions

Initial worktree/source baseline: `692d2ac18397190f71a54ce0297e5e0a54cee5ab`.
Current committed integration base: `35455f7576fc96ad253f2d5a523ba457e1df9321`.
Read the live umbrella and current source, tests and merged Capture successors
before editing. U01 (`73fc1c7b`) already provides common 32-unit faces,
44-unit targets and adaptive console geometry; reuse those controls. U11
(`cf7707d3`) already preserves the System/source and capture mounting boundary;
do not repeat its wiring. The later Facade change at this base does not edit
Capture, ModalDialog or their owning browser journeys.

Still outstanding: Capture uses one generic heading and a centered 44rem
viewport dialog. The new Figma places recording and retained trim in the right
368-unit touch area. Read high-fidelity context and screenshots for
`407:5574` and `407:5985` using `figma-design-to-code`. Their waveforms, timer
and target are dynamic readouts; no new static asset is needed in this panel.
The unchanged rail/Pad/overview assets in the complete frames are out of scope.

Already delivered: all seven Capture phases, real-buffer waveform and meter,
quota-bounded frame selection/crop, failed commit retention, fixed original Pad,
native modal ownership, keyboard/return focus and Continue in Sequence. Keep
those owners and callbacks intact. The Figma omits permission, saving and error
states; that omission does not remove them. Sequence's separate recording bar
needs an App projection and is not part of this Task.

## Declared files and ownership

One Task, these nine paths only:

1. `apps/creator-web/src/components/modal_dialog.tsx`: default-preserving optional
   touch-area placement; no portal, state-owner remount or lifecycle rewrite.
2. `apps/creator-web/src/components/capture_panel.tsx`: phase headings, real
   timer/target, readout and action hierarchy; existing handlers unchanged.
3. `apps/creator-web/src/components/capture_panel.css`: new scoped presentation.
4. `apps/creator-web/test/capture_panel.test.tsx`: preserve all 52 current cases
   and add presentation/state assertions.
5. `apps/creator-web/test/modal_dialog.test.tsx`: new placement/default/native
   ownership/focus tests.
6. `tests/platform/web/creator/creator_web_capture.spec.mjs`: all nine original
   journeys and budgets, plus actual geometry and rotated trim/focus coverage.
7. `apps/docs-site/docs/hosts/creator-web.mdx`: Capture facts only.
8. `apps/docs-site/docs/hosts/creator-interactions.mdx`: Capture facts only.
9. `docs/plans/2026-10-13-creator-capture-interaction-layout.md`.

No App, SampleSurface, global CSS, controller/reducer, S6 worktree, runtime,
Provider or SDK edits. U12a merged separately as `dad44c45`; its Recovery
presentation and mount boundaries are retained.

## Layout and modal boundary

An opt-in `touch-workspace` placement reads the actual mounted touch section's
viewport rectangle and natural dimensions. Resize/scroll/ResizeObserver updates
only the native dialog's presentation. It stays in its existing React parent
and browser top layer. Missing anchor retains the existing centered behavior;
all other ModalDialog consumers keep that default.

Wide and compact layouts align to the touch rectangle and use its scale only
when at least one. The 32/44 control geometry must never be reduced below
44 actual CSS pixels. Clamp to visible viewport margins and use natural inner
vertical scrolling while Stop/Commit remain outside the scrolling details.

Root explicitly accepted upright modal content in the rotated portrait console:
anchor to the rotated touch area's bounding rectangle, but retain horizontal
trim coordinates. Rotating the content would require changing the existing
clientX gesture mapping, which this presentation Task does not own. No portal
or remount is used to position the panel. Full browser proof must exercise trim
and focus/returnFocus in portrait, not just take a geometry screenshot.

The existing all-phase Close action remains in the fixed header, beside the
phase heading and original target. This preserves its direct availability in
permission and committing states absent from Figma; the header reserves its
full 44-unit target. Crop spans the action row; Commit and Discard share the
next row. Input identity and actual stop/error messages remain in the single
scrolling details region. Recording and retained waveforms use the Figma dim
and sky fills while keeping the actual buffer/envelope drawing.

Reference viewports: 1440×900, 1280×720, 1280×600, 1024×768, 768×600 and
768×1024, plus resize out and back while the same capture remains mounted.
The approved console acceptance minimum remains 768×600; smaller devices are
not silently claimed as supported by this Task.

## Verification and resource admission

Lowest tier: original CapturePanel baseline, presentation RED, complete
CapturePanel and new ModalDialog suites, existing mounted workspace
capture/recovery tests, and TypeScript. Keep native ownership, target, trim,
cancel, error, backgrounding and quota assertions intact.

Before shipping: whole Portal, staged scope including new files, fresh normal
Creator build/package and the complete original Capture browser spec in its
granted/denied projects. Preserve all 600s/900s budgets and existing platform
skips. Each original transition retains its far-side assertion:

- Record → exact frame trim → commit → actual artifact digest/bytes →
  reload/reopen and persisted Truth.
- Focus loss/blur → retained take; permission denied → explicit retry.
- Armed capture → Continue in Sequence → playing transport → retained trim;
  refused commit → Discard → Record-off → fresh capture/commit → later Pattern
  events → reopen exact Truth.
- Queried quota beyond the old cap, privacy, and empty-Pad press/release capture
  retain their complete existing legs.

The browser spec does not operate the Crop button. Existing component cases
`Crop to selection mutates the same buffer, rebases PCM, and resets the view`
and `Crop clears a commit error and remains available for another edit` in
`capture_panel.test.tsx` exercise that button, retained-buffer identity/PCM,
selection rebasing and repeat edits. Their coverage belongs to the recorded
component-suite receipts below; this wording correction executes no new check.

Add actual right-area/viewport rectangles, stable outer geometry, no horizontal
overflow or overlapping action hits, center/edge hit tests, state screenshots,
keyboard containment, non-dismissible backdrop, and rotated trim/return focus.
Component style assertions cannot replace this browser acceptance.

Historical low-tier scheduling: Root admitted this nine-file committed-main integration
and the complete 63 component cases, three original mounted Capture cases,
TypeScript, browser syntax and staged scope checks. After the S6 Portal slot
released naturally at 07:46:19 UTC, Root admitted the serial low-tier run below.
At that checkpoint U12b had no Portal, Creator build/browser, Native or Wasm
authorization. The later bounded heavy admission and its scheduling hold/release
are recorded below; they do not authorize a full Creator proof or fixture Native
regeneration.

## Documentation impact

Documentation impact: required — `/hosts/creator-web` and
`/hosts/creator-interactions`, narrow Capture presentation and preserved
semantics only. Physical microphone/device/hearing and candidate acceptance
remain separate from browser proof.

## Version Management

Version impact: none. Presentation changes reuse existing Host/runtime behavior
and do not allocate Product, Module or Contract identities.

## Results

- `/tmp/lmdj-u12b-capture-baseline.log`: all 52 current Capture cases PASS;
  the older read-only decomposition's count of 49 was stale.
- `/tmp/lmdj-u12b-presentation-red.log`: five causal presentation/placement
  failures plus a new test fixture failure (jsdom has no native showModal).
  After supplying the test's native-method doubles and correcting its default
  placement invocation, `presentation-red-confirmed.log` retains precisely
  those five causal failures, with 55 passing cases against old source.
- `/tmp/lmdj-u12b-presentation-green-first.log`: one retained failure from the
  changed input-identity text container; the current markup keeps the original
  exact input name while adding captured duration separately. The first tsc
  log also retains two test typing errors, subsequently corrected.
- `/tmp/lmdj-u12b-final-source-components.log`: complete Capture (55) plus
  ModalDialog (8), 63 PASS, exit 0. All 52 pre-existing Capture cases remain.
  Three elapsed-time assertions now check the new frame-derived millisecond
  readout against the same delivered frames. The imported existing global
  stylesheet emits jsdom's nested-CSS parse warning; this is not visual proof.
- `/tmp/lmdj-u12b-mounted-capture.log`: three explicitly selected existing
  workspace cases PASS (empty Pad Capture, audio recovery retaining the same
  panel, and new-Project capture failure/history). The other 188 workspace
  cases were not selected; this is not a whole workspace-suite PASS.
- `/tmp/lmdj-u12b-final-source-tsc.log`: TypeScript PASS, exit 0. Browser source
  syntax and diff whitespace checks PASS.
- All nine original Capture browser cases and their budgets are retained.
  Six viewport idle/recording geometry checks, actual center/edge button hits,
  saved screenshots/JSON and the original full trim/commit journey in rotated
  portrait with focus/return-focus assertions are prepared, not executed.
- Independent source review caught `recordAtLeast` still matching the old
  decimal-seconds display after the timer changed to `MM:SS.mmm`. Its seven
  calls now poll the existing waveform's delivered `data-frame-count` against
  the requested duration at the fixture's 48 kHz rate, preserving the 60-second
  deadline and all nine journeys. No wall-clock sleep was added.
  `/tmp/lmdj-u12b-buffered-wait-components.log`: the two existing mono/stereo
  frame-count provenance cases PASS; 53 other cases were unselected. Browser
  syntax and whitespace checks PASS. This correction has not run in a browser.
  The original source receipt is retained; the new checkpoint is
  `/tmp/lmdj-u12b-buffered-wait-source-receipt.json`. The nine declared paths
  have no upstream delta from this Task base to main `edb05dbb14c0f6ed28abeeeceab742fc3e282080`.

At the original source checkpoint, whole Portal, staged scope, fresh normal
build/package, complete browser journeys/state geometry and physical/candidate
acceptance were UNRUN. The integration results below supersede only staged
scope and the repeated low-tier checks; no commit or push.

## Committed-main integration checkpoint

Root admitted source integration after preserving all nine frozen files,
including the untracked CSS/test/plan, in
`/tmp/lmdj-u12b-preserved-before-35455f75/` and retained stash
`7f43c1710595703dba4c710c02301e20f07c8817`. The old complete packet and causal
receipts remain unchanged. The branch fast-forwarded from the original base
to committed main `35455f7576fc96ad253f2d5a523ba457e1df9321`; no other owner's
uncommitted work was imported.

Premises refreshed at this base:

- Still outstanding: the Capture presentation and all actual browser geometry/
  full-journey acceptance described above. The same seven phases, frame source,
  fixed target, controller and handler boundaries remain authoritative.
- Already delivered: U05 Playback (`14fcb4`), U12a Recovery (`dad44c45`) and C1
  independent Perform Filter (`0909a301`) are retained. The only source merge
  conflict was adjacent Playback/Capture prose in `creator-web.mdx`; both whole
  paragraphs remain, in that order. Both Host pages retain all current Recovery
  and C1 sections. This Task adds only its Capture paragraphs against main.
- C1 changes PerformSurface/FxSliderBank/perform_state and Perform-scoped CSS.
  Its controller adds a live-status read on connect and headered Performance
  recording/control-tail handling. It is not a change to CapturePanel's own
  microphone controller or frame buffer. App, SampleSurface, Capture/Modal, the
  mounted workspace suite and the full Capture browser input are unchanged
  between `dad44c45` and this base. Capture transport exclusion remains an
  explicit leg of the original full browser journey; source inspection alone
  does not establish its integrated runtime outcome.
- The later `35455f75` release-tooling change edits no Creator input. SDK
  observed-recording cursor and owned master-capture-handle changes since the
  original baseline concern Performance's master recording. They do not alter
  this panel's microphone producer or commit callback.
- U12a relocates the same Recovery prompt before normal page content without
  changing Sample/System mounting or Capture callbacks. Native Modal sibling
  ownership covers that location. The three owning mounted Capture case bodies
  remain intact; their old receipts are historical until rerun on this base.

The six product/test/browser candidate files are byte-identical to the accepted
buffered-wait checkpoint. Only main integration of the two Portal pages and
this plan differ. All nine original browser names, budgets and skip directives
remain intact. The admitted integrated low-tier checks completed as recorded
below; Portal, normal build/package and all browser journeys remain UNRUN.

## Integrated low-tier results

Bound to base `35455f7576fc96ad253f2d5a523ba457e1df9321` and the preserved
six product/test/browser SHA-256 values. Raw logs and per-command receipts are
in `/tmp/lmdj-u12b-light-35455f75/`; each receipt records the command, UTC
start/end, actual exit, log hash and empty remaining owned process group.
No command was retried. Only this plan's result record changed afterwards.

- `components.log`: full CapturePanel plus ModalDialog, 63 PASS, exit 0
  (07:48:48–07:48:51 UTC). All 52 pre-existing Capture cases remain covered.
- `mounted.log`: the three original complete mounted Capture cases PASS,
  exit 0 (07:49:04–07:49:07). The remaining 189 cases were unselected; this
  is not a whole workspace-suite PASS. The existing nested-CSS parse warning
  and Node localStorage warning remain visible in the raw logs.
- `typescript.log`: `tsc --noEmit`, exit 0 (07:49:15–07:49:16).
- `browser-syntax.log`: existing Capture browser source, `node --check`,
  exit 0 (07:49:21); this executes no browser journey.
- `scope.log`: complete change-scope suite, 77 PASS, exit 0
  (07:49:44–07:49:53), after staging exactly the nine declared paths.

Whole Portal, fresh normal Creator build/package, the complete nine browser
journeys in their granted/denied projects, six-viewport geometry and actual
rotated trim/focus remain UNRUN. They require Root's separate resource window.
The candidate is staged for source review only; no commit/push is authorized
at this checkpoint.

## Portal receipts and bounded heavy continuation

The preceding complete nine-file packet is preserved unchanged at
`build/verification/u12b/final-original/preceding-source-nine-manifest.json`
and `preceding-source-nine.patch` (SHA-256
`8cda726f9190d67157fe93c84803bc6401a57b4eca8efeddc211739cbd5a9061`).
Only this plan's results changed before the clean source checkpoint; the eight
product/test/browser/Portal files retain their frozen SHA-256 values.

- Original whole `bash scripts/docs-site.sh check`: **exit 1**,
  08:02:56–08:03:06 UTC, 81 passing tests and eight module-loading failures.
  This worktree lacked docs-site dependencies; it also lacked the browser
  dependencies. This was a preflight omission, not a product failure. Source
  and lockfiles were unchanged; all owned process groups were absent at the
  08:04:23 release. Original log/receipt remain in
  `build/verification/u12b/initial/`; log SHA-256
  `baa51ef022b466671a9397fe6f81a4788df8c75d5aaf9d58a4f4700fbf75126c`.
- Root granted one finite dependency remedy: existing locked
  `bash scripts/docs-site.sh install` (08:06:27–08:06:33, exit 0) and
  `npm ci` in `tests/platform/web` (08:06:46–08:06:47, exit 0).
  Both lockfile hashes and all nine source hashes were unchanged. Exact logs,
  commands, dependency readiness and exits are in
  `build/verification/u12b/remedy/`.
- The one admitted repeat of the **whole original Portal check** passed:
  08:07:13–08:08:16 UTC, exit 0, **179 tests, 52 documentation pages,
  10 diagram sources / 20 outputs and 50 routes**. Raw log SHA-256
  `36a7cbad57571fd925d904dda16f7f3de5e8926882d9cdc638842956958282d5`.
  `remedy/portal-receipt.json` binds the original command and source base.
  No page/product change occurred after this check.
- Root required a scheduling hold after that natural Portal terminal because
  independent C2 full Creator proof was running. No checkpoint, build/package
  or browser began during the hold. `remedy/portal-release-and-hold.json`
  records all three owned groups absent at 08:08:57 UTC.
- Independent C2's original proof later ended naturally at 08:24:59 UTC and
  its owner explicitly released the window at 08:26:45. Root read its receipts
  and granted U12b the sole next heavy window: one clean source checkpoint,
  normal Creator build/package, then the complete original nine Capture cases
  in the granted/denied projects, with all original budgets/workers/legs and the
  prepared six-viewport/portrait trim/focus evidence. Failure stops dependent
  work and retains the original evidence; no automatic retry is admitted.

Immediately before this checkpoint, `git fetch origin main` resolved
`8a5142efd9a86f207fade75661ed0f4a225c56e0`. Compared with the retained
`35455f75` base, intervening release identity/snapshot changes and Pad #2145
do not change CapturePanel, ModalDialog, App, SampleSurface, Capture runtime,
the complete Capture browser source or Playwright configuration. Pad CSS edits
are limited to the five palette values, Pad presentation and picker selector;
there is no Capture selector or modal geometry change. Both newer Portal edits
are in the separate Pad sections. Their later merge union must preserve them;
this unrelated movement does not require rebasing this verified source packet.

Disk preflight measured 3,120,898,048 free bytes; this worktree had no prior
Creator build output. Three retained comparable normal Creator output trees
each occupy about 77 MiB. Dependencies are present; the fixed official sample
fixture is under 1 MiB. No cleanup or deletion is authorized or performed.
Build/browser outputs will be measured again at their natural terminals.

Normal Creator build/package and both complete Capture browser projects are
still **UNRUN** at this source checkpoint. It is a local verification identity,
not a shipping/completion claim. Push/PR and final acceptance remain separate.

## Original browser failure and bounded source correction

The local clean source checkpoint is
`c43c382a1b17fc030d8f29fda1cc99d370c545fd`. It contains exactly the nine
declared paths. Its normal `bash scripts/creator-web.sh build` completed
08:41:05–08:41:59 UTC, exit 0; normal `package` completed
08:43:45–08:43:46, exit 0. No Native fixture was regenerated. The existing
official all-Pad and Sample fixture bytes were hash-checked, copied into this
worktree and independently verified with `project_bundle.py verify`, exit 0.
Their original native-generator provenance remains attached; no other worktree's
Creator product artifact was borrowed.

The original complete Capture spec ran in both granted/denied projects in one
selection, with the original workers=1, all nine journeys, original deadlines
and no grep/retry override. It ended naturally at 08:45:15 UTC with **8 PASS,
1 FAIL, 9 existing project skips**, exit 1. The only failure was the new actual
portrait trim geometry assertion: `contentOverflow` was **14**, exceeding the
unchanged allowance of 1. The six-viewports idle/recording case passed, and the
remaining original Capture journeys completed. The failing portrait case did
**not** reach its subsequent pointer trim, inert-middle, Commit, saved Sample
waveform, exact frame count/artifact byte length and revision assertions; those
legs remain unverified on this candidate, rather than inferred from other cases.
This case has no Crop-button or reload/reopen leg. Reload/reopen is covered by
other original Capture cases; Crop-button behavior is not exercised by this
browser spec.

The original source, built/package input hashes, raw logs, trace, JSON and PNG
remain at `build/verification/u12b/final-original/` and the separate Playwright
slot `test-results/u12b-final-original-capture`. Browser log SHA-256 is
`2a9d8f3e1fde09c58b4002e0052637b5f8b2393f766ec55ec659940fd856c7c5`.
`failure-release-and-retention.json` records all **55** result-file hashes and
all **221** observed owned process IDs absent at 08:46:22 UTC. The server
terminated only after the browser's natural exit, actual exit −15. The source
was unchanged, the worktree clean, and the heavy window was explicitly released.

Read-only diagnosis used that original trace, without another browser run.
`portrait-trim-source-trace-diagnosis.json` records the captured End input at
value/max 86400, with `left: calc(100% - 22px)`. The delivered stylesheet in the
same trace (SHA-256
`39df0d426091a49e6f954800c4671ff54142e0ab172edc257cb31204d0e2adee`)
sets that native range to 44px wide, while this Task's trimming view reserved
only 8px on each side. The right extension is 22 − 8 = **14px**, matching the
measured overflow. Opacity zero does not remove the native input's overflow;
focus reveals it, so clipping would hide part of the keyboard control.

Root admitted a correction to exactly three of the existing nine paths:

- `capture_panel.css`: reserve `var(--creator-control-hit) / 2` on both sides
  in trimming and commit-error, preserving the native input's complete size.
  No JSX, callbacks, trim partition, pointer behavior or cancel logic changes.
  The fix does not add clipping or reduce a target.
- `creator_web_capture.spec.mjs`: keep the original failed assertion, all nine
  cases, every deadline and every original leg. Add the six-viewports trim
  geometry and focused Start/End bounds/opacity/overflow evidence while the
  full recorded range remains selected, then restore portrait and the previous
  focus context before this case's original pointer trim, inert-middle, Commit,
  saved-waveform, exact frame/byte length and revision legs.
- This plan: retain the actual failure and scope its correction honestly.

The other six declared files are byte-identical to the original checkpoint.
At the correction's initial source-only snapshot, no syntax/component/type/
scope check, amendment, Portal, rebuild/package or browser repeat had run.
The independent B1 owner holds the current heavy window. Root/capability source
review and a separate finite verification admission precede any such commands.

Separate existing geometry debt: Capture pointer `gripZoneStyle` uses ±12px
partitioned zones, yielding 12px at an endpoint and up to 24px inside (and less
when selection boundaries approach). These are not the native 44px keyboard
range inputs or the four action buttons measured in this run. The original
button hits and this native-focus correction therefore **do not establish 44px
pointer grip targets**. This input-interaction debt remains explicitly open;
it is not silently fixed, waived or included in the presentation correction.

## Correction source review and admitted light checks

Independent review found no CSS/browser logic defect. Its P3 evidence wording
was corrected: this failed case does not include Crop or reload; other original
Capture cases cover reopen, while the complete browser spec does not exercise
the Crop button. Neither the original failure receipt nor its log was rewritten.
The reviewer read the v3 nine-file packet, confirmed the unchanged six files
and retained journeys/budgets, and reported no remaining findings. That source
review is not rendered acceptance.

Root admitted one serial light check sequence while B1 retained the heavy
window. `overflow-source-correction/light/` preserves raw command/exits, hashes
and descendant census. Browser `node --check` passed at 09:00:32 UTC, exit 0.
The existing change-scope suite passed **77 tests**, 09:00:52–09:01:02 UTC,
exit 0, with no remaining observed child. Staging explicitly named all nine
declared paths: the complete index against base `35455f75` contains nine paths,
while the correction against existing checkpoint `c43c382a` contains only its
three changed paths. No reset, rebase or amendment was used to change that
distinction. Final whitespace is checked after staging this results record.

No component/TypeScript repeat was claimed or required for this CSS/browser
correction. The prior 63-component, three-mounted-case and TypeScript receipts
remain bound to their original inputs. Both Portal pages retain their original
hashes and documented behavior; Root explicitly allowed retaining the original
whole **179 tests / 50 routes** Portal receipt, rather than claiming a new run.
At that source-review checkpoint, no amendment, rebuild/package, browser retry
or push had occurred. The separately admitted corrected run follows below.

## Corrected complete browser verification

After B1's explicit natural release at 09:29:43 UTC, Root transferred the sole
heavy window and admitted one corrected run. The nine-file clean verification
checkpoint is `8225079d8a47aece34f459004ab6f037e76ccec0`. Current-main premise
readback remained `8a5142efd9a86f207fade75661ed0f4a225c56e0`: only the independent
Pad/palette Portal paragraphs overlap; Capture producers, consumers and tests
have no intervening change. The final integration must preserve those paragraphs.

`build/verification/u12b/corrected-final/` contains the preceding source packet,
clean-checkpoint receipt, fixture identities, raw command logs, start/end and
exit receipts, delivered artifact hashes, and final release census. Both retained
official fixtures were independently verified again with unchanged file hashes;
no Native fixture regeneration was performed. Normal `creator-web.sh build`
passed at 09:37:58–09:38:01 UTC, followed by normal `package` at 09:38:25–26 UTC.

The original complete Capture spec ran once in both granted and denied projects,
using the unchanged one worker, nine journeys and original deadlines. It exited
naturally at 09:39:46 UTC with **nine passed, nine existing project skips, zero
failures**. Its raw log SHA-256 is
`7588572c9a65b5563a0901523fc4bc0a86afc2bf5454259eb650b93ec3be99e6`.
This includes the original pointer trim, inert middle, Commit, Sample waveform,
exact frame/artifact byte-length/revision assertions, plus the other original
retained-capture, permission, transport, quota, privacy and reopen journeys.

The six viewports passed idle, recording and retained-trim geometry. All measured
action rectangles have at least 44 actual CSS pixels in both dimensions, with
center/four-edge ownership and no overlap. Each viewport also passed focused
Start and End native-range checks: opacity one, unchanged values, complete
rectangles inside the content area, and at least 44 by 44 actual CSS pixels.
The corrected portrait content overflow is zero, as it is across all six trim
viewports. The owner inspected the portrait trim, compact End-focus and portrait
Start-focus screenshots. These native keyboard-range measurements do not close
the separate pointer grip-zone size debt documented above.

The source nine and all delivered files stayed unchanged during the run. The
125 new result files, including 31 geometry JSON files, are hashed in
`success-release-and-retention.json`; all 55 original failure artifacts were
hash-checked unchanged. The server stopped only after browser completion.
All 58 observed owned process IDs were absent at 09:40:22 UTC, when the heavy
window was explicitly released. No second heavy run or new Portal pass is
claimed. The plan-only amendment `bb5177e2` recorded these actual results;
its executable, test and Portal inputs remained identical to the verified checkpoint.

## Published-head review: recorded-time announcement

Review of published `bb5177e2af3a034dd9d099a9358403467a368294` identified one P3:
the new recorded-time `<output>` has an implicit status role with polite/atomic
live-region semantics, while its frame-derived display can update at the
nominal ten frame-batch notifications per second. Actual assistive-technology
speech was not measured. The independent source review confirmed the semantic
cause; it did not claim an observed screen-reader failure.

Root admitted an explicit `aria-live="off"` on that existing output, preserving
its element, accessible label, frame-derived text and update behavior. Only
`capture_panel.tsx` and this plan change. The published commit stays immutable;
this review correction is a new atomic commit, not an amendment or force push.
No implementation-mirroring test or artificial RED was added. The admitted
checks are the existing complete Capture/Modal suites, locked TypeScript and
whitespace. The complete two suites passed all **63 tests** at 10:00:21–25 UTC,
exit 0. The pre-existing jsdom stylesheet warning also appears in the retained
07:48 component log; no CSS changed here. Locked `tsc --noEmit` passed at
10:00:35–36 UTC, exit 0. Both commands ended with no remaining observed child.
Raw receipts are retained under `build/verification/u12b/aria-live-review-fix/`.
The exact two files are staged and whitespace-checked before the new commit.

The real browser evidence remains bound to `8225079d`: full nine passes/nine
existing project skips, 125 retained artifacts and six-viewport geometry. The
current source adds this explicit aria-only delta plus plan records; it no
longer claims that all eight non-plan files equal that browser checkpoint.
Both Portal pages retain the original whole179/50 evidence. No new browser,
Portal or physical assistive-technology acceptance is claimed for this change.
