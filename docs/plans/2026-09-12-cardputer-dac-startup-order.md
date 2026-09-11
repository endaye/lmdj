# DAC startup-order candidate — physical verification pending

## Scope

Local candidate on production source 9e542c54dab883214c542e68dd1af563087cb994.
Two files: this plan and `apps/cardputer-host/main/audio_driver.cpp`.
No push or PR until physical validation and shipping verification are complete.

Keep DAC powered down (register 0x12 = 0x02) during configure and I2S startup.
Power it up (0x12 = 0) at the existing hardware-unmute transition, which occurs
only after silent DMA prewarm and drain. Restore normal unity codec gain and
hardware unmute. No diagnostic sleep or permanent mute is included; normal
software volume, prewarm, DMA, stop and timeout policies remain unchanged.

## Evidence and verification

Diagnostic 0cea879e75d3d9b056247805a789b29403b78771, with DAC always powered
down, produced no playback-start short sound, with confirmed Running/error 0.
The otherwise-matching DAC-enabled diagnostic did produce a short sound.
That isolates a DAC/clock interaction but does not establish this candidate as
a repair. A separate reset sound was observed and is not reclassified.

Verify the real ESP register-write order with a native traced-I2C harness,
strict warnings and ASan/UBSan. Build with pinned EIM ESP-IDF, commit the local
candidate, rebuild exact head, record image hash, and flash. Load the unchanged
four-pad A content and verify full digest/length plus Ready. User starts once:
require Running/error 0, audible continuous music and no startup transient.
Then independently check stop/restart, mute/unmute, and repeated pad triggers.
An absent sound while empty, failed, or inaudible is not a successful result.
Final immutable Product candidate and sustained acceptance remain outstanding.

## Version Management

Version impact: none. Local source candidate only; no Build allocation or
release. Final Product acceptance needs a new immutable candidate and snapshot.

## Documentation Impact

Documentation impact: none
Reason: This local candidate has not established a product behavior change;
before shipping, reassess portal impact and add applicable regression coverage.
