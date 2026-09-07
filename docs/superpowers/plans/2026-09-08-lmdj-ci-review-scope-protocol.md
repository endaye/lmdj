# T2a — Review fallback and trusted scope publication protocol

This is the pure protocol prerequisite of T2, not live backend/workflow wiring.
It depends on T1 commit-bound scope records and retains the old publisher API.

## Declared files

- `scripts/ci/review_scope.py`
- `tests/build/ci_review_scope_test.py`
- This plan.

## Behavior

One structured model response contains summary, findings and test_scope labels
with a reason. GLM → Kimi → Grok stops at the first process-successful, valid
response, including a response with findings. Invalid output is infrastructure
failure, never clean review. Error categories are finite and contain no stderr
or secrets. Proposed adapter budget is 300 seconds/backend, 900 seconds total;
T2b must enforce real execution limits, not merely record these constants.

The publisher reuses T1's deterministic floor and record recomputation. It
requires independent API run/workflow/repository/current-PR identity, actual
producer job completion and equality of run workflow code to trusted control.
Same-target prior authenticated records contribute their union. Labels are a
projection. The union also applies when all new backends fail: `not-reviewed`
cannot erase a prior valid test requirement. Full-retention and stale-head
rejection regressions both failed before the shared prior-record validation fix.
The durable copy will be attached to the exact-head COMMENT review
with an artifact copy; T2b owns actual storage, read authentication and head race
checks. No digest is a signature and no model claim authenticates a backend.

All three failures produce a versioned sanitized artifact for the existing
issues-capable reporter. This Task cannot open issues or increase permissions.

GitHub's [label REST API](https://docs.github.com/en/rest/issues/labels#add-labels-to-an-issue)
documents Pull requests write as an accepted permission for adding PR labels.
Therefore T2b may use the existing publisher permission; no issues write is
proposed. Actual installation-token writes remain an O1 verification obligation.

## Verification

Lowest tier: `python3 tests/build/ci_review_scope_test.py`; T1 scope regression;
staged `ci_change_scope_test.py` ownership/document-consumer gate; cached diff
check. Each refusal states why/remedy. Existing workflow remains untouched.

Acceptance gaps: real Claude action and Grok execution, runtime timeout, API
pagination, actual source-byte authentication, artifact upload and review/label
mutation races are T2b/O1 work. No mocked API fixture is live platform evidence.

Pitfall impact: none; reused secret-safe diagnostics and identity-not-display
rules without claiming a new observed incident.

## Documentation Impact

Documentation impact: none

Reason: New unused internal protocol only; no current Portal or runtime changes.

## Version Management

Version impact: none

Reason: CI-internal schema only; no Product, Module or cross-language Contract
version changes, publication, deployment or Channel promotion.
