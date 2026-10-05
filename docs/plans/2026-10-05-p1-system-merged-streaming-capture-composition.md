# P1 System with protected default streaming and current capture

Relates to #1665. Relates to #1664. Compose the reviewed System head
`f6e0462b381b4a3187b9f76dc43081a7b4b5e7a0` with the actual current capture
head `cd5512ef96a3b903689155a3445382b72efc93e5`. That incoming commit has
protected Main `fb66a608d82134f7f485a05aad0f7a61f0107130` as a real parent,
including the actual T5 squash. T6 must actually squash before this System PR.

## Declared files

The merge is conflict-free. These complete 29 incoming paths match their actual
capture-parent blobs and modes. Every prior System Creator source/test path is
unchanged; no new System or capture behavior is introduced.

- `.agents/pitfalls/asan-macos-fork-child-stack-depot-boundary.md`
- `CMakeLists.txt`
- `apps/cardputer-host/main/transfer_session.hpp`
- `apps/cardputer-host/main/usb_transfer_endpoint.cpp`
- `apps/cardputer-host/main/usb_transfer_endpoint.hpp`
- `apps/docs-site/docs/platform/input.mdx`
- `docs/plans/2026-09-12-cardputer-transfer-display.md`
- `docs/plans/2026-10-05-1752-crash-test-processes.md`
- `docs/plans/2026-10-05-cardputer-transfer-display-recovery.md`
- `docs/plans/2026-10-05-p1-capture-merged-streaming-composition.md`
- `docs/release-evidence/2026-10-05-supersede-allocated-1.0.21.0-1.0.25.0.md`
- `docs/release-evidence/release-intents.json`
- `tests/build/release_model_test.py`
- `tests/build/test_active_tree.sh`
- `tests/core/facade/c_api_test.cpp`
- `tests/core/facade/candidate_fixture.hpp`
- `tests/core/facade/candidate_store_test.cpp`
- `tests/core/facade/sequence_surface_test.cpp`
- `tests/core/project_io/candidate_adoption_test.cpp`
- `tests/core/project_io/performance_lifecycle_test.cpp`
- `tests/core/provider/byte_harness.hpp`
- `tests/core/provider/execution_crash_test.cpp`
- `tests/core/provider/host_settings_invariant_test.cpp`
- `tests/core/support/child_process.hpp`
- `tests/core/support/no_bare_fork_test.py`
- `tests/platform/cardputer/CMakeLists.txt`
- `tests/platform/cardputer/fake_esp/driver/usb_serial_jtag.h`
- `tests/platform/cardputer/fake_esp/esp_random.h`
- `tests/platform/cardputer/usb_display_test.cpp`

This plan is the only additional source document. The real pre-plan index must
match the read-only Git merge tree, and all other prior entries retain exact
System-side mode/blob identities.

## Verification

- `scripts/creator-web.sh test`: retain System navigation, Runtime/take ownership,
  capture cancellation and uninterrupted transport across the imported source.
- Creator TypeScript/Vite build: retain the composed Host callback interfaces.
- `tests/build/ci_change_scope_test.py`: verify staged new-file ownership.
- `scripts/docs-site.sh check`: verify imported Input facts, current Creator
  documentation and unchanged immutable historical snapshots.

On the clean committed head, derive canonical selected lanes against actual
protected Main. Run every selected batch-only lane with its original complete
recipe and budget, obtain current-head review, then refresh actual dependency
merges, protection, conversations and closing relations before guarded squash.
Old-head adoption does not attest the new head.

## Version Management

Version impact: none. Import existing Main identities without allocation.
Coordinated P1 version settlement remains the separately declared T8 work.

## Documentation impact

Documentation impact: required.
Affected portal pages: /platform/input/ /hosts/creator-web/

The Input page is an exact Main import; the current Creator page retains reviewed
System and capture facts. No Product Build or snapshot, release, tag, deployment,
Channel promotion, physical/hearing acceptance or cleanup is initiated.
