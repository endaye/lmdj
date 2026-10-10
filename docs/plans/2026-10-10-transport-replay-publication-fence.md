# Transport replay through a pending Pattern publication

## Premises at current main

Base: `4281d5f54dd01ad73c18e876c2119a35b0229e0b`.
Relates to #1230 and the Creator Desktop Final follow-up Goal. This is separate
from #1941's landed-overlay cutoff repair; do not change its live proof tree.

The exact-head #1941 Creator proof accepted a Play/Stop command, then refused
same-identity retries with `a Pattern publication is pending` before the next
stopped Record could run. The retained debug requests show the original accepted
payload and identical retries. This identifies a concrete ordering premise,
not the complete cause of that browser journey's later failure.

Current main still checks pending Engine publication before calling the Facade
controller. The Facade already retains pending and completed command identities
and resolves exact replays before new admission effects. No successor merged
or open bounded issue found in the publication/replay queries implements this
premise. Pending publication must continue refusing genuinely new stopped
intents before durable admission; an existing retained command must reach its
original authority, including payload/identity validation. All earlier browser
failures, #1868/#1733 and physical transport acceptance remain open.

## T1 — reproduce and repair retained replay ordering

Declared files:

- `packages/application-facade/include/lmdj/facade/pattern_transport_controller.hpp`
- `packages/application-facade/src/pattern_transport_controller.hpp`
- `packages/application-facade/src/pattern_transport_controller.cpp`
- `packages/application-facade/src/pattern_transport_controller_factory.cpp`
- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `docs/plans/2026-10-10-transport-replay-publication-fence.md`

First add a real ControlRuntime/RealtimeEngine scenario: play and stop; schedule
an unapplied BPM publication while stopped; replay both retained commands;
reject a changed payload and genuinely new play/record intents while publication
is pending; apply the publication and verify the fresh play then works. Replays
must change no Truth, transport epoch or publication identity. Use deterministic
render quanta, not wall-clock musical progress or a mocked Facade.

Run the complete existing `host.web_control_runtime` group against this new
scenario before repairing source, and retain its own failing assertion. Only
then choose the repair. Any additive Facade identity query must be a pure read
on the existing serialized control lane; the Facade keeps full replay/payload
validation and admission authority. Do not duplicate the command ledger in the
Host, special-case only the last command, lift the pending-publication guard for
new intents, change timing/stop behavior, or settle any new concurrency policy.

Lowest-tier verification:

- `scripts/core.sh configure dev`
- `cmake --build build/core/dev --target lmdj_web_control_runtime_tests`
- `ctest --test-dir build/core/dev -R '^host.web_control_runtime$' --output-on-failure`
- `scripts/docs-site.sh check` for the documented public Facade query

Use the actual configured build directory produced by the stable entry point;
record it and retain all original group cases and CTest deadlines. Rebuild the
artifact for red/revert/restore proofs with fresh source mtimes; record build
exit status and the failing scenario line. The complete selected batch lanes,
current-head independent review and live protections remain merge obligations.
Do not count this lowest-tier group as complete browser/device acceptance.

## Version Management

No version identity or Product Build is allocated in this Task.
The repair adds a public pure-read Facade identity query: compatible
application-facade MINOR debt; the Web platform behavior repair records PATCH
debt. Bind the final
assessment to the implemented diff and settle it with the Goal's V1 work using
active manifests. This Task performs no tag, Release, deployment or promotion.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/
Reason: the implemented repair adds a public pure-read controller query.
Document its serialized control-lane requirement and absence of admission
authority on the existing Facade page. No protocol shape, user action,
ownership boundary or architecture diagram topology changes.

## Pitfall Impact

Pitfall impact: none
Reason: the suspected defect is a product ordering invariant covered by a real
native regression. Existing retained-artifact and rebuild-proof guidance applies.

## Verification state

The first full native-group invocation rebuilt successfully, then timed out at
the original 120-second CTest deadline before observing the new assertion at
line 8246. It is an invalid defect proof; no product repair follows from it.
Retain that log and move only the added scenario to the start of the same
`main()`, preserving every original case and their relative order. Rebuild and
invoke the complete group again at its unchanged deadline to identify the
scenario's own failure. This is test ordering for the reduction, not a filter,
skipped case, relaxed bound, or successful verification.

The case-first rebuilt group failed at its own line 8246 in 1.64 seconds,
before any product repair. Every original case and their relative order remain
byte-identical after removing the added call. Fresh main
`d5554ed55f7ebc2d800285715cef79dcfed57c9a` leaves all six declared product/test
sources unchanged from this Task's base.

The bounded repair adds `retains_command_id`, a pure lookup of pending and all
completed IDs on the existing serialized Facade control lane. Host pending
publication refusal applies to new IDs; retained IDs reach the original full
request validation, including changed-payload refusal. No Host ledger, special
last-command exception, admission side effect or new concurrency policy is
introduced. The complete unchanged-deadline native group must now pass before
commit. The initial unrelated timeout remains retained, without causal closure.

The first repaired build passed (30.17 seconds). The complete group then passed
the retained replay, changed-payload and new-ID refusal checks, but failed at the
new scenario's far-side line 8279 in 0.995 seconds. One render quantum did not
reach the existing scheduled publication's bar boundary. This is an invalid
fixture assumption, not evidence that the boundary should change. The scenario
now advances deterministic render quanta through the engine's reported
`pending_activation_frame`, then asserts the exact pending generation landed.
No clock sleeping, musical phase policy, original case or CTest deadline changes.
The original pre-fix line 8246 and its preceding reproduction remain unchanged.
Rebuild and run the complete group again before commit.

The corrected fixture rebuilt successfully (8.95 seconds), then the complete
original `host.web_control_runtime` group passed in 59.89 seconds at its unchanged
120-second deadline. Staged-file ownership passed all 77 checks (6.15 seconds),
and the Portal check passed all 50 routes (78.68 seconds). The frozen eight-file
input inventory remained unchanged throughout these checks; this results
paragraph is the only subsequent edit. A fresh precommit main audit at
`d5554ed55f7ebc2d800285715cef79dcfed57c9a` confirmed all six product/test
baselines still match the Task's base. The earlier unrelated timeout and invalid
one-quantum fixture result remain retained.

Task-specific green verification is complete. Push, current-head independent
review, complete selected batch lanes, guarded merge, browser/device acceptance
and V1 remain incomplete.
