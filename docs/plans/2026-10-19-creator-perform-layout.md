# Creator Perform presentation — #2227 / U07

## Premises and ownership

Refreshed integration base: `1e9e5fbea57f2250b6fda7c39634d1a4d542438b`.
Task parent: Draft #2384, `8d85f862e08ee1f7306ecb27146dde35af490059`.
The live #2227 body/comments and open successor PRs were read before editing.
The old memory note predating dedicated #2227 is not current admission policy.
One writer owns this isolated `feat/creator-perform-layout` worktree.

| Premise | Disposition and evidence at the parent |
| --- | --- |
| Filter and Mute/Solo need implementation | Already delivered by C1 #2139 and C2 #2177: `perform_state.ts` owns producer receipts, typed Filter, mask priorities, gesture identity and durable recording. Reuse; no producer/controller/contract change. |
| MASTER and meter need implementation | Already delivered by M1 #2156 and stacked #2383/#2384. Reuse the same monitor preference/ENC4 and real SDK stereo meter; no fake data, polling or second monitor. |
| Four-slot presentation and horizontal faders | Still outstanding: `pattern_launch_strip.tsx` owns all 16 identities in four groups, but late CSS renders two columns; `fx_slider_bank.tsx` uses vertical ranges. |
| PRIMARY/FILTER/MORE navigation | Still outstanding: main faders remain mounted beside expanded drawers; App registers only Perform pad arrows. Add exclusive groups and bounded physical left/right navigation; preserve SHIFT/System priority and pad arrows. |
| Removed-touch lifetime | Still outstanding: existing cleanup only closes non-main FX or Filter drawers. Exclusive groups must close all removed UI touch tokens, including same Cutoff replacing a main input; controller rotary ownership/HOLD must survive. |
| Independent Filter/Mute view | Still outstanding presentation only: use real phase/provenance and all-64 masks; no bypass switch or new command disabling policy. |
| Narrow overview header | Still outstanding: #2384 retained mode/transport crowding at 390 px. Fit existing facts in the same header height, preserving count-in/meter/footer/encoder facts. |

Fresh Figma design context/screenshots: file `GPFarNiZNsjLQzfG9kR8DO`,
08 `404:1742`, 09 `404:2017`, 36 `410:4498`, 37 `410:4749`.
Reuse existing fonts/tokens/native touch controls. The 24/32 px prototype faces
do not override actual 44 px interactive hit regions. Keep the single outer
touch scroller, main three faders and HOLD on its first screen. Put the FX
section before launch cards to retain that original gate with horizontal rails
and 44 px controls. MASTER remains one common horizontal row; all four launch
groups/16 slot identities, recording and recovery stay reachable in the same
outer scroller. No new fixed footer or nested scroll viewport.

## Declared files — one Task / one Conventional Commit

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/main.tsx`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/fx_slider_bank.tsx`
- `apps/creator-web/src/components/pattern_launch_strip.tsx`
- `apps/creator-web/src/components/perform_surface.css` (new)
- `apps/creator-web/src/components/overview_display.css`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/creator-web/test/monitor_output_controls.test.tsx`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_touch_fit.spec.mjs`
- `tests/platform/web/creator/creator_web_output_meter.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `apps/docs-site/docs/platform/input.mdx`
- `docs/plans/2026-10-19-creator-perform-layout.md`

Expand this declaration before editing any additional path. No CI, Native,
SDK, persistence, manifests or version allocation is part of this Task.

## Verification and defect ownership

Baseline: five existing owning component files (Perform, workspace, monitor,
Perform overview and overview display), **432 passed**, exit 0.

1. Component tests: exclusive groups, truthful pending/unavailable states,
   sole MASTER/HOLD, physical navigation bounds/SHIFT/System, removed-touch
   release and late old-element isolation; preserve rotary takeover/HOLD,
   original More-collapse, all-64 mask, recording and replay assertions.
   Keep producer calls/receipts as the far-side assertions of UI transitions.
2. Run the complete Creator component selection and type checks. A targeted
   restored-source mutation must demonstrate the removed-touch lifetime test
   catches its named defect; never report a stale artifact as mutation proof.
3. Official clean-source Native CLI and pinned Emscripten/Node Creator build
   and package. An unpublished source checkpoint is not Task completion;
   browser findings must be fixed, reverified and folded into the same Task.
4. Run original complete `creator_web_perform.spec.mjs`, not a green prefix:
   stopped/queued/withdrawn/applied launch; device SNAP reload; complete
   gestures/WAV/save/replay/empty-pad master capture; rotary takeover/leave;
   discard/owner-loss recovery apply and discard; every capture failure;
   retryable WAV bind/temp removal; empty-slot ACK/interruption; import crash;
   one capture owner after process loss; replay neutralization; pan/tone PCM;
   native drag-off; typed Filter→PCM/HOLD/page exit/save/replay; all-64 live
   masks→record/leave/reopened replay. Preserve all existing budgets, crash
   legs, identities, byte lengths/digests and far-side assertions.
5. Complete original touch-fit and meter browser selections. Only change the
   approved fader orientation oracle; retain original first-screen faders,
   HOLD, no-overlap, outer-scroll, four-group and all-subpage legs. Add six
   viewport checks at 1440×900, 1280×720, 1024×768, 820×1180, 768×1024 and
   390×844 for group/slot/range geometry, ordinary controls >=44 CSS px,
   visible text, overview/header/meter and actual FX/mask readback. Persist
   successful JSON and screenshots to output paths and read them back.
6. `scripts/docs-site.sh check`, source dependency verification, pitfall disposition,
   new-file ownership/admission tests (staged and committed), and both final
   PR body/declaration checks. Native/Wasm, Portal and audio/browser heavy
   windows run serially. Lane ownership is not a claim of full execution.

Before commit refresh main and inspect relevant intervening source/history.
Inspect staged and committed exact files, diff check and final worktree status.
Current-head independent review remains PENDING on the frozen Draft stack.

## Version Management

Creator Host additive presentation/navigation records MINOR version debt in
#2237. No ABI, Contract, Core/Provider, persistence or Product allocation;
do not guess a version or create a release snapshot in this Task.

## Documentation Impact

Documentation impact: required — `/hosts/creator-web/`,
`/hosts/creator-interactions/`, `/platform/input/`. Update current behavior in
the same Task. Existing diagrams retain their Module boundaries and flows;
this UI composition changes no architecture edges and needs no new diagram.

## Delivery boundary

Main remains frozen until explicit owner unfreeze. Push one Draft successor
of #2384 in the existing linear stack after Task verification. No merge,
auto-merge, release, deployment, Channel operation or resource cleanup.
Task checks, independent review, integration, combined release candidate,
physical device/hearing and final #2112 acceptance remain separate facts.

## Results

Source implementation is complete in17 declared files, in one unpublished
Conventional Commit on the frozen Draft stack. No CI, Native/SDK, Contract,
manifest, Product allocation, deployment or merge operation is included.

- Complete Creator components:82 files/1891 PASS (latest88.40s); TypeScript,
  native CLI and pinned Creator configure/build/package PASS.
- Complete first packaged Chromium selection:29 PASS/0 FAIL/0 skipped,6.1m,
  exact checkpoint `e9a240e421a7237f96de35543ae41b2238e5fff6`; all original
  Perform/meter/touch-fit journeys and native PCM/crash/recovery legs retained.
- Six viewport/three group observations prove real44px touch/physical/Pad
  targets, horizontal local rails, complete encoder text, four contained
  nonoverlapping regions and actual Filter/masks.390px native REC/cancel
  read `COUNT-IN · 8 beats left`; mode refit heights786→552→786 were measured
  without resizing. Seven PNGs and full JSON were written and read back.
- Both group-cleanup and stale-pointer mutants produced their owning semantic
  RED1, then fresh-byte/fresh-process restored GREEN0. Historical failures and
  scope refinements below remain separate evidence.
- Portal179 tests/50 routes and internal links passed. Final publication
  repeats the applicable Portal/ownership/body checks on final inputs.
- Locked Playwright WebKit's canonical general capability-refusal boundary
  passed1/1. Its UI is unsupported in this environment; the attempted UI
  selection failed5/interrupted1/unrun3, exit130. No compatibility overrides,
  new skips, weaker assertions or wider budgets were added. WebKit UI/PCM and
  physical Safari/iPad/MIDI/hearing are unverified.

The new shared layout case adds one Chromium case. Before push/PR, require
complete30-case Chromium selection and canonical WebKit boundary on the final
clean commit, plus final type, Portal, committed ownership/admission and PR
body/declaration checks. The Draft PR and canonical Issues record those actual
postcommit receipts once complete. No pending result is counted as passed in
this source checkpoint. Independent review, integration, complete combined
candidate and device acceptance remain pending; #2112/#2227 stay OPEN.

<details>
<summary>Historical probes, negative evidence and scope refinements</summary>

Implementation verification in progress. Fresh main moved to
`a0d3a6dc914e6e1c6d54f89e4b0cd01c5941e140`: #2385 allocates Build
2.0.119.0 and #2386 retains its snapshot squash witness. The actual path diff
contains immutable Portal snapshot/metadata, Assembly/Product identities and
Cardputer allocation; none changes Perform source, controller, input or its
owning tests. No premise was delivered by these commits. Retain the exact
#2384 stack parent and the owner freeze; external release movement does not
unfreeze this Task.

Baseline 432 passed. First changed component selection: 431 pass / 1 fail
(old expanded-drawer test looked for the main Filter while FILTER was open).
Second: 435 pass / 2 fail (new rotary oracle expected a redundant move instead
of the existing engage-at-value; new App fixture omitted Performance/capture
capabilities). All seven new focused facts subsequently passed. First complete
Creator selection: 1890 pass / 1 fail; its old DOM order assertion still named
Pattern-before-FX, corrected to the declared first-screen FX-before-Pattern
order without removing any surface/identity assertions. Preserve these outcomes.
Final source checks: complete Creator **82 files / 1891 PASS**, exit 0,
91.26 s; TypeScript PASS; staged new-file ownership/admission **76 PASS**;
offline Core dependency verification PASS. Complete Portal check PASS,
including 179 tests, production build and 50 routes/internal links. (The
attempted nonexistent standalone ledger-test path is not a verification pass;
the repository contract requires a disposition, not that invented runner.)
No new process pitfall: the group/pointer defects are covered by product tests;
existing success-artifact, journey-completeness and fresh-restore guidance is
followed. No ledger file changes.

Mutation 1 removed group cleanup: genuine missing `fx_release` RED exit 1;
fresh-mtime byte-identical restore and fresh Vitest GREEN exit 0.
Mutation 2 removed pointer identity: genuine late event released `new-token`
RED exit 1; fresh-mtime byte-identical restore and fresh Vitest GREEN exit 0.
The first mutation used the earlier display-only source bytes; the second and
complete Creator run include the later truthful unknown-value presentation.
The first pointer-mutant harness also rejected its own overly specific output
phrase after observing the real RED; the corrected harness reran the genuine
RED/restored GREEN and records both actual subprocess exits.

Native CLI and pinned Emscripten/Node Creator configure/build PASS. A final
narrow-header CSS grid retains all COUNT-IN facts within the same two lines;
its real native active/cancel geometry is part of the browser check below.
Packaged browser verification is pending at the unpublished source checkpoint;
this checkpoint is not Task completion or independent review.


### Portrait proof correction and scope refinement before editing

First packaged six-viewport probe exited 1 at 820×1180: the existing whole
console rotates −90 degrees, so a horizontal native input's viewport rectangle
is vertical (44×85.328 px). This is not evidence that its local rail is vertical.
Keep the actual viewport 44px hit checks unchanged; assert horizontal writing
mode and local width > height, and compare four slot positions in the console's
local coordinates. Retain both local and screen measurements in JSON.

Declare `apps/creator-web/src/main.tsx` as the seventeenth exact path before
editing: expose the existing measured stage scale as a CSS custom property,
without changing fit/rotation policy. Only Perform touch controls consume its
inverse so their targets stay >=44 actual pixels after portrait downscaling.
Use upward pixel rounding to avoid fractional-pixel undershoot. This does not
clear the separately owned #1221 full-console/physical-control acceptance debt.
Original first-screen/outer-scroll journeys and all six screen rectangles stay
strict. The new raw-screen orientation failure is retained as a failed probe,
not relabeled PASS.

Portrait refinement: owning Perform + hardware-console component selection **200 PASS**, exit 0; TypeScript PASS. Packaged rerun pending.

Second packaged probe exited 1 on narrow header text: actual context scroll width109 vs104 available CSS px. Reduced only the transport column 132→124px to preserve the 10px context text, with unchanged clipping/overlap assertions; native COUNT-IN still must fit both rows.


Third packaged probe: six-view touch target/local rail/slot/text/header checks,
real Filter engage/release and masks/readback/Truth checks completed, then the
new active-count-in setup timed out (240000ms) clicking physical Sequence at
390×844. Its retained trace shows the Touch Live button intercepting the rail.
This is a real whole-console reachability FAIL, not a missing fixture or budget
problem. #1221 remains OPEN and owns fitting/reachability of all workspaces;
U07 does not clear that final acceptance bucket. Do not force-click through it
or label the failed probe PASS. The separate count-in *display* proof now arms
and cancels in a fitting 1440×900 console and measures the real active readout
at390×844 between those transitions; it proves the header only. Task layout
facts and the outstanding 390px whole-console defect are reported separately.


### Resolve Perform's narrow overlap in the declared CSS scope

The fourth display-only probe passed10.4s but does not discharge the third
probe's rail reachability failure. Keep that restriction explicit and repair
Perform itself before Draft publication: in compact portrait <=480px place
its 250px Pad grid above a 344px touch viewport, both to the right of the
physical rail. Console height778px plus existing margins fits390×844 without
shrinking targets. Other modes and full/landscape fit policy are unchanged;
#1221 still owns their combined/final acceptance. Reuse the existing single
outer touch scroller and all controls. Primary card padding/type fit the new
width; no text clipping or hit-floor relaxations. Add actual physical-key44px,
four-region no-overlap/containment and real390px mode-exit/REC/cancel legs to
the six-view journey. All edits stay in the17 declared files.

The declared `main.tsx` also refits when narrow Perform appears/disappears:
its existing MutationObserver only compared workspace identity, which would
retain the old inline height/translation after a mode/System transition.
Track just this layout-affecting boolean; text/telemetry mutations remain
no-ops. Verify System→Back to music refits without a resize and real390px
Sequence exit/Record/cancel. No global compact-rotation policy changes.

Source refinement: App keeps Perform mounted inside `hidden={systemOpen}`.
System therefore preserves the narrow composition; it does not change the
new refit marker. The actual dynamic boundary is mode exit/reentry. Verify
workspace local height decreases on390px Sequence exit and increases on
native keyboard Perform reentry, with no resize between them; then verify
System/Back preserves reachability and real390px REC/cancel. Sequence's
existing phone pointer-rail overlap is explicit #1221 debt; no force-click
or source-side DOM command substitutes for a user input.


Fifth packaged probe passed10.6s: all six views, actual physical/Pad/touch
44px targets, four nonoverlapping contained regions, dynamic mode refit,
System return, native Filter/masks/Truth and real390px COUNT-IN arm/cancel.
Read the390px PNG: PRIMARY wrapped and the old four-across encoder labels
ellipsized. Keep the24px encoder row height but use two12px rows of two
complete label/value cells, explicitly test child text widths, and keep
PRIMARY on one line. Phone Pad captions/mask badges fit their actual tiles.
The original native drag-off journey now sweeps along the approved horizontal
axis; capture, drag-off, release, all page/recording and Save assertions remain.
These final presentational refinements require a fresh packaged rerun.

The original outer-scroll journey explicitly returns from exclusive MORE to PRIMARY before measuring Filter; all initial MORE, four groups/16 slots, four subpages and Sound Sets legs remain. No original journey is deselected.

Final phone source Creator suite:82 files/1891 PASS; full Portal179 tests/50 routes PASS. Subsequent caption/readback-row CSS and browser text/native-count-in assertions are verified by the next official package; final exact-head proof and Portal readback follow before push.


Complete first Chromium package on `e9a240e421a7237f96de35543ae41b2238e5fff6`:
**29 PASS / 0 FAIL / 0 skipped**, actual subprocess exit0,6.1m. This includes
both unchanged meter journeys, the entire original Perform file (all fault,
crash/recovery, PCM, save/reopen/replay and takeover legs), every original
touch-fit case and the strengthened native six-view/COUNT-IN geometry case.

Register one additional cross-engine layout case in the already declared
`creator_web_touch_fit.spec.mjs`: real boot/Perform projection, all three groups
at all six views; actual touch/physical/Pad targets>=44, local horizontal rails,
complete encoder labels/values, contained nonoverlapping console regions.
No audio/processorerror equivalence is inferred for WebKit. Run all nine owning
touch-fit cases in locked WebKit and the final complete30-case Chromium
selection; retain success JSON by path. Full current-head independent review,
combined candidate, physical Safari/iPad/MIDI/hearing and integration remain
separate. No CI or manifest modifications.


### WebKit premise disposition and final publication gates

The attempted nine-case WebKit UI selection was not the repository's owning
selection: five failed in unchanged `waitForBootProject` at `unsupported`,
one was interrupted and three unrun; actual runner exit130 after SIGINT to
its verified owned CLI PID. The owned server exited through `finally`.
No assertions, timeouts, skips or capability flags were changed to pass it.
`scripts/creator-web.sh` selects WebKit only by `capability boundary` (normal
and separate Sample Editor boundary); this locked engine does not admit the
product UI. This is expected capability refusal, not CSS/native-audio proof.
The canonical general boundary passed **1/1**, exit0,1.0s, on
`a2baf238fdb097ddcf0eefcbc5b9c9989ede912c`: user-facing refusal, private
UNSUPPORTED_WEB_RUNTIME diagnostics, absent activation and disabled export.
WebKit UI/PCM/processorerror and physical Safari/iPad remain unverified; do not
claim nine UI passes or bypass compatibility. The new shared layout test stays
registered without new skip/expected-failure annotations and runs in the
normal Chromium selection.

Final source publication requires, on the final clean commit:
complete30-case Chromium Perform/touch-fit/meter selection (all prior29 plus
new layout case), canonical WebKit refusal boundary, complete current Portal
check, committed ownership/admission, type and PR body/declaration checks,
exact file/status and parent/main refresh. Record those actual receipts in the
Draft PR and canonical Issues after completion, not anticipated results here.
The first complete package already retained seven PNGs and full JSON readback;
actual active native count-in was `COUNT-IN · 8 beats left`, four complete
encoder cells in all18 group/viewport observations, and native Solo[0].
The definitive success artifacts must be read back by path again after the
final head's run. Integration, independent review, full candidate/lane and
physical/device/hearing remain pending beyond this Task's bounded checks.



### Final screenshot projection correction

Final checkpoint `9cc15cd5fe7f39347336dac901329d6b9234cf67` passed the
complete30-case Chromium selection (6.2m) and both canonical WebKit boundaries.
The390px PNG nevertheless captured PRIMARY faders with the previous MORE
encoder labels/direction bounds: passive registration allowed a painted frame
to lag. This is a presentation defect, not a completed binding-coherence proof.
Update the already declared Perform registrations to layout effects so the
parent physical/upper bindings settle before paint; preserve all controller,
rotary and touch semantics. Assert the actual corresponding ENC1 binding after
every touch group transition and before the final PRIMARY screenshot in both
layout journeys. Fit the selected narrow Pad caption without splitting its
last letter. Re-run complete owning components and full30 packaged cases on
the corrected final head; retain the old successful run and its imperfect PNG.


Final coherence checkpoint premises refreshed to main `ba67a81d4200019f3e604bae2a69ea30f0354e91`:
external #2387 allocates2.0.120.0 plus immutable snapshot/Assembly identities;
no Perform/SDK/audio/Facade source, owning tests or governance changes.
Keep actual parent #2384 and owner freeze; no strict-update rebase is required.
The first coherence-checkpoint harness stopped at its deliberately stale-main
sentinel before committing, then its outer shell incorrectly continued:
clean-source package refused the dirty tree (exit2) and browser preflight
also refused it. These are harness/gate refusals, not product-test passes.
The corrected single Python driver checks each subprocess and stops at the
first failure; unrelated main movement is classified rather than treated as
a product blocker. Complete Creator82/1891 and current Portal179/50 already
passed after the binding fix; repeat only the affected final source/package,
ownership/type, complete30 browsers and canonical boundaries below.

</details>
