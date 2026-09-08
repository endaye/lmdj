# LMDJ Web Runtime Hardening Implementation Plan

**Goal:** Close the four defense-in-depth gaps found by the 2026-08-11 Stage 6
design-and-code review: an unbounded terminal quiescence wait in the Wasm
AudioWorklet, lost Web storage error distinction, an unguarded `append_durable`
platform primitive, and a silently ignored unknown-response protocol path. The
executed supplemental Task 4A is a docs-only errata that reconciles the Stage 6
design authority with the same accepted review; it does not add runtime
behavior.

**Architecture:** Every change strengthens an existing failure boundary without
adding behavior. The Audio Runtime terminal wait becomes bounded and typed; the
Web storage platform reports the same typed `storage_condition` details the
JavaScript layer already distinguishes; the OPFS platform enforces the writer
lease on all three mutation primitives instead of two; the private Host
transport fails closed on a response it cannot correlate. No Contract, Facade
operation, Project Truth, or Host protocol envelope shape changes.

Review provenance: findings 1–4 of the Stage 6 review recorded against
`main` revision `38a8c13` on 2026-08-11, reviewing
`docs/design/2026-08-03-lmdj-formal-web-runtime-host-design.md`
and the merged Stage 6/7 implementation. The accepted review also recorded
design-authority drift D1–D3: the `restart-required` terminal state, the actual
OPFS storage topology, and the terminal-owner grace. Task 4A resolves that
documentation drift, plus its two editorial findings, without changing code,
version identities, generated Portal facts, or immutable versioned snapshots.

Final branch review correction: Tasks 1–6 below are retained as executed
history, but the review proved that Task 4 changed only the standalone
`createProtocolTransport()` helper. The production Runtime Session never
instantiates that helper. Browser Main instead owns its transport in
`packages/web-runtime-platform/src/web-runtime-pre.js`, whose production
`pollTransport()` still silently ignored a response with a string
`request_id` absent from `pendingRequests`. Tasks 7–9 correct that production
path and supersede `1.0.16.6` as a releasable candidate without rewriting any
Task 6 evidence or immutable snapshot.

Final corrective review: Tasks 1–9 remain immutable executed history, but the
review found two remaining evidence gaps. First, the worker-global OPFS lease
lookup was path-aware but owner-unaware for the three file mutators, allowing a
distinct same-page `ProjectStoragePlatform` to reuse another platform's lease
after its own acquisition correctly returned `PROJECT_BUSY`. Second, the real
Browser Main mismatch cases did not actually hold another production request
pending while `failClosed` rejected and cleared `pendingRequests`. Tasks 10,
10A, 11, and 12 close those gaps without rewriting either existing schema-2
snapshot. Product Builds `1.0.16.6` and `1.0.16.7` are immutable, unshipped,
abandoned canary candidates and are never reused, tagged, released, deployed,
published, or promoted.

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

### Task 4A: Reconcile the Stage 6 design authority with the accepted review

Executed as a docs-only errata after Tasks 1–4. Correct the Stage 6 formal
design to record D1–D3 as current implementation truth: `restart-required` is
a first-class terminal Host state; WasmFS/OPFS is an availability/mount probe
while production Project I/O uses Asyncify `lmdj_opfs_*` JavaScript library
imports for semantic storage obligations; and terminal-owner native completion
has a 5,000 ms grace before force termination, independent of the 1,000 ms
publication-settlement watchdog. Also correct the duplicate English `and` in
the Host-local error-code list and link the conceptual feature list to the
authoritative exact Emscripten lock, including its `-sPROXY_TO_PTHREAD` and
`-sASYNCIFY=1` entries.

- Scope is only the Stage 6 design authority and this executed plan. It changes
  no runtime code, version identity, generated Portal fact, or immutable
  versioned snapshot, and it claims no new capability or evidence.
- F5/F6 remain separately triaged cleanup/backlog and are not implemented or
  otherwise folded into this docs Task.
- Verify the corrected design against the current state machine, Project I/O
  implementation, toolchain lock, and Portal current truth; search it for the
  stale claims; then run `scripts/architecture-portal.sh check` and
  `bash tests/build/test_active_tree.sh`.

Files: `docs/design/2026-08-03-lmdj-formal-web-runtime-host-design.md`,
`docs/plans/2026-08-11-lmdj-web-runtime-hardening.md`.

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
- Historical Task 6 execution froze the immutable `1.0.16.6 · canary` Portal
  snapshot with `scripts/architecture-portal.sh version 1.0.16.6 canary` from
  a clean committed source boundary. Final review later classified that
  unshipped candidate as abandoned; the snapshot remains evidence only.
- Record automated acceptance evidence in
  `docs/quality/2026-08-11-web-runtime-hardening-acceptance.md`, keeping the
  five deferred physical rows accurately deferred and claiming no push, PR,
  merge, tag, Release, deployment, or Channel promotion.

### Task 7: Deliver F4 on the real Browser Main transport

- Add Chromium conformance cases that submit a real native response through
  `_lmdj_web_host_poll` into the production `pollTransport()` branch, covering
  both an unknown request ID and an ID whose first request already settled.
  The conformance-only native-submit seam remains inside the existing
  `LMDJ_WEB_AUDIO_CONFORMANCE` block and is stripped from production packages.
- Each case proves once-only terminal `HOST_PROTOCOL_MISMATCH`, rejection and
  sealing of further requests, no notification delivery, and the existing
  terminal-owner release behavior.
- Make production `pollTransport()` call the existing `failClosed` path and
  return when a string `request_id` has no matching `pendingRequests` entry.
  Preserve known responses, notifications, malformed-message handling,
  deadlines, settlement, polling, and once-only terminal cleanup.
- Retain a production source-boundary assertion so conformance stripping
  cannot leave the packaged Browser Main path able to silently ignore an
  uncorrelatable response.

Files: `packages/web-runtime-platform/src/web-runtime-pre.js`, the focused
browser conformance spec, this plan, and the Web Host source-boundary test.

### Task 8: Propagate corrective identities and Portal current truth

- Apply the corrective `1.0.16.7` allocation in the exact identity and
  dependency files listed below, regenerate the Product Assembly lock, and
  update the affected current Portal routes. Do not modify any path under the
  immutable `1.0.16.6` snapshot.
- Verify the exact Product/Module/Host dependency graph, Assembly lock,
  version policy, Portal current truth, and active-tree boundary before the
  Task commit.

### Task 9: Rerun complete gates, freeze `1.0.16.7 canary`, and update acceptance

- Rerun every complete Task 6 gate against the corrective committed source:
  Core Proof, ASan full, TSan full, release stress, Web Runtime Host Proof,
  Creator Web Proof, active-tree, and Architecture Portal checks.
- From a clean committed boundary, freeze a new immutable
  `1.0.16.7 · canary` Portal snapshot and update acceptance with exact fresh
  evidence. The existing `1.0.16.6` snapshot is never modified.
- Keep the five physical rows deferred unless separately performed, and claim
  no push, PR, merge, tag, Release, deployment, publication, or Channel
  promotion.

### Task 10: Bind all Web file mutations to the owning platform

- Through the real C++/Emscripten/OPFS bridge, hold platform A's writer lease
  and prove distinct same-page platform B receives `PROJECT_BUSY` on
  acquisition and on direct append, replace, and immutable-create mutations.
  Each mutation must fail before target or intent access; existing bytes,
  absent-target state, and storage/publication-intent inventory remain exact.
- Pass `platform_identity_` through production and test private imports for all
  three file mutators. `activeLease(destination, platformIdentity)` returns
  `InvalidStateError` when no lease covers the path and
  `NoModificationAllowedError` for a different owner; each mutation boundary
  maps the latter to the existing `project_busy` condition.
- Preserve successful owner mutation/release, recovery, short-write, flush,
  held-lease, and publication behavior. Version identities move only in Task
  11; no public C ABI, Facade operation, Contract, or Project Truth field is
  added.

### Task 10A: Prove real Browser Main pending rejection and clearing

- In the existing Chromium audio failure spec, queue an untracked native
  `host.status` response through the conformance native-submit seam, then start
  a different normal `transport.send(host.status)` before the production poll.
  The real `_lmdj_web_host_poll -> pollTransport()` missing-pending branch must
  terminate once with `HOST_PROTOCOL_MISMATCH`, reject that pending promise
  with the same terminal error, clear its ID, deliver no notification, seal
  later sends, and release the terminal owner once.
- Prove the case detects a missing production clear/reject loop with a
  controlled temporary mutation, then restore the already-correct production
  implementation. Any read-only pending-ID observation stays in the stripped
  `LMDJ_WEB_AUDIO_CONFORMANCE` surface and is rejected by generated-production
  boundary checks.
- Version impact: none. Production behavior is unchanged; only conformance and
  exact current Portal evidence wording change.

### Task 11: Propagate exact corrective identities and current truth

- Immediately before editing, live-check that Stage 8 remains unmerged and
  Product Build `1.0.16.8` is free of local/remote tag, GitHub Release, Portal
  registry, snapshot, and metadata. Stop before propagation if allocation is
  invalid.
- Apply the exact corrective allocation below to authoritative manifests,
  direct dependencies, Product Assembly and compiled identity, generated
  locks, fixtures, active README text, and all affected mutable current Portal
  routes. Audio Runtime and every unlisted identity remain unchanged. Neither
  prior snapshot may change.
- Current Portal records owner-aware all-mutator enforcement, the exact pending
  rejection evidence, both abandoned candidates, and Task 12 as the remaining
  local Proof/snapshot boundary.

### Task 12: Run corrective Proof and freeze `1.0.16.8 canary`

- From the clean committed Task 11 source boundary, use only the locked
  Emscripten 6.0.5/Node 22.16.0, Python 3.11.15, and git-lfs tools to run full
  Project I/O Chromium/WebKit, Core Proof, fresh ASan and TSan full, release
  stress, Web Runtime Host Proof, Creator Proof, active-tree, and pre-snapshot
  Portal checks. Infrastructure/setup failures are distinct from semantic
  failures; no semantic failure is waived.
- Recheck remote main, Stage 8, clean source, and zero changes under both prior
  snapshots. Only then freeze `1.0.16.8 · canary`, inventory generator output,
  update acceptance and directly required mutable current testing/release
  pages, and run full post-commit Portal/active-tree/provenance audits.
- Acceptance retains exactly five physical rows as `deferred / unverified` and
  separately records that no push, PR, CI, merge, tag, Release, deployment,
  publication, public smoke, or Channel promotion has occurred.

### Task 13: Repair merged-main squash provenance without rewriting `1.0.16.8`

- Merged-main verification found that Task 12's direct-parent source relation
  became a divergent projection after GitHub squash merge: the immutable
  snapshot still byte-matched source `56b726092e05821bb76ac1e458c84764b228efcd`,
  while two legitimate mutable current pages and non-projection evidence were
  also folded into introducing commit `7555cfd40472297e62a90c6a1b08f5ed979d847d`.
- Add RED/GREEN coverage for the real history shape, including a fresh clone
  with no source commit object. Generate a version-specific reverse-delta
  witness and accept it only when a temporary Git index reconstructs the exact
  source tree and raw source commit already authenticated by schema-2
  metadata. Missing, malformed, tampered, incomplete, or identity-mismatched
  witnesses remain fail closed.
- Version impact: none. No Product, Assembly, Module, Host, Provider, Contract,
  or Channel identity changes, and the immutable `1.0.16.8` snapshot is not
  edited. Documentation impact: required for
  `/operations/documentation-governance/` and the canonical Portal governance
  rule; document the authenticated witness boundary in this Task.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

Task 4A version impact: none. It documents behavior already present in the
current implementation; Product, Module, Host, Provider, Contract, and Assembly
identities do not change in this Task.

Task 10A version impact: none. It strengthens only conformance evidence and
corrects current Portal wording for production behavior already implemented.

Task 13 version impact: none. It restores verifiability of the already frozen
`1.0.16.8` source relation after squash without changing Product or component
behavior and without rewriting the snapshot.

The following table records the executed Tasks 1–6 allocation as historical
evidence. The corrective table below owns every future identity action.

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

### Corrective allocation after final branch review

Product Build `1.0.16.6` is an immutable, unshipped, abandoned canary
candidate. It cannot be reused, tagged, released, deployed, published, or
promoted. Its existing versioned Portal snapshot remains immutable and is
never rewritten. Task 7 changes the production behavior; Task 8 performs all
identity, Product Assembly, Assembly lock, and current-Portal propagation;
Task 9 reruns the complete gates and freezes the new immutable candidate.

| Identity | Abandoned candidate | Corrective target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.16.6` | `1.0.16.7` | corrective canary after production-path F4 completion |
| Web Runtime Platform | `0.1.3` | `0.1.4` | production Browser Main unknown-response fail-closed behavior |
| Web Runtime Host | `1.2.3` | `1.2.4` | exact Web Runtime Platform dependency update only |
| Creator Web | `1.0.3` | `1.0.4` | exact Web Runtime Platform dependency update only |
| All other Modules and Hosts | `1.0.16.6` candidate identities | unchanged | no additional implementation or dependency impact |
| Contracts, Providers, Models | `1.0.16.6` candidate identities | unchanged | no Contract, Provider, or Model behavior change |

The earlier `lmdj-v1.0.16.6` tag condition is no longer actionable because
the candidate was abandoned by final review. Any later tag consideration must
use the corrective Product Build and still requires separate authorization
after squash merge, full CI, merged-main Proof, and exact identity verification.

### Corrective allocation after final corrective review

Product Builds `1.0.16.6` and `1.0.16.7` are immutable, unshipped, abandoned
canary candidates. Their existing versioned Portal snapshots, metadata,
sidebars, and registry identities remain read-only historical evidence. Task
10 changes Project I/O behavior, Task 10A strengthens evidence without a
version impact, Task 11 performs all identity/current-truth propagation, and
Task 12 runs the complete gates and freezes the only new candidate.

| Identity | Abandoned baseline | Corrective target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.16.7` | `1.0.16.8` | owner-aware Web mutation correction and exact production evidence |
| Project I/O | `0.5.1` | `0.5.2` | bind all three Web file mutators to the owning platform |
| Application Facade | `1.3.2` | `1.3.3` | exact Project I/O dependency update only |
| Web Runtime Platform | `0.1.4` | `0.1.5` | exact Facade/Project I/O dependency propagation |
| Core CLI | `1.0.8` | `1.0.9` | exact Facade dependency update only |
| Core MCP | `1.1.5` | `1.1.6` | exact Facade dependency update only |
| Native Test Host | `1.0.6` | `1.0.7` | exact Facade dependency update only |
| Web Runtime Host | `1.2.4` | `1.2.5` | exact Web Runtime Platform dependency update only |
| Creator Web | `1.0.4` | `1.0.5` | exact Web Runtime Platform dependency update only |
| Audio Runtime | `0.4.1` | unchanged | no additional Audio behavior or dependency impact |
| All other identities | `1.0.16.7` candidate identities | unchanged | no behavior or direct dependency impact |

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
  signed annotated tag `lmdj-v1.0.16.8`. This plan authorizes neither push,
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
  none` is not permitted; the immutable `1.0.16.7 · canary` snapshot in
  Task 9 is mandatory before any team-testing or release allocation. The
  Task 6 `1.0.16.6 · canary` snapshot is retained only as immutable evidence
  for the abandoned, unshipped candidate and satisfies no future allocation.
- Task 4A corrects Stage 6 design authority only. Current Portal routes are
  updated in Task 5; Task 4A neither changes generated Portal facts nor rewrites
  immutable versioned snapshots.
- Task 7 amends this plan and production-path conformance only. Task 8 updates
  the affected current Portal routes and identities. Task 9 creates the new
  immutable `1.0.16.7 · canary` snapshot; the `1.0.16.6` snapshot remains
  untouched.
- Task 10 updates `platform/web-runtime` and `operations/testing-and-proof` for
  owner-aware file-mutation semantics. Task 10A corrects the production
  pending-rejection evidence on `hosts/web-runtime` and
  `operations/testing-and-proof`. Task 11 updates every affected mutable
  current identity route. Task 12 creates the mandatory immutable
  `1.0.16.8 · canary` snapshot and records completed local evidence; both prior
  snapshot families remain untouched.
- Task 13 updates `/operations/documentation-governance/` and canonical
  governance with the authenticated squash-witness rule. It adds only external
  provenance evidence for `1.0.16.8`; all immutable `.6`, `.7`, and `.8`
  snapshot paths remain unchanged.

## Pull Request and Completion Boundary

After Task 13, inspect every commit and staged file list, run
`git diff --cached --check` per commit, and request code review before any
push authorization. A green local Proof does not authorize push; a green
pushed PR does not authorize merge; a squash merge does not authorize tag,
Release, deployment, or Channel promotion. The plan is complete only when the
approved PR is squash-merged, required checks pass on current code, and merged
`main` re-runs Core, Web Runtime Host, Creator Web, and Portal Proof.
