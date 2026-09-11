# Cardputer shared I2C lifetime repair

Relates to #1104. Fix one defect: starting audio creates controller 0 on the
same pins already routed to the keyboard's controller 1. ESP-IDF rewrites the
GPIO output matrix, so keyboard reads fail after the first successful start.

## Declared files

- apps/cardputer-host/main/audio_driver.cpp
- apps/cardputer-host/main/audio_driver.hpp
- apps/cardputer-host/main/keyboard_scanner.cpp
- apps/cardputer-host/main/keyboard_scanner.hpp
- apps/cardputer-host/main/main.cpp
- tests/platform/cardputer/CMakeLists.txt
- tests/platform/cardputer/shared_i2c_test.cpp
- tests/platform/cardputer/fake_esp/driver/i2c_master.h
- tests/platform/cardputer/fake_esp/driver/i2s_std.h
- tests/platform/cardputer/fake_esp/esp_attr.h
- tests/platform/cardputer/fake_esp/freertos/FreeRTOS.h
- tests/platform/cardputer/fake_esp/freertos/queue.h
- tests/platform/cardputer/fake_esp/freertos/task.h
- apps/docs-site/docs/platform/native-audio.mdx
- docs/plans/2026-09-11-cardputer-shared-i2c.md

## Implementation and verification

The scanner owns one bus. It is installed before audio boot, and outlives the
audio session. Audio borrows this bus explicitly, removes only its own codec
device on stop or partial failure, and preserves failed cleanup for retry.
Standalone audio retains its existing dedicated-bus ownership behavior.
ESP-IDF serializes synchronous device transactions with the bus mutex.

Lowest-tier regression compiles the actual ESP audio source against fake SDK
functions that model GPIO routing theft. A keyboard register read must succeed
before, during and after three audio configure/enable/disable/release cycles,
after add-device failure, and after release failure/retry. Dedicated ownership
must still delete its bus. The old audio implementation fails the keyboard-read
assertion immediately after configure (exit 134); the corrected four scenarios
pass. These stubs do not model DMA service or analog sound.

Run CMake's four I2C scenarios, existing Cardputer tests, strict EIM v6.1 target
build, scope ownership checks, Portal check and whitespace inspection. No new
required gate or threshold changes. Follow with physical Enter/load/start,
mute/unmute, volume, stop and restart; record those separately from fake tests.
The umbrella's four-pad, full-duration and recovery acceptance remains required.

## Version Management

Version impact: none for this source repair. No distributed Package or Product
Build is allocated; Host-internal configuration only, no Facade or wire change.
A device image built for diagnosis is source validation, not acceptance of a
new immutable Product Build. Formal Build allocation remains a subsequent step.

## Documentation Impact

Documentation impact: required
Affected portal pages: /platform/native-audio/
Explain bus ownership and cleanup boundaries.

## Pitfall disposition

Product defect expressed by a regression test. No pitfall ledger entry needed.
