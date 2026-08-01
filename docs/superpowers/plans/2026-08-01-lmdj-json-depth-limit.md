# LMDJ JSON Depth Limit Implementation Plan

**Goal:** Reject excessively nested external JSON without crashing a Core Host
or crossing the C ABI with a partially parsed value.

**Architecture:** Apply the same maximum container depth at each JSON boundary:
CLI requests, C ABI configuration and requests, and Product Assembly loading.
The limit is enforced during SAX parsing so rejected subtrees are never built.
Application operations and versioned JSON Contracts remain unchanged.

## Tasks

- [x] Add boundary tests proving 63 nested containers reach Application
  validation while 64 nested containers are rejected by the Host boundary.
- [x] Add crash regressions using 200,000 nested containers for CLI requests,
  C ABI requests, and Assembly files.
- [x] Enforce the limit during parsing at all three external boundaries.
- [x] Run the integrated Core Proof and version verification gates.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

- Product: `1.0.6.0` to `1.0.7.0`; this PR changes the runnable Product
  Assembly's invalid-input behavior and becomes the next gated dev build after
  merge to `main` and full CI.
- Modules: `application-facade` `0.1.0` to `0.1.1` and `core-cli` `0.1.0` to
  `0.1.1` for a backward-compatible robustness fix. `core-mcp` moves from
  `0.1.0` to `0.1.1` because its exact `application-facade` dependency changes.
- Contracts, Providers, and Models: no version change. The existing request,
  response, C ABI, Assembly, Capability, and Project Contract shapes and
  meanings do not change.
- Compatibility: valid inputs with at most 63 nested containers remain
  accepted. Inputs starting a container at parser depth 64 now return the
  existing `INVALID_ARGUMENT` boundary result. No Project migration is needed.
- Files: update the three module manifests, Product `version.json`,
  `assembly.json`, compiled Assembly catalog, Product README, and regenerate
  `assembly.lock.json`. No Schema or Provider Manifest changes are allowed.
- Tag condition: only after squash merge to `main`, full CI, Core Proof, and
  version conformance pass may the Integration Owner create annotated tag
  `lmdj-v1.0.7.0` on the full merge SHA with message
  `LMDJ Product Build 1.0.7.0`.
- This plan authorizes neither merge, tag creation or push, release, deployment,
  publication, nor Channel promotion. The branch and PR remain candidates.
- Rollback reuses immutable tag `lmdj-v1.0.6.0`; no tag is moved or reused.
