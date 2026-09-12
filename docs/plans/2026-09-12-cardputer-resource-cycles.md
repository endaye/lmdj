# Cardputer resource cycle ledger

Relates to #1104 and #1111. This Task records identity-bound resource samples
for the pending device observation journey; it does not claim a capacity,
leak, stack, or physical acceptance result.

## Scope

- `apps/cardputer-host/main/resource_observation.hpp`
- `apps/cardputer-host/main/runtime_host.hpp`
- `apps/cardputer-host/main/runtime_host.cpp`
- `tests/platform/cardputer/resource_observation_test.cpp`
- `tests/platform/cardputer/CMakeLists.txt`
- `apps/docs-site/docs/hosts/cardputer-host.mdx`
- this plan

`ResourceCycleLedger` is a fixed 100-record control-owner accumulator. A
record begins before a successful content load, is bound to the published
content SHA-256 and byte length only after load validation, and completes only
after the corresponding stop and unload succeed. Samples supplied after load,
after audio start, after stop/join, and at unload are folded into per-heap free
and largest-block minima and caller/audio stack high-water minima. The initial
free values and SDK low-water minima remain in each record so a later report
can derive the observed allocation peak, including a transient allocation
between two control samples, without treating overlapping heap capability
classes as additive.

The ESP Host allocates the bounded ledger once during Host construction rather
than placing its records on the `app_main` control-task stack. This setup
allocation is part of the Host resource cost and is reclaimed only after the
normal audio/platform shutdown boundary.

Failed loads are explicitly aborted. A full ledger increments `dropped_cycles`
and does not overwrite an earlier record. An unbound or active record is never
published as a completed journey. Sampling is serialized with the Host control
owner and never runs in render code or an ISR; all SDK heap observations remain
sequential and non-atomic.

`RuntimeHost::read_resource_cycles` copies the caller-owned report for a future
reviewed observation transport. It does not add a wire opcode, alter the
legacy STATUS payload, or publish a Contract. Device allocator locking,
FreeRTOS stack reclamation, 30-minute combined-load stability, actual voice
capacity, physical latency, and all A1 far-side assertions remain pending.

## Verification

The resource component target runs the existing sampler vectors plus ledger
identity/minimum folding, explicit abort, and exact 100-record capacity cases.
The test uses deterministic API samples only; it does not substitute for
target allocator, scheduler, DMA, or physical measurements. Rebuild the
existing Cardputer Host consumers, run native and ASan/UBSan component lanes,
the pinned EIM Host build, ownership, and the complete Portal check before
shipping.

## Version Management

Version impact: none. This is internal Host measurement plumbing; no Module,
Contract, Assembly, Product Build, or release identity changes. A later
distribution Task must bind the reviewed observation transport to exact
identities before allocating a Build snapshot.

## Documentation Impact

Documentation impact: required — `/hosts/cardputer-host/` documents the fixed
cycle ledger, identity binding, explicit failure/drop accounting, and the
remaining device-measurement boundary.
