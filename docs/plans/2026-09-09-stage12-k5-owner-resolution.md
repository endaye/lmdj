# Stage 12 K5: Project Asset owner resolution and Host reference execution

Status: owner API and Host source implemented after user confirmation on
2026-09-09; clean-source packaging, immutable snapshot and full acceptance
are the remaining K5b verification boundaries.
Relates to #1037, #467, #472. This document does not complete those Issues.
Observed implementation baseline: `9b404548` after K4 #1084 and #1085.
Implementation allocation: `1.0.48.0`, canary. At allocation, fresh main was
`9b404548`; open PRs #1086/#1082/#1076/#1031 had no competing Product allocation, and
the exact remote `lmdj-v1.0.48.*` tag query returned no refs on 2026-09-09.

## Confirmed decision

The user confirmed this complete proposal ("确认") on 2026-09-09.
The approved integration is bounded: only an explicitly named, already imported
Project Asset can own an input. CLI, MCP, Native Host and both Web Hosts forward
through the Facade. Add explicit, session-local permission configuration; keep
the Product default policy and Slice's `test` platform descriptor unchanged.
The result is a programmatic reference-execution journey, not a slicing UI,
production detector selection, preview, adoption, native/web platform claim,
Job/recipe state or new Project Contract. Those remain later Tasks.

The prior K5 gate is concrete: the existing plan says “The owner-read API and
all new production Host wiring remain separately unapproved”. User authority to
ship an implemented Task does not choose this previously unspecified public
input-owner or permission surface. That separate design decision is now confirmed. Normal
commit/push/PR/review/merge need no repeated approval.

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
The internal metadata read omits the ordinary full-Project blob scan; verify
only the selected owned Artifact after checking metadata identity. Ordinary
authoring loads retain their existing full-asset verification.
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
  The existing published `window.lmdjWebRuntimeHost` namespace gains a read-only
  `providers` object containing those five Session methods in both packaged Hosts;
  standalone Session consumers continue to call the same methods directly.
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
| Packaged Web never routes owner bytes or loses terminal on restart | New `tests/platform/web/host/web_runtime_host_provider_owner.spec.mjs` through `scripts/web-runtime-host.sh proof`, and `tests/platform/web/creator/creator_web_provider_owner.spec.mjs` through `scripts/creator-web.sh proof` |
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
Native startup validates every Project Asset; for missing/corrupt-file refusal
fixtures, assert no changes first, then restore the original input bytes before
Native restart. The failed terminal must remain byte-for-byte unchanged after
that repair. Web Attempt inspection works after restart without reopening the
corrupt Project. Web holds its Project writer lease for the retained session;
a competing Host is refused at Project open before owned execution, with no
Attempt. Pair that real admission leg with the owner-read busy component and
CLI/MCP/Native refusal legs; do not inject a fake release of Web's live lease.
After restart, a new Slice run without regrant must fail permission checks.

Run both existing complete Web proofs after shared bridge changes (pinned
Emscripten/Node/browser environment). Linux `--no-device`, browser automation and
component simulations are distinct evidence. A missing platform or failed lane
remains an unresolved acceptance item; do not close K5 on the green native prefix.
No stress tier is newly introduced merely for synchronous owner reads; if the
implementation changes lock-free/shared concurrent code, its stress/TSan
requirements apply and this inventory must be revised before that change.

## K5a exact source inventory

The implementation must start with a fresh main/collision audit and reconcile
this inventory before editing. No wildcard authorizes additional production files.

- `packages/project-io/include/lmdj/project_io/project_store.hpp`
- `packages/project-io/include/lmdj/project_io/storage_platform.hpp`
- `packages/project-io/src/project_store.cpp`
- `packages/project-io/module.json`
- `packages/provider-sdk/src/attempt_store.cpp`
- `packages/provider-sdk/src/durable_file.cpp` (Web immutable publication under workspace lock)
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
- `tests/platform/web/host/web_runtime_host_provider_owner.spec.mjs` (new)
- `tests/platform/web/creator/creator_web_provider_owner.spec.mjs` (new)
- `tests/platform/web/provider_owner_journey.mjs` (new; shared packaged Host assertions)
- `tests/build/version_test.py`
- `tests/conformance/module_graph_test.py` (exact allocated Host dependencies)
- `tests/conformance/version_lock_test.py` (allocated Provider identity fixture)
- `apps/docs-site/test/repo-facts.test.mjs` (exact allocated Host identities)
- `scripts/ci/scope_policy.json` (shared browser journey owns both Host lanes)
- `.agents/skills/issue-done/SKILL.md` (absorb repeated pristine-symlink preflight)
- `.agents/pitfalls/worktree-checkout-flattens-symlinks.md` (record recurrence and skill exit)
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

### Creator regression fixture prerequisite

The full Creator proof exposed a baseline test classification error, reproduced
with both Node 22.16.0 and 22.23.1: WHATWG leaves `^` unchanged in a path, while
the proof server's intentionally narrower grammar refuses it. This separate
verification-repair Task declares only
`apps/creator-web/test/server_test.py`,
`tests/platform/web/creator/creator_web_capture.spec.mjs` and this plan. Move that input to the
existing proof-server-stricter corpus, retain server-start refusal for both
refused corpora, and require the Worker's complete unchanged base in the stricter
corpus. No input, refusal assertion, or acceptance journey is removed.
The complete capture journey also exposed a stale expected Asset shape after
reopen: Project v4 includes `lineage: null` for raw capture. Add that explicit
field to the complete equality assertion, retaining the full Artifact identity,
revision, Pattern events and restart boundary checks.
Verify the complete server suite and both complete Web proofs before freeze.
Version impact: none; test expectations only, no shipped behavior or identity.
Documentation impact: none; no Portal fact changes.

After K5a source/tests pass and the one source commit is clean, use
`scripts/docs-site.sh version PRODUCT_BUILD canary`. Stage only its exact
generated inventory under `apps/architecture-portal/` in a second Task/commit,
in the same integration PR. Full Product proof and Portal validation must pass
with that snapshot before shipping. Retain source objects through verification
at the actual merged introducing SHA; use the official witness only if required.
No frozen snapshot is edited to fit a later source change.

## Version Management

Version impact: required for K5a implementation. Exact manifest dependency
closure was inspected against main before edits:

| Identity | Baseline | Target | Reason |
| --- | --- | --- | --- |
| Project I/O | 3.0.0 | 3.1.0 | Add nonvirtual owned Artifact read |
| Facade | 4.0.1 | 4.1.0 | Add optional owners and session permission command |
| Provider SDK | 2.0.0 | 2.1.0 | Add Web durable execution and preserve trusted owner corruption classification; no ABI change |
| Proof success/failure Providers | 2.0.0 | 2.0.1 | Exact SDK dependency rebuild |
| Slice Provider | 1.0.0 | 1.0.1 | Exact SDK dependency rebuild |
| Web Runtime Platform | 5.0.1 | 5.1.0 | Add Provider transport methods |
| CLI / MCP / Native Hosts | 3.2.2 | 3.3.0 | Add owner execution and permission surfaces |
| Web Runtime / Creator Hosts | 4.1.2 | 4.2.0 | Forward programmatic Provider operations |
| Product | 1.0.47.0 | 1.0.48.0 | Changed Assembly identities; canary snapshot in K5b |

No Contract, model or descriptor platform changes. Existing Project data needs
no migration. Public C ABI version and existing SDK ABI remain unchanged;
Facade policy state stays private, with the AttemptStore reconstructed using
its existing constructor on explicit configuration. All exact consumers appear
in the declared inventory. Lock and runtime identities are regenerated through
their supported tools.

No tag, Release, deployment or Channel promotion is initiated. Any future
`lmdj-v1.0.48.0` tag requires the exact merged-main candidate, its complete
verified release evidence and separate overall release authorization. A rollback
uses an explicitly selected, previously verified immutable deployment; it never
moves or reuses an allocated identity.

## Documentation Impact

Documentation impact: required for this implementation. The earlier planning-only
PR #1086 changed no Portal availability. Affected portal pages:
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

### Packaged Web storage implementation finding

The first actual browser Provider run returned IO_ERROR before a terminal:
the SDK native hard-link publication is not supported by the pinned WasmFS
OPFS backend. The existing Project I/O Web platform factory already mounts
the workspace on OPFS; retain that single mount and reuse it for SDK files.
SDK Web mutations
hold one origin-scoped Web Lock for the workspace across selection or complete
execution. Native publication remains unchanged. Under that lock, Web immutable
files use checked file moves; artifact directories publish files individually,
then the existing terminal publishes last. Interrupted reservations remain
unavailable for reuse, and an incomplete directory is never a successful
terminal. This adds no public SDK API or persisted format. Browser restart and
competing-writer tests validate the actual backend, not a memory substitute.

The SDK allocation is MINOR for the additional Web durable-execution capability;
its public C++ ABI and terminal format are unchanged. Consumers pin that exact
identity. This replaces the earlier PATCH estimate for resolver normalization alone.

### K5a verification and clean-source sequencing

K5a verification includes the native Project I/O/SDK/Facade/Host regressions,
all 518 Creator unit tests, current Portal validation, version/lock/module-graph
checks and the packaged Web Runtime's 11 Provider owner journeys. The shared
journeys also assert real output bytes after restart, failed terminal identity,
Project file identity, and workspace-lock refusal followed by same-ID retry.

Creator's packager and full proof require a clean Git source tree. Therefore
commit K5a after those source checks, then package and run the Creator journeys
and both complete Web proofs before freezing K5b. Any source correction stays
in K5a before the immutable snapshot. Run complete Core proof and Portal check
with the K5b snapshot before shipping either Task. Missing snapshot failures
before K5b are retained prerequisites, not waived gates.

The shipping-skill tests and changed pitfall entry pass. The whole existing
ledger suite also reports a baseline failure in
`snapshot-page-pin-only-fires-at-freeze.md` (`area: docs`); that entry is unchanged.
