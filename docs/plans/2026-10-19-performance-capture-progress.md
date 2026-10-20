# Capture progress producer: current-main integration of #2391

## Premises before implementation

Integration and isolated worktree base:
`9ff12bc7162a0884381b0135464ac83f2db953ec`.
Original Draft #2391 source `e24072d0cbae9e56c442d95fe52ce87ff1f602f8`,
parent #2390 `547032fddfc2a816489b0765c52f7a9c1dafc12b`.
Live #2112/#2135/#2228/#2237 and comments, #2390/#2391/#2392/#2411 and actual
source/diffs were refreshed. Seven governing files match current main. This
Task has one writer in `feat/performance-capture-progress-main`; the root main
worktree and original published stack remain untouched. All10 tracked symlinks
are actual links. No subagents or concurrent heavy verification.

| Premise | Disposition at the exact current base |
| --- | --- |
| Public received-frame/rate/identity query exists | Outstanding: all three owning source/type files contain neither performanceMasterCaptureProgress nor captureProgress. Current API exposes capture configuration/status/start/stop, with exact old handle keys. Re-home only this additive optional Session query. |
| Authoritative validated capture boundary is missing | Already present: exact started generation/binding, contiguous validated stereo batches and finalSequence drive capture. Reuse that real boundary and actual AudioContext sampleRate; no new owner, packet, clock or admission rule. |
| Saved metadata and startup discovery still require these old ancestors | Already delivered independently through #2437/#2438/#2439, latest actual merge9ff12bc7. Preserve current Runtime metadata queue/owner retirement, public methods/types and Portal descriptions. None of these files equals the old Draft parent; never replace them with whole old blobs. |
| Capture progress requires meter or Perform layout | Not required by the API: original parent additionally carries held meter #2383 and layout/Slots. Their original source is not current main. Migrate only the nine-file producer delta; do not import meter, restore withdrawn COUNT-IN or alter the pending #2430 owner exception. |
| Received PCM establishes durable WAV or complete Performance duration | Rejected by approved #2135 A0/A/B scope: received, Host durable/drop/checkpoint, saved verified metadata, whole Performance elapsed and Replay event progress are distinct facts. Only the approved received producer is this Task; Host/UI consumers remain separate. |
| Old Draft's full-main freeze still governs | Historical: user now permits sequential ordinary feature/fix/test integration with current-head review/protection and safe postmerge cleanup. Release-owned paths remain frozen; candidate8c361623f unchanged. |

Before any Task edit, all current Platform Node tests passed586/586 in1.865s
(Node26.7.0), no skips. Original main already has valid legacy/null and headered
ACK contracts; preserve both. A matching old-parent filename is not a reason to
rewind current metadata or to include unrelated upstream Draft functionality.

## Behavior and ownership

Add synchronous immutable `performanceMasterCaptureProgress()` through a separate
optional capability interface. Existing configuration, public capture `{stop}`,
Worklet messages, Facade keys and capture admission remain exact.

- Before exact started ACK: unavailable. After ACK: capture identity/generation,
  existing begin binding, actual context rate, validated cumulative receivedFrames.
  Silence and the final partial batch count; delayed/unposted frames do not.
- Recording/stopping/stopped/failed follow original lifecycle and exact stop ACK.
  A reported Worklet post-message failure has known droppedFrames; protocol,
  timeout, processor/stop failure have unknown loss, never invented zero.
- Retain only a compact stopped snapshot, never a settled sink/queue. Replacement
  start and Session/tap close revoke old projection. Late old batches cannot be
  adopted or relabeled. Reads add no RPC, timer, I/O or capture owner.
- Missing optional telemetry/rate/identity makes this read unavailable without
  refusing or stopping valid capture. Host queue/writer drops remain separate.

## Declared files: one atomic integration Task

- `packages/web-runtime-platform/web/performance_master_capture.mjs`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `packages/web-runtime-platform/test/performance_master_capture.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `docs/plans/2026-10-19-performance-capture-progress.md`

No Creator UI/controller/queue/writer, C++/worklet, schema, CI, manifest, Product
or version allocation edits. Preserve current main outside the exact delta.

## Verification and independent oracles

1. Port all original new Node regressions while retaining every current main
   test and method inventory entry. Full Platform selection covers exact ACK,
   4800+64 real Worklet frames, non48k rate, immutable binding, replacement/late
   owner traffic, reported versus unknown loss, optional old provider/identity
   failure and unchanged old handle keys. Creator types and owning Perform
   caller tests cover compatibility.
2. Counting and identity mutations must each fail the intended semantic
   assertion in fresh Node processes; restore exact working-file snapshots
   with fresh mtimes, not HEAD (which lacks the uncommitted implementation).
   Full owning/all-Platform GREEN follows. A third verification-only mutant
   omits the real Worklet's final partial flush: the independently executed
   batch-sum/getter parity must still agree at4800 while the absolute4864 oracle
   fails. Snapshot and restore that exact owned Worklet file; no Worklet change
   enters the nine-file implementation commit. The absolute4800/4864 real-VM
   count catches the shared omission even when batch/getter/WAV agree.
3. Build owning Native CLI and official pinned Emscripten6.0.5/Node26 Creator
   configure/build/package serially. Use a clean unpublished source checkpoint
   for production package provenance; amend only before first publication if
   source verification needs correction. Published heads receive follow-ups.
4. Preserve the original added packaged journey in full: real retained Session
   and real port batches; silent frames and final partial batch; exact actual
   started binding (including supported null), finalSequence; independently
   observed batch sum and actual exported WAV header/frame/length/SHA; second
   capture's distinct identity; discard; terminal cleanup; actual reload and
   fresh idle projection. Persist output-path JSON and read it back.
5. Run every current-main Perform/touch-fit journey plus that new journey with
   original budgets/assertions, including original PCM/save/reopen/Replay,
   failure-prefix/retry-bind/crash/owner-loss/recovery legs. Main has no meter
   spec/UI, so the old mixed-ancestor33-case stack receipt cannot be reused as
   current evidence: its additional meter/layout combination remains owed at
   actual combined integration. Do not skip or truncate any available main
   journey or the new producer journey. Run both canonical locked WebKit
   capability-refusal boundaries; they do not establish product WebKit UI/PCM.
6. Full Portal check; offline dependencies/source boundaries; staged and
   committed ownership/admission; final committed scope and PR body/declaration;
   exact-head authenticated independent review, all findings/conversations,
   live protection and expected-head squash before actual merge/cleanup.

Controlled PCM/fixtures and local speaker endpoint observations are not device
hearing/captured external audio. Full candidate, sanitizer/batch debt, physical
acceptance and missing consumer/combination journeys remain open; their closure
requires the corresponding actual integration and full owning evidence.


## Source verification before unpublished clean checkpoint

Current-main baseline586/586 Node PASS1.865s. Initial delta application correctly
rejected contexts belonging to old meter/Slots ancestors; those rejects are
retained externally. Re-homed all progress hunks onto the current code, without
meter restoration or metadata rollback. First new-only failures exposed absent
old outputMeterFixture/VM clock; after the capture-only fixture was added, its
old createRealMasterTap alias was also absent. Reuse the already imported real
createPerformanceMasterTap and restore the real VM clock. These7- then6-case
setup failures are retained, not counted as semantic producer RED or passes.

Final complete Platform Node601/601 PASS1.873s, zero skips. All original586 tests
and15 new tests remain. Owning capture24 and Runtime Session416 pass after exact
snapshot restores. Three current-source mutations each produce semantic RED1:
missing increment gives0 versus4800; retained first identity makes the next
capture unavailable; omitted real Worklet final flush makes batch/getter parity
still agree at4800 while the independent rendered4864 oracle fails, and the
owning test rejects [4800] versus [4800,64]. Restored standalone parity and
absolute oracle return [4800,64]/4864. Worklet bytes exactly match HEAD again;
no Worklet implementation edit remains. All source snapshot/mutant/restored
hashes and actual fresh-process exits are retained.

Creator types PASS; existing Perform caller170/170 PASS12.466s; offline Creator,
web and Portal dependencies, Core dependencies, Runtime/explicit-root Host
boundaries and browser-spec syntax PASS. Native CLI configured and built from
current main in16.633s. The unchanged authoritative embedded Creator fixture
generator, current CLI/Assembly and real kick.wav produce two byte-identical
bundles:767554 bytes, SHA66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f.
Their hash also matches the separately retained original fixture; current
readback has its own CLI/Assembly/source hashes, not an inherited build claim.
Full Portal PASS62.442s:179 tests,53 pages,51 routes/internal links.

Eight non-plan source/test/Portal input hashes are recorded. This checkpoint is
unpublished and not completed shipping: clean-head official production configure/
build/package, complete current-main packaged journeys/new capture evidence,
WebKit refusal boundaries, committed ownership/scope, independent exact-head
review and actual merge/cleanup still require their own positive receipts.
No parent33-case mixed-stack result or full candidate/deferred lane is reused.

## Version Management

Compatible additive Web Runtime Platform JS API MINOR debt under #2237,
deduplicated within its actual compatibility domain. Preserve higher existing
Audio Runtime ABI MAJOR debt. No Native ABI/cross-language Contract, persistence,
Host UI, dependency, manifest, Product/Assembly/Build or snapshot allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/web-runtime-platform/ /platform/web-runtime/
Describe received-only optional progress, identity/ACK/lifecycle, known/unknown
loss and missing Host/UI consumption. Preserve current metadata and all other
facts. Module/diagram boundaries remain unchanged.

## Historical evidence and delivery boundaries

The [original immutable Task record](https://github.com/endaye/lmdj/blob/e24072d0cbae9e56c442d95fe52ce87ff1f602f8/docs/plans/2026-10-19-performance-capture-progress.md)
and original Draft stay unchanged. Its615/616 Node, mixed33-case stack browser,
Portal/production results are historical, not current-head passes. Preserve its
initial public-method inventory failure, packaged headered-only assumption
failure, counting/identity mutation RED/GREEN and all other negative evidence.
Current startup-discovery/Save OOM and old B0 WebKit evidence remains in the
prior immutable integration archives; this producer does not explain or erase it.

User authorizes ordinary protected main integration and safe postmerge cleanup;
retain original refs/WTs needed downstream and both unrelated dirty WIPs. The
release-owned workflow/tools/evidence/releases path freeze remains. No auto-merge,
tag, Release, Runtime deployment or Channel operation. #2112/#2135/#2228 remain
open until their full actual consumer/candidate/device acceptance is verified.
