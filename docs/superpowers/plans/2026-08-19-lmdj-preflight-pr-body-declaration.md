# LMDJ Local Pre-flight PR Body Declaration Check Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Let `scripts/local-ci.sh` verify a Pull Request body's
documentation-impact declaration before the body reaches CI. Today the
declaration is checked only by the `portal` lane's `check:impact` step, which
reads `github.event.pull_request.body`, so a malformed declaration is
discoverable only after a full portal lane run — and only after a *new*
`pull_request` event, because a re-run replays the original payload.

**Why it is worth tooling.** PR #186 paid the full price on 2026-08-18: the
body declared the impact as `**Documentation impact: required.**` (bold, with a
trailing period), which the checker's
`^Documentation impact:\s*(required|none)\s*$` cannot match. `PR Gate` went red
~13 minutes in, on a change whose content was already correct. The remedy also
could not be a re-run: `ci.yml`'s `pull_request` types are
`[opened, synchronize, reopened, ready_for_review, converted_to_draft]` — no
`edited` — so the body edit had to be paired with a close/reopen to emit a
fresh event. The declaration is machine-checked but had no local pre-check,
and `scripts/ci/local_lanes.json` recorded that gap as permanent.

**Architecture:** Repository tooling and documentation only —
`scripts/local-ci.sh`, `scripts/ci/local_preflight.py`,
`scripts/ci/local_lanes.json`, their test file, one governance document and one
portal page. No Core Module, Application Facade, Contract, Provider, Host,
Product Assembly, or CI workflow change. `apps/architecture-portal/scripts/check-doc-impact.mjs`
is **reused unmodified**: the pre-check must run the same code CI runs, or it
is a second opinion rather than a pre-check.

## Current state (verified against `main` at `4b4b0834`, 2026-08-19)

- `check-doc-impact.mjs` requires three bare lines in the body:
  `^Documentation impact:\s*(required|none)\s*$`, `^Reason:\s*(.*)$`, and —
  when the impact is `required` — `^Affected portal pages:\s*(.*)$` whose
  entries all start with `/`. It also cross-checks the declaration against the
  changed files: `required` demands a changed
  `apps/architecture-portal/docs/**.mdx?`, `none` forbids one, and a
  `products/lmdj/` identity change forces `required`.
- It imports only Node builtins (`node:path`, `node:url`,
  `node:child_process`, `node:util`), so it runs on bare `node` with **no npm
  install** — the expensive part of the `portal` lane is irrelevant to it.
- It already reads `PORTAL_PR_BODY` and `PORTAL_CHANGED_FILES` from the
  environment, and falls back to `git diff --name-only HEAD^ HEAD`. Nothing in
  the checker is CI-specific; only its *input* was unavailable locally.
- `local_lanes.json` records the gap as a `ci_only` note on `portal`:
  "npm --prefix apps/architecture-portal run check:impact reads the Pull
  Request body, which does not exist locally". `ci_only` notes are validated
  by `load_lane_commands` but never surfaced in output — they are checked-in
  documentation.
- The declaration step runs in CI only when the `portal` lane is selected. A
  change confined to `docs/prd/` selects `docs_static` alone
  (`scope_policy.json` maps `docs/` → `docs_static`), so CI never checks its
  declaration; `docs/governance/` and `docs/quality/` do select `portal`.

## Chosen shape, and one shape deliberately rejected

**Rejected: adding the check to `portal`'s `commands` in `local_lanes.json`.**
The lane cache key digests the lane name, its resolved commands, and the
content identity of every *repository* path that is an input to that lane
(`lane_cache_key`, `lane_input_paths`). A PR body file is not repository
content — it is an arbitrary path such as `/tmp/body.md` — so editing the body
would leave the key unchanged and the lane would report `cached-pass` while the
declaration it claims to have checked had changed underneath. That is a false
pass, which is the one thing this pre-flight is built not to produce. Adding
the body to the digest is not a fix either: it would make an out-of-tree file
part of a content-addressed repository cache.

**Chosen: a separate, never-cached declaration check**, reported alongside the
lanes but not as a lane.

- New flag `--pr-body PATH` on `scripts/local-ci.sh` (forwarded to
  `local_preflight.py`). Absent, behaviour is byte-for-byte what it is today.
- The check runs `node apps/architecture-portal/scripts/check-doc-impact.mjs`
  with `PORTAL_PR_BODY` from the file and `PORTAL_CHANGED_FILES` from the same
  inventory the classifier already computed for lane selection.
- It mirrors CI's applicability: the declaration is checked only when the
  `portal` lane is selected, because that is the only condition under which CI
  checks it. When `portal` is not selected the check reports
  `not-applicable`, never `pass`.
- It is never cached, and never contributes a `cached-pass`.
- A failure exits non-zero like a lane failure, since it *will* fail CI.

**Local input is a superset of CI's, deliberately.** CI diffs
`base..head` (committed only); the pre-flight's inventory is
`base..working tree` plus untracked files. So the pre-check sees a portal page
you have edited but not yet committed. That is the safer direction for a
pre-flight — it cannot claim `none` is valid while an uncommitted `.mdx` edit
is staged to arrive — and it is the same inventory the lane selection already
uses, so the two cannot disagree about what changed.

## Global Constraints

- Execute only on `feat/preflight-pr-body` in
  `/Users/endaye/Projects/lmdj/.worktrees/preflight-pr-body`. Never on `main`.
- `check-doc-impact.mjs` is not modified. If the pre-check needs behaviour the
  checker does not have, that is a finding to report, not a local
  reimplementation.
- Fail-closed only: an unreadable body file, absent `node`, or a checker
  crash must report a non-pass verdict with the reason, never a silent pass.
- The four existing verdicts (`pass`, `cached-pass`, `fail`,
  `not-runnable-here`) keep their current meanings for lanes. The declaration
  check is reported as its own row, so no lane's vocabulary changes.
- The pre-flight stays advisory and produces no evidence; `PR Gate` remains
  the single aggregate decision. A green local run authorizes no push, Pull
  Request, merge, or later state transition.
- Every Task is one reviewable Conventional Commit. Before every commit:
  verify the branch is not `main`; run the Task-specific tests and
  `scripts/architecture-portal.sh check`; stage only declared files; inspect
  `git diff --cached --name-status` and `git diff --cached --check`; after
  committing inspect `git show --name-status --oneline HEAD`.
- Local commits only. Push, PR, merge and every later state transition need
  separate explicit authorization.

## Tasks

### Task 1 — The pre-flight checks a supplied PR body against CI's own checker

- [x] Add `--pr-body PATH` to `local_preflight.py`'s parser and to
      `scripts/local-ci.sh`'s usage comment block.
- [x] Add a `DeclarationResult`-shaped report (lane-independent) with verdicts
      `pass`, `fail`, `not-runnable-here` (no `node` on PATH, or the checker
      script is missing) and `not-applicable` (the `portal` lane is not
      selected, so CI will not check the declaration either). Reuse the
      existing verdict constants where they apply and add only what is
      genuinely new.
- [x] Resolve the changed-file list from the plan's existing inventory rather
      than re-diffing, flattening rename records to all their paths, so lane
      selection and the declaration check cannot disagree about what changed.
- [x] Run the checker with `PORTAL_PR_BODY` and `PORTAL_CHANGED_FILES` set,
      capturing its stderr as the failure detail so the operator sees the
      checker's own message (`affected portal pages must list one or more
      absolute routes`, etc.) rather than a generic exit code.
- [x] Fail closed on an unreadable or non-UTF-8 body file with a named reason.
- [x] Surface the result in the human summary (`_render`), in `--json`, and in
      `--list` (as a planned/not-planned line). Never write it to the lane
      cache.
- [x] A `fail` verdict makes `main` return 1, matching a lane failure. Keep
      `--strict` semantics for `not-runnable-here` consistent with lanes.
- [x] Replace `portal`'s `ci_only` note in `local_lanes.json`: the impact step
      is no longer permanently CI-only, it is checked locally when
      `--pr-body` is given. Keep it listed as a step the lane commands
      themselves do not run.
- [x] Extend `tests/build/ci_local_preflight_test.py`:
      - a well-formed `required` body plus a changed portal `.mdx` → `pass`;
      - the exact PR #186 malformation (`**Documentation impact: required.**`)
        → `fail`, with the checker's own message in the detail;
      - `required` with no absolute routes → `fail`;
      - `none` while a portal page changed → `fail`;
      - body valid but `portal` not selected → `not-applicable`, exit 0;
      - missing/unreadable body file → non-pass with a named reason;
      - no `--pr-body` → behaviour and exit code identical to today, and no
        declaration row is emitted;
      - the declaration verdict is never written to the lane cache.

**Verification:** `python3 -m unittest tests.build.ci_local_preflight_test -v`
(or the repository's runner for that file) passes; new tests fail before the
change. `bash tests/build/test_active_tree.sh`.
`scripts/local-ci.sh --pr-body <this PR's body> --lanes docs_static` reports
the declaration row. As an end-to-end check, run the pre-check against a file
containing PR #186's original malformed body and confirm it reproduces the
failure CI took 13 minutes to find.

### Task 2 — Correct the two documents that state the gap is permanent

- [x] `docs/governance/git-workflow.md` §4 "Local pre-flight": add
      `scripts/local-ci.sh --pr-body FILE` to the command block and state what
      it checks, that it mirrors CI's portal-selected applicability, and that
      it is never cached. Keep the existing advisory-only framing.
- [x] `apps/architecture-portal/docs/operations/testing-and-proof.mdx`: the
      page currently lists "Portal impact check 读取的 PR body" among the CI
      steps the pre-flight **deliberately does not reproduce**, which this
      change makes false. Correct that sentence and name the new
      `not-applicable` result so the page's account of the pre-flight's
      verdicts stays complete. Do not restate any Product, Module, Host,
      Provider, Contract or Channel identity — the portal derives those from
      active manifests.

**Verification:** `scripts/architecture-portal.sh check` passes;
`git diff --cached --check` clean.

## Version Management

**Version impact: none.**

- `scripts/`, `scripts/ci/` and `tests/build/` are unversioned repository
  tooling: not Core Modules, not Providers, not Hosts in the module graph, and
  no Contract or Product identity is touched. No Product Build is allocated.
- `local_lanes.json` carries the schema id `lmdj.ci-local-lanes.v1`. This plan
  does not change its shape — only the text of one `ci_only` note — so the
  schema id is unchanged. Were a new key added, the closed-schema validation
  in `load_lane_commands` would require the id to move; it does not.

## Documentation impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: that page states the local pre-flight deliberately does not reproduce the Portal impact check's PR body and enumerates its four verdicts; this change makes both statements incomplete, so the page is corrected in Task 2 alongside the governance workflow document.

The three machine-readable lines above are the form
`check-doc-impact.mjs` accepts, and the Pull Request body must repeat them
verbatim — bold or a trailing period defeats the anchored pattern. This plan's
own declaration is written in that form on purpose: it is the artifact the
next agent copies.

## Out of scope

- Modifying `check-doc-impact.mjs`, or adding `edited` to `ci.yml`'s
  `pull_request` types. Making a body edit re-trigger CI is a separate CI
  control-plane change with its own authorization and cost argument; this plan
  removes the need for that round trip rather than shortening it.
- Making the declaration check run when the `portal` lane is not selected.
  Widening it beyond CI's own applicability would report a verdict CI never
  forms, and the gap it would cover — a `docs/prd/`-only change whose
  declaration nothing checks — is a scope-policy question, not a pre-flight
  one.
- Fetching the body from GitHub with `gh pr view`. The pre-flight runs before
  a Pull Request exists, and reading remote state would make an offline,
  advisory tool depend on network and auth.
- Any change to lane selection, the scope policy, `PR Gate`, or the cache
  format.
