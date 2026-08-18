# LMDJ Application Facade Coverage Raise Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise `packages/application-facade/` line coverage from 84.04% to the
policy's own long-term target of 90%, by writing behavioral tests for the
failure semantics that today have none — and only then ratchet the floor up to
hold the new level. This supersedes triage item C1, whose premise the
2026-08-18 measurement disproved: the gate is deterministic on the enforcing
platform, so the remaining work was never gate repair, it is coverage.

**Direction, fixed by the product owner:** the floor number is not the point.
What matters is why 16% of the package is unexercised — hard to test, or
simply untested — and closing the part that is merely untested. Coverage is a
review signal, not the goal: every test added under this plan asserts an error
contract (code, message, envelope shape); a test that executes lines without
asserting behaviour does not count, per
`docs/quality/core-test-policy.md` §Coverage Thresholds.

**Architecture:** Test additions in `tests/core/facade/`, plus one
compile-time-gated fault hook in `packages/application-facade/` mirroring the
`project-io` precedent (`LMDJ_PROJECT_IO_TESTING` / `FaultPoint` /
`invoke_fault`, `project_store.cpp:1468-1477`, exercised by
`tests/core/project_io/fault_matrix_test.cpp`). No Contract, protocol, or
behaviour change; production code paths are untouched except for inert hook
call sites compiled only in testing configurations.

**Tech Stack:** C++20, CTest tiers per `docs/quality/core-test-policy.md`,
LLVM source coverage via `scripts/core-coverage.sh`.

## Evidence base

[`2026-08-18-facade-coverage-gate-measurement.md`](../../quality/2026-08-18-facade-coverage-gate-measurement.md)
established that the measurement is deterministic where it counts. The
line-level anatomy of the 648 uncovered lines (Ubuntu: 648/4061; local macOS
numbers differ by two Apple-only coverage objects):

| File | Uncovered | Shape |
| --- | ---: | --- |
| `src/application.cpp` | 542 | 139 contiguous blocks, only 2 of them ≥10 lines — failure exits scattered through otherwise-covered functions |
| `src/c_api.cpp` | 54 | C ABI boundary rejections and one catch-all |
| `src/assembly_loader.cpp` | 52 | malformed-JSON rejection branches across 13 small validators |

89% of uncovered lines sit on error/failure paths. Grouped by what a test
needs to reach them:

> **Corrected 2026-08-18 during Task 1.** The per-function line counts below
> were produced by a heuristic that scanned upward for the nearest signature,
> which mis-attributed blocks to the preceding function. Measured against
> `llvm-cov report -show-functions`, `validate_initial_pattern` was 4 lines,
> not 39, and covering it fully moved the package 84.08% → 84.18%. The
> corrected attribution is in the table under "Where the volume actually is";
> Tier A is materially smaller than estimated and Tier B carries the volume.
> The tier *shapes* below still hold — what each target needs is unchanged.

**Tier A — reachable today with ordinary bad inputs (line counts unreliable, see correction):**

| Target | Lines | How |
| --- | ---: | --- |
| `validate_initial_pattern` | 39 | invalid patterns: out-of-range step, bad slot, wrong bars |
| `assembly_loader.cpp`, all 13 validators | 52 | malformed assembly JSON rejection cases in the existing `assembly_loader_test` |
| error envelope mapping (`sample_public_message`, `sample_public_details`, `internal_error`) | ~37 | table-driven over the ErrorCode enum |
| C ABI rejections (`lmdj_engine_create` null/invalid args, `bounded_c_string` overlength, `copy_string`, `acquire_engine`) | ~40 | existing C API test framework |
| Sample import session limit | 8 | open sessions in a loop until "Sample import session limit reached" |
| corrupted waveform cache (`cache_unsigned`, `decode_waveform_cache`) | 18 | corrupted cache JSON in project state |
| TriggerMode cold branches (`gate`, `loop_toggle`) | 6 | direct calls |

**Tier B — needs the fault hook (~180 lines):**

| Target | Lines | How |
| --- | ---: | --- |
| render scratch/staging family (`read_verified_scratch` 42, `write_verified_staging` 23, `create_temp_render` 14, `create_scratch_render` 14, related returns ~40) | ~130 | facade-side fault points at the filesystem seams, mirroring project-io's mechanism |
| 24 per-API catch-alls ("unexpected Application Facade Host API failure", 52 occurrences) | ~50–100 | one throw-injection hook, parameterized across every API entry |

**Tier C — deliberately not pursued (~50–80 lines):** deep defence such as
specific rare errno combinations, byte-level TOCTOU re-verification ("scratch
changed while it was being read"), and allocation failure. Fixture complexity
exceeds the value; these lines are why 100% is not a sane target.

Arithmetic: 90% needs 3655/4061 covered on Ubuntu, i.e. +242 lines. The
per-tier landing points estimated here were derived from the mis-attributed
counts and are **not** to be relied on; the honest statement is that Tier B
holds most of the reachable volume, and each task re-measures rather than
predicting. Branches start at 66.86% against an 80% target.

## Where the volume actually is (measured 2026-08-18)

`llvm-cov report -show-functions` over `application.cpp`, functions with
uncovered lines, largest first:

| Uncovered | Of total | Function |
| ---: | ---: | --- |
| 43 | 112 | `Impl::begin_sample_import` |
| 37 | 128 | `Impl::cleanup_sample_import_staging` |
| 22 | 80 | `Impl::render_offline` |
| 21 | 87 | `Impl::cook_project` |
| 14 | 76 | `Impl::commit_sample_import` |
| 12 | 104 | `Impl::query_sample_waveform` |
| 12 | 103 | `Impl::take_commit` |
| 9 | 72 | `Impl::update_sample_pad` |
| 9 | 42 | `Impl::append_sample_import` |
| 8 | 27 | `Impl::create_initial_project` |
| 7 | 13 | `Application::append_project_bundle_index` |
| 7 | 12 | `Application::prepare_runtime_snapshot` |

356 uncovered lines across 47 functions with gaps; the remainder sit in
file-scope helpers.

**What this changes.** The concentration is in the sample import, staging
cleanup, render and cook paths — the storage and provider seams — not in the
input validators. Those are Tier B by nature: reaching them means making a
filesystem or provider operation fail at a chosen point. Tier A remains worth
doing (it is cheap, and its contracts are real), but it will not carry the
package to 90% on its own, and the plan's task ordering should not assume it
does. Task 2's throw-injection hook and Task 3's fault matrix are now the
load-bearing work.

## Global Constraints

- Execute on `feat/facade-coverage-raise` in its own worktree. Never on
  `main`. (This plan document itself lands via its own docs branch.)
- Every added test asserts the failure's observable contract — error code,
  public message, envelope/details shape — not merely that lines ran.
- The fault hook must be compile-time gated exactly like project-io's: zero
  code in non-testing configurations, no runtime cost, never reachable from
  a shipped Host.
- Do not touch `tests/quality/core-coverage-thresholds.json` until Task 4,
  and then only upward, citing the sustained measured level, per the policy
  rule that floors may rise after sustained behavioral coverage lands.
- Tier C lines are out of scope; do not chase them and do not mark them
  excluded in tooling.
- Every Task is one reviewable Conventional Commit. Before every commit:
  verify the branch is not `main`; run the Task-specific verification and
  `scripts/architecture-portal.sh check`; stage only declared files; inspect
  `git diff --cached --name-status` and `git diff --cached --check`; after
  committing inspect `git show --name-status --oneline HEAD`.
- Local commits only; push, PR, merge and later transitions each need
  separate explicit authorization.

## Tasks

### Task 1 — Tier A: behavioral tests for reachable failure contracts

- [ ] `validate_initial_pattern` rejection matrix in the facade component
      tests.
- [ ] Assembly loader rejection cases across all 13 validators.
- [ ] Table-driven error envelope mapping tests over the ErrorCode enum.
- [ ] C ABI boundary rejections in the existing C API test.
- [ ] Session-limit, corrupted-cache, and TriggerMode cold-branch cases.
- [ ] Re-measure with `scripts/core-coverage.sh check`; record the new facade
      number in the measurement record.

**Partially done 2026-08-18** (`3a9aee3a`): the initial-pattern rejection
matrix and the trigger-mode round trip landed, both mutation-verified. The
remaining Tier A items are deferred behind Task 3, since the corrected
attribution shows the volume is in the storage seams, not the validators.

**Verification:** `scripts/core.sh test dev fast` plus the facade component
tier green; coverage measured ≥88% lines locally; every new test name states
the contract it asserts.

### Task 2 — Tier B, part 1: the throw-injection hook and the 24 catch-alls

- [x] Add a facade testing hook mirroring project-io's pattern
      (compile-gated, `FaultPoint`-style), able to throw inside an API entry.
- [x] Parameterized test walking every public API entry, asserting each
      catch-all converts the throw into the documented
      `internal_error` envelope instead of propagating.
- [x] Re-measure; expected to cross 90% lines.

**Done 2026-08-18** (`28958adb`). All 22 entries carry the hook; the test
walks every one and asserts the typed and JSON envelope contracts, ending by
proving the hook disarmed itself. 84.18% → 85.60% lines. Mutation-verified.

The symbol-absence check was dropped with the compile gate: this hook follows
the facade's own unconditional one-shot precedent rather than project-io's
gated scheme, so there is no gate to prove. The cost is one atomic exchange
per public API call on non-realtime control paths.

### Task 3 — Tier B, part 2: render scratch/staging fault matrix

- [ ] Fault points at the render temp/scratch/staging filesystem seams.
- [ ] A fault-matrix test in the style of
      `tests/core/project_io/fault_matrix_test.cpp`, asserting each failure's
      error code and message.
- [ ] Re-measure lines and branches; record both.

**Verification:** as Task 2; branches expected materially above 70%.

### Task 4 — Ratchet the floor up and close the ledger

- [ ] After the coverage level has held across the PR's own `core-coverage`
      lane and a `main` run, raise
      `packages/application-facade/` floors in
      `tests/quality/core-coverage-thresholds.json` to hold the new measured
      level with a small explicit margin, and update the enforced-ratchet
      table in `docs/quality/core-test-policy.md` in the same commit.
- [ ] Close C1 in `docs/quality/2026-08-17-machine-task-todo.md` and triage
      C1 in `docs/quality/2026-08-16-outstanding-work-before-stage9.md`:
      invalidated as filed by the 2026-08-18 measurement, superseded by this
      plan's coverage raise.

**Verification:** `scripts/core-coverage.sh check` green at the new floors
twice locally and on the PR lane; `scripts/architecture-portal.sh check`.

## Version Management

**Version impact: none.**

> **Corrected 2026-08-18 during Task 2.** This section previously declared a
> SemVer patch bump for `application-facade`. That was written before the
> precedent was checked and is wrong: commit `7b6f00c0`
> ("test(project-io): inject persistence publish faults") added
> `packages/project-io/src/testing_hooks.hpp` and reworked two module sources
> without touching `packages/project-io/module.json`. Private testing hooks
> under `src/` are not part of a Module's API, so they carry no version.
>
> The attempted bump also showed why this matters: moving
> `application-facade` 1.4.0 → 1.4.1 required synchronised edits in
> `web-runtime-platform/module.json`, `products/lmdj/assembly.json`,
> `products/lmdj/src/compiled_assembly.cpp`, five literals in
> `tests/build/version_test.py`, and a regenerated `assembly.lock.json` — a
> live demonstration of triage item B3, and pure cost for a change that needs
> no version at all.

Pure test additions under `tests/`, private hooks under a Module's `src/`, and
threshold/policy edits are unversioned. No Contract, Product Build, or
Assembly identity changes; no Build is allocated by this plan.

## Documentation impact

**Documentation impact: none.** No portal route states the facade floor or
test inventory; the canonical coverage policy lives in
`docs/quality/core-test-policy.md` and is updated in the same Task that moves
the floor. Run `scripts/architecture-portal.sh check` before every commit.

## Out of scope

- Tier C lines, coverage-exclusion annotations, or any tolerance in
  `coverage_gate.py`.
- Any floor change before the tests that justify it have landed and held.
- Other packages' floors (the same method applies later if wanted; audio-
  runtime and project-io have their own gaps and their own plans).
- F6 (render-path amplitude ramp) — realtime code, separate decision.
