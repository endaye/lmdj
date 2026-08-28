# Stage 9 Armed-Pad Capture Rebase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close H3 from the Stage 9 review by preserving an active Sequence session while the Pad Capture armed before Record enters trimming, commits to its exact armed Pad, and rebases the session.

**Architecture:** The active Sequence journal and in-memory Facade runtime own one optional armed Capture Pad identity established at Sequence begin. Project I/O admits only `ImportAssignSample` carrying the matching session and Pad identity, commits it under the Project writer lease, then atomically advances the journal revision and consumes the arm. Web Runtime Platform transports the identity without interpreting Project Truth; Creator keeps the Sequence underlay active while its existing Stage 8B `CapturePanel` hosts the trim overlay.

**Tech Stack:** C++20 Core and tests, TypeScript/React Creator, JavaScript Web Runtime protocol, Vitest, Playwright, Docusaurus Architecture Portal.

## Global Constraints

- The selective-rebase allowlist remains closed to BPM, Quantize/Swing, and the approved armed-Pad Capture commit.
- The armed Capture must already target an empty Pad when Sequence Record begins; starting a new Capture while Record is active remains forbidden.
- Stage 8B trimming, the 240,000-frame limit, explicit commit, and conflict-retained Host-local buffer remain unchanged.
- Unknown authoring commands and unarmed/changed Pad targets fail closed without sealing or stopping the active Sequence session.
- No retired `lmdj.patch.v1` or `lmdj.materials.v1` surface is restored.
- One reviewable implementation Task produces one Conventional Commit; no push, PR, merge, release, deploy, publication, or Channel transition is authorized.

---

### Task 1: Preserve and consume the armed Capture identity across Core and Creator

**Files:**

- Modify: `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/sequence_journal.cpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `tests/core/facade/sequence_surface_test.cpp`
- Modify: `packages/web-runtime-platform/src/control_runtime.cpp`
- Modify: `packages/web-runtime-platform/src/bridge.cpp`
- Modify: `packages/web-runtime-platform/web/protocol.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_types.d.ts`
- Modify: `packages/web-runtime-platform/test/control_runtime_test.cpp`
- Modify: `packages/web-runtime-platform/test/protocol.test.mjs`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `apps/creator-web/src/app.tsx`
- Modify: `apps/creator-web/src/components/sample_surface.tsx`
- Modify: `apps/creator-web/src/runtime/runtime_types.ts`
- Modify: `apps/creator-web/src/runtime/sample_actions.ts`
- Modify: `apps/creator-web/src/runtime/sequence_actions.ts`
- Modify: `apps/creator-web/src/state/sequence_state.ts`
- Modify: `apps/creator-web/test/sample_actions.test.ts`
- Modify: `apps/creator-web/test/sequence_actions.test.ts`
- Modify: `apps/creator-web/test/sequence_state.test.ts`
- Modify: `tests/platform/web/creator/creator_web_capture.spec.mjs`
- Modify: `docs/quality/2026-08-27-stage9-sequence-recording-review.md`
- Modify: `docs/quality/2026-08-23-stage9-sequence-recording-acceptance.md`
- Modify: `apps/architecture-portal/docs/core/modules/application-facade.mdx`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/docs/product/workflows.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

**Interfaces:**

- `SequenceBeginRequest::armed_capture_slot: std::optional<domain::PadSlotId>` records the only Pad eligible for Capture rebase.
- `SampleImportBeginRequest::sequence_session_id: std::optional<foundation::SequenceSessionId>` explicitly classifies an import as the approved Capture commit.
- `SequenceJournal::prepare_armed_capture(...)` durably binds the exact session, slot, expected revision, command, asset, and artifact before Project publication; `complete_armed_capture(...)` verifies that identity, advances `expected_revision`, and consumes the arm.
- `SequenceJournal::disarm_capture(bundle, session_id, slot)` consumes an abandoned arm without changing Project revision or pending events.
- `CreatorSequenceRuntimeSession.beginSequence(...armedCaptureSlot)` and `importAssignSample(...sequenceSessionId)` transport identities; `disarmSequenceCapture({sessionId, slot})` closes cancel/discard authority.

- [x] **Step 1: Write failing Core persistence and Facade tests**

Add a Facade component journey through the real journal/Store that proves the begin record round-trips the armed slot, only the matching `ImportAssignSample` session/slot/revision is admitted, successful commit consumes the arm and rebases the journal, and disarm consumes it without a Project mutation. The journey records pending events on an assigned Pad, rejects the armed Pad as an event, keeps the session active through a failed/unarmed commit, commits the matching Capture, records the newly assigned Pad, stops, reloads, and sees both the Pattern events and Pad assignment.

- [x] **Step 2: Run the Core tests and verify RED**

Run:

```bash
cmake --build build/core/dev --target lmdj_facade_sequence_surface_tests
build/core/dev/bin/lmdj_facade_sequence_surface_tests
```

Expected: compile or assertion failure because armed Capture identity and admission do not exist and `sample.import.commit` is rejected by the active journal.

- [x] **Step 3: Implement the minimal Core authority**

Persist `armed_capture_slot` as nullable/additive journal metadata. Admit the special sample import only when the active journal is `active` or `switching`, the supplied session equals the journal owner, the slot equals the armed slot, and `expected_revision` equals journal authority. Keep the writer lease through validation and publication. On success, append one checked completion record that both rebases and clears the arm; on cancel append one checked disarm record. Mirror the same checks in the Facade runtime, update `expected_revision` and `available_slots` after commit, and never clear pending events on failure.

- [x] **Step 4: Run the Core tests and verify GREEN**

Run the Step 2 command again. Expected: all three focused executables pass.

- [x] **Step 5: Write failing Web Runtime and Creator tests**

Add protocol/session tests for optional `armed_capture_slot` and `sequence_session_id`, Control Runtime coverage for matching and mismatched imports, reducer tests that `recording -> trim-overlay -> recording` and `switch-pending -> trim-overlay -> switch-pending` retain session/status, and action validation for the exact identities. Extend the packaged Chromium Capture journey to start Capture on empty A1, continue to Sequence, Record another Pad, press A1 to enter trim without Stop, commit, assert the Sequence is still recording, then record A1, Stop, reload, and verify the committed Pad plus flushed Sequence truth.

- [x] **Step 6: Run Web/Creator tests and verify RED**

Run:

```bash
node --test packages/web-runtime-platform/test/protocol.test.mjs packages/web-runtime-platform/test/runtime_session.test.mjs
npm --prefix apps/creator-web test -- --run
```

Expected: request-shape and reducer/journey failures because the existing Host stops Sequence before trim and the bridge has no armed identity.

- [x] **Step 7: Implement the minimal bridge and Creator behavior**

Carry the nullable arm on Sequence begin, carry the exact Sequence session only for Capture import, and expose explicit disarm. In Creator, pass the armed slot when Record begins; do not call `stopSequence()` when that Pad stops Capture; preserve the active/switching underlay during `trim-overlay`; serialize the matching Capture commit against current Sequence revision; on commit refresh authoritative revision/status, and on cancel/discard disarm then restore the underlay. Ordinary file imports and Sample mutations remain outside the allowlist.

- [x] **Step 8: Run focused Web/Creator tests and verify GREEN**

Run the Step 6 commands plus the rebuilt `web_runtime.control_runtime` CTest. Expected: all focused tests pass.

- [x] **Step 9: Update current truth and review disposition**

Mark H3 source disposition as fixed by #374 without claiming merge, Product Build integration, immutable snapshot, physical acceptance, Release, or deployment. Correct the acceptance concurrency row from settings-only to the approved closed allowlist and record the new automated evidence. Update current Portal routes for Application Facade, Creator, workflows, and testing/proof. Do not edit immutable `1.0.37.0` snapshot files; #379 and #380 own identity integration and the corrected snapshot.

- [x] **Step 10: Run full verification and commit**

Run focused tests, `scripts/core.sh test dev fast`, `scripts/core.sh test dev full`, `scripts/core.sh test dev stress`, Creator build/tests, `scripts/architecture-portal.sh check`, dependency/active-tree/version checks, and the applicable local CI lanes. Audit `.agents/pitfalls/` by `area:core`, `area:creator`, and `area:product`; product-logic behavior fully expressed by regression tests does not create a pitfall entry. Stage only declared Task files, inspect cached diff/check/stat, and commit. Then run the packaged Chromium Creator Proof from the clean commit (the stable script intentionally refuses a dirty source tree):

```text
fix(sequence): preserve armed Pad capture sessions (fixes #374)
```

## Version Management

Version impact: deferred to [#379](https://github.com/endaye/lmdj/issues/379).

This Task changes behavior and public headers/protocol surfaces in the `project-io`, `application-facade`, `web-runtime-platform`, and `creator-web` version domains, but does not independently allocate or reuse a Module version, Host version, Contract version, Product Build, active manifest, or Assembly lock. #379 performs the fresh identity audit and integration allocation; #380 owns the separate clean-commit immutable snapshot boundary. Product Build `1.0.37.0` is historical evidence and is not rewritten by this Task.

## Documentation Impact

Documentation impact: required.

Affected current Portal routes:

- `/core/modules/application-facade/`
- `/hosts/creator-web/`
- `/product/workflows/`
- `/operations/testing-and-proof/`

The Task also updates the approved Sequence design/decision, Stage 9 review disposition, and Stage 9 acceptance ledger. No immutable snapshot is created here; #379 and #380 own final identity integration and corrected immutable evidence.

---

### Task 2: Review fix for interrupted Capture publication and packaged persistence proof

**Files:**

- Modify: `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`
- Modify: `packages/project-io/src/sequence_journal.cpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `tests/core/project_io/fault_matrix_test.cpp`
- Modify: `tests/platform/web/creator/creator_web_capture.spec.mjs`
- Modify: `docs/superpowers/plans/2026-08-29-stage9-armed-pad-capture.md`
- Modify: `docs/quality/2026-08-27-stage9-sequence-recording-review.md`
- Modify: `docs/quality/2026-08-23-stage9-sequence-recording-acceptance.md`
- Modify: current Architecture Portal routes already declared above
- Modify: `.agents/pitfalls/acceptance-journey-truncation.md`
- Modify: `.agents/skills/issue-done/SKILL.md`

- [x] Reproduce the manifest-published/journal-incomplete window with the existing post-publication fault hook and a fresh UI retry command identity.
- [x] Append a durable Capture precommit marker before Project publication. Bind session, armed slot, expected revision, original command, asset, and exact artifact identity; reject a changed retry without mutating either Project or journal.
- [x] On a matching retry, validate the original transaction command, receipt, event, assigned Pad, asset, artifact, and exact `N + 1` revision before replaying and completing the journal. On restart, perform the same receipt-driven reconciliation before sealing owner loss.
- [x] Prove the reconciled session can append/commit a later flush and stop cleanly without a second Sample mutation.
- [x] Strengthen the packaged Creator journey to record A2 before the armed A1 stop, reject the stop hit from Sequence, record A1 only after commit, stop, reload/reopen, and inspect exact persisted revision, event delta/order/count, Pad assignment, Asset, and WAV artifact identity.
- [x] Keep the armed Capture Pad as the Sample selection owner while a different Pad remains ordinary playable/recordable Sequence input, so the eventual Capture commit retains its exact slot identity.
- [x] Record the second `acceptance-journey-truncation` recurrence and absorb it into the `issue-done` prerequisite as a leg-by-leg far-side evidence map.

Review-fix verification uses the same Version Management and Documentation Impact decisions as Task 1. Version allocation remains deferred to #379; current Portal/review/acceptance truth changes are required, while immutable snapshots remain untouched. The independently shared running-audio BPM-update → immediate switch failure remains outside #374 and is reported against #375 rather than hidden by this journey.

## External Boundaries

This Task authorizes no push, Pull Request, merge, Product tag, Release, deployment, publication, or Channel promotion. Physical/manual acceptance remains deferred under #360.
