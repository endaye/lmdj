# LMDJ Release Audit Ancestry and Witness Remedy Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Close the two release-governance defects the pre-Stage-9 triage files
as B1 and B2: the audit approves release intents that `prepare` will refuse,
and every squash merge of a Build that carries an immutable Portal snapshot
turns `main` red with a failure that does not say how to fix it. Both fixes
make the release path tell the truth about its own readiness; neither adds a
new mutation capability.

**Architecture:** Repository tooling only — `tools/release/audit.py` and the
Architecture Portal provenance scripts under
`apps/architecture-portal/scripts/`. No Core Module, Application Facade,
Contract, Provider, Host runtime or Product Assembly change. The audit remains
read-only and fail-closed; the witness creator keeps writing with `wx` (never
overwrite) and gains no new write target.

**Tech Stack:** Python 3 (release tooling + `tests/build/*_test.py`), Node.js
ESM (portal scripts + `node --test`), Bash entry points.

## Current state (verified against `main` at `af32a0eb`, 2026-08-18)

### B1 — the audit gates on a weaker condition than prepare enforces

- `tools/release/prepare.py:108` refuses any target that fails
  `is_main_ancestor` — "release target does not have canonical main ancestry".
- The audit checks ancestry only **after a remote tag exists**
  (`tools/release/audit.py:491`, inside `_audit_remote_intent`'s
  tag-present flow). The two pre-mutation paths return earlier and never reach
  it:
  - `Disposition.ALLOCATED` returns `ok` at `audit.py:452-459` with no
    ancestry check;
  - a releasable intent with no remote state returns `ok` at
    `audit.py:471-485` after CI-evidence checks only.
- The only pre-tag check on target commits is `git cat-file -e` object
  existence in the static projection at `audit.py:394-403` — local object
  availability, not ancestry, and against the local repository rather than the
  canonical fetched `refs/lmdj-release/origin-main`
  (`git_repository.py:42,61-62`).

Consequence, already paid for: the `1.0.22.0` and `1.0.23.0` intents pointed
at branch-side allocation commits that squash merging had collapsed. They were
unpreparable from the moment they were written; the audit stayed green until
garbage collection removed the objects. #180 rebound those two intents; the
mismatch that admitted them is untouched.

### B2 — the provenance failure names the disease, not the cure

Every Product Build carrying an immutable Portal snapshot goes red on `main`
immediately after squash merge, because the squash collapses the freeze
revision. The verifier's failure branch
(`apps/architecture-portal/scripts/lib/snapshot-provenance.mjs:667`) reports:

> `source projection is neither direct-parent nor squash-equivalent and
> authenticated squash witness is unavailable`

The remedy is always the same and always applied by hand afterwards
(#129, #169, #179 — three witness-authentication PRs, five affected Builds):
run `scripts/architecture-portal.sh witness PRODUCT_BUILD INTRODUCING_REVISION`
and merge the resulting file. At the moment the verifier produces that error it
**already holds both arguments** — `metadata.product_build` and the
`introducing` revision it resolved itself (`snapshot-provenance.mjs:546-548`) —
and names neither.

Emitting the witness **on the merge path is impossible by construction**: the
witness records the introducing squash revision, which exists only after the
merge, and the witness file must itself be committed, which on protected
`main` means a follow-up PR. The honest fix is the second shape triage offers:
make the failure name the exact command, and make that command harder to
misuse.

## Global Constraints

- Execute only on `fix/release-audit-ancestry` in
  `/Users/endaye/Projects/lmdj/.worktrees/release-audit-ancestry`. Never
  implement on `main`.
- The audit stays read-only. No task here adds a remote mutation, a tag
  operation, or a new file-write target.
- Fail-closed direction only: every behaviour change may turn a previously
  green state red, never the reverse. No existing red state may become green
  except by the operator running the named remedy.
- Do not weaken or remove the `cat-file -e` object-existence projection at
  `audit.py:394-403`; local object availability is still required by
  `validate_release_target`'s detached worktree at `audit.py:443`.
- Do not change intent dispositions, the ledger schema, `policy.json`, or any
  Contract.
- `.agents/skills/lmdj-release/SKILL.md` remains authoritative for release
  operations; this plan changes what the audit reports, not the authorization
  boundaries around it.
- Every Task is one reviewable Conventional Commit. Before every commit:
  verify the branch is not `main`; run the Task-specific verification and
  `scripts/architecture-portal.sh check`; stage only declared files; inspect
  `git diff --cached --name-status` and `git diff --cached --check`; after
  committing inspect `git show --name-status --oneline HEAD`.
- This plan authorizes local commits only. Push, PR creation, merge, tag,
  Release, publication, deployment and Channel promotion each require separate
  explicit authorization.

---

## Tasks

### Task 1 — Audit asserts canonical main ancestry before authorizing a mutation (B1)

An intent the audit reports as actionable must be one `prepare` would accept.

- [x] In `_audit_remote_intent`, assert
      `context.git.is_main_ancestor(intent.target_revision)` on both
      pre-mutation paths:
      - the `Disposition.ALLOCATED` early return (`audit.py:452-459`);
      - the releasable-with-no-remote-state path (`audit.py:471-485`),
        **before** CI evidence is evaluated — CI evidence for an unpreparable
        target is noise, and the finding must name the real defect first.
- [x] On failure return the existing vocabulary: an `unauthorized` finding for
      the intent's tag with the established message
      `release target is outside protected main ancestry`, so the failure is
      immediate and named, matching prepare's refusal.
- [x] Wrap the ancestry probe exactly as the post-tag flow does
      (`audit.py:493-494`): a probe error is an `external-error` finding
      naming `git-remote`, never a silent pass.
- [x] Leave `ABANDONED` and `SUPERSEDED_UNRELEASED` paths unchanged: neither
      authorizes a future mutation, and abandoned targets may legitimately sit
      outside `main`. Record this boundary in the test names.
- [x] Extend `tests/build/release_audit_test.py` (fake git already exposes
      `is_main_ancestor`, line 80):
      - allocated intent off-main → `unauthorized`, message as above;
      - releasable intent with no remote state, off-main → `unauthorized`,
        and CI evidence is not consulted;
      - ancestry probe raising → `external-error` with `git-remote` source;
      - both paths on-main → findings unchanged from today;
      - abandoned and superseded-unreleased intents off-main → findings
        unchanged from today.

**Verification:** `python3 -m pytest tests/build/release_audit_test.py -q`
passes (or the repository's equivalent runner for that file);
`python3 tests/build/version_test.py`; full
`bash tests/build/test_active_tree.sh`. New tests fail before the change and
pass after.

### Task 2 — The provenance failure names the exact remedy, and the remedy needs one argument (B2)

- [x] In `snapshot-provenance.mjs`, extend the failure at line 667 so the
      message carries the concrete remediation:
      `run scripts/architecture-portal.sh witness <product_build> <introducing>`
      with both values filled from `metadata.product_build` and the already
      resolved `introducing` revision — copy-pasteable, not a template.
- [x] Keep the distinct-error passthrough (`squashRelationError =
      error.message` for every other witness failure) byte-for-byte: a
      malformed witness must keep reporting its own defect, not the missing
      remedy.
- [x] In `create-squash-witness.mjs`, make `INTRODUCING_REVISION` optional:
      when omitted, derive it with the same resolution the verifier uses
      (`snapshot-provenance.mjs:546-548`), refusing with the existing usage
      message when derivation is ambiguous or fails. An explicitly passed
      revision keeps exact current behaviour, including the
      `does not exist` refusal (`snapshot-provenance.mjs:286-287`).
- [x] Update `scripts/architecture-portal.sh` usage text
      (`witness PRODUCT_BUILD [INTRODUCING_REVISION]`) and the command's
      documentation in `docs/governance/architecture-portal.md:107`.
- [x] Extend `apps/architecture-portal/test/snapshot-provenance.test.mjs`:
      - the unavailable-witness failure message contains the exact command
        with both concrete arguments;
      - witness creation with the second argument omitted produces a witness
        byte-identical to one created with the derived revision passed
        explicitly;
      - ambiguous or failed derivation refuses and writes nothing.

**Verification:** `scripts/architecture-portal.sh check` passes 48+ tests
including the new ones; the witness-creation tests confirm `wx` semantics are
untouched (existing file still refuses).

### Task 3 — Close the ledger entries

- [x] Mark B1 and B2 done in
      `docs/quality/2026-08-17-machine-task-todo.md`, naming the commits.
- [x] Update section B of
      `docs/quality/2026-08-16-outstanding-work-before-stage9.md` the same
      way; B3 and B4 remain open.
- [x] If reviewers of the audit change surfaced anything worth keeping,
      record it; otherwise this task is the two ledger edits and nothing else.

**Verification:** `scripts/architecture-portal.sh check`;
`git diff --cached --check`.

---

## Version Management

**Version impact: none.**

- `tools/release/` and `apps/architecture-portal/scripts/` are unversioned
  repository tooling: not Core Modules, not Providers, not Hosts in the module
  graph, and no Contract or Product identity is touched. The three prior
  witness PRs (#129, #169, #179) carried no version change for the same
  reason.
- No Product Build is allocated by this plan. If a future Build's audit or
  witness behaviour is described in release evidence, that evidence cites the
  merge commit, not a version.

## Documentation impact

**Documentation impact: none** for Tasks 1 and 3 — the audit's authorization
boundaries are unchanged and no portal route describes the pre-tag audit
ordering. Task 2 updates `docs/governance/architecture-portal.md` (the witness
command's canonical usage) in the same Task, which is a governance document,
not a portal route; no `apps/architecture-portal/docs/` page states the
witness arity, so no portal page changes. Run
`scripts/architecture-portal.sh check` before every commit regardless, since
Task 2 edits portal scripts that the check executes.

## Out of scope

- B3 (hand-written Build identity) and B4 (double lock regeneration) — same
  section of the triage, separate plans.
- Any automation that commits to `main` on the merge path — publication stays
  Git-triggered and human-authorized.
- Ancestry enforcement for `ABANDONED` / `SUPERSEDED_UNRELEASED` intents —
  historical states that authorize no mutation.
- The release skill document's operational flow — unchanged authorization
  boundaries mean no skill edit.
