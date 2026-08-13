# LMDJ Stage 7 Keyboard Spatial Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the Creator Web default physical-keyboard rows with the visual Pad order and show the derived key on every Pad.

**Architecture:** Keep `DEFAULT_KEYBOARD_MAPPING` in `web-runtime-platform` as the single mapping truth. Creator Web derives a local Pad-to-key presentation map from that exported object, so triggering and labels cannot acquire independent hard-coded tables. Pointer, MIDI, Project Truth, Bundle, Runtime Snapshot, and audio lifecycle behavior remain unchanged.

**Tech Stack:** JavaScript ESM, TypeScript, React, Vitest/Testing Library, Playwright, Python identity tooling, Docusaurus Architecture Portal.

## Global Constraints

- Work only in `/Users/endaye/Projects/lmdj/.worktrees/stage7-review-remediation` on `fix/stage7-review-remediation`; never modify `main`.
- Use `KeyboardEvent.code`: `Q W E R T Y U I -> local Pads 1..8` and `A S D F G H J K -> local Pads 9..16` in every selected Bank.
- The visible `kbd` hint and accessible name derive from `DEFAULT_KEYBOARD_MAPPING`; Creator must not contain a second literal mapping table.
- Do not change Pointer, Touch, MIDI, stable Slot identity, Project Truth, Bundle, Runtime Snapshot, Provider, persistence, or audio lifecycle semantics.
- Version targets after the live baseline check are Product `1.0.20.0`, Platform `0.2.1`, Creator `1.1.2`, and diagnostic Host `1.2.8` through exact dependency propagation.
- Preserve immutable `1.0.19.0` snapshot and evidence; create a new `1.0.20.0 · canary` snapshot and unexecuted human sheet.
- Documentation impact: required for `/hosts/creator-web/`, `/platform/input/`, Product/Host/version/testing current routes, acceptance wording, snapshot, and release evidence.
- Local commits are authorized. Push, PR, merge, tag, Release, deployment, publication, and Channel promotion are not authorized.

---

### Task 1: Correct and expose the keyboard mapping

**Files:**

- Modify: `packages/web-runtime-platform/test/input_adapters.test.mjs`
- Modify: `apps/creator-web/test/input_controller.test.ts`
- Modify: `apps/creator-web/test/workspace_shell.test.tsx`
- Modify: `tests/platform/web/creator/creator_web_browser.spec.mjs`
- Modify: `packages/web-runtime-platform/web/input_adapters.mjs`
- Modify: `apps/creator-web/src/components/pad_surface.tsx`
- Modify: `apps/creator-web/src/styles.css`

**Interfaces:**

- Consumes: `DEFAULT_KEYBOARD_MAPPING: Readonly<Record<string, number>>` and the visible Pad's stable flat `slot`.
- Produces: corrected keyboard Trigger Slots and `<kbd>`/accessible key hints derived from the same mapping.

- [x] **Step 1: Write RED behavior assertions**

  Change the Platform literal expectation to `KeyQ..KeyI: 0..7` followed by `KeyA..KeyK: 8..15`. Change Creator controller expectations so `KeyQ` triggers Bank C Slot 32 and Bank D Slot 48, while representative `KeyI`, `KeyA`, and `KeyK` prove local Slots 7, 8, and 15. Change the workspace assertion to require sixteen accessible names of the form `Pad A1 — empty — Key Q` through `Pad A16 — empty — Key K`, with visible `kbd` values in exact Pad order. Add packaged Chromium key/address pairs and require each held key to move only its named Pad away from `data-outcome="idle"` before release.

- [x] **Step 2: Run RED tests and verify the intended failures**

  Run:

  ```bash
  node --test packages/web-runtime-platform/test/input_adapters.test.mjs
  npm --prefix apps/creator-web test -- --run \
    test/input_controller.test.ts test/workspace_shell.test.tsx
  ```

  Expected: mapping assertions fail because `KeyQ` still resolves to 8, controller Trigger Slots are inverted, and Pad names/`kbd` hints are absent.

- [x] **Step 3: Implement the minimal shared-map and UI correction**

  Reorder/revalue `DEFAULT_KEYBOARD_MAPPING`. In `pad_surface.tsx`, import it from `@lmdj/web-runtime-platform/input_adapters.mjs`, derive a module-local `Map<number, string>` with `Object.entries()` and `code.replace(/^Key/, "")`, use `pad.slot % 16` to obtain the current Bank's key, append ` — Key X` to `aria-label`, and render `<kbd aria-hidden="true">X</kbd>` as secondary metadata. Add only the CSS required to align and style that secondary metadata legibly in disabled and active states.

- [x] **Step 4: Run GREEN focused tests**

  Run:

  ```bash
  node --test packages/web-runtime-platform/test/input_adapters.test.mjs
  npm --prefix apps/creator-web test -- --run \
    test/input_controller.test.ts test/workspace_shell.test.tsx
  ```

  Expected: all focused tests pass.

### Task 2: Allocate and propagate the corrected candidate identity

**Files:**

- Modify: `products/lmdj/version.json`, `assembly.json`, `src/compiled_assembly.cpp`, `CMakeLists.txt`, and `README.md`
- Modify: `packages/web-runtime-platform/module.json`
- Modify: `apps/creator-web/module.json`, `package.json`, and `package-lock.json`
- Modify: `apps/web-runtime-host/module.json`
- Regenerate: `products/lmdj/assembly.lock.json`
- Regenerate: `products/lmdj/generated/web-runtime-identity.json` and `.mjs`
- Modify: exact identity assertions returned by `rg` under active `tests/`, `apps/*/test`, and `packages/*/test`
- Modify: `apps/architecture-portal/docs/assembly/lmdj.mdx`
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
- Modify: `apps/architecture-portal/test/repo-facts.test.mjs`
- Modify: `apps/architecture-portal/test/stage7-review-remediation.test.mjs`
- Modify: `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md`
- Modify: `docs/quality/2026-08-12-stage7-creator-editor-review.md`
- Modify: `docs/release-evidence/2026-08-13-stage7-remediation-canary.md`
- Modify: this implementation plan

**Interfaces:**

- Consumes: active component manifests and Product Assembly version policy.
- Produces: one self-consistent `1.0.20.0` Assembly with Platform `0.2.1`, Creator `1.1.2`, and Web Runtime Host `1.2.8`.

- [x] **Step 1: Write RED identity expectations**

  Update active version/module/Host/package/conformance expectations to the target identities before changing manifests or generated identity. Update the unversioned canary checklist so step 5 explicitly checks `Q..I -> A1..A8` and `A..K -> A9..A16`, and mark all human results unexecuted for the new candidate. Do not edit `docs/release-evidence/2026-08-13-stage7-remediation-canary-1.0.19.0.md` or `apps/architecture-portal/versioned_*` content.

- [x] **Step 2: Run RED identity gates**

  Run:

  ```bash
  python3 tests/build/version_test.py
  python3 tests/conformance/module_graph_test.py
  python3 tests/conformance/version_lock_test.py
  ```

  Expected: failures report stale `1.0.19.0`/`0.2.0`/`1.1.1`/`1.2.7` manifests and lock data.

- [x] **Step 3: Update manifests and regenerate derived identities**

  Set the four target identities in their authoritative manifests and exact dependency entries, then run:

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

- [x] **Step 4: Update current Portal and acceptance truth**

  Describe the corrected top-to-bottom mapping and visible key hints on current Creator/Input pages; update current Assembly/Host/version/testing identity statements. Record `1.0.19.0` as historical branch-local evidence superseded for this mapping acceptance, and keep merged-main/manual physical evidence pending for `1.0.20.0`.

- [x] **Step 5: Run GREEN behavior, identity, and current-doc gates**

  Run:

  ```bash
  node --test packages/web-runtime-platform/test/input_adapters.test.mjs
  npm --prefix apps/creator-web test -- --run
  python3 tools/web-runtime/generate_runtime_identity.py --check
  python3 tests/build/version_test.py
  python3 tests/conformance/module_graph_test.py
  python3 tests/conformance/version_lock_test.py
  bash tests/build/test_active_tree.sh
  npm --prefix apps/architecture-portal run check:current
  ```

  Expected: all pass.

- [ ] **Step 6: Commit the implementation and current identity atomically**

  Verify the branch is not `main`, stage only declared Task paths, inspect `git diff --cached --name-status` and `git diff --cached --check`, then commit:

  ```bash
  git commit -m "fix(creator): align keyboard and Pad order"
  ```

### Task 3: Freeze and prove the 1.0.20.0 canary

**Files:**

- Create: Docusaurus versioned docs/sidebars/diagrams/metadata for `1.0.20.0`
- Create: `docs/release-evidence/2026-08-13-stage7-keyboard-mapping-canary-1.0.20.0.md`
- Modify: `apps/architecture-portal/versions.json`
- Modify: `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md`
- Modify: `docs/quality/2026-08-12-stage7-creator-editor-review.md`
- Modify: `docs/release-evidence/2026-08-13-stage7-remediation-canary.md`

**Interfaces:**

- Consumes: clean committed `1.0.20.0` implementation source.
- Produces: immutable `canary` portal snapshot, branch-local automated Proof evidence, and an honest unexecuted ten-step human checklist.

- [ ] **Step 1: Freeze the clean candidate snapshot**

  Confirm `git status --short` is empty, then run:

  ```bash
  scripts/architecture-portal.sh version 1.0.20.0 canary
  scripts/architecture-portal.sh check
  ```

- [ ] **Step 2: Commit the immutable snapshot separately**

  Stage only generated `1.0.20.0` snapshot paths and `versions.json`, inspect staged paths/checks, and commit:

  ```bash
  git commit -m "docs(portal): freeze 1.0.20.0 canary snapshot"
  ```

- [ ] **Step 3: Run full Product verification**

  Run:

  ```bash
  scripts/creator-web.sh proof
  scripts/web-runtime-host.sh proof
  scripts/core.sh proof
  bash scripts/verify-core-dependencies.sh
  bash tests/build/test_active_tree.sh
  python3 tests/build/version_test.py
  python3 scripts/version.py verify \
    --version-file products/lmdj/version.json \
    --assembly products/lmdj/assembly.json \
    --lock products/lmdj/assembly.lock.json
  scripts/architecture-portal.sh check
  ```

  Expected: all automated gates pass. Synthetic keyboard coverage is not reported as physical hearing evidence.

- [ ] **Step 4: Record honest evidence and commit it**

  Record exact committed revisions, Assembly lock digest, Proof command outcomes/counts, package/fixture paths and digests, and an unexecuted Chinese ten-step table. Mark physical Keyboard, physical MIDI, hearing, Safari, and iPadOS `deferred / unverified`; mark merged-main Proof `pending — requires separate push/PR/merge authorization`. Stage only the new evidence file plus the three declared current acceptance/review/checklist files, inspect staged paths/checks, and commit:

  ```bash
  git commit -m "docs(stage7): record keyboard mapping canary proof"
  ```

- [ ] **Step 5: Inspect final branch state**

  Require a clean worktree, list committed file sets, and confirm no push, PR, merge, tag, Release, deployment, publication, or Channel promotion occurred.
