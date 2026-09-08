---
id: coalesced-main-wakeup-lost
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/actions/runs/34277723029
    observed_by: Codex
exit: gate:tests/build/ci_incremental_entry_test.py
---

# A completion can be the surviving main wakeup even when its cancelled parent never claimed a batch.

## Why

The linked controller authenticated relay `34277673180/1` and cancelled main
push `34277607211/1`, then returned idle solely because there was no matching
active executor. Its complete controller artifact `10076567458` recorded
processed/pending at `2a2da287a3dbc25cd6bedb8850fd90307943ae69`, active null,
while main/control was `2ecd64a04ed4da12b04d9df22b6379ee2e77a1f9`.
This observes missed immediate recovery, not the cancellation actor or failure
of the independent health tick. Coalesced notifications are not durable work;
an active-parent settlement guard alone cannot also decide idle recovery.

## How to apply

Keep authentication and active ownership strict. For an idle authenticated batch
callback compare freshly read main with durable processed before returning idle;
use the existing locked reconciler for new work, never the parent's conclusion
as success. Preserve no-write idle behavior when main is unchanged, and never
settle another active owner. The entry regressions cover this deterministic
transition through real Git and journal replay, including a second main merge,
duplicate callback and unavailable main. Actual GitHub delivery/coalescing and
chain-limit recovery still need platform evidence; this gate proves neither.
