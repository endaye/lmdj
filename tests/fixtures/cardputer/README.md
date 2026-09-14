# Cardputer music capacity fixture

Original synthesized drum material, dedicated to the public domain under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). No downloaded
samples or third-party recording is included. The generator uses integer-only
DSP, explicit little-endian PCM16 and seeded noise: no platform libm or RNG.

`music_fixture.json` fixes all sample hashes/lengths and the complete event table.
Each of A and B contains a 250 ms kick, 250 ms snare, 100 ms closed hat and
400 ms clap: 48000 mono frames / 96000 PCM bytes at 48 kHz. Different synthesis
seeds and pitched bodies distinguish B from A; the 32-event two-bar pattern
stays constant so the sound change is not confused with a timing change.

```bash
python3 tests/fixtures/cardputer/music_fixture.py --check
python3 tests/fixtures/cardputer/music_fixture.py --output /tmp/cardputer-music-new
python3 tests/build/cardputer_music_fixture_test.py
```

The output directory must not exist. PCM files are generated research inputs,
not checked-in Product artifacts. A same-source native probe constructs a
Runtime Snapshot from these samples/events and calls the actual Core encoder;
this generator does not duplicate or translate the Runtime Content contract.
The report binds each exported content to its full digest and byte length.

During the performance journey, press all four pads within one render block
while the Pattern runs, collect four `voice_started` receipts, then release and
retrigger; record actual overlap with an appropriate probe instrument. The
event table alone does not prove four simultaneously audible voices. Automation
also cannot certify subjective drum recognizability or physical input latency.

These tests fix the agreed workload, not a smaller substitute for device
acceptance. Failing memory admission leaves timing, physical audio and the
30-minute combined Host journey unmeasured, never reported as zero or PASS.
