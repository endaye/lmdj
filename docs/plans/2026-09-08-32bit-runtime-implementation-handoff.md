# 32-bit runtime: evidence and implementation handoff

Status: proposed next Task, not an approved implementation specification.
Date: 2026-09-08.

## Objective remains A → B1

The original render-kernel probe must compile and link its complete declared
closure, retain each translation unit, produce full build/map/size and atomic
attribution evidence, and settle the artifact filesystem/stack questions.
Only after independent Step A delivery may B1 probe the existing Facade surface.
No B2 Host, Contract or Embedded Runtime Profile is authorized.

The user subsequently selected a separate 32-bit concurrency design: retain
64-bit semantics, split synchronization by purpose, support multiple telemetry
readers, and permit their mutual exclusion without blocking audio. The user
also authorized version-controlled standalone prototypes in `demos/`.
Neither prototype output nor a local commit is an Engine implementation or
an authorization to change unresolved public concurrency semantics.

## Verified evidence at this handoff

| Requirement | Actual evidence | Still missing |
| --- | --- | --- |
| Original Step A unchanged-source build | Original `handoff.md`: 13/14 translation units compiled; realtime_engine.cpp rejected atomic64; exceptions-only probe-local adjustment retained | app ELF, full retained closure, map/size, final atomic and VFS resolution |
| Safe observation candidate | `demos/32bit-observation`: finite SC model, early-release negative control, C++ carry/reset/paused-reader/4-reader stress, host TSan | Complete Engine fields/lifecycle, arbitrary weak-memory executions and real target integration |
| Claim progress candidate | `demos/32bit-pattern-mailbox/model.py`: SC admission/no-admission comparison, empty/nonempty Q | Complete Q/A handoff, multiple claim rounds, every control writer and actual target protocol |
| Cancel/reclaim candidate | Same model: both cancel/activate winners, safe reuse, early-reclaim negative control | Full authority validation, queued cancel/replace, Voice retirement and all combined interleavings |
| Timing constraints | `boundary_test.py`: callback-start frontier and origin-before-clear counterexamples | Complete publication decision equivalence, overflow, retries and Engine regression execution |
| ESP32-S3 code generation | GCC 15.2.0 -O2/-Os standalone object compilation; S32C1I retry loops; atomic64 positive control | Linked libc implementation, SDK flags and memory placement; no real-time or hardware evidence |

Original probe source revision: `5eb314f52ea71c879a8a4e00f749135791c16879`.
Prototype product-code inspection baseline: `694b983b3a6b9de7be780d1399072b9b2afdf5cc`.
Prototype commits: `8aa1d6a7`, `470fbd48`, `bbb5700a`, `8f8e74af`.
Those commits are local evidence, not merged-product or release evidence.

## Proposed implementation sequence and stop conditions

1. Close the design, before changing Core. Combine Q/A/slot ownership and
   admission; cover queued replacement/cancel, in-flight CAS across reuse,
   full generation/Pattern identity/activation authority, and cancel versus
   activation. Give every ordinary payload access an owner/lifetime and every
   transfer its release/acquire edge. Keep frame-frontier publication at its
   original callback-start point; publish new origin before clearing A.
   Review all fifty atomic64 fields, bounded reservations/rollback, start/stop
   writer handoff and every public return path. Do not infer full correctness
   from the independent finite models or approve a protocol merely to proceed.
2. In a separately authorized isolated Core Task, implement private observation
   and Transport channels, bounded atomic32 counters, and the approved Pattern
   protocol. Audio cannot acquire reader locks, allocate/free, wait for control,
   or destroy banks. Keep 64-bit generations/epochs and exhaustion behavior.
   Non-realtime readers copy values and never borrow actual PatternSlot payload.
   Proposed product areas: audio-runtime header/source and private protocol
   helpers, audio unit/component/stress tests, and affected documentation-site
   pages. The implementation plan must name exact files before edits.
3. Validate complete Engine journeys, not just primitives: publish → claim →
   replace/cancel → activate → retire → reclaim → same-slot reuse, with
   observable assertions after every transition. Exercise multiple readers,
   paused owners, no-next-callback final values, reset and exhaustion; preserve
   existing claim-boundary/apply-point tests and all audio stress coverage.
   Run the approved Core unit/component suite, explicit stress and supported
   sanitizer configurations. Any unsupported runtime is a gap, not PASS.
4. Rebuild Step A only after the separate source repair is delivered at the
   required boundary. Preserve original logs/cache and create a fresh build
   using the verified EIM installation. Fix probe-local retained symbol roots,
   inherited warning exemptions and declared wrapper layout. Retain render and
   describe_artifact without executing them or constructing an engine before
   heap reporting. Recheck the plan's remaining dependency/override obligations.
   Save full build logs, ELF/map, size reports and exact source/toolchain identity.
5. Reconcile atomic evidence with the intentionally changed source. The original
   plan's zero-atomic64 distrust rule must not be silently dropped: demonstrate
   complete retained closure and a positive control, distinguish old unchanged-
   source expectations from new protocol evidence, and obtain any necessary
   plan amendment. Independently settle filesystem/ifstream, 64-KiB stack
   retention and VFS/Picolibc symbol resolution. Rerun the named 7+4 host tests
   on the final source revision. No deadline/jitter/underrun or audio claim.
6. Deliver Step A independently under applicable push/PR/merge authority, then
   start B1 from that delivered baseline. Do not stack B1 on an undelivered A or
   alter Facade/Contract design to make it compile.

## Current stop boundary

Further product-source implementation requires the user's explicit authority
for the separate Core Task. Design closure remains a prerequisite even if that
authority is granted. Do not disable the atomic64 lock-free assertion, emulate
it using a global lock, truncate identities, weaken tests, or call the original
goal complete based on these prototypes. Original design draft and failure
evidence remain untouched.

## Verification of this handoff Task

Declared file: this document only. Verify cited local commits, original probe
handoff and current product source; run staged ownership and whitespace checks.
No product tests or target builds are claimed by this documentation-only commit.

## Version Management

Version impact: none
Reason: this Task records evidence and proposed boundaries only. The future
Core Task must evaluate API/threading guarantees and ABI/layout changes under
Module SemVer; it may not inherit this none declaration.

## Documentation Impact

Documentation impact: none
Reason: no current product support claim or documentation-site page changes.
Future Engine implementation requires current audio-runtime and affected Host
concurrency documentation plus the documentation-site check.
