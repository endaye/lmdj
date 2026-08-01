# LMDJ Product Assembly

`assembly.json` and its generated `assembly.lock.json` are the Product Assembly
source of truth for Product Build `1.0.8.0`. The lock binds every declared
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
- Implemented by this plan: Headless Core Proof only.
- Not implemented: realtime audio, Web/PWA, Creator UI, Sample intelligence,
  Sequence editing, Perform, Sound Sets, production Providers, cloud
  deployment.

Run the complete Proof from the repository root:

```bash
scripts/core.sh proof
```
