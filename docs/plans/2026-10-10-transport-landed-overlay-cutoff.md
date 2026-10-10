# Retain a landed transport overlay before cutoff

## Objective and premises

This bounded repair belongs to Creator Desktop Final follow-up acceptance. The
complete clean b07e178d Creator proof failed global Record-off with
`cutoff does not match last applied publication`, while retaining the journal.
The current main base is 414268d654adeae32dfb500f62c000f06e4f2b47. Its coordinator,
journal cutoff validator and controller tests are byte-identical to b07e178d.
Live #1230 comments establish that transport and recovery are implemented;
#1513 and its coordinator-owned overlay publication are already delivered.
Those capabilities must not be implemented again. Current open PRs #1929,
#1936, #1937 and #1939 do not repair this coordinator.

The remaining hypothesis is a control/render interleaving: an overlay reaches
its audio boundary, but no idle control cadence retains that applied generation
before the closing command becomes pending. Current existing coverage always
calls publish_overlay after landing. The new regression must first demonstrate
that omitting only this cadence reaches the same cutoff failure; until then the
hypothesis remains unproven until the rebuilt regression runs. Other Creator failures remain independent gaps.

## T1 — Preserve the closing receipt's actual overlay authority

Declared files:

- packages/application-facade/src/pattern_transport_controller.cpp
- tests/core/facade/pattern_transport_controller_test.cpp
- docs/plans/2026-10-10-transport-landed-overlay-cutoff.md

Use the real engine-backed controller fixture to land the coordinator's overlay
without an intervening idle control tick, then close recording. Require
successful authoritative cutoff, continued playback for Record-off, exactly one
Project revision and retained event after reopen, and removal of the settled
journal. Also cover Play/Stop closing through the same boundary and a foreign writer
lease refusing repeated durable retains before the exact close retries. Preserve the
strict journal validation and its generation, Pattern and cutoff invariants.
Retain only an overlay generation proven applied by the actual receipt; preserve
journal retry/ack ordering and never label an unlanded or superseded generation
as applied. Change no audio receipt, public API or journal Contract.

Lowest-tier verification: configure dev; build target
lmdj_pattern_transport_controller_tests; CTest facade.pattern_transport_controller
with its original timeout. Retain failing rebuilt-artifact proof before source
repair, and rerun the complete unchanged controller group after repair. Use
canonical local-ci classification after the declared diff to identify required
batch-only evidence. A focused native pass is not full Creator or hardware
acceptance, nor permission to drop any selected lane.

## Version Management

Version impact: none
Reason: correction of the existing application-facade implementation without
manifest, API or Contract allocation; the module PATCH debt belongs to the Goal's
separate V1 version/Assembly settlement.

## Documentation Impact

Documentation impact: none
Reason: the repair restores the already documented Record-off/Stop authority and
exactly-once behavior; it adds no product capability, route or source identity.

## Pitfall Impact

Pitfall impact: none
Reason: pending investigation is a product interleaving, not a demonstrated new
workflow pitfall. Existing rebuild-proof and wall-clock budget guidance apply.

## Acceptance status

The unchanged implementation failed the rebuilt regression in 9.56 seconds at
its own closed.has_value assertion, reporting the same cutoff publication
mismatch. The regression pins both Record-off and Play/Stop interleavings using
the real engine. The repair retains only the matching applied generation named
by the no-switch closing receipt before strict cutoff validation; a failed
journal write keeps the marker and unacknowledged receipt for retry.

The final committed source diff selects full mode: three expensive families
(core, Creator, Web Runtime). Earlier focused classification covered the test-only
hypothesis diff and does not describe the final repair. Pull Request lanes are
ci_contract, docs_static and portal. Batch-only lanes are chameleon_lab,
core_asan, core_coverage, core_macos, core_ubuntu, creator, deploy_contract,
package, web_runtime_host, web_runtime_lab and web_toolchain. All remain pending;
start the three Linux Core lanes on the committed source, then continue the
remaining selected lanes. No selection, deadline, floor or acceptance leg is
reduced. No pass key, merge, whole-Creator or physical acceptance is claimed. The native controller group passed with real-writer retry coverage in 6.35
seconds. Removing only the 14-line repair, rebuilding with the final regression
unchanged, failed at its own closed.has_value assertion in 4.35 seconds with the
same cutoff publication mismatch. The fixed source was restored with a fresh
mtime and the complete original controller group passed again. Original
Creator failures, deadlines and retained artifacts remain.
