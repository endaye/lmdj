# Cardputer observed DMA reservation deadline

Relates to #1104, #1107 and #1111. Development continues before joint device
testing; this Task neither flashes a device nor establishes physical acceptance.

## Declared files

- `apps/cardputer-host/main/audio_driver.cpp`
- `tests/platform/cardputer/dma_deadline_test.cpp`
- `tests/platform/cardputer/fake_esp/driver/i2s_std.h`
- `tests/platform/cardputer/fake_esp/freertos/queue.h`
- `tests/platform/cardputer/CMakeLists.txt`
- This plan.

## Defect and correction

Reservation at EOF k only makes a descriptor writable until EOF k + N - 1,
when the N-descriptor ring starts transmitting that descriptor again. Previous
generation and byte-equality checks could accept a render/copy delayed into
that transmission, before the descriptor's own next EOF detected anything.
Reject observed expiry before the copy, recheck after it, and latch the existing
fault to fence later writes. Preserve the actual accepted sample count when
the platform has already copied data. No attempt is made to undo transmitted
samples. Existing AudioDriver failure handling owns stop/mute/quiescence.

ESP-IDF v6.1 `i2s_common.c` invokes on_sent for the completed descriptor,
auto-clears it after that callback and queues it for channel_write. The fixture
models that callback, clear, control FIFO and copy ordering at the real
EspAudioIo entrypoints; it does not model physical DMA pacing, analogue sound,
interrupt masking/delivery latency, cache coherence or scheduler timing.
This guard detects delivered EOF expiry; absence of its fault does not prove
zero physical underruns. Timing instrumentation and physical measurements
remain necessary and are not replaced by this Task.

## Verification

The original driver passes the on-time case but fails both before-copy and
during-copy expiry cases with `late submission reported successful` (CTest
exit 8, `/tmp/cardputer-dma-red.log`). Each corrected case asserts the actual
write count and accepted sample count; both failure cases also assert later
reservations are fenced. Run native/ASan for these and existing audio-driver
consumers, EIM compile/link, staged ownership and documentation checks.

Native and ASan/UBSan each pass 36/36 (35 component and the existing audio
stress case), with terminal exit 0; raw logs are `/tmp/cardputer-dma-tests.log`
and `/tmp/cardputer-dma-asan-tests.log`. EIM compile/link exits 0 at
`/tmp/cardputer-dma-eim.log`; staged ownership passes 72/72 at
`/tmp/cardputer-dma-scope.log`. No device commands were executed.
The first portal attempt exited 1 because this fresh worktree had no installed
Node dependencies (`/tmp/cardputer-dma-portal.log`), not because its source
checks had run and found a product defect. Preserve that failure separately
from the dependency-install and subsequent verification logs.

## Version Management

Version impact: none for this internal safety correction; no public API,
wire contract, Assembly or Build allocation changes. The complete candidate
will need its own final Host/Build identities before formal acceptance.

## Documentation Impact

Documentation impact: none — this internal observed-EOF guard does not change
the portal's public Host behavior or acceptance claims; limitations and source
verification are recorded in this development plan.
