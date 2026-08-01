# LMDJ Core Distribution Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a platform-specific Core ZIP whose CLI and MCP Hosts run from a fresh extraction without the repository, build tree, or caller-supplied `PYTHONPATH`.

**Architecture:** A Python standard-library packager stages the Release CLI binary, C ABI shared library, MCP Python package, Product Assembly, version lock, and two relocation-safe launchers. A black-box acceptance test extracts the ZIP outside the repository, poisons source-tree discovery, and proves CLI/MCP parity through the bundled Assembly.

**Tech Stack:** CMake 3.24+, C++20, Python 3.11+ standard library, POSIX shell, ZIP, CTest.

## Global Constraints

- Work only on `feat/core-distribution-package` in its isolated worktree.
- Do not ship a source checkout, CMake metadata, static libraries, tests, or Proof scratch data.
- The caller does not set `PYTHONPATH`; the MCP launcher resolves bundled files relative to itself.
- The CLI launcher uses the bundled Assembly unless the caller supplies `--assembly`.
- The Build Manifest binds Product Build, full Git SHA, Assembly lock hash, and every shipped file.
- Archive paths are normalized non-symlink files below one root directory.
- macOS ships `liblmdj_core_c.dylib`; Linux ships `liblmdj_core_c.so`.
- Acceptance runs on macOS and Ubuntu through `scripts/core.sh proof`.
- No new runtime dependency; MCP continues to require system Python 3.11+.
- Capability, Project Truth, Provider, Facade, and C ABI semantics do not change.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

| Domain | Current | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.8.0` | `1.0.9.0` | Adds the first distributable Core package and clean-extraction gate. |
| Core Modules | unchanged | unchanged | No Module API or ownership change. |
| Hosts | `core-cli` `1.0.0`, `core-mcp` `1.0.0` | unchanged | Host protocols are unchanged; packaging is Product-level. |
| Contracts | unchanged | unchanged | No wire or persistence Contract change. |
| Providers / Models | unchanged | unchanged | Provider code and identities are unchanged. |

- Update Product version, Assembly, compiled identity, README, Proof output, version tests, and Assembly lock.
- Candidate builds display `1.0.9.0 · canary · g<short-sha>`.
- Future Product tag: `lmdj-v1.0.9.0`, only on squash-merged `main` after macOS, Ubuntu, ASan, Coverage, Proof, and package acceptance pass.
- This plan authorizes implementation, commit, branch push, and PR creation under the active user goal. Tag creation, tag push, Release, deployment, and Channel promotion remain separate post-merge gates.
- Rollback uses immutable Product Build `1.0.8.0`.

---

### Task 1: Add the failing clean-extraction acceptance test

**Files:**

- Create: `tests/distribution/package_acceptance_test.py`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: build root containing `bin/lmdj-core` and the C ABI shared library.
- Produces: `package.acceptance` CTest and direct `--build-root` test entrypoint.

- [x] **Step 1: Write the acceptance test before the packager exists**

The test invokes:

```python
completed = subprocess.run(
    [
        sys.executable,
        str(REPO_ROOT / "scripts/package-core.py"),
        "--build-root",
        str(build_root),
        "--output-dir",
        str(output_dir),
    ],
    cwd=REPO_ROOT,
    env={**os.environ, "PYTHONPATH": "/nonexistent/lmdj-poison"},
    check=False,
    capture_output=True,
    text=True,
)
assert completed.returncode == 0, (completed.stdout, completed.stderr)
archive = Path(completed.stdout.strip()).resolve(strict=True)
```

Extract with platform `unzip` into a temporary directory outside the repository. Require this exact inventory:

```text
README.md
bin/lmdj-core
bin/lmdj-core-mcp
build-manifest.json
share/lmdj/contracts/assembly/lmdj.assembly.v2.schema.json
lib/liblmdj_core_c.dylib | lib/liblmdj_core_c.so
libexec/lmdj-core
python/lmdj_core_mcp/__init__.py
python/lmdj_core_mcp/__main__.py
python/lmdj_core_mcp/c_api.py
python/lmdj_core_mcp/server.py
share/lmdj/assembly.json
share/lmdj/assembly.lock.json
share/lmdj/version.json
```

Run the extracted CLI from the extraction parent with `PYTHONPATH` removed and `PYTHONNOUSERSITE=1`; create a Project and query `provider.list`. Start the extracted MCP launcher with the same environment, initialize MCP `2025-11-25`, call `lmdj.provider.list`, and require the same structured result.

- [x] **Step 2: Register the test in CTest**

```cmake
lmdj_add_test(
  NAME package.acceptance
  TIER e2e
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/distribution/package_acceptance_test.py
    --build-root "${CMAKE_BINARY_DIR}"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS abi assembly generated
  TIMEOUT 180
)
```

- [x] **Step 3: Run RED**

Run:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
python3 tests/distribution/package_acceptance_test.py --build-root build/core/dev
```

Expected: non-zero exit because `scripts/package-core.py` is absent, before Host assertions.

### Task 2: Implement the relocation-safe Core ZIP

**Files:**

- Create: `scripts/package-core.py`
- Create: `packaging/core/README.md`
- Modify: `scripts/core.sh`

**Interfaces:**

- Consumes: `--build-root PATH` and `--output-dir PATH`.
- Produces: absolute `lmdj-core-<version>-<platform>-<architecture>.zip` path on stdout.

- [x] **Step 1: Implement strict discovery and staging**

Use:

```python
repo_root = Path(__file__).resolve().parents[1]
version = verify(
    repo_root / "products/lmdj/version.json",
    assembly_path=repo_root / "products/lmdj/assembly.json",
    lock_path=repo_root / "products/lmdj/assembly.lock.json",
)
```

Require regular non-symlink inputs for CLI, platform library, four MCP Python files, Assembly, Assembly Schema, lock, version, and README. Reject unsupported systems/architectures with exit `2` and `package error:`. Stage under `tempfile.TemporaryDirectory` below the output directory; copy only Task 1's inventory.

- [x] **Step 2: Generate relocation-safe launchers**

`bin/lmdj-core` is a POSIX shell launcher resolving its physical package root. If any argument is `--assembly`, execute `libexec/lmdj-core` unchanged; otherwise inject the bundled Assembly before caller arguments.

`bin/lmdj-core-mcp` is Python 3 code resolving the root from `__file__`, prepending `root / "python"` to `sys.path`, and invoking:

```python
sys.argv = [
    "lmdj-core-mcp",
    "--library",
    str(library),
    "--assembly",
    str(root / "share/lmdj/assembly.json"),
    *sys.argv[1:],
]
runpy.run_module("lmdj_core_mcp", run_name="__main__")
```

Modes: launchers and real CLI `0755`; all other files `0644`.

- [x] **Step 3: Generate manifest and ZIP**

Use the existing version manifest implementation against the staged root. Require current Product version, staged Assembly lock digest, and full Git SHA. Create the ZIP in lexicographic order below one root; preserve file modes through `ZipInfo.external_attr`; write a temporary archive then atomically replace the exact final path.

- [x] **Step 4: Add stable commands**

Add `scripts/core.sh package`. It configures/builds Release and runs:

```bash
python3 scripts/package-core.py \
  --build-root "$build_root/release" \
  --output-dir "$build_root/dist"
```

Extend `scripts/core.sh proof` to run clean-package acceptance against Release before its Proof Build Manifest.

- [x] **Step 5: Run GREEN**

```bash
python3 tests/distribution/package_acceptance_test.py --build-root build/core/dev
ctest --test-dir build/core/dev --output-on-failure -R '^package\.acceptance$'
```

Expected: both print `core distribution package acceptance: PASS` and exit `0`.

### Task 3: Allocate Product Build 1.0.9.0 and prove integration

**Files:**

- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Modify: `products/lmdj/README.md`
- Modify: `scripts/core.sh`
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/version_lock_test.py`
- Regenerate: `products/lmdj/assembly.lock.json`

**Interfaces:**

- Consumes: package behavior from Tasks 1–2.
- Produces: consistent Product Build `1.0.9.0` and full Proof evidence.

- [x] **Step 1: Change exact version assertions first**

```python
assert version == ProductVersion(1, 0, 9, 0)
assert str(version) == "1.0.9.0"
assert version.product_tag() == "lmdj-v1.0.9.0"
```

Change Product Assembly source identity expectations to `1.0.9.0`.

- [x] **Step 2: Run RED**

Run `python3 tests/build/version_test.py`.

Expected: failure because Product still identifies `1.0.8.0`.

- [x] **Step 3: Update identity and regenerate lock**

Set Build `9` and `1.0.9.0` in version, Assembly, compiled Assembly, Product README, and Proof output. Run:

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
```

- [x] **Step 4: Run complete acceptance**

```bash
scripts/core.sh proof
scripts/core.sh package
unzip -l build/core/dist/lmdj-core-1.0.9.0-*.zip
git diff --check
```

Expected: 23 Release tests pass; Schema, graph, CLI, MCP, parity, Headless E2E, package acceptance, Product `1.0.9.0`, and lock pass.

- [x] **Step 5: Commit**

Stage only files declared by Tasks 1–3 plus this plan, verify staged paths and `git diff --cached --check`, then commit:

```bash
git commit -m "feat(core): package standalone CLI and MCP hosts"
```

### Task 4: Push, review, and integrate

**Files:** none

**Interfaces:**

- Consumes: clean feature commit.
- Produces: PR to `main`, four green Core CI jobs, and squash-merged Build.

- [ ] **Step 1: Push and create a ready PR**

Push `feat/core-distribution-package`; create PR `feat(core): package standalone CLI and MCP hosts` with local Proof/package evidence.

- [ ] **Step 2: Require remote gates**

Require green `core (macos-latest)`, `core (ubuntu-latest)`, `core-asan`, and `core-coverage`. Fix failures on the same branch.

- [ ] **Step 3: Squash merge and verify main**

After green checks, squash merge; pull exact remote `main`; run `scripts/core.sh proof`; verify the ZIP manifest references the full merge SHA.

- [ ] **Step 4: Evaluate tag gate**

Only then may the Integration Owner create annotated `lmdj-v1.0.9.0`. Tag push and GitHub Release remain separately reported states.

## Final Review Checklist

- [x] Fresh extraction runs outside repository and build tree.
- [x] Caller has no usable `PYTHONPATH` or source checkout.
- [x] CLI and MCP use the bundled Assembly and return identical Provider inventory.
- [ ] Shared library loads on macOS and Ubuntu.
- [x] Inventory is exact, normalized, single-rooted, and symlink-free.
- [x] Executable modes survive `unzip`.
- [x] Build Manifest covers every shipped file and matches Product/Assembly identity.
- [x] All Product identity sources say `1.0.9.0`.
- [ ] Local Proof, package acceptance, four CI jobs, and squash merge pass before tag consideration.
