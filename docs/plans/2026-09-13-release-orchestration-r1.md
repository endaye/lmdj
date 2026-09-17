# Release orchestration R1: authority and closed defaults

Status: implemented and locally verified; PR delivery pending. This Task does not
perform a release.

## Scope

Implement the first prerequisite of the single-command release design: align
agent authority with current AGENTS.md and parse immutable closed defaults for
web-hosts-dev. Keep all transition verification, current-head review, signing,
history and external approval boundaries. The full run/status/resume controller,
candidate preparation, changelog publication, service and live rehearsal remain
subsequent Tasks; this Task is not the complete automation deliverable.

Declared files:

- `.agents/skills/lmdj-release/SKILL.md`
- `docs/governance/git-workflow.md`
- `docs/governance/version-management.md`
- `docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md`
- `docs/plans/2026-09-13-release-orchestration-r1.md`
- `tools/release/orchestration-policy.json`
- `tools/release/orchestration_policy.py`
- `tests/build/release_model_test.py`
- `tests/build/release_skill_test.py`
- `apps/docs-site/docs/operations/version-and-release.mdx`

## Verification

Run `python3 tests/build/release_model_test.py` for scope closure, digest binding,
duplicate-key rejection and bounded recovery; existing registration in root
`CMakeLists.txt` already executes this file. Run `python3 tests/build/release_skill_test.py`
for retained verification requirements and removal of obsolete unconditional
per-transition stops. Independently forward-test full release, audit-only and
unknown-result / external-approval scenarios without external mutations.

Run skill-creator quick validation, `scripts/docs-site.sh check` and staged
`python3 tests/build/ci_change_scope_test.py`. No new required CI gate is added.
The original baseline tracked build outputs violated ownership (72 tests,
two failures). Prerequisite PR #1266 removes those generated outputs and adds
regressions against reintroduction; R1 is based on that independent repair.
The initial failure remains recorded, not reclassified as a pass.

### Delivery verification after prerequisite merge

PR #1266 merged as `52856e25f16f9dd9487a776ea1b43838ae8e34cc`.
This R1 change was replayed without conflicts from original `74d20f59` onto
that refreshed main in `feat/release-policy-delivery`; the original local
implementation stack remains intact. Only the ten declared files are included.

- Model: 28/28; release skill: 13/13; both exit 0.
- Staged ownership: 74/74 in 5.746s, exit 0;
  `/tmp/lmdj-policy-delivery-ownership.log`.
- Skill quick validation: valid, exit 0.
- Full Node 22 Portal check: 116/116 tests, production build, 46 routes and
  internal links passed, exit 0; `/tmp/lmdj-policy-delivery-portal.log`.
  Actual built operations/version-and-release HTML includes the default scope
  and the explicit boundary that run/resume and unattended release are not yet
  implemented by this Task.
- PR body closing-directive lint and documentation-impact declaration passed.
  Range classification selects ci_contract, deploy_contract, docs_static, portal;
  classification is advisory, not a claim those entire CI lanes ran locally.
- Pitfall disposition: no new recurrence; the Task implements the requested
  authority change and retains staged ownership and current-page checks.

No candidate, live review, complete-CI dispatch, signing, public Release,
deployment, promotion, credential change or protection change is established
by these local checks. Full controller and real acceptance remain outstanding.

## Version Management

Version impact: none

Reason: operational policy and agent guidance only; no Product, Assembly, Host,
Module, Provider, Contract or Model identity changes, allocation or snapshot.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: describe single authorization with separate verification, and distinguish
implemented default parsing from the not-yet-implemented end-to-end controller.
