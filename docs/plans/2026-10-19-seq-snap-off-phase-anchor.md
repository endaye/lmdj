# SEQ SNAP OFF: current-loop phase anchor (S5 P1)

Parent: #2112 / #2234. Original stack layer #2378; independently integrated
from main after the owner's partial unfreeze.

## Current main integration (2026-10-20)

This section supersedes the historical stack-only shipping hold below for this
Task. The owner permits ordinary feature/fix/test integration while the current
release stays fixed at `8c361623f`. Frozen paths remain `.github/workflows/`,
`tools/release/`, `scripts/release.sh`, `scripts/cloudflare-host-deploy.sh`,
`docs/release-evidence/` and `apps/docs-site/docs/releases/`; none belongs to P1.
No release, deployment, Channel or Git cleanup action is authorized here.

Isolated branch `feat/seq-phase-anchor-main` starts at refreshed main
`8126d401bae8681caca98af32594458edc4be9ba`. Preserve published #2378 and the
remaining Draft stack without history rewriting. Integrate exactly P1's ten
declared files below on a new main-target PR; keep #2377 Draft and COUNT-IN UI
withdrawn until its existing blockers are addressed. P1 has no production call site and
depends on neither Creator C4 nor COUNT-IN UI. Actual C3 was delivered by
#2373 / `8c1ee714147b6ba64decb1036b46fd76c89ebf80`; do not repeat it.

Fresh premise disposition: #2234 remains OPEN; no successor delivered this
arithmetic on main. The three owning source/header/test files are byte-identical
to #2378's original parent. Existing exact anchor helpers are present, while
this new cross-Pattern mapping is absent at their authoritative declarations,
definitions and owning tests. Preserve the approved loop example and unresolved
Voice chase question; this layer cannot select or start a Voice. Version debt
remains the existing Audio Runtime additive API MINOR debt under #2237, not a
new allocation or a reduction of the P2 ABI debt.

Unchanged main baseline: configure and existing test target build PASS;
complete `audio.prepared_sample_bank` PASS (5.599 s). Repeat the full owning
component, the rebuilt target-only mutation and restored producer, dependency
check, official diagrams and complete Portal, then staged/committed ownership
and exact-body declaration checks. Independent current-head review, complete
conversations, conflicts and live protection are still required before merge.
The original stack's evidence and unrun OFF/candidate/device journeys below
remain historical evidence; they do not become full acceptance here.

Integration owning receipts: fixed producer and complete component PASS
(7.943 s). A fresh build with only the source-loop reduction removed fails
the actual literal approved-example assertion at
`prepared_sample_bank_test.cpp:541` (CTest exit 8, 5.145 s). Restore byte-identical
source with a fresh mtime, confirm the producer recompiles, then the complete
component PASS (5.945 s). Core dependencies PASS. Official diagrams and the
complete Portal PASS (62.887 s): 179 tests, 53 pages, 10 sources/20 outputs and
51 routes/internal links. Staged new-path ownership PASS (76 tests). Final
precommit main remains `8126d401bae8681caca98af32594458edc4be9ba`; all applicable
governance and owning premises are unchanged. Three owning code/test files
are byte-identical to the original P1 head. No frozen path is included.
Current-head independent review remains pending until the new PR is reviewed.

## Authority and refreshed premises

- Integration main inspected at
  `fa1a402b0da4f043864b409d40e04e0821aefbf3`; actual stack parent is
  `0c36797f30e3b52923145bab7cc00d3f984bbc58`
  (`feat/creator-recording-pattern-switch`). The intervening #2376 is a
  separate Product allocation/snapshot, not an OFF implementation.
- Live #2234 remains OPEN with the approved current-loop example. Native
  `PatternSwitchSnap` still has only beat/bar/pattern_end. Existing
  `publish_pattern_view_preserving_phase` requires the same Pattern and
  geometry; it must not be relaxed into an unverified cross-Pattern path.
- Still outstanding: a checked, allocation-free mapping from actual source
  musical position to target loop position. Existing `TransportAnchor`,
  denominator and exact boundary projection are delivered; reuse them.
- C3 #2373 and C4 #2377 are Draft stack predecessors; recording selection and
  retained actual publication S are delivered there, not repeated here.
- Target-note chase is an unresolved product choice. P1 only maps position;
  it neither selects nor starts Voices. Further concurrency/consumer work
  must refresh and settle its applicable contracts before implementation.
- No OFF successor appears in the refreshed open PR inventory. The owner's
  explicit main freeze remains until an explicit unfreeze, independently of
  external release activity. Draft stack only; no merge or auto-merge.

## Implementation and declared files

One Conventional Commit: `feat(audio): match Pattern switch phase within source loop`.
Only these ten paths belong to P1:

- `docs/design/2026-10-19-seq-snap-off-phase-model.md`
- `docs/plans/2026-10-19-seq-snap-off-phase-anchor.md`
- `docs/plans/2026-10-10-pattern-switch-and-count-in.md`
- `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`
- `packages/audio-runtime/src/prepared_sample_bank.cpp`
- `tests/core/audio/prepared_sample_bank_test.cpp`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/diagrams/audio-runtime.architecture.json`
- `apps/docs-site/static/diagrams/audio-runtime.html`
- `apps/docs-site/static/diagrams/audio-runtime.svg`

`phase_matched_pattern_anchor(S, source_N, source_loop_ticks,
target_loop_ticks, target_bpm)` first reduces N within the source loop, then
within the target loop. It preserves actual S and the fractional numerator,
returns unavailable on invalid BPM/geometry/overflow, and constructs no
synthetic frame origin. No existing public object layout changes.

## Verification and acceptance boundary

Baseline: configure dev, build existing `lmdj_prepared_sample_bank_tests`, then
`ctest --test-dir build/core/dev -R '^audio\.prepared_sample_bank$'
--output-on-failure`: PASS before edits (4.97 s).

Lowest owning tier is the existing `audio.prepared_sample_bank` component
binary; no new binary, translation unit, registration or coverage inventory.
Keep all original calls. New fact-specific tests use literal expectations for
the approved second-loop example, shorter target, exact source-loop boundary,
fractional clock at 97 BPM, negative-synthetic-origin witness, maximum unsigned
input and invalid geometry. A rebuilt mutation removing the source-loop reduction must
fail the approved example; restore saved working bytes with a strictly newer
mtime, verify recompilation and rerun the complete owning selection.

Also run `bash scripts/verify-core-dependencies.sh`, official diagram rendering,
`scripts/docs-site.sh check`, `python3 tests/build/ci_change_scope_test.py`, and
PR body/declaration checks against the actual stack parent. Classification is
ownership evidence, not an executed full lane. No new required gate is added.

P1 PASS proves the arithmetic primitive only. Actual audio application and
retained nonzero anchor, successor/cancel/Stop/concurrency, recording/recovery,
Host/SDK, Creator preference/metronome and packaged audio/persistence journeys
remain UNRUN for OFF. Existing quantized switch behavior is not modified.
No full candidate, physical device, human audio or release acceptance is claimed.

## Executed results

- Initial implementation build and complete owning component PASS (5.10 s).
  Mutation omitting the source-loop reduction rebuilt the actual producer
  translation unit, then failed at the approved example's literal target
  anchor assertion (`prepared_sample_bank_test.cpp:541`, CTest exit 8).
  Saved working bytes restored identically with mtime strictly newer than the
  mutant object; the log confirms recompilation, build exit 0 and complete
  owning component PASS (4.90 s). Original tests remain selected.
- Vendored/offline Core dependency verification PASS. New-path scope suite
  before staging: 76 PASS; repeat against the staged and committed paths before
  commit/push. No new process pitfall: the product rule has a load-bearing
  regression test and existing saved-WIP/rebuild procedures were followed.
- Official diagrams regenerated; complete `scripts/docs-site.sh check` PASS:
  179 tests, production build and all 50 routes/internal links. No identity,
  manifest, versioned snapshot or other diagram changed.
- Pre-commit main refresh is still
  `fa1a402b0da4f043864b409d40e04e0821aefbf3`; governing files and owning Native
  source/tests have no intervening change. Live #2234 remains OPEN with no
  comments/successor PR; the only feature parents remain #2373 then #2377.
  An external CI PR does not change this Task's scope or the owner's freeze.

## Version Management

Version impact: Audio Runtime additive API MINOR debt, tracked in #2237. P1
adds a function without changing existing DTO/class layouts, persisted grammar,
Contract, manifest or Product identity. Later Native storage/layout changes
require their own ABI classification; private Engine storage can still be a
C++ ABI MAJOR change. No version or Build allocation in this Task.

## Documentation Impact

Documentation impact: required.
Affected portal pages: /core/modules/audio-runtime/

Update the current module page and official diagram to distinguish available
position arithmetic from still-unwired OFF publication. Preserve existing
S6/current clock claims, identity projection and immutable snapshots. No
Product/Assembly change and no permanent snapshot in this Task.

## Shipping boundary

Push only this Task branch and open a Draft PR targeting
`feat/creator-recording-pattern-switch`. Independent current-head review stays
PENDING during the Draft/non-main stack; this is not a waiver or review PASS.
After an explicit unfreeze, refresh applicable premises, review, conversations,
conflicts and live protection before any separately eligible integration.
No release, deployment, promotion or cleanup belongs to P1.
