# Restore post-squash Portal provenance for CI integration

## Scope

Supporting Task for the CI simplification: rebasing T4 onto merged PR #761
exposed a missing authenticated source-tree witness. The existing snapshot
verifier failed closed and named the exact generator command. This Task
retains the immutable snapshot, identities, and verifier unchanged.

Declared files:

- `apps/architecture-portal/versioned_provenance/version-1.0.43.0-squash-witness.json`
- `.agents/pitfalls/squash-witness-provenance.md`
- `.agents/skills/issue-done/SKILL.md`
- `tests/build/ci_self_test_report_workflow_test.py`
- This plan.

Generate the proof with the stable Portal interface using the existing
metadata identity and the introducing squash revision reported by the checker:

```bash
scripts/architecture-portal.sh witness 1.0.43.0 ee5a9a18f4d43873f2ebf4622fe2439318753614
```

The generated data reconstruct the authenticated source tree; they are not a
new snapshot, version allocation, tag, Release, deployment, or promotion.
Move conditional post-merge follow-through into the ordinary shipping skill,
where Product Build cuts actually finish, without adding a universal gate.

The same integration also exposed T3's undeclared PyYAML test dependency in
real CI run 34125274822, job 101752447034. Replace that import with the existing
standard-library workflow inventory and explicit block checks, retaining all
ten assertions, including the actual Bash retry invocation. Verify with
`python3 -S` so local site packages cannot mask a missing runner dependency.

## Verification

- Original failure: latest-main T4 `check:release-docs` reported that source
  projection is neither direct-parent nor squash-equivalent and the witness
  is unavailable.
- After generation: the unchanged `check-release-docs.mjs` accepts the proof.
- Before commit: full Portal check, CI contract tests including staged path
  ownership, skill validation, generated proof identity/tree reconstruction,
  staged whitespace and exact declared-file review.

Documentation impact: none
Reason: This supporting Task adds authenticated provenance and conditional
shipping guidance, without changing current Portal pages or allocating a
Product Build. The containing T4 PR separately declares its current-page edit.

## Version Management

Version impact: none — the existing Product Build identity and immutable
snapshot are unchanged; this only supplies their missing post-squash proof.
