# Project I/O Web stack: fewer ProjectState copies and a measured headroom gate (#1720)

## Outcome and authority

Close [#1720](https://github.com/endaye/lmdj/issues/1720). #1717 raised the Web stack from 128 KiB to 256 KiB after the `5.1.0` parity keys grew wasm32 `ProjectState` from 4 424 to 6 472 bytes, and Project I/O's deep paths overflowed. This Task:

- removes the copies that made the stack scale with every Pad field;
- sets the budget from a measured high-water mark instead of the last overflow;
- adds a gate that catches the next growth long before the product traps.

Baseline: `52747713` on an isolated `fix/1720-project-state-stack-copies` worktree. The Task includes a verified commit, push, current-head review and squash merge. It does not release, and it does not clean worktrees.

Owner decision, 2026-10-01: keep `STACK_SIZE` at 256 KiB and fail any Project I/O Web conformance action whose high-water mark exceeds half the stack.

## Behavior

No public behaviour, persisted format, error, or error-order change. Only where large values live changes:

- **Measurement.** `project_io_web_test` paints the unused stack below `main()` once, keeping clear of `STACK_OVERFLOW_CHECK`'s cookie words. When an action finishes, it reports `stack: {size_bytes, high_water_bytes}` beside `result`. The spec logs every report.
- **Gate.** For every `project_io_web_test.html` action, the spec requires a report and requires `high_water_bytes <= size_bytes / 2`, and fails with `why` and `remedy`. It catches a grown Pad or Project field, or a new by-value `ProjectState` local on a deep frame, while about half the budget is still free. That half covers the Host frames above Project I/O, which this binary does not include.
- **`foundation::Result::success`** takes `T&&` and `const T&`, and constructs the variant in place. A by-value `T` used to leave a full copy in the frame of every function returning `Result<T>`.
- **`foundation::describe_artifact`** reads through a heap buffer, not a 64 KiB stack array.
- **Project I/O:**
  - `load_project` returns `std::unique_ptr<LoadedProject>`, built in place, and `commit_loaded` takes ownership of it. No caller keeps a `LoadedProject` in its frame.
  - `read_checkpoint`, `replay_transaction` and `checkpoint_matches_replay` are `noinline` phases, so each checkpoint, replayed transaction and comparison lives only in its own short frame.
  - Replay moves the applied state instead of copying it.
  - `parse_project` fills the created state in place.
  - `commit_loaded` commits the applied value in place, and promotes and re-validates it in `promote_for_persist`.

Measured with the Web build flags. Frames come from `em++ -O3 -fstack-usage`; high-water marks from the probe at 256 KiB.

| Measure | Before (`52747713`) | After |
| --- | ---: | ---: |
| Deepest action high-water (`mutate_sample_cache`) | 175 624 | 98 208 |
| `admission` high-water | 157 848 | 83 136 |
| `load_project` frame | 40 944 | 848 |
| `commit_loaded` frame | 28 448 | 8 992 |
| `import_assign_sample_bytes` frame | 36 256 | < 13 400 |
| `execute_performance_rebase` frame | 41 504 | 14 992 |
| `foundation::describe_artifact` frame | 66 272 | 736 |

## Declared files

- `packages/foundation/include/lmdj/foundation/error.hpp`
- `packages/foundation/src/artifact.cpp`
- `packages/project-io/src/project_store.cpp`
- `packages/project-io/CMakeLists.txt` (comment only)
- `tests/platform/web/project_io/project_io_web_test.cpp`
- `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `.agents/pitfalls/web-project-io-stack-scales-with-project-state.md` (absorbed by the gate)
- `.agents/pitfalls/asan-macos-fork-child-stack-depot-boundary.md` (new; escalated to #1752)
- `docs/plans/2026-10-01-project-io-web-stack.md`

## Verification

- `scripts/core.sh build dev` and `test dev full`. Project I/O, Facade, Domain and every consumer of `Result` run unchanged.
- `scripts/web-toolchain-conformance.sh proof` with the gate active passes, and its reports give the high-water marks above.
- Gate mutation proof: lowering the gate fraction to `0.3` made 9 conformance tests fail with the `why … remedy` message, and restoring `0.5` passes. The baseline high-water mark (175 624 B, above 131 072 B) is the failure the gate would have reported on `52747713`.
- All batch-only lanes run locally on the committed head.
- `core_macos` hit a test-harness hazard. With `TMPDIR=/private/tmp/lmdjt`, the fork-based crash tests `project_io.candidate_adoption` and `facade.candidate_store_recovery` lost their children to SIGKILL inside `fork()`.
  - Cause: the heap allocation sites added here moved those binaries' ASan stack depot within a few ids of a growth boundary. libSystem's fork child handlers then allocate into a lock the child cannot own.
  - Rates under the same `TMPDIR`: 0/16 on `main`, 11/16 on this head.
  - Product code does not fork. The owner chose to run `core_macos` under the macOS default `TMPDIR`, which `ci.yml` leaves unset as well, and to fix the hazard in #1752 (pitfall `asan-macos-fork-child-stack-depot-boundary`).

## Version Management

Version impact: none in this Pull Request.

Reason: under the owed-version convention (#1550, #1717, #1746), Assembly pins keep Module identity changes out of a fix Pull Request. The next coordinated settle owes these PATCHes:

| Module | Owed | Why |
| --- | --- | --- |
| `foundation` | `0.4.0` → `0.4.1` | `Result::success` signature (source-compatible) and `describe_artifact` buffer; no behaviour change |
| `project-io` | `6.0.0` → `6.0.1` | Internal stack layout; no API, format or behaviour change |

Every exact-dependency consumer takes a PATCH. No Contract, Product Build or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: `/core/modules/project-io`.

Reason: the page states the Web stack budget, what #1720 changed and the gate that now guards it.
