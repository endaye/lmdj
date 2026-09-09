# T4 — ESP32-S3 Runtime Facade cross-compile and static budget probe

Authority: the user's 2026-09-09 instruction to begin B2 T4 after T3 merged.
CI scope/review publication repair belongs to another agent. Effective review
is deferred until that repair is available; no review takeover or merge is
inferred while this explicit hold applies.

## Scope and exact inputs

Source revision: `b24114f5082cbdd494bb599b49e6e6f2674da44b`, the fresh
`origin/main` at Task start, containing T1–T3. The source is referenced in place
from this isolated checkout, not copied or patched. No Product source change,
Host, firmware flashing, transport decision, device execution or CI repair.
Historical A/B1 probes and their failures remain untouched.

Declared repository files (one research Task, one Conventional Commit):

- `docs/plans/2026-09-09-esp32-runtime-probe-t4.md`
- `docs/research/2026-09-07-esp32-idf6-toolchain-and-atomics-amendment.md`

The external probe lives separately under
`/Users/endaye/esp/lmdj-spike/lmdj-runtime-probe-t4/`. Its bounded scaffold is
`CMakeLists.txt`, `sdkconfig.defaults`, `run-eim.sh`, `capture.py`,
`retain-symbols.py`, `analyze.py`, `check-evidence.py`, `inputs.json`, `main/CMakeLists.txt`,
`main/probe.cpp`, `main/sizes.cpp`, `main/atomic64-positive.cpp`, and one
`CMakeLists.txt` per declared archive in `components/`. Generated builds and
evidence are not product inputs or repository files. Evidence capture must
retain the exact scaffold, source/input hashes, tool identity, commands,
unfiltered output and real exit codes.

Use EIM-managed ESP-IDF v6.1
`fff9895c82d744c7237be8847347bdd1b07c6643`, Xtensa GCC 15.2.0
`esp-15.2.0_20251204`, ESP32-S3, Picolibc, `-Og`, `gnu++20`, no PSRAM/RTTI,
and the already established probe-local C++ exceptions requirement.
Core diagnostics remain `-Wall -Wextra -Wpedantic -Werror`, without inherited
warning exemptions. SDK-owned headers may be classified SYSTEM as in A;
product diagnostics cannot be suppressed. Configuration changes and any
failures are retained separately, never overwritten.

## Closure and evidence method

Audit the current CMake producer, not only an independent wrapper list.
`lmdj_runtime_facade` owns one source and depends on existing Audio Runtime and
Cooker targets; their declared closure is Foundation (3 sources), Domain (3),
Cooker (6), Audio Runtime (5), Facade (1): 18 total. Performance Runtime is a
separate T1 target, not a dependency of the T3 entry. Project IO, Provider SDK,
full Application and platform Hosts are not in this target closure.

The broad existing libraries still declare file-hash/WAV/offline sources.
Do not silently omit them or equate successful linker GC with target-level
isolation. Compile every declared source. Produce a full-retention image with
explicit per-object exported text roots and verify all roots in ELF; separately
produce an API-rooted image to distinguish declared library membership from
actual Runtime Facade reachability. Report any residual file/offline dependency
as a finding against B2's intended boundary, without repairing product code.

For each successful link preserve ELF/map/bin, compile commands and expanded
response files, roots, object/source inventory, section/region sizes and
per-archive attribution. Never fill missing final-link evidence using A/B1 or
intermediate object totals. A failed compile/link is a valid negative research
result, not a passing firmware build.

Analyze actual Facade render → Engine callback reachability and
`__atomic_*_8` references, distinguishing control-side and SDK paths. A separate
non-executed positive control must retain all nine 64-bit atomic helper families
used by A's counter check. Validate object inclusion before interpreting zeros;
report unresolved indirect-call limitations instead of claiming universal
absence of locks, allocation or IO from symbol absence alone.

Budget evidence separates static/map RAM, target-ABI fixed Engine/Facade
objects, compiler stack frames and dynamic preparation costs (input, PCM16,
float Bank, metadata and workspace). Use target types/debug info and the actual
Facade budget formula, not host `sizeof` as target evidence. Allocator overhead,
SDK task stacks, DMA, true heap peak/largest block and deadline remain unmeasured
without hardware. If fixed objects alone exceed device memory, stop before
runtime attempts and report a structural capacity blocker; do not shrink queues,
voice capacity or test budgets within this Task.

## Verification and completion boundary

Fresh native configure/build at the same source revision, then T1 performance
consumer/adapter/bridge/replay and Facade application controls; T2 Cooker
runtime-content and Facade export; T3 Facade component/quiescence/stress; Audio
Bank/Engine and existing value/queue/publication/FX controls including their
stress registrations. Record exact selected tests and counts after CMake
discovery. Do not reuse T3's earlier binaries as this revision's evidence.

Probe scripts receive syntax and positive/negative inventory checks; these are
local evidence integrity assertions, not new CI gates. Run docs_static,
relative-link/diff validation, staged ownership admission and
`scripts/docs-site.sh check` for documented source facts. No global required
check, timeout, coverage floor, selection or journey is weakened.

Commit the verified research record autonomously. Keep effective review and
merge pending the user's CI scope repair condition. No automatic cleanup,
release, public artifact upload or transition to T5.

## Version Management

Version impact: none
Reason: research and external non-distributed probe only; no Module, Contract,
Host, Product Assembly, Build, snapshot, tag or Channel allocation. Existing
T2/T3 staged allocation obligations are not changed by this experiment.

## Documentation Impact

Documentation impact: none
Reason: this records experimental cross-compile/budget evidence in the research
appendix, not supported ESP32 product capability or a current Portal boundary
change. Portal validation still checks documented source facts.

## Pitfall Impact

Pitfall impact: none. Producer-bound inventory, fresh rebuild, complete
retention and explicit negative-result guidance were applied. Fixed-object
capacity and stale host-test version expectations are source-derived findings,
not a new process/invariant ledger entry. Probe-only scaffolding/tool invocation
errors remain in raw evidence; no product or CI repair is included.

## Recorded outcome

See the research appendix §10. All 18 declared sources compile; full-retention
and Facade-API-rooted images link, with a separate nine-helper atomic positive
control. This is not a firmware/runtime PASS: target `RealtimeEngine` alone is
594,624 bytes, exceeding the no-PSRAM device's internal memory capacity; the
tiny golden fixture has a modeled admitted subtotal of 606,487 bytes before
platform reserve. The declared targets still include file/offline sources.
Fresh exact-source host controls are 21/22 PASS, with `facade.application`
failing its pre-existing hard-coded version expectation. No test was removed
or fixed within this research Task. Callback indirect-call, heap peak, hardware
stack and deadline evidence remain unmeasured. Effective review remains held
for the separately owned CI scope repair; T5 is not started.
