# Bounded concurrent journal provenance reads

## Evidence and scope

Production controller `34189876280/1` spent 95 seconds in control, 214 seconds
in reports and 61 seconds in discovery. This is a rollout-burst observation,
not a normal-load baseline. Its original log is retained at
`/tmp/lmdj-report-callback-diagnosis.A7A0xC/backlog-controller.log`.
Every cold transport serially authenticates historical writers through complete
run, workflow, main ancestry, source and job reads. The business limit does not
bound this read latency. Do not replace authentication with trusted hashes.

## Task

One control-plane Task, declared files:

- `scripts/ci/batch_github_journal.py`
- `tests/build/ci_batch_github_journal_test.py`
- this plan

Authenticate independent unique writers in each complete comment page with at
most four simultaneous read operations. Preserve all existing checks, complete
pagination, original record order and fresh anchor/comment reads. Finish every
authentication before returning its page; any failure must prevent replay and
writes. Do not share mutable pagination state between workers. No workflow,
permission, writer-lock, persisted-schema, lane or retry-budget changes.

Inspect the real HTTP adapter's thread-safety before selecting the mechanism.
If safe bounded concurrency requires a broader transport change, amend this
declared scope before implementing it; do not assume thread-safety from mocks.

## Verification

Baseline: `python3 tests/build/ci_batch_github_journal_test.py` passed 37 tests.
Add deterministic synchronization-based tests for actual overlap and the bound,
duplicate-writer handling, stable output order, a failed writer yielding no
page or write, full pagination refusal and fresh post-append reads. Retain all
existing provenance-negative tests. Run the complete CI contract suite, staged
new-file ownership and nonempty-range docs/static checks before shipping.

Compare actual read-only production-journal authentication with the serial
baseline, retaining complete envelopes and identical replayed state. Local
fixtures alone do not establish GitHub latency or rollout acceptance. After
merge, measure actual controller step times without claiming a single burst
measurement is steady-state capacity. O2, schedule recovery and final idle
remain separate incomplete acceptance journeys.

### Local implementation evidence

The production HTTP adapter creates a separate Request, opener and response
per call; it holds no shared request session. Workers use only the existing
GET authentication path. Trust-cache publication and pagination state remain
on the caller thread, after every reader has joined successfully.

The original 37 transport tests and eight new transport tests pass (45 total).
The overlap regression failed against the serial source before the change.
Root review and a separate initial 44-test run also passed; the final added
negative distinguishes complete writer identities within the same run.
Three synchronized regressions passed another 50 rounds (150 tests).
The final full CI contract suite passed 1711 tests, zero skips, with pinned
actionlint 1.7.12 and ShellCheck 0.9 available. Staged ownership passed 66 tests.
Production-HTTP timing comparison did not complete: two local serial samples
and one concurrent sample failed on API reads. The latter samples observed HTTP
200 followed by JSON parsing failure, not a proven rate-limit response. All
failed samples remain retained and no speedup ratio is computed.

A separate strict read-only `gh api` adapter supplied real GitHub responses to
the unchanged concurrent journal transport: 166 successful requests, all 59
complete authenticated records exactly equal to the prior serial-authenticated
snapshot, and identical fresh before/after anchors. Root independently compared
the complete records and anchors. This is transport-logic evidence, not evidence
for production HTTP performance. The initial local replay lacked the newly
merged main Git object; an ordinary fetch supplies it without repeating any
remote journal read. Retain that initial failure as well as the completed replay.

Evidence directories: `/tmp/lmdj-journal-serial-http-baseline`,
`/tmp/lmdj-journal-serial-http-retry`, `/tmp/lmdj-journal-parallel-http-final`,
and `/tmp/lmdj-journal-parallel-gh-logic`. Actual hosted timing and O2 remain
unverified until measured after rollout; no local result declares them complete.

Pitfall disposition: no new entry. The settled implementation invariants are
captured by the transport regressions. The existing burst-sample guidance is
applied by retaining this measurement's rollout-load qualification.

## Version Management

Version impact: none. This is internal CI transport scheduling only; no product,
module, provider, Host, Contract or release identity changes.

## Documentation Impact

Documentation impact: none
Reason: internal independent read scheduling preserves the documented CI
protocol, authority, test scope and operator interfaces; no Portal facts change.

## Authority

Related CI commit, push, PR and exact-head-reviewed squash merge are authorized.
Retain worktrees and branches. No release, deploy, protection change, destructive
fault injection or additional permissions. Relates to #807.
