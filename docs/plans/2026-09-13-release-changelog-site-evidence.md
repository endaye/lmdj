# R3c.5: authenticate retained Portal changelog deployment evidence

Status: locally verified implementation, stacked on `8985ebd8`;
not pushed, merged, configured or production-exercised.

## Scope

Add a read-only consumer and closed GitHub GET transport. Reviewed controller
configuration supplies numeric repository/workflow identities and the minimum
trusted producer commit; no artifact may select them. Authenticate protected
main ancestry using real Git without executing source code or fetching objects.
Derive the complete expected page inventory and source hashes from the source
commit's ledger and publication records. The selected publication must match
the caller's freshly verified Release record and descend from its target.

Require the exact successful first-attempt main push, successful deployment
steps, unique unexpired artifact, API SHA256 matching bounded downloaded ZIP,
and exact safe member identity. Validate Preview/production URLs, Worker version,
every page's source/response identity and matching rendered-content hashes.
Reobserve run and protected main at the end. Incomplete run is pending; missing
observations are unverifiable; conflicting evidence never yields success.

The authenticated producer owns HTML comparison; this consumer does not
independently reconstruct rendered content from response hashes. It certifies
retained observations, not current live Worker state. Production backend
configuration, merged evidence-PR authentication, fresh live-site smoke and
driver admission remain required. No release, deployment, PR or signing action
is introduced. Append-only corrections and the complete run/resume journey are
still unfinished.

Declared files:

- `tools/release/changelog_site_evidence.py`
- `tools/release/github_api.py`
- `tests/build/release_changelog_site_evidence_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-changelog-site-evidence.md`

## Verification

Use real temporary Git histories and the production GitHub transport with
fixture API responses and ZIP bytes. Assert successful repeated reads do not
mutate Git, and independently reject identity, step, retention, archive, page,
publication and mid-observation state drift. API errors must not expose secrets.
Run API/batch/site regressions, staged path ownership, full Portal check and
independent read-only review. These fixtures do not prove real GitHub artifact
availability, public HTTPS state or release-controller operation.

Initial fixture run failed because the synthetic ZIP response lacked the
required Content-Type; corrected the fixture, not the production check. Logs
remain `/tmp/lmdj-site-evidence-tests.log` and subsequent `-v2`/`-v3` logs.
Consumer tests passed 16/16, API regressions 39/39, batch evidence regressions
68/68, page projection 7/7, staged ownership 74/74 and Python compilation
(all exit 0). Independent reviewer `/root/release_journal_review` inspected
all six files, independently ran the 16 consumer tests, and found no actionable
finding. No remote API or provider was called during review.

The first Portal check used an incorrectly narrowed command PATH and selected
system Python 3.9, failing the existing StrEnum import. The rerun restores the
existing Python 3.11 PATH while selecting Node 22; no test/code relaxation.
Original failure remains `/tmp/lmdj-site-evidence-docs.log`. The existing locked
npm install reported 27 dependency advisories; no unrelated dependency changes
or automatic audit fixes are included. These are not resolved by this Task.

Full Portal rerun passed 139/139 tests, production build and 47 routes/internal
links (exit 0), retained in `/tmp/lmdj-site-evidence-docs-v2.log`. Other raw
results use `/tmp/lmdj-site-evidence-` with `tests-v3`, `api`, `batch`,
`projection` and `scope` `.log` suffixes. No suite was skipped to obtain these
results; real release/deployment acceptance remains unexecuted.

The Task's rejection invariants are expressed in regression tests; no new
process-only pitfall entry is needed. The implementation stack remains local
behind PR #1266's unresolved review-adoption boundary.

## Version Management

Version impact: none

Reason: internal read-only evidence verification; no Product Build, Assembly,
Module, Provider or public Contract identity changes and no snapshot mutation.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish authenticated retained observations from live-site proof.
