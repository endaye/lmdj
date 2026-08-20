# LMDJ PRD Question Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Migrate the 19 files in `docs/prd/questions/` to GitHub Issues, so that
active discussion, priority, dependency and open state live where
`docs/governance/github-work-management.md` says they belong, while the files
keep the source context that an Issue body should not absorb.

**Why now.** The repository contract that gates this landed in `23241344`
(#215). Before it, `docs/governance/github-work-management.md` stated
explicitly that `docs/prd/questions/*.md` **must not be migrated**. That
sentence no longer blocks, and the same paragraph sets the shape of the work:

> After merge, an approved migration may create and verify replacement Issue
> links and update source state in the same reviewed Task. Those question files
> retain their current live state and context until the replacement Issue exists
> and its source link is verified.

Two consequences bind this plan. **Creating the Issue and updating the file
happen in one reviewed Task** — a half-migrated question has two live states and
no authority. And **link integrity must be verified**, not assumed: the file
names an Issue and the Issue names the file.

**Architecture:** `docs/prd/questions/` and `docs/prd/` documentation, plus
GitHub Issues. No Core Module, Facade, Contract, Provider, Host, or Product
Assembly change.

---

## Inventory

19 questions, with the status each currently declares. That status becomes
`原迁移状态` — retained as history, no longer meaning anything live.

| Slug | 原迁移状态 | Suggested `area:*` |
| --- | --- | --- |
| `build-manifest-embedding` | 待决 | `area:ci-release` |
| `canonical-timing-analyzer-precedence` | 待评审 | `area:core` |
| `curated-packs-content-rights` | 延后 | `area:product` |
| `empty-pad-fill-strategy` | 延后 | `area:product` |
| `export-zip-missing-stem-presentation` | 待验证 | `area:creator` |
| `generation-provider-hosting` | 延后 | `area:provider` |
| `hardware-proof-thresholds` | 延后 | `area:product` |
| `key-analysis-confidence-threshold` | 待验证 | `area:core` |
| `long-material-prepared-pcm-quota` | 待设计评审 | `area:core` |
| `loop-material-bpm-time-stretch` | 待决 | `area:core` |
| `mcp-protocol-version-upgrade` | 延后 | `area:native-host` |
| `midi-learn-controller-profiles` | 已收缩 | `area:creator` |
| `native-test-host-classification` | 待决 | `area:native-host` |
| `performance-arcade-protection-tiers` | 延后 | `area:product` |
| `production-separator-checkpoint` | 待验证 | `area:provider` |
| `project-bin-storage-model` | 延后 | `area:product` |
| `provider-artifact-byte-access` | 待架构设计 | `area:provider` |
| `recording-concurrency-semantics` | 待设计评审 | `area:core` |
| `take-event-vs-audio-bounce` | 待决 | `area:core` |

`area:*` above is a starting point derived from each question's scope line, not
a ruling; correct it per question while migrating.

## Three questions already have partial state — handle them first

- [ ] **`provider-artifact-byte-access`** already has **#206**, opened before this
  contract existed. It must **not** get a second Issue. Reuse #206: add the
  `GitHub Issue: #206` line to the file, rename `状态：` to `原迁移状态：`, and
  confirm #206's body links back to the file. This is the link-integrity check
  in miniature.
- [ ] **`native-test-host-classification`** is the question behind **#210**
  (`assembly: native-test-host ships in the Product Assembly…`), which is the
  A2 decision. Same treatment: reuse #210, do not open a second Issue. Verify
  the two describe the same question before binding them — if #210 is narrower
  than the question file, say so in the Issue rather than silently widening it.
- [ ] **`mcp-protocol-version-upgrade`** is already recorded as a deliberate
  deferral. Migrating it must not read as reopening it: the Issue body states
  the deferral and its trigger, and carries `priority:p3`.

## Tasks

### Task 1 — Migrate in reviewable batches, not one sweep

- [ ] Do **not** migrate all 19 in one commit. Each migration is a judgement
  about scope, priority and area, and 19 of those in one diff cannot be
  reviewed. Batch by `area:*` so a reviewer sees one domain at a time.
- [ ] For each question, in the same commit as its Issue creation:
  1. create the Issue through the **Question form**
     (`.github/ISSUE_TEMPLATE/question.yml`) so the required sections are
     present, not free-form;
  2. label it `type:question`, one `priority:*`, and at least one `area:*`, per
     `docs/governance/github-work-management.md`;
  3. add `- GitHub Issue: #<number>` to the file, positioned per the format
     block in `docs/prd/open-questions.md`;
  4. rename that file's `- 状态：` line to `- 原迁移状态：`, keeping the same
     value — the vocabulary is retained history, not current state;
  5. link the file from the Issue body, so the binding is verifiable from both
     ends.
- [ ] Do **not** copy the question's reasoning into the Issue. The governance
  doc is explicit that retained Specs, Plans, research, acceptance records and
  release evidence are not copied into Issues. The Issue carries the decision to
  be made; the file keeps the context.

**Verification:** for every migrated question, the file names an Issue **and**
that Issue names the file. Script the check rather than eyeballing it — a
one-directional link is the failure mode this Task exists to prevent.

### Task 2 — Prove link integrity mechanically

- [ ] Add a check that fails when a `questions/*.md` file carries a
  `GitHub Issue:` line whose Issue does not exist, or whose Issue body does not
  reference the file back.
- [ ] Decide deliberately where it runs. A check that needs the GitHub API
  cannot sit in the offline conformance suite; `tests/build/ci_github_work_management_test.py`
  already exists from #215 and is the natural home for the offline half (format,
  presence, `原迁移状态` vocabulary). The live half — that the Issue exists and
  links back — belongs wherever the repo is willing to make a network call, or
  nowhere at all, stated plainly.
- [ ] A file with **no** `GitHub Issue:` line is not a failure. It means "not
  migrated yet", and the governance doc says such files retain their live state.
  The check must distinguish "unmigrated" from "migrated and broken".

**Verification:** introduce a broken link, watch the check fail, revert.

### Task 3 — Update the conventions that describe the end state

- [ ] `docs/prd/open-questions.md` already carries the migrated-file format from
  #215. Once migration completes, its sentence about unmigrated files retaining
  live state stops describing anything — revisit it then, not before.
- [ ] `docs/prd/README.md` likewise. Do not pre-edit either to describe a state
  that has not been reached.

**Verification:** `scripts/architecture-portal.sh check`.

---

## Global Constraints

- **One Task creates the Issue and updates the file.** The governance doc
  requires it, and the reason is real: between the two, a question has two live
  states and no authority.
- **Never open a second Issue for a question that already has one.** Three do
  today — see above. A duplicate splits the discussion and both copies then rot.
- **A question Issue closes only after the authoritative Decision, Contract,
  PRD, governance or validation record is merged and linked** — not when someone
  answers in a comment. That is the governance doc's closure rule for
  `type:question`, and it is stricter than for the other types.
- **Do not settle any question while migrating it.** Migration moves where the
  discussion lives; it does not conclude the discussion. A question whose answer
  becomes obvious during migration still needs its Decision file, written in its
  own Task.
- No push, Pull Request, merge, tag, release or Channel promotion is authorized
  by this plan.

## Version Management

**Version impact: none.** Documentation and GitHub Issue state only — no Core
Module, Contract, Provider, Host, Product Assembly, or lock content changes, and
no `module.json` version moves. Task 2 may add a test file, which does not move
any version identity.

## Documentation impact

**Documentation impact: none.**

Reason: migrates `docs/prd/questions/` source state and may add a build-tier
check; no architecture-portal route changes and no manifest-derived facts change.
Task 3 revisits `docs/prd/` conventions only after migration completes, and will
carry its own declaration if it changes a portal-published page.

## Out of scope

- Answering any question. Migration relocates the discussion; conclusions go to
  `docs/prd/decisions/` in their own reviewed Tasks.
- Deleting question files. A file is deleted only in the Task that writes its
  Decision, per `docs/prd/open-questions.md`.
- The `LMDJ Work` Project. Adding migrated Issues to it is portfolio state, and
  the governance doc treats Project membership as a separate transition from
  Issue creation.
- Migrating `docs/quality/` TODO lists. Those already point at Issues #203–#214
  and #167; converting the lists themselves is a different decision.
