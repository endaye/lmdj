# LMDJ Web Runtime Hardening Implementation Plan

**Goal:** Close the four defense-in-depth gaps found by the 2026-08-11 Stage 6
design-and-code review: an unbounded terminal quiescence wait in the Wasm
AudioWorklet, lost Web storage error distinction, an unguarded `append_durable`
platform primitive, and a silently ignored unknown-response protocol path.

**Architecture:** Every change strengthens an existing failure boundary without
adding behavior. The Audio Runtime terminal wait becomes bounded and typed; the
Web storage platform reports the same typed `storage_condition` details the
JavaScript layer already distinguishes; the OPFS platform enforces the writer
lease on all three mutation primitives instead of two; the private Host
transport fails closed on a response it cannot correlate. No Contract, Facade
operation, Project Truth, or Host protocol envelope shape changes.

Review provenance: findings 1–4 of the Stage 6 review recorded against
`main` revision `38a8c13` on 2026-08-11, reviewing
`docs/superpowers/specs/2026-08-03-lmdj-formal-web-runtime-host-design.md`
and the merged Stage 6/7 implementation. The two documentation-drift findings
from the same review (the `restart-required` terminal state and the actual
OPFS storage topology never being written back into the Stage 6 design) are
explicitly out of scope here and need a separate docs Task.

## Global Constraints

- Work happens on `fix/web-runtime-hardening` in an isolated worktree; `main`
  stays deployable.
- Each Task is one reviewable Conventional Commit with its declared files only.
- No new Facade operation, C ABI symbol, Contract, or protocol operation is
  added. `lmdj.patch.v1` and `lmdj.materials.v1` remain retired.
- Task 1 touches concurrent Audio Runtime code, so the `stress` tier and the
  TSan lane must run in addition to `full`.
- Provider failure stays in Attempt state; nothing here writes Project Truth.
- This plan settles no open product-level Contract or concurrency question.

## Tasks

### Task 1: Bound the terminal quiescence wait in the Wasm AudioWorklet

`RealtimeAudioWorklet::await_quiescent`
(`packages/audio-runtime/src/web/realtime_audio_worklet.cpp:415-426`) latches
`quiescence_timeout` after the caller deadline, then enters a
`while (in_flight)` loop whose `emscripten_futex_wait` uses an infinite
timeout. If the Worklet thread dies mid-render, `in_flight` never clears and
the Control Worker blocks forever. The browser-main watchdogs keep the Host
from hanging externally, but §13.2 of the Stage 6 design requires that the
Host must not hang indefinitely, and the Control Worker currently can.

- Add a failing native test first. Under `LMDJ_WEB_AUDIO_CONFORMANCE`, add a
  test hook that marks the callback in-flight without a live render thread,
  then prove `await_quiescent` returns a typed failure within a bounded wall
  time instead of blocking.
- Replace the infinite terminal wait with a bounded wait derived from the
  caller's `timeout_ms` (an equal second bound, never infinite). On expiry
  with `in_flight` still true, return the existing internal-error shape with a
  distinct message so callers and evidence can tell "terminal but quiescent"
  from "terminal and possibly still rendering".
- The render callback, gate protocol, memory ordering, and the successful
  quiescence paths do not change. The failure keeps latching
  `quiescence_timeout` exactly once.
- Verify: `scripts/core.sh test dev full`, `scripts/core.sh test tsan full`,
  `scripts/core.sh test release stress`, and the existing
  `tests/platform/web/audio` Chromium specs via
  `scripts/web-runtime-host.sh proof` in Task 6.

Files: `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`,
`packages/audio-runtime/include/lmdj/audio/web/realtime_audio_worklet.hpp`,
native audio worklet test source.

### Task 2: Preserve typed Web storage conditions across the C++ boundary

`web_error` (`packages/project-io/src/web/storage_platform.cpp:42-56`) only
attaches `storage_condition` details for busy (-3), already-exists (-4), and
atomic-publish-unsupported (-8). The JavaScript layer already distinguishes
`QuotaExceededError` (-6), `InvalidStateError` (-5), and
`NoModificationAllowedError` (-7), but those collapse into an undifferentiated
`io_error`. §13.2 requires quota and flush failures to surface as typed
persistence failures; today the type survives but the condition is lost.

- Add failing Web conformance cases first: a fault-injected quota failure and
  an invalid-state failure must surface `storage_condition` details through
  the production bridge, using the existing `tests/platform/web/project_io`
  fault harness.
- Add `kStorageConditionQuotaExceeded` and `kStorageConditionInvalidState`
  alongside the existing constants in the storage platform header, map
  -6 and -5 in `web_error`, and keep -7 folding into the existing busy
  semantics where the writer-lease path already converts it.
- Native platform behavior is unchanged; the constants are shared so a later
  native mapping can reuse them.
- Verify: `scripts/core.sh test dev fast` for the header change, then the Web
  project I/O conformance suite via `scripts/web-runtime-host.sh proof` in
  Task 6.

Files: `packages/project-io/include/lmdj/project_io/storage_platform.hpp`,
`packages/project-io/src/web/storage_platform.cpp`,
`tests/platform/web/project_io/project_io_web_conformance.spec.mjs`,
`tests/platform/web/project_io/project_io_web_faults.mjs`.

### Task 3: Enforce the writer lease on `append_durable`

`replaceComplete` and `createImmutable` both pass through
`createIntent → activeLease`, so a mutation without an acquired writer lease
fails closed. `appendDurable`
(`packages/project-io/src/web/library_opfs_storage.js:802-827`) opens the
file directly and never consults the lease table. Common `TakeJournal` code
always holds the lease today, so this is not an exploitable hole, but the
three mutation primitives must present one uniform obligation: no lease, no
mutation.

- Add a failing Web conformance case first: calling the append primitive for
  a path with no acquired writer lease must fail with the typed busy/invalid
  condition and must not change file length or content.
- Make `appendDurable` resolve `activeLease(destination)` exactly like the
  other two mutation primitives before opening the file, and keep its
  truncate-append-single-flush sequence unchanged under a held lease.
- The clean-prefix, torn-tail, arbitrary-binary, oversized-prefix, and
  concurrent-append conformance cases must keep passing unchanged.
- Verify: Web project I/O conformance suite via
  `scripts/web-runtime-host.sh proof` in Task 6.

Files: `packages/project-io/src/web/library_opfs_storage.js`,
`tests/platform/web/project_io/project_io_web_conformance.spec.mjs`.

### Task 4: Fail closed on uncorrelatable Host protocol responses

`createProtocolTransport().receive`
(`packages/web-runtime-platform/web/protocol.mjs:423-425`) silently returns
`false` for a response whose `request_id` matches no pending entry. On a
same-build private transport an unknown or duplicate response is a protocol
violation, and §11.2 already demands `HOST_PROTOCOL_MISMATCH` for the
equivalent outcome-path cases. Silence hides a duplicated or replayed
response instead of surfacing it.

- Add failing transport tests first: a response with an unknown `request_id`,
  and a second response for an already-settled request, must each terminate
  the transport with `HOST_PROTOCOL_MISMATCH` and reject all remaining
  pending requests through the existing `failClosed` path.
- Change `receive` to fail closed instead of returning `false` when no
  pending entry matches. Responses arriving after the transport is already
  terminated keep returning `false`; termination stays once-only, so the
  post-timeout and post-close paths do not double-fail.
- Audit the runtime session and diagnostic client for any caller that relies
  on the silent-ignore behavior; the Stage 6/7 sessions correlate strictly by
  pending id, so none is expected.
- Verify: `node --test` for
  `packages/web-runtime-platform/test/protocol.test.mjs` and
  `runtime_session.test.mjs`, then the packaged browser journeys in Task 6.

Files: `packages/web-runtime-platform/web/protocol.mjs`,
`packages/web-runtime-platform/test/protocol.test.mjs`.

### Task 5: Integrate versions, Assembly, and Portal current truth

- Apply the exact version movements in `## Version Management` to every
  module manifest, Product `version.json`, `assembly.json`, and README
  identity text, then regenerate `products/lmdj/assembly.lock.json` through
  `scripts/version.py lock`.
- Update the affected Portal current pages: the Web Runtime platform and Host
  failure semantics (bounded terminal quiescence, uniform lease obligation,
  fail-closed unknown responses, typed quota condition) and the
  version-and-release table.
- Run `scripts/architecture-portal.sh check`; identities come from the active
  manifests, never hand-entered.
- Verify: `python3 scripts/version.py verify --version-file
  products/lmdj/version.json` and the Portal check.

Files: module manifests listed in `## Version Management`, product identity
files, `apps/architecture-portal/docs/**` current pages and diagram sources.

### Task 6: Final Proof, snapshot, and acceptance evidence

- Run the full gate set on the completed branch: `scripts/core.sh proof`,
  `scripts/core.sh test asan full`, `scripts/core.sh test tsan full`,
  `scripts/core.sh test release stress`, `scripts/web-runtime-host.sh proof`,
  `scripts/creator-web.sh proof`, `bash tests/build/test_active_tree.sh`, and
  `scripts/architecture-portal.sh check`.
- Freeze the immutable `1.0.16.6 · canary` Portal snapshot with
  `scripts/architecture-portal.sh version 1.0.16.6 canary` only from a clean
  committed source boundary.
- Record automated acceptance evidence in
  `docs/quality/2026-08-11-web-runtime-hardening-acceptance.md`, keeping the
  five deferred physical rows accurately deferred and claiming no push, PR,
  merge, tag, Release, deployment, or Channel promotion.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

| Identity | Baseline | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.16.5` | `1.0.16.6` | hardening-only canary candidate |
| Audio Runtime | `0.4.0` | `0.4.1` | bounded terminal quiescence wait, compatible |
| Project I/O | `0.5.0` | `0.5.1` | typed storage conditions and uniform lease enforcement, compatible |
| Application Facade | `1.3.1` | `1.3.2` | exact `project-io`/`audio-runtime` dependency update only |
| Web Runtime Platform | `0.1.2` | `0.1.3` | fail-closed unknown-response transport plus exact dependency updates |
| Core CLI | `1.0.7` | `1.0.8` | exact Facade dependency update only |
| Core MCP | `1.1.4` | `1.1.5` | exact Facade dependency update only |
| Native Test Host | `1.0.5` | `1.0.6` | exact Facade/Audio dependency updates only |
| Web Runtime Host | `1.2.2` | `1.2.3` | exact Platform dependency update only |
| Creator Web | `1.0.2` | `1.0.3` | exact Platform dependency update only |
| Contracts | current | unchanged | no envelope, schema, or wire shape changes |
| Providers, Models | current | unchanged | no Provider behavior change |

- Compatibility: every change tightens a failure path. Successful operations,
  Project Truth, `lmdj.project.v1`, `lmdj.storage.intent.v1`, protocol
  envelope shapes, and all existing passing journeys are unchanged. The new
  behaviors are: a bounded typed failure where the Control Worker previously
  blocked, `storage_condition` details where details were previously empty, a
  typed failure where an unleased append previously succeeded at the platform
  layer, and transport termination where an uncorrelatable response was
  previously ignored.
- Coordination: the in-flight `feat/stage8-sample-editor` branch targets
  Product Build `1.0.17.0`. Whichever merges second rebases and re-verifies;
  if Stage 8 merges first, this candidate re-allocates to the next free
  `1.0.17.x` patch identity and this table is corrected before the PR.
- Tag condition: only after squash merge to `main`, full CI, merged-main
  Proof, and exact identity verification may the Integration Owner create
  signed annotated tag `lmdj-v1.0.16.6`. This plan authorizes neither push,
  PR, merge, tag, Release, deployment, publication, nor Channel promotion.
- Rollback reuses the immutable prior Product tag; tags are never moved.

## Documentation Impact

Documentation impact: required.

- Affected portal routes: `platform/web-runtime` (bounded terminal
  quiescence, uniform lease obligation, typed storage conditions),
  `hosts/web-runtime` (fail-closed unknown-response transport),
  `operations/version-and-release` (new Product Build and module identities),
  `operations/testing-and-proof` (new conformance cases).
- This plan changes the Product Build and Assembly, so `Documentation impact:
  none` is not permitted; the immutable `1.0.16.6 · canary` snapshot in
  Task 6 is mandatory before any team-testing or release allocation.
- The Stage 6 design errata (the `restart-required` terminal state and the
  actual OPFS storage topology) remain a separate documentation Task and are
  not silently folded into this plan.

## Pull Request and Completion Boundary

After Task 6, inspect every commit and staged file list, run
`git diff --cached --check` per commit, and request code review before any
push authorization. A green local Proof does not authorize push; a green
pushed PR does not authorize merge; a squash merge does not authorize tag,
Release, deployment, or Channel promotion. The plan is complete only when the
approved PR is squash-merged, required checks pass on current code, and merged
`main` re-runs Core, Web Runtime Host, Creator Web, and Portal Proof.
