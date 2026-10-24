# Recording segments retain nonzero target phase

Parent: #2112 / #2234. Base `6c7dfa88ecccd11557c01d96feec737109964ac3`.

## Premise refresh and authority

S5 P1/P2 are delivered by #2427/#2428 and must not be repeated. The approved
current-loop position model requires the actual `(S, numerator, BPM)` for
recording. The existing strict timing-profile grammar and transfer converter
already represent nonzero anchors. `continue_segment` instead hardcodes zero
in both creation and exact replay, while the private work carries only S/BPM.
The supplied anchor's voice/chase policy does not affect its durable identity.

Implement the independent I/O producer capability: carry an explicit unsigned
numerator with the private segment work, retain it unchanged in the existing
profile and refuse changed-numerator retries of the same work. Current
quantized production calls explicitly supply zero. Keep target input parked
until profile durability ACK; before that ACK no target candidate may require
a missing profile during cold recovery. Preserve every existing restart leg.

This does not enable Native OFF, choose target-note chase or claimed-predecessor
semantics, alter public wire/SDK, or expose a Creator option. Those dependencies
remain open and need their actual producers and acceptance.

## Task and declared files

One Task, one Conventional Commit.
- `packages/application-facade/src/pattern_admission_controller.hpp`
- `packages/application-facade/src/pattern_admission_controller.cpp`
- `packages/application-facade/src/pattern_transport_io_owner.cpp`
- `packages/application-facade/src/pattern_transport_controller.cpp`
- `tests/core/facade/pattern_transport_segment_test.cpp`
- `docs/plans/2026-10-25-recording-segment-phase-anchor.md`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/diagrams/application-facade.architecture.json`
- `apps/docs-site/static/diagrams/application-facade.html`
- `apps/docs-site/static/diagrams/application-facade.svg`

## Verification

Baseline and fixed complete `facade.pattern_transport_segment` and its original
restart registration. A valid nonzero fixture must fail the original literal
profile or independently expected event assertion before the product edit.
Verify retained fractional numerator, full A/B Truth, exact retry and changed
numerator refusal, UNKNOWN durability replay on reconstructed owner, actual
SIGKILL recovery and fresh Application reopen. Preserve all original zero-phase
cases, budgets and cleanup checks. Run the owning admission/transport/controller/
switch/stress and Journal checks; run complete segment component/restart under
ASan. No unrelated complete product lane is implied.

Run Core dependency checks, official Facade diagram rendering, complete Portal,
staged/committed path ownership, exact PR body/declaration and current-head
independent review before guarded merge. No new required gate or relaxed bound.

## Version Management

Version impact: Application Facade additive internal capability MINOR debt,
absorbed by its existing #2237 MINOR floor. No public class layout/vtable,
Journal grammar, Contract or active identity changes. No Product allocation.

## Documentation Impact

Documentation impact: required on `/core/modules/application-facade/`. Distinguish
phase-capable private I/O from the current quantized caller and still-unwired
OFF product. Regenerate only its official diagram outputs.

## Observed Task evidence

The untouched baseline component/restart passes (16.399s wrapper). The new
valid 960.5-tick fixture rebuilds the real test against the unchanged producer
and fails its literal retained-numerator assertion at line241 (CTest exit8);
that source and executable are retained. The fixed complete owning selection
passes10/10 (65.586s wrapper), including both Journal and switch stress and
all original segment legs. Nonzero exact replay, one-unit numerator collision,
malformed/missing phase refusal, source/target events and whole cold-reopened
Truth are checked independently.

Restart now executes32 original zero-phase and32 nonzero actual SIGKILL
boundaries, plus all3 failed-barrier child-reaping controls. ASan component
and restart also pass completely (64.906s wrapper), with no sanitizer finding.
Core dependency verification and official diagram rendering pass. No budgets,
assertions or original journey legs were weakened.

An initial aggregate build command named nonexistent `lmdj_project_io_tests`;
authoritative CMake identifies `lmdj_sequence_journal_tests`. The corrected
complete seven-target command passes. This command-selection error is retained
separately from the discriminating product RED.

Portal, staged path ownership, committed scope/body checks and independent
review remain required before shipping; their receipts belong to the PR.
