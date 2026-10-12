# FIX: Native Host Performance CLI inventory missing the P1 live-control operations

## Task

`host.performance_cli` is red on main since P1 (`d21ea97c`): the Facade
registered `performance.live.control` / `performance.live.status`
(`application.cpp:185-186`) but the Native Host forwarding table
`kPerformanceOperations` (`apps/native-host/src/main.cpp`) and the pinning
expectation dict (`tests/host/performance_cli_test.py`) were never updated.
P1's plan neither declared nor deliberately deferred the Native Host
inventory — this is an oversight, and the CLI contract test exists precisely
to make inventory drift loud.

## Fix

Add the two operations to `kPerformanceOperations` (command / query matching
the Facade registration) and to the test's `PERFORMANCE_OPERATIONS` dict
(24 → 26). No Facade, Contract, or behavior change; the CLI forwards to the
already-registered Facade operations.

## Declared files

- `apps/native-host/src/main.cpp`
- `tests/host/performance_cli_test.py`
- `docs/plans/2026-10-12-performance-cli-live-ops-fix.md` (this file)

## Verification

- RED on this tree before the fix: `ctest -R '^host\.performance_cli$'`
  exit=8, `performance_cli_test.py:279` inventory assertion
  (`/tmp/fix2-owning.log`).
- GREEN after the fix on rebuilt artifact: exit=0
  (`/tmp/fix2-build3.log`, `/tmp/fix2-owning3.log`).

## Version Management

Version impact: none
Reason: the Native Host forwards already-registered Facade operations; no
Module SemVer-visible behavior change, no Contract, no Product Build change.
The P10-D20 inventory pin is a test fact, not a versioned identity.

## Documentation Impact

Documentation impact: none
Reason: no portal page enumerates the Native Host CLI operation inventory;
the Facade operation registration it documents was P1's and is unchanged.
