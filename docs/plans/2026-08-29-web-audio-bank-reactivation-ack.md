# Web Audio Bank Reactivation Acknowledgement Implementation Plan

**Issue:** #410
**Authority:** existing Web Runtime Host request budget, AudioWorklet lifecycle,
and immutable Prepared Sample Bank publication contracts

## Outcome

A successful live Bank reload and every later AudioWorklet activation acknowledge
the exact latest accepted Bank generation. A stale nonzero acknowledgement may
not satisfy activation, and an acknowledgement that cannot become exact within
the original Host request budget fails closed without extending the timeout.

## Implementation

1. Add deterministic Control tests for a live Bank publication whose response
   races the audio callback, and for reactivation while the prior generation is
   still reported.
2. Put an exact-generation acknowledgement barrier after explicit live
   `snapshot.reload`/retry publication and the running-Bank automatic
   publications from `sample.import.commit`, `sample.update_pad`, and
   `sample.reset_pad`. Preserve the existing request deadline and seal the
   Runtime on timeout or generation mismatch. A sample mutation that already
   committed remains a successful Project mutation response, with
   `runtime_published=false` and a typed `snapshot_error` describing the
   fail-closed Runtime outcome. If its deadline expires after Project commit
   but before Runtime publication completes, including during immutable
   Snapshot and Bank preparation, the running Runtime seals while the committed
   Project revision remains authoritative.
3. At AudioWorklet activation, validate that the Bank has no pending
   publication and latch its current generation before opening the realtime
   gate. The first callback acknowledges that latched generation; later
   callbacks continue reporting the live engine generation.
4. Count every valid callback, including paused callbacks, with a lock-free
   production heartbeat. Initial AudioWorklet bootstrap completes before the
   activation deadline is established immediately beside the callback baseline
   and `AudioContext.resume()` edge. Browser Main then waits for that heartbeat
   to advance before asking Control to open the realtime gate, and passes only
   the remainder of that one-second activation budget. Recovery keeps one budget
   from its resume edge through Control acknowledgement.
5. Exercise the production Browser Main → Control Worker → Wasm AudioWorklet
   path with a live reload followed by suspend/reactivate, and require the same
   latest generation after both acknowledgements.
6. Update the current acceptance ledger and Portal routes that own the Audio
   Runtime and Web Runtime lifecycle contracts.
7. Keep the Bridge caller cutoff authoritative end to end: compute the absolute
   effective deadline as the earlier of the operation cutoff and caller cutoff,
   pass that absolute value into Control Runtime, and never reconstruct a fresh
   operation budget from the original submission time. A Project mutation that
   wins its publication claim before that cutoff retains authority to settle its
   commit or abort; this does not exempt unclaimed work or later Runtime-derived
   publication and acknowledgement from the absolute cutoff.

## Realtime Safety

The audio callback adds a lock-free atomic increment and exchange only. It
performs no allocation, destruction, lock acquisition, Host call, Project
mutation, or unbounded work. Browser/Main and Control-side waiting stays
outside the realtime callback and shares the original activation request
deadline.

## Verification

- Focused Web Control Runtime tests for explicit publication, all three
  running sample-mutation publication paths, fake-clock post-commit and
  pre-publication fail-closed timeout semantics, a 100 ms caller-bounded
  activation with stale acknowledgement, and realtime AudioWorklet lifecycle
  tests including slow initial bootstrap.
- Core full, stress, and proof gates.
- Full Web Runtime Host, Creator build/tests, and packaged browser proof.
- Architecture Portal, dependency, active-tree, version, and production-symbol
  boundary checks.

## Local Verification Evidence

At the final candidate tree based on `c82c284d`, the following local gates pass:

- deterministic Runtime Session heartbeat TDD, including `uint32` wrap, and
  Web Control tests for `sample.import.commit`, `sample.update_pad`, and
  `sample.reset_pad` exact acknowledgement plus committed/fail-closed timeout;
- Core full 79/79, stress 5/5, and proof 63/63;
- Web Host nonbrowser 160/160, real AudioWorklet 22/22, clean packaged Chromium
  20 passed with one designed skip, and WebKit 2 passed with 14 declared
  capability skips;
- Creator build, Vitest 354/354, Python 13/13, and shared Web platform Node
  133/133. Creator's clean-tree reproducibility/browser proof remains the first
  post-amend gate because its stable entrypoint rejects an uncommitted tree;
- Portal 59/59 tests, 37 current pages, 10 diagram sources and 20 outputs, and
  42 rendered routes, plus dependency, active-tree, version, production source
  boundary, Web toolchain symbol identity, and diff checks.

This evidence is local and uncommitted at the time of recording. It does not
imply independent review, push, Pull Request, CI, merge, release, deployment,
Channel promotion, or physical-device acceptance.

## Version Management

Version impact: none. This repair restores the already documented Bank
publication and Web Audio lifecycle contract without changing a public
Contract, manifest, Module/Host version, Product Assembly, or Product Build.

## Documentation Impact

Documentation impact: required. Update Portal routes
`/core/modules/audio-runtime/` and `/platform/web-runtime/`, plus
`docs/quality/2026-08-03-formal-web-runtime-host-acceptance.md`. No immutable
Portal snapshot is created because no Product Build is allocated.
