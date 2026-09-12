# R3b.1: frozen source-accounted Product changelog

Status: locally verified artifact module, stacked on release driver `41e15c82`.

## Scope

Implement the common structured source and Markdown payload for both release
changelog destinations. Select the unique nearest published same-profile Product
ancestor from the canonical ledger, not floating latest, tag-number sorting or
unpublished candidates. A true first release records its full Git history.
Unknown or ambiguous prior history fails closed. The caller must independently
audit the selected baseline's signed tag and public Release; a ledger flag is
not that audit.

Bind tag, derived Product Build, candidate target, profile, baseline and complete
ordered commit inventory. Each source commit must appear exactly once in a
feature/fix/compatibility/known-issue entry or a reviewed exclusion reason.
User-visible entries distinguish Creator, Runtime, Core and release work.
Use actual commit links; never invent PR linkage from a number in a subject.
Plain-text, bounded editorial content is rendered once for both destinations.
Freeze the structured-content and rendered-notes digests. The source validator
re-enumerates exact Git evidence and refuses changed scope.

Source membership does not prove semantic correctness, reverted functionality,
acceptance or secret absence. The evidence PR reviewer must inspect those claims
and exclusions; this module does not automatically publish commit messages.
Git reads discard ambient Git environment/config injection and replace objects,
reject shallow graphs, and do not fetch or mutate the user's repository.

Declared files:

- `tools/release/changelog.py`
- `tests/build/release_changelog_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-frozen-changelog.md`

This Task supplies the shared frozen artifact; prepare/plan binding, all Draft
and published-body validators, portal generation and live two-destination proof
remain subsequent R3b/R3c work. Do not declare the changelog journey complete
from a green artifact test. No Product release is initiated.

## Verification

`python3 tests/build/release_changelog_test.py` uses real temporary Git histories
for first release, nearest and ambiguous baselines, nonancestor history, complete
accounting, frozen scope drift, replacement objects, ambient Git injection,
shallow history, unsafe text and deterministic shared rendering. The existing
release test glob and explicit CMake registration execute the new suite.
Run staged ownership, Python compilation, Portal check and independent review.
No gate, coverage floor or timeout is weakened.

Verified 2026-09-13: 17/17 changelog tests, 74/74 staged ownership tests,
Python compilation and Portal check (46 routes/internal links), all exit 0.
Independent review found legacy Git grafts could hide real commits; the reader
now fixes `GIT_GRAFT_FILE` to the null device. Real normal-repository and linked
worktree regressions verify the complete original range. Re-review found no
remaining actionable findings. No new pitfall entry: this exact source-graph
defect is expressed by the regression tests. No remote acceptance was performed.

## Version Management

Version impact: none

Reason: internal release tooling only. No Product Build is allocated; no Module,
Host, Provider or public Contract identity changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document the artifact's verified boundaries and remaining publication
integration without implying an active two-destination release workflow.
