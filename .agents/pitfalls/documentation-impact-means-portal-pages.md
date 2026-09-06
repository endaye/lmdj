---
id: documentation-impact-means-portal-pages
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/594
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/595
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/600
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/603
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/608
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/611
    observed_by: claude-code/opus-5
  - date: 2026-09-04
    occurrence: https://github.com/endaye/lmdj/pull/624
    observed_by: claude-code/opus-5
exit: skill:.agents/skills/issue-done/SKILL.md
---

# `Documentation impact` means Architecture Portal pages, not any file under `docs/`, and the declaration has one exact spelling.

## Why

`check-doc-impact.mjs` reads three lines of the Pull Request body: `Documentation
impact:` must be exactly `required` or `none`; a non-empty `Reason:` line must be
present; and `required` needs an `Affected portal pages:` line of `/`-routes **and**
a changed page under `apps/architecture-portal/docs/`. Nothing else under `docs/`
is portal impact.

Seven Pull Requests in two days declared `required` for `docs/quality/` edits on a
`Routes:` line the gate does not read. Each block refuted itself — the line after
`required` said no portal route had changed — and survived because it was copied
forward from the previous Pull Request rather than written from the diff. The
gate caught it every time it ran; six were merged by hand while it was queued or
red. **A gate that is bypassed teaches nothing.**

The obligation runs the other way too, and no gate covers it: a portal page's
`source_paths` names the repository files it describes, and `validate-docs.mjs`
checks only that they exist. #624 edited two such files, declared `none`, passed
every check, and left `testing-and-proof.mdx` stating something the same Pull
Request had just disproved.

## How to apply

- `required` when a page under `apps/architecture-portal/docs/` changes, **or**
  when Product Build / Assembly identity changes (`products/lmdj/version.json`,
  `assembly(.lock).json`, `CMakeLists.txt`, `src/`) — those cannot declare `none`.
- Before settling on `none`:
  `grep -rl "<changed path>" apps/architecture-portal/docs --include='*.mdx'`.
  A hit whose text your change makes wrong must be updated in the same Task.
- Routes go on `Affected portal pages:`, each starting with `/`. `Routes:` is
  not read.
- Re-read the block against itself: `required` beside "no portal route changed"
  has already answered itself. Never copy a block forward from another Pull
  Request.
- Gate the body before `gh pr create`: `issue-done` §4 writes it to a file, runs
  `scripts/local-ci.sh --pr-body`, then passes `--body-file`. The verdict prints
  first, but `--pr-body` then runs every selected lane — interrupt if the verdict
  is all you need. After a fix, a rerun replays the stale event; push or reopen.
- Do not merge past this gate by hand.
