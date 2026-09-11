# Cardputer transfer state for the LCD

Relates to #1104, #1108, #1109 and #1111. Depends on the LCD adapter source
and its ScreenTransfer projection. Joint device testing remains deferred until
the complete candidate is ready, per the user's 2026-09-12 instruction.

## Declared files

- `apps/cardputer-host/main/transfer_session.hpp`
- `apps/cardputer-host/main/usb_transfer_endpoint.hpp`
- `apps/cardputer-host/main/usb_transfer_endpoint.cpp`
- `tests/platform/cardputer/usb_display_test.cpp`
- `tests/platform/cardputer/fake_esp/driver/usb_serial_jtag.h`
- `tests/platform/cardputer/fake_esp/esp_random.h`
- `tests/platform/cardputer/fake_esp/esp_timer.h`
- `tests/platform/cardputer/CMakeLists.txt`
- `apps/docs-site/docs/platform/input.mdx`
- This plan.

## Behavior

Expose a bounded value view of the real protocol session, active receive byte
count and failure state to the serialized display caller. Progress comes from
TransferReceiver, not a second counter or received packet lengths. A session
does not prove cable presence. Duplicate DATA must not inflate progress;
timeout/abort/HELLO discard clears progress; successful retry clears failure.

Local Esc currently disarms the Host but leaves the receive transaction active
until timeout. The endpoint must consume that local cancellation before any
further incoming frame, discard staging and invalidate the old session.
No new wire operation or STATUS layout is introduced.
Discard means clearing the active transaction and logical staged bytes.
TransferReceiver already retains its vector capacity after clear; this Task
does not change that allocation policy or claim that heap storage was freed.
The retained capacity remains part of the final resource measurements.

## Verification

Run the actual ESP endpoint over a fake serial FIFO and clock, with real
TransferSession/Receiver and real RuntimeHost/Facade. Assert far-side display
state after HELLO, BEGIN, DATA, duplicate DATA, timeout, local cancel and
retry/COMMIT; malformed bytes must never be published. Existing transfer and
screen tests remain selected. Native/ASan, EIM compile/link, ownership and
portal checks are required. Fake clock/serial do not establish USB enumeration,
physical disconnect behavior or display timing.

Development evidence: initial progress test passed, while timeout feedback and
local-cancel transaction clearing failed (CTest exit 8), retained at
`/tmp/cardputer-usb-display-red.log`. After correction, native and ASan/UBSan
each pass 18/18 across USB display, session, transaction, bounded hash and
screen projections. The retry test checks real RuntimeHost ready and the
complete published digest/byte length after a rejected transfer. Its tiny
single-Pad fixture is not the D1 music/capacity fixture. EIM firmware compile
and link exit 0; no device flash or physical test was performed.

## Version Management

Version impact: none for this internal projection and cancellation correction;
no wire/schema or manifest identity changes. Final Host/Build allocation and
immutable snapshot belong to the complete B1 integration before formal A1.

## Documentation Impact

Documentation impact: required — `/platform/input/` describes the projection
and cancellation behavior while retaining the pending device integration gap.
