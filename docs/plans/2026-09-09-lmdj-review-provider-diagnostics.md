# Preserve Grok error envelopes during review recovery

Relates to Issue 939 and the result-driven delivery plan. The desired outcome
remains real current-head AI review, not an author takeover or a green merge-map
job. PRs 998 and 1006 have independently landed model pins and honest failure
conclusions; do not duplicate those changes.

## Evidence and scope

Run 34292102873/1 used the older workflow: GLM and Kimi both initialized
`claude-opus-5[1m]` and timed out around five minutes. Grok exited 1 in under a
second; the adapter discarded its error envelope before reading JSON. This
does not establish a shared outage or a specific remote authentication defect.
The same pinned Grok 1.0.13 binary (SHA256
`edf79521581bb5e6b95abef848491a6a742e860da3e237ebe86a280d30dce4c1`)
locally returns exit 1 plus a JSON error envelope when isolated dummy auth is
not signed in. No real credentials or model calls were used for that probe.

Preserve only a finite diagnostic classification from a bounded, duplicate-free
JSON error envelope before handling a nonzero process status. Recognize the
observed local not-signed-in message prefix as `authentication_required`; other
error envelopes remain `error_envelope`, unknown nonzero output remains
`process_failure`. These are reported hints, not trusted provider-root-cause
claims or authority. Never print raw stdout/stderr/message/exception text.
Nonzero process output cannot become a successful review even if it contains
a valid review. Preserve the existing fallback order, exact-head publication,
scope floor, time budgets and temporary credential cleanup.

## Declared files

- `scripts/ci/review_pipeline.py`
- `tests/build/ci_review_pipeline_test.py`
- This plan.

## Verification

Start with regressions demonstrating that exit-1 JSON errors lose their category.
Cover authentication-required/unknown errors, duplicate keys, malformed/oversized
JSON, non-error output at nonzero exit, spoofed diagnostic prose and secret
non-disclosure through the actual CLI adapter entry. Run review adapter and
workflow tests, CI-contract discovery, staged/committed ownership and final scope.
No new merge gate or reduced coverage. After shipping, inspect actual producer
artifacts and publisher evidence for a current head using the new model pins;
closed-PR merge-map success is not review evidence. Keep Issue 939 open until
its remaining acceptance is actually satisfied. No credential rotation, host
mutation, Product allocation, deployment or automatic repair.

Observed verification: the adapter's 45 tests and Claude/Grok workflow tests
(14/20) pass, as does the exact pinned local CLI dummy-auth probe. Full
CI-contract discovery is **not green**: 2,075 tests report 5 failures, 8 errors
and one optional actionlint skip. A clean main worktree at `658951782d6722222cc5384732d660883bdd943d`
reproduces the identical 13 failing canary cases (210 tests); Issue 1029 owns
their version-fixture/canonical-input diagnosis. They do not execute the changed
review adapter. No failures were excluded or expectations weakened. Portal
verification passes 112 tests and 44 route/link checks. This bounded diagnostic
Task's review tests pass; broader plan health and live provider recovery do not.

## Version Management

Version impact: none
Reason: CI diagnostics only; active Product, Host, Module and Contract identities
remain unchanged.

## Documentation Impact

Documentation impact: none
Reason: internal diagnostic classification; no Portal routes, projected facts,
operator entry points or deployment behavior change.
