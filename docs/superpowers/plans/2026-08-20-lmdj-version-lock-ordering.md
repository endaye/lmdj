# LMDJ Version Lock Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `scripts/version.py lock` deterministically regenerate `products/lmdj/src/compiled_assembly.cpp` and `assembly.lock.json` as one authoritative transaction so a post-lock source edit cannot leave a stale lock.

**Architecture:** Choose automatic paired generation because a lock-time validator cannot prevent the original `lock -> later source edit` ordering defect. `scripts/version.py lock` will treat `version.json`, `assembly.json`, the Assembly Contract schema, and each Provider's unique `factory.hpp` declaration as authority; it will deterministically render the complete compiled catalog, calculate the lock from those exact in-memory C++ bytes, and only then replace both outputs. Provider factory ambiguity or invalid model identity fails before either destination changes, while rerunning the command repairs any post-lock source edit. The generator remains in `scripts/version.py`, so no new production file or identity is introduced.

**Tech Stack:** Python 3 standard library, subprocess-based conformance tests, canonical JSON lock generation.

## Global Constraints

- Work only on `fix/version-lock-order`; never modify or commit on `main`.
- Keep this Issue to one atomic Conventional Commit and stage only the declared files.
- Use a real copied `scripts/version.py lock` command for the regression, not a string-only assertion or a mocked helper.
- Do not modify Product, Module, Host, Provider, Contract, Channel, Assembly, Portal snapshot, or revision identities.
- Do not allocate a Product Build.
- Do not push, open a Pull Request, merge, close Issue #208, tag, release, deploy, publish, or promote a Channel.

## File Structure

- Create `docs/superpowers/plans/2026-08-20-lmdj-version-lock-ordering.md` to record the selected paired-generation design, scope, TDD cycle, and acceptance gates.
- Modify `tests/conformance/version_lock_test.py` to construct a minimal isolated repository and exercise lock, post-lock source tampering, Provider model wiring, factory ambiguity, and repeat generation through the real CLI.
- Modify `scripts/version.py` to resolve unique Provider factory declarations, render compiled Product Assembly identity/inventories/model identity, calculate its source-package hash from the rendered bytes, and replace the source/lock pair only after all validation succeeds.
- Leave `tests/build/version_test.py` unchanged unless the conformance test reveals an existing build-version contract that also needs direct coverage.

## Version Management

Version impact: none. This Task hardens the existing lock-generation tool and its tests without changing runtime code, Product Assembly contents, any Product Build, Module or Provider SemVer, or Contract identity.

## Documentation Impact

Documentation impact: none. The implementation changes an internal build-tool generation transaction and adds its required implementation plan; it does not alter architecture, manifests, Product Assembly truth, or any Architecture Portal route, and both existing generated artifacts remain byte-identical for valid input.

---

### Task 1: Generate Compiled Assembly And Lock As One Authority Boundary

**Files:**
- Create: `docs/superpowers/plans/2026-08-20-lmdj-version-lock-ordering.md`
- Modify: `tests/conformance/version_lock_test.py`
- Modify: `scripts/version.py`

**Interfaces:**
- Consumes: `generate_lock(version_file, assembly_path, output_path)`, validated `version.json`/`assembly.json`, the Assembly Contract schema, and each Provider's unique `factory.hpp` registration declaration.
- Produces: deterministic compiled-source bytes derived from current authority, a lock calculated from those exact bytes, and a paired writer that leaves both prior destinations unchanged when validation fails.

- [ ] **Step 1: Add real-command paired-generation regressions**

  Copy `scripts/version.py` and the exact Product/component sources needed by the current assembly into a temporary repository and run:

  ```bash
  python3 <isolated-repository>/scripts/version.py lock \
    --version-file <isolated-repository>/products/lmdj/version.json \
    --assembly <isolated-repository>/products/lmdj/assembly.json \
    --output <isolated-repository>/products/lmdj/assembly.lock.json
  ```

  Assert the first run produces compiled source byte-identical to the tracked source and a lock byte-identical to the tracked lock. Then swap the two Provider factory symbols in the generated C++, rerun the same real command, and assert the authoritative bytes and matching lock are restored rather than silently locking the tampered source. Add a non-null `model_identity` to an isolated valid assembly and assert its exact three fields are rendered and remain idempotent. Make one `factory.hpp` declare two symbols, move its sole declaration outside the target block, nest it in `namespace detail`, and wrap the target namespace in `namespace outer`; every real CLI call must exit `2`, diagnose the exact factory scope/assembly-lock ordering, and leave both destinations unchanged. Finally inject an `OSError` into the second destination replacement and assert the exception propagates, both old destination byte sequences are restored, and no temporary files remain.

- [ ] **Step 2: Run the regression to verify RED**

  Run: `python3 tests/conformance/version_lock_test.py`

  Expected: FAIL because the old command returns `0` after a post-lock factory swap and hashes the tampered source instead of restoring authoritative compiled bytes; it also does not render model identity and does not reject an ambiguous factory declaration.

- [ ] **Step 3: Implement deterministic paired generation**

  In `scripts/version.py`, resolve exactly one real `factory.hpp` per Provider and use a comment/literal-aware brace-depth scan to require exactly one global-depth `namespace lmdj::providers { ... }` block containing exactly one direct-depth `provider::ProviderRegistration symbol();`; reject every same-shape declaration outside that exact depth, plus missing, duplicate, symlinked, or ambiguous declarations, before writing. Deterministically render sorted Provider includes, Product ID/Build, Assembly Contract schema SHA-256, ordered Module/Host/Contract inventories, Provider IDs/versions, fully qualified factory symbols, and complete `model_identity` values (`std::nullopt` when absent).

  Extend source-package hashing so `_lock_document(...)` can consume the exact rendered compiled bytes without first mutating the checkout. Fully construct and validate both byte payloads in memory, write both temporary files, then replace the destinations with rollback on a replacement error. The error must name compiled assembly, Provider factory declarations, and assembly-lock ordering; no validation error may leave one new destination beside one old destination.

- [ ] **Step 4: Run targeted GREEN and full acceptance**

  Run:

  ```bash
  python3 tests/conformance/version_lock_test.py
  python3 tests/build/version_test.py
  python3 scripts/version.py verify --version-file products/lmdj/version.json
  scripts/architecture-portal.sh check
  ```

  Expected: every command exits `0`; the conformance and build tests print their PASS markers, version verification reports Product Build `1.0.24.0`, and the Portal check succeeds without changing tracked files.

- [ ] **Step 5: Review and create the atomic commit**

  Confirm the branch is not `main`, stage only this plan plus `scripts/version.py` and `tests/conformance/version_lock_test.py`, list the staged files, run `git diff --cached --check`, inspect the complete staged diff, and commit:

  ```bash
  git commit -m "fix(build): enforce assembly lock ordering"
  ```

  Then inspect the committed file list and final worktree status; do not perform any remote or release mutation.
