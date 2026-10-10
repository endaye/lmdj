---
id: absence-assertion-races-async-command-chain
area: product
status: open
recurrences:
  - date: 2026-10-10
    occurrence: https://github.com/endaye/lmdj/issues/1962
    observed_by: opencode (GLM 5.3)
exit: none
---

# A synchronous absence assertion placed right after a synthetic event that starts an async command chain passes vacuously; the negative read must wait for the chain's turn.

## Why

`fireEvent.pointerUp` (and siblings) dispatch synchronously, but the handler
under test hands the command to an async `void` chain (`onEdit={(edit) =>
{ void editSequenceGridEvents(edit); }}`): inspect, then commit, then state
refresh. An `expect(...).not.toHaveBeenCalled()` executed immediately after
the event reads the world before the chain has run at all, so it can never
fail — on a tree with the exact defect the test claims to catch. In #1962's
app-level regression test the first version stayed green on a mutant with the
VEL-tap guard deleted, a false pass that only a mutation run exposed; the
same edit visibly reaches the fake Host within milliseconds once awaited.

The root cause is a tool boundary, not product code: jsdom/fireEvent makes
dispatch synchronous while the app's effect chains are microtask/macrotask
asynchronous, so "immediately after" is always "before".

## How to apply

When a test asserts that a synthetic event did *not* produce a command, first
let the chain have its turn: `await act(async () => { await new Promise(r =>
setTimeout(r, N)); })` with N comfortably above the chain's observed latency
(the contrast path in a neighbouring test shows that latency), then read
absence. Prove the wait is real with a mutation that makes the handler fire:
the absence assertion must fail inside the test under proof before trusting
the green run. A synchronous absence assertion is evidence of nothing. Remains
`open` with `exit: none`: whether an author waited for the chain is not
mechanically decidable from the test text alone.
