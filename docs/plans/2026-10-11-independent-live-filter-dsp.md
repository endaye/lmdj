# F1 — 独立 LP/HP/BP、Cutoff、Resonance 的实时 DSP

## Task and approved result

This is Task F1 of
[Performance 实时控制 producer／consumer 计划](2026-10-11-performance-live-control-producers.md),
implementing exactly its F1 section: the audio-runtime typed independent
Filter branch (type LP/HP/BP, integer-Hz Cutoff 20–20 000, Resonance
0–1000 milli-percent), single Filter stage ownership, and the Filter state
needed for bounded master-control reservation/ACK. Product behavior follows
the approved
[D04 filter decision](../prd/decisions/2026-10-10-mixer-live-controls-and-meter.md)
and the
[D0 technical proposal](../prd/decisions/2026-10-11-performance-live-control-encoding.md);
the legacy 0–1000 scalar Filter path, its events and its PCM goldens are
unchanged. Mask-command audible effect is M1's scope and is not here.

Core DSP types (`FilterType` / `FilterParameters` in
`packages/audio-runtime/include/lmdj/audio/master_fx.hpp`) carry integer Hz
and milli-percent; Domain persisted types keep their own representation and
translate explicitly at the boundary (P0's scope). No Host Hz is swapped for
Sample Tone.

Within the D0 proposal's recommendations, this Task fixes:

- One second-order TPT SVF per channel; LP/HP/BP derive from the same state
  (LP = low integrator, HP = input − k·band − low, BP = k·band with
  k = 1/Q so BP is unity at the center frequency).
- Q = (1/√2)·(10·√2)^(r/1000): 0% is Butterworth (Q ≈ 0.7071), 100% is
  Q = 10. Coefficients use g = tan(π·fc/fs) at the engine's fixed 48 kHz;
  the 20 kHz boundary is not lowered.
- Coefficient (g, k) changes and the wet gate ramp over the shared 96-frame
  (2 ms) ramp length, with integer frame counters so full-on and full-off are
  bit-exact. OFF is a bit-identical bypass: once the wet ramp reaches zero,
  frames are never touched.
- engage switches mode, tuple and active state atomically and clears the
  legacy branch's engaged/frozen; a legacy `fx.filter` engage (and a legacy
  move while the independent branch owns the stage) takes over as legacy;
  a legacy release owns only the legacy gesture and cannot kill an
  independent gesture. move requires an engaged independent gesture; release
  freezes under HOLD or bypasses and retains the tuple for readback.

The engine extends the existing bounded 1024-entry master-control SPSC queue
with a `filter` control kind carrying the typed gesture and its accepted
sequence. The control-side accepted shadow and the audio-side applied
snapshot are separate: the shadow updates only after the queue accepts an
event (queue-full changes nothing and consumes no sequence), and the render
thread publishes the coherent applied `FilterLiveState` + sequence + engine
start epoch through a fixed three-slot value channel after any drain that can
change it. No render mutex, no audio-thread allocation, no unbounded retry,
no extra master output gain. `FxEnqueueResult` gains no enumerators, because
application-facade switches over it exhaustively; invalid tuples reuse
`invalid_value` (a release never inspects its tuple and is never rejected for
it). Typed and legacy events share the queue-occupancy counter and the
`queue_full` budget.

## Refreshed source premises (issue-done §0)

Integration base and worktree base: `deb95de722b845d708371e90bcac138ae5e25e01`
(fresh `origin/main` on 2026-10-11). Dispositions against that base:

- **Independent Filter producer outstanding — still outstanding.**
  `MasterFxChain::process_filter` at deb95de (master_fx.cpp) has only the
  0–1000 scalar / 500 bypass path; no type/cutoff/resonance input exists.
  `git log 4a2b26f..deb95de -- packages/audio-runtime tests/core/audio
  apps/docs-site/...audio-runtime...` is empty: no successor PR delivered any
  F1 scope. Old LP/HP PCM tests remain as positive controls and are retained
  unchanged.
- **Open PRs do not overlap the declared files.** Live file lists:
  PR #2001 (creator-web history navigation, 4 files), PR #2008
  (application-facade/web-runtime-platform, 4 files), PR #2010
  (creator-web portal + perform spec, 4 files). None touches
  `packages/audio-runtime`, `tests/core/audio` or the audio-runtime portal
  files.
- **All pre-existing declared files exist at deb95de** (verified with
  `git cat-file -e` per path). The only new file is this plan.
- **Sibling Task P0** (project-io/domain/cooker durable data) owns a disjoint
  file set; no coordination conflict.

## Declared files

1. `packages/audio-runtime/include/lmdj/audio/master_fx.hpp`
2. `packages/audio-runtime/src/master_fx.cpp`
3. `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
4. `packages/audio-runtime/src/realtime_engine.cpp`
5. `tests/core/audio/master_fx_test.cpp`
6. `tests/core/audio/master_fx_determinism_test.cpp`
7. `tests/core/audio/master_fx_allocation_guard_test.cpp`
8. `tests/core/audio/master_fx_stress_test.cpp`
9. `apps/docs-site/docs/core/modules/audio-runtime.mdx`
10. `docs/plans/2026-10-11-independent-live-filter-dsp.md` (new, this file)
11. `apps/docs-site/diagrams/audio-runtime.architecture.json`
12. `apps/docs-site/static/diagrams/audio-runtime.html`
13. `apps/docs-site/static/diagrams/audio-runtime.svg`

No CMake/test-registry entry is added: the four existing suites absorb the
new cases, per the program plan's minimization rule.

## Lowest-tier verification and acceptance

- `audio.master_fx`: default OFF is bit-identical bypass (including after a
  release's wet ramp); LP/HP/BP steady-state gains match the analytic
  warped-bilinear prototype (independent closed-form oracle, named blind
  spot recorded in the test) at 20 Hz / 1 kHz / 4 kHz / 10 kHz / 20 kHz and
  resonance 0 / 500 / 1000; single-parameter moves preserve the other two
  parameters and same-tuple moves preserve DSP continuity; extreme settings
  stay finite and decay under silence; legacy takeover and legacy-release
  ownership are locked; invalid tuples are refused without state change.
- `audio.master_fx_determinism`: one explicit integer control stream (typed
  engage/move/release plus legacy HOLD/takeover interleaved) is sample-
  identical across repeated runs in the chain and in the real engine; the
  coherent applied state through the engine equals the shared DSP's state;
  exact golden samples lock the stream's output.
- `audio.master_fx_allocation_guard`: all new parameter changes,
  HOLD/release/neutral render with zero allocations; invalid and
  out-of-range enqueues leave the accepted shadow untouched; applied catches
  up to accepted after the drain; the source scan keeps lock syntax out of
  the new code.
- `audio.master_fx_stress`: the three original scenarios and budgets are
  unchanged. New: deterministic queue-full rejection consumes no sequence and
  the next callback drains the full queue coherently; concurrent parameter
  churn (typed + legacy takeover/HOLD interleavings) stays finite and
  conserves accepted/dequeued/applied; engine restart yields a new epoch
  whose applied snapshot is the default independent OFF, so a stale ACK is
  distinguishable by epoch and content.
- Adjacent old-behavior guards: `scripts/core.sh test dev fast` (all unit
  and component tiers, including `audio.realtime_engine` and the facade
  Performance suites) and `scripts/core.sh test dev stress` run the stress
  tier explicitly.
- `scripts/docs-site.sh check` for the portal page and regenerated diagrams.

## Version Management

Version impact: audio-runtime ABI MAJOR debt — the public `MasterFxTelemetry`
grows two counters, new public Filter types and engine methods are added, and
private `RealtimeEngine`/`MasterFxChain` layouts grow. The legacy Filter
branch and its golden vectors are unchanged. No Project Contract, Host,
Assembly or Product Build change; no version number is allocated here.
Inspected audio-runtime manifest identity at the base is 5.2.0 / api 2; exact
settlement belongs to the program's V1 Task.

## Documentation Impact

Documentation impact: required — `/core/modules/audio-runtime/`. The current
page and the audio-runtime source diagram plus its generated HTML/SVG are
updated in this same Task; `scripts/docs-site.sh check` runs before commit.

## Pitfall Impact

Pitfall impact: none recorded. The parity-test oracle discipline
(independent analytic oracle beside the engine/chain agreement) follows the
existing `parity-check-between-agreeing-copies` entry; no new recurrence.
`FxEnqueueResult` could not gain a typed-filter enumerator because
application-facade's exhaustive switch is outside this Task's declared files;
that coupling is visible in code and needs no ledger entry.

## Progress

Implementation complete on `feat/independent-live-filter-dsp`. Verification
on the final tree (dev build, arm64 macOS):

- `ctest -R 'audio\.master_fx'`: all four owning suites pass
  (`audio.master_fx` 2.3 s, `audio.master_fx_determinism` 1.0 s,
  `audio.master_fx_allocation_guard` 0.9 s, `audio.master_fx_stress` 4.4 s).
- `ctest -R 'audio\.(master_fx|realtime_engine|offline_renderer|voice_dsp|value_channel|realtime_queue|prepared_sample_bank|snapshot_publication)'`:
  14/14 adjacent audio suites pass, including the legacy LP/HP PCM positive
  controls.
- `scripts/core.sh test dev fast`: exit 0 (207/207 tests on the final tree).
- `scripts/core.sh test dev stress`: exit 0 (15/15 stress tests on the final
  tree); original `master_fx_stress` scenarios and budgets unchanged, with
  the new churn / queue-rejection / epoch cases added.
- Analytic-oracle margin: worst measured/prototype deviation across all 19
  response cases is ~7e-6 against a ≥2e-3 tolerance (err/tol ≤ 0.0007).
- Mutation proof: removing the BP unity scaling (`selected = k * v1` →
  `v1`) fails `audio.master_fx` inside
  `independent_filter_response_matches_the_analytic_prototype` and fails
  `audio.master_fx_determinism` at the BP-region golden, while the
  chain/engine parity agreement alone stays green under the shared defect —
  the exact blind spot the analytic oracle and goldens exist to cover.
  Fixed-tree restore rebuilt and re-passed all four suites.
- `scripts/docs-site.sh check`: exit 0 (50 routes, page/diagram validation,
  production build); diagrams regenerated with `npm run diagrams`
  (source sha256 20f1d4f5…6362 embedded in both outputs).

One process incident during implementation, retained for honesty: a mutation
proof initially restored `master_fx.cpp` with `git checkout --`, which
reverted the still-uncommitted implementation instead of the mutation. The
file was reconstructed from the recorded edits; the rebuilt fixed source
reproduced every previously locked golden sample bit-for-bit before the
mutation proof was redone with a byte-level backup.

Follow-up fix commit on the same branch (independent audit of the F1 head):
the churn stress test's renderer is now rendezvous-bounded (`control_round`),
so it cannot exit before the round-100 pause handshake — the pre-fix hang was
reproduced with a diagnostic 500 ms control-thread slowdown (bounded 60 s
wait killed it) and the same slowdown completes in 4.8 s on the fixed tree;
and the block tail clamp now runs only when a whole-block effect processed,
with the independent branch clamping exactly the frames it processed — a
release settling mid-block leaves settled dry frames bit-identical on any
block split (permanent regression test
`independent_release_settling_never_clamps_settled_dry_frames`, red on the
pre-fix head at master_fx_test.cpp:977). The BP mutation proof was redone
against the fixed code with a byte-level backup: the same two suites fail,
the restore rebuilds and passes.
