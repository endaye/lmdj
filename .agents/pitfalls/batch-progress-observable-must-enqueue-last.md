---
id: batch-progress-observable-must-enqueue-last
area: core
status: open
recurrences:
  - date: 2026-10-12
    occurrence: https://github.com/endaye/lmdj/issues/1822
    observed_by: Kimi Code (k3)
exit: none
---

# When a multi-item batch drains through a render cycle, the externally observable progress item must be enqueued last

## Why

The Facade's replay `reset_neutral` enqueues a batch of live controls
(pad-gate masks, typed Filter release, legacy gesture burst) and waits for a
three-channel drain ACK before completing dispatch. A Host test observes the
batch through exactly one progress signal — the enqueued-gesture counter —
and renders the next audio boundary the moment that counter moves. When the
gesture burst was enqueued *before* the gates/filter cleanup, the counter
moved while the rest of the batch was still unqueued; those items landed
after the boundary render, the drain ACK never arrived within the test's
render protocol, and dispatch deadlocked into a host timeout. The pre-change
ordering passed only because the batch coincidentally ended at the same item
the observer watches. The invariant — "the item whose progress signal the
consumer watches must move only after the whole batch is queued" — lives in
the interplay between producer enqueue order and the consumer's observation
point; no single file states it.

## How to apply

When extending a drained batch with new item kinds, identify what external
progress signal observers key on, and enqueue that item last (or move the
observation point). Any reordering must keep the drain-ACK wait guarantee
intact — never "fix" the deadlock by dropping a channel from the ACK set or
widening the timeout. When a regression of this shape escapes a Task, check
whether the Task's owning suites actually include the rendezvous test; a
fast-tier-only local run will not see host-tier rendezvous failures, and
that is a verification-scope fact to record, not automatically a lane defect.
