# Replay neutral handoff test frontier

## Task and refreshed premises

Initial base: `171f0f1be1d022b512d38a90a96c789e1aa821c6`; user authorized
continuing remaining worktrees. Sequence I2a integration on c2de40b6 passed
its Audio components and SPSC, but full audio-tag validation failed the Web
Host handoff fixture at control_runtime_test.cpp:7371 with HOST_TIMEOUT.
Retain that exact failed receipt. Current-main product/test inspection shows
#2044 reset_neutral submits nine legacy FX controls followed by an optional
independent Filter release and an unconditional Pad gate clear. The old
fixture waits only for nine FX enqueues, renders once and stops audio while
waiting for the next Pattern publication. The ninth FX is a prefix: audio may
run before the Pad gate is published. Control then correctly waits for that
undrained clear while the fixture incorrectly supplies no audio.

This is test scheduling, not permission to weaken the product reset fence.
Keep independent render/control, the two-second request deadline and complete
play/stop/record/rejection journeys. Advance explicit 128-frame audio quanta
until the handoff publication is observable; require every reset channel's
far-side drain and neutral state before the final publication callback. No
wall-clock musical progression, sleep, timeout increase or dropped assertion.

Declared files: this plan and
`packages/web-runtime-platform/test/control_runtime_test.cpp`, plus the shipping
recurrence in `.agents/pitfalls/shared-temporary-staging-ownership.md`.
Keep Sequence source and replay profile repair in separate Tasks.

## Verification

Build lmdj_web_control_runtime_tests freshly and run the unchanged complete
`host.web_control_runtime` registration. Preserve the prior failing fixture
receipt; independently rebuild the old no-progress wait as a mutation and
retain any actual outcome without inventing deterministic causation. Restore
with fresh mtime and verify the complete original registration. The strict
assertions additionally require all legacy FX drains, typed Filter neutral,
Pad gates accepted/applied agreement and neutral masks at the observed handoff.
Run staged new-file ownership and staged whitespace checks before commit.

## Version Management

Version impact: none — test-only scheduling correction changes no public ABI,
manifest, Contract grammar or active identity.

## Documentation Impact

Documentation impact: none — no Portal product boundary, source diagram,
projected identity, stable command, registration or timing policy changes.

## Pitfall disposition

The missing queued channel is derivable from the current reset product code.
The corrected owning journey is its exit; no process ledger recurrence.
The separate shared-cache ownership observation during shipping does qualify:
bump the existing absorbed entry, whose child-only temporary-directory
procedure is already the mechanism. No new gate or permission change.

Evidence: `/home/en/orca/evidence/worktree-resume-20261012/`.

### Input-bound checkpoint

Fast-forwarded to `a4923f20f78ba6780d1265882669b8a00a762de4`, which retains
the intervening CI recovery Task and merged direct Replay profile preflight.
Neither changes the reset protocol or this fixture. On this exact production
input, freshly rebuilding the original no-progress helper yields exit 8 at
HOST_TIMEOUT after 14.52 seconds. Restoring the corrected helper with fresh
mtime rebuilds its object and the complete unchanged registration passes,
exit 0 in 63.43 seconds. Preserve both receipts.

Final inspection accounts for publication arriving during the last reset
callback: require observable publication progress instead of requiring the
control response to remain pending. Its success, full reset drains, neutral
state and final selected Pattern remain required. Rebuild and rerun the
complete registration after this scheduling correction before commit.

Final helper fresh build exits 0 and the unchanged complete registration passes
in 61.77 seconds, exit 0. Both reset and publication transitions retain far-side
assertions and unchanged caller journeys. Staged new-file ownership passes all
77 tests with the plan in the index; staged whitespace check passes.
