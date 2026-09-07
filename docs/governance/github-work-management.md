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

## Closure

A feature, bug, task, or documentation Issue closes after its required change
is merged and acceptance evidence is linked. A question closes only after the
authoritative Decision, Contract, PRD, governance, or validation record is
merged and linked.

A merged Pull Request does not imply release, deployment, publication, or Channel promotion.
Those remain separate authorization and verification boundaries.

## Self-test triage

`self-test-report.yml` maintains one failure-collection Issue per suite/class,
labelled `self-test` and assigned to the configured maintainer until triaged.
These are collection buckets, not proven root-cause deduplication: real test
IDs and log-error fingerprints are not yet extracted, so different defects
may share a bucket. A maintainer may split them into separate defect Issues.
Each day someone reads the open `self-test` Issues and does two things:

- Classify each as a product regression, a test flake or an infrastructure
  failure, and relabel it; the reporter's `test_failure` /
  `infrastructure_failure` / `blocked` / `missing` class is where it starts,
  not the verdict.
- Decide severity. A high-severity product defect makes the targets it was
  observed on ineligible as release candidates; it never blocks an ordinary
  Pull Request merge, and a fix Pull Request merges on the same terms as any
  other. Infrastructure failures go to the host or workflow owner.

An Issue is closed by a person after the cause is understood, not by the next
green batch: one green run does not establish that a flaky defect is gone. A
`self-test-missing` Issue means the daily batch did not start; the check that
files it runs on GitHub Actions and cannot report a day on which Actions did
not run it, so a day with no `Self-test Report` run at all is unchecked, not
clean.

The reporter is a bounded recovery tool, not an infinite event store. Every
completion, retry and daily check reconciles retained runs from the last
30 days (at most 100 per allowed event); reaching that cap is a visible
`reporting-error`. A maintainer must explicitly retry affected run IDs after
an outage or overflow. A run whose selected request has no verdict is an
infrastructure observation; legacy sweeps that have not selected the new
self-test path are not relabelled as failed self-tests. Verify the configured
`self-test` label and default assignee during rollout before enabling reports.
To repeat a self-test, start a new dispatch for the same exact target; do not
rerun the old run because the current producer rejects later attempts. After
a product fix, explicitly choose and dispatch the fixed target. Reporter-only
retries still reference the original run ID and do not execute tests again.

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
