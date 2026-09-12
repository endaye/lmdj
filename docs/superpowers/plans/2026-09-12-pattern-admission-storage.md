# Pattern Admission Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not use brainstorming: the user explicitly prohibited it.

**Goal:** Supply durable bounded admission candidates, exact fence outcomes and idempotent canonical-tail transfer for global Pattern recording under #1230.

**Architecture:** Extend the existing Sequence journal, checksum envelope, writer lease and recovery lifecycle. A transfer atomically records the complete replacement recoverable tail and its source receipt; it never reenqueues live input. Sequence adopts the new format directly, without backward compatibility.

**Tech Stack:** C++20, existing ProjectStoragePlatform, nlohmann JSON, native CTest, Emscripten 6.0.5, Node 22, locked Playwright 1.62.1 and real OPFS.

**Spec:** [Durable Pattern recording admission](../specs/2026-09-12-pattern-admission-storage-design.md), subordinate to sections 5–6 of [global transport](../specs/2026-09-11-global-pattern-transport-design.md).

## Global Constraints

- Full migration #1207 remains U0–U8. This plan supplies storage, not the Facade coordinator, runtime adapter or finished Creator controls.
- Pre-release demo: no legacy Sequence reader/writer, compatibility harness, migration utility or bulk project conversion. Do not delete existing user data.
- Preserve Performance journal behavior and unrelated Project bundle formats.
- Hosts use Application Facade; no audio-thread IO and no Project Truth transport metadata.
- Keep #725 live successful/failed/unknown results and existing per-slot release ownership. Storage stores identities, not acoustic acceptance.
- Original input identity is distinct from journal input sequence. No sequence advancement on unknown append; no live-input replay.
- Existing `append_tail` receives a complete canonical recoverable tail. Transfer also replaces this tail; it must not append that whole tail to itself.
- Record-off retains playback; Play/Stop stops at audio cutoff before IO flush. Storage never reverses an applied audio effect.
- Missing historical fences remain unresolved. No guessed origin, switch outcome or auto-start after restart.
- Use isolated task branches and one reviewable Conventional Commit per Task; no history rewrite or cleanup. Follow issue-done for shipping and exact-head review. CI repair belongs to the other agent.

## Baseline and file responsibilities

Base design commit: `e470d8620c8e2f1d2dc7ef58b1d558b3385ca744`; product source is its parent `bbdf8d71ecb7641d1f9b6c8915905b4117cad06d`.
Existing `project_io.sequence_journal` passed 1/1, 1.81 s. No new feature test has run.

- `packages/project-io/include/lmdj/project_io/sequence_admission.hpp` (new): typed storage records, bounds and checkpoint; no audio-runtime dependency.
- `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`: journal methods and optional admission state at the end of ActiveSequenceJournal.
- `packages/project-io/src/sequence_admission_codec.hpp` and `.cpp` (new): internal JSON codec and pure transition validation. Keep JSON out of the public API.
- `packages/project-io/src/sequence_journal.cpp`: lease-protected appends, replay dispatch, new Sequence format, snapshot/sealing/completion integration.
- `packages/project-io/src/project_store.cpp`: preserve unfinished admission during owner-loss reconciliation.
- Existing native and browser tests own fault/reopen evidence; no new test framework or CI gate.

## Shared storage interface

Names below are the contract between the storage Task and its later Facade consumer.
All UUID wrapper types come from existing Foundation headers; PadSlotId and
PatternEvent come from Authoring Domain. Public types are in `lmdj::project_io`.
Each struct has defaulted equality, enabling complete-payload duplicate checks.

```cpp
inline constexpr std::size_t kSequenceAdmissionMaxCandidates = 1024;
inline constexpr std::size_t kSequenceAdmissionCandidateBytes = 1024 * 1024;
inline constexpr std::size_t kSequenceAdmissionTransferBytes = 1024 * 1024;
inline constexpr std::size_t kSequenceAdmissionControlBytes = 64 * 1024;
inline constexpr std::uint32_t kSequenceAdmissionFenceTimeoutMs = 5000;

enum class SequenceCandidateKind : std::uint8_t { press, release };
enum class SequenceFenceKind : std::uint8_t { admission, cutoff };
enum class SequenceSwitchOutcome : std::uint8_t {
  none, applied_before_cutoff, canceled_at_cutoff
};
enum class SequenceAdmissionCloseReason : std::uint8_t {
  requested, capacity, deadline, storage_failure, owner_lost
};

struct SequenceAdmissionIdentity {
  foundation::CommandId operation_id;
  std::uint64_t runtime_generation{};
  std::uint64_t transport_epoch{};
};
struct SequenceAdmissionPreparation {
  SequenceAdmissionIdentity identity;
  foundation::ProjectId project_id;
  foundation::PatternId pattern_id;
  std::uint64_t publication_generation{};
  std::uint64_t first_watermark{};
  std::uint32_t candidate_limit{kSequenceAdmissionMaxCandidates};
  std::uint32_t candidate_byte_limit{kSequenceAdmissionCandidateBytes};
  std::uint32_t fence_timeout_ms{kSequenceAdmissionFenceTimeoutMs};
};
struct SequenceAdmissionCandidate {
  std::uint64_t watermark{};
  std::uint64_t runtime_frame{};
  domain::PadSlotId slot;
  SequenceCandidateKind kind{};
  std::uint8_t velocity{};
  std::uint64_t press_sequence{};
};
struct SequencePublicationAuthority {
  foundation::PatternId pattern_id;
  std::uint64_t generation{};
  std::uint64_t frame{};
};
struct SequenceAdmissionFence {
  SequenceFenceKind kind{};
  foundation::CommandId command_id;
  std::uint64_t transport_epoch{};
  std::uint64_t effective_frame{};
  std::uint64_t origin_frame{};
  foundation::PatternId pattern_id;
  std::uint64_t publication_generation{};
  std::uint16_t bpm{};
  bool playing{};
  std::optional<SequencePublicationAuthority> switch_authority;
  SequenceSwitchOutcome switch_outcome{};
  std::optional<std::uint64_t> switch_applied_frame;
};
struct SequenceAdmissionClosure {
  std::optional<std::uint64_t> last_retained_watermark;
  SequenceAdmissionCloseReason reason{};
};
struct SequenceOwnedPress {
  domain::PadSlotId slot;
  std::uint64_t press_sequence{};
  std::uint64_t raw_attack_tick{};
  std::uint32_t onset_tick{};
  std::uint8_t velocity{};
};
struct SequenceAdmissionCheckpoint {
  foundation::PatternId pattern_id;
  std::uint64_t publication_generation{};
  std::uint64_t last_runtime_frame{};
  std::vector<SequenceOwnedPress> owned_presses;
};
struct SequenceCandidateReceipt {
  std::uint64_t watermark{};
  std::string payload_sha256;
};
struct SequenceAdmissionTransfer {
  foundation::CommandId transfer_id;
  bool terminal{};
  std::uint64_t first_watermark{};
  std::uint64_t last_watermark{};
  std::string candidates_sha256;
  std::vector<SequenceCandidateReceipt> candidate_receipts;
  foundation::PatternId pattern_id;
  std::uint64_t expected_revision{};
  std::optional<std::uint64_t> journal_input_sequence;
  std::vector<domain::PatternEvent> recoverable_tail;
  SequenceAdmissionCheckpoint checkpoint;
};
struct SequenceAdmissionState {
  SequenceAdmissionPreparation preparation;
  std::vector<SequenceAdmissionCandidate> candidates;
  std::optional<SequenceAdmissionFence> admission_fence;
  std::optional<SequenceAdmissionFence> cutoff_fence;
  std::optional<SequenceAdmissionClosure> closure;
  std::vector<SequenceAdmissionTransfer> transfers;
  std::vector<SequencePublicationAuthority> applied_switches;
  std::uint64_t segment_generation{};
  bool completed{};
};
```

`press_sequence` is the original accepted press sequence, not a new gesture ID.
A release with no correlated press uses zero and cannot acquire journal ownership.
The runtime adapter must verify it can supply that existing correlation without
changing routing; that is a separate integration gate, not a storage assumption.

Append `std::optional<SequenceAdmissionState> admission;` to ActiveSequenceJournal.
Add these methods to SequenceJournal, each returning `foundation::Result<void>`:

```cpp
prepare_admission(const std::filesystem::path& bundle,
                  foundation::SequenceSessionId session,
                  const SequenceAdmissionPreparation& preparation);
append_admission_candidate(const std::filesystem::path& bundle,
                  foundation::SequenceSessionId session,
                  const SequenceAdmissionIdentity& identity,
                  const SequenceAdmissionCandidate& candidate);
retain_admission_fence(const std::filesystem::path& bundle,
                  foundation::SequenceSessionId session,
                  const SequenceAdmissionIdentity& identity,
                  const SequenceAdmissionFence& fence);
retain_admission_switch(const std::filesystem::path& bundle,
                  foundation::SequenceSessionId session,
                  const SequenceAdmissionIdentity& identity,
                  const SequencePublicationAuthority& authority);
close_admission(const std::filesystem::path& bundle,
                  foundation::SequenceSessionId session,
                  const SequenceAdmissionIdentity& identity,
                  const SequenceAdmissionClosure& closure);
transfer_admission_prefix(const std::filesystem::path& bundle,
                  foundation::SequenceSessionId session,
                  const SequenceAdmissionIdentity& identity,
                  const SequenceAdmissionTransfer& transfer);
complete_admission(const std::filesystem::path& bundle,
                  foundation::SequenceSessionId session,
                  const SequenceAdmissionIdentity& identity);
```

Inspection uses existing `read_active` and sealed recovery, not another service.
`transfers` is durable journal history for exact retry, not an unbounded unresolved
candidate buffer. Candidate limits apply to the unresolved set; immutable journal
history grows under the existing session lifecycle. Never claim the entire recording
file has a fixed size. Bound each decoded record before allocating its arrays.

`retain_admission_switch` stores an acknowledged ordinary applied boundary before
source flush/switch. Its authority frame is actual, not scheduled. Ordered
`applied_switches` retain immutable generation identities; generations strictly
increase, frames never decrease, exact retries reconcile durably, and collisions
fail. Only one boundary may be ahead of the durable journal segment at a time.
`segment_generation` starts at preparation publication generation and advances only
when the existing journal switch reconciles a retained boundary. Checkpoints must
match that segment generation, including P->Q->P without any Q transfer. History
follows the session lifecycle with per-control-record bounds, not candidate limits.

## Task S1: Durable records, atomic transfer and recovery ownership

**Files:** All six product files in the responsibility map; modify
`packages/project-io/CMakeLists.txt`,
`tests/core/project_io/sequence_journal_test.cpp`,
`tests/core/project_io/session_mutual_exclusion_test.cpp`,
`apps/docs-site/docs/core/modules/project-io.mdx`.
No Product Build allocation. Add the codec source to both production and testable
source lists. Existing storage fault hooks suffice unless a test proves otherwise.

**Consumes:** Existing begin/read/append_tail/flush/recovery methods, checksum
envelope and `ProjectStoragePlatform::append_durable` under the journal writer lease.
**Produces:** The complete shared interface above, exercised through native storage.

- [ ] Add types and declarations, then write a native `admission_candidate_reopens`
  test using the existing TempDirectory and UUID fixture constants. Create a normal
  journal, prepare admission with generation 1 / epoch 1 / first watermark 10, append
  press `{10, 1000, {0,0}, press, 100, 7}`, destroy the journal object and construct a
  new one on the same directory. Assert complete preparation/candidate equality,
  unchanged `pending_events`, and no `last_input_sequence` advancement.

```cpp
const auto reopened = SequenceJournal{}.read_active(directory.path());
LMDJ_CHECK(reopened.has_value());
LMDJ_CHECK(reopened.value().admission.has_value());
LMDJ_CHECK(reopened.value().admission->candidates ==
           std::vector<SequenceAdmissionCandidate>{candidate});
LMDJ_CHECK(reopened.value().pending_events.empty());
LMDJ_CHECK(!reopened.value().last_input_sequence.has_value());
```

- [ ] Build/run the native command below and retain the expected missing-method
  failure. Implement the codec and lease/read/validate/append/replay flow, then run
  the same command to green. Pure codec transitions run before append on a copy;
  return storage errors without treating the tentative copy as durable state.

```bash
cmake --build --preset dev --target lmdj_sequence_journal_tests lmdj_session_mutual_exclusion_tests
ctest --preset dev --output-on-failure -R '^project_io\.(sequence_journal|session_mutual_exclusion)$'
```

- [ ] Replace only Sequence active/recovery discriminators with
  `lmdj.sequence.journal.v2` and `lmdj.sequence.recovery.v2`; these remain internal
  journal discriminators, not newly allocated public bundle Contracts. Keep current
  flush payload version 2, remove legacy Sequence payload-version fallbacks, and
  require writer-produced fields in new snapshots. Update the checksummed mutual
  exclusion fixture using canonical JSON plus SHA-256, not hand-edited stale hashes.
  Rewrite legacy-acceptance Sequence tests into unsupported-format rejection tests;
  retain Performance and Project bundle compatibility tests unchanged.

- [ ] Implement validation before mutation: valid UUIDs and current session,
  Project identity checked against manifest, nonzero generation/epochs/publication,
  current Pattern authority, bounds, slot bank<4/pad<16, press velocity 1–127,
  release velocity 0, and strictly increasing watermarks. First watermark is a
  lower bound, not a requirement of consecutive values: noncandidate input may
  consume watermarks. Exact duplicate payload is success without appending bytes;
  same identity with changed payload fails. Reconcile ambiguous writes by reading
  the existing journal under its lease before retrying.
  Transfer history retains each consumed candidate's watermark and canonical
  payload hash. Candidate retries after transfer compare against that receipt;
  removing the unresolved candidate must not erase its deduplication evidence.

- [ ] Implement two independent immutable fence slots: admission and cutoff.
  Admission epoch equals preparation epoch; cutoff epoch must be later. All belong
  to the preparation's runtime generation. Same-slot replacement is forbidden.
  Validate origin<=effective frame, valid BPM, and complete switch evidence:
  `none` has no authority/applied frame; applied has S<F; canceled has authority
  but no applied frame. Storage does not derive an audio outcome from these fields.

- [ ] Enforce limits on outstanding candidate count and canonical encoded bytes.
  Streaming preflight must bound unknown envelope/payload arrays before DOM
  construction as well as known admission fields, without capping the entire
  historical session. New active tail/flush event fields must be arrays.
  Admit at most 1024 candidates / 1 MiB. Reserve 1 MiB for transfer and 64 KiB for
  both fence records plus closure/completion. A candidate that consumes the final
  available count/byte slot writes its capacity closure in the SAME envelope, so
  a crash cannot leave the final slot occupied with admission falsely open. A
  candidate that cannot fit is refused without mutation; coordinator closes at
  the previous watermark using reserved control space before accepting another.
  Allow test preparations with smaller limits; reject limits above hard caps.
  Deadline is a 5000 ms monotonic coordinator policy, not a persisted wall-clock
  timestamp. Project IO validates/stores the policy and explicit closure only.

- [ ] Implement transfer as one record, with this replay order on a temporary state:

```text
find exact contiguous prefix of outstanding candidate records by watermark
verify SHA-256 of canonical JSON candidate array, first/last and session identity
verify every per-candidate receipt against the corresponding canonical payload
require durable admission authority; require cutoff authority for terminal drain
validate target Pattern/revision against current journal after any switch reconciliation
validate complete canonical recoverable_tail with existing append_tail rules
validate <=64 unique owned slots and checkpoint Pattern/ticks/velocity
replace pending_events with recoverable_tail (do not concatenate)
advance journal sequence only when a new sequence is present and valid
retain immutable transfer payload; remove exactly its source prefix
retain checkpoint; publish all these changes only after the single durable append
```

  An excluded-input-only transfer has null journal sequence, an unchanged tail and
  unchanged checkpoint. A held-press transfer can update its checkpoint/tail using
  the existing recoverable unreleased-note projection. Later duplicate transfer
  lookup precedes freshness checks so an already durable result can be recovered
  after revision advancement; a conflicting payload still fails. New transfers
  must pass current revision validation. Do not call append_tail and then append
  a second transfer receipt: that leaves the crash gap this Task must remove.

- [ ] Add an explicit empty-source terminal variant (`terminal=true`). Require
  first_watermark=last_watermark=0, empty candidate_receipts, and candidates_sha256
  equal to SHA-256 of canonical JSON `[]`. The explicit flag distinguishes this
  from an actual watermark-zero candidate. Require both durable fences, closure
  and no outstanding candidates. Require empty resulting owned_presses and null
  journal_input_sequence: terminal finalization is not another input. Replace the
  recoverable tail using the Facade-supplied existing unreleased-note finalization,
  preserve last_input_sequence, and retain the receipt atomically. No other new
  transfer is permitted after a terminal transfer; exact retries still reconcile.
  `complete_admission` requires that terminal receipt and known completed flushes.
  Add regression: transfer held press -> drain all candidates -> retain cutoff and
  close -> terminal transfer -> reopen -> exact retry -> flush/complete -> admission
  completion. Assert empty ownership, one canonical tail, unchanged input sequence
  and no synthetic release. Ordinary excluded-input transfers keep terminal=false
  and cannot use this checkpoint-clearing exception.

- [ ] Prevent bypasses: while admission is incomplete, direct append_tail cannot
  replace the managed tail. Existing flush/switch operations are permitted only
  after the relevant outstanding prefix has drained; they cannot consume unknown
  candidates. Completion requires both fences, closure, no outstanding candidates,
  no owned presses and known completed canonical flushes. Plain journals without
  admission continue current Sequence operations using the new format.

- [ ] Retain ordinary applied-switch authority before source flush/switch, bound
  to preparation operation/runtime identity. Reject a switch before mutation when
  its exact authority is missing. Drain source candidates before S; target-side
  candidates at/after S may remain across source flush/switch. Preserve the S<F
  cutoff route, reject conflicting ordinary/cutoff authority and never turn a
  canceled S>=F boundary into an applied switch. Initialize the target checkpoint
  from its retained Pattern/generation/actual frame, not Pattern identity alone.
  Prove ordinary P->Q with both candidate sides, source flush, target transfer,
  reopen and later no-pending-switch cutoff/terminal; P->Q->P without intermediate
  transfers; duplicate/collision/unknown-sync receipts; and unchanged held-terminal
  and S<F regressions. Persist/validate history and reconciled generation in sealing.

- [ ] Add independent native regressions for exact retry with unchanged file size;
  collision; generation/session mismatch; invalid watermark and integer extremes;
  withheld fence; final-slot atomic closure; full count/bytes; no candidate after
  closure; two immutable decisions; transfer-lost-response reopen with one tail;
  held checkpoint persistence; no-sequence excluded prefix; torn candidate/fence/
  transfer; write failure before append; and pending admission with empty event list.
  For each failure assert retained bytes/state, not merely a failure return.

- [ ] Extend snapshot serialization/parsing, seal/list and completion checks in the
  same change. Add `admission && !admission->completed` to ProjectStore's recovery
  pending predicate. Test a completed old flush plus unresolved admission and empty
  pending_events: owner loss must seal the admission, not remove it. Test unsupported
  active and sealed data rejection with byte-identical files. Do not add old readers.

- [ ] Update the Project IO portal section with the implemented storage-only scope,
  hard bounds, atomic replacement-tail transfer and missing-runtime recovery behavior.
  State explicitly that global transport integration remains pending. No identities
  entered manually. Run native component and existing stress plus portal checks:

```bash
ctest --preset dev --output-on-failure -R '^project_io\.(sequence_journal|sequence_journal_stress|session_mutual_exclusion|session_mutual_exclusion_stress)$'
scripts/docs-site.sh check
```

- [ ] Stage only S1 declared files, run `git diff --cached --check` and
  `python3 tests/build/ci_change_scope_test.py`, inspect complete diff and commit
  `feat(project-io): retain durable Pattern admission and transfer receipts`.
  Get independent review before S2. S1 alone does not satisfy browser acceptance.

## Task S2: Real OPFS interruption and reopen proof

**Files:** `packages/project-io/CMakeLists.txt`,
`tests/platform/web/project_io/project_io_web_test.cpp`,
`tests/platform/web/project_io/project_io_web_conformance.spec.mjs`,
`tests/platform/web/project_io/project_io_web_faults.mjs`,
`tests/platform/web/project_io/opfs_browser.fixture.mjs`,
`apps/docs-site/docs/core/modules/project-io.mdx`.
Use existing worker/fault bridge. If an actual missing production capability is
found, stop S2 testing edits and fix that defect in S1-owned code with its own red
regression; do not emulate successful durability in JavaScript.

**Consumes:** S1 public interface and existing real OPFS worker interruption hooks.
**Produces:** Reopen evidence through browser-backed ProjectStoragePlatform, not a
native/mock substitution.

- [ ] Add worker scenario operations that prepare, append, retain a fence, transfer,
  close and inspect using the actual C++ API. Return full identity/state summaries
  through the existing report channel. Generate fixture records via S1 writers.
  Expose no test-only controls in production targets.
- [ ] Add a Playwright journey that waits for the existing after-flush observation,
  terminates the writer Worker before its response, creates a new worker against
  the SAME OPFS directory and retries the exact transfer. Assert one consumed prefix,
  complete tail equality, exact sequence and unchanged immutable receipt. Do not
  graceful-stop the writer in the crash leg.

```text
prepare -> append press/release -> persist admission fence
-> append transfer -> observe storage flush -> terminate before reply
-> reopen same directory -> inspect exact transfer -> retry same payload
-> inspect one tail and one transfer -> reopen again -> same result
```

- [ ] Exercise analogous lost-response boundaries for candidate and fence append,
  and distinguish write failure before flush from response loss after flush. Assert
  no fabricated durable suffix. Add quota failure using existing storage-condition
  fault injection and record that it proves error handling, not physical disk-full
  hardware behavior.
- [ ] Exercise smaller-limit final-slot closure, candidate refusal after closure,
  withheld fence plus abrupt owner loss and seal/list reopen. Assert unresolved
  identity remains and canonical events were not guessed. Exercise old/unknown
  discriminator rejection without file mutation using the NEW reader only.
- [ ] Run the stable real-browser proof (Chromium and WebKit) with pinned toolchain:

```bash
scripts/web-toolchain-conformance.sh build-project-io
scripts/web-toolchain-conformance.sh proof
```

  Retain each process handle and collect its terminal result. Unsupported OPFS,
  missing browsers or toolchain failure is not a pass; keep the precise acceptance
  gap and resolve it without dropping a browser or widening timeouts.
  User-authorized environment adjustment: the locked Linux WebKit does not expose
  OPFS. Keep the pinned SDK and Playwright client; explicitly set
  `LMDJ_WEBKIT_OPFS_EXECUTABLE` to an independently installed OPFS-capable WebKit
  for Project IO only. Use a fresh persistent profile per test and retain the
  same-context crash/reopen journey. Record the exact browser build separately
  from the locked client's version. Without this opt-in the default remains
  unchanged and missing OPFS is still a failed S2 assertion. The portal documents
  the isolated installation and the same full proof command; no mocked storage,
  test exclusions or product dependency upgrade are permitted by this adjustment.
  The Project IO CMake exception flags are the scoped correction for real
  malformed-record rejection paths aborting in Emscripten; they do not claim
  exception support for every dependency module.
- [ ] Update portal evidence to distinguish tested storage semantics from pending
  runtime integration. Run `scripts/docs-site.sh check`, inspect/stage only S2 files,
  `git diff --cached --check`, and commit
  `test(project-io): prove admission recovery through OPFS interruption`.
  Independent exact-head review and issue-done shipping apply. Retain #1230/#1207.

## Required downstream integration, not claimed by S1/S2

Storage cannot validate live enqueue or apply audio effects. The next coordinator/
adapter plan must consume this seam and cover all of the following, without changing
the user's approved button behavior:

| Requirement | Owning source and far-side proof |
| --- | --- |
| Prepare before stopped Record; playing Record retains origin | Facade application/control runtime; both actual audio state and durable admission |
| Original press correlation, refusal/partial/unknown outcome | control_runtime.cpp and runtime_session tests; unchanged #725 result, no second enqueue |
| Five-second deadline and capacity close before next candidate | coordinator continuation tests; persisted B, later input live-only, truthful error |
| Persist receipt before audio acknowledgment | coordinator crash/retry; original immutable decision retained before receipt release |
| Pre-admission held press; cutoff-owned press release | Facade sequence tests; no orphan and unchanged sixteenth-tick finalization |
| S<F / S=F / S>F | Facade/runtime journal segments after delayed decision; never a segment beyond terminal F |
| Transfer checkpoint restores musical conversion | Facade recovery; full reopened Pattern event equality, not just storage record equality |
| Async lane and lifecycle barrier | runtime session; live input progresses between continuations, navigation continuity, explicit shutdown reconciliation |
| Same-Pattern committed replacement | Audio integration; preserve phase/voices or truthful pending publication after durable commit |

This table keeps integration gaps explicit; it does not reduce the parent spec or
authorize closing the capability Issue after storage tests pass.

## Version Management

Version impact: none for this plan-only change. S1 changes the public C++ journal
layout/API and directly replaces internal Sequence formats. Treat that as a staged
breaking Project IO change requiring next-MAJOR/API assessment and coherent consumer
rebuild before distribution, alongside the already staged audio change. Do not
guess or allocate module/Product Build identities here. The subsequent coordinated
assembly/version Task must follow repository version policy; demo clean-break
authorization removes compatibility work, not identity governance.

## Documentation Impact

Documentation impact: none for this plan-only change; proposed work is not a current
portal feature. S1 and S2: Documentation impact: required.
Affected portal pages: `/core/modules/project-io/`.
No diagram topology changes are intended: storage stays in existing Project IO.
If implementation changes ownership topology, update its source diagram and derived
artifacts in that same Task rather than omitting the documentation impact.

## Plan self-review and execution status

Clean-break format, identity, bounds, transfer, recovery and native/OPFS requirements
map to S1/S2. Musical admission/transport requirements map explicitly to the downstream
table and remain open under #1230. No implementation step or acceptance checkbox is
complete. Use the existing authorized subagent execution workflow; no additional
user confirmation or brainstorming gate is requested.
