# Cardputer codec unity-gain repair

Relates to #1104 and #1107. User reported complete silence with four-pad music
loaded and Host Running. ES8311 DAC register 0x32 was incorrectly set to 0x40
(-63.5 dB); software default volume then applied another 20% gain.

## Task and declared files

- `products/lmdj/src/cardputer_assembly.cpp`: use codec unity gain 0xBF;
  preserve software volume, mute, ramps, pin profile and memory limits.
- `tests/platform/cardputer/codec_gain_test.cpp`: compile the actual Assembly,
  assert the datasheet gain equation and quiet default PCM/mute behavior.
- `tests/platform/cardputer/CMakeLists.txt`: register the component regression.
- `apps/docs-site/docs/hosts/cardputer-host.mdx`: explain source output gain.
- This plan.

## Verification

Independent register oracle: ES8311 datasheet Rev 10, register 0x32, 0.5 dB
per step from -95.5 dB; https://files.waveshare.com/wiki/common/ES8311.DS.pdf .
Previous device hearing research also records 0xBF, not 0x40.

Old Assembly fails the compiled regression (exit 134). Run the regression with
strict warnings and ASan/UBSan; native PCM ramp/mute/volume/lifecycle scenarios;
staged scope ownership; portal check; pinned EIM ESP-IDF build. New test catches
codec attenuation mistakenly multiplied into the software gain path. No new
required CI gate. The native test does not prove sound pressure or hardware
output. Follow with same four-pad music transfer and physical listening at
default software volume; do not auto-play during flashing or raise software
volume to compensate. Combined-load, duration and final candidate remain open.

## Version Management

Version impact: none for this source-only correction; no Build allocation or
release. Existing immutable snapshots are unchanged. Final team acceptance
requires a separately allocated Build and matching immutable portal snapshot
containing all accumulated source repairs; this diagnostic is not that candidate.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/cardputer-host/
Reason: Product Assembly codec output gain changes; current page explains the
gain stages and retains the physical/candidate acceptance boundary.

## Pitfall disposition

Product-logic regression; no new process-ledger entry.
