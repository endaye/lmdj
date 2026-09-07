# GitHub Work Management

## Authority model

For a migrated item, Issues own active lifecycle state: intake, priority,
dependency, assignee, discussion, acceptance checklist, and closure. An Issue
becomes the lifecycle authority only after a replacement Issue exists and its
source link is verified.

For a migrated item, GitHub Project owns portfolio state: Status, Priority,
Stage, Area, and Target. GitHub Project becomes the portfolio authority only
after `LMDJ Work` exists and the item is added.

Repository documents own durable truth: current PRD and architecture, Contracts,
governance, approved Decisions, Specs, Plans, acceptance evidence, and release
evidence. An Issue comment is not a product decision and cannot override those
sources. Before migration, repository question/TODO sources retain their current
live state.

## Intake and labels

Every Issue uses one primary type (`type:feature`, `type:bug`, `type:question`,
`type:task`, or `type:docs`), one priority (`priority:p0` through
`priority:p3`), and at least one namespaced `area:*` label. Workflow state is
recorded only in the Project Status field.

## From Issue to Pull Request

Use `Closes #<number>` only when the Pull Request satisfies the Issue closure
rule. Use `Relates to #<number>` for partial work or evidence. Use
`None — reason:` only when no Issue is warranted.

One umbrella feature may have several bounded implementation Issues. It never
authorizes unrelated Tasks in one branch, commit, or Pull Request.

PR 保留 Task 范围验证、当前 head 的 review 与 findings 处置；
AI 失败、缺凭据或过期证据须显式人工/agent 接管，不视为空 findings。
不要求追逐无冲突的 main 更新、排 Integration Queue 或等待全量测试绿。
这不扩大 push、PR、merge、Issue 写入或清理权限；未合入草案不替代当前规则。

## Closure

A feature, bug, task, or documentation Issue closes after its required change
is merged and acceptance evidence is linked. A question closes only after the
authoritative Decision, Contract, PRD, governance, or validation record is
merged and linked.

A merged Pull Request does not imply release, deployment, publication, or Channel promotion.
Those remain separate authorization and verification boundaries.

## Self-test triage

The approved incremental main-only strategy replaces daily product tests, not
manual exact-candidate full verification. Its automatic T5 switch is not yet
enabled by these governance edits: current manual controller/report operations
coexist with legacy automatic triggers until the authorized cutover.

The incremental report runtime consumes authenticated selected batch results
and all-backend review-infrastructure failures through a durable outbox.
The same `self-test-report.yml` controller owns the short writer lock; its
existing permissions are not expanded by this policy. Models, mutable labels
and unverified artifact digests are not report authority. An invalid or missing
receipt is an error, not a clean review or proof that all review backends failed.

Reports maintain failure-collection Issues per stable bucket (suite/class for
test observations and the review-infrastructure bucket for review failures),
labelled `self-test` and assigned to the configured maintainer until triaged.
These are collection buckets, not proven root-cause deduplication: real test
IDs and log-error fingerprints are not yet extracted, so different defects
may share a bucket. A maintainer may split them into separate defect Issues.
During triage, a maintainer reads the open `self-test` Issues and does two things:

- Classify each as a product regression, a test flake or an infrastructure
  failure, and relabel it; the reporter's `test_failure` /
  `infrastructure_failure` / `blocked` / `missing` class is where it starts,
  not the verdict.
- Decide severity. A high-severity product defect makes the targets it was
  observed on ineligible as release candidates; it never blocks an ordinary
  Pull Request merge, and a fix Pull Request merges on the same terms as any
  other. Infrastructure failures go to the host or workflow owner.

An Issue is closed by a person after the cause is understood, not by the next
green batch: one green run does not establish that a flaky defect is gone.
Display processed SHA, selected results, unexecuted verification debt and
unresolved defects separately. A docs-none batch or later focused pass cannot
erase prior failures or prove full release readiness. Infrastructure debt may
pause after bounded attempts; resuming it is an explicit operation, not an
Issue closure or an instruction to retry indefinitely.

The outbox persists immutable report intent, a pre-write claim and a receipt.
After an unknown POST response, an exact positive receipt can complete delivery;
a temporarily absent list entry or 404 cannot justify repeating the POST.
Claim-before-POST crashes are also ambiguous and may require manual inspection.
An unresolved claim remains visible with why/remedy; waiting is not successful
recovery. Replaying a delivered observation does not duplicate it. Reporting
does not execute product tests, mutate old results or change result colors.
If the storage API itself is unavailable, persistence cannot be promised:
keep the error visible and do not advance scheduler state on fabricated data.

### Legacy reporter during the trigger transition

The retained legacy adapter is not the incremental reporting policy. Until T5
retires the old schedule and daily-missing alert together, a legacy
`self-test-missing` Issue means the daily batch did not start; the check that
files it runs on GitHub Actions and cannot report a day on which Actions did
not run it, so a day with no `Self-test Report` run at all is unchecked, not
clean.

That legacy reporter is a bounded recovery tool, not an infinite event store. Main
completion callbacks and daily checks reconcile retained runs since the later
of the 30-day retention boundary and the verified producer's scan floor.
The first producer is PR #757's squash `22247897e9163a3f34e15f564bec133419d1f177`;
its committer time, `2026-09-07T12:20:36Z`, conservatively precedes the PR's
`merged_at` by one second. Time only narrows queries: each run independently
proves control ancestry from that producer and membership in main history.
Older control revisions, including their recent reruns, are explicitly legacy;
post-deployment startup failures remain visible, and unknown/diverged ancestry
fails closed. Non-main queue completion callbacks do not start this reporter.

The scan is capped at 100 per allowed event; reaching the cap is a visible
`reporting-error`, not proof of recovery. A maintainer must explicitly retry
affected run IDs after an outage or overflow. Manual reporter dispatch defaults
to `reconcile: false`, processing only that run so unrelated history or a full
scan window cannot block its recovery; set `reconcile: true` only to request
the wider scan. A run whose selected request has no verdict is an
infrastructure observation; legacy sweeps that have not selected the new
self-test path are not relabelled as failed self-tests. Verify the configured
`self-test` label and default assignee during rollout before enabling reports.
To repeat a self-test, start a new dispatch for the same exact target; do not
rerun the old run because the current producer rejects later attempts. After
a product fix, explicitly choose and dispatch the fixed target. Reporter-only
retries still reference the original run ID and do not execute tests again.
These retention, scan-floor and legacy dispatch rules describe only that
adapter; incremental journal progress/debt must not expire with artifacts.
The T5 switch must verify its own main wakeup, completion recovery and idle
behavior before this legacy automatic path is retired.

## Migration and history

Migrate active work only after the replacement Issue is created and the source
link is verified. Add a migrated item to `LMDJ Work` before treating Project
fields as its portfolio state. Until both transitions occur, the repository
source retains its live state; do not infer a migration from a planned Issue or
Project alone.

Every migrated Issue links its prior source. Retained Specs, Plans, research,
acceptance records, and release evidence are not copied into Issues.
`docs/prd/questions/*.md` must not be migrated before this repository contract
is merged. After merge, an approved migration may create and verify replacement
Issue links and update source state in the same reviewed Task. Those question
files retain their current live state and context until the replacement Issue
exists and its source link is verified.
