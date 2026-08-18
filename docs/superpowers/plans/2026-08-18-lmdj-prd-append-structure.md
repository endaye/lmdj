# LMDJ PRD Append Structure Plan (C2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Close machine task C2: restructure `docs/prd/decision-log.md` and
`docs/prd/open-questions.md` so concurrent branches stop colliding. Both files
are append-at-the-end today, and `open-questions.md` additionally carries a
shared `更新时间` line that every session edits, so every pair of parallel
sessions that records a decision or touches a question conflicts on the same
lines. Stage 8b paid for this on its final sync.

**Architecture:** Documentation only — `docs/prd/` plus the two quality
ledgers that track C2. No Core Module, Application Facade, Contract, Provider,
Host, Product Assembly, script, or CI change.

**Chosen fix shape:** the triage offered "dated section files with an index,
or an append convention that keeps concurrent additions apart". This plan
takes one-entry-one-file directories **without a hand-maintained per-entry
index**, because any index file that must be edited on every addition is
itself a shared append point and recreates the collision the task exists to
remove. Date-prefixed filenames make the directory listing the chronological
index.

- New confirmed decisions become individual files in `docs/prd/decisions/`,
  named `YYYY-MM-DD-<slug>.md`. Parallel sessions create distinct files and
  never share an append point.
- Every open question becomes an individual file in `docs/prd/questions/`,
  named `<slug>.md`, carrying its own scope, status, and rationale. Status
  edits touch only that question's file; a new question is a new file; the
  shared `更新时间` line disappears.
- `docs/prd/decision-log.md` keeps its canonical path (CLAUDE.md, AGENTS.md,
  README.md, and 30+ documents link it, none with fragment anchors — verified
  2026-08-18) and becomes the entry point: a convention header plus the frozen
  2026-07-02 … 2026-08-16 historical archive, byte-preserved and closed to
  further appends. History is immutable decision record; migrating 476 lines
  into ~40 files would be a large mechanical diff with no collision benefit,
  since closed entries are never appended to.
- `docs/prd/open-questions.md` keeps its canonical path and becomes the
  convention page pointing at `questions/`. Unlike decisions, questions are
  live state (statuses change), so all 18 open rows migrate; the table form
  remains in git history.

## Global Constraints

- Execute only on `docs/prd-append-structure` in
  `/Users/endaye/Projects/lmdj/.worktrees/prd-append-structure`. Never on
  `main`.
- Migration is content-preserving: every question's 问题 / 为什么重要 /
  处理时点 / 状态 text carries over verbatim (formatting may change from
  table cell to list item); no question is dropped, added, reworded, or
  re-statused. This task settles no open product question.
- The two canonical paths `docs/prd/decision-log.md` and
  `docs/prd/open-questions.md` continue to exist; no link elsewhere in the
  repository needs to change.
- Every Task is one reviewable Conventional Commit. Before every commit:
  verify the branch is not `main`; run `scripts/architecture-portal.sh check`;
  stage only declared files; inspect `git diff --cached --name-status` and
  `git diff --cached --check`; after committing inspect
  `git show --name-status --oneline HEAD`.
- Local commits only. Push, PR, merge, and every later state transition need
  separate explicit authorization.

## Tasks

### Task 1 — Restructure the two files and their directories

- [x] Create `docs/prd/decisions/README.md`: naming rule
      (`YYYY-MM-DD-<slug>.md`, confirmation date, lowercase kebab-case slug),
      one decision per file (one review producing a batch like S8-D1–D13 may
      share a file), entry template (`已确认` heading; 日期 / 结论 / 原因 /
      影响 list), no per-entry index, corrections are new dated files that
      link the superseded entry, and the rule that a decision resolving an
      open question deletes the matching `../questions/` file in the same
      Task. This README also keeps the directory tracked while it waits for
      its first entry.
- [x] Rewrite the header of `docs/prd/decision-log.md`: from 2026-08-18 new
      decisions are files under `decisions/`; everything below is the
      2026-07-02 … 2026-08-16 archive, closed to appends and edits. The
      archived sections themselves stay byte-identical.
- [x] Migrate all 18 open questions to `docs/prd/questions/<slug>.md`, each
      with 范围 / 状态 / (optional 来源) / 为什么重要 / 处理时点. The 新内核
      section preamble becomes those six files' 来源 line.
- [x] Rewrite `docs/prd/open-questions.md` as the convention page: file
      naming, entry format, the existing status vocabulary, lifecycle (new
      question = new file; resolved question = file deleted in the Task that
      writes the decision entry), no per-entry index, and a note that the
      pre-2026-08-18 table lives in git history.
- [x] Update `docs/prd/README.md` so 文档分工 and 推荐迭代节奏 describe the
      two directories instead of in-file appends.
- [x] Extend the frontmatter `source_paths` of the two portal pages that
      declare these files as sources —
      `apps/architecture-portal/docs/product/positioning.mdx` (both files)
      gains `docs/prd/decisions/` and `docs/prd/questions/`, and
      `apps/architecture-portal/docs/platform/input.mdx` (open questions
      only) gains `docs/prd/questions/` — because the content those pages
      cite now physically lives in the directories. Page bodies are
      unchanged; `page-metadata.mjs` validates `source_paths` by existence
      only, which directories satisfy.

**Verification:** `scripts/architecture-portal.sh check` passes; question
count in `questions/` is exactly 18; spot-grep confirms each migrated
question's text appears verbatim in its file; `git diff --cached --check` is
clean.

### Task 2 — Close the C2 ledger entries

- [x] Mark C2 done in `docs/quality/2026-08-17-machine-task-todo.md` (table
      row and suggested-order item), naming Task 1's commit.
- [x] Mark section C2 fixed in
      `docs/quality/2026-08-16-outstanding-work-before-stage9.md`, recording
      the chosen shape and why no index file exists.

**Verification:** `scripts/architecture-portal.sh check`;
`git diff --cached --check`.

## Version Management

**Version impact: none.**

- `docs/prd/` and `docs/quality/` are unversioned repository documentation:
  no Core Module, Provider, Host, Contract, or Product identity is touched,
  and no Product Build is allocated. The version policy's plan requirement is
  satisfied by this section and this reason.

## Documentation impact

**Documentation impact: required.** Affected portal routes:
`product/positioning` and `platform/input` — frontmatter `source_paths`
only, no rendered content change, because those two pages declare
`docs/prd/decision-log.md` / `docs/prd/open-questions.md` as sources and the
cited content now also lives in `docs/prd/decisions/` and
`docs/prd/questions/`. No identity is hand-entered: the portal derives
Product, Module, Host, Provider, Contract, and Channel identities from
active manifests, and this change touches none of them. No Product Build or
Assembly change, so no snapshot is required. Run
`scripts/architecture-portal.sh check` before every commit.

## Out of scope

- Migrating the historical decision archive into per-entry files — closed
  entries have no append pressure, and the diff would be noise.
- Answering, rewording, or re-statusing any open question — C2 is structure
  only; the "do not silently settle open questions" rule stands.
- A generated index or tooling for these directories — `ls` over
  date-prefixed names is the index; new scripts would add verification
  surface with no collision benefit.
- The other quality-ledger tasks (B3, B4, C4, C5, C6) — separate plans.
