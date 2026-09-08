# LMDJ Runtime Invariant Harness Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Check the relations that only a *running* system can violate, and that
the build-time conformance suite structurally cannot see. This is Track 3 of
[`2026-08-19-lmdj-dsh-derived-hardening.md`](2026-08-19-lmdj-dsh-derived-hardening.md).

**Why.** Every consistency guard in this tree is either build-time
(`tests/conformance/`) or a fail-closed validation at a load boundary. Nothing
observes whether a *sequence* of operations left the workspace coherent. The
investigation behind this plan found four real defects of exactly that shape —
listed in "Findings" below — none of which any existing test could have caught,
because each requires a completed operation sequence rather than a single call.

**Architecture:** `tests/` only. See the boundary decision below: this harness
is deliberately **not** a Core Module.

---

## Decision: a `tests/` harness, not a Core Module

The goal document left this open. It resolves against a Core Module on two
grounds, one practical and one architectural.

**Practical.** A new `packages/<m>` requires roughly ten files inside the
module and eleven registrations outside it: `module.json` (5-key shape, exact
dependency-version match), a `CMakeLists.txt`, an `add_subdirectory` in
dependency order in the root `CMakeLists.txt`, the `packages/README.md` graph,
a `modules[]` entry in `products/lmdj/assembly.json`, a `CompiledComponent` in
`products/lmdj/src/compiled_assembly.cpp`, a regenerated `assembly.lock.json`,
a Product Build bump in `version.json`, a coverage-threshold entry, the
`lmdj_coverage_targets` list, a `.architecture.json` diagram, an `.mdx` portal
page, a `sidebars.ts` id, a `check-build.mjs` route, the pinned module list in
`repo-facts.test.mjs`, and a `scope_policy.json` rule. A `tests/`-owned harness
costs one source file, one `lmdj_add_test` block, and one scope rule.

**Architectural, and the reason that actually decides it.** A Core Module
becomes a *product component*: it is listed in `assembly.json` and
inventory-cross-checked at runtime by
`packages/application-facade/src/assembly_loader.cpp:355-371`, hashed into the
Assembly Lock, and every invariant added to it bumps the Product Build. That
inverts the relationship — the thing whose job is to observe the product would
itself become part of what it observes, and adding an observation would change
product identity. dsh's invariant registry ships in-product because in dsh the
plugins *are* the product; LMDJ's invariants are verification, and this repo
already has a strong precedent for verification living outside the shipped
tree.

**Consequence accepted:** the harness cannot run inside a shipped Host. It runs
in the `component` and `stress` tiers against real workspaces. If in-product
invariants are ever wanted (a Host self-check surfaced through the Facade),
that is a separate decision with a Contract question attached, and it is out of
scope here.

## Adopted exclusion rule

Verbatim from dsh, because it is the reason its registry stayed useful at
scale: **anything the type system, a load-time validation, or a unit test
already guarantees is not a runtime invariant.** Confirming that a method
exists, that a schema validates, or that a pure function returns a fixed value
is a type, load, or unit-test concern. This harness checks only relations
across a completed sequence of operations.

Two candidates from the goal document are struck under this rule:

- **Snapshot publish atomicity is only partially admissible.** The cooker
  returns `shared_ptr<const RuntimeSnapshot>` built in one shot, so there is no
  partial-construction path to observe — that half is structural. The engine
  side is a real 4-slot bank plus SPSC handoff, but the live bank's identity is
  not externally readable: `RealtimeEngine` exposes only `bank_telemetry()`
  counters, and the live bank's `project_id`/`project_revision` are private
  behind `friend class RealtimeEngine`. Only the counter relations are
  checkable without new production surface (Task 3).
- **"Single-writer lease exclusivity" as the goal document phrased it is
  wrong, and the real invariant is already covered.** Nested acquisition on one
  `ProjectStoragePlatform` **succeeds by design** — leases are reentrant per
  platform instance, sharing one `NativeWriterState` under
  `writer_mutex_`/`writers_`, released when the last `shared_ptr` dies
  (`packages/project-io/src/native/storage_platform.cpp:1143-1217`). The
  exclusion that matters is cross-instance/cross-process `flock(LOCK_EX|LOCK_NB)`
  on a hashed lock file outside the bundle, and it is already tested in three
  places, most thoroughly by
  `tests/core/project_io/storage_platform_contract_test.cpp:372-438` — which
  even renames and recreates the bundle mid-flight and asserts the lock file's
  dev/inode are unchanged. Adding a runtime check here would restate an
  existing test.

  - [x] Correct that bullet in the goal document so the inaccurate phrasing
        does not propagate.

---

## Tasks

### Task 1 — Attempt ledger consistency (first, because it needs no production surface)

The strongest candidate: entirely filesystem-observable, zero new production
API, and it catches a real defect today.

- [x] A harness that, given a workspace, enumerates
  `<workspace_root>/.lmdj-workspace/attempts/` and checks, for every attempt:
  1. `<id>.json` exists ⟺ the attempt reached a terminal state — **this is
     the check that fails today**, see Finding G1.
  2. `<id>.json` bytes equal `canonical_json(parse(bytes)) + "\n"`.
  3. `status == "succeeded"` ⟺ exactly one `candidate_ids` entry and no
     `error`; `status == "failed"` ⟺ no `candidate_ids`, an `error` present,
     `minted_outputs` empty, **and no `<id>/` directory at all**.
  4. `candidate_outputs == minted_outputs` for a succeeded attempt.
  5. For every `minted_outputs` binding: `<id>/artifacts/<sha256>` exists, is a
     regular non-symlink file, `size == byte_length`, and re-hashes to
     `sha256`.
  6. `<id>/artifacts/` holds **no** file not named by some
     `minted_outputs[].artifact.sha256`.
  7. `<id>/staging/` does not exist for any terminal attempt.
  8. `artifacts[]` equals the deduplicated, sorted union of
     `request.inputs[].artifact` and `minted_outputs[].artifact`.
  9. `minted_outputs` and `candidate_outputs` are in canonical binding sort
     order with unique output hashes.
  10. `started_at <= ended_at`; `request.capability == capability.id`.
  11. No leftover `.<name>.tmp.<clock>.<seq>` temp siblings anywhere in the
      workspace.
- [x] **Enumeration is new surface and must stay in the harness.** There is no
  list/enumerate API at any layer: `AttemptStore` exposes only
  `set_provider_selection`, `selected_provider`, `inspect(AttemptId)`, and
  `execute`, and the Facade exposes only `attempt.inspect`. The harness
  therefore walks the directory itself and parses with the same rules
  `inspect` applies — it must **not** add an enumerate operation to the SDK or
  the Facade, which would be product API added for a test's convenience.

**Verification:** new `component`-tier test driving real `execute` calls
(success, failure, and a forced-failure interleaving) then asserting the ledger
holds after each.

**Done —** `tests/core/provider/attempt_ledger_invariant_test.cpp`, registered
as `provider.attempt_ledger_invariant` (`component`, labels `provider
persistence`). Twelve relations, five corruption cases proving the harness can
fail, and one case pinning G1.

### Task 2 — `host-settings.json` canonical form and lock hygiene

Also filesystem-observable with no new production surface.

- [x] Check after every mutation path that the file is byte-identical to
  `canonical_json(settings) + "\n"`, has exactly the two keys
  `format`/`provider_selections`, and that every capability and provider id
  satisfies `valid_file_id`.
- [x] Check that `.host-settings.lock/` does not survive a completed
  operation, and add a case covering the crash-orphaned lock (Finding G3):
  today an orphaned lock directory makes every later write return
  `io_error "host settings are busy"` with no staleness, pid, owner, or
  timeout recovery.
- [x] Note that the read path already enforces byte-identity on every read
  (`packages/provider-sdk/src/attempt_store.cpp:599`), so the harness's job
  here is the *sequence* — that no completed mutation leaves a state the next
  read would reject.

**Verification:** `component`-tier test exercising set/overwrite/concurrent
selection, plus an explicit orphaned-lock case.

**Done —** `tests/core/provider/host_settings_invariant_test.cpp`, registered as
`provider.host_settings_invariant` (`component`, labels `provider persistence`).
Four relations after the id-safety candidate was struck under the exclusion
rule, four corruption cases, and one case pinning G3.

### Task 3 — Snapshot publication counter relations (counters only)

Admissible without new production surface, using
`RealtimeEngine::bank_telemetry()`.

- [x] Check across a publication sequence: `applied <= accepted`;
  `pending == accepted - applied` once quiescent; `current_generation` is
  monotonic non-decreasing; and `accepted` is **unchanged** across each of the
  three rejection paths (`events_pending`, `bank_slots_full`,
  `publish_queue_full`).
- [x] Assert the documented rollback: `publish_queue_full` must fully restore
  the slot (`bank.reset()`, `generation = 0`, state back to `empty`,
  `pending_publications` decremented), observable as `accepted` unchanged and
  no generation movement.
  **Resolved as unreachable, not as a test.** Investigation while writing the
  stress case proved the branch cannot be entered at the current capacities —
  recorded as finding G5 below and pinned by a `static_assert` plus a race
  asserting `publish_queue_drops` stays 0. There is no rollback to assert until
  a capacity changes, and the test says so rather than pretending to cover it.
- [x] **Explicitly out of scope:** "the live bank's project revision equals
  the last accepted snapshot's". That needs either a new `RealtimeEngine`
  accessor or a `LMDJ_*_TESTING` hook, and a test-only hook would have to
  satisfy the symbol-leak gate (the
  `tests/build/project_io_test_hook_symbols_test.py` pattern). Record it as a
  follow-up rather than growing production surface inside this Task.
- [x] Because this exercises the lock-free handoff, register the sequence case
  in the **`stress`** tier as well, per `CLAUDE.md`'s rule that lock-free or
  concurrent changes run the stress tier explicitly.
  **Done —** `tests/core/audio/snapshot_publication_stress_test.cpp`, registered
  as `audio.snapshot_publication_stress` (`stress`, labels `audio concurrency`,
  180s). One control thread publishing against one render thread, asserting a
  conservation law: every publication is accounted for exactly once in exactly
  one bucket. Kept in its own file so a concurrent flake never casts doubt on
  the deterministic component-tier relations. Verified stable over 20 ctest
  repetitions and five direct runs.

**Verification:** `component` tier for the counter relations, `stress` tier for
the concurrent publication sequence.

**Partly done —** `tests/core/audio/snapshot_publication_invariant_test.cpp`,
registered as `audio.snapshot_publication_invariant` (`component`, labels `audio
concurrency`). Six counter relations covering the `events_pending` and
`bank_slots_full` rejection paths. The `stress`-tier variant and the
`publish_queue_full` rollback remain, for the reasons recorded above.

### Task 4 — Register the harness without disturbing the taxonomy

- [x] Register through `lmdj_add_test` only — there is no bare `add_test` in
  first-party CMake, and the tier label is the whole registration contract
  (`cmake/LmdjTesting.cmake:11-60`). Exactly one tier label, a `TIMEOUT` at or
  below the tier maximum, and `native` is auto-assigned, never hand-written.
- [x] `tests/build/test_test_taxonomy.py` additionally requires, under
  ASan/TSan, that native non-stress tests carry *exactly* tier × sanitizer
  factor; the `stress` tier is exempt. Set timeouts accordingly.
- [x] Choose a CTest name prefix deliberately: `scripts/core.sh proof`
  excludes `^(build\.|conformance\.|host\.|e2e\.|contract\.schemas)` patterns,
  so a name under those prefixes silently drops out of the Proof.
- [x] Add a `scripts/ci/scope_policy.json` rule for the new path. Omitting one
  does not fail open — an unclassified path forces `full` mode for every PR
  touching it.
- [x] If a new test executable is added, list it in `lmdj_coverage_targets`
  (root `CMakeLists.txt:76-110`); a listed-but-missing target is a configure
  `FATAL_ERROR`, and an unlisted one is silently absent from coverage.

**Verification:** `scripts/core.sh test dev full` then
`scripts/core.sh test dev stress`; `python3 -m unittest
tests.build.test_test_taxonomy -v`.

**Done for Tasks 1-3 —** `full` 70/70, `stress` 2/2,
`tests/build/test_test_taxonomy.py` PASS at 72 registered tests,
`tests/quality/core_coverage_runner_test.py` OK, and `scripts/core.sh proof`
reporting `Headless Core Proof: PASS` with `Assembly lock: MATCH` at an
unchanged Product Build `1.0.23.0`. No new `scope_policy.json` rule was needed:
`tests/core/` and `packages/audio-runtime/` are already classified, and the
root `CMakeLists.txt` coverage-target edit forces `full` mode anyway.

---

## Findings the investigation surfaced (each needs its own fix, not a check)

Labelled `G*` because `F1`–`F6` are already taken by the Creator UI
remediation findings in
[`2026-08-17-machine-task-todo.md`](../quality/2026-08-17-machine-task-todo.md),
where these are now tracked under the same `G` ids.

These are real defects, found while establishing what the harness could
observe. Per this repo's standing preference for real fixes over instrument
tuning, each belongs in `docs/quality/2026-08-17-machine-task-todo.md` as its
own item; the harness's role is to keep them fixed, not to normalize them.

- [ ] **G1 — an orphan attempt reservation permanently burns its attempt id.**
  `reserve_attempt` creates `attempts/<id>/` as the reservation, and every
  failure return between reservation and persist removes only `staging/` and
  `artifacts/` (`cleanup_attempt_outputs`,
  `packages/provider-sdk/src/attempt_store.cpp:317-330`), leaving `<id>/`
  behind with no terminal `.json`. The reservation directory is removed only on
  the succeeded-with-failure-terminal path (`:1758-1765`). No code path ever
  reclaims an orphan, so retrying that id fails forever with
  `duplicate_id "Attempt id is already reserved"`.
- [ ] **G2 — `host-settings.json` is written without `fsync`.** `write_bytes`
  flushes and closes but never `fsync`s the file, and `write_replace_atomic`
  never syncs the containing directory around the `rename`
  (`attempt_store.cpp:435-471`, `:522-555`). A crash can leave a truncated or
  zero-length file, after which every read fails the shape check. The lease
  path does sync (`packages/project-io/src/native/storage_platform.cpp:1057`),
  so the asymmetry is unintentional.
- [ ] **G3 — the host-settings lock has no crash recovery.** The lock is a
  `create_directory` mutex with no pid, owner, or timestamp
  (`attempt_store.cpp:364-398`). A process killed while holding it leaves
  `.host-settings.lock/` forever and every later write returns
  `io_error "host settings are busy"`.
- [x] **G5 — `PublishResult::publish_queue_full` is unreachable, so its
  rollback branch is dead code.** `kRealtimeBankCapacity` and
  `kRealtimePublishQueueCapacity` are both 4; a queue entry exists per pending
  publication, each pending publication owns a distinct slot, and `try_push` is
  reached only after an empty slot is found — so a full queue would need four
  pending slots plus a fifth empty one. `bank_slots_full` always binds first.
  Found while implementing Task 3's stress case, and pinned there by a
  `static_assert` on the capacities plus a race asserting `publish_queue_drops`
  stays 0. **Resolved by Issue #205:** keep the equal capacities and document
  the complete rollback as defence against a future capacity divergence. Do
  not change realtime headroom merely to make an error path testable.
- [ ] **G4 — temp-sibling names are not unique across processes.**
  `temporary_sibling` (`attempt_store.cpp:423-433`) mixes
  `steady_clock::now()` — which is boot- or process-relative, not globally
  unique — with a *process-local* atomic sequence. Two processes can generate
  the same temp path. It fails closed (`reject_existing_or_symlink` runs
  first), so the outcome is a spurious `io_error` rather than corruption, but
  it is still runtime-observable.

## Global Constraints

- **No new production API for a test's benefit.** Attempt enumeration stays in
  the harness; no `attempt.list` operation is added to the SDK or the Facade.
- **No new test-only hooks in this Task.** The tree does have a sanctioned
  pattern (`packages/application-facade/src/testing_hooks.hpp` behind
  `LMDJ_C_API_TESTING`, `LMDJ_PROJECT_IO_TESTING`) with a symbol-leak gate to
  match, but every invariant in Tasks 1–3 is reachable without one. Anything
  requiring a hook is deferred, not smuggled in.
- **The exclusion rule is binding.** A proposed invariant that a unit test,
  a schema, or the type system already guarantees does not get added because it
  is easy.
- There is no `LMDJ_ASSERT` or debug-assertion facility in `packages/`, and
  this Task does not introduce one. The established idiom is typed, always-on,
  fail-closed validation returning `foundation::Result`, plus `static_assert`
  at compile time.

## Version Management

**Version impact: none.**

No Core Module, Contract, Provider, Host, Product Assembly, or lock content
changes — this Task adds test sources, one or more `lmdj_add_test`
registrations, and a CI scope rule. No `module.json` version moves, so no
Product Build is allocated. Fixing findings G1–G4 *will* bump the owning
modules (`provider-sdk` at minimum) and is deliberately not part of this Task.

## Documentation impact

**Documentation impact: required.**

Affected portal pages: `/operations/testing-and-proof` — the harness adds a
test surface and, for Task 3, a `stress`-tier entry, and that page is the
portal's statement of what the Proof and the tiers cover.
`docs/quality/core-test-policy.md` is the canonical tier definition and is
updated in the same Task if a new risk label is introduced.

## Out of scope

- Fixing findings G1–G4. They are recorded here and belong in the machine-task
  list; each is its own commit with its own version impact.
- Any in-product invariant surface (a Host self-check through the Facade).
  That is a Contract question, not an implementation detail.
- The live-bank identity check (Task 3's deferred item), which needs new
  production surface or a gated test hook.
- Single-writer lease checks. Already covered by three existing tests, and the
  goal document's phrasing of that invariant was wrong — corrected as part of
  this plan's first task list.
