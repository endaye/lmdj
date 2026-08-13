# LMDJ Stage 7 Physical MIDI Channel Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Creator Web accept the Stage 7 `36..51` Pad mapping from an authorized physical MIDI controller on any MIDI channel, then produce a new fully versioned and honestly verified canary.

**Architecture:** Keep note-range, velocity, selected-Bank, permission, disconnect, and admission/outcome behavior in the existing shared `createMidiAdapter`. Remove only Creator Web's extra Channel-1 filter so it consumes the adapter's existing all-channel default; do not add an AKAI-specific profile or change Project Truth. Bind the change to a new Creator Host identity and Product Build, update current architecture truth, freeze an immutable canary snapshot, run full Proof, and keep physical results separate from automated evidence.

**Tech Stack:** TypeScript, React, JavaScript ESM, Vitest, Node test runner, Playwright, Python version tooling, CMake, Docusaurus Architecture Portal.

**Spec:** `docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md`

## Global Constraints

- Work only in `/Users/endaye/Projects/lmdj/.worktrees/stage7-review-remediation` on `fix/stage7-review-remediation`; abort any commit if the branch is `main`.
- Authorized MIDI inputs accept Note On `36..51` with velocity `1..127` from channels `1..16`; Note On velocity `0` and Note Off release the matching Pad; notes outside `36..51` remain ignored.
- The active Bank adds `bank * 16`; Pointer, Keyboard, stable Slot identity, Project Truth, Bundle, Runtime Snapshot, persistence, Provider, and audio lifecycle semantics remain unchanged.
- The shared Platform adapter remains product-neutral and keeps its optional single-channel filter for consumers that explicitly request one; only Creator stops requesting that filter.
- No device-name inspection, AKAI-specific branch, MIDI Learn, telemetry, or second input consumer is added.
- Version targets after live baseline verification: Product Build `1.0.21.0`, Creator Web `1.1.3`; Web Runtime Platform remains `0.2.1`, Formal Web Runtime Host remains `1.2.8`, and all Contracts/Providers remain unchanged.
- Documentation impact: required for `/hosts/creator-web/`, `/platform/input/`, current Product/Assembly/version/testing pages, Stage 7 design/decision/acceptance/review truth, immutable `1.0.21.0` snapshot, and canary evidence.
- Local commits are authorized. Push, PR, merge, tag, Release, deployment, publication, and Channel promotion are not authorized.

## Version Management

- Product: `1.0.20.0 -> 1.0.21.0`; a Host identity change changes Assembly identity, so governance requires a new BUILD rather than PATCH.
- Host: Creator Web `1.1.2 -> 1.1.3`; this is a backwards-compatible bug fix to physical input acceptance. Formal Web Runtime Host stays `1.2.8` because its implementation and Platform dependency do not change.
- Module: Web Runtime Platform stays `0.2.1`; its all-channel default already exists and no public adapter behavior changes.
- Contract, Provider, Model: none; no schema, Capability, Project migration, Provider implementation, or model identity changes.
- Compatibility: existing Projects and `.lmdj` bundles require no migration. Channel-1 controllers behave identically; channels 2–16 newly reach the same bounded note mapping.
- Candidate Channel: `canary`. Freeze `scripts/architecture-portal.sh version 1.0.21.0 canary` only from a clean committed implementation.
- Prospective tag: `lmdj-v1.0.21.0`, only after an authorized PR is merged and the exact merged `main` revision passes required Proof. This plan does not authorize creating or pushing it.

---

### Task 1: Restore generic MIDI-channel acceptance

**Files:**

- Modify: `apps/creator-web/test/input_controller.test.ts`
- Modify: `apps/creator-web/src/runtime/input_controller.ts`
- Modify: `docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md`
- Modify: `docs/prd/decision-log.md`
- Create: `docs/superpowers/plans/2026-08-13-lmdj-stage7-physical-midi-channel-compatibility.md`

**Interfaces:**

- Consumes: `createMidiAdapter({ channel?: number | null, noteStart, slotCount, resolveSlot, ... })`, whose omitted `channel` value accepts all MIDI channels.
- Produces: Creator physical MIDI acceptance for channels 1–16 while preserving Note `36..51 -> local Pad 0..15 -> selected Bank`.

- [x] **Step 1: Write the failing Creator behavior test**

  Change the existing physical mapping test to send the first accepted Pad on Channel 10 and release it on Channel 10. Keep a Channel-1 trigger after the Bank change so the same test proves both channel families and preserves selected-Bank behavior:

  ```ts
  test("maps MIDI 36..51 on every channel to the selected Bank and removes listeners", async () => {
    // existing fixture and authorized input setup
    input.emit([0x99, 36, 73]);
    await settle();
    expect(value.triggers).toEqual([{slot: 16, velocity: 73, source: "midi"}]);
    input.emit([0x89, 36, 64]);
    expect(value.state().pressed.has(16)).toBe(false);

    bank = 2;
    value.selectBank(bank);
    input.emit([0x90, 36, 91]);
    await settle();
    expect(value.triggers.at(-1)).toEqual({slot: 32, velocity: 91, source: "midi"});
  });
  ```

- [x] **Step 2: Run RED and verify the intended failure**

  Run:

  ```bash
  npm --prefix apps/creator-web test -- --run test/input_controller.test.ts
  ```

  Expected: FAIL because Channel-10 status `0x99` is filtered by Creator's current `channel: 0`, so the first Trigger is missing.

- [x] **Step 3: Implement the minimal fix**

  Remove only the explicit `channel: 0` argument from Creator's `createMidiAdapter` call. Do not change `packages/web-runtime-platform/web/input_adapters.mjs`; omitting the argument selects its existing `channel = null` default.

- [x] **Step 4: Clarify approved product truth**

  In the Stage 7 design Pad/Input section and the 2026-08-13 decision log, record that generic Creator MIDI listens to every authorized input and accepts the bounded `36..51` mapping on channels 1–16. Record the physical evidence that exposed the defect without encoding device names into production behavior: the tested AKAI MPD218 program sent PAD BANK A on Channel 10 with the expected note range.

- [x] **Step 5: Run GREEN focused behavior gates**

  Run:

  ```bash
  npm --prefix apps/creator-web test -- --run test/input_controller.test.ts
  node --test packages/web-runtime-platform/test/input_adapters.test.mjs
  ```

  Expected: all tests pass; the Platform's explicit single-channel filter test remains green.

- [x] **Step 6: Commit Task 1 atomically**

  Verify non-`main`, stage only the five declared paths, inspect `git diff --cached --name-status` and `git diff --cached --check`, then commit:

  ```bash
  git commit -m "fix(creator): accept generic MIDI channels"
  ```

### Task 2: Allocate and propagate the corrected candidate identity

**Files:**

- Modify: `products/lmdj/version.json`, `assembly.json`, `assembly.lock.json`, `src/compiled_assembly.cpp`, `CMakeLists.txt`, and `README.md`
- Modify: `apps/creator-web/module.json`, `package.json`, and `package-lock.json`
- Regenerate: `products/lmdj/generated/web-runtime-identity.json` and `.mjs`
- Modify: exact active identity assertions under `tests/`, `apps/*/test`, and `packages/*/test` returned by focused `rg`
- Modify: current Architecture Portal Product, Assembly, Creator Host, input, testing, and version pages plus their current-facts tests
- Modify: `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md`
- Modify: `docs/quality/2026-08-12-stage7-creator-editor-review.md`
- Modify: this plan

**Interfaces:**

- Consumes: Creator behavior commit from Task 1 and the active Assembly/version policy.
- Produces: one self-consistent `1.0.21.0` Assembly with Creator `1.1.3`, Platform `0.2.1`, and diagnostic Host `1.2.8`.

- [x] **Step 1: Write RED identity expectations**

  Update the authoritative test expectations first to Product `1.0.21.0` and Creator `1.1.3`, leaving Platform and diagnostic Host unchanged. Update current acceptance/review text so `1.0.20.0` remains immutable passed keyboard evidence while the new physical-MIDI correction is a fresh, unproven candidate.

- [x] **Step 2: Run RED identity gates**

  ```bash
  python3 tests/build/version_test.py
  python3 tests/conformance/module_graph_test.py
  python3 tests/conformance/version_lock_test.py
  ```

  Expected: failures identify stale Product/Creator manifests, compiled Assembly, generated identity, and lock data.

- [x] **Step 3: Update manifests and regenerate derived truth**

  Set the target Product and Creator identities, update exact Assembly consumers, then run:

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

  Document channels 1–16 as the Creator default, retain the configurable Platform filter, update Product/Creator identities, and mark physical MIDI as `failed on 1.0.20.0 / pending retest on 1.0.21.0`. Preserve Safari and iPadOS as separately observed states; do not rewrite immutable `1.0.20.0` snapshot content.

- [x] **Step 5: Run GREEN behavior, identity, and current-doc gates**

  ```bash
  npm --prefix apps/creator-web test -- --run
  python3 tools/web-runtime/generate_runtime_identity.py --check
  python3 tests/build/version_test.py
  python3 tests/conformance/module_graph_test.py
  python3 tests/conformance/version_lock_test.py
  bash tests/build/test_active_tree.sh
  npm --prefix apps/architecture-portal run check:current
  ```

  Expected: all pass.

- [x] **Step 6: Commit Task 2 atomically**

  Stage only Task 2 paths, inspect staged paths/checks, and commit:

  ```bash
  git commit -m "fix(product): assemble Stage 7 MIDI compatibility candidate"
  ```

### Task 3: Freeze and prove the 1.0.21.0 canary

**Files:**

- Create: immutable Docusaurus docs/sidebars/diagrams/metadata for `1.0.21.0`
- Modify: `apps/architecture-portal/versions.json`
- Create: `docs/release-evidence/2026-08-13-stage7-midi-channel-canary-1.0.21.0.md`
- Modify: current Stage 7 acceptance/review documents

**Interfaces:**

- Consumes: clean committed `1.0.21.0` implementation and Assembly.
- Produces: immutable canary snapshot, full branch-local Proof, and an honest physical retest sheet.

- [x] **Step 1: Freeze the clean candidate snapshot**

  ```bash
  scripts/architecture-portal.sh version 1.0.21.0 canary
  scripts/architecture-portal.sh check
  ```

- [x] **Step 2: Commit the immutable snapshot separately**

  Stage only generated `1.0.21.0` snapshot paths and `versions.json`, inspect staged paths/checks, and commit:

  ```bash
  git commit -m "docs(portal): freeze 1.0.21.0 canary snapshot"
  ```

- [x] **Step 3: Run full candidate verification**

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

  Expected: all automated gates pass. Synthetic Channel-10 coverage is not reported as physical-device evidence.

- [x] **Step 4: Record Proof and physical retest instructions**

  Record exact committed revisions, Assembly Lock digest, toolchain identities, Proof counts, fixture/report hashes, and a physical matrix. Record the observed `1.0.20.0` MPD218 failure, the Safari manual result exactly as supplied, and keep `1.0.21.0` MPD218/iPadOS results unverified until actually performed.

- [x] **Step 5: Commit evidence atomically**

  ```bash
  git commit -m "docs(stage7): record MIDI compatibility canary proof"
  ```

### Task 4: Perform and bind physical acceptance

**Files:**

- Modify: `docs/release-evidence/2026-08-13-stage7-midi-channel-canary-1.0.21.0.md`
- Modify: current Stage 7 acceptance/review documents

**Interfaces:**

- Consumes: the exact `1.0.21.0` package, `stage7-canary.lmdj`, AKAI MPD218, macOS Chrome, and the named human's observations.
- Produces: pass/fail evidence for Chrome physical MIDI, while Safari/iPadOS stay independently scoped.

- [ ] **Step 1: Verify raw device input and Creator behavior**

  Capture at least one raw Note On/Off pair from `MPD218 Port A`, then in Chrome explicitly activate Audio, enable MIDI, and play all 16 physical Pads in Bank A. Verify Channel 10 notes `36..51`, velocity preservation, no duplicate/missing/stuck trigger, Banks B/C/D sample addresses, disconnect/reconnect, suspend/reactivate, and reload/reopen.

- [ ] **Step 2: Record only the performed observations**

  Store operator, date/time/timezone, exact Chrome/macOS/device identity, candidate revision, Project fixture digest, per-row result, and exported privacy-safe report SHA-256. Do not infer iPadOS or another browser from this result.

- [ ] **Step 3: Commit the signed evidence update**

  After validating the supplied human fields, stage only the three evidence/current-truth documents, inspect staged paths/checks, and commit:

  ```bash
  git commit -m "docs(stage7): record physical MIDI canary"
  ```

- [ ] **Step 4: Inspect final local state**

  Require a clean worktree and confirm no push, PR, merge, tag, Release, deployment, publication, or Channel promotion occurred.
