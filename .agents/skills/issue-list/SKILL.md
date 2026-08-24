---
name: issue-list
description: Universal skill to query, classify, and list open GitHub issues and pending project tasks, identifying parallel-executable workstreams across domains.
---

# Issue List (Open Task Triage & Parallel Streams)

This skill enables coding agents (**Antigravity**, **Codex**, **Claude Code**, **Kimi**, **Cursor**, **GitHub Copilot**) to query open GitHub issues, cross-reference project task lists (`docs/quality/2026-08-17-machine-task-todo.md` and `docs/quality/2026-08-17-manual-verification-todo.md`), classify them by readiness and ownership boundaries, and output actionable, parallelizable workstreams.

---

## 1. How to Query Current Issues

1. **Query GitHub Live Issues**:
   ```bash
   gh issue list --state open --limit 50 --json number,title,labels,assignees
   ```
2. **Cross-reference Project Task Ledgers**:
   - `docs/quality/2026-08-17-machine-task-todo.md` (Machine-executable tasks & blockers)
   - `docs/quality/2026-08-17-manual-verification-todo.md` (Human verification & decision gates)
   - `docs/prd/questions/` and `docs/prd/decisions/` (Architecture decisions)

---

## 2. Classification & Independence Rules

When listing and recommending tasks, categorize each item into one of four states:

1. **Ready Machine Tasks**: Concrete engineering tasks with no open design blockers. Can be implemented autonomously in isolated worktrees.
2. **Architecture / Question Issues**: Decision or Contract questions requiring a decision record under `docs/prd/decisions/` before implementation.
3. **Physical / Manual Verifications**: Tasks requiring real hardware (macOS Safari, iPadOS touch, physical MIDI, acoustic microphone tests).
4. **Blocked Tasks**: Blocked on a specific upstream decision gate (e.g. P2, F4, F6, D1-D5).

---

## 3. Identifying Parallel Workstreams

To avoid git merge conflicts and domain coupling, assign parallel tasks to distinct active source boundaries:

- **Stream A (Tooling, Release & Packaging)**: `scripts/`, `tools/release/`, `packaging/`
- **Stream B (Core & Provider SDK)**: `packages/authoring-domain/`, `packages/provider-sdk/`, `providers/`
- **Stream C (Creator Web & UI)**: `apps/creator-web/`, `packages/web-runtime-platform/`
- **Stream D (Architecture Decisions & Docs)**: `docs/prd/decisions/`, `docs/governance/`

Two tasks in different streams can always be worked on simultaneously in separate git worktrees.
