# Creator Interaction UI — U12c Numeric

Date: 2026-10-13. Parent: #2112. Owner: Codex `/root/control_kit`.

## Premises and dispositions

Fresh main and Task base: `28ff18c5c1f3790157193e900b5c7980cc595026`.
Branch `feat/creator-numeric-interaction-layout`, isolated worktree
`lmdj-goal-numeric-layout`, created with real symlinks and no upstream tracking.
Live #2112 was read before edits; its Numeric behavior is already implemented.
The earlier read-only preparation is `/tmp/lmdj-u12c-numeric-source-plan.md`.

Already delivered: six exact inputs, unit/bound validation, legal audition,
Apply/Enter-only save, unchanged-value no-op, Escape/Cancel and stale-owner
cleanup, native text Undo, pending save settlement and complete N13 journey.
The Figma NOT IMPLEMENTED annotation is historical, not a reason to replace
this state machine. Outstanding: touch-area placement, frozen Pad header,
saved/draft hierarchy and a range input sharing this same unsaved draft.

U12b is now actually merged at `0ae6dbd2298b0ca9993171b4178447268a9c94f3`.
Its optional ModalDialog `placement="touch-workspace"` implementation is
SHA-256 `6f2689b699d8d09219a2de6b5cc75fedef31458bc8ea2136b882fe28c02f4e94`.
It measures the actual touch rectangle, stays upright under rotation, scales
no smaller than one, and preserves native top-layer focus/background rules.
Use that API without changing the modal, default consumers or owner lifetime.
U05b1 Trim is merged at this Task base. Since earlier `0c873e67`, no Numeric,
SampleControls, SampleSurface or App producer/consumer source changed.

Root explicitly obtained the Sample writer handoff after U05b1 and the D03
owner's no-write audit for the five dedicated Numeric paths. D03's existing
assignment cancellation/busy seams are retained; App, SampleSurface and SDK
are outside this Task. Do not alter their fences or acquire their writer.

The figma-design-to-code skill was read before fresh high-fidelity context
and screenshot requests for file `GPFarNiZNsjLQzfG9kR8DO`, Numeric panel
`410:4278` and notes `410:4303`. Target: 368 square touch panel, padding16,
gap8, heading14/20, Mono36/50 draft, saved readout, 32-face/44-hit actions.
There are no static image/SVG assets in this panel. Reuse bundled fonts,
tokens, shared Touch control and native Modal; do not add dependencies.

## Declared files

1. `apps/creator-web/src/components/sample_parameter_editor.tsx`
2. `apps/creator-web/src/components/sample_parameter_editor.css`
3. `apps/creator-web/src/components/sample_controls.tsx` — captured padLabel
   prop only; preserve all fences, callbacks and other pages.
4. `apps/creator-web/test/sample_numeric_editor.test.tsx`
5. `tests/platform/web/creator/creator_web_sample_numeric_editor.spec.mjs`
6. `apps/docs-site/docs/hosts/creator-web.mdx` — Numeric paragraph only.
7. `apps/docs-site/docs/hosts/creator-interactions.mdx` — Numeric rules only.
8. This plan.

No writes to global CSS, Modal, ParameterSlider/ValueSlider, SampleSurface,
App, mounted workspace tests, shared Sample browser, ASSIGN, C1 or SDK.
Report a new dependency before expanding these eight paths.

## Implementation boundaries

Preserve the existing draft/preview/settled owner. Number and range both use
one validity/preview path; range release, blur and keyup never save. Explicit
Apply or Enter is the only changed-value save. Enter while the new range is
focused uses the same settlement path; Escape/Cancel/unmount discard it.
Saved value and Pad target come from the captured opening edit, not changing
preview or selection. Invalid text stays invalid; the range displays the
finite saved position until a valid range gesture replaces the draft.

Use the existing passed parameter spec, without a second registry: Volume
−60…6/0.1 dB ×1000; Pitch −24…24/0.1 st ×100; Pan −100…100/1;
Attack 0…2000/1 ms; Release 0…4000/1 ms; Tone −100…100/1.
Retain One Shot's unavailable Release and Pan/Tone explanatory hints.
The distinct new accessible name is `Pad A01 Volume preview` (and equivalent
parameter names). Preserve existing dialog, number and action names, so
inert-background N13 slider queries remain unambiguous. PREVIEW describes
the local draft, not an audio-running or Core-acceptance receipt.

The form has a fixed header/footer and bounded naturally scrolling body.
Reserve real 44px number/range/buttons without overlapping rows or clipping
focus. Use primary Apply then secondary Cancel, native number→range→Apply→
Cancel focus order. Portrait keeps the merged Modal's upright presentation;
resize retains the same owner, draft and fixed target. No below768×600 or
physical-touch/virtual-keyboard acceptance is inferred.

## Verification and acceptance

Source/light admission only at declaration. Actual results are recorded below;
Portal, packaged browser and rendered geometry remain UNRUN.
First add meaningful range/shared-draft cases and run the whole Numeric file
on old product for RED. Then run complete Numeric, SampleControls and Modal
component files, locked Creator typecheck and changed browser syntax.
Preserve the complete five N13 mounted App groups (27 cases): seven unsent
retirements, two Project replacements, native text/history ownership, twelve
pending outcome/boundary members, five sent-result/Runtime replacements.
Those tests are read/run, not edited. New plan admission also needs the full
77-test scope suite and exact staged-path/whitespace checks.

The original Numeric 300s case remains byte-for-byte, including import120s,
transition35s, 450ms pause and all legs: native legal preview with full
playback/response identity → invalid replacement clear → one revision-fenced
Apply and history increment → Escape/return focus/unchanged Truth → native
SHIFT Undo/Redo full playback and distinct command IDs → persisted reopen
and reset history. No raw transport bypass or artificial backend outcome.

Append separate real range/geometry cases at 1440×900, 1280×720, 1280×600,
1024×768, 768×600 and rotated768×1024. Actual pointer and keyboard range
changes must receive far-side preview ACK with zero authoring after release,
blur and keyup; Apply/Enter yields exactly one real update; Cancel clears and
preserves Truth. Measure all four inputs/actions at center plus four inset
edges, actual >=44 width/height, pairwise nonoverlap, focused endpoint bounds,
document/content horizontal overflow. Persist per-viewport screenshots/JSON.
Check initial/trapped/return focus, long/invalid hints, and resize out/back
without remount. Geometry is not audible or physical-device proof.

After separate Root heavy GO: whole Portal, own clean checkpoint, normal
Creator build/package, full original-plus-added Numeric spec and full existing
Sample Chromium/WebKit selections. Shared Sample browser now includes U05b1
Trim's additions; preserve the complete fresh-main selection and all original
600s/300s/180s budgets, Facade/quota/recovery/history/Playback/Tone/Delete/
encoder/failure/reopen legs and existing capability skips. No heavy command,
installation, retry, scope shrink, commit or shipping before its admission.

## Version Management

Version impact: none — no Product allocation, manifest, Module/Contract API
or persisted format changes. No release, deployment or cleanup.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/
Explain fixed target/saved value, touch-area placement and explicit-save range
draft; distinguish it from the existing outer range's release-save behavior.
Retain all historical N13, Playback, Pad, Capture, Trim and other Task sections.

## Dependency preparation

Root admitted only an APFS clone-copy of retained clean Capture Creator
dependencies after package/lock equality, Node26.7.0/darwin/arm64/ABI147 and
native binding identity checks. All nine symlinks resolved inside that source
dependency root. `cp -cR` naturally exited0 at10:38:29 UTC; only this new
destination's generated `.vite`/`.vite-temp` caches were removed. No package
manager, shared dependency symlink, source-tree change or foreign product
artifact was used. Receipt: `build/verification/u12c/dependency-clone-receipt.json`.

## Source/light results — 2026-10-13

The exact eight declared paths implement touch-workspace placement, captured
Pad heading, saved/draft hierarchy and one native range sharing the original
explicit-save draft. No changes to callbacks, underlying parameter registry,
authoring operations, App seams or native Modal implementation. Original
component cases and the complete original Numeric browser prefix are retained.

All commands below used the independent locked Creator dependency copy and
Node26.7.0. Logs and actual start/end/exit/owned-child receipts are in
`build/verification/u12c/`; no retry or shortened selection was used.

- `numeric-red`: whole Numeric file on old product, 10:44:34–10:44:45 UTC,
  exit1, 42 original PASS / 14 new FAIL. New failures identify missing range
  controls and saved/draft presentation. Raw output is retained.
- `numeric-components`: complete Numeric, SampleControls and Modal files,
  10:46:51–10:46:55 UTC, exit0, 96 PASS.
- `numeric-tsc`: locked `tsc --noEmit -p apps/creator-web/tsconfig.json`,
  10:47:53–10:47:54 UTC, exit0.
- `numeric-mounted`: all 27 cases in the five original N13 App groups,
  10:48:01–10:48:18 UTC, exit0. The other 165 cases in that broad file are
  explicitly not selected and are not claimed as verified.
- `numeric-browser-syntax`: complete changed Numeric spec, 10:50:32 UTC,
  exit0. The original 300s journey and all its assertions remain unchanged;
  six independent viewport cases exercise pointer preview, keyboard endpoints,
  Cancel, Enter-save, focus trapping/return, resize identity and invalid Tone.
- `numeric-scope`: full change-scope suite, 10:52:00–10:52:10 UTC, exit0,
  77 PASS. Exact eight-file staging and whitespace inspection followed; the
  initial staging command had run in the primary checkout and failed on the
  absent new plan, with no files staged there. It was corrected with the
  explicit owned worktree before the successful staged inventory/check.

The existing jsdom stylesheet parsing warning appears in the component runs;
these are behavior checks, not CSS rendering evidence. Actual >=44 CSS-pixel
targets, five-point ownership, clipping, focus bounds and six viewport PNGs
remain pending the separate browser admission. All recorded low-tier commands
terminated naturally and their receipts show no remaining owned descendants.
Whole Portal, normal build/package and full Numeric plus existing Sample
browser selections remain UNRUN. This is an incomplete source checkpoint,
not a completed Task, current-main runtime, audible or physical-device claim.

## Admitted heavy checkpoint — 2026-10-13

Root admitted only this already-started Numeric Task after Import's light
commands and the preceding M1 heavy window naturally ended. Fresh read-only
main is `12dcdfee511ff9093b95014c72af6188eb90a8c1`: since readiness
`c4bde2ff`, changes concern Sequence SETUP and M1 stress; the two Portal
intersections are SETUP paragraphs. Numeric/Modal/Sample producer-consumer
wiring, owning browser inputs and config are unchanged. Preserve this Task's
frozen `28ff18c5` base; no current-main runtime claim follows.

All eight source hashes and the `e8397aa9…` staged packet matched the admitted
freeze before execution. `heavy-20261013/initial-readiness.json` records this,
unchanged package/lock inputs, 28.9 GB free and all prior45 PIDs absent.
Official `bash scripts/docs-site.sh install` completed12:06:59–12:07:03 UTC
(exit0); `npm ci --prefix tests/platform/web` including the locked WebKit
postinstall completed12:07:24–12:07:25 (exit0). Source and locks stayed equal.
A readiness invocation mistakenly used unsupported `verify` mode and exited2
before Portal; its error is preserved. The documented `check` mode then
exited0. This was CLI preparation, not a product failure.

The original whole `bash scripts/docs-site.sh check` ran12:07:49–12:08:35 UTC,
exit0; all179 tests and50 rendered routes/internal links passed. Its raw log
SHA256 is `ab7e78c2482dbffc4aee56382671984f2e748a24e87958dc28177c8ab8778d0c`.
All observed children exited naturally. The per-command receipt binds the
unchanged frozen eight bytes and locks. This append only records that result;
Portal pages and product source are unchanged. Normal configure/build/package
and complete Numeric7 + Sample20 Chromium + Sample20 WebKit remain UNRUN.
The following atomic source commit is a clean build checkpoint, not shipping
or Task completion. Original light receipts lack per-command dirty-source
hashes; their truthful timing limits remain in the retained readiness packet,
not retrospectively reconstructed.

## First packaged run and bounded oracle correction — 2026-10-13

Clean source checkpoint `664f5c187c6a5b1097d58377596cbcd84fc6c2f8` was configured,
built and packaged through the normal Creator commands, each actual exit0.
Official all64 Project and retained official Sample fixture bytes matched
`66262c91…`/`1f1dc9cf…` and each public bundle verifier exited0. No Native fixture
regeneration or foreign product output was used. The own server's actual
ready PID55052/port56534/nonce was verified before the full original Numeric7
selection (one worker, all original budgets), 12:12:18–12:14:03 UTC, exit1:
original N13 PASS / six new viewport cases FAIL. Raw log SHA256
`5d7b381b89feed6cc1ce10b609f5a394ccc72bc75bb5364d7390cfa2aacacec4`.

All six failures were the new line438 unconditional opener-focus assertion
after changed-value Enter-save. The actual command ACK, one revision increment,
full saved playback/Truth and dialog removal had passed. At closure the opener
was disabled by the existing pending command. Existing Modal lines34–49 reject
a disabled opener and restore the first eligible fallback; they do not steal
focus again when it becomes enabled. The unchanged SampleControls test226–255
already verifies the disabled-trigger fallback. Original N13 only asserts the
opener after Escape, and the new cases' Cancel return-focus legs also passed.
Thus this new post-save assertion contradicted the established contract; it is
not evidence that this Task changed the product's return-focus handler.

The retained trace shows disabled then enabled opener, and the final 1440
screencast has the System logo focus-visible outline. Trace DOM snapshots do
not serialize activeElement, so no exact fallback DOM readback is claimed for
that historical run. The corrected new case now writes actual activeElement
identity before asserting the exact System fallback focused/enabled with its
panel still closed; waits the original35s opener-enabled budget; then asserts
System remains focused without deferred focus stealing. It also checks zero
background `trigger` receipts and exactly one update. Cancel/Escape opener
assertions, invalid-Tone/Truth/error legs, original N13 prefix and every deadline
remain intact. Only this appended browser evidence and the plan change; no
product, shared Modal, parent handler or callback is modified.

All24 original geometry JSONs (draft, resize-return, minimum and maximum at
six viewports) had zero horizontal overflow/overlap and all five points owned;
minimum observed control height44 CSS px. Each case stopped before invalid-Tone,
so that geometry and later legs remain unverified. Both complete Sample20
selections were not launched after the prerequisite failed. No partial result
is promoted to complete acceptance.

The original109 artifacts remain untouched. Own server exited0 after verified
SIGINT; all454 observed PIDs were absent at12:14:40.176668 UTC and the window
was explicitly released. `build/verification/u12c/heavy-20261013/` holds raw
commands, before/after source/locks/dist/fixtures, logs, six traces, output hashes
and `release-and-retention.json`. Root independently verified that release.
The correction is SOURCE-only until separate admission for the complete7+20+20
sequence. Product source and all10 existing dist hashes remain bound to664f5c18;
no rebuild is required for this test/plan-only delta, and no rerun is yet claimed.

## Corrected complete browsers and visual follow-up — 2026-10-13

Root admitted the exact test-only fallback correction in a new isolated proof
slot against the unchanged664f5c18 product and ten dist files. All original
selections completed with their original budgets, one worker and no grep:
Numeric7 PASS (12:24:02–12:25:14 UTC, exit0); Sample Chromium19 PASS/1 existing
WebKit-only skip (12:26:35–12:29:43, exit0); Sample WebKit1 PASS/19 existing
Chromium-only skips (12:30:10–12:30:16, exit0). Total47 selected,27 PASS and20
existing platform skips. This is three complete owning selections, not full
Creator, current-main or physical acceptance.

The corrected proof stores30 Numeric geometry JSONs, including the previously
unreached invalid Tone, and six exact activeElement records. Each save recorded
System as enabled/connected/non-inert while the opener was disabled, then kept
System focus when the opener became enabled. All30 measured controls retained
>=44 actual CSS-pixel height, all five owned points, zero overlap and zero
horizontal overflow. Source/locks/config/dist/fixture inputs stayed identical
before/after each command. The original109 failure artifacts remain byte-exact.
New255 output artifacts and89 observed child identities are bound by
`corrected-20261013/release-and-retention.json`; all89 were absent at the explicit
12:31:49.195910 UTC release after the own server's actual exit0.

Screenshot review caught an additional presentational defect that those
control-only geometry assertions did not measure: the large `dB` unit wrapped
into `d`/`B` in1440×900 `numeric-draft.png` and768×1024 `numeric-range-min.png`.
Paths are below the `u12c-20261013-corrected-numeric-chromium` output slot.
The fixed touch area inherits `overflow-wrap:anywhere`; the unit span could
shrink beside the input's100% flex basis. Browser PASS is retained, but this
observed visual defect means the Task was not yet visually complete.

The finite correction changes only the local unit span to `white-space:nowrap`
and `flex-shrink:0`, retaining the original input minimum44 and all handlers.
The existing geometry helper now records the actual unit text Range while the
number input is scrolled into view, before assertions. It independently expects
`dB` for Volume and no unit for Tone; requires one text rectangle, text contained
inside its unit box, the unit inside the number row/content, and no unit/input
overlap. All original four-control >=44/touch-point/clip/nonoverlap checks stay.
There are still seven cases: original N13 plus six viewport additions, with no
Pitch/Attack legs added. Actual rendered conclusions will cover `dB` and empty
Tone only; `st`/`ms` share the same nonshrinking/nowrap source rule but are not
claimed as separately browser-measured. This CSS change requires a fresh normal
product build/package and full Numeric7 after explicit Root admission. Prior
complete Sample selections remain evidence for their recorded pre-CSS inputs;
they are not relabelled as later-source runs. No extra Task or shared Modal/
parent/global-CSS change is introduced.

## Final unit correction proof and shipping boundary — 2026-10-13

Root independently reviewed the local CSS, existing helper and plan correction.
Browser syntax and whitespace checks exited0 before the clean unpublished
checkpoint `dafe9e1970829d77f13abbc1da35448fcdb0f0c7` (exact eight files).
Normal `bash scripts/creator-web.sh build` completed12:42:11–12:42:14 UTC,
and `package` completed12:42:50–12:42:51, both exit0. No configure, install,
Portal, Native, full Creator or full Sample repeat was run for this CSS delta.
The new style asset is `f853e165…`; JavaScript and Runtime bytes remain the
earlier verified product bytes. HEAD/tree are externally bound to the actual
ten-file dist and host-manifest hashes in `unit-20261013/artifact-identity.json`;
the host manifest has no Git source-revision field. Both official fixture
hashes remain unchanged and retain their earlier public-verifier PASS.

The complete original Numeric7 selection ran once, with one worker and all
original budgets/legs,12:43:32.308288–12:44:45.574283 UTC:7 PASS,0 failures,
0 skips, actual outer exit0. Raw log SHA256
`dac952fef6b3199d6b43f41108ef50b07e86dc89d927ab93097eb67046d28e9e`.
All30 geometry records retain minimum observed control width164 and height44
CSS px, five owned points, zero overlap and zero horizontal overflow. The24
Volume records each contain exactly one `dB` text rectangle within the unit
box, number row and visible content, without overlap or reducing the input
below its44px minimum. Six invalid-Tone records correctly have no unit. The six save-focus
records retain exact System fallback focus after the opener becomes enabled.
Actual1440×900 draft,768×1024 range-minimum and768×600 invalid-Tone PNGs were
inspected; the previously observed `dB` wrap is absent. `st`/`ms` remain shared
CSS-rule coverage, not separately measured browser claims.

The owned server PID24887 exited0 after verified SIGINT at12:44:59.945710 UTC.
All51 observed child identities were absent at the explicit
12:45:50.548131 UTC release. The133 new artifacts, source/locks/config/dist/
fixture before-and-after bindings and actual outer exits are recorded in
`build/verification/u12c/unit-20261013/release-and-retention.json` (SHA256
`c83b89c9991d4c52262426b245c3963d5e5ea8f05c1c34d85ab0bcaab037a386`).
The original109 failure artifacts and the corrected255 artifacts were each
rehashed and remain unchanged. No automatic retry or shortened journey occurred.

Fresh pre-shipping main is `3f05b962902c9bf2d9c8c5f558ab3b4d033f5492`.
Intervening Slice navigation, read-only overview, Sequence SETUP and Core M1
changes do not alter this Task's Numeric/Modal/Sample producer-consumer files
or owning Numeric/Sample browser/config inputs. The two shared Portal files
have independent overview/Slice/Sequence paragraphs; Numeric paragraphs are
unchanged. The tested base is retained without a rebase. This does not claim
current-main, auditory, candidate, physical-device or virtual-keyboard acceptance.

The final commit may add only this actual-result record after the tested
checkpoint; the other seven files must remain byte-identical. Whole Portal
179/50 remains its original recorded input-bound PASS. Full Sample Chromium
19 PASS/1 existing skip and WebKit1 PASS/19 existing skips remain bound to
the preceding664f5c18 product; they are not relabelled as new-dist runs.
The original focus-oracle failure, preparation failures and light-receipt
provenance limits remain visible above. Merge/review are Root-owned, and this
Task does not close the remaining umbrella work or authorize another Task.
