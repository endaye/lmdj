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
  - date: 2026-10-08
    occurrence: https://github.com/endaye/lmdj/pull/1876
    observed_by: Codex
  - date: 2026-10-11
    occurrence: https://github.com/endaye/lmdj/issues/2031
    observed_by: unknown
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

- `required` when a page under `apps/docs-site/docs/` changes, **or**
  when Product Build / Assembly identity changes (`products/lmdj/version.json`,
  `assembly(.lock).json`, `CMakeLists.txt`, `src/`) — those cannot declare `none`.
- Before settling on `none`:
  `rg -l --fixed-strings "<changed path>" apps/docs-site/docs -g '*.mdx'`.
  A hit whose text your change makes wrong must be updated in the same Task.
- Routes go on `Affected portal pages:`, each starting with `/`. `Routes:` is
  not read.
- Re-read the block against itself: `required` beside "no portal route changed"
  has already answered itself. Never copy a block forward from another Pull
  Request.
- Gate the body before `gh pr create`: `issue-done` §4 writes it to a file, runs
  `scripts/local-ci.sh --declaration-only --pr-body`, reads its actual terminal
  exit, then passes `--body-file`. This command executes no lanes. Revalidate
  a corrected or changed body before publishing it; preserve any earlier failure.
- Read every required prerequisite's actual terminal result before its dependent
  commit or PR operation. Nonzero, signal or missing terminal status stops that
  operation; a returned tool receipt or later successful command cannot clear it.
  Keep advisory checks advisory. `issue-done` §3–§4 owns this result ordering.
- Do not merge past this gate by hand.

The 2026-10-11 recurrence retained a missing-`Reason:` declaration failure and a
precommit inspection failure, followed by a local commit. The author corrected
both checks and preserved the preliminary object. The recorder propagated child
exits correctly; the calling shell's outer verdict and original inspection
expression were not retained. #2031 records the provenance and skill repair.
