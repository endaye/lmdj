# Cardputer ADV: fixed-first allocation enables the I2S probe

Date: 2026-09-09. Historical checkpoint: **digital I2S journey PASS; human hearing pending at capture**.
This is the bounded [allocation-order Task](../plans/2026-09-09-cardputer-allocation-order.md),
not a complete Cardputer Host, normal musical-capacity promise or release.

Later external Host/tone experiments and explicit user confirmations are
recorded separately in the [bounded audio follow-up](2026-09-09-cardputer-audio-hearing.md).
They do not retroactively qualify this earlier image or replace its evidence.

## Result and repair

The same board first reproduced the
[previous refusal](2026-09-09-cardputer-i2s-probe.md): the 52416-byte queue
allocation had 106452 free bytes but only a 51200-byte largest block.
Same-input retry also failed; the old image remained empty/silent and muted.

The product repair only moves candidate Engine construction, including its
existing receipt-bounded queue, before decoded PCM and prepared variable
storage. Complete content inspection and aggregate budget admission still
precede it. Candidate ownership remains local until preparation and identity
copy succeed; every later error destroys the candidate without publishing it.
No queue layout, capacity, concurrency protocol, runtime API or budget term
changed. This ordering helps this measured heap; it does not guarantee that
arbitrary fragmented heaps admit the same content.

Two independent resets of the repaired image each passed all **70 ordered
checks**. Each reset exercises both four-tone journeys, exact command receipts,
stop/drain/software silence/zero DMA tail, disable/mute/unload, malformed
identity rejection with empty/silent state, valid reload, and final cleanup.
The external verifier also rejects 16 deliberately incomplete/corrupted
transcripts, including missing retry, silence, receipt, mute and completion,
wrong input identity, reduced reserve and false DMA/deadline claims.

## Unchanged conditions and exact inputs

- Product baseline `60567f822971631f9669b1755939e70b418fcb69`, with exactly one
  product-source overlay: `packages/application-facade/src/runtime_facade.cpp`.
  Overlay SHA-256:
  `709606bf12cadc98114c5328a322f7638f3ffcc4c973475f023f93d39a379580`.
  All 84 tracked producer-tree files are hash-bound, 83 unchanged; all 18
  product translation units compile and 17 Facade API roots remain linked.
- EIM ESP-IDF v6.1, revision `fff9895c82d744c7237be8847347bdd1b07c6643`,
  Xtensa GCC 15.2.0 (`esp-15.2.0_20251204`). Effective gnu++20,
  Wall/Wextra/Wpedantic/Werror and no Wno escape in product compilation.
- ELF SHA-256:
  `43749b58d7f1f751145c1a8e31e98e36ae80b129c8110111567b3f1766027322`.
  Both actual boot transcripts print this ELF, baseline, overlay and probe
  source digests. The image is baseline-plus-overlay, not unmodified main.
- Exact runtime content: **5008 bytes**, SHA-256
  `3dfb3c49385d74c2a31654f031516b68129eceaa10aa21d791653ad116a3b82e`.
  One 50-ms/2400-frame mono 48-kHz 480-Hz tone, 5-ms fades, one One Shot Pad,
  no Pattern events. Rebuilt native encoder/decoder/Facade produces identical
  bytes and a 2344-nonzero-frame reference per tone.
- Queue capacities remain 2176 for Runtime Facade and 10240 for default Engine;
  Engine is 201024 bytes and its selected queue is 52416 bytes on the target.
  Platform reserve remains **32768 bytes**. Main stack remains 24576 bytes;
  audio-task stack 8192 bytes. No PSRAM.
- Same ES8311 setup and readbacks: I2C address 0x18, SDA 8/SCL 9; I2S BCLK 41,
  WS 43, DOUT 42. Stereo PCM16/48 kHz, six 256-frame buffers = **6144 DMA bytes**.
  Audio task remains core 1/priority 10. Playback volume 0xA7 plus Host gain
  1/4; volume-zero setup and final mute are verified by register readback.

The original 8-MB Flash backup's length/digest and same device identity were
verified, and all three currently installed old image ranges matched before
flashing. Supported `idf.py flash` wrote generated bootloader/partition/app
ranges and verified hashes. Original firmware remains backed up, not restored.
No erase-all, eFuse, SD, microphone, network, UI or product deployment action.

## Measured resource and audio evidence

Both resets retain the same model and entry geometry:

| Quantity | Bytes |
| --- | ---: |
| Free before drivers; largest block | 347960; 278528 |
| Free after drivers/task; admitted cap | 331208 |
| Fixed + encoded + PCM + prepared float | 261860 + 5008 + 4800 + 9600 |
| Metadata + workspace + unchanged reserve | 613 + 11816 + 32768 |
| Admitted total | 326465 |
| Free after first successful load; largest block | 53856; 21504 |
| Free after reload | 53712 |
| Observed minimum through both journeys | 43792 |
| Free after complete cleanup; largest block | 347776; 278528 |

Allocator overhead and simultaneous temporary storage remain real; aggregate
admission is not a largest-block test. The cleanup endpoint is 184 bytes below
entry, as in the old probe; attribution is not established, so this is not a
zero-leak assertion. Heap integrity is 1 at every sample. Minimum main-stack
free is 13884 bytes (10692 used); the actually running audio task reports
3972 free (4220 used) of its 8192 bytes.

Each of the four audio journeys across two resets recorded:

- 450 rendered blocks, 40 nonzero blocks and **9376 nonzero frames**, matching
  four times the native reference; no nonfinite samples or stopped-silence
  violations. The log field calls these `nonzero_samples` but counts stereo
  frames with either channel nonzero, not individual channel samples.
- 12 additional zero-tail blocks; **473088 bytes** fully accepted by I2S;
  462 sent-buffer notifications; no short writes, driver errors or notification
  queue overflows. Notification progress is digital evidence, not an analog
  underrun or oscilloscope measurement.
- Maximum render 4778–4779 µs; maximum conversion 356–358 µs; combined work
  maximum **5071–5072 µs**, below the 5333.33-µs block duration. No measured
  processing deadline misses. The worst observed margin is only about
  **261 µs (4.9%)**; this is a narrow one-voice experiment, not a general
  realtime capacity/jitter guarantee. Driver blocking, measured separately,
  reached 5007 µs and paces output outside Core render.

At this checkpoint no human hearing response or analog capture was recorded. Digital writes
and codec readbacks cannot prove audible speaker output, pitch, clicks, noise
or listening quality. The board retained this diagnostic image at the checkpoint: a
reset waits five seconds, attempts two four-tone groups, then mutes/cleans up;
the screen has no product UI. The later follow-up records the subsequently installed image.

## Native verification and retained failures

The new allocation-order component test failed after rebuilding the old
implementation: Engine allocation position 59, queue 60, PCM 47. After the
repair the same assertion passes. Existing exhaustive allocation-failure
sweeps still verify empty/no identity/silence and successful load/start/render
retry at every load allocation site. Dev Runtime content, Engine, Facade and
Facade stress: **4/4 PASS**. ASan Facade component plus stress: **2/2 PASS**.
This is scoped verification, not a full native build, full CI or TSan claim;
no concurrent algorithm was changed.

The fresh external IDF directory initially selected default ESP32 rather than
ESP32-S3. Compilation failed on the ADV's GPIO numbers, and source verification
also refused that build's flags. Nothing was flashed from it. Explicit
`idf.py set-target esp32s3`, a complete rebuild and strict source/ELF/config
verification then passed. The final sdkconfig equals the preceding probe's;
failed build and verification transcripts remain retained, not overwritten.

Dependency, active-tree and version checks PASS. Portal check: 114 tests,
44 pages, 10 source diagrams/20 outputs and 44 routes/internal links PASS.
No qualifying new process pitfall: the repaired allocation-order defect is
captured by its component regression and same-device evidence.

## Local evidence

External directory: `/Users/endaye/esp/lmdj-spike/cardputer-allocation.5brq88/`.
The inventory binds product overlay, source closure, native reference, strict
target commands/config/ELF/map, failed attempts, raw device journeys and the
full-journey verifier. Private device/reset/flash logs and the original Flash
backup are retained separately and are excluded from any evidence archive.
No evidence upload, release or cleanup is authorized or performed by this Task.

Sealed `probe-evidence.tar.gz`: 79 files, 11004643 bytes, SHA-256
`f718ba3970cfae00d17bfad64c982a107f3ba5c020edaff16004efec39986d2c`.
All members were verified against the explicit length/digest inventory.
