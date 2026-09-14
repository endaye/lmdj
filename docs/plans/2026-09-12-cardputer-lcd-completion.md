# Complete the Cardputer physical display

Parent: #1104; required behavior: approved Runtime Host design §6 and I1 #1108.
User direction on 2026-09-12: finish missing development before resuming joint
physical tests. Do not flash a partial candidate during this work.

## Requirements and remaining development

1. Integration prerequisite Pad feedback correction: processed current-epoch receipts,
   lifecycle clearing, no display prediction from queue admission. PR #1248.
2. Actual ST7789 LCD adapter and bounded text/raster view. Display all required
   phases, Pattern state, four acknowledged Pad inputs, volume/mute, USB
   session/receiving state, error recovery action, Build/Host/source identity
   and published content digest/length. Always explain Enter's destructive
   replacement effect when content is loaded.
3. Product Assembly supplies physical panel wiring and geometry; B1 integrates
   the adapter in the serialized Host loop, allocates the complete candidate,
   and creates its immutable portal snapshot. No copied research identity.
4. Audit/develop the measurement support for D1 §3: separate CPU work, DMA
   wait and delivery timing; measurable late/underrun or explicit inability to
   observe; real voice overlap, heap/largest block, stacks and lifecycle cycles.
   Diagnostic scaffolding must not masquerade as instrumented physical latency.

## LCD implementation Task file scope

- `apps/cardputer-host/main/lcd_display.hpp` and `lcd_display.cpp`
- `apps/cardputer-host/main/screen_view.hpp` and `screen_view.cpp`
- `apps/cardputer-host/main/CMakeLists.txt`
- `tests/platform/cardputer/screen_view_test.cpp`
- `tests/platform/cardputer/lcd_display_test.cpp`
- `tests/platform/cardputer/fake_esp/lcd_fake.hpp`
- `tests/platform/cardputer/fake_esp/driver/gpio.h` and `driver/spi_master.h`
- `tests/platform/cardputer/fake_esp/esp_heap_caps.h`
- `tests/platform/cardputer/fake_esp/esp_lcd_panel_io.h`
- `tests/platform/cardputer/fake_esp/esp_lcd_panel_ops.h`
- `tests/platform/cardputer/fake_esp/esp_lcd_panel_vendor.h`
- `tests/platform/cardputer/CMakeLists.txt`
- `apps/docs-site/docs/platform/input.mdx`
- This plan.

The renderer consumes the existing DisplayFrame value interface and can land
independently of PR #1248. It does not establish the producer's receipt semantics.
Assembly/entrypoint/USB view integration is a following Task with its own
declared paths. Build allocation and its immutable snapshot follow source
integration in a separate version Task. The unconnected
adapter by itself does not make the device screen usable.

## Hardware and SDK sources

M5 official Cardputer ADV hardware page:
https://docs.m5stack.com/en/core/Cardputer-Adv

M5GFX source pinned to `d91077b9a607b59404e4e4a49f775c792bfae382`,
`src/M5GFX.cpp` Cardputer ADV panel configuration. The vendor uses ST7789,
135×240 native panel, offsets 52/40, rotation 1, inversion, SPI3 at 40 MHz;
MOSI 35, SCLK 36, DC 34, CS 37, reset 33, backlight 38. Read the corresponding
rotation implementation before fixing landscape addressing. These pins belong
only in Product Assembly, not neutral adapter defaults.

Use the existing EIM ESP-IDF v6.1 installation. Its LCD IO API explicitly
retains color-buffer ownership until on_color_trans_done and waits for queued
color transactions before command writes. The adapter must honor that lifetime.

## Scheduling and resource design

Use a bounded DMA stripe buffer, not a full 240×135 RGB framebuffer. One owner
submits a stripe only after the prior completion; the callback only publishes
completion with a lock-free atomic. No UI Core calls, rendering, logging or
allocation run in the audio callback or LCD ISR. Snapshot the complete view
at the beginning of a frame to avoid mixed-state rows. Control polling remains
available between stripes; measure its effect on the final combined workload.
Teardown must drain ownership before freeing any DMA buffer/context, including
partially initialized and failed submissions.

## Verification

- Native view tests: bounded text, empty/receiving/ready/running/stopped/error,
  actionable instructions, exact supplied identity, all four input indicators.
- Real adapter with fake ESP IO: initialization order, addressing, buffer
  retained until completion, no second submission while busy, and partial
  failure cleanup. These do not prove pixels or panel electrical behavior.
- Native/ASan suites, pinned EIM compile/link, ownership and portal checks.
- Physical orientation, readability, refresh, USB transitions, Pad feedback
  and audio contention are tested together on the complete B1 candidate.

Development results: native and ASan/UBSan screen/real-adapter tests each pass
10/10, including
buffer lifetime while busy, full-frame addressing, unchanged-frame suppression,
frame snapshot consistency, 13 initialization failures, submission failure and
shutdown backlight clearing. The shutdown test first failed (exit 8), retained
at `/tmp/cardputer-lcd-shutdown-red.log`, before adding backlight cleanup.
The fake tracks DMA ownership and memory reclamation; it does not model SPI
electrical timing, physical orientation, light levels or audio contention.
The final EIM compile/link after shutdown cleanup exits 0, recorded in
`/tmp/cardputer-lcd-final-eim-build.log`; no firmware was flashed.

Initial EIM compilation failed on vendor anonymous C structs under pedantic
C++ warnings and three GPIO enum conversions; retained at
`/tmp/cardputer-lcd-eim-build.log`. Narrow vendor-include diagnostics and typed
GPIO casts corrected these; the retry compiled successfully. The adapter is
not yet instantiated by app_main, so compile/link is not device output proof.

Standalone revalidation on current main, excluding the pending Pad feedback
commits: native LCD/view plus neighboring DMA tests pass 13/13; ASan/UBSan
LCD/view tests pass 10/10; staged ownership passes 72/72; EIM compile/link exits
0. Logs use `/tmp/cardputer-lcd-adapter-` with `tests.log`, `asan-tests.log`,
`scope.log` and `eim-build.log`. The prior failure records above remain retained.

## Version Management

The adapter Task allocates no Product Build and changes no Assembly identity.
After source integration, a separate version Task must allocate the completed
Host/Assembly candidate and include its immutable snapshot before formal A1.
Existing snapshots stay frozen.

## Documentation Impact

Documentation impact: required — `/platform/input/` and, at integration,
`/hosts/cardputer-host/`. Describe implemented output separately from pending
physical measurements; no positive capacity or complete A1 claim before evidence.
