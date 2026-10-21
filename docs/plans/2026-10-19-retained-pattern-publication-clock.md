# Retained actual Pattern publication clock (S5 P2)

Parent: #2112 / #2234. One Native producer Task above Draft #2378, before OFF
publication and recording consumers. The target-note chase question remains
pending; this Task retains existing publication facts and chooses no new Voice
or cross-Pattern concurrency semantics.

## Current main integration (2026-10-20)

This section supersedes the historical Draft-only shipping hold below for P2.
Owner partial unfreeze permits ordinary features/fixes/tests after Task proof,
independent current-head review, full conversations/conflicts and live protection.
The candidate remains fixed at `8c361623f`; `.github/workflows/`,
`tools/release/`, `scripts/release.sh`, `scripts/cloudflare-host-deploy.sh`,
`docs/release-evidence/` and `apps/docs-site/docs/releases/` remain frozen.
None belongs to these ten declared P2 paths. No release/deployment/Channel or
agent Git cleanup is included, and COUNT-IN UI remains withdrawn.

Isolated branch `feat/retained-pattern-clock-main` starts at refreshed main
`7bc7cd4fe551b19bf35e1300ffb14482eccd0e11`. P1 is actually delivered by #2427
at that revision, so do not repeat its arithmetic. Original P2 #2379 remains
on its published branch while this exact layer is independently integrated;
no force push or published-history rewrite. Creator C4 and COUNT-IN are not
P2 dependencies. The four owning Engine/header/component/stress files are
byte-identical to #2379's original parent. Existing retained disposition/S and
current-only tempo queries are present; per-publication historical N/geometry
are absent at the authoritative declarations, definitions and tests. Live
#2234 remains OPEN with no new product decision or successor implementation.
The remaining current Draft inventory has no second implementation of P2.

Baseline before edits: configure/build PASS; complete owning component 1.98 s
and stress 1.75 s PASS (3.74 s CTest total). Integrate exactly the ten declared
files below; keep all original journeys, budgets and 1000-iteration history
checks. Repeat the actual producer mutation/restoration, complete owning dev
and TSan selections, dependency and complete Portal checks, staged/committed
ownership and exact-body declarations. No new binary/TU/workflow/gate or
capacity/timeout change. Preserve full OFF/recording/restart/Host/Creator,
#1973, candidate/device/listening and Voice-chase acceptance as outstanding.
P2's concrete Engine storage is ABI MAJOR debt in #2237; integrating source
neither allocates identities nor lowers that debt.

Integration execution receipts: fixed complete dev component/stress PASS
(5.409 s process total). Store zero for the actual retained numerator, rebuild
ordinary/testable producers, and both original selections fail their independent
literal assertions (`realtime_engine_test.cpp:8403` and stress line1065; CTest
exit8). Restore byte-identical working bytes with fresh mtime and confirm both
producers recompile; complete component/stress PASS (1.84 s /1.63 s). Core
dependencies PASS. Complete TSan component/stress PASS (14.21 s /20.97 s),
actual Engine/stress flags include `-fsanitize=thread`, no TSAN_OPTIONS override
and no race diagnostic. Complete Portal PASS: 179 tests, 53 pages, 10 sources/
20 outputs, 51 routes/internal links; official diagrams regenerated. Four owning
code/test files are byte-identical to original P2. Precommit main remains
`7bc7cd4fe551b19bf35e1300ffb14482eccd0e11`; governing and owning premises
unchanged. Staged new-path ownership PASS (76 tests); body lint and required
Portal-route declaration PASS. Committed ownership/scope and independent
current-head review remain shipping prerequisites. No process pitfall recurrence: product
metadata lifetime is covered by these tests and established proof procedures
were followed without a new mechanism or relaxed budget.

## Refreshed authority and premises

- Integration main: `fa1a402b0da4f043864b409d40e04e0821aefbf3`.
  Actual parent: `e454d909169262737d38e5cd132ccabf2007ef2e`
  (`feat/snap-off-phase-anchor`). Governing files and owning Engine/component/
  stress sources are byte-identical to current main. P1's phase helper is
  delivered on the stack; do not repeat it.
- Live #2234 remains OPEN; no comments or successor implementation in the
  refreshed open PR inventory. The feature stack is #2373 → #2377 → #2378.
  External release/CI work is outside this Task, and cannot end the freeze.
- Delivered C1: a move-only serialized-control lease pins the immutable slot
  before publication. Generation-tagged actual S is written before the slot's
  acquire/release state transition and survives successor/reclaim until reset.
- Outstanding: old `observe_pattern_publication` exposes only actual frame.
  `pattern_tempo_observation` is current-only and cannot prove a historical
  nonzero position after the next generation applies. Recording OFF needs
  actual S plus its historical numerator/BPM/geometry, never delayed inspect.
- Existing same-Pattern phase publication already has exact generation,
  Project/Pattern/BPM/PPQ/loop and pending/transport guards. Reuse them through
  an opt-in retained entry point; do not loosen or replace the old API.

## Implementation and declared files

One Conventional Commit: `feat(audio): retain actual Pattern publication clocks`.
Only these ten paths belong to P2:

- `docs/plans/2026-10-19-retained-pattern-publication-clock.md`
- `docs/design/2026-10-19-seq-snap-off-phase-model.md`
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- `tests/core/audio/realtime_engine_stress_test.cpp`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/diagrams/audio-runtime.architecture.json`
- `apps/docs-site/static/diagrams/audio-runtime.html`
- `apps/docs-site/static/diagrams/audio-runtime.svg`

Add a companion `PatternPublicationClockObservation` containing the unchanged
publication observation, immutable PPQ/loop geometry and optional actual anchor.
`observe_pattern_publication_clock(lease)` uses the existing acquire state/pin;
pending/cancelled has no anchor. Applied with unrepresentable position retains
its real applied frame/disposition but has no anchor, rather than inventing N=0.
Empty/moved/foreign leases remain unavailable.

Audio writes a fixed per-slot optional numerator before publishing the
applied state. Combine it with already-retained actual S and immutable view
BPM/geometry, without duplicating that storage. It is immutable for that
generation under its control pin; no
audio allocation, owner destruction, new atomic protocol or delayed current
clock read. Retain the exact cumulative numerator, not a loop-local reduction;
OFF mapping belongs to P1's distinct helper at the future actual apply point.

Add `publish_retained_pattern_view_preserving_phase(view, expected_generation)`
as the opt-in route to retain existing nonzero phase publications. Require a
running Engine like the retained selected-switch API and forward through the
same admission/pin rollback. Refused material remains available to its caller.
No retained tempo-preview lifecycle, cross-Pattern OFF mode, Host/SDK/Creator,
Journal or recording consumer is implemented here.

## Verification and far-side evidence

Baseline dev configure/build and the complete existing `audio.realtime_engine`
and `audio.realtime_spsc_stress` selections PASS (1.29 s / 1.57 s).

Lowest owning component: `lmdj_realtime_engine_tests`. Preserve all original
cases/budgets. Assert independent literal nonzero frame/numerator after an
existing 120→97 BPM transition and retained phase application, then after a
different-length/BPM successor, reclaim and Stop. Cover real S versus overdue
activation prediction, pending/cancelled/foreign/moved/reset, missing phase and
the new entry point's existing guards. Callback allocation tracking remains.

Owning stress: `lmdj_realtime_engine_stress_tests` / `audio.realtime_spsc_stress`.
Keep the original 48 retained switch/cancel/reclaim cases and all other stress
journeys, adding anchor assertions. Add a retained phase/render/reclaim loop
with an independent literal 97 BPM rounded-loop position oracle and retained
history checks. Run this complete owning binary in dev and TSan; a signal or
unavailable instrument is not PASS and must be resolved/reported explicitly.
No new binary, TU, registration, coverage inventory or relaxed budget.

Rebuilt mutation replacing the retained nonzero numerator with zero must fail
the literal component assertion. Save working bytes, restore with mtime
strictly newer than mutant objects, confirm actual compilation and rerun the
entire owning component/stress selection. Also run Core dependencies, official
diagram generation, complete `scripts/docs-site.sh check`, staged/committed
`ci_change_scope_test.py`, and final PR body/declaration checks against #2378.
Classification is ownership only, not executed full lanes or release evidence.

OFF application, predecessor/later-SNAP behavior, durable segment/restart,
Host/SDK and packaged current/queued/audio/persistence acceptance remain open.
Full candidate, other platforms, device and listening acceptance remain separate.
Those are future implementation scopes, not substitute verification for this
Task's actual lock-free metadata lifetime, which retains its owning stress/TSan.

## Executed results

- Complete owning dev component/stress PASS after implementation (1.51 s /
  1.56 s). The zero-numerator mutation rebuilt both ordinary and testable
  Engine translation units and failed the independent
  `{20, 2237760, 97}` assertion at `realtime_engine_test.cpp:8403` (CTest exit 8).
  Saved working bytes restored identically with a strictly newer mtime; both
  producer builds exit 0 and explicitly recompile. Complete restored owning
  component/stress PASS (1.30 s / 1.56 s).
- TSan configure/build and complete owning component/stress PASS (12.00 s /
  17.61 s), no reported race. Ordinary Engine and stress compile flags include
  `-fsanitize=thread`; no ambient `TSAN_OPTIONS` override. This runs the added
  1000 phase publications, original 48 switch/cancel/reclaim cases and every
  original binary journey, with the callback allocator boundary intact.
- Core dependency verification PASS; complete Portal PASS: 179 tests,
  production build and 50 routes/internal links, with official diagrams.
  Pre-staging ownership suite: 76 PASS; staged and committed new-path checks
  remain shipping prerequisites. Relative Task/design links PASS.
- Pre-commit refresh remains main
  `fa1a402b0da4f043864b409d40e04e0821aefbf3`; governing and owning sources have
  no intervening changes. Live #2234 OPEN, no comments/successor; #2378 remains
  the Draft parent above #2377 and #2373. Freeze remains explicit.
- Final pre-commit refresh: main
  `2f01cc8f707e7211d27ddb28674ca4e663276800` adds external CI host network
  admission #2375 only. AGENTS, issue-done, Git workflow and all owning
  Engine/component/stress sources are unchanged; its test-policy addition
  concerns overflow-runner host admission, not Task verification. All P2
  premises remain. No rebase or repeat product implementation is needed;
  this external merge does not authorize merging the frozen feature stack.
- Pitfall impact: none. Metadata lifetime and arithmetic are derivable from
  source and owning regressions. Existing saved-WIP/rebuild and stress/TSan
  procedures were followed; no new process mechanism or gate.

## Version Management

Version impact: Audio Runtime C++ ABI MAJOR debt in #2237: per-slot anchor
storage enlarges the public concrete `RealtimeEngine`, even though private.
The added DTO/functions are additive API, but do not reduce that MAJOR impact.
Old publication DTOs/vtable and wire/Journal grammar stay unchanged. Later
version settlement deduplicates the actual compatibility domain against already
settled and pending sources; no guessed version, manifest or Build allocation.

## Documentation Impact

Documentation impact: required.
Affected portal pages: /core/modules/audio-runtime/

Update current applied-clock ownership and the existing lease diagram, keeping
OFF product wiring explicitly outstanding. Use only official HTML/SVG outputs;
no immutable snapshot, Product identity or other diagram change.

## Shipping boundary

Push only this short-lived branch; Draft PR base
`feat/snap-off-phase-anchor`. Main is frozen until explicit owner unfreeze.
No merge/auto-merge, release, deployment, Channel or cleanup. Independent
current-head review stays PENDING for this Draft/non-main stack; no waiver or
review PASS. After unfreeze, refresh premises and normal exact-head review,
findings/conversations/conflicts/live protection before eligible integration.
