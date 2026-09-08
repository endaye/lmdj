# Web Physical Run Guidance Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the physical-test operator an exact 500-trigger and uninterrupted 10-minute browser-run guide without presenting browser state as physical acceptance evidence.

**Architecture:** A pure `evaluateBrowserRunGuidance(observation)` function owns the two approved browser-run targets and deterministic operator states. The active lab records only an ephemeral foreground start time and interruption flag, renders the pure result once per second, and keeps report v2 and physical evidence formats unchanged.

**Tech Stack:** JavaScript ES modules, Node.js built-in test runner, static HTML/CSS, Markdown, Python active-tree verification.

## Global Constraints

- The approved browser-run targets are exactly 500 dispatches and 600,000 milliseconds of uninterrupted visible/running foreground time.
- Guidance states are `not-started`, `collecting`, `browser-target-ready`, or `restart-required`; none is a physical `passed` result.
- More than 500 dispatches, acknowledgement loss after a one-second grace window, duplicate acknowledgement, ring-full drop, processor error, non-running audio after start, or hidden/frozen/pagehide after start requires a fresh page reload.
- The ready state still says that retained 240 fps-or-faster high-speed video or calibrated wired-loopback evidence is required.
- Do not write, upload, persist, or add guidance fields to report v2 or physical evidence v1.
- Do not change Core Modules, Product Assembly, Providers, Contracts, or Product Build version.
- Work only on `feat/web-runtime-lab`; create one Conventional Commit, push only to the existing PR #72, and do not merge.

## Version Management

- Product Build version impact: none; this is an ephemeral experimental Host operator aid.
- Core Module SemVer impact: none.
- Provider SemVer impact: none.
- Contract SemVer impact: none.
- Browser report version impact: none; `reportVersion: 2` is unchanged because guidance state is not exported.
- Physical evidence version impact: none; `evidenceVersion: 1` is unchanged.

---

### Task 1: Add Deterministic Browser-Run Guidance

**Files:**

- Create: `docs/plans/2026-08-01-web-physical-run-guidance.md`
- Create: `apps/web-runtime-lab/src/physical-run-guidance.mjs`
- Create: `apps/web-runtime-lab/test/physical-run-guidance.test.mjs`
- Modify: `apps/web-runtime-lab/src/main.js`
- Modify: `apps/web-runtime-lab/index.html`
- Modify: `apps/web-runtime-lab/styles.css`
- Modify: `apps/web-runtime-lab/test/active_tree_test.py`
- Modify: `apps/web-runtime-lab/README.md`
- Modify: `docs/quality/web-runtime-lab-acceptance.md`

**Interfaces:**

- Consumes: `evaluateBrowserRunGuidance({ startedAtMs, nowMs, dispatchedCount, acknowledgedCount, duplicateAcknowledgements, droppedCount, processorErrors, audioState, visibilityState, interrupted })`.
- Produces: a frozen target definition and `{ status, elapsedMs, remainingMs, remainingTriggers, reasons }` with stable state/reason strings.

- [x] **Step 1: Write failing pure guidance tests**

Create tests that require: null start to return `not-started`; partial time/count to return `collecting`; exactly 500 acknowledgements at 600,000 ms with visible/running state to return `browser-target-ready`; and each invalidating condition to return `restart-required`. Assert the ready result contains no physical pass field.

- [x] **Step 2: Run RED**

Run:

```bash
cd apps/web-runtime-lab
npm test
```

Expected: module-not-found for `src/physical-run-guidance.mjs`.

- [x] **Step 3: Implement the pure state function**

Export frozen targets `{ triggerCount: 500, foregroundDurationMs: 600_000 }`. Validate finite non-negative time/count inputs, return stable reasons, require exact acknowledgement parity, and make any invalidating observation outrank collection/readiness.

- [x] **Step 4: Run GREEN**

Run `cd apps/web-runtime-lab && npm test` and require all tests to pass.

- [x] **Step 5: Integrate ephemeral visible guidance**

Add one guidance article with an accessible text output. Start the ephemeral timer only after AudioContext reaches `running`; invalidate it on later non-running state, hidden visibility, freeze, or pagehide. Refresh the display once per second and render exact trigger/time progress plus the external physical-capture reminder. Do not add any guidance state to `createReport(session)`.

- [x] **Step 6: Protect and document the boundary**

Update the active-tree check, README, and acceptance policy to require exact targets, restart conditions, `browser-target-ready` wording, and the explicit non-substitution rule.

- [ ] **Step 7: Verify, commit, and update PR**

Run:

```bash
scripts/web-runtime-lab.sh test
scripts/core.sh proof
git diff --check
```

Verify the branch is not `main`, stage only the nine declared files, inspect staged names and whitespace, then commit:

```text
feat(web): guide physical browser runs
```

Inspect committed files and clean status, push `feat/web-runtime-lab`, wait for PR #72 CI, and do not merge.
