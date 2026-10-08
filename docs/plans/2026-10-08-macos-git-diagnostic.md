# macOS real-Git verification diagnosis — #1878

## Task and declared files

Absorb the second `macos-git-launch-overhead` occurrence into the CI-triage
skill. A real-Git lane timing out on macOS must be profiled before selecting
an equivalent command-local launcher, and completion requires the original
complete lane with its original bounds.

Declared files:

- `.agents/skills/lmdj-review-ci-triage/SKILL.md`
- `.agents/pitfalls/macos-git-launch-overhead.md`
- `docs/plans/2026-10-08-macos-git-diagnostic.md`

The skill owns the diagnostic procedure; the absorbed pitfall retains the two
historical occurrences and points to that procedure. No launcher, PATH, test,
CI trigger or required gate changes in this Task.

## Verification

- Baseline and final `python3 tests/build/ci_pitfall_ledger_test.py`: validate
  the absorbed entry and its existing skill target.
- After staging the declared files, `python3 tests/build/ci_change_scope_test.py`:
  verify ownership of the added plan.
- Review the procedure against both recorded incidents: symlink relocation
  failed exec-path/template equivalence; slower wrappers failed the cost
  justification; a passing prefix/interrupted profile failed completion.
- Check the full diff and whitespace, then classify the committed head and
  validate the PR body and applicable batch-only evidence before merge.

This is skill guidance, not a deterministic performance gate or a rerun of the
Deploy Contract lane. PR #1876 records the subsequent complete 1,865-case pass
under an equivalent command-local environment; earlier failed and interrupted
runs remain historical failures.

## Version Management

Version impact: none

Reason: agent verification guidance changes no Product, Assembly, Module,
Host, Provider or Contract identity.

## Documentation Impact

Documentation impact: none

Reason: this agent workflow and pitfall absorption change no Architecture
Portal page, projected identity, source diagram or product behavior.

## Pitfall Impact

Absorb `macos-git-launch-overhead` into the existing CI-triage skill. Preserve
both recorded recurrences; this mechanism delivery is not a third occurrence.
