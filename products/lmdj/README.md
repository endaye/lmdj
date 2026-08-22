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
recording as `REVISION_CONFLICT` and seals the Take for recovery. This is a
Proof-only safety rule. It does not decide which product Commands are
irrelevant to a Take or whether the user-facing product may selectively
rebase.

## Status

- Designed: full new product/core architecture.
- Implemented: Headless Core Proof, the Formal Native Host, Creator Web Host
  `1.3.4`, Formal Web Runtime Host `1.2.13`, and their shared Web Runtime
  Platform `0.3.4`, including the Stage 8 Sample Editor and Project Truth v2.
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
