# LMDJ

LMDJ is being rebuilt as a modular, cross-platform playable beat instrument:
turn any sound into Pads, perform the Beat yourself, and use optional
Capability Providers for slicing, separation, analysis, and later pattern
assistance.

New Headless Core is the only active product source. The retired
`lmdj.patch.v1` / `lmdj.materials.v1` Web/API/Worker product has been removed
from the active tree and remains recoverable from Git history.

## Current status

- Designed: full product and Core architecture.
- Implemented: M1 Headless Core Proof, the Formal Native Host, Creator Web
  Host `1.0.1`, and Formal Web Runtime Host `1.2.1` in Product Build
  `1.0.16.1`. Both Web Hosts use Web Runtime Platform `0.1.1`, OPFS Project
  I/O, and C++ Audio Runtime through the same Wasm AudioWorklet.
- Not implemented: complete Creator editing, installable/offline PWA behavior, Sample
  intelligence, Sequence editing, production Providers, or cloud deployment.
  The five required Web physical-device rows remain `deferred / unverified`.

## Architecture

```text
Product Assembly
  -> thin Hosts (CLI / MCP / Native / Creator Web / Diagnostic Web)
  -> shared Web Runtime Platform for browser Hosts
  -> Application Facade and narrow C ABI
  -> Authoring Domain + Project I/O
  -> immutable Runtime Snapshot
  -> Audio Runtime

Capability Provider
  -> Attempt-scoped Artifact input/output
  -> Candidate or typed failure
  -> never mutates Project Truth
```

Active source boundaries:

```text
apps/       thin Core Hosts
packages/   product-neutral Core Modules
providers/  Capability Provider implementations
products/   Product Assembly and Product Build identity
contracts/  versioned cross-language Contracts
workers/    future out-of-process Provider Hosts
```

Reference demos under `references/demos/` are frozen and are not product code.

## Build

Requirements: CMake 3.24+, a C++20 compiler, Python 3.11+, Git, and curl.

```bash
bash scripts/verify-core-dependencies.sh
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev
scripts/core.sh proof
scripts/web-runtime-host.sh proof
scripts/creator-web.sh proof
```

`scripts/core.sh proof` is the single vertical-slice acceptance command. It
builds Release, exercises CLI and MCP over the same Product Assembly, renders
the Golden Beat, verifies Provider failure isolation and Take recovery, and
generates a canary Build Manifest. `scripts/core.sh clean` removes only
`build/core`.

`scripts/web-runtime-host.sh proof` requires the pinned Emscripten `6.0.5`,
Node 22, and the locked Playwright browsers. It performs clean reproducible Web
builds, isolated packaging, Chromium full-journey automation, and WebKit
capability smoke; it does not substitute for the five deferred physical rows.

`scripts/creator-web.sh proof` adds deterministic Creator packaging plus the
packaged Chromium creation/import/Pad/runtime journey and WebKit capability
boundary on the same shared native Runtime.

## Source of truth

- [Core redesign](docs/superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)
- [Headless Core implementation plan](docs/superpowers/plans/2026-07-30-lmdj-headless-core-proof.md)
- [Git workflow](docs/governance/git-workflow.md)
- [Version management](docs/governance/version-management.md)
- [Product decision log](docs/prd/decision-log.md)
- [Open product questions](docs/prd/open-questions.md)
- [Reference boundary](references/README.md)
