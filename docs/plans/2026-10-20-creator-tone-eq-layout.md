# Creator Tone/EQ interaction layout (#1667 / U05b2)

## Task and authority

One Task / one Conventional Commit on isolated `feat/creator-tone-eq-layout`,
parent Draft #2421 / `e90891e0673195e3206d6f06935e936bee0882b9`.
Fresh integration main: `1581f3bd42616d36637b1d3131747bb51dee5f8e`.
Root is the sole shared-Sample writer. Development, relevant verification,
commit/push and a Draft child on the same stack are authorized. Main stays
frozen: no merge/auto-merge, release/tag, deployment, Channel or Git cleanup.
The unrelated Native-metronome owner decision remains pending.

## Premise audit before implementation

- Already delivered: #1780 / `f6dedbe53645b52446078ffa9a66710f83fbf24b`
  supplies the shared voice DSP; #1799 /
  `65d0125330baa5e9d5318b8f0a557e51ac16dd36` supplies the Facade/Hosts and
  Creator controls; #1816 / `8845007de025b1559329f2fce07592b7e39cabfc`
  settled the old version debt. All three are actually MERGED. Do not redo
  those Tasks, DSP, Contract, persisted fields or old version settlement.
- Current source positively contains Tone, three original EQ poles, shelf/
  cut/bell and mid Q, grab offsets, keyboard/Delete, preview/commit-once,
  Escape/pointercancel/audio-suspend/unmount cancellation and numeric Tone.
  Reuse those paths and preserve their full owning tests.
- Still outstanding: the scoped Figma touch area (file
  `GPFarNiZNsjLQzfG9kR8DO`, root403:411 / touch403:738) has compact Tone,
  a132px three-band graph with coloured poles/curve, a frequency summary and
  gesture hint. Source instead has the old title/blue borders, a320px minimum
  graph and long readout; it has no response curve or compact summary.
- Still outstanding: fixed22-view-unit SVG hits only stay44px while the
  graph is not reduced. Its minimum width overflows the narrow touch panel.
  Shrinking that minimum alone would make the actual targets too small.
  `viewPoint()` also assumes an unrotated bounding box, while the supported
  tablet shell rotates90 degrees. These are input/layout gaps, not new DSP.
- Exact main/stack-parent equality was verified for `eq_editor.tsx`
  (SHA256 `3e6c36b653fcd79ae35aff1b8afbb526026379232c80f3380113ed6ced77ddcf`)
  and `voice_dsp.cpp`
  (`025c97f0fdf8e2596f86c788f1f20d22b62bcb5956d137ddc35aa2eb318a09fa`).
  Main history names #1799 and the later Playback-only #2140; the complete
  live open-PR inventory has no successor Tone/EQ layout. The existing
  editor/handlers are positive controls for the audit, not a title-only search.

Both initial high-fidelity Figma context responses included screenshots.
Root/touch text and screenshots are retained at `/tmp/lmdj-1667-figma/`.
Existing logo/encoder assets lie outside this touch-only Task. The exported
Three-band-EQ SVG is a prototype of interactive, data-driven UI: reuse the real
EqEditor, not a frozen picture of example parameters. No static image/SVG
asset or temporary Figma URL enters product code. Existing fonts/tokens,
ParameterSlider, ValueSlider and EqEditor are the matching native components;
React/plain CSS remains the stack, without a design-library dependency.

## Declared files

1. This plan.
2. `apps/creator-web/src/components/sample_controls.tsx`.
3. `apps/creator-web/src/components/sample_tone_layout.css` (new, scoped).
4. `apps/creator-web/src/components/eq_editor.tsx`.
5. `apps/creator-web/src/components/eq_response.ts` (new, read-only display math).
6. `apps/creator-web/src/components/value_slider.tsx` (derived paint position).
7. `apps/creator-web/test/eq_editor.test.tsx`.
8. `apps/creator-web/test/eq_response.test.ts` (new).
9. `apps/creator-web/test/sample_controls.test.tsx`.
10. `apps/creator-web/test/value_slider.test.tsx`.
11. `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`.
12. `apps/docs-site/docs/hosts/creator-web.mdx`.
13. `apps/docs-site/docs/hosts/creator-interactions.mdx`.

No Core/SDK/Contract, App, global stylesheet, Provider, package/lockfile,
manifest, Product/Assembly/Build/snapshot, CI/workflow or new asset changes.
Amend this declaration with evidence before adding another file.

## Implementation boundaries

Scope presentation through the actual hardware/Touch/Sample Tone root.
Keep the approved32-unit ordinary faces,44px actual actions and existing
numeric entry. Give the Tone input a44px track hit area with the design's
4px track/14px thumb. A custom paint-position value derives from ValueSlider's
existing shown value, including preview and cancel; no new controller/state.

Reuse the same EQ viewBox, frequency/gain/Q bounds, data units and gesture
handlers. Make the graph responsive and132px high. ResizeObserver measures
its local CSS viewport so invisible hit ellipses remain44 local CSS pixels
and visible dots12; supported outer stage transforms never shrink below1.
This does not compensate by reducing another target. Preserve full hits near
plot edges within the touch panel's existing padding. Convert real pointer
coordinates through the SVG screen matrix for the rotated tablet; retain the
original no-layout fallback for unit DOMs and all original commit/cancel rules.

The new curve is a read-only frequency-response projection of the current
three-band EQ, including the active gesture, never an image or a fake curve.
It evaluates the fixed48kHz engine's existing shelf/bell/Butterworth-cut
coefficients (including float coefficient rounding) without rendering PCM,
creating AudioContexts, calling new Facade operations or changing DSP.
The plot shows its existing +/-18dB window; the underlying response/parameters
are not clamped or persisted. Tone remains the separate existing filter.
Use independent response properties plus a bounded comparison with the
existing Native implementation; do not duplicate or alter Native processing.

Summaries come from shown band values, preserve the full existing readout
(frequency/gain/Q/kind) and keep bypassed bands honest. Do not replace current
values with Figma's example120/1.2k/8k. A gesture hint supplements existing
keyboard/accessible value text. Preserve Cut, mid double-tap Q, Delete/bypass,
all refusal/UNKNOWN/recovery/disabled branches and all allowed parameter ranges.
Coincident poles retain their existing data/DOM order and keyboard access;
do not invent parameter restrictions in a layout Task.

## Verification and far sides

Before product edits: original complete sample_controls/eq_editor/value_slider
files and TypeScript; actual parent-package geometry at all six requested
viewports. New failures must come from the real minimum-width/hit/curve gap,
not a missing import or screenshot-as-implementation.

| Journey | Required far-side assertion |
| --- | --- |
| Tone/EQ at1440x900,1280x600,768x600,768x1024,390x844,844x390 | Real range/value/pole targets>=44; separate12px logical dots; no horizontal overflow/clipped labels; centre/four edge hit owners, including existing SVG-order overlaps; responsive132px graph and live summary |
| Pointer/keyboard edit | Real Native playback/readout changes, one commit; pointer press without travel changes nothing |
| Rotation/resize | Actual new viewport plus rendering frame before measuring; rotated drag follows the intended viewBox direction and retains full hits |
| Preview -> Escape/pointercancel | Changed display/preview, original complete Truth restored; no save |
| Mid Q / shelf Cut / bypass | Correct original Q/frequency/gain/kind units and bounds; readouts/curve follow actual values |
| Undo -> Redo -> cold reopen | Full original playback/revision and Project file SHA/length identities restored/persisted; no truncated journey |
| Disabled/suspended/unmount | Original controls refuse/cancel through existing owners, no new policy |

Run full owning component files and pure response properties, TypeScript,
the complete Creator UI suite when final TSX changes are ready, pinned
Wasm/UI build and a formal clean package. Run the original complete Sample
selection (Tone/parity/history/PCM-owning journeys retained) plus the new six
journeys, and the unchanged existing signal-level Tone PCM owner where
applicable. Do not replace these with screenshots or a shortened happy path.
Run full Portal for changed current pages; staged and committed new-file
ownership, exact-file/diff/body/declaration checks before push. Keep any
source checkpoint local until all owning browser legs pass.

No new universal gate or full13 obligation. Complete candidate/full lanes,
final35-screen composition, physical devices and hearing remain separate.
Preserve historical local Chrome listening records and the old deployed-build
hearing ledger as distinct evidence; this UI Task neither resets those rows
nor upgrades them to a new candidate. Cardputer's compiled-out voice DSP does
not become a non-neutral hearing requirement. Do not close #1667/#2112 here.

### Source-freeze evidence

Fresh precommit fetch still resolves main to the exact SHA above; the open
successor inventory and #1667 scope remain unchanged. On the parent official
package, all six new journeys actually fail inside their geometry/overflow
assertions (terminal1); the original traces and measurements are retained at
`/Users/endaye/.codex/task-evidence/lmdj-1667/parent-red-20261020T100732Z`
(37files, manifest SHA256
`f64541c9fc698fb1b126dca4322a641be7246b8d5345f31621d83941bb1d1f98`).
The baseline three owning component files pass73 tests and TypeScript.

Implemented-source checks: four complete owning files84 tests, TypeScript,
complete Creator UI85 files/1999 tests, and complete Portal179 tests/52pages/
10diagram sources/20outputs/50routes pass. The full UI and Portal were rerun
once to recover missing terminal receipts from a truncated tool response;
both actual reruns exit0. Their final logs are `/tmp/lmdj-1667-full-vitest-receipt.log`
and `/tmp/lmdj-1667-portal-receipt.log`.

The advisory comparison compiles unchanged Native DSP and compares8 parameter
sets at11 frequencies (88points) with the display response. To expose a shared
gain-sign defect, a temporary adapter negates Mid gain before Native prepare
and a fresh display mutation does the same: their parity still passes88points,
but the original independent +6dB centre test fails at its actual assertion
with -6dB (terminal1). Restore uses fresh source bytes/mtime; the original
complete four owning files84 tests and TypeScript pass again, and restored
Native/display agreement passes88points (maximum discrepancy0dB in this run).
The bounded mutation is outside shipping inputs; no Native source is changed.
Receipts: `/tmp/lmdj-1667-mutant-receipt.json`,
`/tmp/lmdj-1667-mutant-oracle.log`, `/tmp/lmdj-1667-native-reference-final.json`.
These mathematical checks are not PCM, browser or device acceptance.

The local commits are unpublished clean-source checkpoints. The owned proof
runner requires clean Git source and records its full HEAD separately from
the package's byte identities. Source audit correction (2026-10-20): both the
stable full `proof` entry point and standalone `package` enforce clean source.
The latter delegates to `apps/creator-web/tools/package.py`, whose
`require_clean_source` runs before distribution output. The earlier contrary
audit note was wrong; the corrective EQ Task retains the actual dirty-tree
exit2 and fixes that description without changing the gate. Neither embeds
HEAD in the distribution manifest. A checkpoint must not be pushed or called
completed work until every declared owning browser leg passes. Any resulting
fix stays in this one unpublished Task commit, with all negative runs retained.
No new pitfall entry: the
responsive/input defects are fully expressed by owning product regressions;
existing resize/output-slot guidance is followed.

The first packaged six-viewport run passes every initial geometry, full hit
owner, preview/cancel, actual drag, Q, cut and bypass leg. All six stop at the
new Undo oracle: its expected Project revision advances correctly, but the
outer inspection `project_revision` incorrectly stays4 instead of6. Correct
both expected revision aliases (6 after Undo,7 after Redo), retain complete
inspection equality and rerun every remaining leg; no parameter/identity
assertion is removed. Original six failures/trace bytes are retained at
`/Users/endaye/.codex/task-evidence/lmdj-1667/tone-v1-20261020T103112Z`
(30files, manifest SHA256
`ce29d392c52030686e0da8be8c0ec1c0eb91138c58a1ec6e77312cfc76674246`).
Product TSX/CSS/response bytes remain exactly the first checkpoint's bytes.
An additional UI binding regression now proves the visible response and
frequency summary both change during a real editor preview and both return
on Escape without commit; a flat decorative path cannot satisfy it. Final
complete owning files now pass85 tests plus TypeScript. Its first harness run
used an unavailable matcher; the corrected test uses the repository's existing
textContent assertion and the original two-decimal frequency format. This was
a test-harness failure, not product evidence.

The next six-viewport run exits1: one complete844x390 journey passes; four
others reach exact cold-reopen Truth/file equality but measure before the
asynchronous controls have mounted (zero targets);390px reaches the edited
Mid's right-edge sample, which correctly belongs to High's later SVG ellipse.
At the permitted1840Hz/+3.9dB Mid and8000Hz High, their44px footprints overlap
on the226px graph. This is the explicitly retained DOM-order overlap behavior,
not undersized geometry. Keep all five samples and the44px threshold: compare
each actual owner to the last ellipse containing that exact screen point,
using an independent screen-matrix ellipse containment calculation; continue
requiring all-owning hits whenever no pole overlap exists. Centre ownership
stays asserted for this separated-centre fixture. Do not alter values, ranges,
drag travel, keyboard rules or product hit order to sidestep this case.
Await the real five controls before measurement after reopen, with the existing
default assertion deadline; retain every reopen/resize/identity leg.
Original5fail/1pass and traces:
`/Users/endaye/.codex/task-evidence/lmdj-1667/tone-v3-20261020T104055Z`
(33files, manifest SHA256
`a15d84979204bed2b81dce26aa1d64a21884b06f3646743ae151ce90c680d5ac`).
The exact2000-test complete UI run also exits0 at this checkpoint. Final tiny
paint alignment uppercases the existing Tone label as in the authoritative
Figma; the accessible label/text and behavior remain unchanged.

### Verified shipping evidence

At tested source `56e00a0055bd40be598a0af566e5ef584ce08c53`, all actual
terminal results have been read: owning85, complete Creator UI2000,
TypeScript, full Portal179/52pages/10sources20outputs/50routes, official
configure/build/package and ownership77 pass. Six complete viewport journeys
pass independently; the complete original Sample selection also passes38
with1 pre-existing WebKit-only skip, including those same six journeys and
every old branch. The unchanged actual Master-output Tone attenuation test
passes1/1. Do not double-count the six repeated journeys as new feature proof.
All runs retain MacBook Pro Speakers as their observed output. This is
automated signal evidence, not new human listening or device acceptance.

Final330-file evidence capsule:
`/Users/endaye/.codex/task-evidence/lmdj-1667/verified-20261020T105805Z`,
manifest SHA256
`451da2b9f84bf8b294011d3343d164ea7eeb715125828c610301c9c5b13c5ecf`.
It includes package bytes, exact source, fixtures, complete identities,
all three terminal browser receipts, screenshots and owning check logs.
Servers are stopped with their exact owned PID/nonce; no Git cleanup occurs.

The final amendment changes this plan only, correcting the proof/package
statement and recording results. Before push, verify the final diff from the
tested source names only this plan, regenerate the official package from clean
final HEAD, and compare all10 distribution files by full SHA256 and byte length
to the tested capsule. Record final/tested heads and that identity check in the
PR; do not pretend that the distribution manifest contains a Git revision.

## Version Management

Creator Host compatible MINOR debt for the added response/summary presentation,
consolidated into #2237's existing same-domain debt while retaining all higher
debts. No new Core/Contract/ABI/persistence impact, version identity allocation
or Product/Assembly/Build/snapshot change. Old Task12-20 settlement remains done.

## Documentation Impact

Documentation impact: required
Reason: describe the responsive interactive graph, derived response and live summaries
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/

The same existing Host components and four-region edges remain; no source
diagram or immutable snapshot is changed. Independent current-head review
remains PENDING, and main's explicit merge hold applies throughout.


## Main integration refresh (2026-10-21)

Original #2423 and corrective #2426 are integrated as one complete corrected
Task. The unchanged original ce6b5e94 source has a proven Mid/High wrong-hit
finding and must never land alone. Reuse the corrected 2d1fcabe implementation,
all original six unconditional geometry journeys, both coincident/edge cases,
full Sample import/history/Truth/files/reopen and unchanged Master Tone PCM.
Historical permissive-oracle results and all actual negative receipts remain.

Live main is 4b25c2e228fa248a98a0244e0516a9950f08c317. Its EqEditor still has
the original geometry and no response/contained separated targets; no successor
delivers this Task. Existing writers, valid ranges, Cut/Q/bypass and gesture
owners are retained. Current locked Vite8.3.4 and shared portrait/short-landscape
shell are the baseline. Local Pad integration d10f3476 is the working parent
while #2462 undergoes browser verification/review. Before commit/publication,
refresh actual main, rules and merged Pad source; retain published original
2d1fcabe history through an ordinary ancestry merge, with only this Task's
verified source delta against the actual main first parent.

Declared integration paths (16):
- `apps/creator-web/src/components/eq_editor.tsx`
- `apps/creator-web/src/components/eq_handle_layout.ts`
- `apps/creator-web/src/components/eq_response.ts`
- `apps/creator-web/src/components/sample_controls.tsx`
- `apps/creator-web/src/components/sample_tone_layout.css`
- `apps/creator-web/src/components/value_slider.tsx`
- `apps/creator-web/test/eq_editor.test.tsx`
- `apps/creator-web/test/eq_handle_layout.test.ts`
- `apps/creator-web/test/eq_response.test.ts`
- `apps/creator-web/test/sample_controls.test.tsx`
- `apps/creator-web/test/value_slider.test.tsx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-20-creator-eq-pole-hit-overlap.md`
- `docs/plans/2026-10-20-creator-tone-eq-layout.md`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`

Verification: run complete current Creator components and types, native fixture
generation, official clean-source configure/build/package, full Sample browser
selection including all eight strict EQ journeys, unchanged Master Tone PCM,
and full Portal. Stage/committed ownership and PR-body/declaration checks apply.
Every actual failure remains evidence; no range/target/assertion/timeout or
journey reduction. No test or package pass is claimed at this source checkpoint.

Version impact: existing Creator compatible MINOR debt in #2237 absorbs this
feature and its PATCH correction; retain higher existing debt. No identity,
manifest, Product/Build/snapshot, Contract/ABI/persistence change.
Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/
Reason: responsive Tone response and actual contained non-overlapping targets.
No frozen release/deployment path, COUNT-IN restoration or device/hearing claim.
Independent current-head review remains required; #1667/#2112 remain OPEN.


Current integration source checks: complete Creator85 files /1963 PASS
(114.560s wrapper), explicit-project TypeScript PASS, offline dependencies PASS,
staged ownership77/77 PASS, native CLI and all three fixtures PASS (38.283s,
Project/Sample reproducibility retained), full Portal PASS (84.634s,179 tests,
53 pages,51 routes/links). Initial npm --prefix exec tsc invocation ran from
the repository root without its tsconfig and exited1 printing compiler help;
that invocation is not a source defect or PASS. The unchanged source then
passes node apps/creator-web/node_modules/typescript/bin/tsc --project
apps/creator-web/tsconfig.json --noEmit. Both actual receipts remain.
Official clean package/browser evidence and final current-head review PENDING.


Pad/Empty #2462 actually merged as `0e3f59a52a39715279980b0bbec4860f7a56a664` from source
`d10f34762c7247a0eb5c4a36b152ce9b77426b3e`; complete13-path retention and unchanged source tree verified.
Refreshed main policies match the already-read AGENTS/CLAUDE, issue-done, Git,
version, Portal and pitfall rules. Both original Tone PRs remain OPEN at their
original heads, with no review threads; no intervening Tone successor exists.
The verified local source is now committed with this actual main as first
parent and original corrected2d1fcabe as the ancestry parent. Only the16
declared corrected Task paths differ against main; no published rewrite.
