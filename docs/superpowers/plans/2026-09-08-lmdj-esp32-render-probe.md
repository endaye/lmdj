# ESP32 render-path compile probe, then a Facade surface: A → B

Base: `71bc885dbe5dc083b094fb79fcdcdccadfcd5071`.
Task branch: `docs/esp32-render-probe-plan` (this plan); implementation Tasks open their own `feat/esp32-render-probe-*` branches.
Status: plan only. Nothing here is a Host, a Product Assembly change, an Embedded Runtime Profile, a Contract, or a hardware SKU decision. Design authority is
[the Core redesign spec](../specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md),
[the 2026-08-27 feasibility assessment](../../research/2026-08-27-esp32-core-feasibility-assessment.md)
and its [2026-09-07 amendment](../../research/2026-09-07-esp32-idf6-toolchain-and-atomics-amendment.md).

## Why this order

Everything measured so far answers "is the platform usable": ESP-IDF v6.1 pinned
and verified against its tag commit; M5GFX 0.2.28 runs on it behind one vendored
line (M5GFX#278) with a two-way-verified smoke gate; Cardputer Adv identifies
itself, paints, and plays int16 PCM through the ES8311 at 48 kHz; the board has
no PSRAM so the 32-bit atomic path is hardware S32C1I. Nothing yet answers
"does our code go on it". Assessment §10.2 lists ten spike proofs; the first
three — cross-compile a chosen subset, report the linker map and `idf.py size`,
make the 64-bit atomic blocker visible without weakening the real-time
contract — need no product decision and no audio output. That is Step A.
Step B adds the Facade surface §8 asks for, and it is second because it pulls
`lmdj_application` whole, and a failure there must be attributable to the
Facade layer rather than to the render kernel underneath it.

## Step A — render kernel compile probe

### Declared subset

Compiled, from the repository tree (not copied), as one ESP-IDF component:

| Module | Files | Role |
| --- | --- | --- |
| `packages/audio-runtime` | `include/lmdj/audio/{mix_math,master_fx,prepared_sample_bank,realtime_engine,runtime_preparation_limits}.hpp`, `src/{master_fx,prepared_sample_bank,realtime_engine}.cpp`, `src/pattern_generation.hpp` | render kernel, ~4.0k LOC |
| `packages/project-cooker` | all | PUBLIC dependency of audio-runtime |
| `packages/authoring-domain` | all | PUBLIC dependency of project-cooker |
| `packages/foundation` | all | PUBLIC dependency of everything above |
| `third_party` | nlohmann_json (PUBLIC of foundation), picosha2 (PRIVATE of foundation) | as linked today |

Excluded on purpose: `offline_renderer.{hpp,cpp}`, `wav_writer.{hpp,cpp}`
(offline tools; the only `std::filesystem`/`<fstream>` users in audio-runtime),
`src/apple/`, `src/web/`, every Host, every Facade file, `project-io`,
`provider-sdk`, `web-runtime-platform`. The dependency chain above is the whole
transitive closure of the render kernel; nothing else is reachable from it.

### Declared files (one reviewable Task)

- `~/esp/lmdj-spike/lmdj-render-probe/` is a **local spike project outside the
  repository**, like the three bring-up projects before it. It carries
  `CMakeLists.txt`, `main/`, `sdkconfig.defaults`, a component wrapper whose
  `EXTRA_COMPONENT_DIRS` / `idf_component_register(SRCS …)` names the files in
  the table by absolute path into a checkout of this repository at a recorded
  commit, and the same `override_path` to the vendored M5GFX the other projects
  share.
- In the repository, Step A touches **only** `docs/`: results land in the
  2026-09-07 amendment as a new section and, if they overturn a band, in the
  2026-08-27 assessment with a header pointer. No `packages/`, `apps/`,
  `products/`, `CMakeLists.txt` or `cmake/` file changes in Step A. If the probe
  needs a source change to compile, that change is a separate `fix/` or `feat/`
  Task with its own tests, never smuggled into the probe.

### Mechanism

1. **Toolchain.** ESP-IDF v6.1 (`fff9895c`), `xtensa-esp-elf-gcc` 15.2.0,
   target `esp32s3`, the same install the amendment §4 records. The component
   sets `-std=gnu++20` on its own sources via `target_compile_options`; IDF 6's
   `gnu++26` default is not adopted. `-Wall -Wextra -Wpedantic -Werror` stay as
   `cmake/LmdjWarnings.cmake` already applies them on hosts, so warnings-as-
   errors is not new discipline for these files; what is new is the xtensa ABI
   (`int32_t` is `long`, amendment §1.2) and any gnu++26-only diagnostic that
   leaks through.
2. **`sdkconfig.defaults`.** Same as the bring-up projects: 8 MB flash, single
   large app partition, USB-Serial/JTAG console, no certificate bundle. No
   `CONFIG_SPIRAM` — Cardputer Adv has none, and §2.2 of the amendment says the
   32-bit atomic path stays hardware S32C1I exactly because of that.
3. **`main/`** is a stub that references one symbol from each compiled object
   (e.g. constructs a `RealtimeEngine` with default limits and calls nothing
   real-time), so the linker keeps the subset instead of discarding it. It does
   not start I2S, does not play, does not measure. It prints `esp_get_idf_version()`,
   `__cplusplus`, and the four heap figures the bring-up already prints, then
   idles. That is the whole runtime behavior of Step A.
4. **Evidence capture.** `idf.py build` log (full, unfiltered — the session's
   pitfall: filtering a command's output discards its failure signal),
   `idf.py size` and `idf.py size-components`, and `build/*.map`. From the map,
   two mechanical counts:
   - references to `__atomic_load_8`, `__atomic_store_8`, `__atomic_exchange_8`,
     `__atomic_compare_exchange_8`, `__atomic_fetch_*_8` resolved from
     `esp_libc` — every one is a 64-bit atomic that compiled silently onto the
     global `portMUX` spinlock (amendment §2.1). The 50 `std::atomic<std::uint64_t>`
     members at `realtime_engine.hpp:517–578` are the expected source; the count
     is the §10.2 item-3 instrument, because on Xtensa the build **passes** and
     nothing else reports the degradation;
   - IRAM occupancy attributed by archive, because the 240×135 display demo
     alone already reported IRAM 16384/16384 and the render kernel is what will
     want IRAM next.
5. **Host-side control.** Before and after any source change the probe needs,
   the same subset's host tests must pass on macOS: `audio.realtime_queue`
   (unit); `audio.prepared_sample_bank`, `audio.realtime_engine`,
   `audio.snapshot_publication_invariant`, `audio.master_fx`,
   `audio.master_fx_determinism`, `audio.master_fx_allocation_guard`
   (component); and, because the atomic layout is exactly what §3 says must
   change, the four stress suites `audio.realtime_spsc_stress`,
   `audio.snapshot_publication_stress`, `audio.long_sample_publication_stress`,
   `audio.master_fx_stress` via `scripts/core.sh test dev stress`. `full` does not
   run them.

### What Step A must report

- Build verdict per file: compiled unchanged / compiled with a probe-local flag /
  needs a source change (listed as a follow-up Task, not made here).
- `idf.py size` totals and the per-archive breakdown for the five libraries.
- The `__atomic_*_8` reference count and the symbols that pull them in.
- Whether `foundation/src/artifact.cpp` (`std::filesystem::is_regular_file`,
  `std::ifstream`, 64 KiB stack buffer) compiles and links under Picolibc, and
  which of its calls resolve to IDF VFS. This is the first data on the
  amendment §5 item "Picolibc and `std::filesystem` untouched".
- Nothing about timing, underrun, voices or audio. Step A produces no such
  numbers, and the report says so in the same words as the bring-up projects.

### Stop conditions for A

- A file needs a change that alters behavior on hosts → stop, open the `fix/`
  Task, run the host control suite, then resume.
- The `__atomic_*_8` count is zero → suspect the map or the probe, not the
  code: `realtime_engine.hpp` declares 50 such members and at least the
  telemetry stores must appear.
- The component compiles only with `-std=gnu++26` → record why; do not move the
  Core's standard in a spike.

## Step B — Facade embedded surface

### Declared subset

Step A's subset plus `packages/application-facade/{include/lmdj/facade/performance_runtime.hpp,
include/lmdj/facade/performance_engine_adapter.hpp, src/performance_runtime.cpp,
src/performance_engine_adapter.cpp}` (1,306 LOC), the shape §8 of the
assessment names "Application Facade embedded runtime surface".

### Known cost, stated before starting

Those four files include `lmdj/facade/application.hpp`, which includes
`project_io/soundset_store.hpp`, `project_io/soundset_catalog_transport.hpp`,
`provider/registry.hpp`, `provider/attempt_store.hpp`, and `lmdj_application`
PUBLIC-links `project_io` and `provider_sdk`. `project_io` alone is 17.4k LOC
with `std::filesystem` in 15 files and `<thread>`/`<mutex>` in 5. So B has two
honest forms:

- **B1 — as-is:** compile `lmdj_application`, `project_io`, `provider_sdk`
  under IDF too, and let the map show what they cost. Cheap to attempt, likely
  to fail on filesystem/thread use, and the failure list is itself the deliverable.
- **B2 — carve:** an embedded surface that does not include `application.hpp`.
  That is the "Embedded Runtime Profile" of §8 and the new runtime Artifact /
  transport Contract it implies. **That is a product-level Contract question**
  ([open-questions](../../prd/open-questions.md); assessment §11) and this plan
  does not settle it. B2 is not authorized here; B1 is.

### Mechanism and evidence

Same as A, plus: the Facade files must compile with the Core's invariants intact
— Hosts use the Facade, Hosts do not parse Project bundles, Runtime Snapshot is
never persisted as Project Truth. The stub `main/` still starts nothing. The
report adds the archive breakdown for the three new libraries and the list of
`project_io` / `provider_sdk` symbols that fail or need VFS.

### Stop conditions for B

- B1 needs a Contract, an Artifact schema or a Host to proceed → stop; that is
  B2, which needs a product decision first.
- Any change to `packages/application-facade` to make B compile → its own
  `feat/` Task with Facade tests, never in the probe.

## Explicit non-goals

No Host. No I2S from the Core. No Provider. No Project IO on device. No local
Cook. No new Contract, Artifact, Channel or version identity. No change to the
Core's C++ standard. No claim about callback deadline, jitter, underrun, voice
count or memory budget — assessment §10.2 items 4–10 remain open, and the
Cardputer Adv cannot serve item 4 (no PSRAM). Microphone capture stays blocked
on esp-idf#18621 and is not on this path.

## Verification and handoff

Step A is done when the build log, size report, map counts and the artifact.cpp
verdict are recorded in the amendment and the host control suite (unit,
component, and the four stress suites) passes at the same repository commit the
probe compiled. Step B is done when the same holds for B1 or B1 has stopped on a
named product question. Each step is one `docs/` Task for the record, plus any
`fix/`/`feat/` Tasks it discovered, shipped separately under `issue-done` §5
(review the exact head, then merge; no `--auto`, no `merge:queue`).

## Version Management

Version impact: none — a local spike project outside the repository and
research documentation inside it. No Product Build, Core Module, Host,
Provider, Contract or Assembly identity changes. Any source change the probe
reveals is a separate Task with its own version declaration.

## Documentation impact

Documentation impact: none — no portal pages, diagrams, projected identities,
product behavior or release policy change. Results go to `docs/research/`.

Pitfall impact: none — the process lesson this spike already taught
(`unpinned-upstream-citation-read-as-decision`) is in the ledger; the
"filtered output discards the failure signal" lesson is written into the
mechanism above as an unfiltered-log requirement rather than as a new entry.
