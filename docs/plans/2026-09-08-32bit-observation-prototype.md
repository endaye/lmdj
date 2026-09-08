# Standalone 32-bit observation protocol prototype

## Scope

Deliver the first reproducible experiment for the user-selected direction:
preserve 64-bit semantics, serialize non-realtime readers, and never acquire
their mutex from the single publisher. This is an independent demo, not Core
implementation authorization or ESP32 support evidence. The existing uncommitted
design draft and Step A failure evidence remain untouched.

Declared files: `demos/README.md`, this plan, and
`demos/32bit-observation/{README.md,triple_buffer.hpp,test.cpp,model.py,run.sh}`.
No product imports, product build registration, new CI gate or manifest changes.

## Verification

- Finite SC model: split payload writes/reads and atomic role exchanges;
  reject torn snapshots and check final-value visibility after publisher stop.
- C++ deterministic tests: low-word carry, stale writer-slot reuse, paused
  reader with continued publishing, reader-held reset, and synchronized writer
  handoff. Test synchronization is harness-only, never on the publisher path.
- C++ stress: four concurrent readers, complete-value integrity, per-reader
  monotonicity within one epoch and exact final snapshot after join.
- Run normal and ThreadSanitizer variants when available; report unavailable
  sanitizer execution as a gap. These tests do not replace Core stress tests.
- Stage exact files; run tracked-path ownership and active-tree checks.

## Version Management

Version impact: none
Reason: standalone experimental code; no Product, Module, Provider, Host or
Contract API/ABI/version changes.

## Documentation Impact

Documentation impact: none
Reason: no current product support or behavior claim; only the demo index and
local experiment instructions change, not current documentation-site pages.

## Remaining design work

Pattern claim/admission, cancel/activate/reclaim, Transport timing, cross-domain
Pattern telemetry composition, Engine integration, and EIM-managed ESP32-S3
object-code/progress analysis remain separate steps. An exchange call and a
host lock-free assertion are not a target wait-free/deadline proof.
