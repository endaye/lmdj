# Complete Pattern selection after a COUNT-IN recording opens

Relates to #2112 and #2233. Refreshed main/base
`fa6998234de0560b09ba4720f6f49f8e8af8ba4e`; isolated branch
`fix/count-in-recording-selection`. This is the sole writer for these Task files;
other dirty worktrees and release-owned resources are preserved.

## Premise dispositions before implementation

Already delivered: C1–C3 and ordinary C4 (#2377, merge98c794d2), COUNT-IN
re-land (#2479, merge880535ae), and the complete ordinary browser preparation /
ingress-clock correction (#2482, mergefa6998234). Reuse those producers,
receipt/SDK shapes, original input clock and exact Truth oracle. Do not
reimplement Native publication, Journal continuation or the JS pre-arm decision.

Still outstanding: current `selectSequencePattern` and the rendered workspace
unconditionally lock `countIn.active`, which remains active through Applied
recording to terminal caller consumption. The current controller exports and
uses `countInBeatsRemaining` and `countInMetronomeArm` (positive controls), but
has no phase-specific selection gate; enumerated App callback, arrow/picker
and Perform consumers all inherit the unconditional lock. The original C4
published0c36797f contains the intended gate and tests; it was excluded from
the ordinary integration and not restored by #2479. Approved
`2026-10-18-recording-pattern-switch-segments.md` explicitly requires Applied
plus durable opening before selection, original S0/caller through genuine
Record-off/Stop, and locks during preparation/cancellation/settlement.

Restore only that consumer boundary against current code. Open no selector on
planned S, a recording lamp alone, pending/failed opening or cancellation.
Retain settings/grid/structure locks throughout recording and retain the
original scheduled caller; do not infer its terminal receipt from current B.
The owner's JS pre-arm / late-refusal risk remains unchanged. S5/I2c policy
questions, full fault composition, candidate/version and physical acceptance
remain separate work, not fulfilled by a green prefix here.

The first clean checkpoint7a8f01be runs the complete four-case browser
selection with3 PASS/1 FAIL (exit1/133.574s). COUNT-IN A-B-A passes exact
Record-off Truth but fails the original5s Stop far-side assertion. Its raw
transport trace proves a positive original-ticket consume followed by a second
cancel of that consumed ticket while final ordinary inspection is outstanding.
Keep the entire failed run. Complete the same consumer boundary with an
explicit post-consume handoff phase: the original caller cannot receive another
cancel/observe after positive consumption; transport keys stay disabled until
the ordinary projection settles, then the user's next gesture uses ordinary
transport. A refused consume still retains its original caller and retry path.
Add a held-projection controller regression and actual mounted key regression
before changing the controller. All changes remain within the declared files.

## Declared files

1. This plan.
2. `apps/creator-web/src/runtime/count_in_controller.ts`
3. `apps/creator-web/src/app.tsx`
4. `apps/creator-web/test/count_in_controller.test.ts`
5. `apps/creator-web/test/workspace_shell.test.tsx`
6. `tests/platform/web/creator/creator_web_recording_switch.spec.mjs`
7. `apps/docs-site/docs/hosts/creator-web.mdx`
8. `apps/docs-site/docs/hosts/creator-interactions.mdx`
9. `apps/docs-site/docs/platform/web-runtime.mdx`
10. `apps/creator-web/src/components/count_in_readout.tsx` — render the explicit
    post-consume handoff as Finishing, retaining the existing user-facing state.

Amend before expanding. No Core/Facade/Host protocol/SDK/Engine/Store, CSS,
workflow/release tool, identity manifest or Product allocation change.

## Verification and complete journeys

First run the mounted selector regression against unchanged App behavior and
the original whole COUNT-IN browser cases against the retained ordinary main
artifact; retain actual RED at the gate. The retained artifact's production
source equals this base (only #2482 tests/plan differ); bind all hashes and
modified test bytes. An undefined pure-helper RED alone is not behavior proof.
Then verify the phase helper and mounted actual App gate, original caller
retention, pending opening, failed/absent Applied, cancellation and authoring
locks. Run complete Creator unit/type checks.

After complete owning unit/type and Portal checks pass, freeze a clean local
source checkpoint to bind the official packager's mandatory clean-source
provenance. It stays unpublished until every declared packaged journey passes;
it is not Task completion, review or shipping evidence. Retain any failed
browser result and fix the owned source before advancing the Task.

Build/package the final ordinary own-tree artifact using pinned6.0.5/Node26 and
locked browsers. Run all four complete S3 cases: ordinary and one-bar COUNT-IN,
each ending on A and B. Keep original per-request and case deadlines.

1. During COUNT-IN selectors stay locked; only real Applied+opening ACK opens
   them, with the original scheduled ticket still retained.
2. Real source Press, queued/actual S, source cross-S physical Release and
   target input retain actual Native sequence/correlation and Journal frames;
   a real refusal requires a distinct explicit gesture, never automatic replay.
3. GROOVE -> B, ordinary Perform Launch -> A, optional final B all follow the
   real current/pending projection, without a second Performance Journal.
4. Record-off closes the actual last Pattern at F. COUNT-IN consumes its exact
   original caller and preserves original A/S0 receipts; Stop then settles
   ordinary playback without rewriting saved Truth.
5. Compare whole expected A/B Project/revisions and every Asset path/length/
   digest, then actual reload/reopen and complete Truth equality/page errors.

Retain complete existing Creator COUNT-IN/metronome browser selections and
original S7 cancellation/clock/recording/reopen legs. Full Creator proof and
candidate-host/full lanes, held-I/O/fault combinations and physical/audio
acceptance remain explicitly unverified unless actually run. Run full Portal
check for current fact corrections, staged/committed new-file ownership,
syntax, body lint, declaration and refreshed exact-head review/protection.
No tolerance, budget, selected acceptance leg or threshold is reduced.

## Source and component evidence

Unchanged-product mounted RED fails at the exact selector-after-opening ACK
assertion (exit1/8.230s). The two complete restored COUNT-IN browser cases on
the authenticated baseline artifact both fail at the still-disabled picker
(exit1/48.908s), after genuine Applied recording. Both failures are retained.

The restored gate and App wiring pass both complete owning component files:
261 tests,87.857s. Removing only the two durable opening guards in a fresh
Vitest process fails3 targeted checks at their intended assertions; exact WIP
bytes restored with fresh write/touch then pass14 selected cases. Complete
Creator unit suite passes87 files/2041 tests,96.719s; TypeScript passes. Existing
CSS/localStorage and optional dependency-script warnings remain in raw logs.
A trailing blank line in the mounted test was removed after the full run;
only EOF whitespace changed, with byte-equivalence after rstrip recorded.
Full Portal check passes69.106s (51 routes/internal links); staged ownership77
and final types pass. Final own-tree package/browser and current-head shipping
still await.

The handoff regressions first fail on duplicate cancellation and the enabled
Stop key (2 FAIL/2.457s). The final source passes the complete87-file Creator
suite,2045 tests/98.199s, including pending-consume refusal retention and actual
mounted Finishing/disabled keys followed by ordinary Stop at epoch3. The first
2044-test run is diagnostic only because the last caller guard/test was edited
while it ran; it is superseded by that complete final run. The fixture's literal
`playing:false` caused one TypeScript failure; its mutable playing field is now
boolean and the original complete type command passes1.374s. Portal passes
64.447s (all51 routes and internal links). Existing warnings are retained.

## Version Management

Version impact: Creator Host MINOR debt for completing the additive S3
COUNT-IN consumer, deduplicated within the existing higher same-domain debt
in #2237. No public SDK/Facade/ABI/Contract/Project change and no manifest,
Product/Assembly/Build/snapshot allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/ /platform/web-runtime/
Reason: current pages still contain withdrawn-COUNT-IN statements and need the
actual Applied/opening/selection boundary. Product topology is unchanged, so
no diagram topology edit is required. Preserve the documented JS pre-arm risk.
