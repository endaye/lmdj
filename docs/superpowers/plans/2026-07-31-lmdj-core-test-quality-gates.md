# LMDJ Core Test Quality Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Headless Core test suite into a measurable, risk-based quality gate that grows with Core behavior without using a fixed test-count quota.

**Architecture:** Keep CTest as the canonical runner, classify every registered test into one execution tier, instrument first-party C++ sources with LLVM source-based coverage, and add deterministic invariant, persistence-fault, and C ABI concurrency suites where defect impact is highest. Pull requests retain a short cross-platform gate; sanitizer, coverage, and bounded stress lanes provide deeper evidence without making every local edit slow.

**Tech Stack:** C++20, CMake 3.24+, CTest, Python 3.11+ standard library, LLVM `llvm-profdata`/`llvm-cov`, AddressSanitizer, UndefinedBehaviorSanitizer, ThreadSanitizer, GitHub Actions.

## Global Constraints

- `main` remains protected and deployable; implementation happens on short-lived `codex/` branches in isolated worktrees.
- New product code remains under `packages/`, `apps/`, `providers/`, `products/`, `contracts/`, or `workers/`; `references/demos/` stays frozen.
- Hosts use only Application Facade and never parse Project bundles.
- Project Truth remains authoritative; Runtime Snapshot remains immutable derived state.
- Pattern events continue to reference Pad Slots, never Assets directly.
- Provider selection and Attempt failure remain Workspace state and never mutate Project Truth.
- `lmdj.patch.v1` and `lmdj.materials.v1` remain retired and must not appear in new code, fixtures, or tests.
- Tests use deterministic seeds and print the seed on failure; no test depends on wall-clock timing for correctness.
- No skipped assertion, quarantine list, retry-on-failure, or platform-specific golden rebaseline is permitted.
- Test-only fault hooks compile only into test targets and are not exposed through public Module headers or the C ABI.
- Each implementation Task uses red-green TDD, stages only its declared files, and becomes one reviewable Conventional Commit.

---

## Current Baseline and Target

The verified `1.0.6.0` baseline on 2026-07-31 has:

- 25 registered CTest suites, all passing in the Dev preset in 15.32 seconds;
- 118 explicitly named C++ `test_*` scenarios plus Assembly Loader and Python Host, Contract, Build, Version, and E2E checks;
- approximately 7,197 nonblank test C++ lines against 10,134 nonblank first-party product C++ lines;
- ASan/UBSan support in a local preset, but no sanitizer CI job;
- no source coverage report or coverage threshold;
- Product Assembly, Assembly lock, CLI/MCP parity, deterministic Golden WAV, Provider failure isolation, conflicted Take recovery, and the complete Headless Core Proof implemented and passing.

The target is not “N tests per version.” The target is:

| Gate | Target |
| --- | --- |
| Pull-request functional gate | 100% registered tests pass on Ubuntu and macOS |
| Fast local feedback | `unit` + `component` tiers finish within 30 seconds on the reference Mac |
| Overall first-party C++ coverage | Lines >= 80%, branches >= 70% |
| Domain, Facade/C ABI coverage | Lines >= 90%, branches >= 80% |
| Project I/O coverage | Lines >= 85%, branches >= 75% |
| Cooker and Audio coverage | Lines >= 90%, branches >= 80% |
| Provider SDK coverage | Lines >= 85%, branches >= 75% |
| Sanitizers | ASan/UBSan full suite passes; TSan C ABI concurrency suite passes |
| Flake policy | 20 consecutive bounded stress repetitions pass with zero retry |
| Determinism | Identical Project inputs yield identical canonical state, snapshot values, and golden WAV hash |

The expected Proof-stage suite size is approximately 180–250 focused C++ scenarios, 15–25 Contract/Host integration scenarios, and 3–5 complete E2E journeys. These ranges are planning capacity, not acceptance gates. A change is accepted because its behavior and risk branches are covered, not because a counter increased.

## Test Layer Model

Every CTest entry has exactly one tier label:

| Tier | Boundary | Examples | Pull request |
| --- | --- | --- | --- |
| `unit` | Pure function or one in-memory module, no filesystem/process | IDs, canonical JSON, Domain command rules, mix math | Yes |
| `component` | One public Module surface with temporary filesystem or linked collaborators | Project Store, Cooker, Audio, Provider SDK, Application Facade | Yes |
| `contract` | Public schema, ABI symbols, module/version/build constraints | Schema conformance, dynamic load, active-tree guard | Yes |
| `host` | CLI or MCP in a child process through Application Facade/C ABI | CLI behavior, MCP lifecycle, CLI/MCP parity | Yes |
| `e2e` | Product Assembly through public Host surfaces | Headless Core Proof | Yes |
| `stress` | Repeated or concurrent execution intended for sanitizer/nightly lanes | C ABI lifetime race, persistence interruption matrix | Sanitizer/nightly |

Additional non-tier labels such as `audio`, `persistence`, `provider`, and `abi` may select a risk area. They never replace the required tier.

## Test Selection Rule for Every Core Change

For each changed behavior, the implementing Task must identify and cover:

1. one valid transition or result;
2. every stable public error code introduced or changed;
3. the “state remains unchanged” assertion for every failed mutation;
4. replay/idempotency behavior when a command or Attempt identity can repeat;
5. restart/recovery behavior when persisted state is involved;
6. boundary values and integer overflow/underflow behavior for audio or frame math;
7. ownership, stale-handle, and concurrent lifetime behavior for C ABI changes;
8. a public-surface Host or E2E check when the behavior crosses a Module boundary.

Pure refactors need no artificial scenario count, but all existing relevant tests and the coverage gate must remain green. A defect fix always adds a regression reproducer unless an existing test already fails for that exact defect.

## File Responsibility Map

### Test governance and registration

- Create `docs/quality/core-test-policy.md`: human-readable test tiers, selection rule, thresholds, and evidence rules.
- Create `cmake/LmdjTesting.cmake`: one registration function that applies tier labels, timeouts, and working directories.
- Create `tests/build/test_test_taxonomy.py`: validates CTest JSON metadata without executing tests.
- Modify root and Module `CMakeLists.txt` files: replace raw `add_test` calls with the registration function.

### Coverage

- Create `cmake/LmdjCoverage.cmake`: LLVM instrumentation flags guarded by `LMDJ_ENABLE_COVERAGE`.
- Create `scripts/core-coverage.sh`: configure, build, run, merge profiles, and export a bounded JSON summary.
- Create `tests/quality/coverage_gate.py`: validate LLVM summary JSON against repository thresholds.
- Create `tests/quality/coverage_gate_test.py`: positive and negative fixtures for the gate itself.
- Create `tests/quality/core-coverage-thresholds.json`: checked-in path thresholds.
- Modify `CMakePresets.json`: add a `coverage` preset.

### High-risk behavioral coverage

- Create `tests/core/support/deterministic_rng.hpp`: fixed cross-platform PRNG and seed reporting.
- Create `tests/core/domain/model_sequence_test.cpp`: generated command/revision/replay invariants.
- Create `tests/core/cooker/determinism_matrix_test.cpp`: generated Project-to-Snapshot determinism.
- Create `packages/project-io/src/testing_hooks.hpp`: test-build-only persistence fault points.
- Create `tests/core/project_io/fault_matrix_test.cpp`: restart and no-mutation assertions for publish failures.
- Create `tests/core/facade/c_api_stress_test.cpp`: independent-engine, stale-handle, and lifetime races.

### CI

- Modify `cmake/LmdjWarnings.cmake`: select ASan/UBSan or TSan without combining incompatible sanitizers.
- Modify `CMakePresets.json`: add `tsan` and retain `asan`.
- Modify `scripts/core.sh`: recognize `coverage` and `tsan` presets and `fast`, `full`, and `stress` test modes.
- Create `tests/build/core_script_test.py`: verify the stable shell entry point's mode routing.
- Modify `.github/workflows/ci.yml`: add ASan/UBSan and coverage jobs.
- Create `.github/workflows/core-nightly.yml`: run TSan and bounded repeated stress.

## Version Management

Version impact: none

Reason: this plan adds post-`1.0.6.0` tests, test-only hooks, build instrumentation, documentation, and CI gates without changing a public Product behavior, Module API/ABI, persisted Project semantics, Contract, Provider result, Assembly, or model identity. Release binaries are built with coverage and test hooks disabled.

- Product Build remains `1.0.6.0`.
- Module, Contract, Provider, and Model versions remain unchanged.
- No `version.json`, `module.json`, Schema, Provider manifest, Assembly lock, or model identity file is modified.
- The existing immutable `lmdj-v1.0.6.0` tag remains at the completed Core Proof commit; no tag is created or moved for this test-infrastructure work.
- Commit does not authorize push, PR creation, merge, tag, Channel promotion, release, or deployment.
- Rollback is the Git revert of the individual Task commit; no published identity changes.

---

### Task 1: Establish the Test Taxonomy and Registration Contract

**Files:**

- Create: `docs/quality/core-test-policy.md`
- Create: `cmake/LmdjTesting.cmake`
- Create: `tests/build/test_test_taxonomy.py`
- Modify: `CMakeLists.txt`
- Modify: `packages/foundation/CMakeLists.txt`
- Modify: `packages/authoring-domain/CMakeLists.txt`
- Modify: `packages/project-io/CMakeLists.txt`
- Modify: `packages/project-cooker/CMakeLists.txt`
- Modify: `packages/audio-runtime/CMakeLists.txt`
- Modify: `tests/core/provider/CMakeLists.txt`
- Modify: `packages/application-facade/CMakeLists.txt`
- Modify: `apps/core-cli/CMakeLists.txt`

**Interfaces:**

- Produces this CMake function:

```cmake
lmdj_add_test(
  NAME <ctest-name>
  TIER <unit|component|contract|host|e2e|stress>
  COMMAND <command> [arguments...]
  [LABELS <risk-label>...]
  [TIMEOUT <seconds>]
  [WORKING_DIRECTORY <absolute-path>]
)
```

- Every registered test exposes exactly one tier through CTest JSON.
- Default timeouts are `unit=10`, `component=30`, `contract=30`, `host=120`, `e2e=180`, and `stress=300` seconds.

- [ ] **Step 1: Write the failing taxonomy validator**

Create `tests/build/test_test_taxonomy.py` to accept the configured build directory in `argv[1]`, run `ctest --test-dir <build-dir> --show-only=json-v1`, parse stdout, and fail when a test has zero or multiple labels from:

```python
TIERS = {"unit", "component", "contract", "host", "e2e", "stress"}
MAX_TIMEOUT = {
    "unit": 10.0,
    "component": 30.0,
    "contract": 30.0,
    "host": 120.0,
    "e2e": 180.0,
    "stress": 300.0,
}
```

The script must also fail on a missing timeout, a timeout above the tier limit, duplicate test names, or an empty test list. Its success sentinel is:

```text
Core test taxonomy: PASS (<count> registered tests)
```

- [ ] **Step 2: Prove the validator fails against current registration**

Run:

```bash
python3 tests/build/test_test_taxonomy.py build/core/dev
```

Expected: FAIL because current tests have no tier labels.

- [ ] **Step 3: Add the registration helper**

Create `cmake/LmdjTesting.cmake` with `cmake_parse_arguments`, tier validation, the timeout defaults above, `add_test`, and one `set_tests_properties` call that writes `LABELS`, `TIMEOUT`, and optional `WORKING_DIRECTORY`.

Reject an invalid or missing tier at configure time:

```cmake
if(NOT TEST_TIER IN_LIST lmdj_test_tiers)
  message(FATAL_ERROR
    "lmdj_add_test ${TEST_NAME} requires one valid TIER")
endif()
```

- [ ] **Step 4: Migrate all 25 existing registrations**

Use these tier assignments:

```text
build.active_tree                contract
host.mcp_stdio                   host
host.mcp_facade_parity           host
build.version                    contract
contract.schemas                 contract
conformance.module_graph         contract
conformance.version_lock         contract
build.proof_failure_artifacts    contract + persistence
e2e.proof_path_safety            contract + persistence
e2e.headless_core_proof          e2e + assembly
foundation.artifact              unit
domain.project                   unit
domain.command_handler           unit
project_io.project_store         component + persistence
project_io.take_journal          component + persistence
cooker.project                   component + audio
audio.offline_renderer           component + audio
provider.conformance             component + provider
provider.attempt_isolation       component + provider
provider.spec_regression         component + provider
facade.application               component
facade.assembly_loader           component + assembly
facade.c_api                     component + abi
facade.dynamic_load              contract + abi
host.cli                         host
```

Preserve current commands, environment properties, target dependencies, and working directories.

- [ ] **Step 5: Register and pass the taxonomy test**

Register `build.test_taxonomy` as a `contract` tier test. Pass `${CMAKE_BINARY_DIR}` to the Python validator so it always inspects the configured build tree that owns the running test.

Run:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev
```

Expected: 26/26 CTest suites pass and the taxonomy sentinel appears.

- [ ] **Step 6: Document the policy**

Write `docs/quality/core-test-policy.md` with the Test Layer Model, Test Selection Rule, coverage thresholds, deterministic seed rule, no-retry policy, and the distinction between automated evidence and device/release acceptance.

- [ ] **Step 7: Commit**

```bash
git add \
  docs/quality/core-test-policy.md \
  cmake/LmdjTesting.cmake \
  tests/build/test_test_taxonomy.py \
  CMakeLists.txt \
  packages/foundation/CMakeLists.txt \
  packages/authoring-domain/CMakeLists.txt \
  packages/project-io/CMakeLists.txt \
  packages/project-cooker/CMakeLists.txt \
  packages/audio-runtime/CMakeLists.txt \
  tests/core/provider/CMakeLists.txt \
  packages/application-facade/CMakeLists.txt \
  apps/core-cli/CMakeLists.txt
git diff --cached --check
git commit -m "test(core): classify canonical test tiers"
```

---

### Task 2: Add LLVM Coverage Measurement and Thresholds

**Files:**

- Create: `cmake/LmdjCoverage.cmake`
- Create: `scripts/core-coverage.sh`
- Create: `tests/quality/coverage_gate.py`
- Create: `tests/quality/coverage_gate_test.py`
- Create: `tests/quality/core-coverage-thresholds.json`
- Modify: `CMakeLists.txt`
- Modify: `CMakePresets.json`
- Modify: `scripts/core.sh`
- Modify: `tests/build/test_active_tree.sh`

**Interfaces:**

- `LMDJ_ENABLE_COVERAGE=ON` is supported only with Clang-compatible source-based coverage.
- `scripts/core-coverage.sh report` creates:

```text
build/core/coverage/coverage/merged.profdata
build/core/coverage/coverage/summary.json
build/core/coverage/coverage/report.txt
```

- `scripts/core-coverage.sh check` creates the same artifacts and applies `tests/quality/core-coverage-thresholds.json`.
- Reports include first-party `.cpp` and public `.hpp` files under `packages/`, `providers/`, `products/lmdj/`, and `apps/core-cli/`; they exclude `tests/`, `build/`, `_deps/`, and frozen references.
- Root CMake generates `build/core/coverage/coverage-objects.txt` with one absolute `$<TARGET_FILE:...>` path per coverage object:

```text
lmdj_foundation_tests
lmdj_domain_project_tests
lmdj_domain_command_handler_tests
lmdj_project_store_tests
lmdj_take_journal_tests
lmdj_project_cooker_tests
lmdj_audio_runtime_tests
lmdj_provider_conformance_tests
lmdj_provider_attempt_isolation_tests
lmdj_provider_spec_regression_tests
lmdj_application_facade_tests
lmdj_assembly_loader_tests
lmdj_application_c_api_tests
lmdj_application_dynamic_load_tests
lmdj_core_cli
lmdj_core_c
```

- [ ] **Step 1: Write coverage-gate unit fixtures**

Create `tests/quality/coverage_gate_test.py` with temporary summary/threshold JSON files covering:

```text
exact threshold passes
line threshold below by 0.01 fails
branch threshold below by 0.01 fails
missing configured path fails
zero executable regions fails
excluded test path is ignored
```

Run:

```bash
python3 tests/quality/coverage_gate_test.py
```

Expected: FAIL because `coverage_gate.py` does not exist.

- [ ] **Step 2: Implement the JSON gate**

`coverage_gate.py` accepts:

```text
python3 tests/quality/coverage_gate.py \
  --summary <llvm-export-json> \
  --thresholds <threshold-json>
```

It aggregates `data[*].files[*].summary.lines` and `.branches` by configured path prefix using `count` and `covered`, rounds only for display, compares unrounded ratios, and prints one deterministic row per prefix. Exit `0` ends with:

```text
Core coverage gate: PASS
```

Exit `1` lists every failed prefix and its actual/required percentages.

- [ ] **Step 3: Check in the final thresholds**

Create `tests/quality/core-coverage-thresholds.json`:

```json
{
  "overall": {"lines": 80, "branches": 70},
  "paths": {
    "packages/foundation/": {"lines": 85, "branches": 75},
    "packages/authoring-domain/": {"lines": 90, "branches": 80},
    "packages/project-io/": {"lines": 85, "branches": 75},
    "packages/project-cooker/": {"lines": 90, "branches": 80},
    "packages/audio-runtime/": {"lines": 90, "branches": 80},
    "packages/provider-sdk/": {"lines": 85, "branches": 75},
    "packages/application-facade/": {"lines": 90, "branches": 80}
  }
}
```

Providers and CLI contribute to `overall` until they grow enough to warrant independent thresholds.

- [ ] **Step 4: Add coverage instrumentation**

`cmake/LmdjCoverage.cmake` must reject MSVC and non-Clang compilers, and apply:

```cmake
add_compile_options(
  -fprofile-instr-generate
  -fcoverage-mapping
)
add_link_options(
  -fprofile-instr-generate
  -fcoverage-mapping
)
```

Only apply the flags when `LMDJ_ENABLE_COVERAGE` is true. Coverage and sanitizer options are mutually exclusive at configure time.

- [ ] **Step 5: Add the coverage preset and runner**

Add a `coverage` configure/build/test preset with:

```json
{
  "CMAKE_BUILD_TYPE": "Debug",
  "LMDJ_ENABLE_COVERAGE": "ON"
}
```

`scripts/core-coverage.sh` must:

1. resolve `llvm-profdata` and `llvm-cov` from `PATH`, falling back to `xcrun --find` on macOS;
2. configure and build the coverage preset;
3. remove only `build/core/coverage/profiles/*.profraw`;
4. run CTest with `LLVM_PROFILE_FILE=.../%p-%m.profraw`;
5. merge profiles with `llvm-profdata merge -sparse`;
6. read each existing executable/shared-library path from `coverage-objects.txt` and fail on a missing entry;
7. export JSON with `llvm-cov export`;
8. write a readable `llvm-cov report`;
9. invoke the gate only in `check` mode.

The script fails if no raw profile, object, or first-party source is present.

- [ ] **Step 6: Verify measurement before enforcing the real gate**

Run:

```bash
python3 tests/quality/coverage_gate_test.py
scripts/core-coverage.sh report
```

Expected: gate unit tests pass and a real summary/report is generated. Record the actual module percentages in the Task commit message body; do not lower the checked-in final thresholds to match the baseline.

- [ ] **Step 7: Protect the active tree**

Extend `tests/build/test_active_tree.sh` so coverage output is permitted only below `build/core/`, and no `.profraw`, `.profdata`, or generated report can appear under a tracked source directory.

- [ ] **Step 8: Commit**

```bash
git add \
  cmake/LmdjCoverage.cmake \
  scripts/core-coverage.sh \
  tests/quality/coverage_gate.py \
  tests/quality/coverage_gate_test.py \
  tests/quality/core-coverage-thresholds.json \
  CMakeLists.txt \
  CMakePresets.json \
  scripts/core.sh \
  tests/build/test_active_tree.sh
git diff --cached --check
git commit -m "test(core): measure source coverage"
```

---

### Task 3: Add Deterministic Domain and Cooker Invariant Matrices

**Files:**

- Create: `tests/core/support/deterministic_rng.hpp`
- Create: `tests/core/domain/model_sequence_test.cpp`
- Create: `tests/core/cooker/determinism_matrix_test.cpp`
- Modify: `packages/authoring-domain/CMakeLists.txt`
- Modify: `packages/project-cooker/CMakeLists.txt`

**Interfaces:**

- `lmdj::test::DeterministicRng(std::uint64_t seed)` implements fixed `xorshift64*`; its algorithm and constants are part of test infrastructure and identical on all platforms.
- `next_u64()`, `bounded(std::uint64_t upper_exclusive)`, and `seed()` are the only public methods.
- Tests use seeds `0..255`, include the failing seed in exceptions, and perform no production randomness.

- [ ] **Step 1: Write the deterministic PRNG contract**

Create the header and assert its first five values for seed `1` in `model_sequence_test.cpp`. Reject seed `0` by substituting the documented nonzero state `0x9e3779b97f4a7c15`.

- [ ] **Step 2: Add failing Domain invariant scenarios**

Add these named scenarios:

```text
test_generated_valid_sequences_increment_revision_once
test_generated_stale_commands_leave_state_byte_identical
test_generated_duplicate_commands_replay_original_outcome
test_generated_invalid_ids_fail_before_receipt_lookup
test_generated_pad_reassignment_keeps_pattern_slot_identity
```

Each seed creates one Project and 64–256 commands selected from the existing `ImportAsset`, `AssignPad`, `CreatePattern`, and `RecordTake` variants. After every operation assert revision, receipt identity, canonical JSON equality on failure, and that every Pattern event still names a valid Pad Slot.

- [ ] **Step 3: Prove the Domain matrix target is missing**

Configure and build:

```bash
cmake --build build/core/dev \
  --target lmdj_domain_model_sequence_tests
```

Expected: FAIL because the target has not been registered.

- [ ] **Step 4: Register and pass the Domain matrix**

Register `domain.model_sequence` as tier `unit`, labels `domain;generated`, timeout 10 seconds. Do not add parallel mutation semantics, command auto-rebase, or Quantize behavior.

- [ ] **Step 5: Add failing Cooker determinism scenarios**

Add:

```text
test_generated_projects_cook_to_identical_snapshots
test_generated_artifact_resolution_is_content_deduplicated
test_generated_invalid_artifacts_never_publish_partial_snapshot
test_generated_slot_reassignment_resolves_current_asset
```

For each seed, cook the same immutable Project twice with fresh resolvers and compare every typed Snapshot field and PCM sample value. Use fixed in-memory mono/stereo PCM fixtures; do not invoke filesystem or offline rendering in this suite.

- [ ] **Step 6: Register and pass the Cooker matrix**

Register `cooker.determinism_matrix` as tier `unit`, labels `audio;generated`, timeout 10 seconds.

Run:

```bash
scripts/core.sh test dev
scripts/core-coverage.sh report
```

Expected: all functional tests pass and Domain/Cooker coverage moves toward their checked-in thresholds.

- [ ] **Step 7: Commit**

```bash
git add \
  tests/core/support/deterministic_rng.hpp \
  tests/core/domain/model_sequence_test.cpp \
  tests/core/cooker/determinism_matrix_test.cpp \
  packages/authoring-domain/CMakeLists.txt \
  packages/project-cooker/CMakeLists.txt
git diff --cached --check
git commit -m "test(core): exercise deterministic state invariants"
```

---

### Task 4: Add a Restart-Safe Persistence Fault Matrix

**Files:**

- Create: `packages/project-io/src/testing_hooks.hpp`
- Create: `tests/core/project_io/fault_matrix_test.cpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `packages/project-io/src/take_journal.cpp`
- Modify: `packages/project-io/CMakeLists.txt`

**Interfaces:**

- Under `LMDJ_PROJECT_IO_TESTING=1`, expose only from the private source header:

```cpp
enum class FaultPoint {
  artifact_temp_sync,
  artifact_publish,
  transaction_temp_sync,
  transaction_publish,
  checkpoint_temp_sync,
  checkpoint_publish,
  manifest_temp_sync,
  manifest_publish,
  active_journal_sync,
  active_journal_remove,
  active_directory_sync,
  sealed_directory_sync,
};

using FaultHook = foundation::Result<void> (*)(
    FaultPoint,
    const std::filesystem::path&);

void set_fault_hook(FaultHook hook);
```

- Production builds do not declare, link, or branch through this hook.
- A failing hook returns the existing typed I/O error; it does not introduce a public error code.

- [ ] **Step 1: Write the 12-point failing matrix**

Create one table-driven test that injects each `FaultPoint` exactly once and asserts:

```text
the operation reports failure
the previous manifest remains loadable
Project revision is unchanged unless the manifest commit completed
restart either completes the committed transaction or removes its orphan
no temporary file is interpreted as Project Truth
no symlink outside the bundle is followed
the hook invocation count is exactly one
```

Split the public scenarios by invariant, not by fault point:

```text
test_publish_faults_preserve_previous_project_truth
test_restart_classifies_committed_and_uncommitted_files
test_take_cleanup_faults_leave_replayable_obligation
test_fault_hooks_are_absent_from_release_library_symbols
```

- [ ] **Step 2: Prove the tests fail before hooks exist**

Run:

```bash
cmake --build --preset dev --target lmdj_project_io_fault_matrix_tests
```

Expected: build fails because `testing_hooks.hpp` and the target do not exist.

- [ ] **Step 3: Implement private fault interception**

Route existing test-only active-directory synchronization through the new hook and add interception immediately before each named filesystem operation. The production code path remains the same statement sequence when `LMDJ_PROJECT_IO_TESTING` is undefined.

- [ ] **Step 4: Register and pass the matrix**

Register `project_io.fault_matrix` as tier `stress`, labels `persistence`, timeout 120 seconds. Link only `lmdj_project_io_testable`.

Run:

```bash
ctest --test-dir build/core/dev \
  -R '^project_io\\.(project_store|take_journal|fault_matrix)$' \
  --output-on-failure
```

Expected: all three persistence suites pass.

- [ ] **Step 5: Verify release symbol isolation**

Build Release and confirm neither `FaultPoint` nor `set_fault_hook` is present:

```bash
scripts/core.sh configure release
scripts/core.sh build release
nm -g build/core/release/lib/liblmdj_project_io.a \
  | rg 'FaultPoint|set_fault_hook'
```

Expected: `rg` exits `1` with no matches.

- [ ] **Step 6: Commit**

```bash
git add \
  packages/project-io/src/testing_hooks.hpp \
  packages/project-io/src/project_store.cpp \
  packages/project-io/src/take_journal.cpp \
  packages/project-io/CMakeLists.txt \
  tests/core/project_io/fault_matrix_test.cpp
git diff --cached --check
git commit -m "test(project-io): inject persistence publish faults"
```

---

### Task 5: Add C ABI Concurrency Stress and ThreadSanitizer

**Files:**

- Create: `tests/core/facade/c_api_stress_test.cpp`
- Modify: `packages/application-facade/CMakeLists.txt`
- Modify: `CMakeLists.txt`
- Modify: `cmake/LmdjWarnings.cmake`
- Modify: `CMakePresets.json`
- Modify: `scripts/core.sh`

**Interfaces:**

- `LMDJ_SANITIZER` accepts `none`, `address`, or `thread`.
- `address` enables `-fsanitize=address,undefined`.
- `thread` enables `-fsanitize=thread`.
- Coverage, AddressSanitizer, and ThreadSanitizer modes are mutually exclusive.
- `facade.c_api_stress` is tier `stress`, labels `abi;concurrency`, timeout 180 seconds.

- [ ] **Step 1: Write failing C ABI stress scenarios**

Add:

```text
test_32_independent_engines_make_progress_concurrently
test_query_and_free_race_never_reuses_stale_handle
test_10000_create_free_cycles_keep_all_stale_handles_invalid
test_response_strings_can_be_freed_in_reverse_thread_order
test_blocked_engine_does_not_block_unrelated_engine_lifetimes
```

Use `std::barrier`, `std::jthread`, atomics, and fixed iteration counts. Every worker records its result into an indexed slot; only the parent thread performs `LMDJ_CHECK`, so exception transport cannot terminate a worker.

- [ ] **Step 2: Prove current ThreadSanitizer mode is unsupported**

Run:

```bash
cmake --preset tsan
```

Expected: FAIL because the preset and sanitizer selection do not exist.

- [ ] **Step 3: Split sanitizer selection**

Replace the boolean sanitizer branch with the exact modes above. Reject an unknown value and reject ThreadSanitizer on MSVC. Preserve `-fno-omit-frame-pointer` for both modes.

Change the root MCP ASan-runtime branch from `if(LMDJ_ENABLE_SANITIZERS)` to:

```cmake
if(LMDJ_SANITIZER STREQUAL "address")
```

ThreadSanitizer runs only the native C ABI stress executable and never preloads a TSan runtime into Python.

The existing `asan` preset sets:

```json
{"LMDJ_SANITIZER": "address"}
```

The new `tsan` preset sets:

```json
{
  "CMAKE_BUILD_TYPE": "Debug",
  "LMDJ_SANITIZER": "thread"
}
```

- [ ] **Step 4: Register and run the stress target**

Run without sanitizer first:

```bash
ctest --test-dir build/core/dev \
  -R '^facade\\.c_api_stress$' \
  --output-on-failure
```

Then configure/build TSan and run only the native stress binary:

```bash
scripts/core.sh configure tsan
scripts/core.sh build tsan
ctest --test-dir build/core/tsan \
  -R '^facade\\.c_api_stress$' \
  --output-on-failure
```

Expected: PASS with no ThreadSanitizer report.

- [ ] **Step 5: Confirm ASan/UBSan remains green**

Run:

```bash
scripts/core.sh configure asan
scripts/core.sh build asan
scripts/core.sh test asan
```

Expected: all non-TSan tests pass with no AddressSanitizer or UndefinedBehaviorSanitizer report.

- [ ] **Step 6: Commit**

```bash
git add \
  tests/core/facade/c_api_stress_test.cpp \
  packages/application-facade/CMakeLists.txt \
  CMakeLists.txt \
  cmake/LmdjWarnings.cmake \
  CMakePresets.json \
  scripts/core.sh
git diff --cached --check
git commit -m "test(facade): stress C ABI concurrency"
```

---

### Task 6: Enforce the Gates in CI Without Slowing the Inner Loop

**Files:**

- Create: `.github/workflows/core-nightly.yml`
- Create: `tests/build/core_script_test.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `CMakeLists.txt`
- Modify: `scripts/core.sh`
- Modify: `docs/quality/core-test-policy.md`

**Interfaces:**

- `scripts/core.sh test <preset> fast` runs only tiers `unit|component`.
- `scripts/core.sh test <preset> full` runs everything except `stress`.
- `scripts/core.sh test <preset> stress` runs only tier `stress`.
- Existing `scripts/core.sh test <preset>` remains an alias of `full`.

- [ ] **Step 1: Add runner argument contract tests**

Create `tests/build/core_script_test.py`. It places a temporary executable named `ctest` first in `PATH`, invokes `scripts/core.sh`, and asserts the recorded arguments:

```text
test dev fast -> ctest --preset dev -L unit|component
test dev full -> ctest --preset dev -LE stress
test dev stress -> ctest --preset dev -L stress
test dev -> ctest --preset dev -LE stress
unknown mode -> exit 64
```

Run:

```bash
python3 tests/build/core_script_test.py
```

Expected: FAIL until `scripts/core.sh` supports the modes.

- [ ] **Step 2: Implement the runner modes**

Preserve all existing configure/build/test calls and usage errors. Pass the regular expression `unit|component` as one argument after `-L`. Do not make `full` include `stress`; the nightly and sanitizer lanes own repeated concurrency/fault tests.

Register `build.core_script` as tier `contract`, timeout 10 seconds.

- [ ] **Step 3: Add pull-request CI jobs**

Keep the existing Ubuntu/macOS Release matrix and its canonical command:

```text
scripts/core.sh proof
```

Add:

```text
core-asan: Ubuntu, configure/build ASan, full suite
core-coverage: Ubuntu with clang, scripts/core-coverage.sh check
```

The existing Proof remains the functional and Product Assembly gate; the new jobs supplement it. Upload `build/core/coverage/coverage/report.txt` and `summary.json` only on coverage failure. Artifacts contain no Project bundles or user data.

- [ ] **Step 4: Add bounded nightly jobs**

`core-nightly.yml` runs on manual dispatch and cron `0 19 * * *` (03:00 Asia/Shanghai):

```text
core-tsan: Ubuntu, facade.c_api_stress under TSan
core-stress: Ubuntu Release, ctest stress tier repeated 20 times
```

Use:

```bash
ctest --test-dir build/core/release \
  -L stress \
  --repeat until-fail:20 \
  --output-on-failure
```

A failure is reported directly; the workflow performs no automatic retry.

- [ ] **Step 5: Enforce the final coverage thresholds**

Run:

```bash
scripts/core-coverage.sh check
```

Expected: PASS after the deterministic, persistence-fault, and C ABI Tasks. If a threshold still fails, stop without lowering it or adding line-execution-only assertions. Return the exact failing path and uncovered branch report so the plan can be amended with named behavior scenarios before implementation continues.

- [ ] **Step 6: Run the final local acceptance matrix**

Run:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev full
scripts/core.sh test dev stress
scripts/core.sh configure release
scripts/core.sh build release
scripts/core.sh test release full
scripts/core.sh configure asan
scripts/core.sh build asan
scripts/core.sh test asan full
scripts/core-coverage.sh check
git diff --check
```

On a Linux worker also run:

```bash
scripts/core.sh configure tsan
scripts/core.sh build tsan
scripts/core.sh test tsan stress
```

Expected: every functional suite and threshold passes with zero sanitizer report.

- [ ] **Step 7: Keep Product Proof acceptance separate**

Update the policy to state that coverage and sanitizer gates do not replace the existing `scripts/core.sh proof` evidence for Product Assembly, CLI/MCP Product-provider wiring, Golden WAV, Provider isolation, and Take recovery. Neither automated gate proves browser realtime audio, physical MIDI/controller behavior, deployment, or release acceptance.

- [ ] **Step 8: Commit**

```bash
git add \
  .github/workflows/ci.yml \
  .github/workflows/core-nightly.yml \
  tests/build/core_script_test.py \
  CMakeLists.txt \
  scripts/core.sh \
  docs/quality/core-test-policy.md
git diff --cached --name-only
git diff --cached --check
git commit -m "ci(core): enforce test quality gates"
```

Before committing, verify the staged list contains exactly the six declared CI, runner, registration, shell, and policy files. Do not stage build output, version files, unrelated product code, or pre-existing changes.

---

## Completion Evidence

Implementation is complete only when all of the following are true:

```text
every registered CTest has exactly one tier
Dev and Release full suites pass
stress tier passes without retry
ASan/UBSan full suite passes
TSan C ABI stress passes on Linux
overall and per-module coverage thresholds pass
coverage artifacts remain under build/core
the existing Headless Core Product Proof still passes and is reported separately
tracked worktree contains only intentional commits
no Product, Module, Contract, Provider, or Model version changed
```

Expected long-term maintenance rule:

- Every implementation Task names its selected tier and risk label.
- Every public behavior or defect adds only the scenarios required by the Test Selection Rule.
- Coverage thresholds may increase after sustained success but never decrease merely to make a PR green.
- Test counts remain an observation for planning; they are never a release gate.
