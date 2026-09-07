# Controlled manual resume and reporting workflow wiring

## Task and declared files

- `.github/workflows/self-test-report.yml`
- `tests/build/ci_batch_runtime_workflow_test.py`
- `docs/superpowers/plans/2026-09-08-lmdj-ci-manual-report-wiring.md`

One Conventional Commit; no runtime/protocol changes, remote Issue creation or
initialization, workflow dispatch, release or automatic-trigger cutover.

## Entry and authority

Extend the existing manual batch_operation choice with resume, report-init-outbox,
report-review, report-batches and report-drain. Legacy remains the default. Keep
the original Core CI completed subscription, daily missing-batch check, legacy
report job and local reusable executor unchanged. T5 replaces automatic triggers
only after independent O1 acceptance.

All new operations run in the existing Incremental batch controller job on main,
first attempt only, exact github.sha checkout and complete history. Existing
contents:read/actions:read/issues:write and the same self-test-report short writer
lock remain unchanged. No parent lock or additional job/permission is introduced.

Resume passes required batch_request JSON to the real batch_runtime resume CLI;
the runtime enforces closed id/suites/reason, no active executor, durable command
deduplication and no execution authorization. Explicit reconcile remains distinct.

Reports use a separate mutually exclusive step in that same authenticated job.
report_config passes unchanged to report_runtime, which enforces the closed
{scheduler: six-field-config, outbox: six-field-config} and distinct fixed Issues.
report-review requires explicit review_run_id and review_attempt; report-batches
passes report_limit (default 8; actual CLI validates 1..32). Reports reject mixed
scheduler inputs and never call batch_runtime, write controller result.json or
publish GITHUB_OUTPUT action/request/executor. They use --summary, not --output.
The controller artifact is uploaded only for scheduler operations. An Issue error
cannot manufacture an execute action. The reusable execution guard is unchanged.

## Verification

Lowest tier: workflow script execution contracts in
`python3 tests/build/ci_batch_runtime_workflow_test.py`, plus the legacy
`ci_self_test_report_workflow_test.py`. Actual embedded report script → CLI JSON
config and exact run/attempt → existing authenticated consumer → Outbox Journal
→ actual fake HTTP Issue body and durable receipt is exercised, with no execution
output on success or failure. Nonclosed configuration and missing/mixed inputs
are rejected. Resume's real runtime persistence/unknown-response journeys remain
owned by `ci_batch_runtime_test.py`; the workflow contract retains its exact argv
and verifies idle, not execute. The real batch callee far-side bridge remains.

Then run all CI contracts with pinned actionlint, lint self-test-report.yml with
only the exact existing queue-key compatibility exemption, staged ownership and
whitespace checks. No assertion, selected lane, timeout or coverage floor changes.

Local results: 19 manual workflow contracts, 10 legacy reporter contracts and
1,411 complete CI contracts passed without skips. Pinned actionlint passes with
only its exact existing `unexpected key "queue" for "concurrency" section`
compatibility exemption. A byte comparison confirms legacy report/executor jobs
and workflow_run/schedule blocks are unchanged. The full-suite import-identity
regression exposed by eager fixture imports was fixed by deferring this new
test's imports until after discovery, without modifying unrelated tests.

Remote token scopes, exact hosted queue/lock ownership, fixed outbox initialization,
actual resume/report dispatch and visibility recovery remain explicit O1 gaps.
No release evidence is created; scoped failures and debt stay independently
reported by the already reviewed runtime. Existing legacy writers bypass Outbox;
global cross-process coverage must not be claimed before the separate cutover.

Pitfall impact: none — applied existing fixture strictness and complete-journey
guidance; no new platform incident was observed in this local wiring Task.

## Version Management

Version impact: none — CI operator entrypoints only, no active version identity.

## Documentation Impact

Documentation impact: none — no Portal routes or projected product facts change;
this plan documents controlled manual inputs, not completed automatic rollout.
