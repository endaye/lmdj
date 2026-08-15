# LMDJ Stage 8B Pad Capture Kickoff Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `feat/stage8b-pad-capture` from a freshly stacked branch to an
implementation-ready state: keep it correctly synced with the still-open Stage 8
branch, audit the capture reuse boundary Stage 8 deliberately left behind
(S8-D13), and produce an approved Stage 8B Pad Capture design spec — after
which this plan is extended with implementation tasks.

**Architecture:** Stage 8B records microphone / audio-input into a Pad by
producing bounded PCM16 WAV bytes that enter the Core through the *same*
Artifact import boundary Stage 8 built (Application Facade Sample mutations →
Project I/O staging → Cooker preparation). Capture device access, permission,
and monitoring live in the Web Runtime Host / Creator layer; the Core never
learns about `MediaStream` or browser permission state. No implementation
happens under this plan until the design gate closes.

**Tech Stack:** C++20, CMake 3.24+, Emscripten `6.0.5`, Wasm AudioWorklet,
WasmFS OPFS, React `19.2.8`, TypeScript `7.0.2`, Playwright `1.62.1`,
`getUserMedia` / `MediaDevices` (design-gated), JSON Schema 2020-12,
Docusaurus Architecture Portal.

## Global Constraints

- Execute only on `feat/stage8b-pad-capture` in
  `/Users/endaye/Projects/lmdj/.worktrees/stage8b-pad-capture`, stacked from
  Stage 8 commit `6b283fe964198bc114c5e1b1aac15055aadf08a7`. Never implement on
  `main`, and never commit Stage 8B work to `feat/stage8-sample-editor`.
- Never push to `feat/stage8-sample-editor` from this branch or worktree. PR
  [#137](https://github.com/endaye/lmdj/pull/137) is owned by the Stage 8
  completion work and must not be affected by Stage 8B activity.
- The authoritative stage ladder
  (`docs/superpowers/specs/2026-08-08-lmdj-stage8-sample-editor-design.md` §3)
  defines Stage 8B as **microphone / audio-input Pad Capture only**. Automatic
  Slice/Stem belongs to Stage 12, Take/Pattern recording to Stage 9, and a
  browser-wide Sample library to the Stage 2+ open questions. Do not pull them
  into Stage 8B.
- Per S8-D13 and `docs/prd/decision-log.md`, Stage 8B is unimplemented and
  unversioned, and its capture lifecycle is an **open product boundary**. Do
  not silently settle any open product-level Contract or concurrency question
  inside an implementation Task; the design gate (Task 3) is where those
  decisions are made and recorded.
- Preserve every Stage 8 architectural and safety boundary listed in
  `docs/quality/2026-08-15-stage8-sample-editor-handoff.md`: Facade-only Hosts,
  Pad-Slot-owned playback truth, `command_id` + `expected_revision` mutation
  semantics, allocation-free/lock-free audio render paths, fail-closed
  telemetry, single-owner lifecycle cleanup, and bounded browser payloads.
- `lmdj.patch.v1` and `lmdj.materials.v1` remain retired.
- Every Task is one reviewable Conventional Commit. Before every commit: verify
  the branch is not `main`; run the Task-specific verification and
  `scripts/architecture-portal.sh check`; stage only declared files; inspect
  `git diff --cached --name-status` and `git diff --cached --check`; after
  committing inspect `git show --name-status --oneline HEAD`.
- This plan authorizes local commits only. Push, PR creation, merge, tag,
  Release, publication, deployment, and Channel promotion each require
  separate explicit authorization.

---

## Current State (observed 2026-08-15)

| Item | Observed state |
| --- | --- |
| Stage 8 branch | `feat/stage8-sample-editor`, local tip `6b283fe9`, **7 commits ahead of origin** |
| Stage 8 PR | #137, Open, Draft; reflects remote tip `64a8ef0b` only |
| `origin/main` | `a71c62d4`, already merged into the Stage 8 local tip |
| Stage 8B branch | `feat/stage8b-pad-capture` at `6b283fe9`, this worktree |
| Product Build | `1.0.22.0 · canary` (immutable snapshot; belongs to Stage 8) |
| Stage 8B versions | None allocated (S8-D13: unimplemented, unversioned) |

### Stage 8 remaining work (prerequisite, tracked here, executed elsewhere)

The following work finishes Stage 8. It is executed **on
`feat/stage8-sample-editor` in `.worktrees/stage8-sample-editor`**, under
`docs/quality/2026-08-15-stage8-sample-editor-handoff.md` — never under this
plan or on this branch. Stage 8B tracks it only because each step can move the
Stage 8 tip and trigger a resync (see Branch and Sync Discipline).

- [ ] ~~Merge latest `main` and resolve the three known conflicts~~ — already
  done locally in `6b283fe9`; `origin/main` has not advanced past `a71c62d4`.
- [ ] Refresh mutable truth to the post-merge HEAD:
  `docs/quality/2026-08-09-stage8-sample-editor-acceptance.md` (its *current
  reviewed implementation* and external-state sections are stale), the PR #137
  body validation revision, and the handoff document if state changes
  materially. Do not touch the immutable `1.0.22.0` Portal snapshot.
- [ ] Run the post-merge local gates from the handoff §3 (`scripts/core.sh`
  full + stress + proof, dependency/tree/version checks,
  `scripts/architecture-portal.sh check`, Creator / Web Runtime Host / Web
  toolchain conformance gates).
- [ ] Push the 7 local commits, confirm remote SHA equals local HEAD, mark PR
  #137 ready for review, and obtain the exact-head full CI matrix (Core, ASan
  full+stress, coverage, package, Creator, Web Runtime Host, Web toolchain
  conformance, Portal, macOS).
- [ ] Stop. Merge of #137 requires new explicit user authorization.

## Branch and Sync Discipline

Stage 8B stacks on an unmerged branch, so synchronization is one-directional
and rebase-based. Keep `feat/stage8b-pad-capture` a **linear run of commits
sitting directly on the Stage 8 tip** at all times.

**When the Stage 8 branch gains commits** (review fixes, truth refreshes):

```bash
cd /Users/endaye/Projects/lmdj/.worktrees/stage8b-pad-capture
git fetch origin --prune
git rebase feat/stage8-sample-editor
```

**After PR #137 squash-merges into `main`** (the Stage 8 commits will not
exist in `main` as-is, so a plain rebase would replay them):

```bash
git fetch origin main
STAGE8_TIP=$(git rev-parse feat/stage8-sample-editor)
git rebase --onto origin/main "$STAGE8_TIP" feat/stage8b-pad-capture
```

**Never** merge `feat/stage8-sample-editor` into this branch (merge commits
break the final `--onto`), and **never** push, cherry-pick, or otherwise write
Stage 8B commits onto `feat/stage8-sample-editor`.

## Stage 8B Scope Authority

In scope (from the approved stage ladder and S8-D13):

1. Capturing microphone / audio-input into an empty or assigned Pad;
2. Input permission request flow, device selection, and capture monitoring;
3. Capture interruption, cancellation, and failure semantics;
4. Converting captured audio into the existing bounded PCM16 WAV Artifact
   identity and importing it through the existing Facade Sample mutations.

Explicitly not Stage 8B (do not design or implement here):

- Automatic slicing, Chop, Stem separation — Stage 12;
- Take / Pattern / Sequence recording, Quantize, Swing — Stage 9;
- Browser-wide / global Sample library, Asset delete, Artifact GC — open
  Stage 2+ questions;
- Non-destructive processing (Pitch, Reverse, Pan, envelopes, time-stretch) —
  excluded by the Stage 8 design §5 and the open BPM/time-stretch question;
- PWA, cloud, account, deployment, Channel promotion.

## Design Gate: open questions Task 3 must resolve

These are the product-level questions the Stage 8 design (§3, §19.5) and
`docs/prd/decision-log.md` explicitly deferred to Stage 8B. Each needs an
approved decision recorded in the Stage 8B design spec, and the corresponding
rows of `docs/prd/open-questions.md` / `docs/prd/decision-log.md` updated at
approval time:

1. **Permission lifecycle** — when Creator requests `getUserMedia`, how denial,
   revocation mid-capture, and re-request are surfaced; Stage 8 deliberately
   never requests recording permission.
2. **Device selection** — which input devices are offered, where the selection
   lives (Workspace/Host settings per the Provider-selection invariant, never
   Project Truth), and how device disappearance mid-capture behaves.
3. **Capture lifecycle** — arm → record → stop → preview → commit/discard state
   machine; whether capture survives blur/hidden visibility or fails closed
   like Stage 8 Voice ownership; single-owner cleanup.
4. **Monitoring and feedback suppression** — whether input monitoring exists in
   v1 and how speaker-to-microphone feedback is prevented or documented.
5. **Quality and format** — capture sample rate/channel policy and how captured
   audio maps onto the existing bounded PCM16 WAV limits (`1,048,576` imported
   bytes, `240,000` decoded source frames per Pad); what happens when a capture
   exceeds them (truncate, reject, or pre-trim).
6. **Concurrency semantics** — how a capture commit interacts with
   `expected_revision` when the Project changed during recording; no auto-
   rebase, no optimistic success (Stage 8 invariant).
7. **Physical evidence gate** — which real-microphone / real-device sessions
   are required before Stage 8B acceptance, and which stay explicitly deferred.

---

### Task 1: Verify baseline and record sync facts

**Files:**
- No file changes. Read-only audit; findings feed Task 3.

**Interfaces:**
- Consumes: nothing.
- Produces: verified baseline facts (`STAGE8_TIP`, divergence counts) quoted in
  the Task 3 design spec's Current State section.

- [ ] **Step 1: Verify worktree, branch, and stacking base**

```bash
cd /Users/endaye/Projects/lmdj/.worktrees/stage8b-pad-capture
git status --short --branch
git merge-base --is-ancestor feat/stage8-sample-editor HEAD && echo "stacked on stage8 tip"
git rev-parse HEAD feat/stage8-sample-editor
```

Expected: branch `feat/stage8b-pad-capture`, clean tree, "stacked on stage8
tip", both SHAs equal until Stage 8B commits exist.

- [ ] **Step 2: Check whether the Stage 8 tip moved**

```bash
git fetch origin --prune
git rev-list --left-right --count feat/stage8b-pad-capture...feat/stage8-sample-editor
```

Expected: `N 0` (right side zero). A non-zero right side means the Stage 8
branch advanced: run the rebase from Branch and Sync Discipline before
continuing, then re-run this step.

- [ ] **Step 3: Confirm the build baseline is intact**

```bash
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
```

Expected: all pass. This proves the stacked baseline is healthy before any
Stage 8B work; failures here belong to Stage 8, not Stage 8B — report them,
do not fix them on this branch.

### Task 2: Audit the S8-D13 capture reuse boundary

**Files:**
- Read: `packages/application-facade/include/lmdj/facade/application.hpp`
- Read: `packages/application-facade/src/application.cpp`
- Read: `packages/web-runtime-platform/src/control_runtime.cpp`
- Read: `packages/project-io/src/project_store.cpp`
- Read: `docs/superpowers/specs/2026-08-08-lmdj-stage8-sample-editor-design.md`
- No file changes in this Task; the audit result becomes the "Reuse boundary"
  section of the Task 3 design spec.

**Interfaces:**
- Consumes: Task 1's verified baseline.
- Produces: the exact list of existing entry points capture must reuse — the
  Facade Sample import/replace mutation signatures (name, `command_id`,
  `expected_revision`, byte-payload parameters), the Web control-runtime
  transport shape for Sample bytes, and the Project I/O staging/lease
  semantics — quoted with file paths and line numbers in the design spec.

- [ ] **Step 1: Extract the Facade import surface**

```bash
grep -n -i "import\|replace" packages/application-facade/include/lmdj/facade/application.hpp
```

Record every Sample import/replace mutation signature verbatim. Capture must
commit through these mutations; if the audit finds capture *cannot* reuse them
without modification, that is a design-gate finding, not a licence to change
the Facade in this Task.

- [ ] **Step 2: Extract the transport and staging boundaries**

```bash
grep -n -i "sample\|import" packages/web-runtime-platform/src/control_runtime.cpp | head -40
grep -n -i "staging\|lease" packages/project-io/src/project_store.cpp | head -40
```

Record the bounded sidecar payload path (browser payloads never carry raw
Sample bytes outside the bounded verified sidecar boundary) and the
writer-lease / idempotent staging semantics the capture commit will inherit.

- [ ] **Step 3: Record the audit in scratch notes for Task 3**

Write the findings (signatures, payload limits, staging semantics, any reuse
blockers) into the working notes that seed the Task 3 spec. No repository file
changes; nothing to commit for Tasks 1–2.

### Task 3: Author the Stage 8B Pad Capture design spec

**Files:**
- Create: `docs/superpowers/specs/2026-08-15-lmdj-stage8b-pad-capture-design.md`
- Modify: `docs/prd/open-questions.md` (only rows the approved design resolves)
- Modify: `docs/prd/decision-log.md` (append the approved Stage 8B decisions)

**Interfaces:**
- Consumes: Task 1 baseline facts and Task 2 reuse-boundary audit.
- Produces: an approved design spec that becomes the authority for this plan's
  implementation extension (Task 4), plus updated PRD truth.

- [ ] **Step 1: Run the brainstorming skill with the user**

Use superpowers brainstorming to work through the seven Design Gate questions
above with the user. Every decision needs an ID (`S8B-D1`, `S8B-D2`, …)
mirroring the Stage 8 `S8-D*` convention. Do not proceed past this step
without explicit user approval of each decision.

- [ ] **Step 2: Write the design spec**

Mirror the Stage 8 design spec structure: Intent, Approved Decisions table,
Stage Boundary, Scope, Non-goals, the reuse-boundary contract from Task 2,
capture state machine, failure/interruption semantics, acceptance checklist,
and an explicit rollback/compatibility section. State plainly which physical
evidence stays deferred.

- [ ] **Step 3: Update PRD truth in the same commit**

Remove or narrow only the open-question rows the approved design actually
resolves; append the `S8B-D*` decisions to `docs/prd/decision-log.md` dated
with the approval date. Preserve unrelated open questions verbatim.

- [ ] **Step 4: Verify and commit**

```bash
cd /Users/endaye/Projects/lmdj/.worktrees/stage8b-pad-capture
scripts/architecture-portal.sh check
git add docs/superpowers/specs/2026-08-15-lmdj-stage8b-pad-capture-design.md \
        docs/prd/open-questions.md docs/prd/decision-log.md
git diff --cached --name-status && git diff --cached --check
git commit -m "docs(stage8b): approve pad capture design"
git show --name-status --oneline HEAD
```

Expected: portal check passes; exactly the three declared files in the commit.

### Task 4: Extend this plan with implementation tasks (governance gate)

**Files:**
- Modify: `docs/superpowers/plans/2026-08-15-lmdj-stage8b-pad-capture.md`

**Interfaces:**
- Consumes: the approved Task 3 design spec.
- Produces: the full Stage 8B implementation task list appended to this plan.

This is a deliberate gate, not an omission: writing implementation tasks now
would force decisions the design gate owns. After Task 3 approval, extend this
plan using the writing-plans skill with, at minimum, the same skeleton the
Stage 8 plan used (`docs/superpowers/plans/2026-08-09-lmdj-stage8-sample-editor.md`):

- [ ] A File Structure section locking file-level decomposition;
- [ ] Per-task TDD implementation tasks (failing test → run → implement → run →
  commit) across Creator capture UI, Web Runtime Host device/permission layer,
  transport, and the Facade-reusing commit path;
- [ ] A version-integration task allocating the Stage 8B Product Build and
  Module/Contract SemVer bumps (see Version Management below);
- [ ] An immutable Portal snapshot task
  (`scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL`);
- [ ] A final automated-acceptance task with an explicit deferred physical
  evidence ledger.

Each extension commit to this plan is itself a reviewable
`docs(stage8b): …` Conventional Commit.

---

## Documentation Impact

Documentation impact: **required at Task 3 and beyond** —
`docs/prd/open-questions.md`, `docs/prd/decision-log.md`, and the new design
spec change in Task 3; the Task 4 extension will declare Portal route impact
for the implementation stage (a Stage 8B Product Build cannot declare
`Documentation impact: none`). The initial commit of this plan document itself
touches no Portal route, active manifest, or derived identity; it is covered
by `scripts/architecture-portal.sh check` before commit.

## Version Management

Version impact: **none for this plan document and Tasks 1–3** — Stage 8B is
recorded in the decision log as unimplemented and unversioned (S8-D13), and
nothing in Tasks 1–3 changes active manifests, Module versions, Contract
versions, or Product Builds.

Planned impact, allocated only in the Task 4 extension after design approval:

- A new Product Build (`MILESTONE.MINOR.BUILD.PATCH`, next after `1.0.22.0`,
  allocated through the portal/version tooling — never hand-entered);
- SemVer bumps for the Modules the approved design actually touches (expected:
  Creator app, Web Runtime Host; Facade/Contract bumps only if the Task 2
  audit proves reuse requires surface changes);
- Contract changes only via new Contract SemVer on stable Contract IDs; the
  retired contracts stay retired.

## Completion Boundary

This plan ends when Task 3's approved design spec is committed and Task 4 has
extended this plan with implementation tasks. Push of `feat/stage8b-pad-capture`,
PR creation, and everything after remain separately authorized. PR #137 and
`feat/stage8-sample-editor` are never written to by work under this plan.
