# DAC startup-order repair

## Scope

Local candidate on production source 9e542c54dab883214c542e68dd1af563087cb994.
Declared files: this plan, `apps/cardputer-host/main/audio_driver.cpp`,
`tests/platform/cardputer/dac_startup_test.cpp`, the adjacent `CMakeLists.txt`
and `fake_esp/driver/i2c_master.h`, and
`apps/docs-site/docs/hosts/cardputer-host.mdx`.
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

## Physical source-candidate observations (2026-09-12)

Flashed local candidate `9afed708767c0bcc8964ece2b19dc85597c83024`;
image SHA-256 `504bb401af4cb5225de8a655f9e2cf09e000ae63e06feba561a66e34f272a578`.
Transferred A: 96808 bytes, SHA-256
`2b3ae5e4f1a1753acfd9e3039439e7ae07c6e2fd885fd8375233184821009d63`;
COMMIT returned that complete identity, followed by Ready/error 0/four pads.
User confirmed continuous drums and no startup POP; far-side Running/error 0,
unmuted, volume 2, four pads and 96808-byte content.
User reported no POP on stop/restart, then pressed Enter and M before status
inspection: Empty/armed/muted/wrong_state was retained, not a successful
post-restart observation. Reload of the identical A returned Ready/error 0.
User then confirmed no POP for muted startup and M unmute/mute/unmute;
far-side Running/error 0/unmuted with the same length and pad count. User also
confirmed restored drums and two audible triggers each on A/S/D/F; final
status again Running/error 0/unmuted, volume 2/four pads/96808 bytes.
This is short source-candidate hearing evidence, not a measured transient,
reset/power-on acceptance, clean per-transition stop/restart receipt, or A1 pass.

## Regression and shipping verification

Component `dac_startup.order` catches DAC enable before clock startup and
incorrect power/gain/unmute ordering over two configure/release cycles.
`dac_startup.power_failure` catches continuation after DAC power-up failure.
Both compile the real ESP driver against fake I2C/I2S; existing
`audio.prewarm`, `audio.explicit_prewarm`, `audio.drain_failure` and
`audio.unmute_failure` are companion lifecycle assertions, not analogue proof.
Run the Cardputer native component set (including strict ASan/UBSan for the
new tests), pinned EIM build, scope ownership tests after staging, and
`scripts/docs-site.sh check`. Preserve a red-baseline run of the order test.
Pitfall disposition: product startup-order defect expressed by regression
tests; no new process-ledger entry. Full combined load, 30 minutes, latency,
simultaneous voices and final immutable candidate/snapshot remain outstanding.

## Version Management

Version impact: none. Source repair only; no Build allocation or
release. Final Product acceptance needs a new immutable candidate and snapshot.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/cardputer-host
Reason: Document the DAC/clock startup ordering and its verification boundary.
