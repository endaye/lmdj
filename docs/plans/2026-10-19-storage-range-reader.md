# Bounded storage range reads — #2135 B0

## Premises before edits

Refreshed integration main: `f0979f2754faca2a2b26efae8c1a411608b2bbf0`.
Task parent: frozen Draft #2393, `a7954f87422f1d7e1faf9c49ca1b25ef7ee7038a`.
Live #2112/#2135, comments and all twelve open Drafts were inspected; no
successor owns bounded storage reads. Their relevant storage/cooker/Facade
source is unchanged from refreshed main. This isolated `feat/storage-range-reader`
starts clean with ten actual tracked symlinks and one writer.

| Premise | Disposition |
| --- | --- |
| Saved WAV metadata needs a public query | Still outstanding. The registry and real performance.list/inspect dispatch are known-positive controls; the list has recording_artifact/event_count, without recording metadata. This Task supplies a necessary lower-level capability and does not claim that query or B is delivered. |
| Existing Artifact reads are bounded | Contradicted: ProjectStore::read_artifact calls read_complete and hashes the full vector; cooker::inspect_wav calls decode_wav and allocates complete PCM. A 30-minute 48k stereo PCM16 payload is345600000 bytes before decoding. Do not use this as an eager list read or limit legitimate takes to smaller test files. |
| A suitable optional capability pattern exists | Delivered: ProjectStorageTextReader/ProjectJournalLayoutValidator preserve the original base vtable. Add a separate ProjectStorageRangeReader companion, keeping all existing complete-read paths unchanged. |
| Native range I/O can preserve path protection | Existing open_regular_file safely traverses ancestors, rejects symlinks/special files and acquires/revalidates a shared regular-file lock. Reuse it and perform bounded pread into the caller buffer plus post-read stable metadata validation. |
| OPFS must allocate an entire Blob | Not necessary: an immutable File snapshot supports slice(start,end).arrayBuffer for only the requested window. Keep original Asyncify admission, path lookup and error mapping. Use two uint32 offset words across Wasm so offsets above4GiB never wrap or lose precision. |
| Range bytes prove an Artifact/Performance fact | False. A range is raw, unverified input. A later owning consumer must hold the existing lease, resolve the committed Performance/revision/ref and verify complete bytes/digest before publishing WAV metadata. No whole-file atomic view, integrity, durability or writer authority is granted here. |

## One Task / declared files

- `packages/project-io/CMakeLists.txt`
- `tests/platform/web/project_io/CMakeLists.txt`
- `packages/project-io/include/lmdj/project_io/storage_platform.hpp`
- `packages/project-io/src/native/storage_platform.cpp`
- `packages/project-io/src/web/storage_platform.cpp`
- `packages/project-io/src/web/library_opfs_storage.js`
- `packages/project-io/src/testing_hooks.hpp`
- `tests/core/project_io/storage_platform_contract_test.cpp`
- `tests/platform/web/project_io/opfs_writer_error_test.mjs`
- `tests/platform/web/project_io/project_io_web_test.cpp`
- `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `apps/docs-site/docs/platform/storage.mdx`
- `docs/plans/2026-10-19-storage-range-reader.md`

Expand before editing another path. No ProjectStore query, WAV parser, Facade,
SDK/Host API, Project Truth/format, writer-control policy, CI, manifest or version
allocation change. The production link smoke must exclude new testing hooks.

Before editing build wiring, the real Chromium journey exposed the new import's
missing Asyncify registration (`Aborted(import lmdj_opfs_read_range was not in
ASYNCIFY_IMPORTS, but changed the state)`). Expand to the two owning CMake files
above: production and test-module lists plus the standalone production-link
fixture must register the same new suspending import. No CI policy or gate change.

## API and implementation

`ProjectStorageRangeReader::read_range(path, uint64_t offset, span<byte> output)`
returns the actual prefix count, bounded by output.size. EOF/beyond EOF and an
empty destination return0 after ordinary path/file validation. A short final
window leaves the rest of the buffer untouched. Failure is typed; any copied
bytes on failure are untrusted. No reader/descriptor cache survives a call.

The companion is discovered from a platform kept alive by its existing owner.
Legacy platform implementations remain valid without the capability; no new
pure virtual slot is added to ProjectStoragePlatform. There is no whole-file
fallback and no hidden retry, timer, hash or write. Native and OPFS implement
the same bounded caller-buffer behavior. Existing whole reads retain their
original retry/ownership/representation contracts.

Native reuses safe open/shared-lock custody, reads at most the available
requested bytes and rejects a changed file after the read. A test-only hook
permits an actual filesystem size change after data read; production contains
no hook. OPFS resolves a fresh File, compares the exact uint64 offset before
Number conversion, slices only the available requested interval and copies
through the current HEAPU8 after await (memory may grow). It never calls the
whole File's arrayBuffer or allocates a file-sized Wasm buffer.

## Verification / defect ownership

1. Baseline: complete existing Native storage-platform contract test and Node
   OPFS boundary tests. Declare the companion and new owning tests before
   implementations; record a real Native missing-capability RED and a Node
   missing-entry RED, not a compiler/setup failure as a semantic proof.
2. Native owning tests fix exact binary windows and destination canaries,
   EOF/empty/missing/unsafe paths, offsets above4GiB without wrap, fresh reads
   after replacement, rejection after a real metadata change, and absence of
   complete-read fallback with a positive-control whole-read fault. Run every
   original storage contract test unchanged, including lock/replacement/FIFO
   cases; no looser deadlines or thresholds.
3. Node executes the production library entry using real Blob slices and an
   instrumented browser file boundary. A whole-file arrayBuffer is forbidden;
   assert exact requested windows, count/buffer boundaries, EOF and errors,
   high/low offset fidelity, fresh snapshots and HEAPU8 replacement across await.
   Retain every original writer/ownership test. Real browser proof separately
   covers the actual C++/Wasm/Asyncify/OPFS boundary.
4. Add an independent C++ range probe and actual browser assertions to the
   existing conformance fixture without changing the common parity report.
   Create bytes through the existing authorized writer path, then prove exact
   binary reads, tail/EOF, zero-length validation, no new writer ownership and
   a fresh browser reopen. Assert fixed expected bytes alongside any producer /
   consumer agreement, preserving the named journey's far-side legs.
5. A wrong Native offset and a whole-file Web read source mutant must each
   fail their owning semantic assertion. Restore exact source bytes with a
   strictly newer mtime, rebuild the affected Native artifact and read actual
   terminal results before claiming restored GREEN. Never commit a mutant.
6. Native owning suite; pinned Emscripten6.0.5/Node26 Project I/O build and
   production-link smoke; complete selected OPFS common-parity/interruption,
   owner/mount refusal and new range journeys in the locked supported browsers.
   Browser capability refusal is not product/physical acceptance. Persistence /
   recovery legs of selected journeys remain complete; no test budget shrink.
7. Full Portal, offline dependencies, final staged/committed ownership and
   PR body/declaration checks. Native/Wasm, browser and Portal heavy windows
   run serially. Full batch/candidate lanes remain explicitly unverified.

Persist successful JSON by output path and read back its actual bytes/state;
retain failures and distinguish Node models, native files, real OPFS, review,
integration, candidate and device evidence. B0 has no user-visible duration;
continue with the bounded verified owner/Artifact scan, WAV metadata and
Facade/SDK/Host consumer after this prerequisite.

Before commit and publication refresh relevant main/history, inspect the full
staged diff, exact committed files and final status. One Conventional Commit
and one Draft successor of #2393; no merge/auto-merge, release, deployment,
Channel or resource cleanup while frozen. Independent current-head review is
PENDING, without a self-waiver. Product regression tests own these facts;
record a process pitfall only if a qualifying non-product invariant is learned.

## Version Management

Version impact: additive optional Project I/O C++ API MINOR debt in #2237,
deduplicated within its actual compatibility domain. The existing storage base
vtable and complete-read entry points do not change. OPFS glue ships with its
matching generated loader/Wasm; no new public Facade/SDK or cross-language
Contract is introduced. No manifest, Product/Assembly/Build or snapshot allocation.

## Documentation Impact

Documentation impact: required — `/core/modules/project-io/` and
`/platform/storage/`. Document bounded raw input, offset/buffer/error/lifetime
semantics and the still-outstanding verified Performance/WAV consumer. No
Module dependency or diagram edge changes; no duration/ownership claim from
raw range success.

## Recorded verification

- Original Native baseline PASS (27 scenarios); missing-companion test RED at
  `reader != nullptr`, with a successful build. Final Native owning CTest PASS
  (33 scenarios), including every original body unchanged. Production Native
  `lmdj_project_io` builds without the test macro. The missing-file test follows
  the existing Native IO_ERROR plus ENOENT detail; Web retains NOT_FOUND.
- Original Node baseline14 PASS; missing-entry RED; final20 PASS. Ignoring the
  Native offset fails the literal binary window; taking a whole Web File slice
  fails the owning Node windows. Both exact sources were restored with fresh
  mtimes; restored Native compilation and complete owning suite, and restored
  Node suite, all terminal0. No mutant was committed.
- Pinned Emscripten6.0.5/Node26 configuration and full Project I/O fixture plus
  production link PASS. First real Chromium run caught the missing Asyncify
  registration (four existing journeys passed, new range journey failed).
  Both CMake import owners were declared and corrected before rebuilding.
- Corrected Chromium selection5/5 PASS: range/reopens, common parity and every
  original interruption/recovery leg, same-page ownership, cross-realm writer
  and untouched v5. Supported OPFS WebKit2361 with the locked1.62.1 client and
  repository protocol wrapper: final2/2 PASS in48.2s, including complete common
  recovery and the range journey. Parent #2393 common recovery control PASS
  in46.2s with the same browser/wrapper. No budgets, predicates or legs changed.
- Retain two earlier WebKit common-recovery timeouts: the first stopped awaiting
  controller `Page.close` after a successful recovery; the second stalled on a
  later navigation until teardown. Their new range journeys both passed. The
  terminal canonical pass does not identify or fix those intermittent lifecycle
  failures. Their traces/logs remain; integration/candidate review must retain
  this finding rather than attribute it to environment without evidence.
- Successful range JSONs are written and attached by path, then read back:
  literal binary bytes, all three reports, two actual page reopens, three closed
  pages and physical writer counts0/0. Full Portal, dependency check, Web timeout
  policy and ownership76 PASS. Full batch/candidate lanes and device/hearing
  acceptance remain unverified; source/Task results do not discharge them.

The API is only B0. Verified owner/Artifact scanning, bounded WAV metadata and
Facade/SDK/Host consumption remain open under #2135. Independent review is still
PENDING; the main freeze and the unresolved WebKit lifecycle finding remain
explicit integration boundaries.

Precommit refresh: integration main advanced to `8c361623f2c1bf32460c32793a33a4d7e204fb7f` through release
allocation/snapshot work and the independent COUNT-IN withdrawal #2396. No
declared B0 path, ProjectStore/cooker/Facade premise or applicable governance
changed. #2393 remains an OPEN Draft at the exact parent. Preserve the stack;
the upstream COUNT-IN withdrawal requires separate reconciliation before future
integration, not a silent replay/rebase or a lift of the owner freeze.
