# GitHub Work Management

## Authority model

Issues own active lifecycle state: intake, priority, dependency, assignee,
discussion, acceptance checklist, and closure.

GitHub Project owns portfolio state: Status, Priority, Stage, Area, and Target.

Repository documents own durable truth: current PRD and architecture, Contracts,
governance, approved Decisions, Specs, Plans, acceptance evidence, and release
evidence. An Issue comment is not a product decision and cannot override those
sources.

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

## Migration and history

Migrate active work only. Every migrated Issue links its prior source. Retained
Specs, Plans, research, acceptance records, and release evidence are not copied
into Issues. Existing question files retain context and link their Issue until
the same reviewed Task records a confirmed decision and removes or supersedes
the question.
