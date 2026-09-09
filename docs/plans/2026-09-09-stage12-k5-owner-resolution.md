# Stage 12 K5: Project Asset owner resolution and Host reference execution

Status: proposed for the owner-API/Host-surface review required by K5.
Relates to #1037, #467, #472. This document does not complete those Issues.
Observed implementation baseline: `9b404548` after K4 #1084 and #1085.
Product identity is read from `products/lmdj/version.json`; no Build is reserved.

## Decision to review

Approve one bounded integration: only an explicitly named, already imported
Project Asset can own an input. CLI, MCP, Native Host and both Web Hosts forward
through the Facade. Add explicit, session-local permission configuration; keep
the Product default policy and Slice's `test` platform descriptor unchanged.
The result is a programmatic reference-execution journey, not a slicing UI,
production detector selection, preview, adoption, native/web platform claim,
Job/recipe state or new Project Contract. Those remain later Tasks.

The prior K5 gate is concrete: the existing plan says “The owner-read API and
all new production Host wiring remain separately unapproved”. User authority to
ship an implemented Task does not choose this previously unspecified public
input-owner or permission surface. Review the complete proposal below once;
normal commit/push/PR/review/merge need no repeated approval afterward.

## Evidence and why an injected callback alone is insufficient

- `ProjectStore::read_artifact(bundle, ref)` reads and verifies bytes but does
  not establish that the named Project/Asset owns the complete reference.
- `ProjectStore::load` may recover uncommitted work and scavenge staging. K5
  must not call it merely to authorize a Provider input; a refusal must not
  trigger authoring recovery or cleanup.
- Facade `provider_run` currently passes an empty resolver. SDK ingress already
  validates permissions/bindings/budgets before resolving inputs and freezes
  verified bytes before `run`.
- An owner read error currently becomes `input_artifact_unavailable` in SDK
  ingress. A verified owner's corruption refusal needs its existing
  `input_artifact_mismatch` category preserved, not hidden as missing input.
- The Wasm `bridge.cpp` constructs an empty Registry/ProviderPolicy even though
  Product CMake links the compiled catalog. Its protocol and ControlRuntime do
  not expose Provider/Attempt operations. Native Host also has no forwarding
  table for these operations. C ABI/CLI/MCP forwarding already exists.

These are source observations, not proof that K5 is implemented.

## Proposed owner read API

Add this non-virtual, product-neutral Project I/O operation:

```cpp
foundation::Result<std::vector<std::byte>> read_asset_artifact(
    const std::filesystem::path& bundle,
    const foundation::ProjectId& project_id,
    const foundation::AssetId& asset_id,
    const foundation::ArtifactRef& artifact) const;
```

Use one existing `ProjectWriterLease` for reading committed metadata, checking
Project ID, Asset ID and the entire ArtifactRef, and reading/verifying bytes.
Do not call public `load`, run recovery, scavenge, import, or mutate Project Truth.
Reuse an internal verified-byte reader with `read_artifact`; do not acquire a
second nested lease. Refuse busy/missing/unowned inputs. Release the lease when
owned bytes have been returned; SDK then independently copies, checks hash and
length and owns its immutable staging. Do not retain a Project lock during the
Provider call. This does not lock against arbitrary external filesystem writers
or promise an owner RSS limit; detected byte/length drift fails closed.

Introduce an explicit Project I/O error discriminator for verified byte mismatch
(e.g. `kStorageConditionArtifactMismatch`), used by the new method's length/hash
failures. Facade translates only that condition to `IO_ERROR` with
`input_artifact_mismatch`; other owner failures become unavailable without paths.
SDK ingress preserves only that exact trusted-resolver code/reason pair; it
normalizes all other resolver errors as before. Provider-returned failures keep
their separate existing whitelist and cannot impersonate this owner error.
No new SDK callback type, plural Candidate, or run ABI is introduced.

## Proposed Facade request and permission API

`provider.run` keeps its existing required fields and adds optional `input_owners`:

```json
{
  "input_owners": [
    {
      "port": "source_audio",
      "occurrence": 0,
      "project_path": "/explicit/project.lmdj",
      "project_id": "00000000-0000-4000-8000-000000000001",
      "asset_id": "00000000-0000-4000-8000-000000000002"
    }
  ]
}
```

This is a fragment of the Facade envelope, never a Provider parameter object.
The actual complete ArtifactRef remains in `inputs`. If owners are supplied,
require exactly one selector per input occurrence, no duplicates, extra keys or
unbound selector. An absent owner list preserves the old unbound Proof and
missing-owner behavior. Shape/selector errors fail before owner reads.
The transient resolver can resolve only the exact bound reference associated
with the selector. It calls the new Project I/O API after SDK permission, port,
media/count and aggregate-budget checks. Unknown Project/Asset or a different
complete ArtifactRef is unavailable; actual corrupt bytes are mismatch.

Owner paths/selectors are not forwarded to Provider `parameters`, saved in
Attempt request metadata, or returned in errors. Attempt inspection retains its
existing complete input ArtifactRefs and immutable terminal. K5 creates no
persistent owner-index, Candidate recipe or Project linkage record.

Add `provider.permissions.configure` with exactly `granted_permissions: string[]`.
This is an explicit Host-settings command that replaces the current Application
session's granted set; duplicates and tokens absent from registered descriptors
are rejected. Return the effective set. Region/classification policy is unchanged.
It does not persist to Project or Workspace and does not grant anything during
`provider.select`/`provider.run`. Restart restores the Assembly default; callers
must configure again explicitly. All calls use the Host's existing serialized
Facade command lane. No new concurrent policy mutation semantics are promised.

This is not an authentication boundary between mutually untrusted callers of one
Application session. It exposes the same trusted Host-settings authority as
`ApplicationConfig.provider_policy`, and must be presented as an explicit grant
by later UI/agent flows. Default `proof.execute` remains the sole Product grant.

## Host adaptation

- CLI and C ABI: existing generic command/query transport carries the Facade
  extension; validate canonical JSON and exact error/terminal parity.
- MCP: add the optional owner Schema and explicit permission tool; preserve all
  current required fields, strict additional-properties checks and error flags.
- Native: add a dedicated forwarding table for Provider list/select/run,
  permission configuration and Attempt inspect. Source owner paths must match
  the Native Host's selected Project. Use its existing Facade mutex; no bundle
  parsing or direct Artifact reads. Test with `--no-device` on Linux and the
  native suite on macOS when available; neither is physical audio acceptance.
- Web: Product CMake embeds its Assembly plus the Assembly schema at known
  virtual paths. `bridge.cpp` asks the existing Facade loader for the installed
  registry/default policy and fails initialization if loading fails. It never
  constructs Product registrations itself. Both Hosts use the shared bridge.
- Web protocol/ControlRuntime: add the five operations above. Owner selectors
  omit `project_path` in Web payloads; reject any supplied path and inject only
  the retained Project path at the Facade boundary. Require an open Project
  for owned execution, and no sidecar. Operations use the existing serialized
  control lane. Expose a small RuntimeSession method for these programmatic
  operations so packaged tests need no private Wasm export or test-only backdoor.
  No Creator controls, preview or adoption behavior are added.

Every positive Slice journey explicitly configures `sample.slice.execute`,
selects `local.sample.slice`, and uses the existing `test` descriptor token.
This demonstrates the reference through real Host transports; it does not add
`native`/`web` to the Provider's advertised platforms or certify physical devices.

## Acceptance and lowest-tier verification

One fact per regression; journeys retain all transitions. New CTest registrations
must exist and be discovered with `ctest --preset dev -N`, not only named here.

| Defect / journey | Concrete test registration or command |
| --- | --- |
| Wrong Project/Asset/full ref can read bytes; read triggers cleanup; nested lease or busy owner mishandled | Extend `project_io.project_store` in `tests/core/project_io/project_store_test.cpp`; instrument existing storage-platform seam and assert no writes/recovery |
| Owner corruption gets mislabeled unavailable; Provider can spoof owner failure | Extend `provider.artifact_source` and existing output-validation tests; trusted resolver mismatch versus untrusted Provider-returned error |
| Facade reads before SDK authorization/budget/binding gates, or leaks owner paths | New `facade.provider_owner` in `tests/core/facade/provider_owner_test.cpp`, registered in Facade CMake and linked to Product in Product CMake |
| CLI/MCP/native disagree on success/refusal/reopen | New `host.provider_owner` in `tests/host/provider_owner_test.py`, registered in Native CMake with CLI/native/C ABI binary arguments; reuse existing MCP transport harness |
| Web payload bypasses retained Project or grants implicitly | Extend `host.web_control_runtime`, `protocol.test.mjs`, `runtime_session.test.mjs`; test real registry supplied through Product linking |
| Packaged Web never routes owner bytes or loses terminal on restart | New `tests/platform/web/host/web_runtime_provider_owner.spec.mjs` through `scripts/web-runtime-host.sh proof`, and `tests/platform/web/creator/creator_web_provider_owner.spec.mjs` through `scripts/creator-web.sh proof` |
| Source identities, lock, Package identities or snapshots disagree | Version/lock/module/schema checks, `scripts/core.sh proof`, full Portal check and exact post-squash provenance |

For each Host, execute: import actual PCM16 WAV through Facade -> inspect source
Project/Asset/ref -> explicit permission grant -> select -> run -> inspect ->
stop/close Host -> restart -> inspect the same terminal. Assert output port,
complete output digest/media/byte length, deterministic expected SlicePoints and
source identity. Compare complete terminal before/after restart, not just status.
The component companion verifies published output bytes against digest/length
and consumer Schema, since Attempt inspect exposes metadata rather than an
arbitrary public blob-reading endpoint. Do not add a blob-scan endpoint for tests.

Run refusal legs for absent permission, missing owner, wrong Project, wrong
Asset/ref, malformed owner binding, missing file, same-length corruption,
changed byte length and busy Project. Snapshot Project JSON/revision/Assets/Pad
assignments before each run and assert unchanged afterward. For execution
refusals, restart and inspect the immutable failed terminal and empty outputs.
Shape errors rejected before Attempt creation must remain absent after restart.
After restart, a new Slice run without regrant must fail permission checks.

Run both existing complete Web proofs after shared bridge changes (pinned
Emscripten/Node/browser environment). Linux `--no-device`, browser automation and
component simulations are distinct evidence. A missing platform or failed lane
remains an unresolved acceptance item; do not close K5 on the green native prefix.
No stress tier is newly introduced merely for synchronous owner reads; if the
implementation changes lock-free/shared concurrent code, its stress/TSan
requirements apply and this inventory must be revised before that change.

## K5a proposed exact source inventory

The implementation must start with a fresh main/collision audit and reconcile
this inventory before editing. No wildcard authorizes additional production files.

- `packages/project-io/include/lmdj/project_io/project_store.hpp`
- `packages/project-io/include/lmdj/project_io/storage_platform.hpp`
- `packages/project-io/src/project_store.cpp`
- `packages/project-io/module.json`
- `packages/provider-sdk/src/attempt_store.cpp`
- `packages/provider-sdk/module.json`
- `packages/application-facade/src/application.cpp`
- `packages/application-facade/module.json`
- `packages/application-facade/CMakeLists.txt`
- `packages/web-runtime-platform/src/bridge.cpp`
- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/web/protocol.mjs`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `packages/web-runtime-platform/test/protocol.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/web-runtime-platform/CMakeLists.txt`
- `packages/web-runtime-platform/module.json`
- `apps/core-cli/module.json`
- `apps/core-mcp/lmdj_core_mcp/server.py`
- `apps/core-mcp/lmdj_core_mcp/__init__.py`
- `apps/core-mcp/pyproject.toml`
- `apps/core-mcp/module.json`
- `apps/native-host/src/main.cpp`
- `apps/native-host/CMakeLists.txt`
- `apps/native-host/module.json`
- `apps/web-runtime-host/module.json`
- `apps/creator-web/module.json`
- `apps/creator-web/package.json`
- `apps/creator-web/package-lock.json`
- `providers/local-proof-success/module.json`
- `providers/local-proof-success/src/provider.cpp`
- `providers/local-proof-success/CMakeLists.txt`
- `providers/local-proof-failure/module.json`
- `providers/local-proof-failure/src/provider.cpp`
- `providers/local-proof-failure/CMakeLists.txt`
- `providers/local-sample-slice/module.json`
- `providers/local-sample-slice/src/provider.cpp`
- `providers/local-sample-slice/CMakeLists.txt`
- `products/lmdj/CMakeLists.txt`
- `products/lmdj/assembly.json`
- `products/lmdj/assembly.lock.json`
- `products/lmdj/version.json`
- `products/lmdj/src/compiled_assembly.cpp`
- `products/lmdj/generated/web-runtime-identity.json`
- `products/lmdj/generated/web-runtime-identity.mjs`
- `tests/core/project_io/project_store_test.cpp`
- `tests/core/provider/artifact_source_test.cpp`
- `tests/core/provider/conformance_test.cpp`
- `tests/core/provider/spec_regression_test.cpp`
- `tests/core/provider/sample_slice_test.cpp`
- `tests/core/provider/output_validation_test.cpp`
- `tests/core/facade/provider_owner_test.cpp` (new)
- `tests/core/facade/assembly_loader_test.cpp`
- `tests/core/facade/application_test.cpp`
- `tests/host/provider_owner_test.py` (new)
- `tests/host/mcp_stdio_test.py`
- `tests/host/mcp_facade_parity_test.py`
- `tests/host/native_host_source_boundary_test.py`
- `tests/platform/web/host/web_runtime_provider_owner.spec.mjs` (new)
- `tests/platform/web/creator/creator_web_provider_owner.spec.mjs` (new)
- `tests/build/version_test.py`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `apps/docs-site/docs/core/modules/provider-sdk.mdx`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/hosts/core-cli.mdx`
- `apps/docs-site/docs/hosts/core-mcp.mdx`
- `apps/docs-site/docs/hosts/native-host.mdx`
- `apps/docs-site/docs/hosts/web-runtime.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/providers/local-sample-slice.mdx`
- `apps/docs-site/docs/product/capability-map.mdx`
- `apps/docs-site/docs/assembly/lmdj.mdx`
- `apps/docs-site/docs/operations/creator-changelog.mdx`
- `apps/docs-site/docs/operations/runtime-changelog.mdx`
- `apps/docs-site/diagrams/application-facade.architecture.json`
- `apps/docs-site/static/diagrams/application-facade.html`
- `apps/docs-site/static/diagrams/application-facade.svg`
- `docs/plans/2026-09-09-stage12-k5-owner-resolution.md`

Verify exact dependency closure from every active manifest before allocation;
if additional consumers need pins, declare them here first. A new path must
pass the staged ownership suite; do not silently widen CI scope rules.

## K5b immutable snapshot

After K5a source/tests pass and the one source commit is clean, use
`scripts/docs-site.sh version PRODUCT_BUILD canary`. Stage only its exact
generated inventory under `apps/architecture-portal/` in a second Task/commit,
in the same integration PR. Full Product proof and Portal validation must pass
with that snapshot before shipping. Retain source objects through verification
at the actual merged introducing SHA; use the official witness only if required.
No frozen snapshot is edited to fit a later source change.

## Version Management

Version impact: none for this review-plan Task. No active identity is allocated.
Reason: the proposed public APIs and Host scope still need the K5 decision.

For implementation, allocate against fresh main, then record exact identities
before K5a edits: Project I/O and Facade MINOR for additive public operations;
SDK PATCH for retaining the already specified trusted mismatch error; Provider
PATCH for exact SDK dependency rebuilds; Web Platform and all Hosts MINOR for
new supported command surfaces. Assess actual ABI changes before assigning
numbers; a breaking implementation requires MAJOR instead. Contract IDs and
Slice Capability/profile/output versions remain unchanged. Product receives a
fresh BUILD with PATCH 0 plus a canary snapshot. No number is reserved here.

## Documentation Impact

Documentation impact: none for this review-plan Task. Reason: retained proposal
and dependency links do not change current Portal availability. Run Portal check
because the proposal makes concrete current-source observations.

Implementation Documentation impact: required. Affected portal pages:
`/core/modules/project-io/`, `/core/modules/provider-sdk/`,
`/core/modules/application-facade/`, `/core/modules/web-runtime-platform/`,
`/hosts/core-cli/`, `/hosts/core-mcp/`, `/hosts/native-host/`, `/hosts/web-runtime/`,
`/hosts/creator-web/`, `/providers/local-sample-slice/`, `/product/capability-map/`,
`/assembly/lmdj/`, `/operations/creator-changelog/`, `/operations/runtime-changelog/`.

## This review-plan Task

Declared files: this file,
`docs/plans/2026-09-08-lmdj-stage12-capability-implementation.md`, and
`docs/plans/2026-09-09-stage12-decision-followups.md`.
Verification: check proposed existing paths and links, compare owner/gate facts
with source, `scripts/docs-site.sh check`, staged ownership suite, PR declaration
and closing-directive lint. Pitfall impact: none; this preserves the existing
explicit owner review gate and names the complete Host journeys rather than
claiming that documenting a gap discharges it.
