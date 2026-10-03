# P1 T2: independently verified Sound Set slots

Relates to #1663. This is the Core/Platform prerequisite of the approved P1
streaming default Bank A workflow; it supplies no default corpus or boot seeding.

## Declared files

- `packages/project-io/include/lmdj/project_io/soundset_store.hpp`
- `packages/project-io/src/soundset_store.cpp`
- `packages/project-io/{include/lmdj/project_io/project_store.hpp,src/project_store.cpp}`
- `packages/application-facade/src/application.cpp`
- `packages/web-runtime-platform/src/{control_runtime.cpp,bridge.cpp}`
- `packages/web-runtime-platform/web/{protocol.mjs,runtime_session.mjs}`
- `apps/creator-web/src/runtime/runtime_types.ts`
- `tests/core/project_io/{soundset_store_test.cpp,soundset_install_commit_test.cpp}`
- `tests/core/facade/{soundset_facade_test.cpp,soundset_install_quota_test.cpp}`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/web-runtime-platform/test/{protocol.test.mjs,runtime_session.test.mjs}`
- Current portal `core/modules/{project-io,application-facade,web-runtime-platform}.mdx`
  under `apps/docs-site/docs/` and this plan.

## Implementation

Store an independently verified slot outside the complete Set publication tree.
Validate the complete original manifest/license, identity, unique-byte accounting
and all declared descriptors before resolving only the requested occupied slot.
Keep writer leases, atomic publication and content reauthentication. Complete Set
listing/install semantics remain atomic and cannot enumerate a slot cache.

Facade exposes catalog metadata without full acquisition, slot acquisition and
slot installation. Installation reuses InstallSoundSet receipts, target-exclusive
quota, lineage and expected revision, with a one-slot write set; collision refusal
must not silently replace user content. Host handles only Core-supplied object
addresses. Network/supply retry cannot hold the serial Project mutation queue.

## Verification

Lowest-tier required checks: native Sound Set store/facade/quota component tests;
Web control request/shape tests; protocol and Runtime Session JS tests. They catch
unrequested blob reads, partial publication as complete, tamper admission, lost
lineage, revision/quota/replay errors and host-defined manifest interpretation.
Run selected committed-head batch-only lanes, sequential Web toolchain/Runtime/
Creator proofs and portal checks before merge. Physical/default-service evidence
belongs to later P1 Tasks and cannot be inferred from this prerequisite.

## Version Management

Version impact: compatible IO/Facade/Platform API additions; MINOR debt is settled
with the approved coordinated P1 version Task. No Product Build or Contract ID is
allocated in this Task. Read live manifests during settlement.

## Documentation impact

Documentation impact: required
Affected portal pages: /core/modules/project-io/ /core/modules/application-facade/
/core/modules/web-runtime-platform/
Reason: Per-slot immutable cache and Facade/Platform acquisition/install behavior.
