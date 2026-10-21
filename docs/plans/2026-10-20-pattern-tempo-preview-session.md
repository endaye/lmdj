# I2b B2: Facade-owned Pattern tempo preview session

## Current main integration (2026-10-21)

The owner authorizes integration of the 19 open PRs under #2112. This section
supersedes historical Draft/freeze wording below. Refreshed base is
`7910ee1db67537a751c0668de97c14b35b53b5c2`: B1 is delivered by #2444, with
all ten tested blobs verified after squash. The complete current Facade source
still has no bind/preview Application lifecycle; live #2235 and #2416 retain
this distinct B2 obligation. Native timing and B1 are reused, not repeated.

Preserve original published head `57c6d47a44908aefd80a983edea3062d586ceac8`
through a normal main merge. Resolve to current main plus only this Task's
original 19 changed paths; all original patches apply cleanly. Preserve all
unrelated main paths and the withdrawn COUNT-IN consumer. No Creator layout
or B3 wire/AudioWorklet implementation is imported.

Rebuild and run the complete original nine-item dev and nine-item TSan
selections, including all existing stress registrations; inspect actual
sanitizer flags. Build the official pinned Wasm Project I/O artifact and run
the original history plus both B2 save/reopen and save/Undo/reopen journeys
on Chromium and isolated OPFS WebKit, with full Truth/Artifact/physical-close
assertions and unchanged budgets. Preserve original negative evidence and
every acceptance leg. Verify dependencies, official diagrams, full Portal,
staged/committed ownership and exact range/body declarations.

Version impact remains Facade C++ MINOR debt in #2237; Documentation impact
remains required for /core/modules/application-facade/ and its diagram.
Independent exact-head review and live protection/conversation/conflict checks
precede guarded squash. B3, Creator, full candidate and device/hearing proof
remain separate; no release, deployment, Channel or cleanup is included.

## Refreshed premises

Fresh main is `1c4462aa8436f81da1db2a9e6420d94f0e84ccb4`. This isolated
`feat/pattern-tempo-preview-session` worktree starts at Draft #2415,
`bc60f952614faf9df89b87370aa894cf32e25359`. Live #2235 and its comments,
the approved 2026-10-10 decision, complete Application dispatch, settings,
history, Sequence/Performance ownership and transport factories were inspected.
All24 open Pull Requests are Draft/no-auto-merge; only #2415 supplies a tempo
gateway. Main's intervening release/COUNT-IN changes deliver no preview session.

| Premise | Disposition before product edits |
| --- | --- |
| Native timing/gateway missing | Already delivered by #2155 and Draft #2415. Reuse them; do not change the same-BPM phase-edit constraint. |
| Application owns reversible preview | Still outstanding. Existing settings writes Truth first and has no retained preview/source/terminal identity. |
| Existing save can be reused with ordinary Web republication | False. That can revert/restart the audible preview. Commit must retain its exact command and adopt committed revision at the audible BPM. |
| Cancellation can forget an admitted preview | False. Wait for actual apply, then restore latest committed Truth and observe actual restoration. Admission is not completion. |
| Native-only storage evidence suffices | False. This Task adds an actual durable command path; own the real OPFS journey in this Task. |
| B2 alone delivers product preview | False. B3 still owns actual Bridge/control/protocol/SDK source retention and Wasm/AudioWorklet producer journeys; #2236 owns Creator400ms/cancellations/metronome/S7. |

## Full outcome and responsibility

Implement the approved continuous audible preview, no preview persistence,
one settled save/Undo, return-to-base without save, latest-Truth cancellation,
and no cancellation of an already-issued durable command. The controller must
retain commit identity and honest UNKNOWN/committed-but-pending outcomes.
Recording/replay and foreign source ownership must not reuse an old preview.

This Task owns the typed Application lifecycle and actual durable/history path,
including Facade-vended transport interlocks. B3 owns every Web source-publication
path, JSON registration/strict validation/SDK and actual Worklet onset journeys.
I2c owns every approved UI cancellation and the same-anchor metronome consumer.
No obligation is removed by the split. #1973 fractional legacy Bar and physical
acceptance remain independent; a new readable anchor does not settle either.

## Declared files

1. `packages/application-facade/include/lmdj/facade/pattern_tempo_preview.hpp`
2. `packages/application-facade/src/pattern_tempo_preview.hpp`
3. `packages/application-facade/src/pattern_tempo_preview.cpp`
4. `packages/application-facade/include/lmdj/facade/application.hpp`
5. `packages/application-facade/src/application.cpp`
6. `packages/application-facade/internal/lmdj/facade/pattern_transport_controller_factory.hpp`
7. `packages/application-facade/src/pattern_transport_controller_factory.cpp`
8. `packages/application-facade/CMakeLists.txt`
9. `CMakeLists.txt`
10. `tests/core/facade/pattern_tempo_preview_test.cpp`
11. `tests/platform/web/project_io/CMakeLists.txt` — inspected for linkage;
    its existing `lmdj::application` link already includes the new source, so no
    CMake edit is needed for this obligation. The actual Web action/spec below
    remain required and are implemented in this Task.
12. `tests/platform/web/project_io/project_io_web_test.cpp`
13. `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
14. `docs/plans/2026-10-20-pattern-tempo-preview-session.md`
15. `apps/docs-site/docs/core/modules/application-facade.mdx`
16. `apps/docs-site/diagrams/application-facade.architecture.json`
17. `apps/docs-site/static/diagrams/application-facade.html`
18. `apps/docs-site/static/diagrams/application-facade.svg`
19. `packages/application-facade/internal/lmdj/facade/mutation_publish_scope.hpp`
20. `packages/application-facade/src/mutation_publish_scope.cpp`

Pre-edit scope refinement: a first-attempt known refusal must not become a
permanent UNKNOWN merely because Store returned an error; nor may a same-revision
foreign Project replace the save target. Hold shared AuthoringHistory then the
exact platform's bundle writer across fresh identity/revision inspection and
execute. Add a private publication observer that delegates every existing outer
publish token callback. A first failed call with no accepted manifest claim is
a known refusal and retains no frozen command; a claimed attempt or previously
unknown command keeps UNKNOWN until exact reconciliation. No error-code heuristic
or override of the Host's cancellation/publish protection is allowed.

Expand this table before another path is edited. Root is sole writer. Native,
TSan, Wasm/browser and Portal heavy verification windows run serially.

## Typed API frozen before implementation

New separate header/types; existing config/public aggregate layouts stay intact.
One source per Application, bound to an exact normalized bundle/Project/Pattern/
revision, engine start epoch, generation and retained original prepared view.
The engine outlives its active binding, and all new calls share the engine
and transport controller's serialized control owner, concurrent only with render.
Core issues nonzero monotone source and preview IDs, scoped to that Application;
zero preview ID starts a new turn, never retargets a previous one.

- `bind_pattern_tempo_source(request, const PreparedPatternView&, RealtimeEngine&)`
  validates actual source and committed identity, retains a tempo-derived copy,
  and returns ready status. A second binding requires release of the first.
- `preview_pattern_tempo({source_id, preview_id, bpm})` validates40..240 and
  current Truth/record/replay ownership, then publishes through B1. Pending
  set refuses another detent; the consumer must preserve/coalesce its input.
- `cancel_pattern_tempo_preview({source_id, preview_id})` records cancellation,
  waits for an admitted preview's real apply, restores the latest committed BPM
  from the retained source, then adopts a changed committed revision if needed.
  Completion requires actual restoration/adoption, never merely enqueue success.
- `commit_pattern_tempo_preview({source_id, preview_id, CommandMeta})` freezes
  the exact existing UpdateSequenceSettings command, seals the history action,
  executes once, and retains uncertain failure for exact retry only. Successful
  persistence is retained while audio applies preview and same-BPM adoption.
  Cancel after issuance never rolls back or relabels that command as cancelled.
- `service_pattern_tempo_preview(source_id)` advances actual apply/terminal
  work and returns a status containing phase, IDs, committed/preview BPM,
  Project revision, optional exact committed revision/command, actual Native
  clock and optional real failure. No fabricated frame or numeric-only success.
- `release_pattern_tempo_source(source_id)` requests/settles graceful cancel or
  committed adoption before releasing; UNKNOWN is retained. Proven foreign
  generation/epoch loss retires old identity without publishing into its owner.
  Terminal Application destruction requires Host-established render quiescence
  per the existing Native stop/clear contract, and clears only an engine
  publication it still owns. Native stop is not a callback gate. Normal graceful
  release settles concurrently with render and permits later Application
  destruction without an Engine lifecycle call. B3 must use the Host's actual
  callback gate for terminal disposal; no pending preview may survive it.

Source/preview identity and stale calls are checked before publication or I/O.
Return-to-base never writes. Failed publication retains source/turn; no blind
retry of Native publication_pending. New service calls can make an explicit
retry only after observing the previous admitted generation's actual apply.
An exact coherent Native owner observation can also prove an admitted
publication was withdrawn before apply: the current generation is its known
predecessor and its generation is absent from both pending cells and the
retained cancellation cell. This produces `preview_refused` plus the actual
`tempo_publication_unapplied` failure, with no automatic detent retry; explicit
set/cancel or the frozen commit still resolves the turn. Already-issued commit
or cancel settlement continues from actual current timing. Unavailable reads
are never treated as withdrawal or owner loss. This proves non-application,
not its particular cause; the reason does not assert why Native retired it.
First-attempt failure before any accepted manifest claim is a known refusal.
Failure after an accepted claim, or any previously unknown command, is UNKNOWN
until exact reconciliation; a later preflight failure cannot erase that identity.
Changed command ID/payload and cancel do not erase it. Authoring/history,
record/replay and vended transport opening cannot cross unsettled preview.

The B3 wire family is reserved as `pattern.tempo.preview.set`, `.cancel`,
`.commit`, `.status`; its complete payload/response validation and registration
must be declared in B3 before edits. B2 adds no private wire bypass or endpoint.
Bindings are Host-owned control setup, not user-supplied Project bundle parsing.

## Verification and far-side evidence

- Baseline original Facade Sequence rebase, vended Pattern transport and B1
  gateway component/stress before product edits.
- Dedicated native executable with named groups instead of growing the existing
  near-budget Sequence surface shard. Use actual Application, shared history,
  real Engine/PCM and file-backed Store. Assert independent onset frames,
  complete Truth/revision/history after preview/cancel/second preview/one
  commit/Undo/reopen; complete Artifact identity where a fixture has audio.
- Pending preview/cancel/adoption, failed publication, exact commit retry and
  changed retry refusal; genuine storage failure after durable publication;
  cancellation cannot erase known or uncertain commit. Stale source/preview,
  original source/material, latest committed cancel, source replacement,
  recording/replay/transport opening and terminal destruction cases.
- Commit preflight refuses changed revision and a same-revision foreign Project
  before writes. Command ID collision stays cancellable. An actual outer Host
  token's denied claim, accepted claim/forced failure/abort and successful
  commit remain delegated; previously unknown retries retain identity even
  when their next writer acquisition fails.
- Actual concurrent render/service/publication/reclaim stress and TSan. Assert
  actual contention/progress, keep original B1/SPSC stress. No timeout, strictness,
  lane or journey reduction. Rebuilt semantic mutation fails an owning behavioral
  assertion, and exact restored fresh-mtime rebuild is green.
- Real Wasm/OPFS action invokes the same typed Application path, checks preview
  and cancel without writes, one durable commit, exact retry/Undo and cold reopen
  with full Truth/history/Artifact identity. Read OPFS lease/intent requirements
  before implementing the write path. No Native-only substitute.
- Core dependencies, official diagrams/full Portal, staged and committed new
  path ownership, exact one-commit/parent/body and clean worktree before Draft.

## Verification record

- Refreshed main before commit: still
  `1c4462aa8436f81da1db2a9e6420d94f0e84ccb4`; all24 remote open PRs remain
  Draft/no-auto-merge, with #2415 the only tempo successor. No duplicate B2
  delivery or changed premise was found. Original baseline4/4 passed.
- Final Native owning selection9/9 passed (8.60s), including original Sequence
  rebase, Pattern switch, B1 gateway/component stress and all five B2 groups.
  Full Truth/Artifact, literal PCM onset, one save/Undo/cold reopen, latest
  committed cancellation, changed/foreign source, publication refusal,
  exact uncertain retry and every record/replay/transport/terminal leg above
  have far-side assertions. Same-session controller retirement first failed
  its guard assertion; per-instance retirement restored the original journey.
- Final-source semantic mutation changed the saved BPM to the committed old
  value. Its actual rebuild succeeded, then owning journey failed at the full
  Truth/one-Undo assertion (CTest exit8). Restored SHA256
  `21b20c05b8595c6275bda8c2fda0c29173242948aab6bf676daa196e351b4996`
  with an mtime newer than the mutant object; the rebuild compiled that source
  and the complete selected9/9 returned green. Earlier failed fixture/API
  attempts and mutation evidence remain retained, not relabeled as passes.
- TSan exact owning selection9/9 passed (90.07s): original SPSC, Pattern switch
  component/stress, B1 gateway stress and all five B2 groups. Actual compiler
  flags include `-fsanitize=thread`; no ambient TSAN/DYLD/preload override.
  New render/control stress observed17 accepted/16 refused publications and
  24,530 actual callbacks, then graceful release/Application destruction while
  render continued. No sanitizer finding. This is not a full sanitizer lane.
- Final Wasm/OPFS build passed with verified Emscripten6.0.5/Node26 and locked
  Playwright1.62.1. Chromium3/3 (12.9s) and WebKit3/3 (16.5s) passed, each the
  original OPFS history journey plus both B2 save/reopen and save/Undo/reopen
  journeys. Previews/cancel/exact retry made zero immutable writes; one save
  produced revision3/240 and one Undo, optional Undo revision4/120 and one
  Redo. Every page closed before cold reopen, which matched the entire
  checkpoint and original WAV digest/24,044 bytes. Physical writer count after
  close was zero. Literal onsets18,001/40,001/57,001/69,001 preserve phase.
  Same-platform nested writer custody ran on actual OPFS. B2 stack high-water
  77,992/262,144 bytes, below the unchanged50% headroom gate.
- The initial Chromium3/3 pass preceded a missing isolated OPFS WebKit
  executable, which prevented that initial WebKit launch. Official
  `scripts/prepare-opfs-webkit.sh` installed WebKit26.6/build2361 in this owned
  ignored build slot; the final complete dual-browser run above passed and its
  private server exited. No shared browser cache or lockfile was changed.
- Core dependency verification passed. Official diagrams were regenerated;
  complete `scripts/docs-site.sh check` passed179 tests,52 source pages,
  10 source diagrams/20 generated outputs and50 built routes/internal links.
  Staged/committed ownership and final exact-head shipping receipts belong in
  the Pull Request after their actual terminal results.

Deferred evidence remains explicit: B3 actual Bridge/control/protocol/SDK and
AudioWorklet producer journeys, I2c Creator400ms/every cancel/metronome/S7,
complete candidate/full lanes/coverage and physical device/hearing acceptance.
No Task result clears that debt or independent review.

## Version Management

Version impact: additive Application Facade C++ API MINOR debt, provided existing
public layouts/vtables/config remain unchanged as planned. Reassess actual diff
before shipping; private pimpl/transport factory changes do not change public
layout. Preserve all higher existing debt under #2237, deduplicate by actual
integrated domain. No persisted Contract/Project format or manifest identity,
Product/Assembly/Build/snapshot allocation in this Task.

## Documentation Impact

Documentation impact: required — `/core/modules/application-facade/`, owning
source diagram and official generated HTML/SVG. Describe actual typed lifecycle,
uncertain commits, interlocks and unimplemented Web/Creator consumers. Complete
`scripts/docs-site.sh check`; do not hand-enter identities or dependency edges.

## Shipping boundary

One verified Conventional Commit, push and Draft successor of #2415. Refresh
main/successors before commit. Independent current-head review remains pending;
no self-waiver. Main freeze forbids merge/auto-merge, Release/tag, deployment,
Channel or Git cleanup until explicit owner authorization. #2235/#2112 stay open.
