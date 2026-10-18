# Real stereo output meter producer (#2231 / D04)

One implementation Task for #2112, based on Draft #2381 / full head
`83ab14ba5c5ee72dbacf91c6a02d0637b8077a3e`. Main is explicitly frozen;
commit/push/Draft PR only, in the same linear stack. No merge or auto-merge,
release, deployment, Channel promotion or Git/resource cleanup.

## Refreshed premises and retained source

Integration main `1e9e5fbea57f2250b6fda7c39634d1a4d542438b`; current governing
AGENTS/CLAUDE/issue-done/git-workflow are byte-identical to this stack parent.
Live #2231 is OPEN with no comments; current open PR inventory contains no
meter successor. #2112 keeps producer and Creator consumption as separate Tasks.
The approved D04 decision supplies Post-FX/Pre-ENC4, excluding click, separate
L/R sample peaks; UI dBFS/one-second hold belongs to the subsequent consumer.

Original candidate `71f29abff01d7c7a25c752a89b9f740ba4918518` still exists on
mbp-m1 `feat/stereo-output-meter`, with exactly 14 files and no attached meter
worktree in that machine's current Git inventory. Fetched read-only into private
`refs/codex/2231-original-producer`; no original refs, bytes, index, processes or
release-owned resources are modified. Original plan, historical negative
reviews R1/R2, 201 Node tests/four controls and pending browser/graph debt stay
bound to that immutable candidate; they are not current verification receipts.
No inference about old process liveness follows from an absent checkout.

| Premise | Current disposition / instrument |
| --- | --- |
| Existing graph | Delivered: native product -> capture tap -> monitor -> destination; COUNT-IN uses a separate native cue output. Read actual activation graph and monitorDestination positive control. |
| Capture start | Delivered: start binding, pending start, exact started ACK, failure/stop timers and fallback. Preserve all W1 and later tests; never copy an old whole file. |
| Always-on meter | Outstanding at main and stack parent: tap process copies audio then returns with inactive generation; manager dispatch owns started/batch/stopped/failed only; exact public Session return and runtime property binding contain sampleAudioClock/monitorVolume/inspection as positive controls, no meter projection. |
| Product-neutral SDK measurement | Reuse original private same-build owner/ACK/window design; no native telemetry query, Truth, event or new cross-language Contract. |
| Current consumer/FX/click | Creator already uses independent filter Cutoff and native metronome output. Adapt the original browser witnesses to those real controls, retaining all original transition legs/budgets and far-side assertions. UI meter is not delivered by this Task. |

## Exact declared files

One final Conventional Commit: `feat(web-runtime): measure stereo output before monitor gain`.
Only these 15 paths (the existing pitfall recurrence is added after actual causal proof):

- `.agents/pitfalls/live-phase-polling-alias.md`
- `apps/docs-site/diagrams/web-runtime-platform.architecture.json`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/static/diagrams/web-runtime-platform.html`
- `apps/docs-site/static/diagrams/web-runtime-platform.svg`
- `docs/plans/2026-10-19-stereo-output-meter-producer.md`
- `packages/web-runtime-platform/test/performance_master_capture.test.mjs`
- `packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `packages/web-runtime-platform/web/performance_master_capture.mjs`
- `packages/web-runtime-platform/web/performance_master_tap_worklet.js`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `tests/platform/web/creator/creator_web_output_meter.spec.mjs`

Integrate archived deltas with a three-way merge against its real parent;
resolve any overlaps around current capture ACK/lifecycle/Session wiring rather
than overwriting newer source. Reuse the existing measurement graph. Worklet
counts every copied frame, independent L/R absolute PCM maxima and exact peak
frames over 50ms windows. At most one in-flight packet and one scalar pending
window coalesce under Main stalls; owner changes cannot multiply queued packets.
Known meter traffic demultiplexes BEFORE pending/active capture validation.
ACK drains only its own exact token. A malformed meter never acknowledges or
poisons capture; capture errors retain their exact original behavior.

Session exposes immutable synchronous outputMeter, with actual context rate and
clock freshness, not arrival time or Engine callback frames. Unavailable stays
explicit for pending/stale/nonrunning/closed/unsafe clocks/protocol/tap failure;
real zero requires actual rendered zero PCM. Fresh running/recovery uses a new
owner; safety/fatal/close synchronously revoke, and old closures cannot borrow
new owners. Transparent audio/capture and direct-monitor processorerror fallback
must survive. No new gain stage, storage, timer query or fake animation.

## Verification and complete journeys

Lowest owning Node selection (entire three current files, retaining every W1,
capture, activation/recovery and current recording-switch prefix):

```sh
node --test packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs packages/web-runtime-platform/test/performance_master_capture.test.mjs packages/web-runtime-platform/test/runtime_session.test.mjs
```

Run syntax, strict SDK declarations and affected Creator type checking as
applicable. Run existing complete SDK Node selection if integration affects
shared Session behavior. Preserve exact original assertions, timers and negative
cases. New test registration must pass the staged and final committed 76-test
ownership suite. Meaningful controls: every-frame impulse, demux during pending
capture ACK, foreign owner guard, actual-clock freshness; restore WIP bytes with
fresh mtime and confirm actual owning red and restored green, never HEAD reset.

Full current Portal check and canonical source diagram rendering are required;
regenerate only the declared outputs, hash-check every unrelated diagram.
After verified source create an unpublished clean checkpoint for the official
Native/Wasm/UI build/package. A browser finding keeps the Task incomplete;
correct, reverify and amend this same atomic Task before push/Draft publication.

The original browser suite's complete normal and real processorerror journeys
remain required. Normal: real inactive-capture zero -> unequal stereo native
signal and absolute oracle -> actual independent FX changes measured PCM ->
ENC4 zero gives zero monitor output with nonzero unchanged pre-monitor meter ->
recording applied ACK/first PCM batch -> matching captured L/R -> Stop/seal and
meter continues -> empty Pattern with actual metronome energy but zero product
meter -> suspend unavailable -> real activation/recovery new owner -> 1000 reads
send no transport command. Failure: separately derived hash-correct/offline-ready
candidate with unchanged Wasm, actual next-render throw/processorerror -> real
direct-monitor audio continues -> old meter remains unavailable. No synthetic
processorerror, offline bypass, old digest or production fault hook.

Run the real downstream-of-monitor graph RED/restored GREEN against rebuilt,
verified artifacts, preserving both complete browser journeys and original
300s/240s budgets and 35s/125s transition bounds. Record actual default output
at start/end; no acoustic/device claim. A required failure blocks shipping;
unexecuted full platform/candidate/device lanes remain explicitly unverified,
not universal full13 work forced by ownership classification.

## Historical integration source receipts

Actual baseline at this stack parent: all three owning files 421 PASS. First
integration run: 439 PASS / 5 failures, bound to old source assumptions: missing
null start binding/started ACK in three new tests, plus two existing capture-only
VM journals observing the new meter clock error. Corrected the new fixtures to
observe real started ACK; existing oversized/no-clock VM now asserts its exact
meter-unavailable separately and retains all original capture/queue/PCM/stop
assertions. Added pending-start meter isolation. Owning 445 PASS, complete SDK
Node 600 PASS, strict SDK and Creator TypeScript PASS. Portal full check PASS
with 50 routes; only target diagram HTML/SVG regenerated, other18 byte-identical.
The four fresh controls each exited RED1 at their owning semantic assertion,
then restored byte-identical WIP with newer mtime and GREEN0 in a fresh process.
All14 source hashes matched the pre-control snapshot after every restoration.
The complete restored SDK Node selection is re-run before the source checkpoint.
These are source checks; real Browser and graph control remain pending here.

The graph negative control lives only in the declared proof observer. Under an
explicit test environment flag, fresh real AudioWorklet connections build
Native product → monitor → tap → destination, recording both rewired edges.
Processor, measured PCM/packets, getter, native source and package hashes are
untouched. The unchanged complete normal journey must fail its pre-monitor
signal at zero ENC4; flag-off creates a new context with the ordinary graph and
must pass. This rebuilds the real graph for each run without a production fault
hook or a commit of deliberately broken product source. The separate hash-correct
render-throw candidate and its complete fallback journey remain required.

## First packaged findings

The first two real Chromium journeys both failed the retained 4:1 oracle with
an actual 1:1 reading. This is the old witness premise: Engine renders one mono
voice value then pans to L/R (current realtime_engine/voice_dsp), so importing a
stereo file into one centre Pad cannot establish unequal native output. Replaced
only that source setup with two real mono Pads, 0.5/0.125 source amplitudes and
hard-left/right pan. Every native hit now requires both new actual started
sequences; retains the 4:1 oracle and adds literal 0.55679399/0.13919850 absolute
peaks: positive int16 amplitude /32767 × actual default keyboard velocity
100/127 × established sqrt(2) hard-pan curve. These constants were derived
from prepared_sample_bank.hpp, input adapter defaults and voice_dsp before
running the revised witness, never fitted from a successful run. Existing FX/monitor/capture/
click/lifecycle/failure legs and all timeouts remain unchanged. Both original
negative receipts, source checkpoint and artifact are retained; no producer
behavior change was made to accommodate the witness.

The second run passed literal dry peaks and the original >10% FX leg, then
correctly caught that max independent LP cutoff is still engaged (not old scalar
Filter500 bypass). Preserve the opposite rotary leg, then HOLD off/page exit/
reenter and require actual Core OFF before the unchanged dry monitor oracle.
The separate real-render fault journey did not observe processorerror; add
private fault-arm and actual-next-render notifications to the derived proof
candidate to locate that gap. They are diagnostics only: the real native
processorerror and monitor-audio assertions remain required, no synthetic event.
Both negative receipts remain retained; producer code is unchanged.

The third run was explicitly interrupted (owned wrapper SIGINT, terminal130)
after trace proved the new Sample→Perform return lacked its Sample-visible
far side, so a late completed Sample navigation detached the Perform locator.
It is not a pass. Add that exact transition assertion, retaining all budgets.
The fault candidate also records actual installed/armed/render markers and
loaded module URLs on failure; the real processorerror/audio gate is unchanged.

The diagnostic run proves real fault installation/arming/next-render throw,
but no `processorerror` listener notification; meter correctly becomes stale
while audio fallback never starts. An independent minimal native Worklet probe
(with/without the observer subclass) observes a trusted `ErrorEvent` named
`error`: addEventListener(processorerror) sees zero, onprocessorerror and
addEventListener(error) both see one. The [standard event API](https://webaudio.github.io/web-audio-api/#dom-audioworkletnode-onprocessorerror)
is retained. Add both native event names to the same existing idempotent SDK
fallback. New owning regression first RED: real-model `error` leaves a just-delivered
available value instead of processor-failed; duplicate error/processorerror
must reconnect only once. Browser proof now records the actual trusted event,
without constructing or dispatching a synthetic error.

After the native error listener fix, full SDK 601 PASS, Creator TypeScript
PASS and complete Portal 179 PASS/50 routes PASS. All four fresh controls again
RED1/restored GREEN0 with all14 WIP bytes restored, followed by full SDK 601
PASS. Browser fault/normal and actual graph control remain pending at this
source checkpoint; no push/Draft has occurred for this Task yet.

The corrected actual render-fault journey PASS (15.2s) proves real trusted
native ErrorEvent, immutable processor-failed meter and nonzero direct-monitor
PCM after failure; the old getter never revives. The normal journey then caught
another missing far side: optimistic HOLD-off followed immediately by exit can
retire its unsent control, leaving a frozen LP. Require real public SDK applied
HOLD=false with accepted/applied sequences equal BEFORE leaving; keep the exact
OFF/core and dry PCM oracles. Its original failure remains retained; no threshold
or timeout is relaxed and no product HOLD policy is changed.

Normal now passes dry/FX, monitor-zero, real capture/Stop/seal and reaches
metronome output. Its default poll misses the short click PCM and times out.
The existing analyser window is 2048/48000s and click lasts 40ms; use 20ms
observation cadence with the same >0.001 predicate and 35s deadline. Correlate
actual nonzero PCM with its scheduled AudioContext click and require contiguous
zero pre-monitor windows covering that entire 40ms interval, stronger than one
near-side zero read. A test-only alias control samples mid-gap at whole periods
and retains clock/PCM observations on actual RED; it never forces the clock or
changes a product packet, gain, threshold or timeout. Confirm causal aliasing
before recording the applicable existing pitfall recurrence.

A later run caught a first-window 3.937:1 FX transient while the two native
chord starts were asynchronous. Keep the exact 4:1/absolute/10% oracles; select
one complete measurement window beyond both actual received started receipts.
The receive-time AudioContext bound is conservative test ownership evidence,
not a fabricated Native frame or producer freshness clock. Both voices must
still be started, and the original 35s/300s bounds remain unchanged.

The steady-window run passes the real click PCM and contiguous zero tap
windows over its entire scheduled 40ms interval. It then fails an obsolete
Stop witness: creator-phase remains running because it describes Host audio,
not transport. Replace that wrong field with the existing canonical transport
status projection (stopped) AND exact physical Play/Stop lamp name; also require
the playing name before clicks. Preserve the actual Stop action, 35s budget,
all following suspension/recovery legs, and attach successful click frame/PCM
observations. The old false witness and failure remain retained.

The next full normal prefix passes genuine transport Stop, then catches the
old explicit-context interruption fixture: AudioContext.suspend remains parked
until resume, so waiting for a context-usable recovery state is not its return
leg. Observe the actual production meter-owner null message after the real
suspend, require unavailable, then resume that same real browser context and
retain the original recovering→accepted Pad/voice receipt→new owner journey.
No mock statechange, skipped Native lifecycle barrier or fake completion is
introduced. Failure artifacts now include public SDK diagnostics/actual context,
owner messages and last real meter for bounded investigation of any real gate.

## Completed source and real-audio verification

Checkpoint `bca06427090aa21ae428a881c2afd861ba010b1a` is clean and its
parent is exactly `83ab14ba5c5ee72dbacf91c6a02d0637b8077a3e`. Official
configure/build/package PASS; pinned Emscripten 6.0.5 and Node26. Native CLI
and unchanged official deterministic fixture generation PASS. All original
fixture bytes remain SHA-bound; no Project bundle schema is edited by a test.

- Complete SDK: 601 PASS, zero skips/failures; strict SDK and Creator types PASS.
- Four actual fresh owning mutations: RED1 / restored GREEN0 each, complete
  SDK 601 PASS afterward. Native error-event regression also first RED then GREEN.
- Full Portal: 179 PASS, production build and 50 routes/internal links PASS;
  only owning diagram outputs regenerated, other18 outputs byte-identical.
- Complete packaged Chromium normal + actual-render-fault: **2 PASS (38.5s)**.
  The normal journey retains every recording/Stop/seal, click, explicit suspend,
  actual context interruption/return, accepted voice and new-owner leg.
- Real graph negative: both actual rewired edges observed, dry/FX prefix passed,
  then signal at zero monitor correctly RED at the original 35s predicate;
  actual running meter reports L/R zero. Fresh original graph complete2 GREEN.
- Observation negative: 0.5s actual click period, 71 clicks, 35 observations,
  actual clock advances34.181333s; gap sampling sees zero at phases
  0.258667–0.440000s and original click assertion RED. Restored20ms full2 GREEN.
  This confirms existing pitfall recurrence2; record it in the declared ledger,
  keep open with escalation #2382 (no new CI/control/generic cadence gate).
- Core dependencies PASS; new-file ownership suite has staged and committed
  76 PASS at earlier checkpoints and must pass again on the final commit.

All browser runs used the default built-in MacBook Pro Speakers at start/end.
These are real computed/observed PCM facts, not acoustic or physical-device
acceptance. Original negative results, explicit interrupted exit130, private
source refs and traces remain retained; no historical failed run is relabelled.
The initial omitted Playwright spec argument exited1 at fixture collection,
then the explicitly selected full normal journey PASS; it is not product evidence.
Only this receipt/ledger documentation changed after the above complete2 cut.
Rebuild the final clean package and rerun both complete journeys before push,
then record its exact head in the Draft body. No consumer UI or full product
proof, candidate, sanitizer or physical-input/hearing PASS is claimed.

## Version Management

Version impact: compatible additive Web Runtime Platform JS API MINOR debt in
#2237; existing higher ABI debt remains separate. No native layout, persistence
or public cross-language Contract change. Do not allocate module/Host/Product
identities, Assembly, Build, Channel or immutable snapshot in this Task.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/web-runtime-platform/ /platform/web-runtime/

Update narrow measurement, demux, ownership and freshness facts plus the existing
web-runtime-platform source diagram. Consumer pages and meter rendering are a
subsequent Task. Complete Portal check before commit; PR body lint and actual
parent-relative declaration must finish with observed exit0 before publication.

## Shipping boundary

Base Draft #2381 branch `feat/creator-retained-asset-assign`. New successors
build on this branch. Independent current-head review remains PENDING for a
Draft/non-main layer; no waiver or clean-review claim. After explicit owner
unfreeze, refresh premises/review/protection/conflicts/conversations before any
merge. Keep #2231/#2112 open for consumer and final candidate/device acceptance.
