# Runtime voice scan budget (#1176)

## Scope and evidence

R2 retained a real target CPU-margin failure. The target render disassembly
shows two per-frame loops scanning all 128 Voice slots, including idle slots:
65,536 slot visits per 256-frame block. This is a bounded-work observation,
not a measurement of the fraction of total CPU spent in those loops.

One Task changes only:

- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- this plan
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`

Maintain an audio-owned highest-active-slot-plus-one extent. Both admission
paths expand it; completion/cancellation trim inactive trailing slots; quiescent
start/stop reset it. Bound only the two per-frame scans. Preserve holes,
first-free admission, ascending mix order, all 128 voices, and existing ramps,
ownership, counters, overflow and queue semantics. Do not change fixtures,
sample rate, gains, thresholds, contracts, FX or Host wiring.

## Verification

Lowest-tier `audio.realtime_engine` checks high-slot survival after lower slots
finish, low-slot reuse, completion and restart, alongside existing full-capacity,
pattern, release, allocation and ownership tests. Rebuild affected consumers.
Use the same external release benchmark before/after with idle, low sparse,
high sparse and dense cases, exact PCM checks and telemetry; native timings are
diagnostics, not a CI threshold or Cardputer acceptance. Rerun the original R2
target workload after integration before claiming target CPU-margin recovery.
Run `scripts/docs-site.sh check` for the updated source fact.

## Version Management

The added private field changes Engine C++ layout; all binary consumers must
rebuild together. Audio Runtime MAJOR allocation and Product Build/immutable
snapshot remain staged for B1, together with M1/M2. No identity is allocated
here; this source cannot replace an old-ABI binary.

Documentation impact: required — `/core/modules/audio-runtime`.


## Acceptance completion (2026-09-27)

The implementation is already merged by PR #1178 at
`6d4c68042eaf53bbfdc5f16c2398694fbf1c7dfb`; do not repeat the optimization.
This follow-up Task declares only the existing Engine test, this plan and the
Audio Runtime portal page listed above. Its purpose is complete PCM regression
and evidence reconciliation. Product source, fixtures, thresholds and manifests
are unchanged by this follow-up.

### Source and attribution audit

The original red source is `22a62ada74f8fb387240648b23973a0f1d9ce6ce`.
Its actual I2S image/capture and 4284 us conservative service maximum remain in
[the R2 report](../research/2026-09-10-cardputer-music-capacity-retest.md).
Of the 96 product/fixture files frozen in the postscan probe, only the Engine
header and implementation differ from that red source. All 96 frozen byte
lengths and SHA-256 values match the measured merged revision. All five files
reviewed at PR head `e5e5eb0bf582224137866b5c1c9508baecfec77e` match the squash.

Before implementation, target disassembly counted two 128-slot scans per frame:
65536 visits per 256-frame block. The external A-B-B-A native experiment then
isolated sparse-slot work: pooled six-voice low-slot medians were 30.818209 to
5.549230 us/block; slot-127-only was 27.140480 to 29.133854 and dense 128 voices
136.674605 to 136.626979. The high-slot overhead is retained. The benchmark's
checksum sampled only each block's final left sample; it was never complete PCM
parity. These bounded-work and controlled comparisons support scan attribution,
not a function-level target CPU percentage or a universal speedup.

The postscan probe rebuilt the exact merged source with no product overlay,
unchanged SDK/GCC, 240 MHz/O2, 4 Pads, 96000 PCM bytes, 32 events,
48 kHz/256 frames, reserve and 128-slot capacity. Full A/B native reference bytes
match the target's embedded reference. Two separate actual I2S captures each
contain 100 complete load/play/stop/unload cycles, 4568 music blocks, Core max
1649 us and conservative service maxima 1876/1874 us against the original
4266.666... us budget. The complete target ABI admission is 302383 bytes.
Combined with the controlled source delta, this is measured evidence that the
scan fix recovered the observed R2 workload's CPU margin. It makes no promise
for arbitrary 128-voice music.

The follow-up base is `6ab797dc884c4b4731723cbf0950ee791737367f`. Later source
changes include Pattern transport/phase handling, peak-voice observation and
audition publication fixes. Inspection confirms both admission paths still
expand the extent, both per-frame scans use it, both terminal paths trim it,
and quiescent start/stop reset it. The historical hardware captures establish
results only for `6d4c6804`, not today's source. This Task changes no product
source requiring a replacement target probe.

### Lowest-tier regression matrix

Engine cases execute in `audio.realtime_engine`; the Facade reset evidence is
listed separately. New PCM assertions compare complete left/right buffers
exactly, including ramps and terminal silence; no epsilon or checksum replaces
sample assertions. Setup-only rendering advances are not PCM assertions.

| Invariant / transition | Observable after transition |
| --- | --- |
| All 128 slots and excess admission | Existing capacity test mixes 128 and reports exactly one dropped voice |
| Slot 127 survives lower natural completion | Complete attack/body/boundary/first-silent-frame PCM equals the specified envelope |
| Interior hole, first-free reuse, ascending mixing | Non-associative float inputs distinguish inserting into the hole from appending or reversing order |
| Release, stop-slot, stop-all | Separate invocations check every frame of the 96-frame tail and following silence |
| Choke of a releasing high voice | Second stop produces immediate full-block silence and no active voice |
| Preview set/clear | High-slot voice retains the snapshotted gain after preview clearing |
| Audition stop | High audition renders the complete tail then silence |
| Pattern admission and scheduled release | Slot 127 produces complete PCM and releases at its prepared deadline despite lower holes |
| Quiescent stop/restart/reset | Stopped and restarted outputs are silent, then a new trigger starts at the first sample and attack frame |
| Facade running reset | Retained same-source native R2 journey reaches Empty with no identity and silent output |

The Engine suite and new order test are also checked with external, temporary
active-count and reverse-mix mutations. Both fail (the active-count mutation
first trips the existing phase-retirement regression; reverse-mix trips the
new interior-hole PCM assertion). The rebuilt restored Engine passes. No mutation is committed or used in target
measurements. No new test registration, CI gate or timing threshold is added.

Task commands: configure/build `dev`, `asan`, `tsan`; run
`ctest --test-dir build/core/PRESET -R
'^audio\.(realtime_engine|realtime_spsc_stress|snapshot_publication_stress|long_sample_publication_stress)$'
--output-on-failure` after building the corresponding four test executables.
Also run `scripts/docs-site.sh check`, exact staged-file/diff checks and final
committed scope classification. Sanitizer executions are serialized.

### Retained evidence and review

The external evidence directories remain under `/Users/endaye/esp/lmdj-spike/`:
`runtime-voice-scan-m3.qeAkHQ`, `cardputer-capacity-i2s.u3pYjy` and
`cardputer-capacity-postscan.bIfER9`. The follow-up rechecks original receipt/log
hashes, full native/reference bytes, source manifests, ELF/probe identities, both
I2S analyzers and all 14 bad-evidence controls. The old audit script refers to a
removed worktree; a separate read-only audit resolves the measured files through
Git objects. Original scripts, raw logs and failed runs are preserved.

The earlier Issue comment predates the owner's unchanged, numeric-identity-bound
[PR #1178 takeover attestation](https://github.com/endaye/lmdj/pull/1178#issuecomment-5620644651)
and [PR #1179 report attestation](https://github.com/endaye/lmdj/pull/1179#issuecomment-5620645307).
The former adopts an independent inspection of all five implementation files
and verification; the latter adopts independent source/receipt/analyzer review.
Both report no findings and state their limitations. The #1178 review was
supplemental **after** its historical merge. This resolves the missing adopted
review evidence; it does not reconstruct a premerge review or turn automated
run `34456258170/1` into success. This follow-up must independently pass current
head review, findings/conversation checks and protected squash merge.

R2 #1131, H1/B1/A1 and the umbrella remain separate acceptance scopes. The
short I2S probes do not establish 30-minute stability, physical underrun,
1000 analog latency measurements, full Host cost or complete audio quality.
The original failure and faint crackling feedback remain evidence.

## Follow-up Version Management

Version impact: none. Only regression tests and evidence documentation change;
no additional API/ABI, Product Build, tag, Release, Channel or snapshot is
allocated. The original private-layout break required consumers to rebuild;
current Module and Assembly identities are derived by the portal from manifests.

Documentation impact: required
Affected portal pages: /core/modules/audio-runtime/
Reason: reconcile the measured-source R2 result, adopted reviews and exact PCM
regression coverage with the original scan invariant and remaining boundaries.
