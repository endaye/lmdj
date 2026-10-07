# Stop Performance replay before transport or Project replacement

Task: implement #1801's [owner decision](https://github.com/endaye/lmdj/issues/1801#issuecomment-5976157940).
Play/Stop, Record and Project replacement stop the current Performance replay
through its own Facade operation, then perform the requested operation. Grid,
Pad and BPM edits retain #1789's replay publication fence.

## Declared files

- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/application-facade/src/performance_engine_adapter.cpp`
- `tests/core/facade/performance_engine_adapter_test.cpp`
- `docs/prd/decisions/2026-10-07-performance-replay-command-handoff.md`
- `docs/plans/2026-10-07-performance-replay-command-handoff.md`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`

## Implementation and verification

The serialized Host stops its tracked replay using the old Project path and
one stop request identity. It waits for the replay's neutral-reset receipt
within the original request deadline; a failure or timeout prevents the next
operation. Before a transport request it publishes the selected Pattern from
current Truth immediately and waits for
that exact publication to become current. Project create/open stop the replay
before replacing its session; the new Project supplies its own Pattern.

Project replacement requires suspended audio. The engine's quiescent Stop
already clears FX and voices, so the private replay sink accepts that stopped
engine as a completed neutral reset. It must not enqueue FX into stopped audio
or reactivate audio just to stop a replay.

Lowest-tier regressions use the real Facade engine adapter and the real Host:

- replay stop after quiescent engine Stop remains stopped after reactivation;
- Play, Stop and Record each wait for replay Stop and the selected Truth view;
- an edited view and a different replay Pattern cannot become transport's view;
- create/open replacement and reopening the original Project leave replay
  stopped, and a subsequent edit publishes normally;
- an unacknowledged Stop times out without starting transport or changing Truth.

Render fixed callbacks at observed acknowledgement boundaries rather than use
elapsed dispatch time as musical progress. Run the regressions against rebuilt
unchanged sources first, then rebuild the implementation and run
`facade.performance_engine_adapter`, `host.web_control_runtime` and
`host.web_performance_bridge`. Run `scripts/docs-site.sh check` for the two
changed portal routes, and staged new-file ownership checks before commit.
Shipping requires committed-head batch-only evidence, independent current-head
review, conversation resolution and a protected expected-head squash merge.
No new required gate, coverage floor or timeout adjustment.

## Version Management

Version impact: none. This implements approved command ordering within existing
operations and private adapters; API/ABI, request and response schemas, persisted
Project semantics and Package distribution identities do not change. No Product
Build or Assembly is allocated by this repair; a subsequent integration cut
allocates its own verified Build and snapshot.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/web-runtime-platform/ /hosts/creator-web/
Reason: replace the documented deferred transport/Project concurrency behavior
with the owner-approved stop-before-command rule. Existing source diagrams and
module ownership remain accurate.

## Pitfall Impact

Pitfall impact: none. The concurrency defect is product logic represented by
the regressions. Apply the existing deterministic audio-driver and complete
acceptance-journey guidance; record any actual process recurrence if encountered.
