# Cardputer bounded transfer integrity

Relates to #1104 and #1109. One Task repairs receive-side hash memory use.

## Scope

- `apps/cardputer-host/main/transfer_transaction.cpp`: feed PicoSHA2 bounded
  ranges, avoid hex formatting, distinguish allocation failure from mismatch.
- `apps/cardputer-host/main/transfer_session.cpp`: preserve resource-limit result.
- `tests/platform/cardputer/transfer_hash_memory_test.cpp`: real receiver,
  independent digest, 96808-byte input, bounded allocation, corruption rejection,
  allocation failure with no sink effect and successful retry.
- `tests/platform/cardputer/CMakeLists.txt`: component test registration.
- This plan.

## Verification

The old receiver fails the bounded-memory test (exit 134). Run all four new
component scenarios with ASan/UBSan, existing transaction/session tests, staged
path ownership, and the pinned EIM ESP-IDF target build. No new required CI gate.
The allocator probe models allocation refusal, not actual device fragmentation,
DMA, physical sound, or timing. Physical follow-up retains the complete four-pad
96808-byte music content and checks the COMMIT digest/length and ready status.
Playback, reload, combined 30-minute acceptance and the immutable candidate
remain separate unfulfilled acceptance boundaries.

## Version Management

Version impact: none. Internal Host integrity implementation repair; no Product
Build allocation, public API, Contract or capacity limit change.

## Documentation impact

Documentation impact: none. No portal route or documented interface changes;
the existing integrity contract and memory limits remain unchanged.

## Pitfall disposition

Product-logic defect fully expressed by a regression test; no ledger entry.
