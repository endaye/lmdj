# LMDJ Storage Platform Replacement-Reader Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make native `read_complete` always observe a complete old-or-new snapshot while an existing complete file is being replaced, so racing readers never return no-value because of that replacement.

**Architecture:** Keep retry inside shipped complete-read. Classify open/lock/short-pread/revalidation failures that a `renameat` publish can produce as replacement-transient and retry them; leave missing, symlink, and non-regular failures failing. Leave the contract test as an honest caller of the real default platform.

**Tech Stack:** C++20, POSIX `openat`/`pread`/`fstat`/`flock`/`renameat`, existing `LMDJ_CHECK` native contract tests, `scripts/version.py lock`, Architecture Portal freeze.

## Global Constraints

- Issue [#167](https://github.com/endaye/lmdj/issues/167) / machine-task C12. The contract is stronger than C12's "diagnose next time": a racing complete-read must observe a complete version.
- Start on `fix/storage-platform-replacement-reader`; never edit `main`.
- One implementation Conventional Commit. Do not commit intermediate TDD steps.
- Do not change Web/OPFS storage-platform behavior, Host-settings durability, or unrelated machine tasks (G2/G3/C5/…).
- Do not weaken same-inode mutation serialization (`LOCK_SH` vs `LOCK_EX` on the same inode) or the existing flock contract unless required for the replacement contract.
- Do not move retry/absorb into the test while production `read_complete` can still return no value.
- Do not mock the platform or start past `read_complete` in `test_replacement_readers_observe_only_complete_versions`.
- `assembly.lock.json` only via `python3 scripts/version.py lock`; never hand-edit.
- Portal snapshot channel is `canary`.
- Tests use `LMDJ_CHECK`, not GoogleTest.
- Do not push, open a PR, merge, tag, release, deploy, promote a Channel, or remotely close #167.

---

## File Structure

- Modify: `packages/project-io/src/native/storage_platform.cpp` — retry replacement-transient complete-read failures; treat an already-unlinked stable snapshot as complete.
- Modify: `packages/project-io/src/testing_hooks.hpp` — add `FaultPoint::complete_read`.
- Modify: `tests/core/project_io/storage_platform_contract_test.cpp` — keep the real race test; add a hook-driven retry proof; raise contention.
- Modify: `docs/quality/2026-08-17-machine-task-todo.md` — close C12 as actually fixed.
- Modify: project-io / facade / host / Product Build manifests, compiled assembly, generated lock and Runtime identity, current Portal pages, and the `1.0.26.0` canary snapshot.

## Version Management

Version impact: required.

| Identity | From | To |
| --- | --- | --- |
| `project-io` | 0.6.0 | 0.6.1 |
| `application-facade` | 1.4.2 | 1.4.3 |
| `core-cli` | 1.0.14 | 1.0.15 |
| `core-mcp` | 1.1.11 | 1.1.12 |
| `native-test-host` | 1.0.12 | 1.0.13 |
| `web-runtime-platform` | 0.3.2 | 0.3.3 |
| `web-runtime-host` | 1.2.11 | 1.2.12 |
| `creator-web` | 1.3.2 | 1.3.3 |
| Product Build | 1.0.25.0 | 1.0.26.0 |

Contract versions: none. Public ABI/capability additions: none. PATCH because complete-read reliability changes without a new public API. Facade and Hosts PATCH because their exact dependency pins change. Proof Providers stay `1.0.4` (they do not depend on project-io). Product Build allocates a new BUILD because Assembly member identity changes.

Rollback: reuse immutable Product Build `1.0.25.0`. Do not move tags.

Tag text `lmdj-v1.0.26.0` is future-only. This Task does not create, sign, or push a tag.

## Documentation Impact

Documentation impact: required

Affected portal pages: `/core/modules/project-io/` `/platform/storage/` `/assembly/lmdj/` `/operations/version-and-release/` `/product/capability-map/` `/core/modules/application-facade/` `/hosts/overview/` `/hosts/creator-web/` `/hosts/web-runtime/` `/overview/` `/operations/testing-and-proof/`

Reason: native complete-read now retries replacement-transient failures, and Product Build plus Assembly identities change.

---

### Task 1: Identify the no-value path and lock the contract in tests

**Files:**
- Modify: `packages/project-io/src/testing_hooks.hpp`
- Modify: `tests/core/project_io/storage_platform_contract_test.cpp`

**Interfaces:**
- Consumes: shipped `make_default_project_storage_platform()->read_complete` / `replace_complete`.
- Produces: a race test that still drives those APIs, plus a hook that can inject one replacement-transient complete-read failure.

Root cause: `replace_complete` publishes with `renameat` of a temp sibling. The writer's `LOCK_EX` is on that sibling inode; the reader's `LOCK_SH` is on the destination inode, so locks do not exclude the rename. `same_stable_metadata` only waives ctime when `st_nlink` goes 1→0. That does not cover:

- `openat` of the destination name returning ENOENT/ESTALE under overlay/NFS/shared-host IO
- short `pread` / "file ended" if the opened inode becomes unreadable across publish
- post-read revalidation failure when the snapshot was already unlinked (`st_nlink` 0→0) or metadata could not be re-read
- "changed while locking" if overlay copy-up appears to change identity

Those are the replacement-race no-value paths. Missing/symlink/non-regular complete-reads must stay failures.

- [ ] **Step 1: Add `FaultPoint::complete_read`**

```cpp
enum class FaultPoint {
  artifact_temp_sync,
  // ... existing points ...
  complete_read,
};
```

- [ ] **Step 2: Add a hook-driven retry test that fails before production retry exists**

```cpp
void test_complete_read_retries_replacement_transient_open() {
  TempDirectory temp;
  const auto directory = temp.path() / "retry";
  const auto path = directory / "pointer.json";
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(directory).has_value());
  auto lease = platform->acquire_writer(temp.path());
  LMDJ_CHECK(lease.has_value());
  const auto payload = bytes("complete-version");
  LMDJ_CHECK(platform->create_immutable(path, payload).has_value());

  complete_read_fault_calls = 0;
  StorageHookGuard hook(fail_first_complete_read_open);
  const auto observed = platform->read_complete(path);
  LMDJ_CHECK(observed.has_value());
  LMDJ_CHECK(observed.value() == payload);
  LMDJ_CHECK(complete_read_fault_calls >= 2);
}
```

`fail_first_complete_read_open` fails only `FaultPoint::complete_read` on the first call with `io_error` / `storage file could not be opened` / `system_error=strerror(ENOENT)`, then succeeds.

- [ ] **Step 3: Keep and tighten the real race test**

Keep `test_replacement_readers_observe_only_complete_versions` calling shipped `read_complete` concurrently with shipped `replace_complete`. Do not retry inside the test. Raise contention: four reader threads and 64 replacements of the two 256KiB payloads. A no-value result still throws `code=` and `message=`.

- [ ] **Step 4: Run the binary and confirm the new retry test fails for the missing retry**

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --test-dir build/core/dev -R '^project_io\.storage_platform$' --output-on-failure
```

Expected: FAIL with the injected `storage file could not be opened` (or the race test's no-value throw). Sibling missing/symlink/non-regular cases must still be in this binary.

---

### Task 2: Retry replacement-transient complete-reads in production

**Files:**
- Modify: `packages/project-io/src/native/storage_platform.cpp`

**Interfaces:**
- Consumes: existing `open_regular_file`, `pread`, `same_stable_metadata`.
- Produces: `read_complete` that returns old-or-new complete bytes across `replace_complete`.

- [ ] **Step 1: Treat an already-unlinked stable snapshot as complete**

In `same_stable_metadata`, waive ctime when identity/size/mode/uid/gid/mtime match and the snapshot is unlinked (`st_nlink` 1→0 or already 0→0).

- [ ] **Step 2: Split one complete-read attempt and wrap it with bounded retry**

Invoke `FaultPoint::complete_read` at the start of one attempt (testing builds only). Retry at most 16 times, yielding between attempts, only when the error is `io_error` and one of:

- `storage file could not be opened` with `ENOENT`/`ESTALE`
- `storage file could not be read completely` with `ESTALE`/`EAGAIN`/`EWOULDBLOCK`
- `storage file ended during complete read`
- `storage file changed while locking`
- `storage metadata could not be revalidated`
- `storage file changed during complete read`

Do not retry `invalid_project` (symlink) or "not a regular file". After the bound, return the last error so a genuinely missing path still fails.

- [ ] **Step 3: Re-run the contract binary**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R '^project_io\.storage_platform$' --output-on-failure
```

Expected: PASS, including `project storage platform tests: PASS`.

---

### Task 3: Version cascade, current Portal, C12 close, canary snapshot

**Files:**
- Modify manifests and identity literals to the Version Management table
- Modify current Portal MDX listed in Documentation Impact (additive `1.0.26.0` prose; do not rewrite `1.0.25.0` evidence)
- Generate lock, Runtime identity, and `1.0.26.0` / `canary` snapshot
- Modify: `docs/quality/2026-08-17-machine-task-todo.md` C12 row

- [ ] **Step 1: Apply the version table and regenerate derived identity**

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
```

- [ ] **Step 2: Update current Portal prose and close C12**

State on `/core/modules/project-io/` and `/platform/storage/` that native complete-read retries replacement-transient failures so a racing reader observes a complete old or new version. Record Product Build `1.0.26.0` as this cascade, not a new product capability.

- [ ] **Step 3: Freeze the canary snapshot from a clean worktree**

Commit the non-snapshot files first if needed so freeze sees a clean tree, then:

```bash
scripts/architecture-portal.sh version 1.0.26.0 canary
scripts/architecture-portal.sh check
```

---

### Task 4: Verify and commit

- [ ] **Step 1: Run the contract target five consecutive times**

```bash
for n in 1 2 3 4 5; do
  ctest --test-dir build/core/dev -R '^project_io\.storage_platform$' --output-on-failure \
    | tee "{SCRATCH}/storage_platform-run${n}.log"
done
```

Each run must exit 0 and print `project storage platform tests: PASS`. Record Linux/ASan/Contabo unavailability in `{SCRATCH}/env-limit.txt` if those hosts cannot run here.

- [ ] **Step 2: Conventional Commit on `fix/storage-platform-replacement-reader`**

```
fix(project-io): retry complete-read across atomic replacement

Closes #167
```

Do not push.
