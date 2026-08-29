# Sequence Armed-Capture Rebase Implementation Plan

**Goal:** Let a capture that was armed on an empty Pad before Sequence recording enter the existing trim overlay and commit to that exact Pad without stopping, flushing, or losing the active Sequence session.

**Architecture:** Sequence begin binds an optional empty armed Pad to the session authority. A capture-specific Sample import carries that session identity through Creator and Web Runtime, while ordinary imports remain unprivileged. Under the Facade Sequence lock, commit validates the active owner, expected revision, unchanged target, and empty Pad; Project Store independently validates the same active journal owner, commits the existing `ImportAssignSample` transaction, and rebases the journal. The Facade then rebases its in-memory runtime revision and available-slot mask while preserving pending events, transport, Pattern-switch state, and overlay generation.

**Tech Stack:** C++20, TypeScript/React, nlohmann/json, CMake/CTest, Node test runner, Vitest, Playwright, Docusaurus Architecture Portal.

## Global Constraints

- SR-D15, SR-D18, and SR-D24 are authoritative: the capture begins before Sequence; stopping capture opens the existing Stage 8B trim overlay without stopping Sequence; only the exact armed target may commit.
- Project Truth remains authoritative. The capture buffer, trim selection, overlay state, Provider attempt state, and Runtime Snapshot remain derived or ephemeral state.
- Ordinary file import, long-source import, Pad reset/update, and any unowned or changed-target capture remain blocked while Sequence is active.
- A rejected, cancelled, or failed capture commit leaves the active session, journal revision, Pattern-switch authority, pending events, and captured buffer recoverable.
- A successful capture commit changes only the armed Pad assignment, advances Project/journal/session revision together, makes the Pad available for future hits, and does not retroactively record or synthesize events.
- Existing Stage 8B trim, explicit commit, retry, cancellation, quota, and conflict behavior remains intact.
- #373 hard-crash tail persistence and #376 switch-boundary flushing remain outside this Task.
- The Task is one reviewable Conventional Commit that closes #374.

## Task 1: Bind an optional armed Pad to Sequence authority

**Files:**

- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/web-runtime-platform/src/control_runtime.cpp`
- Modify: `packages/web-runtime-platform/web/protocol.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_types.d.ts`
- Modify: `apps/core-mcp/lmdj_core_mcp/server.py`
- Modify: `apps/creator-web/src/runtime/runtime_types.ts`
- Modify: `apps/creator-web/src/app.tsx`
- Test: `tests/core/facade/application_test.cpp`
- Test: `tests/core/facade/c_api_test.cpp`
- Test: `tests/core/facade/sequence_surface_test.cpp`
- Test: `packages/web-runtime-platform/test/control_runtime_test.cpp`
- Test: `packages/web-runtime-platform/test/protocol.test.mjs`
- Test: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Test: `apps/creator-web/test/sequence_actions.test.ts`
- Test: `tests/e2e/headless_core_proof.py`
- Test: `tests/e2e/requests/record-pattern.json`
- Test: `tests/host/mcp_facade_parity_test.py`
- Test: `tests/host/mcp_stdio_test.py`
- Test: `tests/platform/web/audio/realtime_failure.spec.mjs`
- Test: `tests/platform/web/host/web_runtime_host_browser.spec.mjs`

- Add `armed_capture_slot` as a nullable, exact-shape Sequence-begin field at the Web bridge and Facade command boundary.
- Validate that a bound target is a valid, currently empty Pad and retain it only in the active `SequenceRuntime`; do not persist it as Project Truth.
- Pass the current Creator armed-capture slot when recording begins. A Sequence begun without one remains unable to authorize capture commit.

## Task 2: Add the narrow capture-import authorization and atomic rebase

**Files:**

- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `apps/creator-web/src/runtime/runtime_types.ts`
- Modify: `apps/creator-web/src/runtime/sample_actions.ts`
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_types.d.ts`
- Test: `tests/core/facade/sequence_surface_test.cpp`
- Test: `tests/core/facade/sample_surface_test.cpp`
- Test: `tests/core/project_io/project_store_test.cpp`
- Test: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Test: `apps/creator-web/test/sample_actions.test.ts`

- Carry a nullable `sequence_session_id` on Sample import begin; only `captureCommitJourney` may supply it in Creator.
- Under `sequence_mutex`, reject missing/wrong owner, wrong or changed slot, stale revision, assigned target, switching/flush incompatibility, and any active-session import without capture authority before Project mutation.
- Have Project Store admit `ImportAssignSample` only for the matching active journal session and rebase that journal after commit, while retaining the existing fail-closed admission for every unprivileged mutation.
- After success, update the Facade runtime expected revision and available-slot mask, clear the one-shot armed target, and preserve pending events, pressed state, transport, overlay generation, and pending Pattern switch.
- Prove cancellation and all pre-commit failures leave Project and journal unchanged; prove Stop/flush/reload retains both the committed Pad and pending Pattern events.

## Task 3: Preserve the active Creator state through trim and commit

**Files:**

- Modify: `apps/creator-web/src/state/sequence_state.ts`
- Modify: `apps/creator-web/src/app.tsx`
- Modify: `apps/creator-web/src/components/sample_surface.tsx`
- Test: `apps/creator-web/test/sequence_state.test.ts`
- Test: `apps/creator-web/test/sample_actions.test.ts`
- Test: `apps/creator-web/test/capture_panel.test.tsx`
- Test: `tests/platform/web/creator/creator_web_capture.spec.mjs`

- Stop only the armed capture when its Pad is pressed during Sequence; never call Sequence Stop as part of that gesture.
- Let trim overlay retain the active/switch-pending underlay and restore the current authoritative phase on cancel, failure, or success.
- Commit with the freshest Sequence revision and session identity, refresh Sequence authority after success, and keep the capture buffer available after rejection or failure.
- Prove only future hits on the newly assigned Pad are recorded and that ordinary imports remain blocked.

## Task 4: Update current documentation and acceptance evidence

**Files:**

- Modify: `docs/quality/2026-08-27-stage9-sequence-recording-review.md`
- Modify: `docs/quality/2026-08-23-stage9-sequence-recording-acceptance.md`
- Modify: `apps/architecture-portal/docs/core/modules/application-facade.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/project-io.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify source diagrams and their generated current HTML/SVG only where the implemented boundary changes.

- Mark H3 source-fixed by #374 while leaving integrated Product identity to #379, immutable snapshot work to #380, and physical/manual rows unverified.
- Document the one-shot session/Pad authorization, Project Store journal rebase, non-destructive rejection, and Creator overlay lifecycle.
- Do not edit versioned Portal snapshots, Product Build identity, Assembly locks, tags, Releases, deployments, or Channels.

## Task 5: Verify, audit pitfalls, and ship atomically

- Run focused Project Store, Facade, Web control/session, Creator state/action/component, and packaged browser tests.
- Run `scripts/core.sh test dev full`, `scripts/core.sh test dev stress`, `scripts/architecture-portal.sh check`, `bash tests/build/test_active_tree.sh`, `python3 tests/build/version_test.py`, and `python3 scripts/version.py verify --version-file products/lmdj/version.json`.
- Search open `area:core`, `area:creator`, and `area:web-host` pitfall entries and record or bump only a qualifying process/invariant recurrence.
- Stage only declared Task files, inspect `git diff --cached --check`, commit as `fix(sequence): preserve session during armed capture (fixes #374)`, then use the repository `issue-done` workflow for push, PR, CI, squash merge, and cleanup under the standing authorization.

## Version Management

Version impact: required, allocation deferred to #379. This Task changes Application Facade, Project I/O, Web Runtime Platform, and Creator Web Host behavior/API boundaries, but does not edit their versions, `products/lmdj/version.json`, Assembly manifests/locks, tags, or Product Build snapshots. Issue #379 performs the fresh identity audit and integrated Product Build allocation after all remediation children merge; #380 freezes the corresponding immutable Portal snapshot.

## Documentation Impact

Documentation impact: required.

Affected portal routes: `/core/modules/application-facade/`, `/core/modules/project-io/`, `/core/modules/web-runtime-platform/`, and `/hosts/creator-web/`.

Reason: the current authoring-admission boundary, active-journal rebase, Web bridge authority, Creator trim-overlay lifecycle, and automated evidence change. Only current Portal pages/source diagrams and Stage 9 review/acceptance ledgers move here; immutable Product Build documentation remains deferred to #380.
