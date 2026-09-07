# T4b — Fixed-Issue GitHub Journal Transport

Status: adapter implementation only; no online state initialization, permissions,
workflow triggers or remote mutations. Parent Task owns review and shipping.

## Declared Files

- `scripts/ci/batch_github_journal.py`
- `tests/build/ci_batch_github_journal_test.py`
- This plan.

## Interface

`GitHubJournalTransport` implements T3's `read_body`, `write_body`, `page`,
`append` and an `authenticate` callback. Configure fixed repository, Issue
**number** (T3's `issue_id` argument), Issue node ID, Bot node ID and explicit
workflow path-to-ID inventory. `writer` records repository/Issue number, run ID,
attempt 1, control SHA, workflow path/ID and actual workflow **job display name**.
The display name only locates a job inside the independently checked run; it
does not authenticate a workflow. A run's actor need not be the writing bot.

Instantiate one transport per short controller transaction. Its cache of checked
writer provenance is transaction-local, not durable trust. Reads validate the
platform metadata before yielding the private in-process projection; callers
must never feed arbitrary input to the `authenticate` projection callback.

The API client is the existing `self_test_report.UrllibGitHubApi`, normal JSON
mode only: no redirects, no automatic retries. Embedded Issue JSON is bounded,
closed and rejects duplicate keys/nonfinite values. GraphQL data/errors and
strict types are checked; all comments are traversed by cursor and total count,
all run jobs by explicit total and pages. API response JSON itself is decoded by
the existing GitHub client, not a second custom HTTP stack. The fixed API service
produces that outer envelope; user-controlled journal text is separately parsed.

State objects wrap `{schema,kind,writer,payload}`. Checkpoint payload remains
T3's `{head,pending}`; comment payload is its chain envelope. The transport does
not execute workflow source, journal data, model text or PR text. It verifies
the referenced workflow file exists at control SHA, main ancestry by exact
comparison merge-base, repository/workflow/run identity and a unique writer job.
Run/job may be in progress or later failed: success is not required to recognize
a write made before a lost response. Missing or expired producer API identity
blocks reconciliation instead of silently authenticating by its body claim.
Read the exact recorded run attempt, not the mutable latest-run endpoint: a
later operator rerun must not invalidate legitimate historical attempt-1 writes.
The writer job must independently report attempt 1 as well. Both regressions
were observed failing before the exact-attempt lookup and job check were fixed.

Writing requires the shared lock callback and an existing authenticated fixed
checkpoint. It never creates an Issue or initializes/rebuilds a missing body.
Body PATCH and comment POST are each attempted once; T3 owns pending-intent
reconciliation. The same Issues service failure blocks both checkpoint and
comment persistence. Errors omit raw body, URL responses and credentials.

## Operational Trust, Not a Signature

All repository-controlled automation with the shared Actions bot/token belongs
to the trust domain. GitHub does not expose a writer workflow/run on Issue or
IssueComment, so a self-reported run verified to exist is **not independent proof
that this write came from that run**. No secret, App, permission or cryptographic
claim is added. Malicious administrators or compromised trusted write tokens
are outside this guarantee; ordinary manual edits and tail deletion remain
detectable through edit metadata and T3's separate checkpoint object.

Comments must have null editor and lastEditedAt and the exact trusted Bot node
ID. Body writes intentionally edit: use the current editor when edited and
otherwise the original author. Never compare `updatedAt` with creation time.
On 2026-09-08, independent read-only inspection of Issue #782 and comment
5573637240 observed Issue updatedAt changing through comment activity while
editor/lastEditedAt stayed null; GraphQL Bot login was `github-actions`, REST
login was `github-actions[bot]`, and stable GraphQL Bot node ID was
`MDM6Qm90NDE4OTgyODI=`. GraphQL fullDatabaseId values were JSON decimal strings,
not Issue numbers. Tests use those metadata shapes, not copied production state.

Platform sources:

- [Issue and comment fields](https://docs.github.com/en/graphql/reference/issues#issuecomment)
- [Run-attempt job pagination](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run-attempt)
- [Commit comparison](https://docs.github.com/en/rest/commits/commits#compare-two-commits)

## Verification and Remaining Acceptance

Run the new transport suite, T3 journal and reducer suites, then staged ownership
`ci_change_scope_test.py`; inspect the complete declared diff before commit.
No new required gate is added. Tests distinguish fixed identity, metadata edit
handling, exact API method/path, strict parsing, page completeness, missing
checkpoint, no-lock writes, and intent→POST→checkpoint response-loss recovery.

Fixtures are not remote acceptance: O1 must demonstrate actual body/comment
editing metadata, runtime job names, policy-controlled lock ownership, response
visibility, complete remote paging, missing-state initialization audit, and the
real workflow's write→recover journey. No live endpoint was mutated by this Task.

## Documentation Impact

Documentation impact: none — unwired internal transport; no Portal page or
projected product source identity changes.

## Version Management

Version impact: none — internal CI protocol only; no product/module/host/provider
or product Contract identity, version allocation or publication action.

Pitfall impact: none — existing API visibility, authorization and fixture
strictness ledger guidance applied; planned test faults are not production
incident recurrences.
