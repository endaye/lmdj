# Worker-owned Performance recording metadata reader — #2135 B

## Premises before implementation

Main refreshed to `8c361623f2c1bf32460c32793a33a4d7e204fb7f`; Task parent is
Draft #2403 / `4bd64adb8dfd92a40cdb1d9c19e5ea78f336c20c`. Live #2112/#2135,
comments, #2237 and all15 open Drafts were read; no successor owns this reader.
The isolated `feat/performance-recording-metadata-reader` starts clean with10
actual tracked symlinks. One writer; no sub-agents.

| Premise | Disposition and evidence |
| --- | --- |
| Raw bounded reads, verified recording scans and WAV metadata are missing | Already delivered on the frozen stack by #2401/#2402/#2403. Reuse these exact producers, without duplicating their format, hash, ownership or size policies. They are not present on current main. |
| A saved recording metadata consumer exists | Outstanding: Application header/operation registry/dispatch and Web Runtime performance tables expose the known-positive list/inspect operations, but no recording metadata reader/query. The list projects ArtifactRef and event_count; inspect returns Performance Truth. |
| Candidate Jobs provide a generic asynchronous executor | False: candidate_job_run calls provider_run synchronously and writes durable Candidate/Attempt state. It is not a read-only metadata executor. |
| Pattern transport's worker can host arbitrary reads | False: its retained work cell, durable reconciliation, session registry and shutdown belong to transport. Reusing that cell would couple unrelated audio control to long queries. |
| Moving a scan to a worker automatically protects Control | False: sharing Application's mutable AuthoringHistory mutex would still block Control mutations throughout the scan. A reader must capture only the exact shared storage platform, use a private read-only ProjectStore/history, and publish only the Store's final owner/revision/ref receipt. It must never recover or mutate authoring state. |
| Independent read state weakens owner checks | No: the existing scanner still verifies full bytes/hash/length/EOF and the original committed selector again at the end. A concurrent mutation invalidates its expected revision. Same-platform leases permit existing Control writes; no new writer admission policy or silent serialization is introduced. |

At main, the authoritative Application header/registry/handlers were inspected
using inspect_sample and performance.list/inspect as positive controls; the
new reader is absent. Current main independently withdrew COUNT-IN (#2396).
Retain that integration divergence and the owner's explicit freeze.

## One Task / declared files

1. `packages/application-facade/include/lmdj/facade/performance_recording_metadata.hpp`
2. `packages/application-facade/src/performance_recording_metadata.cpp`
3. `packages/application-facade/include/lmdj/facade/application.hpp`
4. `packages/application-facade/src/application.cpp`
5. `packages/application-facade/CMakeLists.txt`
6. `tests/core/facade/performance_recording_metadata_test.cpp`
7. `tests/platform/web/project_io/project_io_web_test.cpp`
8. `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
9. `apps/docs-site/docs/core/modules/application-facade.mdx`
10. `apps/docs-site/docs/platform/storage.mdx`
11. `docs/plans/2026-10-19-performance-recording-metadata-reader.md`

Expand before editing another path. No storage/parser behavior, mutable authoring
history, capture/writer policy, JSON protocol/SDK/Host UI, CI or manifest change.
This supplies the required Host-neutral C++ reader; the asynchronous Runtime
coordinator, stale-owner retirement, SDK and actual Take UI remain required next
consumer work. Do not substitute this producer for the complete B acceptance.

## API and ownership

Application creates a move-only PerformanceRecordingMetadataReader. It owns a
private Store using the Application's exact storage platform, not Application,
its sessions, providers or live AuthoringHistory. Construction performs no I/O.
One sequential caller owns the reader; it may transfer the idle reader to a
worker. Every scan/lease and its retirement run on that caller. The reader may
outlive Application, retaining only the platform. Destroy only after inspect
returns; no concurrent use/destruction or audio-thread call is permitted.

The typed request snapshots absolute bundle path, Project/Performance IDs,
expected revision and exact ArtifactRef at entry. Only a bound recording is
inspected; existing public list/inspect represent no-WAV separately. Metadata
contains exact verified owner/ref and Project/recording revisions plus an audio
Result: rate/channels/source_frames on success, UNSUPPORTED_AUDIO only after
complete raw verification on unsupported format. Outer failures preserve owner,
revision, storage and Artifact mismatch distinctions. Metadata never asserts
capture completeness, physical close or Performance elapsed.

A std::stop_token provides cooperative cancellation before I/O, on each bounded
consumer window, and after final verification. Cancelled is a distinct variant,
never metadata or a new Foundation error code. It cannot abort an in-flight
platform operation, claim a timeout is cancellation, or revoke a value already
returned. A later async coordinator must still discard retired owner/generation
completions and keep the worker alive until its actual terminal state.

Retain parser failures while consuming the full raw hash. Only final successful
Store verification permits a metadata/format result; integrity failure wins over
a provisional format diagnosis. No whole-file or decoded PCM allocation/fallback.
Unexpected exceptions use the existing privacy-safe typed Facade boundary.

## Verification / defect ownership

- Baseline original facade.application, facade.performance_operation_contract
  and project_io.performance_recording_scan before product edits.
- New Native component uses real Native storage with a forwarding range observer,
  fixed independent WAV identity/metadata oracles and unchanged persisted Truth.
  Verify valid silence/odd JUNK, verified unsupported encoding/structure, late
  digest corruption over provisional format error, selector errors, unavailable
  range capability, cancellation before/window/after verification, request input
  snapshots, no whole audio reads/writes, lease retirement and reopen.
- Deterministic real-thread barrier holds a read while Control commits a rename;
  assert Control completed before the read was released, then reject the stale
  scan. Verify the detached reader still works after Application destruction.
  The barrier has bounded failure cleanup and every worker joins before fixture
  teardown. Run the owning component under TSan for shared-platform/stop-token
  races; do not discharge a sanitizer failure by a plain pass.
- Rebuilt mutants skipping cancellation publication checks and short-circuiting
  provisional parser errors must fail their respective owning assertions.
  Snapshot all uncommitted source, restore with a strictly newer mtime, require
  actual source compilation and read rebuild/test terminal exits.
- Actual C++/Wasm/Asyncify/OPFS worker proof uses the public Facade factory and
  the same platform beneath a Control root writer. The reader outlives its
  Application, is consumed/destroyed on a distinct worker, and the parent pumps
  until actual worker exit readiness before joining. Validate pre-cancel and
  actual valid/unsupported/mismatch results, root/child custody retirement and
  two real close/reopen legs per case, with complete independent physical
  digest/length readback and retained output-path JSON. Preserve the original
  direct scan/parser journey and all selected common recovery/owner/range/scan
  assertions, budgets and half-stack gate. Use the supported OPFS WebKit and
  protocol wrapper from the outset.
- Production Native/pinned Wasm link, full Portal, dependencies, staged ownership
  and exact PR body/declaration. Heavy build/browser/Portal phases run serially.
  Full batch/candidate, existing WebKit lifecycle findings and physical-device/
  hearing acceptance remain separate; no wider pass is inferred.

Refresh main/successors before commit/publication. Inspect the full staged diff,
exact committed paths and final clean worktree. One Conventional Commit, push and
Draft successor of #2403. Independent current-head review PENDING, no self-waiver.
No merge/auto-merge, release/tag/deployment/Channel or Git cleanup while frozen.

## Version Management

Version impact: additive Application Facade C++ API MINOR debt, deduplicated by
compatibility domain under #2237 without lowering higher existing debt. No new
Module dependency or Foundation/Project/JSON/SDK/wire Contract change; no manifest,
Product/Assembly/Build or immutable snapshot allocation.

## Documentation Impact

Documentation impact: required — `/core/modules/application-facade/` and
`/platform/storage/`: private read-state ownership, complete verified identity,
format/cancellation distinctions and the remaining async Runtime/SDK/Host path.
No dependency or source diagram edge change.

## Initial verified evidence

Original Native baseline3/3 and the first complete owning selection4/4 passed.
The final component additionally verifies external stop while the worker is
actually blocked: cancellation retains physical writer exclusion until the
worker returns, then foreign acquisition succeeds. The owning TSan component
passed with the same actual Control mutation/stop-token/reader retirement
interleavings. Unexpected exceptions are checked for generic typed errors and
lease retirement rather than private exception text.

Actual rebuilt cancellation-publication and premature-format-return mutants
failed their respective owning assertions. All uncommitted source was snapshotted,
restored with strictly newer mtimes, actually recompiled and returned GREEN.
The first Wasm fixture build found that the existing stack probes are global,
while the new forward declarations were in the anonymous namespace. Declaration
placement was corrected without changing probes or stack thresholds; the real
Wasm fixture and production-link rebuild returned0.

## Final Task evidence

- Final Native owning selection4/4 PASS, including the original Application,
  Performance operation and recording scan components. The new reader component
  also distinguishes Project revision1 from recording revision17, proving both
  values come from the verified receipt rather than a shared revision guess.
- Final dedicated TSan component PASS with actual concurrent Control mutation,
  external stop, exact shared-platform retention and worker retirement. No
  sanitizer suppression, timeout, threshold or assertion was relaxed.
- Chromium8/8 and supported OPFS WebKit5/5 PASS, including all original selected
  journeys. Both retained Facade output-path JSON files were read back: three
  cases, each prepare/close/reopen/close/reopen/close, nine reports per browser.
  Exact owner/ref/revisions, literal metadata, unsupported/integrity distinctions,
  independent full physical SHA-256/192124-byte length/prefix/tail, Application
  retirement, worker/root custody and all nine closed pages match. Worker stack
  high-water is17896/262144 bytes on both browsers; the unchanged half-stack gate
  applies to the worker itself. Original direct parser journeys remain intact.
- Production Native Facade/C API and pinned Emscripten6.0.5 / Node26 Wasm fixture
  plus production-link smoke PASS. Dependency and original Web timeout-policy
  checks PASS. Full Portal PASS:179 tests,52 page validations,10 diagram sources /
  20 outputs, typecheck, production build and50 rendered routes/internal links.
- Precommit main refresh remains `8c361623f2c1bf32460c32793a33a4d7e204fb7f`.
  Live Issues/comments and all16 open PRs were read again; the additional #2405
  owns release intent batch selection, not this reader. The15 Draft stack heads
  and exact parent are unchanged. No duplicate reader successor was found.

Pitfall impact: none — parser/reader behavior and the fixture's declaration
placement are derivable from code. Existing independent-oracle, fresh-rebuild,
complete-journey, worker-stack and retained-artifact procedures were followed.
Old B0 WebKit lifecycle failures remain unresolved; selected passes do not explain
their cause. Full batch/candidate, full Creator/transport and device/hearing
acceptance remain unverified. Current-head independent review remains PENDING.
Shipping ownership, full staged inspection and committed-range/body classification
are recorded in the PR. Freeze remains explicit; this Task adds no merge authority.
