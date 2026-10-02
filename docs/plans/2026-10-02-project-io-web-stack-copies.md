# Project I/O Web stack, second pass: keep ProjectState copies off deep frames (#1771)

## Outcome and authority

Close [#1771](https://github.com/endaye/lmdj/issues/1771). #1667's Core half adds the `5.2.0` tone parity fields to `PadPlayback`, which grows wasm32 `ProjectState` from 6 472 to 10 568 bytes. The 50% Web stack gate from #1720 then fails: `mutate_sample_cache` reaches 151 472 of the 262 144-byte stack. Each action has 9–13 `ProjectState`-sized values live at its deepest point.

Owner decision, 2026-10-02: clean up the copies first, in this prerequisite PR. #1667's fields then land with the planned `int32` types. The 256 KiB stack and the 50% gate are unchanged.

Baseline: `eee7f371`, on an isolated `fix/1771-project-state-stack-copies` worktree. The Task includes a verified commit, push, current-head review and squash merge. It does not release, and it does not clean worktrees.

## Behavior

No public behaviour, persisted format, error or error-order change. Only where large values live changes:

- **`foundation::Result::emplace_success(args...)`** constructs `T` in place from constructor or aggregate arguments. A composite such as an applied command, which holds a `ProjectState`, is then never a separate temporary in the frame that returns it.
- **Authoring Domain:**
  - `applied()` takes the working state by `&&` and returns the `Result` built in place. Each command handler now holds only its working copy. It used to hold three: the working copy, `applied()`'s by-value parameter, and the `AppliedCommand` temporary.
  - The receipt path builds its result in place.
  - `create_project` builds the new Project in its caller's return slot.
- **Project I/O:**
  - `parse_project` returns the parsed Project on the heap. `create_heap_project`, a short `noinline` frame, creates it, so neither `parse_project` nor `read_checkpoint` holds a `ProjectState`.
  - `promote_for_persist` canonicalizes the committed state in place and compares it with a heap re-parse.
  - `import_artifact_with_identity` builds its execution result in place.
- **Conformance harness:** `mutate_sample_cache` in `project_io_web_test.cpp` held six `ProjectState`-sized values in its own frame, two per `value(...)` of a `ProjectState` result. That frame was 41 792 of the action's 98 208 bytes on `main`, the largest single share and not Project I/O's demand. The load and each import now run in their own `noinline` frames, and the later-checked results live on the heap. Every assertion and message is unchanged.

Measured with the Web build flags. Frames come from `em++ -O3 -fstack-usage` on `main` sources; high-water marks come from the conformance probe in Chromium.

| Frame | Before (`eee7f371`) | After |
| --- | ---: | ---: |
| `domain::apply` (per command) | 19 904 | 6 992 |
| `parse_project` | 9 296 | 2 848 |
| `read_checkpoint` | 6 624 | 176 |
| `create_project` | 6 608 | 176 |
| `promote_for_persist` | 6 512 | 64 |
| `import_artifact_with_identity` | 16 016 | 9 232 |

| Deepest action high-water | `main` (`eee7f371`) | This PR | This PR + #1667 fields |
| --- | ---: | ---: | ---: |
| `mutate_sample_cache` | 98 208 | 59 496 | 88 168 |
| deepest of all actions | 98 208 (`mutate_sample_cache`) | 71 972 (`history_roundtrip`, 27%) | 112 932 (`history_roundtrip`, 43%) |

## Declared files

- `packages/foundation/include/lmdj/foundation/error.hpp`
- `packages/authoring-domain/src/command_handler.cpp`
- `packages/authoring-domain/src/project.cpp`
- `packages/project-io/src/project_store.cpp`
- `tests/platform/web/project_io/project_io_web_test.cpp`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `.agents/pitfalls/web-project-io-stack-scales-with-project-state.md` (this occurrence; the gate caught it)
- `docs/plans/2026-10-02-project-io-web-stack-copies.md`

## Verification

- `scripts/core.sh build dev` and `test dev full`.
- `scripts/web-toolchain-conformance.sh proof`, with the gate unchanged at 50%.
- With #1667's Domain and Project I/O commits (`6ce4d9d9`, `1d38b06d`) applied on top, the Chromium Project I/O conformance passes 42/42, and every action is at or under 45% of the stack (the #1771 acceptance).
- All batch-only lanes run locally on the committed head.

## Version Management

Version impact: none in this Pull Request.

Reason: under the owed-version convention (#1550, #1717, #1746), Assembly pins keep Module identity changes out of a fix Pull Request. The next coordinated settle owes:

| Module | Owed | Why |
| --- | --- | --- |
| `foundation` | `0.4.0` → `0.5.0` | `Result::emplace_success` is a new public member. This supersedes #1720's owed `0.4.1`. |
| `authoring-domain` | PATCH | Internal result construction; no API or behaviour change |
| `project-io` | PATCH | Internal stack layout; no API, format or behaviour change |

Every exact-dependency consumer takes a PATCH. No Contract, Product Build or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: `/core/modules/project-io`.

Reason: the page states the Web stack budget, what #1720 and #1771 changed, and the measured high-water mark.
