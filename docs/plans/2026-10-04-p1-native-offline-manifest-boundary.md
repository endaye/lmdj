# P1 Native offline manifest boundary

## Problem and Task

Independent review R22 of the unpublished T4 composition `d3255af1` proves
that the real production packager emits the current generated seven-role
Creator favicon manifest, but Native `ManifestGate::initialize` rejects it
because the old P1 gate requires an offline Worker starting at the favicon
MAJOR. The complete Core200 run passed because its fixture added that
unpublished Worker to the current graph and also hard-coded the old offline
version. The review's fresh native build and unmodified real packager produce
a current-manifest RED; the synthetic next-MAJOR offline control passes.

Align the Native offline boundary with the already composed Python/JS
packager and validator: the current favicon inventory has no Worker, and
the next MAJOR's offline inventory requires exactly one. Repair the fixture
to read the actual generated `expected_assets`, rather than mirroring the
old gate. Preserve all identity, digest, schema, bounds, tap, compatibility,
late-initialization and terminal-before-mutation assertions.

## Declared files

- `packages/web-runtime-platform/src/manifest_gate.cpp`
- `packages/web-runtime-platform/test/manifest_gate_test.cpp`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- this plan

No additional API, role, storage schema, Product/Module identity, Runtime
architecture or acceptance policy is introduced. This Product-logic defect
is fully expressed by its regression and does not require a new pitfall gate.

## Verification

Before changing the production gate, rebuild the actual Native test target
with the generated-inventory regression and retain its RED at the new
acceptance assertion. Accept only a fresh successful rebuild after repair.
Read ready and `begin_runtime` after acceptance; missing or duplicate future
Workers and an extra current Worker must refuse both readiness and Runtime
creation. Remove assets by their asserted role so a future fixture cannot
turn a negative mutation into a no-op. The synthetic next-MAJOR identity is
a bounded test input, never an allocated Host or Product Build.

Run the complete native manifest target, stable Core build/fast, package and
published-role parity, version/graph and scope checks with existing budgets.
Run official full Portal against the complete staged tree and legitimate
single-parent ancestry before the separate Conventional Commit. The earlier
18 lower checks remain authentic evidence for their old exact Source and
inputs; they did not prove this missing real-packager/native transition.
Re-derive committed-head canonical keys, then execute all selected batch
obligations and obtain complete independent current-head review before merge.
Retain R22 and earlier environment negatives; do not change test selection,
timeouts, coverage floors, collectors or reviewer thresholds.

## Version Management

Version impact: none for this unpublished composition repair. It introduces
no public delta beyond the existing P1 inventory work and restores agreement
with Main's already allocated current favicon graph. The coordinated T8
IO/Facade/Platform MINOR and additional offline Host MAJOR debts remain with
the new Product Build and immutable snapshot; no identity is allocated here.

Documentation impact: required. `/hosts/creator-web/` and
`/core/modules/web-runtime-platform/` record the actual Native asset-inventory
acceptance and terminal refusal boundaries. Browser startup, formal offline
install/reopen/update, Safari/iPad/MIDI and mic/master hearing remain pending.
No publication, release, deployment or Channel promotion occurs.
