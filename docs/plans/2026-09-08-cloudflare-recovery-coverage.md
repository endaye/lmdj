# Portal recovery transaction coverage

Relates to #873 and #923.

## Task

Add deterministic failure and concurrent-operator coverage of the existing Portal
production transaction. Declared files: this plan and
`tests/build/ci_cloudflare_portal_deploy_test.py`.

Verify first upload failure, existing candidate failure, first production smoke
failure, a competing deployment during preview and production checks, unknown
publication receipt without duplicate candidate POST, and rejected recovery.
Each test asserts resulting route/deployment state and evidence after the fault.
The fake API models a committed mutation before a lost response, and another
operator changing deployment state during smoke. This is deterministic ordering
coverage, not a proof of atomic compare-and-swap against every possible race.

Validation: `python3 tests/build/ci_cloudflare_portal_deploy_test.py` and
`python3 tests/build/ci_change_scope_test.py`; no new runtime gates.

The actual isolated A → B → A cloud journey is separately recorded on #923,
comment 5581166280. These tests do not claim physical acceptance, a completed
stability window, or a live production rollback. Product behavior is unchanged.

## Version Management

Version impact: none; tests and plan only, no Product or Assembly change.

## Documentation Impact

Documentation impact: none; verification coverage only, with no changed Portal
source facts or deployment behavior.
