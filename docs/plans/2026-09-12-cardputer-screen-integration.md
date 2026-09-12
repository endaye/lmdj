# Cardputer screen integration

Relates to #1104. Development in progress; no physical acceptance claimed.

## Scope

Integrate the pending Pad receipt feedback, ST7789 adapter and USB receiver
projection with current main. Preserve both new main diagnostic tests and
pending display tests. Connect the screen to the single control owner in
`apps/cardputer-host/main/main.cpp`, with immutable configuration supplied by
`products/lmdj/src/cardputer_assembly.cpp` through `cardputer_assembly.hpp`.
Display failure exits through normal Host/audio destruction rather than leaving
playback running with stale visual feedback.

Declared dependency files are the exact files of commits 55d5bb69, e1dbd548,
0e7fca1a and c2da7c45. Integration additionally owns the three files above,
this plan, and timer reconciliation in the existing USB display test/fakes.
Identity derivation also owns `apps/cardputer-host/identity.cmake`, both Host
CMake files, `tests/build/cardputer_identity_test.py`, root `CMakeLists.txt`
test registration and its exact ownership rule in `scripts/ci/scope_policy.json`.
The identity tests catch stale Product/Host pins, mismatched Assembly bytes,
and a missing Host lock entry. CMake derives all three runtime identity fields
and ESP application version from the same manifest inputs.
Do not ship this aggregate over the outstanding prerequisite PRs; retain the
local integration until they are reviewed and their retained changes can be
separated from the final integration Task.

## Verification

Run native LCD, screen, USB display, Pad feedback and existing diagnostic
tests after conflict reconciliation. Then compile the complete app using the
existing EIM-managed ESP-IDF environment. Native fakes cannot establish panel
orientation, electrical timing, audio/display contention or real USB timing.
`tests/platform/cardputer/main_failure_test.cpp` directly calls the real
`app_main` for LCD initialization and first-draw failure. Its CMake registration
and `fake_esp/freertos/task.h` delay hook are also declared files. The test uses
the actual Host/scanner/USB/LCD code with a substituted physical audio worker;
it asserts boot silence callback output, audio destruction before borrowed
I2C bus deletion, and no retained LCD/DMA allocations after return. A delay
after the injected failure aborts immediately. This proves the control-owner
exit path, not a real running worker join or failure during audible playback.

Panel source reference: M5GFX revision
`d91077b9a607b59404e4e4a49f775c792bfae382`, `src/M5GFX.cpp`
Cardputer/ADV configuration and `src/lgfx/v1/panel/Panel_LCD.cpp` rotation
transform. `Panel_ST7789.hpp` inherits the LCD MADCTL rotation mapping;
rotation one uses axis swap and X mirror. The driver initialization and scan
direction still require hardware verification. Hardware orientation remains
joint physical acceptance.

## Version Management

Version impact: a new integrated Build is required for subsequent team testing.
This source Task does not allocate it. Firmware identities are derived from
manifests; feature integration must land before the separate Build allocation
Task under version policy section 2. That later Task owns the updated Assembly
identity and matching immutable snapshot. A build of this dirty source tree is
not evidence for a new integrated candidate.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/cardputer-host /platform/input

Update current documentation and run the portal check before commit. Joint
physical tests and flashing remain deferred until missing development is ready.
