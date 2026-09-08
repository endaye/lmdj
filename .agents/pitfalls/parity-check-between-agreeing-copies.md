---
id: parity-check-between-agreeing-copies
area: core
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/799
    observed_by: Claude Code (Opus 5)
exit: none
---

# Two copies of one vocabulary that both omit an entry agree perfectly, so a parity check between them is blind to the omission that matters

## Why

A Facade operation reaches the Web Host through three hand-maintained
inventories: `control_runtime.cpp` serves it, `bridge.cpp`'s
`supported_operation` admits it, and `HOST_OPERATIONS` in `protocol.mjs` sends
it. `soundset.audition` merged in #796 with the first and neither of the other
two. `supported_operation` fails closed, so every audition request was rejected
with `bridge_protocol_error()` before reaching the handler written to serve it,
and the payload validator and deadline entry in `control_runtime.cpp` were dead
code from the Web Host's side.

Nothing was red. The operation was in the Facade table, in Facade dispatch, in
`apps/core-mcp`, and in the Native Host's `kSoundSetOperations`. Its own suite,
`control_runtime_test.cpp`, calls `dispatch()` directly and so never crosses
the bridge that was rejecting it — the test for the feature and the thing
blocking the feature never meet.

The trap is in the repair, and it is why this is an entry rather than just a
fixed bug. The obvious gate is "assert `bridge.cpp` and `protocol.mjs` agree".
That check was written, it passed, and it was **worthless**: both files omitted
`soundset.audition`, so they agreed exactly. Reverting both to the pre-fix state
and re-running produced a clean pass. A parity check between two consumers can
only find a disagreement, and the defect class here is a *shared* omission,
which is agreement.

The fix is directional. Bind the consumers to the **producer** — the inventory
that is written when the feature is built, and therefore the one that gets
ahead. Asserting `control_runtime`'s served operations are a subset of what
`bridge.cpp` admits and `protocol.mjs` sends catches the real defect; the
consumer-to-consumer comparison is a weaker extra, worth keeping but never the
main assertion.

The same asymmetry appears wherever N copies of one vocabulary exist and one of
them is the reason the others must change:
[`manifest-role-validator-sync`](manifest-role-validator-sync.md) is the same
shape resolved the stronger way, by deleting the copies so there is one
definition to compare against.

## How to apply

- Before writing a parity check, name which copy leads. If a new entry appears
  in copy A because a feature was built, A is the producer; assert A ⊆ B and
  A ⊆ C. A check between B and C alone cannot see an entry missing from both.
- Prove a new parity check against the **exact pre-fix tree**, not against a
  hand-made perturbation of your fixed tree. `git checkout origin/main -- <the
  files you fixed>` and re-run: the check must fail and name the operation. A
  check that passes there is measuring nothing, however plausible its
  assertions read. This is the specific step that exposed the worthless
  version above.
- Prefer removing the duplication to gating it. A single definition both sides
  import cannot drift; a gate over three copies is the fallback for when the
  copies are in three languages, as they are here (C++ allowlist, JS frozen
  array, C++ served table).
- Do not read a green suite for the served operation as evidence it is
  reachable. Ask which layer that suite enters at. `control_runtime_test.cpp`
  enters below the bridge, so no amount of coverage there can observe a bridge
  rejection.
- State the blind spot in the check itself. The gate landed for #799 parses
  `control_runtime`'s `soundset_operations` map only; operations served by its
  `if (operation == ...)` branches are outside it, because those branches are
  not an enumerable inventory. Turning them into one is the mechanism that
  would let this exit, and it is not this Task's to land.

`exit: none` at recurrence 1: the gate added for #799
(`check_served_operations_are_reachable` in
`packages/web-runtime-platform/test/source_boundary_test.py`, run by CTest as
`platform.web_runtime_source_boundary`, tier `contract`) covers the Sound Set
table only. It is a partial mechanism, not this class's exit, because the
general invariant — every served operation is reachable — is not yet
mechanically decidable while most operations are served from `if` branches.
