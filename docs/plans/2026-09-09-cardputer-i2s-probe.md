# Cardputer ADV bounded I2S output probe

Date: 2026-09-09. User approved continuing from the successful receipt-bounded
resource probe to a minimal I2S/actual-audio experiment. Product source is the
unmodified merged revision `53170ee2f240e63458e8041eedf84c88351e886e`.

## Scope and declared files

One external research probe and one evidence commit, not the complete B2 T5
Host. Repository changes are this plan and
`docs/research/2026-09-09-cardputer-i2s-probe.md` only. External source, fresh
builds and raw evidence live in
`/Users/endaye/esp/lmdj-spike/cardputer-i2s.1vRZjv/`. Preserve earlier probes and
the verified original 8-MB Flash backup; publish neither Flash nor device ID.
No Core, Contract, queue capacity, Assembly, UI, keyboard matrix, microphone,
SD, network, release or CI changes. No Product Build allocation.

## Probe design

- EIM-managed IDF v6.1 at `fff9895c82d744c7237be8847347bdd1b07c6643`,
  fresh target build with all 18 sources / five producer closures retained.
- ADV ES8311 output only: I2C SDA 8/SCL 9, address 0x18; I2S BCLK 41,
  WS 43, DOUT 42. Use 48 kHz stereo PCM16, 256-frame blocks, six DMA
  descriptors, automatic zero clearing. No external MCLK pin; codec derives
  clock from BCLK as in pinned M5Unified board initialization.
- Desktop producer uses the existing runtime-content encoder, not a new wire
  format. One 50-ms faded sine sample provides a known audible reference;
  it is not a representative music library. Bind full SHA-256 and byte length,
  decode/inspect through product code and check native Facade PCM/receipts.
  Before implementation, the existing budget formula showed that a 100-ms
  PCM/float/workspace footprint adds about 57600 B and leaves insufficient
  space for drivers plus the unchanged reserve. Select 50 ms (28800 B)
  for this bounded experiment; this is not a reduced product capacity or a
  revised failed-test threshold. Report refusal if even this input cannot fit.
- Board behavior enters only Runtime Facade. Allocate drivers/DMA/audio task
  before admission and measure the remaining heap cap; keep the existing
  explicit 32-KiB provisional reserve. Never shrink capacity/reserve or enlarge
  measured cap to obtain a pass. Report allocation failure and largest block.
- Dedicated fixed-core audio task renders/converts/writes; I2S ISR only counts
  notifications. No logging, I2C, load, allocation or receipt polling in the
  render path. Use finite write timeouts and stop on short/error writes.
- Low digital output gain and reduced codec volume; bounded pulse sequence,
  followed by explicit silence/mute. Announce before flashing/output. Same
  sole board identity and previous image ranges must be verified first; write
  only generated bootloader/partition/application ranges, no erase-all/eFuse/SD.

## Verification and acceptance boundaries

Lowest tiers: native input identity/encoder-decoder/Facade checks and sample
conversion edge tests; strict target compile, source/flags/roots/ELF binding.
Real board must retain all ordered legs: codec readback and DMA allocation;
load identity; start; accepted Pad commands; nonzero software PCM and exact
voice-started receipts; drained stop; zero PCM/DMA tail; unload/no identity;
bad-identity refusal/silence; valid retry and replay; final stop/unload. Repeat
after independent resets. For stop, wait until the render task is quiescent
before destroying/unloading its Facade; flush multiple full DMA rings of zeros
before disabling I2S and muting the codec.

Report render/conversion durations against 256/48000 seconds, write errors,
ISR queue-overflow counts, heap/DMA deltas and task stack high water. Driver
notification overflow is not a calibrated analog underrun detector. No claim
of physical clock accuracy, analog latency, jitter, sound quality, ordinary
sample capacity or long-run stability without corresponding instruments.
Human hearing is a separate pending row until the user confirms this exact
image, pulse sequence and output route. Software PCM/DMA success cannot fill it.
Checker negative controls must reject omitted receipt, silence, identity and
completion evidence. No new global gate, weaker threshold or omitted leg.

Run scoped native checks, external probe checks, docs_static, source-fact
Portal checks and staged new-file ownership before the evidence commit.

## Version Management

Version impact: none
Reason: unmodified product source, external non-distributed research firmware
and two evidence documents; no Module, Host, Contract, Product Build, Assembly,
tag, release or Channel change.

## Documentation Impact

Documentation impact: none
Reason: this is experimental board evidence, not a supported Host or a change
to current Portal product boundaries. Portal source-fact checks still run.

## Pitfall Impact

No new qualifying process finding at planning time. Preserve failed attempts,
full source identity and every journey leg; never equate DMA writes with hearing.

## Outcome

The [research record](../research/2026-09-09-cardputer-i2s-probe.md) documents
codec/I2S/DMA setup success followed by actual allocation failure before audio
start. Two instrumented resets identify the 52416-byte Voice-state allocation
against a 51200-byte largest matching block, despite sufficient aggregate heap
and modeled budget. All refusal/retry/mute/cleanup legs execute, while the
original `load` check remains FAIL. The complete playback journey and hearing
are blocked, not passed. The probe did not change product layout or capacity
to bypass this boundary; a separately scoped allocation-layout repair is next.
