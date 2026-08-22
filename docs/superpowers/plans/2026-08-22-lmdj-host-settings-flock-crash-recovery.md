# Host Settings `flock` Crash Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crash-orphanable Host settings directory mutex with a fail-fast native `flock` whose kernel lifetime ends with the owning process, closing Issue #204.

**Architecture:** Keep the process-local mutex for threads, then acquire one private regular `.host-settings.lock` file with `flock(LOCK_EX | LOCK_NB)` before loading `host-settings.json`. Hold its descriptor through the complete read-modify-atomic-rename sequence; an RAII owner closes the descriptor on every return path, and the kernel releases it after process death. The Emscripten build retains no persistent or concurrent Provider execution and compiles a no-op acquisition path without creating a second storage abstraction.

**Tech Stack:** C++20, POSIX `open`/`fstat`/`flock`/`close`, CTest, Python manifest gates, Docusaurus Architecture Portal.

## Global Constraints

- Work only on `fix/issue-204-host-settings-lock-flock`; never commit on `main`.
- Preserve `LOCK_NB` fail-fast behavior and the typed `io_error` message `host settings are busy` while another process owns the lock.
- The lock serializes the entire `host-settings.json` read-modify-write; it is not a read lock and does not change atomic-rename behavior.
- Do not introduce pid files, timestamps, stale-lock windows, retries, blocking waits, or operator cleanup semantics.
- Do not make `host-settings.json` durable; Issue #203 deliberately keeps it flush-and-rename configuration while making Attempt evidence durable.
- Do not add public Provider SDK, Application Facade, Contract, Project Truth, or Web storage surface.
- Native tests must use process synchronization, not sleeps, to prove contention and release after process death.
- Historical plans, release evidence through `1.0.25.0`, and earlier immutable Portal snapshots remain byte-identical. This plan may record the Controller execution evidence below.

## Controller execution amendment

The Architecture Portal snapshot command requires a clean worktree and records the committed source revision. The Controller therefore committed the byte-final implementation and current Portal truth as `129f6908e932a7a840f5f52f6f5ba4b068b7ebd2`, then generated and committed the immutable `1.0.26.0` snapshot as descendant `20650c0deb8292639791d80983c0559f2da7447c`.

The final local correction `1aa70b27ca1611ee23b8493617d6da46599b7a83` only aligns the source-package test expectation with the planned local-proof Provider version `1.0.5`; the complete implementation at that revision passed `scripts/core.sh test dev full` with `73/73` tests. These provenance commits remain in the reviewed branch ancestry, but this Pull Request does not register a `1.0.26.0` Release intent.

Product Build `1.0.26.0` and its immutable `canary` snapshot are source allocation only. A future Release intent requires separate authorization and a separate reviewed Pull Request after this Pull Request squash-merges; it must target the exact protected-`main` squash SHA and satisfy the current release evidence gates. No branch-local provenance or documentation commit is a substitute for that target.

These local provenance commits are required execution evidence; they do not change the integration contract. After exact-head review and CI, the Pull Request still squash-merges to `main` as one atomic Conventional Commit.

---

## Version Management

This native concurrency fix changes Provider SDK behavior without changing its public API or persisted Host settings schema, so it is a Provider SDK PATCH. Because the Product Assembly locks Provider SDK and every dependent identity, the patch cascades through the Assembly and allocates the next Product Build after Issue #203.

| Identity | From | To | Reason |
| --- | --- | --- | --- |
| `provider-sdk` | `1.1.3` | `1.1.4` | Native Host settings lock crash-recovery fix; API version remains `2`. |
| `application-facade` | `1.4.2` | `1.4.3` | Locks `provider-sdk` `1.1.4`. |
| `core-cli` | `1.0.14` | `1.0.15` | Locks `application-facade` `1.4.3`. |
| `core-mcp` | `1.1.11` | `1.1.12` | Locks `application-facade` `1.4.3`. |
| `native-test-host` | `1.0.12` | `1.0.13` | Locks `application-facade` `1.4.3`. |
| `web-runtime-platform` | `0.3.2` | `0.3.3` | Locks `application-facade` `1.4.3`; Web behavior is unchanged. |
| `web-runtime-host` | `1.2.11` | `1.2.12` | Locks `web-runtime-platform` `0.3.3`. |
| `creator-web` | `1.3.2` | `1.3.3` | Locks `web-runtime-platform` `0.3.3`. |
| `local.proof.success` | `1.0.4` | `1.0.5` | Locks `provider-sdk` `1.1.4`. |
| `local.proof.failure` | `1.0.4` | `1.0.5` | Locks `provider-sdk` `1.1.4`. |
| Product Build / Assembly | `1.0.25.0` | `1.0.26.0` | New Assembly identity for the Provider SDK patch. |

Contract versions and API versions do not change. Product Build `1.0.26.0` remains `canary`; allocation does not authorize a tag, Release, deployment, or Channel promotion.

## Documentation Impact

Documentation impact: required

Affected portal routes:

- `/`
- `/overview/`
- `/core/modules/provider-sdk/`
- `/core/modules/application-facade/`
- `/core/modules/web-runtime-platform/`
- `/assembly/lmdj/`
- `/hosts/overview/`
- `/hosts/creator-web/`
- `/hosts/web-runtime/`
- `/operations/testing-and-proof/`
- `/operations/version-and-release/`
- `/platform/input/`
- `/platform/web-runtime/`
- `/product/capability-map/`
- `/providers/overview/`

Reason: the Provider SDK's native cross-process lock lifetime and test evidence change, and the Assembly/Product Build identities must be represented by current pages and an immutable `1.0.26.0` canary snapshot.

---

### Task 1: Recover Host settings writes after lock-owner death and cascade the Assembly

**Files:**

- Modify: `docs/superpowers/plans/2026-08-22-lmdj-host-settings-flock-crash-recovery.md`
- Modify: `docs/quality/2026-08-17-machine-task-todo.md`
- Modify: `tests/core/provider/host_settings_invariant_test.cpp`
- Modify: `tests/core/provider/spec_regression_test.cpp`
- Modify: `packages/provider-sdk/src/attempt_store.cpp`
- Modify: `packages/provider-sdk/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `packages/web-runtime-platform/module.json`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/core-mcp/pyproject.toml`
- Modify: `apps/core-mcp/lmdj_core_mcp/__init__.py`
- Modify: `apps/native-test-host/module.json`
- Modify: `apps/native-test-host/src/main.cpp`
- Modify: `apps/web-runtime-host/module.json`
- Modify: `apps/web-runtime-host/test/deployment_smoke_test.py`
- Modify: `apps/web-runtime-host/test/distribution_test.py`
- Modify: `apps/web-runtime-host/test/main_shell.test.mjs`
- Modify: `apps/web-runtime-host/test/package_test.py`
- Modify: `apps/creator-web/module.json`
- Modify: `apps/creator-web/package.json`
- Modify: `apps/creator-web/package-lock.json`
- Modify: `apps/creator-web/test/acceptance_report.test.ts`
- Modify: `apps/creator-web/test/audio_lifecycle.test.tsx`
- Modify: `apps/creator-web/test/input_controller.test.ts`
- Modify: `apps/creator-web/test/project_actions.test.ts`
- Modify: `apps/creator-web/test/runtime_context.test.tsx`
- Modify: `apps/creator-web/test/workspace_shell.test.tsx`
- Modify: `providers/local-proof-success/module.json`
- Modify: `providers/local-proof-success/CMakeLists.txt`
- Modify: `providers/local-proof-success/src/provider.cpp`
- Modify: `providers/local-proof-failure/module.json`
- Modify: `providers/local-proof-failure/CMakeLists.txt`
- Modify: `providers/local-proof-failure/src/provider.cpp`
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Modify: `products/lmdj/CMakeLists.txt`
- Modify: `products/lmdj/README.md`
- Generate: `products/lmdj/assembly.lock.json`
- Generate: `products/lmdj/generated/web-runtime-identity.json`
- Generate: `products/lmdj/generated/web-runtime-identity.mjs`
- Modify: `tests/build/release_prepare_test.py`
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/module_graph_test.py`
- Modify: `tests/conformance/version_lock_test.py`
- Modify: `tests/core/facade/application_test.cpp`
- Modify: `tests/core/facade/assembly_loader_test.cpp`
- Modify: `tests/core/provider/conformance_test.cpp`
- Modify: `tests/host/mcp_stdio_test.py`
- Modify: `tests/host/native_host_source_boundary_test.py`
- Modify: `tests/host/native_host_test.py`
- Modify: `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- Modify: `tests/platform/web/host/web_runtime_host_manifest_gate.spec.mjs`
- Modify: `apps/architecture-portal/docs/assembly/lmdj.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/application-facade.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/provider-sdk.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/docs/hosts/overview.mdx`
- Modify: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`
- Modify: `apps/architecture-portal/docs/overview/index.mdx`
- Modify: `apps/architecture-portal/docs/platform/input.mdx`
- Modify: `apps/architecture-portal/docs/platform/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/product/capability-map.mdx`
- Modify: `apps/architecture-portal/docs/providers/overview.mdx`
- Modify: `apps/architecture-portal/test/repo-facts.test.mjs`
- Modify: `apps/architecture-portal/versions.json`
- Verify, no final Pull Request change: `docs/release-evidence/release-intents.json`
- Generate: immutable Architecture Portal snapshot `1.0.26.0` / `canary`

**Interfaces:**

- Consumes: `AttemptStore::set_provider_selection`, the existing canonical `host-settings.json` format, and the private `.host-settings.lock` path.
- Produces: no public API; native lock ownership is represented only by a private file descriptor and the existing typed error contract.

- [x] **Step 1: Write the failing crash-recovery test**

In `host_settings_invariant_test.cpp`, replace the test that pins an orphaned directory with a POSIX child-process fixture. The child opens `.host-settings.lock` as a regular file, takes `LOCK_EX`, signals readiness through a pipe, and waits. The parent must observe `host settings are busy`, terminate and reap the child, then successfully overwrite the selection and read back the new Provider. Make the fixture's destructor terminate/reap a still-live child so assertion failures cannot leak a process.

Change `host_settings_violations` so a persistent owned regular lock file is valid, while a directory/symlink/special `.host-settings.lock` still reports `the host settings lock is not a regular file`. Assert the successful sequence leaves no violation and no `.host-settings.lock/` directory.

- [x] **Step 2: Add the failing implementation-shape regression**

In `spec_regression_test.cpp`, read `attempt_store.cpp` and assert the Host settings lock region contains `LOCK_EX | LOCK_NB` and does not contain `std::filesystem::create_directory(lock_path` or `release_settings_lock`. This protects the required kernel-lifetime primitive without adding a public test hook.

- [x] **Step 3: Run RED**

```bash
scripts/core.sh build dev
ctest --preset dev \
  -R '^provider\.(host_settings_invariant|spec_regression)$' \
  --output-on-failure
```

Expected: FAIL because the old implementation treats the child-created regular lock file as permanently busy and still contains the directory-lock acquisition/release functions.

- [x] **Step 4: Implement the private native file lock**

In `attempt_store.cpp`, add native POSIX includes under `#ifndef __EMSCRIPTEN__`. Replace `acquire_settings_lock` / `release_settings_lock` with:

- an RAII `SettingsFileLock` that owns an acquired descriptor and closes it in its destructor;
- `acquire_settings_lock` returning `foundation::Result<int>`;
- native `open(O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600)` with `EINTR` retry;
- `fstat` validation that the descriptor is an owned single-link regular file, plus `fchmod(0600)`;
- `flock(LOCK_EX | LOCK_NB)` with `EINTR` retry and the existing busy error for `EWOULDBLOCK`/`EAGAIN`;
- post-lock `lstat` identity validation so replacing the named lock file cannot split writers across inodes;
- an Emscripten compile path returning descriptor `-1`, whose RAII owner performs no close.

Construct the RAII owner immediately after acquisition in `set_provider_selection`, delete every explicit release branch, and keep the owner alive through `read_host_settings` and `write_replace_atomic`.

- [x] **Step 5: Run GREEN and the provider neighborhood**

```bash
scripts/core.sh build dev
ctest --preset dev \
  -R '^provider\.(host_settings_invariant|spec_regression|durable_file|attempt_isolation|attempt_ledger_invariant|conformance)$' \
  --output-on-failure
```

Expected: all selected tests PASS. Run the two changed tests at least twice to expose process cleanup or descriptor-lifetime flakiness.

- [x] **Step 6: Apply the exact version cascade**

Update every current manifest and baked identity from the Version Management table. Do not rewrite historical version statements or immutable snapshot files. Regenerate the lock and Web identity only after `assembly.json` and `compiled_assembly.cpp` are byte-final:

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 tools/web-runtime/generate_runtime_identity.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
python3 tools/web-runtime/generate_runtime_identity.py --check
```

- [x] **Step 7: Update current Portal truth and freeze the canary snapshot**

Record on `/core/modules/provider-sdk/` that native Host settings writers fail fast on a kernel-owned advisory lock and recover automatically when the owner exits; reads remain lock-free because publication is atomic rename. Record the new invariant test on `/operations/testing-and-proof/`, and describe `1.0.26.0` as the G3 crash-recovery/identity cascade rather than a new product capability on the remaining affected routes.

```bash
scripts/architecture-portal.sh version 1.0.26.0 canary
scripts/architecture-portal.sh check
```

Expected: the snapshot command freezes `1.0.26.0 (canary)` and the full Portal check exits 0.

- [x] **Step 8: Run full local verification**

```bash
scripts/core.sh test dev full
scripts/core.sh test dev stress
python3 tests/build/version_test.py
python3 tests/conformance/version_lock_test.py
python3 tests/conformance/module_graph_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
python3 tools/web-runtime/generate_runtime_identity.py --check
scripts/architecture-portal.sh check
scripts/core.sh proof
```

Expected: every command exits 0; Proof reports `Assembly lock: MATCH`. Stress is explicit because this Task changes cross-process concurrency, even though it does not change lock-free realtime code.

- [x] **Step 9: Inspect local provenance and prepare atomic PR integration**

The clean-worktree snapshot gate requires committed source provenance, so preserve the local implementation, snapshot, and follow-up evidence commits without rebasing, squashing, or rewriting them. Inspect their file lists and the final worktree, run `git diff --check`, and complete exact-head local verification before handoff.

The reviewed Pull Request range is the task boundary. The Integration Queue squash-merges that range into one atomic `fix(provider-sdk): recover host settings lock after crashes` Conventional Commit on protected `main`. Only that resulting protected-main SHA can become a future Release-intent target through the separate authorization and Pull Request described above.

---

## Completion Evidence

Issue #204 is complete only when all of these are current and exact:

- the regression test was observed RED on the directory-lock implementation and GREEN on `flock`;
- the implementation holds one descriptor across the full read-modify-write and has no stale-lock reclamation heuristic;
- provider neighborhood, full, stress, version, lock, Portal, and Proof gates pass locally;
- the reviewed branch range contains only the planned implementation, snapshot provenance, and follow-up evidence files, and the final Pull Request squash is one atomic Conventional Commit on `main`;
- a PR targeting `main` declares the required Documentation Impact and expected CI mode;
- exact-head selected CI and `PR Gate` pass;
- the serialized Integration Queue squash-merges the exact reviewed head;
- PR state, merged `main` SHA/tree, Issue closure, and post-merge `main` CI are verified separately.
