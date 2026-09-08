# Web Realtime Audio Approved Gate Implementation Plan

> **For Codex:** Execute this plan in the current isolated worktree. Keep physical-device evidence separate from browser-generated estimates, and create one reviewable Conventional Commit for the complete approval follow-up.

**Goal:** Record the Product Owner's approval of the Web realtime-audio thresholds and make the lab able to evaluate an explicitly supplied physical acceptance matrix against those thresholds.

**Architecture:** The existing browser probe remains responsible only for browser-observable timing and lifecycle signals. A separate pure evaluator owns approved physical-gate configuration and evaluates operator-supplied evidence. A small command-line entry point makes the evaluator usable without turning its input into a product Contract or persisting it as Project Truth.

**Tech Stack:** JavaScript ES modules, Node.js built-in test runner, static HTML/CSS/JS, Markdown, Python active-tree verification.

## Global Constraints

- Do not treat browser estimates, headless automation, CI, or Bluetooth measurements as physical acceptance evidence.
- Do not change Core Modules, Product Assembly, Providers, Contracts, or shipped product behavior.
- Preserve the five approved required rows and their built-in/wired route requirements.
- Overall status is `passed` only when every required row is present and passes; any required-row failure yields `failed`; otherwise the result is `unverified`.
- Keep stable machine-readable reason codes and deterministic JSON output.
- Work only on `feat/web-runtime-lab`; stage only the files declared by this plan.
- Push only to the existing feature branch and update PR #72. Do not merge, tag, release, deploy, or publish.

## Version Management

- Product Build version impact: none. This approval follow-up changes an experimental lab and governance documentation, not a shipped Product Build surface.
- Core Module SemVer impact: none.
- Provider SemVer impact: none.
- Contract SemVer impact: none. The physical-evidence JSON is a local lab input format, not a cross-language Contract.
- Lab report version: remained `1` for this approval Task because only the
  decision status changed. The later physical-evidence preparer Task upgrades
  it to `2` to retain touch identity and every dispatch; see
  `2026-08-01-web-physical-evidence-preparer.md`.
- Physical evidence input version: `1`, local to the lab evaluator.

## Task 1: Formalize and Implement the Approved Physical Gate

**Files:**

- Create: `docs/plans/2026-08-01-web-realtime-audio-approved-gate.md`
- Create: `apps/web-runtime-lab/src/physical-gate.mjs`
- Create: `apps/web-runtime-lab/src/evaluate-physical-evidence.mjs`
- Create: `apps/web-runtime-lab/test/physical-gate.test.mjs`
- Modify: `docs/architecture/2026-08-01-web-realtime-audio-threshold-decision.md`
- Modify: `docs/prd/decision-log.md`
- Modify: `docs/prd/open-questions.md`
- Modify: `apps/web-runtime-lab/package.json`
- Modify: `apps/web-runtime-lab/src/probe-core.mjs`
- Modify: `apps/web-runtime-lab/test/probe-core.test.mjs`
- Modify: `apps/web-runtime-lab/src/main.js`
- Modify: `apps/web-runtime-lab/index.html`
- Modify: `apps/web-runtime-lab/README.md`
- Modify: `docs/quality/web-runtime-lab-acceptance.md`
- Modify: `scripts/web-runtime-lab.sh`
- Modify: `apps/web-runtime-lab/test/active_tree_test.py`

### Step 1: Record the approved decision

Change the threshold decision from proposed to approved, record the approval date and source, add the exact gate to the PRD decision log, and remove the resolved open-question row.

### Step 2: Write failing evaluator tests

Add tests covering:

- all five eligible physical rows passing;
- missing required rows remaining `unverified`;
- any threshold failure producing `failed`, even if other rows are missing;
- browser estimates and Bluetooth-only measurements never satisfying a required row;
- exact boundary values passing;
- invalid or duplicated evidence remaining `unverified` with stable reason codes;
- command-line JSON output and exit codes.

Run:

```bash
cd apps/web-runtime-lab
npm test
```

Expected: FAIL because the approved-gate evaluator and command do not yet exist.

### Step 3: Implement the pure evaluator and operator command

Add the frozen approved threshold configuration, strict local evidence validation, deterministic per-row and overall evaluation, and a JSON command-line entry point. Extend `scripts/web-runtime-lab.sh` with an `evaluate <evidence.json>` action.

Run:

```bash
cd apps/web-runtime-lab
npm test
```

Expected: PASS.

### Step 4: Update lab status and operator documentation

Move the browser report and visible lab status from pending approval to threshold approved while keeping the physical gate visibly `unverified`. Document the input format, required physical rows, route boundary, command, statuses, and exit codes. Update active-tree assertions so retired pending-approval text cannot return.

Run:

```bash
bash tests/build/test_active_tree.sh
bash scripts/verify-core-dependencies.sh
```

Expected: PASS.

### Step 5: Verify and create one atomic commit

Run:

```bash
scripts/core.sh proof
bash scripts/web-runtime-lab.sh test
git diff --check
```

Then verify the branch is not `main`, stage only the declared files, inspect `git diff --cached --name-only` and `git diff --cached --check`, and commit with:

```text
feat(web): enforce approved physical audio gate
```

Inspect the committed file list and final worktree status, push the feature branch to update PR #72, and wait for its checks. Do not merge.
