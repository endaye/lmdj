# LMDJ Product Assembly

`assembly.json` and its generated `assembly.lock.json` are the Product Assembly
source of truth for Product Build `1.0.13.0`. The lock binds every declared
Module, Host, Provider, and Contract to its exact version and
source-package/schema hash. `assembly.json` declares the effective Region,
data-classification, and permission policy; the lock binds both that declaration
and the versioned Product Assembly wiring source. Hosts receive the Assembly
path explicitly; Provider selection remains Workspace/Host state and is never
written into Project Truth.

The Headless Core Proof intentionally treats every revision change during a
recording as `REVISION_CONFLICT` and seals the Take for recovery. This is a
Proof-only safety rule. It does not decide which product Commands are
irrelevant to a Take or whether the user-facing product may selectively
rebase.

## Status

- Designed: full new product/core architecture.
- Implemented: Headless Core Proof, the 5A realtime engine, and the 5B Formal
  Native Host with Project/Snapshot integration and Take capture.
- Not implemented: product GUI and MIDI/keyboard/pointer input adapters,
  Creator UI, Web product, Sample intelligence, Sequence editing, production
  Providers, or cloud deployment. Physical audible acceptance remains a
  separate device gate.

Run the complete Proof from the repository root:

```bash
scripts/core.sh proof
```
