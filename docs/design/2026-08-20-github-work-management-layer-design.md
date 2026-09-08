# LMDJ GitHub Work Management Layer Design

**Date:** 2026-08-20

**Status:** approved for implementation

**Scope:** repository work intake, prioritization, uncertainty tracking, and Pull Request linkage

## 1. Outcome

LMDJ will use GitHub Issues and GitHub Projects as its work-management layer
without replacing the repository's versioned sources of truth.

The system must make active work visible, sortable, assignable, and directly
connected to Pull Requests. Product truth, architecture, Contracts, governance,
approved decisions, detailed designs, implementation plans, acceptance evidence,
and release evidence remain in Git so that they are reviewed and versioned with
the code they govern.

```text
Issue: why, scope, state, acceptance, dependencies
  -> versioned Spec / Plan: design and implementation authority
  -> Pull Request: reviewed change and verification
  -> Decision / Portal / Evidence: durable confirmed truth
```

## 2. Current Baseline

The 2026-08-20 audit found:

- repository Issues are already enabled;
- four Issues are open and no repository Issue forms are installed;
- the existing Issues have no consistent labels;
- `docs/` contains 210 Markdown files, including 41 design Specs, 71
  implementation Plans, and 19 individual PRD question files;
- the Pull Request template has verification, CI, version, documentation,
  release, and transition-authority declarations, but no explicit related-Issue
  declaration.

This is a governance migration, not an Issue feature toggle.

## 3. Authority Boundaries

Every information type has one authoritative home.

| Information | Authority | GitHub role |
| --- | --- | --- |
| Feature, bug, task, technical debt, validation work | Issue | Authoritative lifecycle record |
| Unresolved product or architecture question | Issue | Authoritative open state and discussion |
| Current priority, Stage, owner, dependency, status | Project | Authoritative portfolio view |
| Confirmed product decision | `docs/prd/decisions/` | Issue links the decision PR before closing |
| Confirmed architecture decision | `docs/architecture/` | Issue links the decision PR before closing |
| Current PRD, architecture, Contract, governance | Repository / Architecture Portal | Issue may request a change but cannot override it |
| Detailed design Spec and implementation Plan | `docs/design/` 与 `docs/plans/` | Issue links the versioned files |
| Acceptance, proof, and release evidence | `docs/quality/` or `docs/release-evidence/` | Issue links retained evidence |
| Historical frozen artifact | Git history and dated document | No Issue is created solely to duplicate history |

An Issue comment does not silently settle a product Contract or concurrency
question. The confirmed conclusion becomes authoritative only after the
corresponding Decision, Contract, PRD, governance, or Portal change is merged.

## 4. Issue Types and Forms

The repository will install five Issue Forms:

1. **Feature** — a user or product outcome that may require design and one or
   more implementation Tasks.
2. **Bug** — reproducible incorrect behavior, regression, or flaky failure.
3. **Question / Decision needed** — an unresolved product, architecture,
   Contract, concurrency, or acceptance question.
4. **Task** — bounded engineering, validation, research, or governance work
   that is not itself a product feature.
5. **Documentation** — a bounded change to canonical documentation,
   navigation, evidence, or other retained project knowledge.

Blank Issues remain disabled. A public contact link is unnecessary while the
repository is private.

Each form captures only fields needed for routing and closure:

- outcome or question;
- context and evidence;
- in-scope and out-of-scope boundaries;
- acceptance or decision criteria;
- dependencies and blockers;
- affected product area and Stage;
- version impact;
- documentation impact;
- authority or source document links when applicable.

Detailed implementation steps do not live in an Issue body when a versioned
Plan is required by repository governance.

## 5. Label Taxonomy

Labels are namespaced so that their meaning remains obvious in lists and API
results.

### Required labels

- Type: `type:feature`, `type:bug`, `type:question`, `type:task`, `type:docs`
- Priority: `priority:p0`, `priority:p1`, `priority:p2`, `priority:p3`
- Area: `area:core`, `area:creator`, `area:web-host`, `area:native-host`,
  `area:provider`, `area:contracts`, `area:ci-release`, `area:product`,
  `area:docs-governance`

Normal workflow status does not use labels. It belongs to the Project Status
field, avoiding two competing status systems. Labels may be combined only when
the Issue genuinely crosses areas; every Issue has exactly one primary type and
one priority.

## 6. GitHub Project

One owner-level Project named **LMDJ Work** provides the active portfolio view.
It contains repository Issues and Pull Requests and uses these fields:

| Field | Values |
| --- | --- |
| Status | Inbox, Ready, In progress, In review, Blocked, Done |
| Priority | P0, P1, P2, P3 |
| Stage | Foundation, Stage 7, Stage 8A, Stage 8B, Stage 9, Stage 10, Stage 11, Stage 12, Later |
| Area | Core, Creator, Web Host, Native Host, Provider, Contracts, CI/Release, Product, Docs/Governance |
| Target | free-form iteration or milestone name |

Initial views are:

- **Triage:** Inbox and unclassified items;
- **Roadmap:** active items grouped by Stage and sorted by Priority;
- **Execution:** Ready through Blocked, grouped by Status;
- **Questions:** open `type:question` items;
- **PR Review:** linked Pull Requests in review.

Milestones are reserved for a concrete integration or release target. Stages
remain Project metadata and must not be represented by creating long-lived Git
branches.

## 7. Pull Request Linkage

The Pull Request template gains a `Related Issue` section requiring one of:

- `Closes #<number>` when merging the PR satisfies the Issue's closure rule;
- `Relates to #<number>` when the PR is partial work or only contributes
  evidence;
- `None` with a reason for administrative changes that have no Issue.

A feature may use an umbrella Issue with several bounded implementation Issues.
Each implementation Task still maps to one reviewable Conventional Commit and
one short-lived branch. An umbrella Issue is not itself permission to combine
unrelated Tasks into one PR.

## 8. Closure Rules

- A feature, bug, or task closes only after its required PR is merged and the
  Issue's acceptance evidence is linked.
- A question closes only after the authoritative decision or validation record
  is merged and linked. A discussion consensus alone is insufficient.
- A documentation Issue closes only after the canonical document change is
  merged and link checks pass.
- A PR being merged does not imply release, deployment, publication, or Channel
  promotion.
- `Done` means the Issue closure rule is satisfied. Release verification remains
  a separate evidence state where the underlying work requires it.

## 9. Migration Strategy

Migration covers active work only. It does not bulk-copy every dated document
into GitHub.

### Pass 1: install the management layer

- create Issue Forms and config;
- create the label taxonomy;
- create the Project and fields/views;
- add the Related Issue declaration to the Pull Request template;
- document the authority and closure rules in repository governance.

### Pass 2: inventory active work

Build a reviewable migration table from:

- the existing open GitHub Issues;
- current PRD question files;
- active quality TODO, review backlog, and manual-verification documents;
- incomplete acceptance items for the current Stages;
- the current implementation plan and open Pull Requests.

Each row is classified as `create Issue`, `link existing Issue`, `already
complete`, `historical only`, or `needs owner decision`. The inventory itself
does not delete or rewrite source documents.

### Pass 3: create and cross-link active Issues

- triage the four existing open Issues before creating possible duplicates;
- create new Issues in small batches with source links and required metadata;
- add all active items to LMDJ Work;
- update source question/TODO documents only after their replacement Issue
  exists and link integrity is verified;
- preserve frozen Specs, Plans, research, acceptance, and release evidence.

Repository question files may be removed only in the same reviewed Task that
records their confirmed decision, or replaced by a small index pointing to the
authoritative open Issues after every link is verified. Historical documents
are never deleted merely because their work is complete.

## 10. Automation Boundaries

The first implementation uses GitHub-native forms, labels, Projects, and PR
closing keywords. It does not introduce a bot or custom synchronization service.

After one operating cycle, automation may be considered for:

- detecting a missing Related Issue declaration;
- checking that new Issues have a type and priority;
- adding repository Issues to the Project;
- identifying closed questions without a linked decision record.

Automation must never infer or write product decisions, version changes,
release authority, or deployment authority.

## 11. Verification and Acceptance

The management layer is accepted when:

- all five Issue Forms render and create correctly classified Issues;
- blank Issues are disabled;
- required labels exist with documented descriptions and colors;
- LMDJ Work contains the declared fields and views;
- the four pre-existing open Issues are triaged without duplication;
- a test or real Pull Request body passes the Related Issue convention;
- every migrated Issue links its prior source;
- every migrated question retains a path to a future authoritative decision;
- repository link checks and `scripts/architecture-portal.sh check` pass;
- no Product Build, release, deployment, or Channel state changes as a side
  effect of this governance work.

## 12. Version Management

Version impact: none.

Reason: this design changes work-management governance only. It does not change
a Product Build, Core Module, Provider implementation, or Contract.

## 13. Documentation Impact

Documentation impact: none for Architecture Portal routes.

Reason: this Spec defines a future repository workflow and does not change
current Product, Module, Host, Provider, Contract, Channel, or revision
identity. The implementation Task will update repository governance and the
docs map, but no current Architecture Portal page is affected.
