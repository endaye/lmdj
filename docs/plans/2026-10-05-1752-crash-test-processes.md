# Crash-test process isolation (#1752)

## Scope and ownership

Replace the remaining native C++ test children with `posix_spawn` child roles.
PR #1830 owns `tests/core/facade/candidate_store_test.cpp` and
`candidate_fixture.hpp`; do not duplicate that migration. The final bare-fork
guard depends on that PR landing. Python release-tooling processes are outside
this ASan-instrumented native-test boundary.

Declared files:

- `tests/core/support/child_process.hpp`: shared self-spawn launch helper.
- `tests/core/project_io/candidate_adoption_test.cpp`: attach to the parent's
  bundle and crash at the same three publication hooks.
- `tests/core/project_io/performance_lifecycle_test.cpp`: spawned lock holders
  retain pipe readiness and owner-death reconciliation assertions.
- `tests/core/provider/host_settings_invariant_test.cpp`: spawned settings lock
  owner retains the busy/write/release journey.
- `tests/core/provider/execution_crash_test.cpp`: spawned execution and restart
  roles retain all six checkpoints and complete persisted Artifact identities.
- `tests/core/provider/byte_harness.hpp`: explicit borrowed fixture ownership,
  leaving default fixture creation and removal unchanged.
- `tests/core/facade/sequence_surface_test.cpp`: spawned sequence owner and
  admission-transfer roles retain SIGSTOP/SIGKILL and recovery/replay checks.
- `tests/core/facade/c_api_test.cpp`: spawned JSON-depth probes retain both
  rejected depths and the accepted depth control.
- `tests/core/support/no_bare_fork_test.py` and
  `tests/build/test_active_tree.sh`: after #1830 lands, reject native C++ test
  fork calls, including newly added files, independently of sanitizer state.
- `.agents/pitfalls/asan-macos-fork-child-stack-depot-boundary.md`: record the
  guard as the absorbed mechanism after all seven migrations are present.
- This plan.

## Verification

Lowest tier: the six existing component suites, including all three Sequence
Surface shards. Build and run them under native macOS ASan with the default
TMPDIR and the original 18-character `/private/tmp/lmdjt` control. Keep all
sanitizer settings, crash hooks, budgets and far-side assertions unchanged.
Each child attaches to the parent's exact fixture path; the parent alone owns
creation and deletion. Spawn failure and unexpected child exit remain failures.

The source gate catches native tests continuing in a copied ASan process image
after `fork`, before any test code can protect against Darwin child-handler
allocation. Its invariant is settled, decidable from C++ call tokens and
deterministic. Ignore comments and string literals; mutation-check a newly
added call and a comment-only reference. Run the existing active-tree entry
point and staged path-ownership suite. Before merge, run the selected batch-only
lanes on the committed head and retain their input-bound evidence.

## Version Management

Version impact: none — only native test process startup and regression guards
change; Product, Module, Provider and Contract identities do not change.

Documentation impact: none — no Architecture Portal route, diagram, projected
identity, product behavior or documented product source fact changes.
