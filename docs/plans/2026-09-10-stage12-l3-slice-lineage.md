# Stage12 L3 — persisted Slice lineage (#1040)

Implement the approved R2-F evidence carrier only. Workspace publication/recovery
belongs to L1; materialization and AdoptCandidates revision semantics belong to
L2. This Task preserves generic Project I/O replay identity, including every
lineage field, without promising idempotent adoption commands.

## Declared files

- `apps/docs-site/diagrams/authoring-domain.architecture.json`
- `apps/docs-site/diagrams/project-io.architecture.json`
- `apps/docs-site/docs/contracts/project-bundle.mdx`
- `apps/docs-site/docs/contracts/project.mdx`
- `apps/docs-site/docs/core/modules/authoring-domain.mdx`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `apps/docs-site/static/diagrams/authoring-domain.html`
- `apps/docs-site/static/diagrams/authoring-domain.svg`
- `apps/docs-site/static/diagrams/project-io.html`
- `apps/docs-site/static/diagrams/project-io.svg`
- `contracts/project/lmdj.project-bundle.v1.schema.json`
- `contracts/project/lmdj.project.v5.schema.json`
- `docs/plans/2026-09-10-stage12-l3-slice-lineage.md`
- `packages/application-facade/src/application.cpp`
- `packages/authoring-domain/include/lmdj/domain/project.hpp`
- `packages/authoring-domain/src/command_handler.cpp`
- `packages/authoring-domain/src/project.cpp`
- `packages/project-io/include/lmdj/project_io/project_store.hpp`
- `packages/project-io/src/project_bundle_transfer.cpp`
- `packages/project-io/src/project_store.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/web-runtime-platform/web/project_bundle_reader.mjs`
- `tests/conformance/project_bundle_contract_test.py`
- `tests/conformance/schema_contract_test.py`
- `tests/core/domain/command_handler_test.cpp`
- `tests/core/domain/performance_test.cpp`
- `tests/core/domain/project_test.cpp`
- `tests/core/facade/application_test.cpp`
- `tests/core/project_io/performance_journal_test.cpp`
- `tests/core/project_io/project_bundle_transfer_test.cpp`
- `tests/core/project_io/project_store_test.cpp`
- `tests/core/project_io/soundset_install_commit_test.cpp`
- `tests/core/support/legacy_project.hpp`
- `tests/fixtures/contracts/project-bundle-valid.json`
- `tests/fixtures/contracts/project-v5-valid.json`
- `tests/host/cli_test.py`
- `tools/project-bundle/project_bundle.py`


### Integrated version and current-documentation closure

- `packages/authoring-domain/module.json`
- `packages/project-io/module.json`
- `packages/project-cooker/module.json`
- `packages/audio-runtime/module.json`
- `packages/application-facade/module.json`
- `packages/web-runtime-platform/module.json`
- `apps/core-cli/module.json`
- `apps/core-mcp/module.json`
- `apps/native-host/module.json`
- `apps/web-runtime-host/module.json`
- `apps/creator-web/module.json`
- `apps/core-mcp/pyproject.toml`
- `apps/core-mcp/lmdj_core_mcp/__init__.py`
- `apps/creator-web/package.json`
- `apps/creator-web/package-lock.json`
- `products/lmdj/version.json`
- `products/lmdj/assembly.json`
- `products/lmdj/assembly.lock.json`
- `products/lmdj/src/compiled_assembly.cpp`
- `products/lmdj/generated/web-runtime-identity.json`
- `products/lmdj/generated/web-runtime-identity.mjs`
- `tests/build/version_test.py`
- `tests/conformance/module_graph_test.py`
- `tests/host/native_host_source_boundary_test.py`
- `tests/conformance/version_lock_test.py`
- `apps/docs-site/test/repo-facts.test.mjs`
- `apps/docs-site/docs/core/overview.mdx`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/docs/core/modules/project-cooker.mdx`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/hosts/overview.mdx`
- `apps/docs-site/docs/hosts/core-cli.mdx`
- `apps/docs-site/docs/hosts/core-mcp.mdx`
- `apps/docs-site/docs/hosts/native-host.mdx`
- `apps/docs-site/docs/hosts/web-runtime.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/product/capability-map.mdx`
- `apps/docs-site/docs/product/workflows.mdx`
- `apps/docs-site/docs/assembly/lmdj.mdx`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `apps/docs-site/docs/operations/creator-changelog.mdx`
- `apps/docs-site/docs/operations/runtime-changelog.mdx`
- `apps/docs-site/diagrams/lmdj-core.architecture.json`
- `apps/docs-site/static/diagrams/lmdj-core.html`
- `apps/docs-site/static/diagrams/lmdj-core.svg`
- `apps/docs-site/diagrams/lmdj-product.architecture.json`
- `apps/docs-site/static/diagrams/lmdj-product.html`
- `apps/docs-site/static/diagrams/lmdj-product.svg`
- `apps/docs-site/diagrams/project-cooker.architecture.json`
- `apps/docs-site/static/diagrams/project-cooker.html`
- `apps/docs-site/static/diagrams/project-cooker.svg`

Official generated Build51 snapshot paths: `apps/architecture-portal/versions.json`,
`static/versions/1.0.51.0/`, `versioned_docs/version-1.0.51.0/`,
`versioned_metadata/version-1.0.51.0.json`, and
`versioned_sidebars/version-1.0.51.0-sidebars.json` beneath that portal root.

## Implementation and verification

Add typed capability/provider/model identities and a closed slice interval
recipe to the existing derivation variant. Require all evidence, explicit null
model identity, asset_artifact source, valid digests/IDs/versions and nonempty
bounded intervals. Reject extra keys at every nested object and capability
lineage in old v4 documents. Preserve old variants byte-for-byte on migration.
Introduce v5 read/write and deterministic v4 migration; preserve the current
Contract through commands and replay. Add schema vectors and lowest-tier domain
codec tests, Project I/O save/reopen/replay/collision tests and old variant
regressions. Run targeted tests, full dev Core tests, dependency checks and
`scripts/docs-site.sh check`; build concurrency at most four. No new gate.

## Version Management

Version impact: required. Project v5 starts at 5.0.0, preserving unchanged v1-v4
schemas and reads; Bundle 1.2.0 -> 1.3.0 admits v5. Authoring Domain 3.0.0 ->
4.0.0 and Project I/O 3.2.0 -> 4.0.0 cover the closed public variant and new
writer semantics. Facade 4.2.0 -> 5.0.0 exposes the changed ProjectState through
its typed return values. The public C ABI shape is unchanged. Project Cooker
1.1.0 -> 1.1.1 and Audio Runtime 4.0.0 -> 4.0.1 rebuild exact dependencies;
Web Runtime Platform 5.1.1 -> 5.2.0 adds compatible Bundle admission. CLI/MCP/
Native 3.3.1 -> 3.3.2 and Web/Creator 4.2.1 -> 4.2.2 follow dependency pins.
Provider SDK, Providers and their identities are unchanged by L3.
Product 1.0.50.0 -> 1.0.51.0 gets an official immutable canary snapshot; recheck
live allocation before freeze. No tag, release, deployment or Channel promotion.
Rollback retains prior immutable builds, never changes their snapshots.

## Documentation Impact

Documentation impact: required. Update the persisted evidence, reader/writer
boundary, dependent Host current facts, and source diagrams.
Affected portal pages: /contracts/project/ /contracts/project-bundle/
/core/overview/ /core/modules/authoring-domain/ /core/modules/project-io/
/core/modules/application-facade/ /core/modules/project-cooker/
/core/modules/web-runtime-platform/ /hosts/overview/ /hosts/core-cli/
/hosts/core-mcp/ /hosts/native-host/ /hosts/web-runtime/ /hosts/creator-web/
/product/capability-map/ /product/workflows/ /assembly/lmdj/
/operations/testing-and-proof/ /operations/creator-changelog/
/operations/runtime-changelog/
Identity components derive current identities from manifests; historical Build
records remain intact.

## Verification evidence

Integrated onto merged L1 baseline. The typed lineage codec preserves opaque SDK
Attempt IDs such as `slice-job.attempt_1`; empty/path/oversized/newline identifiers
are refused. Source revision and exact terminal identities are persisted; Job
and recipe IDs remain Workspace references, as required by R2-F.

- Integrated dev build at four jobs: passed.
- Integrated full dev Core: 143/143 passed after complete manifest and snapshot
  closure (`scripts/core.sh test dev full`; /tmp/l3-snapshot-full.log).
- Domain, Project I/O, Facade and Host tests cover save/reopen, replay collision,
  old lineage variants, Bundle browser admission and native boundaries.
- Schema conformance, version inventory/lock, vendored dependency verification
  and active-tree check passed. Exact dependency fixtures preserve their strict
  version assertions against the new allocation.
- Official `scripts/docs-site.sh version 1.0.51.0 canary` passed both current
  and complete snapshot-aware portal checks (44 routes and links). Frozen source
  is 6e93c986284cab3dc1658893e9add935555741dd, including the merged L1 witnesses.
- New-file ownership: 70 tests passed after source staging and after staging all
  67 generated snapshot paths. No historic snapshot was edited.
- Independent source review at 8574f7f40c8095ab3c928a68d99d819013dcc41a found
  no blocking findings; final commit/provenance review precedes shipment.
- L2 adoption and L5 browser acceptance are explicitly outside L3 evidence.

## Integration boundary

L1 is merged. L2 must construct lineage from validated terminal evidence,
preserve analysis source revision, and apply under current Project/Workspace
eligibility; L3 adds no adoption command replay guarantee. L2/L4/L5 remain
separate Tasks. No qualifying process pitfall was introduced by L3; the opaque
Attempt ID mismatch is expressed in domain/schema regression tests.
