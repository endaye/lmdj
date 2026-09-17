# Cardputer keypad event polarity repair

Repair Task: #1240. Relates to #1104 and #1108. Base:
`ee3b94577407f5dbb2263c3ad25cea01f3b760c6`.

## Defect and scope

TI TCA8418 datasheet SCPS215G, section 8.6.2.4, page 30 defines KEY_EVENT_A
bit 7 as 1 for a press and 0 for a release. The current scanner inverts that
bit, so InputController discards the real press as an unmatched release and
can admit the subsequent physical release as a new press. Existing synthetic
PhysicalKeyEvent tests do not exercise this hardware-byte conversion.
Source: https://www.ti.com/lit/ds/symlink/tca8418.pdf

Declared files:

- `apps/cardputer-host/main/keyboard_scanner.cpp`
- `tests/platform/cardputer/keyboard_scanner_test.cpp`
- `tests/platform/cardputer/fake_esp/driver/i2c_master.h`
- `tests/platform/cardputer/CMakeLists.txt`
- `apps/docs-site/docs/platform/input.mdx`
- this plan

Only correct event polarity; retain the matrix mapping, filtering, queue,
repeat handling, audio lifecycle, scan rate, resource limits and timeouts.
Do not bundle unrelated FIFO overflow or driver lifecycle work.

## Verification

Compile the real ESP scanner with a fake I2C register FIFO and the real
InputController/RuntimeHost/Facade. The native AudioSession renders real Core
PCM but does not run I2S or the speaker. Independently specified A/S/D/F event
bytes must trigger nonzero PCM on press, carry release to Core, and admit the
next press once; the M command must toggle on press only. Preserve a red run
with the old production scanner, then rerun after the one-bit correction.
The fake models event count and destructive FIFO reads, not electrical
debounce, scan latency, physical overflow or acoustic onset. A1 still requires
instrumented end-to-end timing on an immutable Product candidate.

Run registered scanner/input components, strict ASan/UBSan, pinned EIM ESP-IDF
build, staged ownership checks and `scripts/docs-site.sh check`. After commit,
classify the exact final range, obtain independent current-head review and
ship through the normal guarded PR workflow. Device source-candidate hearing
may test press-and-hold versus release, but is not the 1000-trigger p99 proof.

## Version Management

Version impact: none
Reason: Internal scanner repair, unchanged public API/wire and manifests;
no independently distributed Host or Product Build allocation. B1 must bind a
fresh immutable candidate before formal A1 acceptance.

## Documentation Impact

Documentation impact: required
Affected portal pages: /platform/input
Reason: Describe correct hardware-event polarity and distinguish register-level
regression coverage from physical input timing acceptance.

## Pitfall Impact

Pitfall impact: none — product defect expressed by the real-scanner regression;
synthetic-input limitations are documented rather than treated as hardware proof.
