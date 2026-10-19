# I2b B1: Pattern tempo publication gateway

## Refreshed premises before product edits

Fresh main is `1c4462aa8436f81da1db2a9e6420d94f0e84ccb4`. This isolated
`feat/pattern-tempo-publication-gateway` Task starts at frozen Draft #2414 /
`b05a11ad8b1c360cb86a0d3d474da392259f01ea`. All23 open PRs are Draft with
no auto-merge; live #2235/#2236/#1973 have no successor delivering preview.
Main remains frozen; no merge, release/tag/deployment/Channel or Git cleanup.

The approved2026-10-10 decision requires continuous audible tempo, exact
musical position, retained voices,400ms single authoring commit and genuine
cancel/ownership resolution. This Task does not revise that behavior.

| Premise | Evidence-backed disposition |
| --- | --- |
| Native continuous timing must be implemented again | Delivered by merged #2155. `with_tempo`, `publish_pattern_tempo_transition`, `pattern_tempo_observation` and exact cutoff anchors exist. Retain their same-BPM rejection and native onset/stress checks. |
| The current product already performs reversible preview | Outstanding. Creator keeps a local `tempoPreview`; App's400ms callback calls only durable settings. Complete Facade dispatch, Web registration/control and SDK public object have no preview lifecycle. No current product caller consumes I2a's tempo primitive. |
| Any newly cooked snapshot can stand in for the current source | False. Native tempo transition requires the same event/playback/immutable PCM identity except derived timing. The caller must retain its original prepared source and derive detents/cancel values from it. Recooking by Project ID alone does not prove material ownership. |
| Publication admission proves its actual clock | False. Only the audio-applied observation supplies actual frame/anchor. Native generation plus engine start epoch bind one source; pending, stale, restarted or stopped ownership cannot produce a fabricated applied result. |
| Existing settings publication can commit without a tempo dip | Outstanding. The Web settings path normally republishes a Project Pattern. Preview commit needs same-BPM revision adoption after the durable command, retaining the current continuous anchor and voices. |
| #1973 is closed by exposing a clock | False. Keep the fractional legacy Bar issue OPEN. This gateway forwards exact native anchors unchanged; later metronome/record consumers must prove their actual boundary algorithms and noninteger-BPM oracles. |

## Full delivery map, not a reduced outcome

| Task | Owns the obligation | Required far-side evidence |
| --- | --- | --- |
| B1, this Task | Typed Core engine gateway: retained prepared-source tempo publication, same-BPM committed revision adoption, actual applied clock and explicit native refusal | Real engine onset/anchor/cancel/adoption/voices/source/epoch/pending/refusal and concurrent render/reclaim, including TSan |
| B2 | Facade Project/Pattern/revision/preview identity, latest committed cancel target, one durable commit and committed-but-pending adoption, recording/replay/source interlocks and owner disposal | Complete Truth/revision/history, every set/cancel/commit/refusal/reopen leg, genuine UNKNOWN/late result retention; actual Web storage leg when the new path writes |
| B3 | Web bridge registration, Control adapter, protocol validation, typed SDK and actual clock payload; prepare/retain source in every affected product publication path | Real Wasm/AudioWorklet onset before/during/cancel/second preview/commit; strict wire/source/owner/late/terminal cases; no raw private protocol bypass |
| I2c/#2236 | Creator400ms encoder queue, every approved cancellation, actual anchor in metronome/S7 handoff | Complete input/onset/cancel/commit/Undo/reopen journey and all original budgets/legs; physical listening separately |

B2/B3 must declare exact current files and operation/payload/response shapes
before their implementation edits. Their obligations are not marked unchanged
or complete by this split. B1 creates no Web endpoint, numeric-only UI or
second clock. Native Hosts gain no claimed preview feature merely because a
reusable Core gateway exists. #2235 and the full #2112 scope stay open.

## One Task / declared files

1. `packages/application-facade/include/lmdj/facade/pattern_tempo_gateway.hpp`
2. `packages/application-facade/src/pattern_tempo_gateway.cpp`
3. `packages/application-facade/CMakeLists.txt`
4. `tests/core/facade/pattern_tempo_gateway_test.cpp`
5. `CMakeLists.txt`
6. `docs/plans/2026-10-20-pattern-tempo-publication-gateway.md`
7. `apps/docs-site/docs/core/modules/application-facade.mdx`
8. `apps/docs-site/diagrams/application-facade.architecture.json`
9. `apps/docs-site/static/diagrams/application-facade.html`
10. `apps/docs-site/static/diagrams/application-facade.svg`

Expand before editing another path. Root is the sole writer; heavy native,
sanitizer, Portal and browser windows run serially on owned processes.

## Public C++ interface and invariants

Add `PatternTempoAuthority {start_epoch, generation}` and a separate additive
`PatternTempoPublicationGateway` with three control-thread callbacks:

- `publish(const audio::PreparedPatternView&, uint16_t bpm, authority)` derives
  via the existing `with_tempo`, checks actual source authority and calls only
  the existing tempo transition. The retained source is never consumed.
- `adopt(audio::PreparedPatternView&&, authority)` calls only the existing
  same-BPM phase-preserving publication. It is for later committed revision
  adoption, not authoring or restoring a prior BPM. Refusals consume no view.
- `observe(authority)` returns an optional actual `PatternTempoObservation`.
  Match native generation and engine start epoch; stopped engine or unavailable
  audio evidence is null, never a predicted frame or default-zero anchor.

`make_engine_pattern_tempo_publication_gateway(RealtimeEngine&)` binds them to
one existing engine. Engine outlives the gateway; all calls and destruction
are serialized control operations, concurrent only with render. The caller
owns source preparation, preview identity/Project policy and lifecycle. No
new callback queue, shared shadow, timer, render allocation, lock or source
parser is introduced. Reclaim remains control-side. A successful Result means
native admission only; actual apply must still be observed. Map native
publication refusals to closed reason strings without auto-retry, suppressing
the refusal, consuming a generation on a failed precondition, or clearing a
previous publication.

## Verification / owning defects

- Before product edits, configure stable dev and run the existing prepared
  sample-bank, realtime-engine and Facade performance-engine-adapter baseline.
- New real-engine component registration: independent literal120→240 at real
  F12001 keeps N1382515200 and next beat onset18001; cancellation/deceleration,
  fractional97BPM, full numerator, pending versus actual apply, same-BPM
  revision adoption without revert, held voices, original source reuse,
  changed material/source/stale generation/epoch, stopped/restarted and native
  pending/refusal behavior. Observe PCM/actual source, not only returned BPM.
- Semantic perturbation must rebuild and fail in the owning actual onset or
  source/epoch assertion. Snapshot dirty working bytes, restore exact bytes
  with fresh mtime newer than mutant artifacts, confirm compilation and exit.
- Register a distinct stress invocation for concurrent control publication/
  observation/reclaim versus render. Assert accepted and refused outcomes
  actually occur. Run it under dev and TSan; retain native I2a SPSC stress.
  No sleeps-as-progress, enlarged budget or omitted original cases.
- Existing baseline registrations remain selected after changes. Core
  dependencies, full owning Portal/official diagram, staged/committed new-path
  ownership and exact parent/body declaration pass before Draft publication.
- B1 does not claim Facade Project history, Web wire/OPFS, Wasm product onset,
  Creator metronome or device acceptance. B2/B3/I2c must execute those named
  legs; a native gateway is not substitute evidence for them.

## Version Management

Version impact: compatible Application Facade C++ API MINOR debt. New separate
types/factory only; existing ApplicationConfig, EnginePerformanceAdapter,
PatternPublicationGateway and RealtimeEngine layouts/vtables stay unchanged.
Record actual impact under #2237 without lowering higher existing debt. No
manifest, Product/Assembly/Build/snapshot allocation, persisted Contract or C
ABI change. B2 must reassess any actual configuration/layout changes.

## Documentation Impact

Documentation impact: required — `/core/modules/application-facade/`, its
source diagram and official generated HTML/SVG. Document the exact reusable
gateway and explicit unimplemented product lifecycle; no new dependency edge
or manually entered identity. Run the complete Portal check.

## Shipping boundary

One reviewable Conventional Commit, push and Draft successor of #2414 after
owning verification. Refresh main and successors before publication.
Independent current-head review remains explicit; no self-waiver. No merge,
auto-merge, release/tag/publication/deployment/Channel or Git cleanup until
owner authorizes the applicable transition. No B1 result closes #2235/#2112.

## Verification record

- Baseline configure/build and four owning registrations passed before product
  edits. The initial new-target invocation preceded CMake regeneration and
  therefore found no target; after registration, fixture type/include and
  testable-library linkage errors were corrected. No compiler failure is
  counted as a semantic negative proof.
- New component contains ten isolated real-engine cases. The first run exposed
  an incorrect test expectation: same-BPM revision adoption retains the prior
  tempo anchor at F12001, with its own actual applied frame F20000. Corrected
  that oracle to the existing Native contract while retaining literal real
  onsets at F30001/F42001 and stale revision refusal. The complete six-item dev
  selection then passed, including both new registrations and all four baseline
  registrations.
- Semantic mutation ignored the requested240BPM while keeping a valid source
  and publication. Its rebuild passed; the component failed at the expected
  real F18001 onset assertion, not at compile/link or a telemetry-only check.
  Exact working source SHA-256
  `d7d27dae2cbdc9af83b82d6c32c782e33a435354bbbe68038019e2e84e19bdda`
  was restored with mtime strictly newer than mutant artifacts. The rebuild
  explicitly recompiled the source, relinked the new and original adapter
  targets, and all six dev registrations passed again.
- Native TSan instrumentation was verified on gateway, test and Engine compile
  flags, with no ambient TSan/DYLD override. All three selected registrations
  passed: new component, new stress and original SPSC stress. New stress
  actually observed256 accepted/256 refused publications and256 render
  callbacks under TSan; no suppression, sleeps-as-progress or budget change.
- Core dependency verification passed. Portal, staged ownership and publication
  receipts are recorded in the Pull Request after their actual completion.
- Precommit live refresh retained main
  `1c4462aa8436f81da1db2a9e6420d94f0e84ccb4`, parent #2414 at
  `b05a11ad8b1c360cb86a0d3d474da392259f01ea`, all23 Draft/no-auto-merge
  layers, and no tempo/BPM successor. B2/B3/I2c remain substantive outstanding
  development and acceptance work.
