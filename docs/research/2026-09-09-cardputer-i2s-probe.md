# Cardputer ADV I2S probe: configured, but playback blocked by contiguous allocation

Date: 2026-09-09. Status: **BLOCKED_RESOURCE — no I2S playback or hearing PASS**.
This is the bounded experiment in the
[probe plan](../plans/2026-09-09-cardputer-i2s-probe.md), following the
[receipt-bounded storage improvement](../plans/2026-09-09-runtime-facade-voice-budget.md).
It is not the complete B2 T5 Host, Product Assembly, release or supported-device
acceptance. No product source or capacity changed in this Task.

## Result

The board acknowledged and read back the ES8311 configuration, initialized
48-kHz stereo PCM16 I2S with **6144 bytes of DMA buffers**, and allocated its
8192-byte audio task stack. Runtime Facade's modeled budget fit the measured
post-driver heap cap, but actual `load` returned **`allocation_failed`**.
The renderer was never started, the I2S channel was never enabled, and the
codec volume stayed zero. There should have been no test tones.

An allocation-failure observer identified the cause on two independent resets:

| Measurement at the failed allocation | Initial load | Same-input retry |
| --- | ---: | ---: |
| Requested aligned allocation | 52416 B | 52416 B |
| Free bytes matching allocation capabilities | 106452 B | 106404 B |
| Largest matching contiguous block | 51200 B | 51200 B |
| Request minus largest block | **1216 B** | **1216 B** |
| Result | `allocation_failed` | `allocation_failed` |

The requested size equals the target ELF's receipt-bounded Voice-state queue
allocation. The aggregate free space is sufficient, but no individual block
can hold the queue. This is a contiguous-allocation failure, **not a modeled
budget overrun, codec NACK, I2S API failure, or evidence that a smaller queue is
needed**. The difference above is between allocator-reported quantities, not
a claim that adding exactly 1216 physical bytes would guarantee success.

The previous 248-byte/four-frame fixture's successful resource probe remains
valid for that image/input. It did not prove admission with the larger sample,
I2C/I2S resources and an extra task present. Likewise, the current failure does
not establish that every allocation ordering or material on this board fails.

## Exact experiment

- Unmodified product source: `53170ee2f240e63458e8041eedf84c88351e886e`.
  All 84 tracked files in the five producer trees are hash-bound; the target
  compiles the complete 18-source closure and retains 17 Facade API roots.
- EIM-managed ESP-IDF v6.1:
  `fff9895c82d744c7237be8847347bdd1b07c6643`; Xtensa GCC 15.2.0,
  `esp-15.2.0_20251204`. Effective gnu++20 and strict Wall/Wextra/Wpedantic/Werror
  remain enabled for product sources, with no Wno escape. No parallel SDK.
- External probe/evidence directory:
  `/Users/endaye/esp/lmdj-spike/cardputer-i2s.1vRZjv/`.
- A desktop program uses the existing runtime-content encoder to produce one
  mono 48-kHz, 2400-frame, 480-Hz sine with 5-ms edge fades. Duration **50 ms**,
  source peak about 0.5, one One Shot Pad, no Pattern events. It is a known
  reference tone, not a normal musical-material library or capacity promise.
- Runtime-content identity: **5008 bytes**, SHA-256
  `3dfb3c49385d74c2a31654f031516b68129eceaa10aa21d791653ad116a3b82e`.
  Native decoder/inspector and Facade validate the complete identity, exact
  decoded sample, finite/nonzero PCM, voice-started receipt, natural end,
  stop/silence/unload, wrong-length refusal and valid reload. Native conversion
  checks cover zero, sign, clipping and NaN/infinity-to-silence. The resulting
  stereo reference has 2344 nonzero frames in its first 3072 frames.
- The initial planning sketch used 100 ms. Before implementation, the existing
  accounting formula showed about 57600 B of PCM/encoded/float/workspace growth,
  excluding driver cost; 50 ms was selected as a bounded 28800-B growth input.
  Once the actual 50-ms load failed, neither duration nor any limit was reduced.

### Driver configuration and intended journey

The [M5Stack board documentation](https://docs.m5stack.com/en/core/Cardputer-Adv)
identifies ES8311 and its ADV pin map. I2C uses SDA 8/SCL 9 at address 0x18;
I2S uses BCLK 41, WS 43 and output 42, with no external MCLK pin. The codec
clock/power register sequence is adapted from
[M5Unified at the pinned upstream revision](https://github.com/m5stack/M5Unified/blob/8530f5377d782e4a25a6c482de2e71c3f75ca8eb/src/M5Unified.cpp#L1000),
which selects BCLK-derived clocking. Volume is initialized/read back as zero;
the unexecuted playback path selects 0xA7 with an additional Host digital gain
of 1/4. The board documentation also notes that headphone insertion disables
the speaker amplifier; hearing route must be explicit in any later test.

The [pinned IDF I2S interface](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/components/esp_driver_i2s/include/driver/i2s_common.h)
defines six 256-frame stereo PCM16 DMA buffers in this probe: 6 × 256 × 4 =
6144 bytes. Automatic TX zero clearing is enabled. The fixed-core-1,
priority-10 task would call Facade render, bounded conversion and full-block
I2S writes with a 50-ms write timeout. ISR callbacks only count sent buffers
and queue-overflow notifications. No I2C, logging or control mutation enters
the render path. Notification overflow is not an analog underrun instrument.

The intended sequence was four short Pad pulses spaced by half a second,
stop, at least 24 software-zero blocks, two additional full zero DMA rings,
I2S disable, codec mute, unload, invalid-identity refusal, valid reload and a
second four-pulse journey. **None of those post-load playback legs executed.**
Compiled code for them is not timing, concurrency or audio acceptance evidence;
they must be exercised after the allocation obstacle is repaired.

## Resource and refusal evidence

First image (without the observer) already failed at load. Its ELF and source
are preserved under `attempt-01/`; `run-01.serial.log` retains the failed load
and muted cleanup. Its modeled admission was 326465 B against a 331304-B cap.

The second image adds a bounded, control-load-only failed-allocation observer
and complete refusal/retry assertions. The observer makes no allocation or
log call. It reads geometry after IDF's base allocator has released its lock,
before C++ exception unwinding frees Engine. It is never active in audio/ISR.
The 96-B baseline heap difference from the first image is retained rather than
claiming the instrumentation has zero footprint.

Second image probe source SHA-256:
`7f21e67b26e3ee68e3b0274297f427a80cbacac0a596b6139a6208696a90ae03`.
Second image ELF SHA-256:
`8dd314d465eff99251e61c3a4fb6d7d887c53957abc63e0245ca76ebc069e7bd`.
Both `run-02` and `run-03` report those complete identities and these readings:

| Heap stage | Free | Largest block |
| --- | ---: | ---: |
| Before drivers | 347960 B | 278528 B |
| Drivers and audio task allocated | 331208 B | 278528 B |
| After failed load and unwinding, Facade alive | 322636 B | 270336 B |
| Facade/drivers/task cleanup | 347776 B | 278528 B |

Driver/task allocation delta is **16752 B**, including the 6144-B DMA payload
and the 8192-B task stack; the remainder includes driver/control structures.
This delta is not a calibrated final platform reserve. The unchanged 24-KiB
control stack has minimum observed free space **13884 B**, i.e. 10692 B used.
The audio task only waited; its active-render stack high water was not measured.
PSRAM is zero and all sampled heap-integrity checks return 1. Observed global
heap minimum is 106144 B. Cleanup is 184 B below pre-driver free heap; without
attribution or repeated allocation tracing, this is **not a zero-leak claim**.

Admission model, using the measured post-driver cap of **331208 B**:

```text
fixed       261860
encoded       5008
PCM           4800
float         9600
metadata       613
workspace    11816
reserve      32768
-----------------
admitted    326465  (4743 B below the cap)
```

The current RuntimeConfig cap is a modeled preparation allowance, not an
allocator-enforced or fragmentation-aware guarantee. It correctly allows the
model then preserves failure atomicity when actual allocation fails. No cap,
reserve, queue capacity, Voice count, sample or product behavior was changed.

Each instrumented run contains **21 passed checks and one failed `load`
check**: observer/setup/codec/DMA/task; initial empty; failed load; empty/no
identity/software silence; rejected start; same failure on retry; retry remains
empty/silent; unload; zero-volume readback and full driver cleanup. Both load
attempts fail the same 52416-B allocation with a 51200-B largest block.
The original playback checker exits 1 for all three runs and is not rewritten
to report audio success. A separate refusal-evidence checker verifies all 22
ordered assertions, complete identities, both failure sites, budget, DMA,
readbacks and cleanup; **16 negative controls** reject omitted silence/start
rejection/retry/mute/completion, wrong length, erased failure and false geometry.
Its verdict is complete evidence of **blocked playback**, never playback PASS.

## Verification, recovery and next boundary

- Fresh native `cooker.runtime_content` and `facade.runtime_facade`: 2/2 PASS;
  the separate native producer/conversion/journey program also passes.
- First target build failed because `auto` could not deduce the type of IDF's
  designated-initializer macro; explicit `i2s_chan_config_t` fixed the external
  probe, without relaxing strict warnings. Subsequent target builds pass.
- The first device-identity parser wrongly expected only one MAC-print line;
  esptool prints the same identity before and after loading its stub. The
  corrected check requires one unique identity and equality with the retained
  board receipt. Both failed transcripts remain preserved; no mismatch was
  waived and no firmware was written until the corrected check passed.
- Pre/post-build source/ELF/roots/flags/input checks pass. Portal/source-fact
  check passes 114 tests, 44 current pages, 10 diagrams/20 outputs and 44
  routes/internal links. docs_static and staged ownership results accompany
  the evidence commit/PR.
  No full product CI or release verification is claimed.
- Before the first write, the original 8388608-byte Flash backup digest and
  same device identity were verified, and all three previous diagnostic image
  ranges matched. Before the instrumented write, the first probe's three
  current image ranges matched. Both supported `idf.py flash` writes verified
  only bootloader 0x0, partition table 0x8000 and application 0x10000.
  No erase-all, eFuse, SD, network, UI or original-backup modification occurred.
  The board currently retains the muted **instrumented diagnostic firmware**;
  the original firmware remains backed up, not restored.

Next work should investigate allocation layout/lifetime or bounded storage
placement **with capacities and the 32-KiB reserve unchanged**, then rerun this
same 5008-byte input and complete playback journey. An allocation-order or
storage-layout repair must carry its own proof and Task; it was not silently
implemented in this research probe. No success is promised for a particular
reordering from these measurements alone.

Human hearing, physical I2S clocks/data, analog silence/quality/latency,
render/write deadlines, underruns and active audio-task stack remain unmeasured.
The user was initially asked about the planned tone sequence before load failed;
that question is superseded by the observed pre-playback refusal, not an audio
acceptance row. The next hearing request must identify an image that actually
passes load and starts playback.

## Evidence inventory

Raw/source/build evidence stays local. The sealed inventory records exact
lengths and hashes for both image variants, the producer, fixture, configuration,
ELF/map, strict compile commands, source closure and serial/refusal checks.
Private device/reset/flash logs and the original Flash dump are excluded from
the shareable archive; nothing was uploaded or released.

`probe-evidence.tar.gz`: **89 files**, **21507400 bytes**, SHA-256
`19796177573030ecd7a1921a91bb2a1f186f7fb69331d880a374826cbfd3071a`.
Each archived member was checked against its digest/length inventory.
