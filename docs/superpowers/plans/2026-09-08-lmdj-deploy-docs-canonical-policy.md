# Repair canonical deployment-documentation coverage

## Declared files

- `docs/governance/git-workflow.md`
- `tests/build/creator_web_public_deployment_docs_test.py`
- This plan.

## Defect and boundary

Real bootstrap target `24ee0c4f79e0fe21a89be8813cb0566948583aa4`
failed [Deploy contract](https://github.com/endaye/lmdj/actions/runs/34155431379/job/101846325427)
because its documentation test still demanded release-profile and historical
version text in Git workflow. Commit `c733f968` deliberately centralized those
facts in the canonical version policy, but left that test expecting duplicates.
The same one-of-three failure was reproduced locally before editing.

Git workflow now explicitly links the authoritative Web Host release/deployment
policy in its release section. It does not duplicate the current profile,
asset count or historical version identity. Its replacement assertion resolves
that exact local link and checks every original fact in the actual linked
Web Host policy section. The other five current documents retain their existing
fact assertions. Missing navigation, wrong target, missing canonical section or
missing canonical facts remain red with why/remedy diagnostics.

This changes neither release policy nor deployment behavior, authorization,
version identities or CI lane selection. It runs no release command or remote
mutation. The unrelated shallow-clone CI test failure belongs to another Task.

## Verification

Lowest tier: `python3 tests/build/creator_web_public_deployment_docs_test.py`.
After replacing the duplicate-content expectation, the new navigation test
was observed red before adding the documentation link. Verify the linked
policy facts with the real files, not only synthetic content. Run neighboring
Runtime documentation and both Host workflow contract suites, plus staged
ownership and whitespace checks. Mutation probes must still reject each
missing canonical fact and a wrong link target; they do not edit repository
files. No end-to-end deployment or remote O1 pass is claimed.

Local results: Creator documentation 4 tests, Runtime documentation 10 tests,
and each Host workflow contract suite 16 tests passed. Eight in-memory mutation
probes rejected removal of each of the seven canonical facts and a wrong link
target. Existing assertions on the five other current documents are unchanged.

## Documentation Impact

Documentation impact: none

Reason: Correct a governance reference and its test ownership only. No Portal
page, source diagram, projected identity or documented product fact changes.

## Version Management

Version impact: none

Reason: No Product Build, Host, Module, Provider or Contract changes; no tag,
release, publication, deployment or Channel operation.

Pitfall impact: none. The regression now expresses the complete navigation and
far-side documentation invariant; no new process rule or incident ledger entry
is needed. Apply issue-done verification and stop after the local commit.
