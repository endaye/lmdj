# Cardputer ADV runtime resource and admission probe

## Authority and scope

Approved 2026-09-09: use the user's sole connected Cardputer ADV to measure
real resources and attempt minimal Runtime Facade admission. This is a bounded
external research probe, not the complete B2 T5 Host or an audio acceptance.
No product capacity, CI, model backend, Contract, driver or Assembly change.

Exact product source: `692ac4837ce79c9681fed81d06eedfac9ee84f5c`.
The isolated checkout remains at that source during firmware construction;
documentation changes do not enter the source closure. Reuse the complete
T4 18-source closure after comparing its five producer CMake files, compile
every source, and bind ELF/source/config/fixture and serial evidence by hashes.

One research commit, declared files:

- this plan;
- `docs/research/2026-09-09-cardputer-runtime-resource-probe.md`.

External probe and private recovery backup:
`/Users/endaye/esp/lmdj-spike/cardputer-runtime-resource.RSMqZL/`.
Do not commit or publish a device Flash dump, device identity or unrelated
firmware contents. Preserve original T4 and memory-optimization evidence.

## Device and safety boundaries

Resolve the sole USB serial device, verify ESP32-S3 and 8 MB Flash, and read
security information. Do not alter eFuses, security, voltage or partition data
outside the probe's explicit flash image ranges. Back up the full Flash and
verify it against the device before writing. A failed/incomplete backup is not
permission to overwrite the firmware. No blanket erase or microSD writes.

Use EIM-managed IDF v6.1 at
`fff9895c82d744c7237be8847347bdd1b07c6643` and its Xtensa GCC 15.2.0.
No PSRAM, Wi-Fi, display or audio driver. The probe's explicit 24 KiB main
task stack accounts for the previously measured 6800-byte decoder frame and
nested calls; report its actual high-water mark rather than treating that
allocation as free. An explicit 32 KiB future-platform reserve is provisional,
not a calibrated DMA/Host budget or a product setting.

## Lowest-tier evidence and stopping rules

1. Validate the exact 248-byte golden runtime-content fixture's SHA-256 and
   length against its checked-in identity; embed bytes in flash read-only data.
2. Preserve complete build transcript/exit and producer/source/root inventory,
   ELF/map/size. Verify strict product warnings and gnu++20 are retained.
3. On hardware report internal 8-bit heap total/free/minimum/largest, PSRAM,
   task-stack high water, exact Engine size and a temporary aligned allocation
   of that exact size. Free a successful temporary allocation immediately.
4. Through Runtime Facade, attempt admitted load using the measured entry heap
   as the cap and the declared reserve. Record every RuntimeBudget field and
   exact result. On refusal assert empty phase, absent identity, silent render,
   rejected start; retry and record its result. Never raise the cap, shrink
   queues or bypass admission to force playback.
5. If admission unexpectedly succeeds, validate full identity, start/submit,
   render and receipt, stop/silence/unload, invalid-identity rejection, then
   reload. This is CPU-render evidence only, not I2S, sound or deadline proof.
6. Retain raw serial receipts and repeat after a reset. A crash, incomplete
   transcript or unmet leg remains failure/pending, never a success prefix.

Run fixture conformance, probe checks and docs_static; run Portal checks for
the reported source facts and staged new-file ownership before commit.
No new required CI gate, timeout change or weaker test assertion.

## Version Management

Version impact: none
Reason: external, non-distributed research firmware and two evidence documents;
no Product Build, Module, Host, Contract, Assembly, release or Channel allocation.

## Documentation Impact

Documentation impact: none
Reason: experimental board evidence does not establish supported ESP32 product
capability or change current Portal boundaries. Portal source checks still run.

## Pitfall Impact

Pitfall impact: none. No new process defect was established. Device resource
refusal is a measured capacity finding, not a repaired product defect. Preserve
failed attempts and distinguish Flash capacity, total heap and largest block.

## Completion

The [research record](../research/2026-09-09-cardputer-runtime-resource-probe.md)
contains two complete independent reset runs. Both report the same 351672-byte
free heap, 286720-byte largest block, failed 446976-byte aligned allocation and
`budget_exceeded` admission with 139935-byte modeled deficit including the
provisional reserve. All 11 refusal/retry/reset assertions per run passed.
This completes the probe, not successful B2 loading or audio acceptance.
Do not start full T5 or alter capacities under this research Task.

Fresh native Cooker/Facade controls (2 tests), independent runtime-content
conformance and target preflash/source/fixture checks passed. Portal check passed
113 tests, 43 current pages, 10 source diagrams / 20 outputs and 44 built routes.
Staged ownership/document checks are completed before the documentation commit.
