---
id: revert-proof-rebuild-skipped
area: core
status: absorbed
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/769
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/issues/1058
    observed_by: Claude Code (Opus 5)
exit: skill:.agents/skills/issue-done/SKILL.md
---

# Proving a change by reverting it silently tests a stale binary when the restore moves a file's mtime backwards

## Why

The standard way to prove a behavioural change is load-bearing is to revert it,
rebuild, and watch the specific assertion fail. The revert is usually done by
restoring files from a snapshot taken before the experiment — `tar x`, `cp -p`,
or anything else that preserves timestamps. Those restore the file's *original*
mtime, which is older than the object file produced by the intervening build,
so `make` decides the translation unit is up to date and skips it. The test
then runs against the previous binary.

Both directions of the resulting evidence are wrong and both look right:

- Restoring the real change after an experiment leaves the experimental binary
  in place, so the suite "passes" without the change compiled in.
- Restoring a snapshot before a fresh experiment leaves the previous
  experiment's binary in place, so an assertion fails at a line that has
  nothing to do with the change under proof — in this Issue, a `project_store`
  proof reported a failure inside a test `main()` was no longer even calling.

Nothing in the build output says this happened; `scripts/core.sh build dev`
exits 0 because it genuinely had nothing to do. The defect is in the
verification method, not in any product code, so no product test can catch it.

## How to apply

- Restore with `tar xmf` (do not preserve mtimes), or follow any
  timestamp-preserving restore with `xargs touch < <file list>`.
- Never send a proof rebuild to `/dev/null`. Capture its exit status and read
  it: `scripts/core.sh build dev >/tmp/b.log 2>&1; echo build=$?`. A proof run
  after a failed build is not evidence of anything.
- Check that the reported failure line is inside the test you are proving. A
  failure at an unrelated line, or in a function the current `main()` does not
  call, means you are looking at a stale binary — not at a second defect.
- When a single-assertion proof needs one test to run first, reorder the call
  in `main()` rather than deleting the other calls: `-Werror=unused-function`
  will fail the build, and a skipped build is exactly what hides the problem.

## Second occurrence, 2026-09-09: the same mechanism with `.pyc`

Perturbing `apps/core-mcp/lmdj_core_mcp/__init__.py`, then restoring it with
`cp`, left the restored file older than
`__pycache__/__init__.cpython-*.pyc`. Python reused the bytecode of the broken
version, so the run *after* the restore still failed on the perturbation's own
line while `grep` showed the source was already correct. Deleting
`__pycache__` made it pass immediately.

The dangerous direction is the other one. If the restore precedes the
*breaking* run, a perturbation that never actually took effect reports green,
and a perturbation proof that proves nothing gets written into a report as if
it did.

The recurrence-2 escalation [#1058](https://github.com/endaye/lmdj/issues/1058)
exits to a skill rule: which artifact a proof runs against is a verification
method, not a derivable product invariant, so no gate qualifies. `issue-done`
§1 now fixes the discipline — restore with `git checkout --` / `git stash`
(current mtime, never a timestamp-preserving `cp`/`tar` rollback without a
follow-up `touch` and `__pycache__` clear), capture the proof rebuild's exit
status, and confirm the failure line sits inside the test under proof.
