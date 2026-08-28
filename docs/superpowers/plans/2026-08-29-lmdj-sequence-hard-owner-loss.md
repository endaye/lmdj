# Stage 9 Sequence Hard Owner-Loss Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this single Task inline. Preserve
> the RED/GREEN evidence and finish with the repository `issue-done` pitfall
> audit and one local Conventional Commit.

Date: 2026-08-29

Status: implementation

Issue: [#373](https://github.com/endaye/lmdj/issues/373)

**Goal:** Ensure every acknowledged Sequence pad event has a durable journal
tail so a non-graceful owner death produces one fingerprint-gated
`owner_lost` recovery candidate containing the accepted unflushed performance.

**Architecture:** Project I/O extends the append-only, checksummed Sequence
journal with monotonic full-tail snapshots. The Application Facade computes the
post-event runtime state on a copy, durably appends its canonical recoverable
tail, and only then publishes the in-memory state and acknowledges the event.
Flush consumes the durable tail into the existing pending-flush record, so
restart reconciliation has one source for each uncommitted event and can never
apply it twice.

**Tech Stack:** C++20, native/OPFS `ProjectStoragePlatform`, nlohmann JSON,
CMake/CTest, Docusaurus Architecture Portal.

## Global Constraints

- SR-D17 remains authoritative: owner loss never writes uncommitted events to
  Project Truth automatically; it seals a recovery candidate for explicit
  fingerprint-gated apply or discard.
- SR-D21 remains authoritative: manifest publication plus reload-visible
  receipt is the only flush commit point.
- A successful `record_sequence_event` response occurs only after the
  corresponding recoverable tail snapshot is durably appended.
- A press is represented recoverably with the existing 240-tick unreleased
  default; its matching release replaces the duration in the next tail
  snapshot.
- Tail snapshots use strict monotonic input sequence and canonical Pattern
  events. A flush record consumes the current tail in the same append-only
  journal chain.
- A partial record without its terminating newline, malformed checksum, or
  non-monotonic tail fails closed, retains the active journal, and returns the
  path, durable prefix length, observed length, reason, and recovery remedy.
- Recovery stays fingerprint-bound, explicit, and idempotent. No Take object,
  retired Contract, Project autosave, Product Build allocation, snapshot,
  release, deployment, or physical acceptance is introduced.

---

### Task 1: Persist and recover the unflushed Sequence tail

**Files:**

- Create: `docs/superpowers/plans/2026-08-29-lmdj-sequence-hard-owner-loss.md`
- Modify: `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`
- Modify: `packages/project-io/src/sequence_journal.cpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `tests/core/project_io/sequence_journal_test.cpp`
- Modify: `tests/core/facade/sequence_surface_test.cpp`
- Modify: `docs/superpowers/specs/2026-08-22-sequence-recording-semantics-design.md`
- Modify: `docs/quality/2026-08-27-stage9-sequence-recording-review.md`
- Modify: `docs/quality/2026-08-23-stage9-sequence-recording-acceptance.md`
- Modify: `apps/architecture-portal/docs/core/modules/project-io.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/application-facade.mdx`
- Modify: `apps/architecture-portal/docs/platform/storage.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

**Interfaces:**

- Consumes: `SequenceJournal::begin`, `SequenceJournal::append_flush`,
  `ProjectStoragePlatform::append_durable`, `domain::merge_pattern_events`, and
  the existing Facade `SequenceEventRequest` ordering contract.
- Produces:
  `SequenceJournal::append_tail(bundle, session_id, pattern_id,
  expected_revision, input_sequence, events) -> Result<void>`;
  `ActiveSequenceJournal::pending_events`; and restart recovery that merges the
  tail with incomplete flush records exactly once.

- [x] **Step 1: Add the Project I/O RED tests.** Extend
  `sequence_journal_test.cpp` so a begin followed by two monotonic
  `append_tail` snapshots reloads the second canonical event set; appending a
  flush consumes `pending_events`; seal/list exposes the tail; and manually
  appending a truncated JSON fragment makes `read_active` return
  `INVALID_PROJECT` with `reason=sequence_journal_torn_tail`, exact prefix and
  observed byte lengths, a path, and a retain/repair remedy.

- [x] **Step 2: Add the hard-crash Facade RED test.** Fork a child process that
  begins a real Sequence session, receives successful press/release results for
  two different Pad/tick identities, then stops itself with `SIGSTOP`. The
  parent must observe the stopped child, send `SIGKILL`, wait for a signaled
  death, restart the Facade, require one `owner_lost` candidate with two events,
  apply it, and assert canonical recovered identity/order and a single Project
  revision increment. No child destructor or `abandon_sequence_sessions` call
  may run.

- [x] **Step 3: Run the focused tests and capture RED.** Build
  `lmdj_sequence_journal_tests` and
  `lmdj_facade_sequence_surface_tests`, then run CTest cases
  `project_io.sequence_journal` and `facade.sequence_surface`. Expected RED:
  compilation fails because `append_tail`/`pending_events` do not exist, and
  after the journal-test API compiles the crash journey lacks a recovery tail
  until production ordering is implemented.

- [x] **Step 4: Implement the append-only tail contract.** Add canonical tail
  JSON records with monotonic `tail_seq` and `input_sequence`; parse them into
  the active pending tail; make `append_flush` require and consume the same
  canonical tail; include the tail in sealed recovery snapshots; count/merge
  it in recovery; and reject any unterminated trailing bytes with the actionable
  `sequence_journal_torn_tail` evidence instead of silently truncating them.

- [x] **Step 5: Implement acknowledgement-after-durability.** In
  `record_sequence_event`, apply press/release handling to a copied runtime,
  materialize canonical recovery events from completed pending events plus
  240-tick defaults for every still-pressed Pad, call `append_tail`, and publish
  the copied runtime only after that call succeeds. Keep all journal work on
  the control path and leave Audio Runtime/render-thread code unchanged.

- [x] **Step 6: Make flush and graceful owner loss consume the durable tail.**
  Flush the existing runtime events through the journal's consume operation;
  ensure provisional pressed events receive the same default used by recovery;
  seal the already-durable active journal directly on graceful owner loss; and
  merge `pending_events` with incomplete flushes during explicit recovery.

- [x] **Step 7: Run focused GREEN and regression checks.** Rebuild both targets,
  run their CTest cases, then run `scripts/core.sh test dev fast`. Expected:
  all focused assertions pass, the child exits only by `SIGKILL`, recovered
  events match their original slot/onset/velocity/duration order, and the fast
  suite reports zero failures.

- [x] **Step 8: Update current truth and acceptance.** Clarify SR-D17/§5/§8.6
  acknowledgement ordering, provisional press durability, tail consumption,
  and torn-tail failure evidence. Change M2's source disposition to #373 with
  local source/RED-GREEN evidence while explicitly deferring Module/Product
  identity, immutable snapshot, remote CI/merge, and physical rows to #379,
  #380, and #360. Update the four current Portal routes listed below without
  editing immutable versioned routes.

- [x] **Step 9: Run all required verification.** Run focused CTest, Core fast,
  Core full, Core stress, dependency, active-tree, version-file, version suite,
  project-I/O hook-symbol, and Architecture Portal checks. Inspect every output
  and retain exact counts/results for the report.

- [x] **Step 10: Audit pitfalls and create one local commit.** Search open
  `area:core`, `area:web-host`, and `area:product` pitfalls. Product logic that
  is fully expressed by the new regression tests does not create a ledger
  entry. Stage only the declared files, run `git diff --cached --check`, inspect
  the staged list, and commit as
  `fix(core): persist Sequence tail before acknowledgement (fixes #373)`.

## Version Management

Version impact: deferred to [#379](https://github.com/endaye/lmdj/issues/379).

This Task adds a Project I/O journal API/representation and changes Application
Facade acknowledgement behavior, so it records accumulated impact in the
`project-io` additive API domain and the `application-facade` patch domain. It
does not edit module manifests, exact dependency references, Assembly identity,
Product Build, Contract ID/SemVer, Host protocol, Provider identity, or release
intent. #379 performs the fresh identity audit and applies all six remediation
children's accumulated versions once; #380 owns the separate clean-commit
immutable snapshot. Existing Product Build `1.0.37.0` is not rewritten or
reclassified by this Task.

## Documentation Impact

Documentation impact: required.

Affected current Portal routes:

- `/core/modules/project-io/`
- `/core/modules/application-facade/`
- `/platform/storage/`
- `/operations/testing-and-proof/`

The Task also updates the current Sequence semantics, Stage 9 review
disposition, and Stage 9 automated acceptance ledger. No generated identity,
source diagram, or immutable versioned Portal route changes in this functional
child; final accumulated current truth and diagrams belong to #379, and #380
freezes immutable evidence.

## External Boundaries

This Task creates one local commit only. Push, Pull Request, merge, tag,
Release, publication, deployment, Channel promotion, and physical/manual
acceptance are not authorized.
