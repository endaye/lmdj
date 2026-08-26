# LMDJ Product Assembly

`version.json` is the source of truth for the current Product Build.
`assembly.json` is the reviewed, explicit Product Assembly declaration and its
Product Build must match that authority. `assembly.lock.json` and
`src/compiled_assembly.cpp` are generated together from those inputs; the lock
binds every declared Module, Host, Provider, and Contract to its exact version
and source-package/schema hash. `assembly.json` also declares the effective
Region, data-classification, and permission policy. Hosts receive the Assembly
path explicitly; Provider selection remains Workspace/Host state and is never
written into Project Truth.

The Headless Core Proof intentionally treats every revision change during a
recording as `REVISION_CONFLICT` and seals the recording for recovery. This
Proof-only safety rule is superseded as product authority by the approved
[2026-08-23 Sequence recording decision](../../docs/prd/decisions/2026-08-23-sequence-recording-semantics.md):
the product classifies concurrency (a closed selective-rebase allowlist,
Sample-class Commands failing while recording continues, unknown Commands
failing closed) and records event-only Pattern data with no Take object. The
Proof rule remains in effect in the implemented Core until Stage 9 ships.

## Status

- Designed: full new product/core architecture.
- Implemented: Headless Core Proof, the Formal Native Host, Creator Web Host
  `1.5.5`, Formal Web Runtime Host `1.2.15`, and their shared Web Runtime
  Platform `0.3.6`, including the Stage 8 Sample Editor and Project Truth v2.
  Browser Hosts depend only on that Platform; Product Assembly owns exact Host
  identities and Provider catalog wiring.
- Not implemented: installable/offline PWA behavior, Sample intelligence,
  Sequence editing, production Providers, or cloud deployment.
  Web automation and physical Touch/MIDI/audio acceptance remain distinct; all
  five required Web physical rows are `deferred / unverified`.

Run the complete Proof from the repository root:

```bash
scripts/core.sh proof
scripts/web-runtime-host.sh proof
scripts/creator-web.sh proof
```
