# Current candidate skill contract regression

## Scope

Declared files:

- `tests/build/release_skill_test.py`
- `docs/plans/2026-09-08-lmdj-ci-candidate-skill-contract.md`

The actual Deploy contract job `101942661777` in run `34188723712` failed on
the obsolete assertion demanding the former direct `main`/`target` wording.
The current skill correctly documents `self-test-report.yml`, main ref,
`batch_operation=reconcile` and the closed stable-ID/candidate/exact-target JSON.
The exact old test reproduced locally with one failure on baseline
`4eb6a139` (`/tmp/lmdj-candidate-skill-red.log`). This Task updates the test,
not the skill, policy, workflow, release state or product.

Keep the existing complete-test-v2, 16-suite, provenance, retention and
authorization assertions. A separate minimal regression parses the documented
candidate JSON and checks the current entry plus full scope, immutable request
redelivery and automatic-progress/release separation. It does not add obsolete
prose to make an old assertion green. Historical failed runs remain failed.

## Verification

Lowest tier: the exact `release_skill_test.py` contract. Also run the complete
`release_*test.py` inventory, affected incremental/runtime workflow contracts,
and staged ownership. This is test-only work; no release audit, product run,
remote dispatch or mutation is performed.

Actual local verification:

- Exact stale assertion: one reproduced failure before the change; the whole
  updated skill contract passes all 12 tests.
- Six isolated invalid-document mutations (wrong workflow, operation, kind,
  target field, missing stable ID, and 14 rather than 16 suites) are rejected;
  these probes do not edit the skill.
- Complete release contract inventory: 426 tests pass in 160.908 seconds.
  Its local fixture audit output is not a remote release audit or acceptance.
- Complete CI contract inventory: 1699 tests pass in 38.356 seconds with pinned
  actionlint 1.7.12 and explicit ShellCheck 0.9.0, without skips. An earlier
  default-tool run passed with one skip and is not the complete lint evidence.
- Staged ownership: 66 tests pass; staged whitespace check passes.

Local logs are `/tmp/lmdj-candidate-skill-{red,green,mutations,release,ci-pinned,ownership}.log`.
These are local regression results, not a rerun of the failed hosted job or
proof that the ongoing full product batch passed.

## Version Management

Version impact: none — only a regression test and its implementation record
change; no identity or product assembly allocation.

## Documentation Impact

Documentation impact: none — current Portal pages, diagrams, tooling and
documented product facts remain unchanged; the current skill is a read-only
test subject. A full Portal build is not applicable, not claimed passed.

## Pitfall Impact

Pitfall impact: none — the directly derivable stale assertion is repaired by
its local regression; existing full-journey and readable-failure guidance applies.

Root owns subsequent push, PR and merge; this Task commits locally only.
