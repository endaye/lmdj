# Performance capture progress producer — #2135 A prerequisite

## Premises and ownership

Integration main refreshed to `ba67a81d4200019f3e604bae2a69ea30f0354e91`;
Task parent is frozen Draft #2390, `547032fddfc2a816489b0765c52f7a9c1dafc12b`.
The live #2135 body/comments, parent and all ten open PRs were inspected.
The other open PR is a release snapshot witness; none owns capture duration.
Governance is identical at main and the stack head. The intervening SDK meter
changes belong to the existing stack; capture/queue/writer behavior still
matches the inspected main. Original C1/C2 have merged; no original C1 worktree
or in-flight duration PR remains in the current inventory. This Task has one
writer in its new isolated worktree; heavy verification runs serially.

| Premise | Disposition before source edits |
| --- | --- |
| Audio capture lacks an authoritative frame source | Already present internally: `performance_master_capture.mjs` admits only matching generation, exact started binding, contiguous validated stereo batches and finalSequence. Reuse that boundary; no new clock, worklet message or capture owner. |
| Public progress fields exist | Outstanding: `WebPerformanceCaptureSession` exposes configuration and start/stop only; the public capture handle is exactly `{stop}` (explicit test). Add a separate read-only Session capability; preserve all old exact response/handle keys. |
| Host may assume48k or use attempted/durable frames as live duration | Not authorized: context rate must be read from the actual AudioContext; received PCM and durable WAV are different facts. This prerequisite supplies received frames/rate/identity only. Host queue/writer durable projection remains #2135 A; saved verified metadata remains B. |
| Meter can supply capture timing | Rejected: independent meter owner/windows are not capture identity, do not establish complete delivery and must remain separate. |
| Old owner holds implementation admission | Historical note predates merged C1/C2 and the current authorized stack. Preserve its ownership history; do not edit another worktree or create a concurrent writer. Current #2135 explicitly allows the smallest missing public-field producer prerequisite. |

Baseline: three owning Node files,446 PASS, exit0. This is the required public
producer prerequisite, not completion of A, B, U08b or #2135. Follow it with
Host queue/writer projection, verified saved-WAV metadata and actual Creator
Recording/Takes presentation. Replay keeps event progress and existing timing.

## API and lifecycle

Add `performanceMasterCaptureProgress()` and a separate optional capability
interface. It is a synchronous immutable read with no RPC, I/O, new timer or
effect on capture admission. Do not widen existing result schemas, capture
handles, Worklet packets or manifest contracts.

- Before confirmed started ACK: unavailable. After ACK: actual sampleRate,
  cumulative validated receivedFrames, captureId, generation and existing
  begin binding. Silence counts; absent/delayed batches do not advance.
- Phase recording→stopping→stopped follows the existing stop request and exact
  finalSequence ACK; include the actual final partial batch. Retain the stopped
  snapshot only until replacement start or owner close.
- Failed capture retains only validated received frames. A valid Worklet
  failure's droppedFrames is known; protocol errors, timeout, processor failure
  or closure do not manufacture zero lost frames. These report unknown loss.
- Identity is passive telemetry, never a second recording owner. Missing/bad
  rate, identity or optional producer capability yields unavailable without
  stopping/refusing an otherwise valid capture. Old callers work unchanged.
- Snapshot copies are frozen and bind the same tap/generation/start identity;
  late old traffic and a new capture cannot relabel old frames. Session close,
  tap retirement and replacement revoke the old getter's current projection.
- Received frames are not durable WAV frames, whole Performance elapsed,
  saved completeness or Replay duration. No Project/persistence changes.

## Declared files — one atomic Task / Conventional Commit

- `packages/web-runtime-platform/web/performance_master_capture.mjs`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `packages/web-runtime-platform/test/performance_master_capture.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `docs/plans/2026-10-19-performance-capture-progress.md`

Expand this declaration before editing any additional file. No App/Creator UI,
writer/queue, C++, worklet, schema, CI, manifest or version allocation change.

## Verification and defect ownership

1. Node component tests fix independent facts: exactACK/identity, silence and
   batch-only advancement, immutable snapshots, authoritative non48k rate,
   final partial/stop, old generation isolation, replacement/close revocation,
   reported versus unknown loss, optional capability/telemetry failure, and
   unchanged old exact-key handles. Reuse the real Worklet VM and port parser;
   injected public seams retain exact producer shapes.
2. Run all Platform Node tests and Creator type checks for compatibility.
   Source mutations must fail named counting/owner assertions, followed by
   exact-byte fresh-mtime restore and a fresh-process green check. No broken
   source mutation enters a commit.
3. Build the Native CLI and official pinned Node26/Emscripten6.0.5 Creator
   distribution. An unpublished clean source checkpoint permits packaging;
   fold any browser fixes into the same atomic Task before publication.
4. Packaged proof reads the public SDK on the real retained Session and real
   tap batches. Assert received count equals the independently observed batch
   sum, final sampleRate/count matches the real WAV header/PCM length, silent
   audio contributes frames and Stop retains the final partial batch. New
   capture changes identity; stopped/closed/reopened lifecycle cannot inherit
   old counts. Persist actual JSON evidence by output path and read it back.
5. Preserve the complete original Perform/touch-fit/meter selection, including
   all PCM, failure-prefix, retry-bind, save/reopen/Replay, crash/owner-loss and
   recovery legs and budgets. Run canonical locked WebKit refusal boundaries;
   unsupported product UI is not a pass. Keep full candidate/device deferred.
6. Complete Portal check, offline dependencies, new-file ownership/admission,
   final body lint and parent-relative declaration checks. Refresh relevant
   main/history, inspect exact staged/committed files and final clean status.

Process guidance: existing complete-journey, real-primitive stubs, fresh restore,
path-backed artifacts, load-correlation and live-polling cadence pitfalls apply.
Pure progress reads must not submit requests or introduce sampled phase gates.
Product regressions belong in owning tests, not duplicate process entries.

## Version Management

Additive compatible Web Runtime Platform JS API MINOR debt, deduplicated in
#2237 with the same compatibility domain's existing debt. No Native ABI,
cross-language Contract, Host UI, persistence or Product/Assembly/Build
allocation. Preserve prior Audio Runtime ABI MAJOR debt; no guessed version.

## Documentation Impact

Documentation impact: required — `/core/modules/web-runtime-platform/` and
`/platform/web-runtime/`. Describe actual read-only capture semantics and limits.
Host pages change with their later real consumer Task. No Module boundary or
diagram edge changes; existing diagrams stay accurate.

## Delivery boundary

One Draft successor of #2390 on the same linear stack. Main remains frozen
until explicit owner unfreeze. No merge/auto-merge, release, deployment,
Channel or resource cleanup. Independent current-head review, integration,
full candidate and physical acceptance remain pending. #2112/#2135 stay open.


## Results and retained evidence

Source checks PASS: all Platform Node615 (before the final provider-loss guard); Perform caller components179;
Creator TypeScript; offline Core dependencies; Native CLI; pinned official
Creator configure/build; complete Portal179 tests/50 routes/internal links.
No Creator-wide/full candidate lane or physical device pass is claimed.

Two source mutation proofs each produced semantic RED1, followed by exact-byte
fresh-mtime restore/fresh-process GREEN0: deleting the validated frame increment
failed the real silent Worklet4800-frame assertion; keeping the first progress
identity through replacement failed the real Session's new-generation available
assertion. Both restored source hashes are retained in the proof receipts.

Historical first-source check failed only the explicit public Session method
inventory because the new additive method was not listed yet. Updated that
inventory to declare the intended method; retained all old capture-handle,
configuration, packet and response assertions. The complete615-case check then
passed. Baseline446, intermediate owning458/all-Platform614 and final615 are
separate observations, not a fixed future case-count gate.

The clean unpublished checkpoint still requires real packaged frame/WAV/
identity/reopen proof, the complete original Perform/touch-fit/meter selection,
canonical WebKit boundaries, committed ownership and final body/declaration
checks before publication. Bind their actual head and results in the Draft PR
and canonical Issues. Host durable projection, saved metadata, UI, independent
review, integration and candidate/device acceptance remain pending.


Final staged source review tightened the optional provider boundary: only an
explicit Worklet post-message-failed report may quantify loss; protocol/timeout/
processor failures cannot turn unknown into zero. Its independent public
contract test rejects the bad telemetry without stopping capture, then accepts
null loss. Rerun all Platform Node tests and the official Creator build before
the clean checkpoint; no response shape or capture admission changes.

Final provider guard: complete Platform Node616 PASS and official Creator
build (including TypeScript) PASS. All original public-handle/schema assertions
remain; only the explicit Session method inventory admits the new capability.


First packaged probe at `d2f2c12d` failed the new test's unconditional headered
binding assumption. The actual capture was the already-supported legacy null
binding; received frames/rate assertions passed before that line. Record the
real started ACK independently and compare its exact actual binding (null only
when the ACK is null), plus the real finalSequence. Preserve all frame/WAV/
replacement/cleanup/reopen legs and budgets; do not force a different product
profile, weaken SDK validation or count this interrupted journey as a pass.
