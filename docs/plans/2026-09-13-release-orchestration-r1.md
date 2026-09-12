# Release orchestration R1: authority and closed defaults

Status: implementation in progress. This Task does not perform a release.

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

## Version Management

Version impact: none

Reason: operational policy and agent guidance only; no Product, Assembly, Host,
Module, Provider, Contract or Model identity changes, allocation or snapshot.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: describe single authorization with separate verification, and distinguish
implemented default parsing from the not-yet-implemented end-to-end controller.
