---
id: clean-text-merge-breaks-the-build
area: ci-release
status: open
recurrences:
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/pull/1766
    observed_by: Claude Code (Opus 5.5)
exit: none
---

# A Pull Request that GitHub reports `MERGEABLE` can still break main's build when main has advanced past its base

## Why

`mergeable` is a textual three-way merge. It says nothing about whether the
merged tree compiles. An ordinary Pull Request is not required to update when
main advances, and its batch-only lane evidence describes its own head, not the
merge result.

#1766 was verified on its head against base `738a3e48` and squash-merged as
`b76cf207`, which did not compile. Two changes had landed on main in between:

- **#1768 and #1766 each added one operation** to the bridge's
  `std::array<std::string_view, N>` inventory, and each sized it 94. Both edits
  of the size line were identical, so the merge took 94 once and kept both
  entries: 95 initialisers for 94 slots.
- **#1771 changed the Domain helper `applied()`** to return
  `Result<AppliedCommand>` in place. #1766's new handler still wrapped the
  result in `success(...)`.

Neither is a conflict to Git, and neither PR's own tests could see the other.

## How to apply

Before squash-merging a PR whose base is behind main:

1. List main's commits since the PR's base that touch the PR's files, or the
   helpers and inventories it calls or extends:

   ```bash
   git log --oneline <base>..origin/main -- <files>
   ```

2. If any exist, build the merge result before merging: a worktree at
   `origin/main` with the exact head merged in. Run the affected tests there.
3. Treat these as conflicts even when Git does not:
   - counted inventories (`std::array<…, N>` lists, pinned operation and API
     lists in tests);
   - signature or ownership changes to shared helpers;
   - renamed or relocated functions.

This entry has no mechanism yet. The ordinary-PR policy deliberately carries no
strict-update or full-CI merge gate, so requiring a merge-result build is an
owner governance decision rather than something to add under a Task's
authority. Until then it is a manual pre-merge step.
