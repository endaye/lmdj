# Recover the Cardputer transfer display Task

Base: `0050db4a4`. Recover only commit `c2da7c45de0e9fb065b08b58f7b76ba66daecdb4`
from the early transfer display branch. The user authorized shipping and cleanup
on 2026-10-05 after the branch-by-branch audit. Relates to #1104.

## Declared files

- `apps/cardputer-host/main/transfer_session.hpp`
- `apps/cardputer-host/main/usb_transfer_endpoint.hpp`
- `apps/cardputer-host/main/usb_transfer_endpoint.cpp`
- `tests/platform/cardputer/usb_display_test.cpp`
- `tests/platform/cardputer/fake_esp/driver/usb_serial_jtag.h`
- `tests/platform/cardputer/fake_esp/esp_random.h`
- `tests/platform/cardputer/CMakeLists.txt`
- `CMakeLists.txt` (register the recovered binary in the coverage object roster)
- `apps/docs-site/docs/platform/input.mdx`
- `docs/plans/2026-09-12-cardputer-transfer-display.md` (retained original plan)
- This plan.

## Implementation and scope

Preserve the LCD and Pad feedback already on main. Recover receiver-owned byte
progress, timeout/failure and successful-retry display state, and local disarm
cancellation before the endpoint accepts its next frame. Keep the current
resource/diagnostic targets and the existing shared fake_timer implementation;
the recovered test uses that clock instead of introducing a second clock.
Register its native binary in the root coverage object roster, in Cardputer
registration order. The current coverage configure guard caught this missing
entry during recovery; keep that guard and the complete coverage union intact.

The separate local screen integration branch has copies of this work; this Task
is the single source delivery for the transfer projection. That branch and its
entrypoint/Assembly changes are not shipped or removed here. app_main still does
not instantiate the LCD. No wire operation, STATUS layout, device flash,
resource budget reduction or physical acceptance is introduced.

## Task verification

Build the USB display, transfer/session/transaction/hash and screen component
targets under dev and ASan. Run their complete CTest scenario sets, checking
HELLO/BEGIN/DATA/duplicate progress, timeout/clear/retry, local cancel/old-session
refusal, rejected COMMIT/valid retry/ready with complete digest and byte length,
and ABORT/new HELLO reset. Also run neighboring fake-clock resource and DMA
tests to verify the conflict resolution retains current main's clock ownership.

Run the EIM-managed pinned v6.1 `scripts/cardputer-host.sh build` (compile/link
only), staged path ownership, portal check and diff check. Before merge run
every selected batch-only lane on the committed head, require authentic
current-head independent review, and respect live conversation/conflict rules.
The root CMake roster change selects the conservative full lane set; execute
all selected batch-only lanes on the final committed head rather than reuse
the earlier focused-head results. Verify coverage configuration changes from
the named missing-target error to success, and run the complete coverage check.

Fake serial/clock and the small fixture do not prove physical USB, LCD, audio
timing, capacity or A1 acceptance. No new gate is added.

## Version Management

Version impact: none — internal projection and local receive cancellation; no
manifest, wire/Contract, Assembly or Product Build identity change. Completed
Host/Build allocation and immutable snapshot remain separate integration work.

## Documentation Impact

Documentation impact: required
Affected portal pages: /platform/input/
Reason: describe receiver-owned progress and cancellation, retaining the
unconnected LCD and physical acceptance boundaries.

Pitfall impact: none — source behavior is expressed by the component journey
regressions. Existing process pitfalls were read; no new recurrence was observed.
