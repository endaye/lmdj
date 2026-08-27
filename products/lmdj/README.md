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

The implemented [2026-08-23 Sequence recording decision](../../docs/prd/decisions/2026-08-23-sequence-recording-semantics.md)
uses a closed selective-rebase allowlist, fails Sample-class and unknown
Commands closed without silently rewriting the session, and records
event-only Pattern data with no Take product object.

## Status

- Designed: full new product/core architecture.
- Implemented: Headless Core Proof, the Formal Native Host, Creator Web Host
  `2.0.0`, Formal Web Runtime Host `2.0.0`, and Web Runtime Platform
  `1.0.0`, including Project Truth v3 and Stage 9 Sequence recording.
  Browser Hosts depend only on that Platform; Product Assembly owns exact Host
  identities and Provider catalog wiring.
- Not implemented: installable/offline PWA behavior, Sample intelligence,
  general Pattern event editing/Undo, production Providers, or cloud deployment.
  Web automation and physical Touch/MIDI/audio acceptance remain distinct; all
  five required Web physical rows are `deferred / unverified`.

Run the complete Proof from the repository root:

```bash
scripts/core.sh proof
scripts/web-runtime-host.sh proof
scripts/creator-web.sh proof
```
