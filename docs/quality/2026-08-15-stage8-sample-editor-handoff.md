# Stage 8 Sample Editor Handoff — 2026-08-15

This document hands the remaining Stage 8 work from Codex to the next
implementation owner. It records facts observed from the repository and GitHub;
it is not an acceptance record, merge authorization, release authorization, or
Channel-promotion authorization.

## Current repository position

| Item | Observed state |
| --- | --- |
| Repository | `endaye/lmdj` |
| Worktree | `/Users/endaye/Projects/lmdj/.worktrees/stage8-sample-editor` |
| Branch | `feat/stage8-sample-editor` |
| Pull Request | [#137 — feat(creator): deliver Stage 8 Sample Editor](https://github.com/endaye/lmdj/pull/137) |
| PR state | Open, Draft |
| Handoff base | `4379fd160b3defd3a52ec0bb43f96aaa6ccff4ad` |
| Handoff-base `main` | `e11ed52ad223ee56e6300f1afb250db635a53bfc` |
| Product Build | `1.0.22.0 · canary` |
| Project Contract | `lmdj.project.v2 · 2.0.0` |

The handoff base already includes `main` through `90f261b`, but `main` advanced
again after that merge. GitHub currently reports the PR as conflicting.

## Delivered scope

Stage 8A implements the Sample Editor across Project Truth, Cooker, realtime
audio, Application Facade, Web Runtime transport/session, and Creator UI:

- PCM16 WAV inspection, import, replacement, reset, deterministic 48 kHz
  preparation, and content-derived waveform caching;
- per-Pad playback truth with trim, gain, mute, loop, and four trigger modes;
- atomic command/revision semantics, v1 read compatibility, and first-write v2
  migration;
- realtime preview, release/stop controls, Voice-state reporting, and bounded
  fail-closed behavior;
- Creator Sample UI, waveform editing, keyboard/pointer/MIDI journeys,
  interruption/restart ownership, saved-versus-runtime truth, privacy, and
  accessibility;
- Product Build `1.0.22.0` manifests, immutable Portal snapshot, documentation,
  and automated acceptance fixtures.

Stage 8B recording, automatic slicing, a browser-wide Sample library, and
non-destructive processing remain deliberately out of scope and unversioned.

## Review remediation already implemented

The external Stage 8 review found no blocker and two major code defects. Both
have implementation and regression coverage on this branch:

1. `9188410 fix(stage8): close sample editor review gaps` allows a valid
   incomplete same-token staging directory to be reclaimed under the writer
   lease. A crash between staging and manifest publication therefore no longer
   makes the idempotent command unusable for 24 hours.
2. The same commit preserves a successful mutation receipt when preview cleanup
   or the post-commit authoritative Sample inspection fails. The Creator no
   longer reports the persisted mutation itself as failed.

The same remediation also documents the realtime bank publication ordering
invariant and adds a Project I/O fault-matrix regression. Later commits harden
Creator lifecycle ownership, Web Runtime Voice overflow coverage, Facade
waveform behavior, Cooker GCC compatibility, and Web Project I/O conformance.

The governance identity defect was corrected by
`cf30959 docs(quality): rebind stage 8 acceptance truth`: the acceptance record
now names `1.0.22.0` and allocation `ebaf2fea`. Its *current reviewed
implementation* and external-state sections are nevertheless stale because
many later commits were added. Refreshing those sections is still required;
do not rewrite the immutable `1.0.22.0` Portal snapshot.

At handoff time GitHub reported zero unresolved, non-outdated review threads.

## Evidence ledger

Evidence must be attributed to the revision on which it ran. Do not present a
green result from an older revision as exact-head evidence.

### Exact handoff-head remote evidence

Core CI run [31822490596](https://github.com/endaye/lmdj/actions/runs/31822490596)
completed successfully for `4379fd1`, but the PR was Draft. It therefore proved
only the draft-scope gates:

- Change Scope: pass;
- Docs / static: pass;
- CI contract: pass;
- PR Gate: pass;
- Netlify deploy preview: available.

The Architecture Portal, Core, ASan full/stress, coverage, package, Creator,
Web Runtime Host, Web toolchain conformance, and macOS product jobs were skipped
by the draft-scope contract. This is not full exact-head acceptance.

### Latest focused Web Project I/O evidence

After rebuilding the Web Project I/O conformance target with the governed
Emscripten 6.0.5 toolchain, the exact Chromium spec passed 6/6. The bounded
publication fixture observed a maximum chunk of 1,048,576 bytes. Relevant
commits culminate in `daa32b2 test(project-io): verify bounded web publication`.

Toolchain used:

```text
/Users/endaye/Projects/lmdj/.worktrees/stage7-review-remediation/build/toolchains/emsdk
Emscripten 6.0.5, Node 22.16.0
```

Reproduction command:

```bash
export EMSDK=/Users/endaye/Projects/lmdj/.worktrees/stage7-review-remediation/build/toolchains/emsdk
export PATH="$EMSDK/node/22.16.0_64bit/bin:$PATH"
export npm_config_offline=true
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
bash scripts/web-toolchain-conformance.sh build-project-io
npm --prefix tests/platform/web test -- --project=chromium \
  "$PWD/tests/platform/web/project_io/project_io_web_conformance.spec.mjs"
```

### Older broad evidence

The PR body and acceptance record retain broad local evidence from earlier
Stage 8 candidate revisions, including native Core full/stress, Creator,
Web Runtime, Portal, Chromium, and WebKit capability runs. These results are
useful regression context only. The latest branch plus current `main` must run
the required full CI again before merge.

Historical CI run `31812609561` at `ba96741` failed before product jobs started
because GitHub reported an account billing/spending-limit problem. The later
draft-scope run did start and pass. Re-check Billing only if the ready-for-review
full run again fails before runner startup.

## Immediate continuation checklist

Run all Git operations from the isolated Stage 8 worktree. Audit every worktree
before moving or merging branches.

```bash
cd /Users/endaye/Projects/lmdj/.worktrees/stage8-sample-editor
git status --short --branch
git fetch origin --prune
git rev-parse HEAD origin/feat/stage8-sample-editor origin/main
git worktree list --porcelain
```

### 1. Merge the latest `main`

At the handoff base, a read-only `git merge-tree` reported conflicts in exactly:

- `.github/workflows/ci.yml`;
- `apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx`;
- `apps/architecture-portal/docs/hosts/web-runtime.mdx`.

Resolve them semantically, preserving both the current-main CI/Runtime fixes and
the Stage 8 Sample contracts/documentation. Do not resolve by choosing an entire
side. Re-run `git merge-tree` or inspect GitHub again because `main` may advance.

### 2. Refresh mutable truth

Update these mutable records to the post-merge HEAD and actual evidence:

- `docs/quality/2026-08-09-stage8-sample-editor-acceptance.md`;
- PR #137 body, especially its validation revision and evidence boundaries;
- this handoff if the remaining state changes materially.

Do not regenerate or rewrite the immutable `1.0.22.0` Portal snapshot merely to
change the reviewed implementation revision. Preserve the distinction between
the allocation revision, immutable snapshot revision, implementation HEAD, and
the revision on which each test ran.

### 3. Run post-merge local gates

At minimum, run the repository-governed checks affected by the conflict and the
Stage 8 concurrency paths:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev full
scripts/core.sh test dev stress
scripts/core.sh proof
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/architecture-portal.sh check
```

Also run the Creator, Web Runtime Host, and Web toolchain conformance gates using
the repository scripts and governed Node/Emscripten toolchain. Rebuild stale Web
artifacts before diagnosing a browser failure. For trigger journeys, remember
that press admissions contain `velocity`, while release acknowledgements are a
separate count.

### 4. Obtain exact-head CI

After resolving conflicts, committing, and pushing:

1. confirm the remote branch SHA equals local HEAD;
2. keep the PR Draft while iterating on known failures;
3. when locally ready, mark the PR ready for review so the full change-scope
   matrix runs rather than only draft static gates;
4. require the exact-head Core, Core ASan full+stress, coverage, package,
   Creator, Web Runtime Host, Web toolchain conformance, Portal, and macOS gates;
5. inspect failed logs before rerunning; do not treat skipped jobs as green;
6. confirm zero unresolved review threads and a clean merge state.

The user must explicitly authorize the merge after these conditions are met.
Neither this document nor the earlier request to prepare the branch authorizes
merge, tag creation, release, deployment, publication, or Channel promotion.

## Architectural and safety boundaries

Preserve these while continuing Stage work:

- Hosts use Application Facade and never parse Project bundles.
- Project Truth is authoritative; Runtime Snapshot is immutable derived state
  and is never persisted.
- Pattern events reference Pad Slots, never Assets.
- Prepared PCM and waveform caches are derived and never Project Truth.
- Sample mutations retain `command_id` plus `expected_revision` semantics.
- Browser payloads never carry Project paths or raw Sample bytes outside the
  bounded verified sidecar boundary.
- Audio render paths remain allocation-free, lock-free, and system-call-free.
- Voice-state overflow and corrupted telemetry fail closed.
- Saved Project revision and published Runtime revision remain distinct after
  Cooker failure; retry prepares current truth without replaying the mutation.
- Lifecycle cleanup has one owner; do not duplicate stop/release operations
  between Creator and Runtime Session.
- `lmdj.patch.v1` and `lmdj.materials.v1` remain retired.
- Manual Safari, iPadOS, physical MIDI, hearing, and latency evidence stays
  explicitly deferred until actually performed.

## Commit and publication discipline

- Work only on `feat/stage8-sample-editor` in its isolated worktree.
- Preserve unrelated work and stage only declared paths.
- Before each commit, inspect `git diff --cached --name-status` and run
  `git diff --cached --check`.
- Use one reviewable Conventional Commit per implementation task.
- A local commit does not authorize push; a push does not authorize merge;
  merge does not authorize tag, Release, deployment, or Channel promotion.
- Never amend or rewrite the existing reviewed history unless the user gives
  explicit history-rewrite authorization.

## Suggested first message to the next owner

> Continue Stage 8 from
> `/Users/endaye/Projects/lmdj/.worktrees/stage8-sample-editor` and read
> `docs/quality/2026-08-15-stage8-sample-editor-handoff.md` completely. Verify
> all live GitHub and Git facts before acting. First merge the latest `main`,
> resolve the three known conflicts semantically, refresh mutable acceptance/PR
> truth, and run full local plus exact-head CI. Do not merge, tag, release,
> deploy, publish, or promote without a new explicit authorization.
