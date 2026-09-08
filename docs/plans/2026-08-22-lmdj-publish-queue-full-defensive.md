# Publish Queue Full Defensive Contract Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve Issue #205 by recording `publish_queue_full` as a defensive rollback for future capacity changes while preserving the current equal-capacity behavior that makes the branch unreachable.

**Architecture:** Do not change either realtime capacity or the publish algorithm. Put the complete invariant beside the defensive branch, keep the existing stress-tier `static_assert` and race as executable evidence, and reconcile the three current planning/quality records so G5 is no longer presented as an undecided item.

**Tech Stack:** C++20, CTest, Markdown, LMDJ Core scripts

## Global Constraints

- Keep `kRealtimeBankCapacity == kRealtimePublishQueueCapacity == 4`.
- Keep `PublishResult::publish_queue_full` and its complete rollback; a future capacity change must not silently drop a publication.
- Do not add a synthetic path or test hook solely to make the defensive branch reachable.
- Preserve `audio.snapshot_publication_stress` as the executable guard for the equal-capacity invariant.
- Make no Product Build, Module, Host, Provider, Contract, Assembly, or release-state change.

---

### Task 1: Record and close the defensive queue-full decision

**Files:**
- Create: `docs/plans/2026-08-22-lmdj-publish-queue-full-defensive.md`
- Modify: `packages/audio-runtime/src/realtime_engine.cpp`
- Modify: `tests/core/audio/snapshot_publication_stress_test.cpp`
- Modify: `docs/plans/2026-08-19-lmdj-runtime-invariant-harness.md`
- Modify: `docs/plans/2026-08-19-lmdj-dsh-derived-hardening.md`
- Modify: `docs/quality/2026-08-17-machine-task-todo.md`

**Interfaces:**
- Consumes: `kRealtimeBankCapacity`, `kRealtimePublishQueueCapacity`, `PublishResult::publish_queue_full`, and `BankTelemetry::publish_queue_drops`.
- Produces: no new runtime interface; only an explicit defensive contract and reconciled G5 status.

- [x] **Step 1: Preserve the executable equal-capacity guard**

Run the focused stress test before editing:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --test-dir build/core/dev \
  -R '^audio\.snapshot_publication_stress$' --output-on-failure
```

Expected: `audio.snapshot_publication_stress` passes and continues to assert equal capacities, zero `publish_queue_full` outcomes, and zero `publish_queue_drops`.

- [x] **Step 2: Document the production fallback at its control point**

Immediately before `publish_queue_.try_push(slot_index)`, explain that the failure branch is unreachable while Bank and queue capacities are equal because a full queue consumes every Bank slot, while reaching `try_push` requires another empty slot. State that the rollback remains mandatory defence for a future capacity divergence.

- [x] **Step 3: Bind the stress evidence to the approved Issue #205 decision**

Update the G5 comment above `test_publish_queue_full_is_unreachable_at_equal_capacities()` to say that Issue #205 deliberately keeps the rollback defensive and does not change capacity merely to exercise it. Do not weaken the `static_assert`, race, telemetry checks, or conservation relations.

- [x] **Step 4: Reconcile every current G5 status record**

Mark G5 resolved in the runtime-invariant plan and DSH-derived hardening goal. Strike the G5 machine-task row and record that the equal-capacity invariant remains guarded by `audio.snapshot_publication_stress`, while the rollback remains defence against future capacity divergence. Link the resolution to Issue #205 without claiming release or deployment state.

- [x] **Step 5: Verify the complete Task**

```bash
ctest --test-dir build/core/dev \
  -R '^audio\.snapshot_publication_stress$' --output-on-failure
python3 tests/build/test_test_taxonomy.py build/core/dev
scripts/architecture-portal.sh check
git diff --check
```

Expected: the focused stress test and taxonomy pass; the Architecture Portal check passes without current-page changes; the diff has no whitespace errors.

- [x] **Step 6: Create the one atomic commit**

```bash
test "$(git branch --show-current)" = \
  "docs/issue-205-publish-queue-full-defensive"
git add -- \
  packages/audio-runtime/src/realtime_engine.cpp \
  tests/core/audio/snapshot_publication_stress_test.cpp \
  docs/plans/2026-08-19-lmdj-runtime-invariant-harness.md \
  docs/plans/2026-08-19-lmdj-dsh-derived-hardening.md \
  docs/plans/2026-08-22-lmdj-publish-queue-full-defensive.md \
  docs/quality/2026-08-17-machine-task-todo.md
git diff --cached --name-only
git diff --cached --check
git commit -m "docs(audio): record publish queue fallback contract"
git show --stat --oneline --decorate HEAD
git status --short --branch
```

Expected: exactly the six declared files are committed and the worktree is clean.

## Version Management

Version impact: none

Reason: the capacities, algorithm, runtime bytes, public API/ABI, Contract, manifests, Product Assembly, and Assembly Lock remain unchanged. This Task documents an already-proven defensive branch and reconciles planning status only.

## Documentation Impact

Documentation impact: none

Reason: current runtime behavior, public boundaries, version identities, testing surface, and Architecture Portal facts do not change. The existing stress test already proves the equal-capacity invariant; this Task updates source comments and repository planning/quality records only.
