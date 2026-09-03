---
id: gate-matches-its-own-prose
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/587
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/603
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/607
    observed_by: claude-code/opus-5
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A gate that scans source text matches the comment explaining what it forbids, so it fails on the very file it was written to bless.

## Why

The repository's CI contracts are text scans: they read a workflow or a module
and assert a string is present or absent. The absent case has a blind spot.
Anything worth forbidding is worth explaining, the explanation sits in a
comment in the same file, and the scan reads comments and directives alike.

Three occurrences in one day, each a different gate:

- PR #587: the Core benchmark contract asserted `"PR Gate" not in source` and
  `"ci-web-heavy" not in source`, while the workflow's header comment named
  both to say what the lane is *not* and which lane it is the counterpart of.
- PR #603: `ci_classification_inputs_test.py` bans classification modules from
  referencing an exempted policy file, and the comment introducing the
  exemption named that file. The gate matched its own explanation.
- PR #607: the Claude review contract asserted `"PR Gate" not in source`, and
  again the header comment said the lane is not part of the PR Gate.

The failure is loud rather than silent, so nothing ships broken. The cost is a
diagnosis cycle each time, and a standing temptation to loosen the assertion --
which would trade a real invariant for a comfortable one.

## How to apply

- When a contract test asserts a string is **absent**, scan the directives
  rather than the raw source. Strip full-line comments first:

  ```python
  self.directives = "\n".join(
      line for line in source.splitlines()
      if not line.lstrip().startswith("#")
  )
  ```

  Presence assertions can keep reading the raw source; only absence has the
  blind spot.
- Where stripping comments is not enough because the banned string is a path
  the file must also declare, constrain the declaration instead of loosening
  the gate. `change_scope.py` carries that rule inline: name the exempted paths
  only in the declaration, never in prose beside it. Loosening the match to
  accommodate prose is what turns a gate into decoration.
- No mechanical exit. A test that a test scans the right text would need the
  same blind spot solved one level up, and the failure is loud enough that
  guidance at the point of authorship is proportionate. Escalate if it recurs
  after this is in `issue-done`.
