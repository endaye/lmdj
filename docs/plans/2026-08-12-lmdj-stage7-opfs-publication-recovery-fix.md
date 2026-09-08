# LMDJ Stage 7 OPFS Publication and Recovery Fix Implementation Plan

**Goal:** Close the two Web OPFS recovery defects found by the 2026-08-12
Stage 7 review: a failed directory publication can delete its own pending
publication intent while leaving a half-built destination behind, and a torn
`lmdj.storage.intent.v1` record locks a Project's writer lease permanently with
no automatic recovery.

**Architecture:** Both changes correct *cleanup and classification order* inside
`packages/project-io/src/web/library_opfs_storage.js`. No Contract record shape,
Facade operation, C ABI symbol, Host protocol envelope, or Project Truth
semantic changes. No C++ product source changes — the fix is confined to the
Emscripten `--js-library` storage implementation plus test harness actions. The
design invariant being restored is the one stated in the Stage 7 design §7.3:
the Project list may observe only the prior set or a complete new Project, and
recovery metadata must never become the reason a Project is unreachable.

Review provenance: findings F1 and F2 of
`docs/quality/2026-08-12-stage7-creator-editor-review.md`, recorded against
`main` revision `0b5d2d6`, reviewing
`docs/design/2026-08-07-lmdj-stage7-creator-editor-design.md` §7.3
and §11. The other findings from that review are out of scope here: the missing
manual canary and merged-main Proof evidence (T1, G1, G2) is an evidence Task,
the Creator UI findings (F3, F6) are a Creator Host Task, and the
documentation drift (D1–D3, G3, G4) is a docs Task. None of them is silently
folded into this plan.

## Branch Base and Coordination

This plan is **stacked on `fix/web-runtime-hardening`**, not on `main`.

`docs/plans/2026-08-11-lmdj-web-runtime-hardening.md` is fully
implemented on that branch (head `2ce4c8a`) and is awaiting merge. It has
already allocated and frozen Product Builds `1.0.16.6`, `1.0.16.7`, and
`1.0.16.8` with immutable Portal snapshots and a recorded acceptance document,
and it modifies the same file this plan changes. Folding these Tasks into that
plan is therefore **not** an option: it would invalidate frozen acceptance
evidence for a candidate that is already complete.

Stacking follows the precedent Stage 7 used for its `1.0.15.0` dependency:
develop on the overlay branch, but do not merge before the dependency merges.

- This branch must not be merged to `main` before `fix/web-runtime-hardening`.
- If the hardening candidate changes before it merges, this branch rebases onto
  its new head and re-verifies.
- F1 and F2 were confirmed present and unchanged at `2ce4c8a`
  (`library_opfs_storage.js:564-572` and `:644-648`), so the fixes apply to the
  current file state without conflict.

## Global Constraints

- Work happens on `fix/opfs-publication-recovery` in an isolated worktree;
  `main` stays deployable.
- Each Task is one reviewable Conventional Commit with its declared files only.
- No new Facade operation, C ABI symbol, Contract, or protocol operation is
  added. `lmdj.storage.intent.v1` and
  `lmdj.storage.directory-publication.v1` record shapes are unchanged.
  `lmdj.patch.v1` and `lmdj.materials.v1` remain retired.
- Publication intent and storage intent stay Host recovery metadata; neither
  enters Project Truth, Bundle inventory, Creator UI, or privacy-safe reports.
- Every mutation keeps requiring the destination writer lease; no Task weakens
  the no-overwrite collision semantics.
- This plan settles no open product-level Contract or concurrency question.
- Failure classification may only become *more* permissive where the code can
  prove the destination was never mutated. Where that proof does not hold, the
  existing fail-closed behavior is preserved deliberately.

## Tasks

### Task 1: Keep the pending publication intent until destination removal is confirmed — IMPLEMENTED (`a393ed1`)

`publishDirectoryIfAbsent` handled a failed publication by swallowing the
destination removal error and then removing the intent unconditionally. If the
recursive destination removal failed — a quota condition, a transient OPFS
error, or a handle held elsewhere — while the intent removal succeeded, the
result was a half-built destination directory with **no** pending intent
protecting it. `listEntries` only hides a destination while an intent reports
`pending`, so the half-built directory became visible; and
`list_local_projects`
(`packages/project-io/src/project_bundle_transfer.cpp:549-553`) returns failure
on the first directory it cannot summarize, so one such directory made the
entire local Project list unusable. There was no automatic way out, because
`recoverPublicationIntent` is driven by the intent that was just deleted.

The recovery path itself already gets this right: it removes the tree first and
lets a removal error propagate before reaching `removeEntry`, so the intent
survives a failed cleanup. Only the publish catch-block broke the ordering.

Delivered:

- The `committed` short-circuit returns first and keeps its meaning: once the
  `pending → committed` swap has closed, the call returns `0` and never removes
  the destination, even if source or intent cleanup then fails.
- The pending intent is removed **only** after the destination is positively
  confirmed absent via `exists(destinationParts)`, mirroring the positive
  re-check the storage-intent recovery path already performs. If absence cannot
  be confirmed, the `pending` intent stays and the original error propagates.
- A throwing test fault point (`destination_cleanup_failure`, exported as
  `PUBLICATION_CLEANUP_FAULT`) plus a `publish_publication_failure` action make
  a publication fail *with* a failing cleanup. The conformance case asserts the
  intent survives as `pending`, the tree stays hidden from enumeration while
  physically present, and a later writer acquisition recovers and republishes.
- The existing ten `PUBLICATION_FAULT_POINTS` cases, the malformed-intent case,
  and the legacy-project case are untouched.

Files: `packages/project-io/src/web/library_opfs_storage.js`,
`tests/platform/web/project_io/project_io_web_conformance.spec.mjs`,
`tests/platform/web/project_io/project_io_web_test.cpp`,
`tests/platform/web/project_io/project_io_web_faults.mjs`.

### Task 2: Recover from a torn storage intent instead of locking the Project — IMPLEMENTED (`039399d`)

`recoverIntents` threw `InvalidStateError` for any intent file it could not
parse or validate. Because it runs inside `acquireWriter` before the lease is
registered, that throw made **every** subsequent writer acquisition for the
Project fail. The intent file is written incrementally through a sync access
handle, so a crash mid-write can leave a truncated JSON body, and the Project
was then permanently unopenable until OPFS was cleared by hand. The
publication-intent path already established the opposite precedent: an
unreadable publication record is treated as `pending` and recovered.

Automatic removal of a torn record is provably safe. `createIntent` writes the
intent and then reads it back and hash-verifies it *before* the destination is
touched — `replaceComplete` and `createImmutable` both call it before opening
or writing the destination — and `createIntent` refuses to reuse an existing
intent file, so each intent file is written exactly once. A record that fails to
decode or parse therefore cannot correspond to a mutation that began.

Delivered:

- **Torn metadata** — bytes that are not valid UTF-8, or a body that is not
  valid JSON — is removed and recovery continues. The decoder now uses
  `new TextDecoder("utf-8", {fatal: true})` so undecodable bytes classify as
  torn instead of being silently replacement-decoded, matching
  `readPublicationRecord`.
- **Structured but unacceptable metadata** — a body that parses as JSON but
  fails `validateIntent`, or whose filename does not match the hash of its
  declared destination, or a valid intent whose destination state matches
  neither `next` nor `previous` — keeps failing closed, unchanged. A record
  written by a future Contract revision would parse and fail validation on an
  older reader, and an older reader must never destroy rollback metadata it
  does not understand.
- Recovery ordering is otherwise unchanged: the publication intent is still
  handled first, the remaining intents are still processed in stable UTF-8 name
  order, and recovery still completes before any Project mutation and before
  the lease is registered.
- An `acquire_after_intent` action plus conformance cases assert a torn record
  recovers with the destination bytes intact and an empty intent directory,
  and that an unknown `contract` value still fails closed.

Files: `packages/project-io/src/web/library_opfs_storage.js`,
`tests/platform/web/project_io/project_io_web_conformance.spec.mjs`,
`tests/platform/web/project_io/project_io_web_test.cpp`.

### Task 3: Integrate versions, Assembly, and Portal current truth — IMPLEMENTED (`b229400`, `26f67c7`)

Implemented after the browser conformance evidence existed on CI. The
identity move landed as `b229400` (66 files, authored portal narrative, no
textual substitution of proof-bearing sentences; `1.0.16.8` recorded as the
tagged, superseded Build rather than abandoned) and the immutable
`1.0.16.9 · canary` snapshot froze at that clean boundary as `26f67c7`. Two
follow-up alignment commits closed literal forms the token pass could not
see: numeric `"patch": 8` assertions in the CLI/MCP/Creator tests
(`1e2b1e2`) and the Build embedded in the Creator acceptance-report filename
(`1d0fad3`).

- Apply the exact version movements in `## Version Management` to every module
  manifest, Product `version.json`, `assembly.json`, and README identity text,
  then regenerate `products/lmdj/assembly.lock.json` through
  `scripts/version.py lock`. The tooling requires Python 3.10+; CI uses 3.11.
- **Do not propagate identities by blind textual replacement.**
  `apps/architecture-portal/docs/operations/testing-and-proof.mdx` contains
  proof-bearing sentences that name a Product Build *together with* the source
  revision that proved it, the conformance counts, the abandoned-candidate
  list, and the frozen snapshot. Rewriting the Build number in those sentences
  fabricates evidence for a Proof that never ran. Those passages may only be
  rewritten from an actual Proof run, and the abandoned/superseded status of
  `1.0.16.8` is a governance decision for the Integration Owner, not a
  mechanical edit. `apps/architecture-portal/test/content-inventory.test.mjs`
  asserts these sentences with escaped-dot regexes and will not be updated by
  a token replacement either.
- Third-party version strings must not be touched. A token replacement over the
  prior propagation's file set corrupted `@types/estree` in
  `apps/creator-web/package-lock.json`; per-identity, context-checked edits are
  required.
- Update the affected Portal current pages: the storage platform page must
  state the corrected publication-failure cleanup ordering and the torn-intent
  recovery classification, including the deliberate fail-closed boundary for
  structured metadata; the testing-and-proof page gains the new conformance
  cases; the version-and-release page gains the new identities.
- Run `scripts/architecture-portal.sh check`; identities come from the active
  manifests and are never hand-entered.
- Verify: `python3 scripts/version.py verify --version-file
  products/lmdj/version.json`, `tests/build/version_test.py`,
  `tests/conformance/version_lock_test.py`,
  `tests/conformance/module_graph_test.py`, and the Portal check.

### Task 4: Final Proof, snapshot, and acceptance evidence — EVIDENCE RECORDED

The authoring machine has no `emsdk`/Playwright, so the Proof evidence came
from CI `workflow_dispatch` full-mode runs instead of a local clean-room run;
`docs/quality/2026-08-12-opfs-publication-recovery-acceptance.md` records the
per-lane conclusions bound to run IDs and revisions, including the two new
conformance cases passing in Chromium and four self-hosted Linux lanes
recorded as ENVIRONMENT BLOCKED (dependency downloads failing on the
`contabo` runners) rather than PASS, each with a green run at a
lane-equivalent tree.

- Run the full gate set on the completed branch: `scripts/core.sh proof`,
  `scripts/core.sh test asan full`, `scripts/web-toolchain-conformance.sh proof`,
  `scripts/web-runtime-host.sh proof`, `scripts/creator-web.sh proof`,
  `bash scripts/verify-core-dependencies.sh`,
  `bash tests/build/test_active_tree.sh`, and
  `scripts/architecture-portal.sh check`.
- Freeze the immutable Portal snapshot for the allocated Product Build with
  `scripts/architecture-portal.sh version PRODUCT_BUILD canary`, only from a
  clean committed source boundary.
- Record automated acceptance evidence in
  `docs/quality/2026-08-12-opfs-publication-recovery-acceptance.md`, keeping
  the five deferred physical rows accurately deferred and claiming no push,
  PR, merge, tag, Release, deployment, or Channel promotion. If a gate is
  environment-blocked, record it as blocked with its mitigation, never as
  PASS.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

Baselines are the actual values at `fix/web-runtime-hardening` head `2ce4c8a`,
re-read from the active manifests. No version file is written until Task 3, and
the baselines are re-verified against the branch head at that point.

| Identity | Baseline | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.16.8` | `1.0.16.9` | recovery-correctness-only canary candidate |
| Project I/O | `0.5.2` | `0.5.3` | corrected publication cleanup ordering and torn-intent recovery, compatible |
| Application Facade | `1.3.3` | `1.3.4` | exact `project-io` dependency update only |
| Web Runtime Platform | `0.1.5` | `0.1.6` | exact Facade dependency update only; no Platform source change |
| Core CLI | `1.0.9` | `1.0.10` | exact Facade dependency update only |
| Core MCP | `1.1.6` | `1.1.7` | exact Facade dependency and Python package identity propagation only |
| Native Test Host | `1.0.7` | `1.0.8` | exact Facade dependency update only |
| Web Runtime Host | `1.2.5` | `1.2.6` | exact Platform dependency update only |
| Creator Web | `1.0.5` | `1.0.6` | exact Platform dependency update only |
| Audio Runtime | `0.4.1` | unchanged | no DSP, Voice, or realtime contract change |
| Contracts | current | unchanged | `lmdj.storage.intent.v1` and `lmdj.storage.directory-publication.v1` record shapes are unchanged; only recovery classification changes |
| Providers, Models | current | unchanged | no Provider behavior change |

- Compatibility: both changes strengthen failure paths. Every successful
  publication, every already-passing fault point, Project Truth,
  `lmdj.project.v1`, both storage record shapes, and the no-overwrite collision
  semantics are unchanged. The two new behaviors are: a surviving `pending`
  intent where a failed publication previously deleted its own recovery
  metadata, and a removed torn intent where a Project previously became
  permanently unopenable.
- Re-allocation rule: if the hardening candidate moves to another Build before
  it merges, this candidate re-allocates to the next free PATCH above it and
  this table is corrected before the PR. Used or abandoned Build and PATCH
  numbers are never reused, and no tag is moved.
- Tag condition: only after squash merge to `main`, full CI, merged-main
  Proof, and exact identity verification may the Integration Owner create the
  signed annotated Product tag. This plan authorizes neither push, PR, merge,
  tag, Release, deployment, publication, nor Channel promotion.
- Rollback reuses the immutable prior Product tag. Rolling back restores the
  two defects but changes no record shape, so any Project written under this
  candidate stays readable by the prior build.

## Verification Status

Tasks 1 and 2 are implemented and committed. The authoritative browser gate has
not run; what was verified locally is recorded here so no reader mistakes it
for Proof.

| Check | Result |
| --- | --- |
| `node --check` on both changed JavaScript files | PASS |
| Fake-driven exercise of the two edited branches (14 assertions covering intent survival on failed cleanup, intent removal on confirmed absence, committed short-circuit, torn/non-UTF-8 classification, fail-closed on unknown contract, valid-intent resolution) | PASS |
| Same assertions against the pre-fix file | 5 targeted assertions FAIL, all regression assertions PASS — the intended RED |
| `scripts/web-toolchain-conformance.sh proof` (new conformance cases, new C++ actions) | NOT RUN — no `emsdk`, no Playwright `1.62.1` |
| `scripts/core.sh proof`, Host and Creator Proof, Portal check at the new Build | NOT RUN — Task 3/4 |

The fake-driven exercise is a local authoring aid, not a repository test tier;
it is not committed. Only the browser conformance suite is evidence.

## Documentation Impact

Documentation impact: required, deferred to Task 3.

- Affected portal routes: `platform/storage` (publication-failure cleanup
  ordering, torn-intent recovery classification and its deliberate fail-closed
  boundary), `core/modules/project-io` (module version and behavior note),
  `operations/testing-and-proof` (new conformance cases),
  `operations/version-and-release` (new Product Build and module identities).
- Tasks 1 and 2 change no Product Build, Assembly, Module manifest, Contract,
  or portal route, so they carry no documentation impact of their own; the
  Portal check at `2ce4c8a` identities stays valid across them.
- Task 3 changes the Product Build and Assembly, so `Documentation impact:
  none` is not permitted there; the immutable canary snapshot in Task 4 is
  mandatory before any team-testing or release allocation.
- The Stage 7 design §7.3 text already describes the intended cleanup and
  recovery semantics correctly, so no design revision is required — this plan
  makes the implementation match the approved design rather than changing it.
  The separate Stage 7 documentation-drift Task (D1–D3, G3, G4 of the review)
  is not folded in here.

## Pull Request and Completion Boundary

After Task 4, inspect every commit and staged file list, run
`git diff --cached --check` per commit, and request code review before any push
authorization. A green local Proof does not authorize push; a green pushed PR
does not authorize merge; a squash merge does not authorize tag, Release,
deployment, or Channel promotion. This branch additionally must not merge
before `fix/web-runtime-hardening`. The plan is complete only when the approved
PR is squash-merged, required checks pass on current code, and merged `main`
re-runs Core, Web Runtime Host, Creator Web, and Portal Proof.
