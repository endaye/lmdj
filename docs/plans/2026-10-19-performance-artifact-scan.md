# #2402 main integration premises, before edits

Main 9b48e23f66b588c083bda7f497030080cf5263f0; original source 7719e29576c3af6f50a74ac18b629f3400b14b53.

- B0 already delivered by #2432 / 9b48e23f; current header/Native/Web range reader and owning tests are present. No repeated range implementation.
- The complete ProjectStore public header and implementation expose read_artifact/read_asset_artifact (positive control), but neither declares/defines scan_performance_recording or a bounded verified Performance selector/receipt. Whole-vector limit is retained. The scan Task remains outstanding on main.
- All seven existing inputs in the nine-file source delta are byte-identical to the original parent 01aba485; the two new paths are absent. The already-authored original bounded scan can be re-homed without importing stack ancestors or COUNT-IN changes.
- Current owner/history/writer and metadata-only load implementation is unchanged. Source snapshots caller request and revalidates exact owner/revision/binding after complete hash; preserve the alias and reentrant mutation tests.
- Live #2135 and comments retain B0/raw vs scan vs WAV/Facade/SDK/Host separation. #2403 and later PRs are unmerged downstream of #2402, not delivering this missing main API.
- #2430 remains pending the earlier owner exception; no manual closure or merge under this Task. #2433 concerns frozen release tools, excluded from this work.
- Original full native/browser selection and Task-specific semantic controls will be run on the refreshed integration. Old B0 WebKit lifecycle failures remain unexplained and explicitly retained. Candidate/device/audio/full-batch gaps remain.
- User now authorizes ordinary integration and proven-safe cleanup. Original published stack remains unchanged; create an independent replacement PR to main, authenticate exact-head review, protected squash then safe cleanup of the new integration resources only.

## Current integration verification

- Fresh integration Native production/test build PASS; original three baseline CTests PASS and all four final owning CTests PASS (10.09s). Independent digest and final-owner mutants each build successfully and fail their exact owning scan assertions (exit8), then source restored byte-exact with fresh mtime and actually recompiled; restored owning suite PASS.
- Emscripten6.0.5/Node26 official configure/build/build-project-io PASS, including no-testing-hook production link. Locked client1.62.1 Chromium6 PASS31.150s and supported OPFS WebKit2361 three PASS54.488s: no skipped/flaky/retry cases. Complete original common interruption/recovery, ownership and B0 raw-range journeys retained. New scan JSONs prove3 exact owner/revision/ref reports,3 physical digest/length/prefix/tail reads,3 closed pages/two reopens per browser, stale revision refusal and zero published writes/writers after scans.
- All eight code/test/Portal files retained the original7719e295 SHA256 bytes throughout actual verification. Only this integration plan receipt differs. Full Portal179tests/53pages/51routes PASS; dependencies, original Web timeout policy and staged ownership76 PASS.
- Precommit main refresh 9b48e23f66b588c083bda7f497030080cf5263f0; intervening Task paths 0, all seven applicable governance files unchanged. No premise reimplementation required.
- Historical original B0 WebKit lifecycle failures remain unexplained; no environmental closure, new pitfall incident or full candidate/device/hearing claim. Full Core/Creator/Runtime/sanitizer/batch lanes remain unexecuted.
- Current user authorization permits ordinary integration and safe cleanup; original published stack preserved, exact-head independent review and guarded merge still required. Original records and freeze statements below remain historical evidence.

---

# Verified bounded Performance recording scan — #2135 B

## Premises before edits

Integration main refreshed to `8c361623f2c1bf32460c32793a33a4d7e204fb7f`.
Task parent is frozen Draft #2401 at
`01aba485607e468259d14454c2bc64b06525d997`. Live #2112/#2135, comments and
all thirteen open Drafts were inspected. No successor owns the following scan.
The new isolated `feat/performance-artifact-scan` starts clean; all ten tracked
symlinks are actual links. One writer, no concurrent agents.

| Premise | Disposition and source |
| --- | --- |
| Raw bounded reads are missing | Already delivered on the stack by #2401: optional ProjectStorageRangeReader, Native/OPFS implementations and real browser reopens. Do not reimplement them. |
| Existing ProjectStore reads can serve long saved recording metadata | Still outstanding: read_artifact/read_asset_artifact materialize the entire vector and reject above64MiB. They retain those existing contracts. |
| Committed owner resolution is available | Reuse read_asset_artifact/inspect_committed's history-before-writer order, managed-tree validation and load_project(false). This reader verifies metadata/replay without reading unrelated audio and does not recover or scavenge. |
| Holding one lease is enough for arbitrary callbacks | Incomplete: the shared authoring-history mutex and same-platform writer leases are reentrant. A trusted consumer must not mutate/reenter, and final owner/revision/binding revalidation must reject an intervening reentrant mutation before returning a verification receipt. |
| WAV metadata is already bounded | False: cooker::inspect_wav calls decode_wav and allocates complete PCM. A bounded metadata parser and Facade/SDK/Host consumer remain required after this necessary Project I/O producer. |

The integration-main storage/cooker/Facade paths have not changed since the B0
audit. Main's COUNT-IN withdrawal #2396 is an independent integration divergence;
do not silently rebase, restore it, merge or infer an owner unfreeze.

## One Task / declared files

1. `packages/project-io/include/lmdj/project_io/project_store.hpp`
2. `packages/project-io/src/project_store.cpp`
3. `packages/project-io/CMakeLists.txt`
4. `tests/core/project_io/performance_recording_scan_test.cpp`
5. `tests/platform/web/project_io/project_io_web_test.cpp`
6. `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
7. `apps/docs-site/docs/core/modules/project-io.mdx`
8. `apps/docs-site/docs/platform/storage.mdx`
9. `docs/plans/2026-10-19-performance-artifact-scan.md`

Expand before touching another path. No storage implementation, existing read /
writer policy, Project Truth/format, WAV parser, Facade/SDK/Host, CI or manifest
change in this Task. Do not claim B or Take duration from the scan alone.

## API and implementation

Add `PerformanceRecordingSelector` (Project ID, Performance ID, expected Project
revision and exact ArtifactRef) and `PerformanceRecordingVerification` (same
owner, observed Project/recording revisions and exact verified ArtifactRef).
`ProjectStore::scan_performance_recording(bundle, selector, consumer)` holds the
existing history guard and one Project writer lease through committed owner
resolution, all selected raw bytes and final owner revalidation.
Snapshot bundle and selector at entry so callback activity cannot retarget the
in-flight identity through caller-owned aliases.

The synchronous consumer receives contiguous provisional spans valid only for
that callback. It must not retain the span, reenter or mutate Project state.
Only a successful final receipt proves complete bytes/digest for that owner;
consumer state from any failed call must be discarded. Later WAV parsing can
feed a bounded parser, retain its format error provisionally and continue the
complete hash before publishing either verified metadata or unsupported format.

Validate selectors, tree and committed owner before any selected audio read.
Missing owner/binding is NOT_FOUND; stale revision is REVISION_CONFLICT; absent
range capability is a typed unavailable I/O error, without whole-read fallback.
Resolve only committed metadata via load_project(false), with no recovery,
orphan cleanup or unselected audio reads. Expose no mutable Project or path to
the consumer.

Use a64KiB heap buffer, incremental SHA-256 and uint64 offsets. Permit positive
short reads with forward progress; reject zero progress before expected EOF or
an impossible returned count. Verify byte length before/after, probe one byte
at expected EOF, and compare the complete digest. No64MiB cap, decoded PCM,
file-sized buffer, hidden retry or second writer. Propagate storage/consumer
errors and retire this logical lease on every exit. Existing platform physical
close-failure custody/debt is unchanged; the scan receipt is not a physical
close acknowledgement. Re-read committed owner/revision/
binding before success, including the recording revision.

## Verification / defect ownership

- Baseline the original ProjectStore, Performance lifecycle and storage-platform
  suites before product edits. Keep all existing cases, deadlines and limits.
- New independent Native suite uses a forwarding observer over the real Native
  platform, not a replacement storage backend. Fix literal multi-window bytes,
  exact receipt/owner/revision/ref, continuous offsets and bounded requests.
  Prove the selected file never uses read_complete; metadata reads remain real.
- Test wrong Project/Performance/digest/type/length and stale revision before
  audio I/O; unbound/missing recordings; busy physical writer and missing range
  capability; length/digest corruption including a late chunk, EOF and short
  progress, typed read/consumer errors, and post-callback revision change.
  Original files/orphans and write inventory must remain unchanged on reads.
  Independent writer refusal during a callback and acquisition after return
  prove real lease custody and release.
- A real sparse PCM WAV above64MiB with independently computed digest proves
  the new scan is not constrained by the old vector-reader limit. Avoid reading
  it into the fixture's own vector. The normal component timeout remains.
- Mutate digest verification and final owner revalidation separately; each must
  fail its specific owning assertion. Restore exact source with a strictly
  newer mtime, rebuild and inspect terminal results before reporting GREEN.
- Actual C++/Wasm/Asyncify/OPFS probe scans a multi-chunk recording through the
  new ProjectStore API, checks fixed bytes/digest/owner and actual close/reopen
  twice. Retain the full selected common parity/interruption journey, owner /
  mount refusal and the original B0 range journey. Use the repository WebKit
  protocol wrapper from the first run, unique outputs and unchanged budgets.
- Full Portal, production Native/Wasm link, dependency/ownership and final PR
  body/declaration checks. Run Native/Wasm, browser and Portal heavy windows
  serially. Persist successful JSON by path and read back actual identities.
  Earlier B0 WebKit lifecycle failures remain an open review finding; a later
  pass does not identify their cause or prove candidate/device acceptance.

Refresh relevant main/successors before commit/publication. Inspect every staged
and committed path and final status; one Conventional Commit, push and Draft
successor of #2401 on the single stack. Independent current-head review remains
PENDING, with no self-waiver. No merge/auto-merge, release/tag/deployment/Channel
or Git cleanup while the owner freeze remains.

## Version Management

Version impact: additive Project I/O C++ API MINOR debt, deduplicated with B0 and
the actual compatibility-domain rollup in #2237. No persisted/public Facade/SDK
or cross-language Contract, Module dependency, manifest, Product/Assembly/Build
or immutable snapshot allocation.

## Documentation Impact

Documentation impact: required — `/core/modules/project-io/` and
`/platform/storage/`: provisional consumer bytes, verification receipt, exact
owner/revision/binding, bounded hash/EOF/failure/lifetime semantics and remaining
WAV/Facade/Host work. No new dependency or diagram edge.

## Recorded verification

- Original three Native suites passed before product edits. Final production
  Native build and all four owning CTests passed after the last source restore:
  ProjectStore, storage platform, Performance lifecycle and the new scan suite.
  The real70MiB sparse PCM WAV is73400364 bytes including its header; the old
  vector reader refuses it at its unchanged limit, while the bounded scan
  verifies the independent digest. New suite approximately5s; timeout unchanged.
- Digest-bypass mutant built successfully, then failed the late-byte corruption
  assertion at scan-test line229. Final-owner-bypass mutant built successfully,
  then failed the reentrant-revision assertion at line288. Each original source
  was restored with a strictly newer mtime and actually recompiled; both owning
  restored suites and the final complete four-test selection returned0.
- A first new-target build reported no target before CMake regeneration.
  Reconfiguration and subsequent actual build passed. This is setup history,
  not a product semantic RED; the two mutants above are the semantic proofs.
- Pinned Emscripten6.0.5/Node26 fixture, complete Project I/O build and production
  link without testing hooks passed. Chromium6/6 PASS in31.4s; supported OPFS
  WebKit2361 with locked client1.62.1 and the repository protocol wrapper3/3
  PASS in51.7s. Original common recovery/ownership/range journeys retained every
  leg and budget. New scan peak stack68564/262144 bytes on both browsers.
- Both successful scan JSON files were written, attached by path and read back:
  three full owner/revision/ref reports, three independent physical digest /
  length/prefix/tail checks, two actual reopens and three closed pages per
  browser; all reads report stale-revision refusal, zero published writes and
  physical writer count0 after completion. No WAV encoding/duration claim.
- Complete Portal, dependency check, ownership76 and Web timeout policy passed.
  Earlier B0 WebKit lifecycle timeouts remain open; these passes identify no
  cause or fix for them. Full batch/candidate and device/hearing remain unverified.

Precommit integration refresh remains
`8c361623f2c1bf32460c32793a33a4d7e204fb7f`; storage/cooker/Facade premises and
applicable governance unchanged. This Task supplies the missing bounded verified
recording input; #2135 B still requires WAV metadata and Facade/SDK/Host consumer.
Independent review remains PENDING and the owner freeze remains in effect.

Final input-boundary review found that a consumer could change the caller's
selector through an alias. A new real regression built successfully and failed
at `result.has_value()` before the fix. The call now snapshots both bundle and
selector at entry; the final regression retargets both caller-owned objects and
still requires complete bytes and a receipt for the original request. The final
production Native build and all four suites, rebuilt production/test Wasm,
Chromium6/6 (31.1s), WebKit3/3 (51.2s) and full Portal all passed again. New
successful JSONs and their complete identities were read back from unique
snapshot-final paths; earlier outcomes remain preserved.
