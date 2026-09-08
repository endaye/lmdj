# Native Host Rename and Distribution Contents Rule Implementation Plan

**Goal:** Resolve Issue #210 (machine task A2). `native-test-host` is a formal,
versioned, Assembly-listed headless Native Host whose module id still says
"test". Take the rename option: make the module identity match what the
component already is, and write the missing rule for what may enter a
distribution package.

**Decision (A2):** Rename, not removal. Evidence:

- `docs/design/2026-08-02-lmdj-formal-native-realtime-host-design.md`
  created it as the formal Native Realtime Host: "首个正式、版本化、
  Assembly-listed Headless Native Host" with shipped binary
  `lmdj-native-host`.
- `scripts/package-core.py` deliberately stages `bin/lmdj-native-host`, and
  `tests/distribution/package_acceptance_test.py` asserts it is present and
  runnable in every distribution package.
- Removing it would delete a tested, shipped product capability; keeping the
  stale name leaves Assembly identity contradicting `CLAUDE.md`'s `apps/`
  definition.

**Architecture:** The rename is identity-only. CMake target
(`lmdj_native_host`), shipped binary name (`lmdj-native-host`), CLI protocol,
test scripts (`tests/host/native_host_*.py`), and test names do not change.
What changes: module id, source directory, Assembly host entry, and every
current-truth document that names the component. Historical records (frozen
portal snapshots, published release intents, past-build prose) are immutable
and keep the old name.

**Tech Stack:** C++20/CMake, Python repo tooling, Docusaurus portal, Markdown

## Global Constraints

- Retired module id `native-test-host` ends at `1.0.14` and is never reused.
- New module id `native-host` starts its own SemVer line at `1.0.0`; the
  binary protocol is unchanged, so `api_version` stays `1`.
- Assembly identity change allocates a new Product Build: `1.0.30.0` →
  `1.0.31.0` (version policy §2.4: Assembly changes never ride a PATCH).
- `assembly.lock.json` and `products/lmdj/src/compiled_assembly.cpp` are
  regenerated only with `python3 scripts/version.py lock`, never hand-edited.
- Frozen portal snapshots (`versioned_*`), `docs/release-evidence/`, and
  historical build prose keep the retired name; only current-truth pages move.
- One reviewable Conventional Commit for the source change; the immutable
  portal snapshot is generated after that commit and committed separately, and
  the squash merge keeps the Task one commit on `main`.

---

### Task 1: Distribution contents rule

**Files:**
- Create: `docs/governance/distribution-contents.md`
- Modify: `packaging/core/README.md` (the README currently omits the shipped
  Native Host; describe the actual contents and cite the rule)

**Rule summary:** a file may enter a distribution package only if it is the
build output or manifest of a component locked in the active Product Assembly,
or packaging metadata required to verify the package itself. Test-only tools
live under `tests/` and never ship. `scripts/package-core.py` is the single
mechanical inventory; adding anything to it requires Assembly membership and
updating the rule in the same Task.

### Task 2: Rename the Host module

**Files:**
- Rename: `apps/native-test-host/` → `apps/native-host/`
- Modify: `apps/native-host/module.json` (`module: native-host`,
  `version: 1.0.0`)
- Modify: `apps/native-host/src/main.cpp` (`kHostVersion "1.0.0"`, `#error`
  text no longer says "Native Test Host")
- Modify: `CMakeLists.txt` (`add_subdirectory(apps/native-host)`)
- Modify: `scripts/ci/scope_policy.json` (path prefix)
- Modify: `tests/build/version_test.py` (module manifest entry and paths)
- Modify: `tests/host/native_host_test.py` (`host_version == "1.0.0"`)

### Task 3: Allocate Product Build 1.0.31.0

**Files:**
- Modify: `products/lmdj/version.json` (build 31)
- Modify: `products/lmdj/assembly.json` (product version, host entry
  `native-host 1.0.0`)
- Regenerate: `products/lmdj/assembly.lock.json`,
  `products/lmdj/src/compiled_assembly.cpp` via `scripts/version.py lock`
- Regenerate: `products/lmdj/generated/web-runtime-identity.*` via
  `tools/web-runtime/generate_runtime_identity.py`
- Modify: `products/lmdj/CMakeLists.txt`, `products/lmdj/README.md`,
  `tests/conformance/module_graph_test.py` (Product Build literals)

### Task 4: Portal current pages and tests

**Files:**
- Rename: `apps/architecture-portal/docs/hosts/native-test-host.mdx` →
  `native-host.mdx`; rewrite as a product Host page (drop the "测试装配"
  framing; the formal Native Realtime Host design is the authority)
- Modify: `apps/architecture-portal/sidebars.ts`,
  `apps/architecture-portal/scripts/check-build.mjs`,
  `apps/architecture-portal/test/repo-facts.test.mjs`,
  `apps/architecture-portal/test/content-inventory.test.mjs`
- Modify current-build prose in `docs/hosts/overview.mdx`,
  `docs/assembly/lmdj.mdx`, `docs/product/capability-map.mdx`,
  `docs/operations/version-and-release.mdx`,
  `docs/operations/testing-and-proof.mdx`, `docs/overview/index.mdx`,
  `docs/platform/native-audio.mdx`, `docs/platform/input.mdx`,
  `docs/platform/web-runtime.mdx`, `docs/hosts/creator-web.mdx`,
  `docs/hosts/web-runtime.mdx`,
  `docs/core/modules/application-facade.mdx`,
  `docs/core/modules/audio-runtime.mdx`
- Historical build records inside those pages (1.0.22.0/1.0.24.0/1.0.25.0
  paragraphs) keep the retired name.

### Task 5: Architecture documentation and diagram source

**Files:**
- Modify: `docs/architecture/current-product-architecture.md` (the host is no
  longer described as 验收专用/Acceptance-only)
- Modify: `docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json`
  and the generated `…​.html` (node id, paths, labels)

### Task 6: Decision record and status reconciliation

**Files:**
- Create: `docs/prd/decisions/2026-08-24-native-test-host-classification.md`
- Delete: `docs/prd/questions/native-test-host-classification.md` (per
  `docs/prd/decisions/README.md`, the decision file names the question it
  resolves)
- Modify: `docs/quality/2026-08-17-machine-task-todo.md` (A2 done),
  `docs/quality/2026-08-16-outstanding-work-before-stage9.md` (A2 resolved)

### Task 7: Verification, commit, snapshot

```bash
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
bash scripts/verify-core-dependencies.sh
scripts/core.sh configure dev && scripts/core.sh build dev
scripts/core.sh test dev full
scripts/architecture-portal.sh check
```

Then commit the source change, generate the immutable snapshot with
`scripts/architecture-portal.sh version 1.0.31.0 canary` from the clean tree,
and commit the snapshot. Push, PR, merge, and Issue closure remain separate
authorized steps.

## Version Management

1. Version domains affected: Product, Module (Host), Assembly Lock.
2. From → to: Product Build `1.0.30.0` → `1.0.31.0`; Host module
   `native-test-host 1.0.14` → retired; new Host module `native-host 1.0.0`.
3. Bump reason: Assembly identity change (host id and version) — new BUILD per
   version policy §2.4; module rename is breaking, so the old id is retired
   and the new id starts a fresh SemVer line at `1.0.0` rather than implying
   an API break with `2.0.0` (the binary protocol is unchanged).
4. This PR: Product Build `1.0.31.0`, Channel `canary`.
5. Files changed: `products/lmdj/version.json`, `products/lmdj/assembly.json`,
   regenerated `assembly.lock.json` + `compiled_assembly.cpp`,
   `apps/native-host/module.json`.
6. Contract/Project compatibility: none — no Contract changes; existing
   Project bundles are unaffected.
7. Tags: none created by this Task. `module/native-test-host/*` tags stay
   published history; any future `module/native-host/v1.0.0` or
   `lmdj-v1.0.31.0` tag requires the normal merged-main Proof and separate
   authorization.
8. Tag preconditions: not applicable this Task.
9. This Task does not authorize push, Release, deployment, or Channel
   promotion.
10. Rollback: Product Build `1.0.30.0` and its frozen snapshot remain the
    immutable prior state.

## Documentation Impact

Documentation impact: required

Affected portal routes: `/hosts/native-host/` (renamed from
`/hosts/native-test-host/`), `/hosts/overview/`, `/assembly/lmdj/`,
`/product/capability-map/`, `/operations/version-and-release/`,
`/operations/testing-and-proof/`, `/overview/`, `/platform/native-audio/`,
`/platform/input/`, `/platform/web-runtime/`, `/hosts/creator-web/`,
`/hosts/web-runtime/`, `/core/modules/application-facade/`,
`/core/modules/audio-runtime/`

Reason: Host module identity, Product Assembly membership, and Product Build
change; current pages, diagram source, and a frozen `1.0.31.0` snapshot are
updated in the same Task.
