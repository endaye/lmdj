# LMDJ GitHub Work Management Layer Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish GitHub Issues and GitHub Projects as LMDJ's active work-management layer while preserving versioned repository documents as the authority for confirmed truth, detailed design, implementation, and evidence.

**Architecture:** Repository-owned Issue Forms, tests, governance, and Pull Request linkage define the contract. GitHub labels and one owner-level Project provide the remote workflow view. A reviewed inventory then migrates only active questions and work, cross-linking every Issue to its retained source without copying historical documents.

**Tech Stack:** GitHub Issue Forms YAML, GitHub CLI `gh`, GitHub Projects v2, Python 3 `unittest`, Markdown governance, existing LMDJ CI scope classifier and Architecture Portal checks.

## Global Constraints

- Work only on `docs/github-work-management` in its isolated worktree; never edit or commit on `main`.
- Stage only files declared by the current Task, and make each Task one reviewable Conventional Commit.
- Do not push, open a Pull Request, merge, or mutate the default branch without separate explicit authorization.
- Remote labels, Projects, and Issues are authorized by the approved design, but remote setup starts only after the repository contract is merged to `main`.
- `gh` currently has `repo` but not `project`; Project operations stop until the user grants `project` scope or performs the equivalent authenticated browser action.
- Issues own active lifecycle state; repository Decisions, Contracts, PRD, governance, Specs, Plans, acceptance evidence, and release evidence remain authoritative for durable truth.
- An Issue comment never settles an open product Contract or concurrency question.
- No task may create a Product Build, release, deployment, publication, or Channel promotion.
- Blank Issues remain disabled.
- Normal workflow state exists only in the Project `Status` field, not in labels.

## File Structure

- `.github/ISSUE_TEMPLATE/config.yml` — disables blank Issues.
- `.github/ISSUE_TEMPLATE/feature.yml` — feature/outcome intake.
- `.github/ISSUE_TEMPLATE/bug.yml` — reproducible defect intake.
- `.github/ISSUE_TEMPLATE/question.yml` — unresolved question/decision intake.
- `.github/ISSUE_TEMPLATE/task.yml` — bounded engineering/validation/research task intake.
- `.github/ISSUE_TEMPLATE/documentation.yml` — canonical documentation work intake.
- `.github/pull_request_template.md` — requires explicit Issue linkage or a reason for none.
- `docs/governance/github-work-management.md` — canonical authority, lifecycle, taxonomy, and closure policy.
- `docs/README.md` — adds the governance entry point.
- `docs/prd/README.md` — routes new unresolved questions to GitHub Issues and confirmed outcomes back to Decisions/PRD.
- `docs/prd/open-questions.md` — changes from file-creation rules to the migration and cross-linking rule.
- `tests/build/ci_github_work_management_test.py` — dependency-free repository contract tests.
- `scripts/ci/scope_policy.json` — selects `docs_static` and `ci_contract` for Issue Form changes.
- `tests/build/ci_change_scope_test.py` — locks that scope rule.
- `docs/quality/2026-08-20-github-work-management-remote-setup.md` — retained remote setup evidence.
- `docs/quality/2026-08-20-github-work-management-migration-inventory.md` — reviewed active-work classification.
- Existing `docs/prd/questions/*.md` files — gain the authoritative Issue link after migration; their context remains retained until a decision Task removes or supersedes them.

---

### Task 1: Repository Issue Forms and Contract Tests

**Files:**

- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/ISSUE_TEMPLATE/feature.yml`
- Create: `.github/ISSUE_TEMPLATE/bug.yml`
- Create: `.github/ISSUE_TEMPLATE/question.yml`
- Create: `.github/ISSUE_TEMPLATE/task.yml`
- Create: `.github/ISSUE_TEMPLATE/documentation.yml`
- Create: `tests/build/ci_github_work_management_test.py`
- Modify: `scripts/ci/scope_policy.json` in `rules`
- Modify: `tests/build/ci_change_scope_test.py` in `CASES`

**Interfaces:**

- Consumes: GitHub Issue Form schema and the existing `ci_contract` discovery pattern `ci_*_test.py`.
- Produces: five stable intake forms, disabled blank Issues, and a CI-enforced repository contract.

- [ ] **Step 1: Write the failing repository contract test**

Create `tests/build/ci_github_work_management_test.py` with this complete contract:

```python
#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = ROOT / ".github" / "ISSUE_TEMPLATE"

FORM_CONTRACTS = {
    "feature.yml": ("type:feature", ("summary", "outcome", "scope", "acceptance", "dependencies", "stage", "area", "version_impact", "documentation_impact", "source")),
    "bug.yml": ("type:bug", ("summary", "observed", "expected", "reproduction", "evidence", "acceptance", "stage", "area", "version_impact", "documentation_impact")),
    "question.yml": ("type:question", ("question", "importance", "evidence", "decision_criteria", "stage", "area", "source")),
    "task.yml": ("type:task", ("outcome", "scope", "acceptance", "dependencies", "stage", "area", "version_impact", "documentation_impact", "source")),
    "documentation.yml": ("type:docs", ("authority", "change", "audience", "acceptance", "links", "version_impact", "documentation_impact")),
}


class GitHubWorkManagementContractTest(unittest.TestCase):
    def read(self, name: str) -> str:
        return (TEMPLATE_ROOT / name).read_text(encoding="utf-8")

    def test_blank_issues_are_disabled(self) -> None:
        source = self.read("config.yml")
        self.assertIn("blank_issues_enabled: false", source)
        self.assertIn("contact_links: []", source)

    def test_all_five_forms_have_closed_fields_and_one_type(self) -> None:
        self.assertEqual(
            {path.name for path in TEMPLATE_ROOT.glob("*.yml")},
            {"config.yml", *FORM_CONTRACTS},
        )
        for filename, (label, field_ids) in FORM_CONTRACTS.items():
            with self.subTest(filename=filename):
                source = self.read(filename)
                for header in ("name:", "description:", "title:", "labels:", "body:"):
                    self.assertRegex(source, rf"(?m)^{re.escape(header)}")
                self.assertRegex(source, rf'(?m)^labels: \["{re.escape(label)}"\]$')
                ids = tuple(re.findall(r"(?m)^    id: ([a-z_]+)$", source))
                self.assertEqual(ids, field_ids)

    def test_every_form_captures_acceptance_or_decision_criteria(self) -> None:
        for filename in FORM_CONTRACTS:
            source = self.read(filename)
            self.assertTrue(
                "    id: acceptance" in source or "    id: decision_criteria" in source,
                filename,
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Lock the CI scope selection and verify both tests fail**

Add this entry to `CASES` in `tests/build/ci_change_scope_test.py`:

```python
".github/ISSUE_TEMPLATE/feature.yml": {"docs_static", "ci_contract"},
```

Run:

```bash
python3 -m unittest tests.build.ci_github_work_management_test tests.build.ci_change_scope_test
```

Expected: FAIL because the Issue Forms do not exist and the new path currently upgrades to full CI.

- [ ] **Step 3: Create the five Issue Forms and config**

Create `.github/ISSUE_TEMPLATE/config.yml`:

```yaml
blank_issues_enabled: false
contact_links: []
```

Create `.github/ISSUE_TEMPLATE/feature.yml`:

```yaml
name: Feature
description: Propose a user or product outcome.
title: "feature: "
labels: ["type:feature"]
body:
  - type: textarea
    id: summary
    attributes: {label: Summary, description: Describe the requested capability.}
    validations: {required: true}
  - type: textarea
    id: outcome
    attributes: {label: User outcome, description: Describe the observable user value.}
    validations: {required: true}
  - type: textarea
    id: scope
    attributes: {label: Scope, description: State what is in and out.}
    validations: {required: true}
  - type: textarea
    id: acceptance
    attributes: {label: Acceptance, description: List observable completion criteria.}
    validations: {required: true}
  - type: textarea
    id: dependencies
    attributes: {label: Dependencies, description: Link blockers, Issues, Specs, Plans, or PRs.}
  - type: dropdown
    id: stage
    attributes: {label: Stage, options: [Foundation, Stage 7, Stage 8A, Stage 8B, Stage 9, Stage 10, Stage 11, Stage 12, Later]}
    validations: {required: true}
  - type: dropdown
    id: area
    attributes: {label: Area, options: [Core, Creator, Web Host, Native Host, Provider, Contracts, CI/Release, Product, Docs/Governance]}
    validations: {required: true}
  - type: input
    id: version_impact
    attributes: {label: Version impact, description: Name the affected version domain or write none with a reason.}
    validations: {required: true}
  - type: input
    id: documentation_impact
    attributes: {label: Documentation impact, description: Name affected Portal routes or write none with a reason.}
    validations: {required: true}
  - type: textarea
    id: source
    attributes: {label: Authority and sources, description: Link retained product, design, decision, research, or evidence sources.}
```

Create `.github/ISSUE_TEMPLATE/bug.yml`:

```yaml
name: Bug
description: Report reproducible incorrect or flaky behavior.
title: "bug: "
labels: ["type:bug"]
body:
  - type: textarea
    id: summary
    attributes: {label: Summary, description: Describe the defect in one observable statement.}
    validations: {required: true}
  - type: textarea
    id: observed
    attributes: {label: Observed behavior, description: Include exact state and failure text.}
    validations: {required: true}
  - type: textarea
    id: expected
    attributes: {label: Expected behavior, description: Describe the required behavior.}
    validations: {required: true}
  - type: textarea
    id: reproduction
    attributes: {label: Reproduction, description: Give deterministic steps or the best known trigger.}
    validations: {required: true}
  - type: textarea
    id: evidence
    attributes: {label: Evidence, description: Link logs, runs, revisions, screenshots, or devices.}
    validations: {required: true}
  - type: textarea
    id: acceptance
    attributes: {label: Fix acceptance, description: State the regression proof required to close.}
    validations: {required: true}
  - type: dropdown
    id: stage
    attributes: {label: Stage, options: [Foundation, Stage 7, Stage 8A, Stage 8B, Stage 9, Stage 10, Stage 11, Stage 12, Later]}
    validations: {required: true}
  - type: dropdown
    id: area
    attributes: {label: Area, options: [Core, Creator, Web Host, Native Host, Provider, Contracts, CI/Release, Product, Docs/Governance]}
    validations: {required: true}
  - type: input
    id: version_impact
    attributes: {label: Version impact, description: Name the affected version domain or write none with a reason.}
    validations: {required: true}
  - type: input
    id: documentation_impact
    attributes: {label: Documentation impact, description: Name affected Portal routes or write none with a reason.}
    validations: {required: true}
```

Create `.github/ISSUE_TEMPLATE/question.yml`:

```yaml
name: Question or decision needed
description: Track an unresolved product, architecture, Contract, concurrency, or acceptance decision.
title: "question: "
labels: ["type:question"]
body:
  - type: textarea
    id: question
    attributes: {label: Question, description: State one decision as a question.}
    validations: {required: true}
  - type: textarea
    id: importance
    attributes: {label: Why it matters now, description: Name the blocked or affected outcome.}
    validations: {required: true}
  - type: textarea
    id: evidence
    attributes: {label: Known evidence and options, description: Link sources and distinguish facts from hypotheses.}
    validations: {required: true}
  - type: textarea
    id: decision_criteria
    attributes: {label: Decision criteria, description: State the evidence and authority required to close.}
    validations: {required: true}
  - type: dropdown
    id: stage
    attributes: {label: Stage, options: [Foundation, Stage 7, Stage 8A, Stage 8B, Stage 9, Stage 10, Stage 11, Stage 12, Later]}
    validations: {required: true}
  - type: dropdown
    id: area
    attributes: {label: Area, options: [Core, Creator, Web Host, Native Host, Provider, Contracts, CI/Release, Product, Docs/Governance]}
    validations: {required: true}
  - type: textarea
    id: source
    attributes: {label: Authority and source context, description: Link the retained question, PRD, Contract, Spec, or evidence.}
    validations: {required: true}
```

Create `.github/ISSUE_TEMPLATE/task.yml`:

```yaml
name: Task
description: Track bounded engineering, validation, research, or governance work.
title: "task: "
labels: ["type:task"]
body:
  - type: textarea
    id: outcome
    attributes: {label: Outcome, description: State the concrete deliverable.}
    validations: {required: true}
  - type: textarea
    id: scope
    attributes: {label: Scope, description: State included and excluded work.}
    validations: {required: true}
  - type: textarea
    id: acceptance
    attributes: {label: Acceptance, description: Give exact verification and retained evidence.}
    validations: {required: true}
  - type: textarea
    id: dependencies
    attributes: {label: Dependencies, description: Link blockers, Issues, Plans, or PRs.}
  - type: dropdown
    id: stage
    attributes: {label: Stage, options: [Foundation, Stage 7, Stage 8A, Stage 8B, Stage 9, Stage 10, Stage 11, Stage 12, Later]}
    validations: {required: true}
  - type: dropdown
    id: area
    attributes: {label: Area, options: [Core, Creator, Web Host, Native Host, Provider, Contracts, CI/Release, Product, Docs/Governance]}
    validations: {required: true}
  - type: input
    id: version_impact
    attributes: {label: Version impact, description: Name the affected version domain or write none with a reason.}
    validations: {required: true}
  - type: input
    id: documentation_impact
    attributes: {label: Documentation impact, description: Name affected Portal routes or write none with a reason.}
    validations: {required: true}
  - type: textarea
    id: source
    attributes: {label: Authority and sources, description: Link retained design, plan, research, or evidence.}
```

Create `.github/ISSUE_TEMPLATE/documentation.yml`:

```yaml
name: Documentation
description: Change canonical documentation, navigation, evidence, or retained knowledge.
title: "docs: "
labels: ["type:docs"]
body:
  - type: input
    id: authority
    attributes: {label: Authority, description: Name the canonical document or Portal route.}
    validations: {required: true}
  - type: textarea
    id: change
    attributes: {label: Required change, description: Describe the inaccurate, missing, or hard-to-find information.}
    validations: {required: true}
  - type: textarea
    id: audience
    attributes: {label: Audience and use, description: State who needs the document and what they must do with it.}
    validations: {required: true}
  - type: textarea
    id: acceptance
    attributes: {label: Acceptance, description: Name link, rendering, Portal, or evidence checks.}
    validations: {required: true}
  - type: textarea
    id: links
    attributes: {label: Related sources, description: Link superseded text, Issues, Specs, Plans, or PRs.}
  - type: input
    id: version_impact
    attributes: {label: Version impact, description: Name the affected version domain or write none with a reason.}
    validations: {required: true}
  - type: input
    id: documentation_impact
    attributes: {label: Documentation impact, description: Name affected Portal routes or explain why Portal impact is none.}
    validations: {required: true}
```

- [ ] **Step 4: Add the focused CI rule**

Add this rule to `scripts/ci/scope_policy.json` before the exact Pull Request template rule:

```json
{"match": {"kind": "prefix", "value": ".github/ISSUE_TEMPLATE/"}, "lanes": ["docs_static", "ci_contract"]},
```

- [ ] **Step 5: Verify the forms and scope contract**

Run:

```bash
ruby -e 'require "yaml"; ARGV.each { |path| YAML.safe_load_file(path, aliases: false); puts "valid #{path}" }' .github/ISSUE_TEMPLATE/*.yml
python3 -m unittest tests.build.ci_github_work_management_test tests.build.ci_change_scope_test
git diff --check
```

Expected: six `valid` lines, all Python tests PASS, and no whitespace errors.

- [ ] **Step 6: Commit Task 1**

```bash
git add .github/ISSUE_TEMPLATE tests/build/ci_github_work_management_test.py scripts/ci/scope_policy.json tests/build/ci_change_scope_test.py
git diff --cached --name-only
git diff --cached --check
git commit -m "feat(governance): add GitHub work intake forms"
```

Expected committed files: the six template files plus the three declared test/policy files, and nothing else.

### Task 2: Governance Contract and Pull Request Linkage

**Files:**

- Create: `docs/governance/github-work-management.md`
- Modify: `docs/README.md` in the directory map and entry pointers
- Modify: `docs/prd/README.md` in document ownership and iteration rhythm
- Modify: `docs/prd/open-questions.md` in authority and file format rules
- Modify: `.github/pull_request_template.md` before `Verification`
- Modify: `tests/build/ci_github_work_management_test.py`

**Interfaces:**

- Consumes: the five Issue types and label names from Task 1.
- Produces: one canonical work-management policy and a PR-to-Issue relation required for every new change.

- [ ] **Step 1: Extend the failing contract test**

Add these paths and assertions to `tests/build/ci_github_work_management_test.py`:

```python
GOVERNANCE = ROOT / "docs" / "governance" / "github-work-management.md"
PR_TEMPLATE = ROOT / ".github" / "pull_request_template.md"

def test_governance_preserves_durable_authority(self) -> None:
    source = GOVERNANCE.read_text(encoding="utf-8")
    for required in (
        "Issues own active lifecycle state",
        "GitHub Project owns portfolio state",
        "Repository documents own durable truth",
        "An Issue comment is not a product decision",
        "Closes #",
        "Relates to #",
        "release, deployment, publication, or Channel promotion",
    ):
        self.assertIn(required, source)

def test_pull_request_template_requires_issue_relation(self) -> None:
    source = PR_TEMPLATE.read_text(encoding="utf-8")
    self.assertIn("## Related Issue", source)
    self.assertIn("Closes #", source)
    self.assertIn("Relates to #", source)
    self.assertIn("None — reason:", source)
```

Run:

```bash
python3 -m unittest tests.build.ci_github_work_management_test
```

Expected: FAIL because the governance file and PR section do not exist.

- [ ] **Step 2: Write the canonical governance document**

Create `docs/governance/github-work-management.md` with these exact sections and rules:

```markdown
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

A merged Pull Request does not imply release, deployment, publication, or
Channel promotion. Those remain separate authorization and verification
boundaries.

## Migration and history

Migrate active work only. Every migrated Issue links its prior source. Retained
Specs, Plans, research, acceptance records, and release evidence are not copied
into Issues. Existing question files retain context and link their Issue until
the same reviewed Task records a confirmed decision and removes or supersedes
the question.
```

- [ ] **Step 3: Update repository navigation and PRD routing**

In `docs/README.md`, add `governance/github-work-management.md` to the governance entry pointers and state that GitHub Issues/Project own active work state.

In `docs/prd/README.md`, replace the instruction to create new question files with:

```markdown
New unresolved questions enter GitHub Issues through the Question form. The
Issue owns discussion and open state; retained source context links from the
Issue, and a confirmed conclusion is merged into `decisions/`, the PRD,
Contract, governance, or Architecture Portal before the Issue closes.
```

In `docs/prd/open-questions.md`, preserve the current question-file context but state that migrated files contain a `GitHub Issue` line and no longer own live status.

- [ ] **Step 4: Add the Pull Request relation section**

Insert this immediately after `## Summary` in `.github/pull_request_template.md`:

```markdown
## Related Issue

Related issue: <!-- Write exactly one: Closes #123 | Relates to #123 | None — reason: ... -->
```

- [ ] **Step 5: Verify governance, PR impact, and Portal**

Run:

```bash
python3 -m unittest tests.build.ci_github_work_management_test
scripts/local-ci.sh --no-cache --lanes ci_contract
bash scripts/architecture-portal.sh check
git diff --check
```

Expected: contract tests PASS; `ci_contract` PASS; Portal tests, validation, typecheck, build, and internal links PASS; no whitespace errors.

- [ ] **Step 6: Commit Task 2**

```bash
git add docs/governance/github-work-management.md docs/README.md docs/prd/README.md docs/prd/open-questions.md .github/pull_request_template.md tests/build/ci_github_work_management_test.py
git diff --cached --name-only
git diff --cached --check
git commit -m "docs(governance): route active work through GitHub"
```

### Task 3: Publish the Repository Contract Boundary

**Files:** none unless review requests changes.

**Interfaces:**

- Consumes: local Tasks 1–2.
- Produces: a reviewed default-branch contract that remote Project and Issue migration can safely reference.

- [ ] **Step 1: Run final local preflight**

```bash
scripts/local-ci.sh --list
scripts/local-ci.sh --no-cache --lanes docs_static,portal,ci_contract
git log --oneline origin/main..HEAD
git status --short --branch
```

Expected: the classifier reports the full CI required by the central scope-policy change; the three task-specific local lanes PASS; only the declared governance commits are ahead of `origin/main`; and the worktree is clean. Remote PR Gate remains responsible for the complete required job set.

- [ ] **Step 2: Stop at the Git transition boundary**

Report the exact commits and checks. Obtain separate authorization before `git push`, Pull Request creation, or merge. After authorization, use the repository's normal push/PR/squash-merge workflow and verify that the merge commit is on `origin/main` before Task 4. Clean up the merged branch/worktree according to `docs/governance/git-workflow.md`.

### Task 4: Remote Labels and LMDJ Work Project

**Files:**

- Create: `docs/quality/2026-08-20-github-work-management-remote-setup.md`

**Interfaces:**

- Consumes: the governance contract merged by Task 3 and authenticated GitHub owner `endaye`.
- Produces: namespaced labels, the private `LMDJ Work` Project, required fields/views, and retained setup evidence.

- [ ] **Step 0: Start the post-merge evidence branch**

From a clean primary worktree, fetch `origin/main`, then create and enter a new isolated worktree on `docs/github-work-management-remote-setup`. Confirm its HEAD equals current `origin/main` before any remote mutation.

- [ ] **Step 1: Audit remote state and obtain Project scope**

```bash
gh auth status
gh auth refresh -h github.com -s project
gh project list --owner endaye --limit 100 --format json
gh label list --limit 100 --json name,color,description
```

Expected: active account `endaye`, token scope includes `project`, and no existing Project named `LMDJ Work`. If either condition is false, stop without mutation.

- [ ] **Step 2: Create or update the namespaced labels**

Run `gh label create --force` once for every exact label:

```bash
gh label create 'type:feature' --color 1D76DB --description 'User or product outcome' --force
gh label create 'type:bug' --color D73A4A --description 'Reproducible defect, regression, or flaky failure' --force
gh label create 'type:question' --color D876E3 --description 'Decision or validation required' --force
gh label create 'type:task' --color 0E8A16 --description 'Bounded engineering, validation, research, or governance work' --force
gh label create 'type:docs' --color 0075CA --description 'Canonical documentation or retained knowledge' --force
gh label create 'priority:p0' --color B60205 --description 'Immediate stop-the-line priority' --force
gh label create 'priority:p1' --color D93F0B --description 'Blocks the current integration or release target' --force
gh label create 'priority:p2' --color FBCA04 --description 'Planned work that does not block the current target' --force
gh label create 'priority:p3' --color C2E0C6 --description 'Later or opportunistic work' --force
gh label create 'area:core' --color 5319E7 --description 'Product-neutral Core Modules' --force
gh label create 'area:creator' --color 7057FF --description 'Creator Host and workflow' --force
gh label create 'area:web-host' --color 006B75 --description 'Web Runtime Host' --force
gh label create 'area:native-host' --color 006B75 --description 'Native Runtime or test Host' --force
gh label create 'area:provider' --color BFDADC --description 'Capability Provider implementation or SDK' --force
gh label create 'area:contracts' --color C5DEF5 --description 'Versioned cross-language Contracts' --force
gh label create 'area:ci-release' --color F9D0C4 --description 'CI, packaging, release, deployment, or evidence' --force
gh label create 'area:product' --color E99695 --description 'PRD, product decision, Stage, or acceptance' --force
gh label create 'area:docs-governance' --color 0075CA --description 'Documentation, research, or governance' --force
```

- [ ] **Step 3: Create and link the Project**

```bash
gh project create --owner endaye --title 'LMDJ Work' --format json
gh project list --owner endaye --limit 100 --format json
LMDJ_PROJECT_NUMBER="$(gh project list --owner endaye --limit 100 --format json --jq '.projects[] | select(.title == "LMDJ Work") | .number')"
test -n "$LMDJ_PROJECT_NUMBER"
gh project link "$LMDJ_PROJECT_NUMBER" --owner endaye --repo lmdj
```

Capture the returned project number. Create fields with:

```bash
gh project field-create "$LMDJ_PROJECT_NUMBER" --owner endaye --name Priority --data-type SINGLE_SELECT --single-select-options 'P0,P1,P2,P3'
gh project field-create "$LMDJ_PROJECT_NUMBER" --owner endaye --name Stage --data-type SINGLE_SELECT --single-select-options 'Foundation,Stage 7,Stage 8A,Stage 8B,Stage 9,Stage 10,Stage 11,Stage 12,Later'
gh project field-create "$LMDJ_PROJECT_NUMBER" --owner endaye --name Area --data-type SINGLE_SELECT --single-select-options 'Core,Creator,Web Host,Native Host,Provider,Contracts,CI/Release,Product,Docs/Governance'
gh project field-create "$LMDJ_PROJECT_NUMBER" --owner endaye --name Target --data-type TEXT
```

Use `gh project view "$LMDJ_PROJECT_NUMBER" --owner endaye --web` to configure the built-in Status options as `Inbox`, `Ready`, `In progress`, `In review`, `Blocked`, and `Done`, then create the five views exactly as specified in the approved design: Triage, Roadmap, Execution, Questions, and PR Review.

- [ ] **Step 4: Verify and retain remote setup evidence**

Run:

```bash
gh label list --limit 100 --json name,color,description
gh project field-list "$LMDJ_PROJECT_NUMBER" --owner endaye --format json
gh project view "$LMDJ_PROJECT_NUMBER" --owner endaye --format json
```

Create `docs/quality/2026-08-20-github-work-management-remote-setup.md` containing the Project URL/number, label inventory, field inventory, manual view verification, timestamp, authenticated owner, and explicit statement that no release/deployment state changed.

Run `bash scripts/architecture-portal.sh check`, stage only the evidence file, and commit:

```bash
git commit -m "docs(quality): record GitHub work management setup"
```

### Task 5: Active-Work Migration Inventory

**Files:**

- Create: `docs/quality/2026-08-20-github-work-management-migration-inventory.md`

**Interfaces:**

- Consumes: current `main`, open Issues/PRs, 19 PRD question files, and current quality TODO/review sources.
- Produces: a concrete deduplicated disposition for every candidate before new Issues are created.

- [ ] **Step 1: Refresh all active sources**

Audit these exact source sets:

```bash
git fetch origin --prune
gh issue list --state open --limit 100 --json number,title,labels,url
gh pr list --state open --limit 100 --json number,title,isDraft,headRefName,url
rg -n '^- 状态：' docs/prd/questions/*.md
rg -n '^### |^\|.*open|^\|.*blocked|^\|.*待' docs/quality/2026-08-16-outstanding-work-before-stage9.md docs/quality/2026-08-17-machine-task-todo.md docs/quality/2026-08-17-manual-verification-todo.md
```

Expected baseline to reconcile, not blindly reproduce: Issues `#165`, `#166`, `#167`, `#178`; open PR `#202`; 19 question files; and the active A/B/C/D/E/F/manual rows in the three named quality documents.

- [ ] **Step 2: Build the migration table**

Create one row per candidate with columns:

```markdown
| Source | Current state | Proposed type | Priority | Stage | Area | Disposition | Existing/new Issue | Reason |
```

Every `Disposition` is exactly one of `link existing Issue`, `create Issue`, `already complete`, `historical only`, or `needs owner decision`. Apply these rules:

- `待决`, `待验证`, `待评审`, `待设计评审`, and `待架构设计` become active question Issues unless a live Issue already covers the same closure criterion.
- `延后` and `已收缩` become `priority:p3`, Stage `Later`, unless a confirmed Decision has eliminated the question.
- Closed/fixed rows remain historical only and do not become Issues.
- Quality rows that repeat a PRD question link that question Issue instead of creating a duplicate.
- A physical-verification row is a Task, not a product decision; a carry-forward or acceptance-threshold choice is a Question.
- Any row whose classification changes a Product Contract or Stage commitment is `needs owner decision` and stops before Issue creation.

- [ ] **Step 3: Verify and commit the inventory**

Run:

```bash
rg -n '\| needs owner decision \|' docs/quality/2026-08-20-github-work-management-migration-inventory.md
bash scripts/architecture-portal.sh check
git diff --check
```

If owner decisions exist, report them before Task 6. Otherwise stage only the inventory and commit:

```bash
git commit -m "docs(quality): inventory active GitHub work migration"
```

### Task 6: Triage Existing Items and Create Migrated Issues

**Files:**

- Modify: `docs/quality/2026-08-20-github-work-management-migration-inventory.md`
- Modify: only the `docs/prd/questions/*.md` files whose Issues were created or linked

**Interfaces:**

- Consumes: the approved migration inventory and remote Project from Tasks 4–5.
- Produces: deduplicated labeled Issues in `LMDJ Work`, with every migrated source cross-linked.

- [ ] **Step 1: Triage the four existing Issues before creating anything**

Apply these baseline classifications after verifying their live bodies still match:

- `#178`: `type:bug`, `area:creator`, priority determined by current Creator acceptance impact.
- `#167`: `type:bug`, `area:core`, priority determined by current CI blocking impact.
- `#166`: `type:bug`, `area:web-host`, priority determined by current CI blocking impact.
- `#165`: `type:task`, `area:ci-release`, priority determined by the current release target.

Add each to `LMDJ Work`. Do not close or rewrite historical discussion.

- [ ] **Step 2: Create Issues in reviewable batches**

For each `create Issue` row, create exactly one Issue from the matching installed form contract. The title is the retained source heading; the body includes:

```markdown
## Source

Permanent link to the source file and current revision.

## Context

Concise retained facts; hypotheses remain labeled as hypotheses.

## Closure

The exact acceptance evidence or authoritative Decision/Contract/PRD/governance
change required before closing.
```

Apply one type, one priority, at least one area, add the Issue to `LMDJ Work`, and set Stage/Area/Priority fields. Create no more than ten Issues before a duplicate/title/source audit.

- [ ] **Step 3: Cross-link retained question context**

For each migrated `docs/prd/questions/*.md`, add:

```markdown
- GitHub Issue: [#NUMBER](https://github.com/endaye/lmdj/issues/NUMBER) — live status and discussion
```

Replace its old live status value with `已迁移；以 GitHub Issue 为准`. Do not alter the question, importance, timing, or source context.

Update the migration inventory with the real Issue number and URL for every migrated row. Keep `already complete` and `historical only` rows unlinked.

- [ ] **Step 4: Verify deduplication, linkage, and Project membership**

Run:

```bash
gh issue list --state open --limit 200 --json number,title,labels,projectItems,url
gh project item-list "$LMDJ_PROJECT_NUMBER" --owner endaye --limit 500 --format json
rg -L 'GitHub Issue:' docs/prd/questions/*.md
git diff --check
bash scripts/architecture-portal.sh check
```

Expected: no migrated question file lacks an Issue link; every new Issue has one type, one priority, at least one area, and Project membership; no duplicate source link appears in two open Issues.

- [ ] **Step 5: Commit repository cross-links**

Stage only the migration inventory and migrated question files, inspect the staged list and complete diff, then commit:

```bash
git commit -m "docs(prd): link active questions to GitHub Issues"
```

### Task 7: Final Acceptance and Handoff

**Files:**

- Modify: `docs/quality/2026-08-20-github-work-management-remote-setup.md` only if final evidence adds verified values.

**Interfaces:**

- Consumes: completed repository contract, remote setup, and migration.
- Produces: final evidence separating local commit, remote GitHub state, merged state, and any remaining authorization boundary.

- [ ] **Step 1: Verify the complete story**

Verify:

```bash
python3 -m unittest tests.build.ci_github_work_management_test tests.build.ci_change_scope_test
scripts/local-ci.sh --no-cache
bash scripts/architecture-portal.sh check
gh label list --limit 100 --json name,color,description
gh project field-list "$LMDJ_PROJECT_NUMBER" --owner endaye --format json
gh project item-list "$LMDJ_PROJECT_NUMBER" --owner endaye --limit 500 --format json
gh issue list --state open --limit 200 --json number,title,labels,projectItems,url
git log --oneline origin/main..HEAD
git status --short --branch
```

Expected: repository checks PASS; Project fields and all active items are visible; no work-management file is uncommitted; every local commit is enumerated separately from remote/merged state.

- [ ] **Step 2: Report without crossing later boundaries**

Report Issue Forms, label count, Project URL, migrated/linked/skipped/decision-needed counts, commits, test results, and exact Git/PR/merge state. Do not infer push, merge, release, deployment, or publication from local completion.

## Version Management

Version impact: none.

Reason: the work changes repository and GitHub work-management governance only. It does not change a Product Build, Core Module, Provider implementation, or Contract.

## Documentation Impact

Documentation impact: none for Architecture Portal routes.

Reason: repository governance, PRD routing, and quality evidence change, but no current Product, Module, Host, Provider, Contract, Channel, or revision identity changes. `scripts/architecture-portal.sh check` remains required for every documentation Task.
