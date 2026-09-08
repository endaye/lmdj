# B2 T1 — isolate existing Performance ports and runtime implementation

Status: implementation Task authorized by the user's “继续下一步” after the B2
design delivery. This approves the compatible T1 refactor only, not T2–T5,
wire Contracts, device sessions, capacity choices or firmware work.
Base: `f12939974d2d0f0db48e10f63cf30f5406904855`.
Authority: [B2 design](../design/2026-09-08-lmdj-esp32-runtime-only-b2.md) §3 and
[candidate T1](2026-09-08-lmdj-esp32-runtime-only-b2.md).

## One Task, declared files

- `packages/application-facade/include/lmdj/facade/performance_ports.hpp` (new)
- `packages/application-facade/include/lmdj/facade/application.hpp`
- `packages/application-facade/include/lmdj/facade/performance_runtime.hpp`
- `packages/application-facade/include/lmdj/facade/performance_engine_adapter.hpp`
- `packages/application-facade/CMakeLists.txt`
- `tests/core/facade/performance_runtime_consumer_test.cpp` (new)
- `CMakeLists.txt` (register that executable in the existing coverage inventory)
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/diagrams/application-facade.architecture.json`
- `apps/docs-site/static/diagrams/application-facade.html` (generated)
- `apps/docs-site/static/diagrams/application-facade.svg` (generated)
- this plan

Move existing clock, sequencer, launch and gesture port declarations verbatim to
the new header. `application.hpp` includes it, retaining the old public include
entry point, namespace, signatures and configuration layout. Replay remains in
its existing header. Runtime/engine adapter headers include ports and replay
directly, not `application.hpp`.

Create `lmdj_performance_runtime` / `lmdj::performance_runtime` inside the same
Module. It owns the existing `performance_runtime.cpp`, `performance_replay.cpp`
and `performance_engine_adapter.cpp` exactly once. `lmdj_application` PUBLIC-links
it; existing callers retain the full target. Narrow bridge and adapter test
consumers link only the new target plus Threads. No business implementation,
threading algorithm, port semantics or target-wide warning exemption changes.

The new target still depends on Audio Runtime, Cooker, Authoring Domain and
Foundation. This is **Project IO / Provider SDK isolation**, not a complete
embedded dependency closure: lower archives still contain offline/file-related
objects, and the public engine adapter still takes Core types. Do not label it
an ESP32 Host API or a complete B2 runtime facade.

## Tests and red/green evidence

Baseline: build and run `facade.application`, `facade.performance_runtime_bridge`,
`facade.performance_engine_adapter`, `facade.performance_replay` and all three
`facade.sequence_surface` registrations before product edits.

New lowest-tier test: `facade.performance_runtime_consumer` (component) includes
the four narrow headers and links/calls all three implementation units' public
factories. Its compile-time negative controls reject visible Project IO or
Provider SDK include roots: accidentally relinking the full Facade cannot make
the consumer silently pass. Before introducing the split, build this consumer
against `lmdj::application` and retain the expected boundary diagnostic; after
the split it must build and run. Inspect generated link lines and compiler
dependency files too, not merely absent final symbols after linker GC.

Final Task verification:

- Configure/build dev; run every `facade.*` test and the new consumer.
- Build existing C API/dynamic-load and native/Web control consumers to catch
  complete-target transitive linkage regressions; run their registered tests.
- Run `scripts/core.sh coverage check` because a new instrumented test executable
  joins the root coverage inventory. Do not lower floors or omit any target.
- `python3 tests/build/ci_change_scope_test.py` after staging new files;
  `git diff --cached --check` and final committed file/status inspection.
- Regenerate the Facade diagram, then `scripts/docs-site.sh check`.

The consumer detects missing symbol ownership and leaked authoring-service
include/link dependencies. Its failure says why and remedy. No new CI workflow,
lane, coverage floor or stress budget; no concurrency implementation changes.
Existing admission/receipt/replay/stop/recovery journeys remain unchanged.
No new ESP-IDF build, live-device test or audio/deadline claim belongs to T1.

## Version Management

Version impact: none
Reason: internal source ownership and compatible header factoring within the
existing application-facade Module; every existing API/ABI signature and full
CMake target remains supported. The additional target is not an independently
versioned Module or newly shipped Package. Existing manifest version `3.1.0`
and api_version `2` remain unchanged; no Contract/Host/Provider/Assembly/Build
identity is allocated. A future public device API or independent package needs
its own version assessment. No tag, release, deployment or Channel change.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/
Reason: document the compatible header entry points and one-way link/source
ownership boundary, with the Facade source diagram in the same Task. Do not add
an implemented ESP32 Host or new Module identity to the portal. No Build snapshot
is allocated for this refactor.

## Pitfall Impact

Pitfall impact: none — existing coverage inventory guidance is applied by adding
the new executable to the root list. No qualifying process failure has occurred.
