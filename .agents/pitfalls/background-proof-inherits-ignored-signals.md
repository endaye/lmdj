---
id: background-proof-inherits-ignored-signals
area: ci-release
status: open
recurrences:
  - date: 2026-10-01
    occurrence: https://github.com/endaye/lmdj/pull/1741
    observed_by: Codex GPT-6
exit: none
---

# A detached verification launcher can inherit ignored SIGINT and invalidate signal-cleanup tests before they start.

## Why

The first remote P1 deploy-contract proof ran beneath a background/nohup shell.
Its deployment fixture leaders inherited ignored HUP, INT and QUIT (`SigIgn`
0000000000000007). A child Bash cannot install a working INT trap for a signal
ignored on entry. Both INT cases timed out at their existing ten/fifteen-second
bounds; surviving blocked fixture children then contaminated the TERM subcases.
The same two complete tests passed in 13.919 seconds after a task-owned Python
launcher supplied default INT/TERM dispositions and a new session. Product code
and timeouts were unchanged. This concerns the external proof launcher, not the
reviewed deployment's signal semantics.

## How to apply

Launch detached proofs with explicit default INT/TERM dispositions and a new
session. Before attributing a signal failure to product code, inspect the exact
owned process's signal dispositions and session identity. Preserve the original
failure and rerun the complete affected tests with their original bounds. Reap
only identified owned failed-fixture processes; never send a group signal to a
shared SSH daemon/session group. A new session must be verified, not inferred
from the launcher name. Carry the same environment into the complete lane.

No mechanism exits this entry yet: detached launchers live outside the repository
and differ between operator hosts. A product-source test cannot infer their
external inherited state or authorize changes to a shared machine.
