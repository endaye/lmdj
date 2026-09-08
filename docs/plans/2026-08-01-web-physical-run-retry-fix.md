# Web Physical Run Retry Fix Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent a third Safari physical run from starting with an ineligible route or recording more than the approved 500 browser dispatches.

**Architecture:** Keep physical-run policy in the existing pure guidance module by adding two small predicates: one for eligible built-in/wired routes and one for the 500-dispatch hard boundary. The active Host uses those predicates both before creating AudioContext and inside the trigger enqueue path, so UI state is guidance while the production boundary remains authoritative.

**Tech Stack:** JavaScript ES modules, Node.js built-in test runner, static browser Host, Markdown, Python active-tree verification.

## Global Constraints

- `unknown`, `usb`, and `bluetooth` routes must not enable or start a required physical performance run.
- Only `built-in` and `wired` are eligible required-row routes.
- Once the browser has dispatched 500 records, every later Pointer/Touch/MIDI enqueue attempt returns `false` before writing the ring, pending map, dispatch array, or counters.
- The hard boundary prevents the Safari `pointerdown` queue from producing dispatch 501 even when the disabled-button UI is late.
- Route selection and hard-cap state remain ephemeral and do not change report v2 or evidence v1.
- A valid third run still requires Safari to remain visible/running for 600,000 milliseconds and external physical capture.
- Do not change Core, Product Assembly, Providers, Contracts, or Product Build version.
- Work only on `feat/web-runtime-lab`; create one Conventional Commit, update existing PR #72, and do not merge.

## Version Management

- Product Build version impact: none; this fixes an experimental Host operator boundary.
- Core Module SemVer impact: none.
- Provider SemVer impact: none.
- Contract SemVer impact: none.
- Browser report version impact: none; valid reports remain `reportVersion: 2`.
- Physical evidence version impact: none; dossiers remain `evidenceVersion: 1`.

---

### Task 1: Enforce Physical-Run Preconditions

**Files:**

- Create: `docs/plans/2026-08-01-web-physical-run-retry-fix.md`
- Modify: `apps/web-runtime-lab/src/physical-run-guidance.mjs`
- Modify: `apps/web-runtime-lab/test/physical-run-guidance.test.mjs`
- Modify: `apps/web-runtime-lab/src/main.js`
- Modify: `apps/web-runtime-lab/test/active_tree_test.py`
- Modify: `apps/web-runtime-lab/README.md`
- Modify: `docs/quality/web-runtime-lab-acceptance.md`

**Interfaces:**

- Produces: `isEligiblePhysicalRoute(routeCategory): boolean`.
- Produces: `canDispatchBrowserTrigger(dispatchedCount): boolean`.
- Consumes: the frozen `BROWSER_RUN_TARGETS.triggerCount === 500` boundary.

- [x] **Step 1: Write failing predicate tests**

Require `isEligiblePhysicalRoute` to accept only `built-in` and `wired`. Require `canDispatchBrowserTrigger` to return true at 0 and 499, false at 500 and 501, and reject invalid counts.

- [x] **Step 2: Run RED**

Run `cd apps/web-runtime-lab && node --test test/physical-run-guidance.test.mjs`.

Expected: named exports are missing.

- [x] **Step 3: Implement pure predicates**

Use one frozen eligible-route set and the existing target constant. Do not duplicate numeric or route policy in `main.js`.

- [x] **Step 4: Run predicate GREEN**

Run the same focused test and require all guidance tests to pass.

- [x] **Step 5: Enforce both boundaries in the Host**

Disable Start when the current route is ineligible; call `render()` after route changes; recheck route in `startAudio()`; and return `false` at the top of `enqueueTrigger()` when the hard dispatch predicate rejects the current count. Keep the existing visual disable as a secondary cue.

- [x] **Step 6: Protect and document the corrected flow**

Require both predicates and their Host call sites in the active-tree test. Document that route selection must precede Start and that the hard enqueue boundary—not only HTML disabled state—prevents record 501. State that the operator must export before leaving Safari after `browser-target-ready`.

- [x] **Step 7: Verify, commit, and update PR**

Run:

```bash
scripts/web-runtime-lab.sh test
scripts/core.sh proof
git diff --check
```

Verify the branch is not `main`, stage only the seven declared files, inspect staged names and whitespace, then commit:

```text
fix(web): enforce physical run preconditions
```

Inspect committed files and clean status, push `feat/web-runtime-lab`, wait for PR #72 CI, and do not merge.

- [x] **Step 8: Reproduce the corrected Safari setup**

Reload the active Safari page, verify Start is disabled for `Unknown`, select `Built-in`, verify Start becomes enabled, start a disposable session, and prove attempts after the 500-dispatch boundary cannot increase the count. Reload once more, select `Built-in`, and leave the page at `not-started`, `0 / 500`, `00:00 / 10:00` for the operator's third run.
