# P1 Pad capture with protected merged default streaming

Relates to #1664. Compose the actual protected Main after T5 shipping into
the reviewed capture head. The real ordered inputs are capture
`9f2daf95ba0824ff0567ba4fbeb7648f81b5de20` and protected Main
`fb66a608d82134f7f485a05aad0f7a61f0107130`. T5 is actually merged, not merely
represented by a historical feature parent.

## Declared files

The complete incoming Main inventory below is imported byte-exact. The five
conflict resolutions retain the exact reviewed capture-side bytes; the
reference tree from the successful read-only pre-T5 Main-plus-capture merge is
`4f5ccadf47bc025aa908b30636798785e705337d`. No new Creator behavior is introduced.

- `.agents/pitfalls/asan-macos-fork-child-stack-depot-boundary.md`
- `CMakeLists.txt`
- `apps/cardputer-host/main/transfer_session.hpp`
- `apps/cardputer-host/main/usb_transfer_endpoint.cpp`
- `apps/cardputer-host/main/usb_transfer_endpoint.hpp`
- `apps/docs-site/docs/platform/input.mdx`
- `docs/plans/2026-09-12-cardputer-transfer-display.md`
- `docs/plans/2026-10-05-1752-crash-test-processes.md`
- `docs/plans/2026-10-05-cardputer-transfer-display-recovery.md`
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

The conflict resolution paths (unchanged from the reviewed capture head) are:

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/src/runtime/input_controller.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/docs-site/docs/hosts/creator-web.mdx`

This plan is the only new source document. Verify the complete real resolved
index equals the reference tree before adding this plan. Preserve the actual
first conflicting merge and the transient unknown GitHub observation.

## Verification

- `scripts/creator-web.sh test`: preserve native first-gesture input, default
  authoring admission, empty-Pad capture, resource retirement and retained take
  semantics across the actual imported source.
- Creator TypeScript build: retain all callback and shared runtime interfaces.
- `tests/build/ci_change_scope_test.py`: admit the new declared plan and preserve
  conservative ownership of the imported source.
- `scripts/docs-site.sh check`: check the current documented source facts and
  retain all immutable historical snapshots.

After the Conventional merge commit, derive the exact owned lane inputs on the
clean current head. Reuse only genuinely identical verified lane inputs; run
changed Task lanes with original recipes/budgets and retain their original
outputs. Obtain current-head review and recheck real protection/conversations
before guarded squash merge. No old-head adoption is asserted for the new head.

## Version Management

Version impact: none. Import the existing Main identities; all P1 component and
Product Build debt remains in the separately declared T8 settlement. No testing
Build or snapshot is allocated here.

## Documentation impact

Documentation impact: required.
Affected portal pages: /platform/input/ /hosts/creator-web/

The current Input page is an exact Main import; Creator remains exact reviewed
capture Source. No release, tag, publication, Creator deployment, Channel
promotion, real-device/hearing acceptance or cleanup is initiated.
