# Attempt Reservation Release And Provider-Sdk Cascade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix provider-sdk defects G1 and G4 in `packages/provider-sdk/src/attempt_store.cpp`, update the pinned invariant wording, and pay the full Product Build cascade required by the provider-sdk PATCH.

**Architecture:** Keep the behavioral fixes narrow inside `attempt_store.cpp`: release the whole attempt reservation only on the two non-terminal G1 failure paths, and add a process-unique temp-name nonce for G4 without changing public contracts. Then propagate the exact manifest, assembly, runtime-identity, test-table, and Portal current-truth identities required by the version policy for a provider-sdk PATCH and a new Product Build.

**Tech Stack:** C++17 core modules, JSON manifests, Python verification scripts, CMake, Node/Vitest Portal and web-host checks.

## Global Constraints

- Stay on `fix/attempt-reservation-release`; never commit on `main`.
- Scope is G1 + G4 only unless a current committed decision has already unblocked G2; at plan time no such decision is present.
- `provider-sdk` changes from `1.1.1` to `1.1.2`; every dependent manifest version and dependency edge must match exactly.
- Product Assembly identity changes require a new Product Build: `1.0.23.0` to `1.0.24.0`.
- `products/lmdj/src/compiled_assembly.cpp` must be byte-final before regenerating `assembly.lock.json`.
- `products/lmdj/assembly.lock.json` must be generated only via `python3 scripts/version.py lock ...`; never hand-edit it.
- `Documentation impact: required` is mandatory because Product Assembly files change; current Portal pages must be updated, and historical proof text for older Builds must not be rewritten.
- The fixed G1 publish-failed/persist-failed paths are not automatically testable without fault injection; if no seam is added, the plan and final report must say that plainly.

## File Structure

- Modify `packages/provider-sdk/src/attempt_store.cpp` for the two defect fixes only.
- Modify `tests/core/provider/attempt_ledger_invariant_test.cpp` to reframe the orphan-reservation case around current truth instead of the old “burned id” defect statement.
- Modify module/provider/host manifests and identity literals so every dependency edge and baked version string matches the new provider-sdk closure.
- Modify `products/lmdj/{version.json,assembly.json,src/compiled_assembly.cpp,CMakeLists.txt}` and regenerate `products/lmdj/{assembly.lock.json,generated/web-runtime-identity.json,generated/web-runtime-identity.mjs}`.
- Modify current Portal prose in `apps/architecture-portal/docs/product/capability-map.mdx`, `apps/architecture-portal/docs/operations/testing-and-proof.mdx`, and `apps/architecture-portal/docs/assembly/lmdj.mdx` with additive current-build wording.
- Modify gate tables and version-literal tests that pin the old versions/build.

### Task 1: Confirm Scope And Record The Task Contract

**Files:**
- Create: `docs/superpowers/plans/2026-08-20-attempt-reservation-release-and-provider-sdk-cascade.md`
- Read/verify only: `docs/quality/2026-08-17-machine-task-todo.md`
- Read/verify only: `docs/superpowers/plans/2026-08-19-lmdj-runtime-invariant-harness.md`

**Interfaces:**
- Consumes: G1/G4 definitions and version-policy requirements from the authority docs.
- Produces: A committed task scope that excludes G2 unless a committed decision says otherwise.

- [ ] Verify that no current decision document has already unblocked G2.
- [ ] Record in this plan that G1 and G4 are in scope and G2 remains out of scope.
- [ ] Record the exact version cascade and Product Build bump to apply if the current manifests still match the expected closure.

### Task 2: Reproduce And Fix The Two Provider-Sdk Defects

**Files:**
- Modify: `packages/provider-sdk/src/attempt_store.cpp`

**Interfaces:**
- Consumes: Existing `remove_tree`, `cleanup_attempt_outputs`, `temporary_sibling`, and `AttemptStore::execute`.
- Produces: G1 fix on the two no-terminal-record failure returns, plus G4 temp-name uniqueness improvement with no public API change.

- [ ] Inspect the publish-failed and persist-failed returns in `AttemptStore::execute` and confirm they currently call `cleanup_attempt_outputs(attempt_root)` before returning the original error.
- [ ] Change only those two returns to call `remove_tree(attempt_root, "Attempt reservation cleanup failed")` and return the original `published.error()` / `persisted.error()` when cleanup succeeds.
- [ ] Leave the surrounding “cleanup itself failed” returns unchanged so real filesystem failures still surface honestly.
- [ ] Add a static per-process nonce seeded from `std::random_device` and include it in `temporary_sibling(...)` so names are unique across processes without using `getpid()`.

### Task 3: Update The Pinned Invariant Test To Match The Fixed Truth

**Files:**
- Modify: `tests/core/provider/attempt_ledger_invariant_test.cpp`

**Interfaces:**
- Consumes: Existing ledger harness relation that reports orphan reservation directories.
- Produces: A renamed/reworded test that still proves a manually created orphan reservation blocks the id, while no longer presenting “burns its id” as accepted product behavior.

- [ ] Locate the current orphan-reservation test that intentionally asserts the broken framing.
- [ ] Rewrite the test name and assertion comments to state the new truth: a manually created orphan directory still means “someone holds the reservation”, so the duplicate-id result remains correct for that manual corruption case.
- [ ] Keep the harness relation that flags the orphan reservation as a violation.
- [ ] Do not claim automated coverage for the fixed G1 publish/persist failure path unless a real fault-injection seam is added and exercised.

### Task 4: Apply The Required Version Cascade And Product Identity Updates

**Files:**
- Modify: `packages/provider-sdk/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/core-mcp/pyproject.toml`
- Modify: `apps/core-mcp/lmdj_core_mcp/__init__.py`
- Modify: `apps/native-test-host/module.json`
- Modify: `apps/native-test-host/src/main.cpp`
- Modify: `packages/web-runtime-platform/module.json`
- Modify: `apps/web-runtime-host/module.json`
- Modify: `apps/creator-web/module.json`
- Modify: `apps/creator-web/package.json`
- Modify: `apps/creator-web/package-lock.json`
- Modify: `providers/local-proof-success/module.json`
- Modify: `providers/local-proof-success/src/provider.cpp`
- Modify: `providers/local-proof-success/CMakeLists.txt`
- Modify: `providers/local-proof-failure/module.json`
- Modify: `providers/local-proof-failure/src/provider.cpp`
- Modify: `providers/local-proof-failure/CMakeLists.txt`
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Modify: `products/lmdj/CMakeLists.txt`

**Interfaces:**
- Consumes: Current manifest versions and dependency edges.
- Produces: Exact new versions and dependency maps for the closure, plus Product Build `1.0.24.0`.

- [ ] Verify the current tree still matches the expected starting versions.
- [ ] Bump `provider-sdk` to `1.1.2`.
- [ ] Bump every dependent manifest and dependency edge in the required closure: `application-facade`, `core-cli`, `core-mcp`, `native-test-host`, `web-runtime-platform`, `web-runtime-host`, `creator-web`, `local.proof.success`, and `local.proof.failure`.
- [ ] Update all non-manifest identity literals that must match those manifests.
- [ ] Edit `products/lmdj/version.json` by hand to allocate Product Build `1.0.24.0`.
- [ ] Make `products/lmdj/src/compiled_assembly.cpp` byte-final before regenerating the lock.
- [ ] Update `products/lmdj/assembly.json` and `products/lmdj/CMakeLists.txt` to the same identities.

### Task 5: Regenerate Derived Product Identity And Update Current Portal Truth

**Files:**
- Modify: `products/lmdj/assembly.lock.json`
- Modify: `products/lmdj/generated/web-runtime-identity.json`
- Modify: `products/lmdj/generated/web-runtime-identity.mjs`
- Modify: `apps/architecture-portal/docs/product/capability-map.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/assembly/lmdj.mdx`

**Interfaces:**
- Consumes: Final assembly/product source files from Task 4.
- Produces: Matching generated identities and current Portal prose for Build `1.0.24.0`.

- [ ] Run `python3 scripts/version.py lock --version-file products/lmdj/version.json --assembly products/lmdj/assembly.json --output products/lmdj/assembly.lock.json`.
- [ ] Run `python3 tools/web-runtime/generate_runtime_identity.py`.
- [ ] Update current Portal pages with additive prose for Build `1.0.24.0`, preserving historical statements about older Builds.
- [ ] Mention the provider-sdk/application-facade/web-runtime/host identities that changed, and note that G1’s fixed failure path remains untestable without fault injection if that remains true at implementation time.

### Task 6: Update Version-Pinned Gates And Run The Full Verification Suite

**Files:**
- Modify: all tests and gate tables that pin the old versions/build discovered by targeted grep, including at minimum:
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/version_lock_test.py`
- Modify: `tests/conformance/module_graph_test.py`
- Modify: `tests/core/facade/application_test.cpp`
- Modify: `tests/core/facade/assembly_loader_test.cpp`
- Modify: `tests/core/provider/conformance_test.cpp`
- Modify: `tests/core/provider/spec_regression_test.cpp`
- Modify: `tests/host/mcp_stdio_test.py`
- Modify: `tests/host/native_host_test.py`
- Modify: `tests/host/native_host_source_boundary_test.py`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `apps/creator-web/test/...`
- Modify: `apps/web-runtime-host/test/...`
- Modify: `tests/platform/web/...`
- Modify: `apps/architecture-portal/test/repo-facts.test.mjs`

**Interfaces:**
- Consumes: New versions and build identities from Tasks 4 and 5.
- Produces: A tree whose conformance and proof gates match the new identities.

- [ ] Grep for the old version/build literals and update every assertion that intentionally pins them.
- [ ] Run `scripts/core.sh test dev full`.
- [ ] Run `scripts/core.sh test dev stress`.
- [ ] Run `python3 tests/build/version_test.py`.
- [ ] Run `python3 tests/conformance/version_lock_test.py`.
- [ ] Run `python3 tests/conformance/module_graph_test.py`.
- [ ] Run `python3 scripts/version.py verify --version-file products/lmdj/version.json --assembly products/lmdj/assembly.json --lock products/lmdj/assembly.lock.json`.
- [ ] Run `python3 tools/web-runtime/generate_runtime_identity.py --check`.
- [ ] Run `scripts/core.sh proof` and confirm it reports `Assembly lock: MATCH`.
- [ ] Run `scripts/architecture-portal.sh check`.
- [ ] Run `python3 scripts/ci/local_preflight.py`.

## Version Management

- `packages/provider-sdk`: `1.1.1` -> `1.1.2` (PATCH; defect fix, no new public capability declared).
- `packages/application-facade`: `1.4.0` -> `1.4.1` (dependency map changed to `provider-sdk 1.1.2`).
- `apps/core-cli`: `1.0.12` -> `1.0.13`.
- `apps/core-mcp`: `1.1.9` -> `1.1.10`.
- `apps/native-test-host`: `1.0.10` -> `1.0.11`.
- `packages/web-runtime-platform`: `0.3.0` -> `0.3.1`.
- `apps/web-runtime-host`: `1.2.9` -> `1.2.10`.
- `apps/creator-web`: `1.3.0` -> `1.3.1`.
- `providers/local-proof-success`: `1.0.2` -> `1.0.3`.
- `providers/local-proof-failure`: `1.0.2` -> `1.0.3`.
- Product Build: `1.0.23.0` -> `1.0.24.0` because Assembly identity changes.
- Contract versions: none.
- Public capability/ABI additions: none planned.

## Documentation Impact

Documentation impact: required
Affected portal pages: /product/capability-map, /operations/testing-and-proof, /assembly/lmdj
Reason: the task changes Product Build identity, Assembly component identities, and current proof/current-capability prose that the Portal states literally.
