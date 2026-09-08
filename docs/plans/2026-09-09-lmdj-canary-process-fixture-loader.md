# Restore the sanitized-process fixture on CI

This prerequisite repair belongs to the
[result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md).

## Declared files

- `tests/build/ci_canary_assessment_runtime_test.py`
- `.agents/pitfalls/sanitized-child-interpreter-dependency.md`
- This plan.

Main batch `34272435905/1`, target `e07fc92bf866914e2dd403ca9fdcbabe8f5a7048`,
ran only ci_contract and failed the newly added process tests. Even sleep/output
fixtures returned runtime_failure; their output files were absent. Its Python
is installed under `/opt/actions-runner-02/_work/_tool/Python/3.11.15/x64` and
setup-python exports that directory's lib as LD_LIBRARY_PATH. The failure shape
and upstream loader behavior point to an interpreter dependency discarded by
the intentionally sanitized environment, not an actual model timeout. Raw child
stderr was deliberately discarded, so the exact remote loader message is not
available and must not be invented.

Probe a small closed set of interpreter candidates using the same clean child
environment and a fixed stdlib/identity response. Use only a verified interpreter
for the shebangs and direct process fixtures. Fail with why/remedy if no candidate
can start; do not skip tests, pass through LD_LIBRARY_PATH/LD_PRELOAD, modify the
production environment allowlist, loosen assertions or increase budgets. Keep
the parent tests on their configured Python. Exercise a real executable that
requires an environment variable to reproduce the selection boundary; this is
not a reproduction of GitHub's exact dynamic loader binary.

Verification: new failing selection regressions, full runtime/canary/CI tests,
pitfall contract, staged ownership and Portal check. After authorized shipment,
inspect the actual selected ci_contract lane on main; local success alone does
not close the platform acceptance gap.

## Version Management

Version impact: none
Reason: fixture interpreter selection only; no production identity or behavior.

## Documentation Impact

Documentation impact: none
Reason: no operator command, Portal page, workflow or Product change.
