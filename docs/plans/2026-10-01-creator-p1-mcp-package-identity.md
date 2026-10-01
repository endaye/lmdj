# P1 version settlement: align the MCP package identity

The Linux ASan run reached the existing MCP startup fixture and failed because
P1's dependency-pin settlement changed the Host manifest but left both Python
package metadata and the imported Host version behind. Derive both values from
the retained MCP Host manifest. Preserve the already allocated, unpublished Host
version and all other component identities; no tools, schema or Facade behavior
changes. The existing MCP stdio fixture is red at the metadata assertion before
the repair and its eleven complete protocol fixtures pass after the repair.

## Declared files

`apps/core-mcp/pyproject.toml`, `apps/core-mcp/lmdj_core_mcp/__init__.py`,
`products/lmdj/{version.json,assembly.json,assembly.lock.json,src/compiled_assembly.cpp}`,
`products/lmdj/generated/web-runtime-identity.{json,mjs}`,
`apps/docs-site/docs/hosts/core-mcp.mdx`, this plan and the integration plan.
A separate immutable new-candidate snapshot follows the clean source commit.

## Verification

Existing MCP stdio eleven fixtures with the real C ABI: retain pre-repair red
and post-repair green. Product version suite and generated identity freshness,
change-scope classifier and portal source checks. Freeze the new snapshot from
the clean source, then complete the portal gate. The intermediate pre-freeze
check refuses missing snapshot metadata; it is not reported as a complete pass.
Rerun complete candidate Host and Linux lanes. Linux Core/ASan use the default
GNU compiler as CI does; only coverage uses pinned Clang 22. Preserve the first
Clang ASan preload failure, do not alter sanitizer checks or system kernel state.

## Version Management

Version impact: align Python metadata with the existing new MCP Host identity
and allocate the next unused Product BUILD from the retained candidate manifest.
All prior immutable snapshots remain byte-identical. No release or deployment.

Documentation impact: required
Affected portal pages: /hosts/core-mcp/ and generated component/version routes.
Reason: MCP runtime/package identity and the allocated test candidate change.
