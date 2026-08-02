# Native Realtime CoreAudio Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and physically validate a product-neutral, allocation-free realtime one-shot engine, an Apple Default Output Audio Unit adapter, and an Apple-only diagnostic probe without creating a formal Product Host.

**Architecture:** A fixed-capacity SPSC queue transfers validated triggers from one control producer to one audio consumer. `packages/audio-runtime` owns immutable stopped-time sample storage, a preallocated 128-voice mixer, atomic telemetry, and an Apple-only CoreAudio adapter; an unregistered test probe drives that package directly and never reads Project Truth or calls the Application Facade.

**Tech Stack:** C++20, CMake 3.24+, CTest, `std::atomic`, Apple AudioUnit/CoreAudio APIs, Python 3.11 standard library, nlohmann/json through Foundation.

## Global Constraints

- Work only on `feat/native-realtime-host` in `/Users/endaye/Projects/lmdj/.worktrees/native-realtime-host`; never edit `main` or the retained Web worktree.
- Internal audio format is exactly 48,000 Hz, mono float32 samples, and two-channel non-interleaved float32 output.
- Sample Bank capacity is 64; Trigger Queue accepts exactly 1,024 events; Voice Pool capacity is 128.
- `TriggerEvent` is exactly `{std::uint64_t sequence, std::uint8_t slot, std::uint8_t velocity}`; valid values satisfy `slot < 64` and `1 <= velocity <= 127`.
- The producer and lifecycle caller are the same serialized control thread in 5A; the render callback is the sole consumer.
- `RealtimeEngine::stop` is called only after the consumer callback is quiescent; `CoreAudioOutput` must establish that condition before clearing Queue or Voice storage.
- The render callback performs no lock, allocation, deallocation, filesystem/network/Project/Provider I/O, JSON, logging, locale work, exception propagation, or Application Facade call.
- Samples may be loaded or cleared only while stopped; their storage is immutable while running and persists across stop/start.
- Events have no callback-relative frame offset in 5A and begin at frame 0 of the callback that dequeues them.
- No voice stealing: a full pool increments `voice_drops`; output is clamped to `[-1.0F, 1.0F]`.
- The CoreAudio target and probe exist only under `APPLE`; non-Apple builds have neither an adapter target nor a success stub.
- A CoreAudio cleanup failure that cannot prove callback termination enters terminal `failed`, preserves Engine/Sample storage, rejects restart, and makes the Probe flush its error then call `std::_Exit(2)` without unsafe stack unwinding.
- The probe is a platform test artifact, not an `apps/` Host, not an Assembly host, and not a Project-bundle parser.
- Existing retired contracts remain forbidden; no Contract, Provider, Project Truth, Facade API, C ABI, or MCP protocol shape changes.
- CTest `stress` remains excluded from `scripts/core.sh proof` through `-LE '^stress$'`.
- Safari Pointer remains failed against the approved p95; Chrome Pointer/MIDI and iPad Touch/lifecycle remain deferred and unverified.
- Each Task is one independently reviewed Conventional Commit with exact-file staging; this plan authorizes no push, PR, merge, tag, release, deployment, or Channel promotion.

## File Map

- `packages/audio-runtime/include/lmdj/audio/detail/fixed_spsc_queue.hpp`: header-only, fixed-capacity, lock-free SPSC transport.
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`: public realtime event, lifecycle, telemetry, and render API.
- `packages/audio-runtime/src/realtime_engine.cpp`: stopped-time sample ownership, queue/voice reset, render mixer, and atomic counters.
- `packages/audio-runtime/include/lmdj/audio/apple/coreaudio_output.hpp`: Apple-only public output adapter with a PIMPL boundary.
- `packages/audio-runtime/src/apple/coreaudio_services.hpp`: private injectable Audio Unit and monotonic-clock operations.
- `packages/audio-runtime/src/apple/coreaudio_services.cpp`: real Apple framework calls and structured OSStatus errors.
- `packages/audio-runtime/src/apple/coreaudio_output_state.hpp`: private testable lifecycle/callback state machine.
- `packages/audio-runtime/src/apple/coreaudio_output.cpp`: public adapter PIMPL and realtime callbacks.
- `tests/core/audio/fixed_spsc_queue_test.cpp`: exact 1,024-element boundary and FIFO unit test.
- `tests/core/audio/realtime_engine_test.cpp`: lifecycle, mixing, telemetry, and allocation component tests.
- `tests/core/audio/realtime_engine_stress_test.cpp`: producer/consumer concurrency test registered only as `stress`.
- `tests/core/audio/coreaudio_output_test.cpp`: fake-services state-machine, callback, overload, and deadline tests on macOS.
- `tests/platform/audio/native_audio_probe.cpp`: Apple-only stdin probe and deterministic no-device driver.
- `tests/platform/audio/native_audio_probe_smoke.py`: black-box CLI protocol and telemetry assertions.
- `packages/audio-runtime/CMakeLists.txt`: neutral, stress, Apple, and probe targets.
- `CMakeLists.txt`: coverage-object registration for non-stress native test executables.
- Version/Assembly files listed in Task 6: exact dependency and Product Build identities only.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

| Domain | Current | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.9.0` | `1.0.10.0` | Adds an Assembly-listed `audio-runtime` capability and Apple native verification artifact. |
| `audio-runtime` | `0.1.0`, API 1 | `0.2.0`, API 1 | Backward-compatible public realtime Engine and Apple output capability. |
| `application-facade` | `1.0.0`, API 2 | `1.0.1`, API 2 | Exact `audio-runtime` dependency changes to `0.2.0`; Facade behavior is unchanged. |
| `core-cli` | `1.0.0`, API 2 | `1.0.1`, API 2 | Exact Facade dependency changes to `1.0.1`; CLI behavior is unchanged. |
| `core-mcp` | `1.0.0`, API 2 | `1.0.1`, API 2 | Exact Facade dependency and Python package identity change to `1.0.1`; MCP behavior is unchanged. |
| Contracts | unchanged | unchanged | No wire, persistence, C ABI, error-code, Project, or Assembly schema change. |
| Providers / Models | unchanged | unchanged | No Provider code, Capability, model, or rule identity change. |

- Product candidate identity is `1.0.10.0 · canary · g<short-sha>`.
- Update `version.json`, all affected `module.json` files, MCP Python package identity, Assembly source/compiled identity, Product README, version assertions, `scripts/core.sh` Proof output, and the generated lock.
- Contract and Project compatibility is unchanged; no migration or old-bundle rewrite is allowed.
- Future tags are `module/audio-runtime/v0.2.0`, `module/application-facade/v1.0.1`, `module/core-cli/v1.0.1`, `module/core-mcp/v1.0.1`, and signed Product tag `lmdj-v1.0.10.0`.
- Tags may point only to the eventual `main` merge commit after macOS, Ubuntu, ASan, coverage, Proof, physical CoreAudio acceptance, and matching Build Manifest checks; this plan does not authorize creating or pushing them.
- Rollback reuses immutable Product Build `1.0.9.0`; no version number is reused.

---

### Task 1: Add the exact-capacity SPSC queue

**Files:**

- Create: `packages/audio-runtime/include/lmdj/audio/detail/fixed_spsc_queue.hpp`
- Create: `tests/core/audio/fixed_spsc_queue_test.cpp`
- Modify: `packages/audio-runtime/CMakeLists.txt`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: one producer thread, one consumer thread, and trivially copyable event values.
- Produces: `detail::FixedSpscQueue<T, Capacity>` with `try_push`, `try_pop`, `size_approx`, `clear_quiescent`, and `capacity`.

- [ ] **Step 1: Register a failing queue unit test**

Add this target inside the existing `BUILD_TESTING` block and append it to
`lmdj_coverage_targets` in the root coverage block:

```cmake
add_executable(
  lmdj_audio_realtime_queue_tests
  "${CMAKE_SOURCE_DIR}/tests/core/audio/fixed_spsc_queue_test.cpp"
)
target_include_directories(
  lmdj_audio_realtime_queue_tests PRIVATE "${CMAKE_SOURCE_DIR}"
)
target_link_libraries(
  lmdj_audio_realtime_queue_tests PRIVATE lmdj::audio_runtime
)
lmdj_target_warnings(lmdj_audio_realtime_queue_tests)
lmdj_target_sanitizers(lmdj_audio_realtime_queue_tests)
lmdj_add_test(
  NAME audio.realtime_queue
  TIER unit
  COMMAND lmdj_audio_realtime_queue_tests
  LABELS audio concurrency
)
```

The test body must prove all 1,024 slots are usable and preserve FIFO:

```cpp
#include <lmdj/audio/detail/fixed_spsc_queue.hpp>

#include <cstdint>
#include "tests/core/support/test.hpp"

namespace {
struct Event {
  std::uint64_t sequence;
};

void exact_capacity_and_fifo() {
  lmdj::audio::detail::FixedSpscQueue<Event, 1024> queue;
  static_assert(decltype(queue)::capacity() == 1024);
  for (std::uint64_t sequence = 0; sequence < 1024; ++sequence) {
    LMDJ_CHECK(queue.try_push(Event{sequence}));
  }
  LMDJ_CHECK(!queue.try_push(Event{1024}));
  LMDJ_CHECK(queue.size_approx() == 1024);
  for (std::uint64_t sequence = 0; sequence < 1024; ++sequence) {
    Event event{};
    LMDJ_CHECK(queue.try_pop(event));
    LMDJ_CHECK(event.sequence == sequence);
  }
  Event event{};
  LMDJ_CHECK(!queue.try_pop(event));
  LMDJ_CHECK(queue.size_approx() == 0);
}

void clear_requires_quiescence_and_reports_count() {
  lmdj::audio::detail::FixedSpscQueue<Event, 4> queue;
  LMDJ_CHECK(queue.try_push(Event{1}));
  LMDJ_CHECK(queue.try_push(Event{2}));
  LMDJ_CHECK(queue.clear_quiescent() == 2);
  LMDJ_CHECK(queue.size_approx() == 0);
}
}  // namespace

int main() {
  exact_capacity_and_fifo();
  clear_requires_quiescence_and_reports_count();
}
```

- [ ] **Step 2: Run RED**

```bash
scripts/core.sh configure dev
cmake --build build/core/dev --target lmdj_audio_realtime_queue_tests
```

Expected: compilation fails because `fixed_spsc_queue.hpp` does not exist.

- [ ] **Step 3: Implement the queue with acquire/release ownership**

Use `Capacity + 1` internal cells so the advertised capacity remains exactly usable:

```cpp
#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <type_traits>

namespace lmdj::audio::detail {

template <typename T, std::size_t Capacity>
class FixedSpscQueue {
  static_assert(Capacity > 0);
  static_assert(std::is_trivially_copyable_v<T>);
  static_assert(std::atomic<std::size_t>::is_always_lock_free);

 public:
  static consteval std::size_t capacity() noexcept { return Capacity; }

  bool try_push(const T& value) noexcept {
    const auto write = write_.load(std::memory_order_relaxed);
    const auto next = increment(write);
    if (next == read_.load(std::memory_order_acquire)) {
      return false;
    }
    cells_[write] = value;
    write_.store(next, std::memory_order_release);
    return true;
  }

  bool try_pop(T& value) noexcept {
    const auto read = read_.load(std::memory_order_relaxed);
    if (read == write_.load(std::memory_order_acquire)) {
      return false;
    }
    value = cells_[read];
    read_.store(increment(read), std::memory_order_release);
    return true;
  }

  std::size_t size_approx() const noexcept {
    const auto read = read_.load(std::memory_order_acquire);
    const auto write = write_.load(std::memory_order_acquire);
    return write >= read ? write - read : kStorage - read + write;
  }

  std::size_t clear_quiescent() noexcept {
    const auto count = size_approx();
    read_.store(write_.load(std::memory_order_relaxed),
                std::memory_order_release);
    return count;
  }

 private:
  static constexpr std::size_t kStorage = Capacity + 1;
  static constexpr std::size_t increment(std::size_t value) noexcept {
    return value + 1 == kStorage ? 0 : value + 1;
  }

  std::array<T, kStorage> cells_{};
  alignas(64) std::atomic<std::size_t> read_{0};
  alignas(64) std::atomic<std::size_t> write_{0};
};

}  // namespace lmdj::audio::detail
```

- [ ] **Step 4: Run GREEN and taxonomy checks**

```bash
cmake --build build/core/dev --target lmdj_audio_realtime_queue_tests
ctest --test-dir build/core/dev --output-on-failure -R '^audio\.realtime_queue$'
python3 tests/build/test_test_taxonomy.py build/core/dev
```

Expected: queue test and taxonomy pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add packages/audio-runtime/include/lmdj/audio/detail/fixed_spsc_queue.hpp \
  tests/core/audio/fixed_spsc_queue_test.cpp \
  packages/audio-runtime/CMakeLists.txt CMakeLists.txt
git diff --cached --check
git commit -m "feat(audio): add fixed-capacity SPSC trigger queue"
```

### Task 2: Add the realtime sample and voice engine

**Files:**

- Create: `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- Create: `packages/audio-runtime/src/realtime_engine.cpp`
- Create: `tests/core/audio/realtime_engine_test.cpp`
- Modify: `packages/audio-runtime/CMakeLists.txt`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `detail::FixedSpscQueue<TriggerEvent, 1024>` from Task 1 and stopped-time mono float32 PCM.
- Produces: `RealtimeEngine::load_sample`, `clear_sample`, `start`, `stop`, `enqueue`, `render`, and `telemetry` with the exact types below.

- [ ] **Step 1: Define the public API and write failing component tests**

Use this public shape; `sample_unavailable` covers empty or cleared slots and increments `invalid_events`:

```cpp
#pragma once

#include <cstddef>
#include <cstdint>
#include <span>

#include <lmdj/foundation/error.hpp>

namespace lmdj::audio {

inline constexpr std::uint32_t kRealtimeSampleRate = 48'000;
inline constexpr std::uint16_t kRealtimeChannels = 2;
inline constexpr std::size_t kRealtimeSampleSlots = 64;
inline constexpr std::size_t kRealtimeQueueCapacity = 1'024;
inline constexpr std::size_t kRealtimeVoiceCapacity = 128;

enum class RealtimeState : std::uint8_t { stopped, running };
enum class EnqueueResult : std::uint8_t {
  accepted,
  invalid_slot,
  invalid_velocity,
  sample_unavailable,
  not_running,
  queue_full,
};

struct TriggerEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
};

struct RealtimeTelemetry {
  RealtimeState state;
  std::uint64_t enqueued_events;
  std::uint64_t dequeued_events;
  std::uint64_t queued_events;
  std::uint64_t cancelled_events;
  std::uint64_t started_voices;
  std::uint64_t completed_voices;
  std::uint64_t active_voices;
  std::uint64_t cancelled_voices;
  std::uint64_t invalid_events;
  std::uint64_t stopped_rejections;
  std::uint64_t queue_drops;
  std::uint64_t voice_drops;
  std::uint64_t callback_count;
  std::uint64_t rendered_frames;
  std::uint64_t max_callback_frames;
};

class RealtimeEngine final {
 public:
  foundation::Result<void> load_sample(
      std::uint8_t slot, std::span<const float> mono_pcm);
  foundation::Result<void> clear_sample(std::uint8_t slot);
  foundation::Result<void> start();
  void stop() noexcept;
  EnqueueResult enqueue(TriggerEvent event) noexcept;
  void render(float* left, float* right, std::uint32_t frames) noexcept;
  RealtimeTelemetry telemetry() const noexcept;
};

}  // namespace lmdj::audio
```

Create separate test functions with these exact observations:

```cpp
RealtimeEngine engine;
const std::array<float, 2> sample{0.5F, -0.5F};
LMDJ_CHECK(engine.load_sample(0, sample).has_value());
LMDJ_CHECK(engine.start().has_value());
LMDJ_CHECK(engine.enqueue(TriggerEvent{9, 0, 127}) ==
           EnqueueResult::accepted);

std::array<float, 1> left{};
std::array<float, 1> right{};
engine.render(left.data(), right.data(), 1);
LMDJ_CHECK(left[0] == 0.5F && right[0] == 0.5F);
engine.render(left.data(), right.data(), 1);
LMDJ_CHECK(left[0] == -0.5F && right[0] == -0.5F);

const auto telemetry = engine.telemetry();
LMDJ_CHECK(telemetry.enqueued_events == 1);
LMDJ_CHECK(telemetry.dequeued_events == 1);
LMDJ_CHECK(telemetry.started_voices == 1);
LMDJ_CHECK(telemetry.completed_voices == 1);
LMDJ_CHECK(telemetry.active_voices == 0);
LMDJ_CHECK(telemetry.callback_count == 2);
LMDJ_CHECK(telemetry.rendered_frames == 2);
LMDJ_CHECK(telemetry.max_callback_frames == 1);
```

Also assert: slot 64, velocity 0/128, empty slot, empty PCM, NaN, infinity, and running-time load/clear rejection; 1,024 accepted enqueues plus one `queue_full`; velocity `64.0F / 127.0F`; two `0.8F` voices clamp to `1.0F`; 129 simultaneous long voices produce 128 starts plus one `voice_drop`; callback blocks `2 + 3` finish a five-frame sample; stop counts queued/active cancellation; restart resets counters, retains Sample 0, and replays no old event.

Register the component executable and append it to root coverage objects:

```cmake
target_sources(lmdj_audio_runtime PRIVATE src/realtime_engine.cpp)

add_executable(
  lmdj_realtime_engine_tests
  "${CMAKE_SOURCE_DIR}/tests/core/audio/realtime_engine_test.cpp"
)
target_include_directories(
  lmdj_realtime_engine_tests PRIVATE "${CMAKE_SOURCE_DIR}"
)
target_link_libraries(
  lmdj_realtime_engine_tests PRIVATE lmdj::audio_runtime
)
lmdj_target_warnings(lmdj_realtime_engine_tests)
lmdj_target_sanitizers(lmdj_realtime_engine_tests)
lmdj_add_test(
  NAME audio.realtime_engine
  TIER component
  COMMAND lmdj_realtime_engine_tests
  LABELS audio concurrency
)
```

- [ ] **Step 2: Run RED**

```bash
scripts/core.sh configure dev
cmake --build build/core/dev --target lmdj_realtime_engine_tests
```

Expected: compilation fails because `realtime_engine.hpp` and its symbols do not exist.

- [ ] **Step 3: Implement immutable samples, lifecycle, telemetry, and mixer**

The private storage is fixed except for stopped-time Sample vectors:

```cpp
struct Voice {
  const float* samples = nullptr;
  std::size_t frame_count = 0;
  std::size_t cursor = 0;
  float gain = 0.0F;
  bool active = false;
};

std::array<std::vector<float>, kRealtimeSampleSlots> samples_;
detail::FixedSpscQueue<TriggerEvent, kRealtimeQueueCapacity> queue_;
std::array<Voice, kRealtimeVoiceCapacity> voices_{};
std::atomic<RealtimeState> state_{RealtimeState::stopped};
```

Use lock-free `std::atomic<std::uint64_t>` counters and a compile-time lock-free assertion. Control methods return `foundation::ErrorCode::invalid_argument` with fixed messages. `enqueue` validates state, slot, velocity, and a loaded Sample before `try_push`; only successful pushes increment `enqueued_events`, only full pushes increment `queue_drops`, and stopped attempts increment `stopped_rejections`.

The render loop must have this order and no hidden temporary container:

```cpp
std::fill_n(left, frames, 0.0F);
std::fill_n(right, frames, 0.0F);
callback_count_.fetch_add(1, std::memory_order_relaxed);
rendered_frames_.fetch_add(frames, std::memory_order_relaxed);
update_max(max_callback_frames_, frames);

TriggerEvent event{};
while (queue_.try_pop(event)) {
  dequeued_events_.fetch_add(1, std::memory_order_relaxed);
  auto voice = std::find_if(
      voices_.begin(), voices_.end(),
      [](const Voice& candidate) { return !candidate.active; });
  if (voice == voices_.end()) {
    voice_drops_.fetch_add(1, std::memory_order_relaxed);
    continue;
  }
  const auto& sample = samples_[event.slot];
  *voice = Voice{
      sample.data(), sample.size(), 0,
      static_cast<float>(event.velocity) / 127.0F, true};
  started_voices_.fetch_add(1, std::memory_order_relaxed);
  active_voices_.fetch_add(1, std::memory_order_relaxed);
}

for (auto& voice : voices_) {
  if (!voice.active) {
    continue;
  }
  for (std::uint32_t frame = 0;
       frame < frames && voice.cursor < voice.frame_count;
       ++frame, ++voice.cursor) {
    const auto value = voice.samples[voice.cursor] * voice.gain;
    left[frame] += value;
    right[frame] += value;
  }
  if (voice.cursor == voice.frame_count) {
    voice.active = false;
    completed_voices_.fetch_add(1, std::memory_order_relaxed);
    active_voices_.fetch_sub(1, std::memory_order_relaxed);
  }
}

for (std::uint32_t frame = 0; frame < frames; ++frame) {
  left[frame] = std::clamp(left[frame], -1.0F, 1.0F);
  right[frame] = std::clamp(right[frame], -1.0F, 1.0F);
}
```

`stop` changes state before quiescent cleanup, records `queue_.clear_quiescent()` as cancelled events, counts active voices as cancelled voices, and zeros all Voice records. `start` rejects running state, clears Queue/Voice state, resets every run counter, then publishes `running` with release ordering. `telemetry` uses acquire/relaxed loads and is explicitly a best-effort snapshot while running.

Do not maintain `queued_events` as an independent producer/consumer counter:
derive that gauge from `queue_.size_approx()` inside `telemetry()`. This avoids a
publish-then-increment race in which the consumer could pop before a producer
counter update. Cumulative `enqueued_events` and `dequeued_events` remain
independent best-effort atomics while running and satisfy the approved relations
after quiescence.

- [ ] **Step 4: Prove the render path does not allocate**

In the dedicated component executable, override global allocation with a guarded
atomic counter; prepare and enqueue before enabling the guard, call `render`,
disable the guard, then assert the count is zero. Use these complete overloads:

```cpp
std::atomic<bool> g_track_allocations{false};
std::atomic<std::uint64_t> g_allocations{0};

void count_allocation() noexcept {
  if (g_track_allocations.load(std::memory_order_relaxed)) {
    g_allocations.fetch_add(1, std::memory_order_relaxed);
  }
}

void* ordinary_allocation(std::size_t size) {
  count_allocation();
  if (void* memory = std::malloc(size == 0 ? 1 : size)) {
    return memory;
  }
  throw std::bad_alloc{};
}

void* aligned_allocation(std::size_t size, std::size_t alignment) {
  count_allocation();
  void* memory = nullptr;
  if (posix_memalign(&memory, alignment, size == 0 ? 1 : size) == 0) {
    return memory;
  }
  throw std::bad_alloc{};
}

void* operator new(std::size_t size) { return ordinary_allocation(size); }
void* operator new[](std::size_t size) { return ordinary_allocation(size); }
void* operator new(std::size_t size, std::align_val_t alignment) {
  return aligned_allocation(size, static_cast<std::size_t>(alignment));
}
void* operator new[](std::size_t size, std::align_val_t alignment) {
  return aligned_allocation(size, static_cast<std::size_t>(alignment));
}
void operator delete(void* memory) noexcept { std::free(memory); }
void operator delete[](void* memory) noexcept { std::free(memory); }
void operator delete(void* memory, std::size_t) noexcept { std::free(memory); }
void operator delete[](void* memory, std::size_t) noexcept {
  std::free(memory);
}
void operator delete(void* memory, std::align_val_t) noexcept {
  std::free(memory);
}
void operator delete[](void* memory, std::align_val_t) noexcept {
  std::free(memory);
}
void operator delete(
    void* memory, std::size_t, std::align_val_t) noexcept {
  std::free(memory);
}
void operator delete[](
    void* memory, std::size_t, std::align_val_t) noexcept {
  std::free(memory);
}
```

- [ ] **Step 5: Run GREEN**

```bash
cmake --build build/core/dev --target lmdj_realtime_engine_tests
ctest --test-dir build/core/dev --output-on-failure \
  -R '^audio\.(realtime_engine|realtime_queue)$'
```

Expected: both tests pass; the allocation assertion reports zero.

- [ ] **Step 6: Commit Task 2**

```bash
git add packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp \
  packages/audio-runtime/src/realtime_engine.cpp \
  tests/core/audio/realtime_engine_test.cpp \
  packages/audio-runtime/CMakeLists.txt CMakeLists.txt
git diff --cached --check
git commit -m "feat(audio): add realtime voice engine"
```

### Task 3: Add concurrency stress without entering Product Proof

**Files:**

- Create: `tests/core/audio/realtime_engine_stress_test.cpp`
- Modify: `packages/audio-runtime/CMakeLists.txt`

**Interfaces:**

- Consumes: Task 1 `FixedSpscQueue<TriggerEvent, 1024>`.
- Produces: `audio.realtime_spsc_stress`, labelled exactly `stress audio concurrency`.

- [ ] **Step 1: Write the producer/consumer stress test**

Use 1,000,000 events. The producer retries a full queue; the consumer requires every sequence exactly once and in order:

```cpp
constexpr std::uint64_t kEvents = 1'000'000;
FixedSpscQueue<TriggerEvent, 1024> queue;
std::atomic<bool> producer_done{false};

std::thread producer([&] {
  for (std::uint64_t sequence = 0; sequence < kEvents; ++sequence) {
    while (!queue.try_push(TriggerEvent{sequence, 0, 100})) {
      std::this_thread::yield();
    }
  }
  producer_done.store(true, std::memory_order_release);
});

std::uint64_t expected = 0;
while (expected < kEvents ||
       !producer_done.load(std::memory_order_acquire)) {
  TriggerEvent event{};
  if (!queue.try_pop(event)) {
    std::this_thread::yield();
    continue;
  }
  LMDJ_CHECK(event.sequence == expected);
  ++expected;
}
producer.join();
LMDJ_CHECK(expected == kEvents);
LMDJ_CHECK(queue.size_approx() == 0);
```

- [ ] **Step 2: Register and prove tier isolation**

Register with this exact block; do not add the executable to coverage objects:

```cmake
find_package(Threads REQUIRED)
add_executable(
  lmdj_realtime_engine_stress_tests
  "${CMAKE_SOURCE_DIR}/tests/core/audio/realtime_engine_stress_test.cpp"
)
target_include_directories(
  lmdj_realtime_engine_stress_tests PRIVATE "${CMAKE_SOURCE_DIR}"
)
target_link_libraries(
  lmdj_realtime_engine_stress_tests
  PRIVATE lmdj::audio_runtime Threads::Threads
)
lmdj_target_warnings(lmdj_realtime_engine_stress_tests)
lmdj_target_sanitizers(lmdj_realtime_engine_stress_tests)
lmdj_add_test(
  NAME audio.realtime_spsc_stress
  TIER stress
  COMMAND lmdj_realtime_engine_stress_tests
  LABELS audio concurrency
  TIMEOUT 180
)
```

```bash
scripts/core.sh configure tsan
scripts/core.sh build tsan
scripts/core.sh test tsan stress
ctest --test-dir build/core/tsan --show-only=json-v1 | \
  python3 -c 'import json,sys; d=json.load(sys.stdin); t=next(x for x in d["tests"] if x["name"]=="audio.realtime_spsc_stress"); print(next(p["value"] for p in t["properties"] if p["name"]=="LABELS"))'
```

Expected: TSan stress passes and printed labels contain exactly one tier, `stress`; Product Proof selection continues to exclude it.

- [ ] **Step 3: Commit Task 3**

```bash
git add tests/core/audio/realtime_engine_stress_test.cpp \
  packages/audio-runtime/CMakeLists.txt
git diff --cached --check
git commit -m "test(audio): stress realtime trigger queue"
```

### Task 4: Add the Apple CoreAudio output adapter

**Files:**

- Create: `packages/audio-runtime/include/lmdj/audio/apple/coreaudio_output.hpp`
- Create: `packages/audio-runtime/src/apple/coreaudio_services.hpp`
- Create: `packages/audio-runtime/src/apple/coreaudio_services.cpp`
- Create: `packages/audio-runtime/src/apple/coreaudio_output_state.hpp`
- Create: `packages/audio-runtime/src/apple/coreaudio_output.cpp`
- Create: `tests/core/audio/coreaudio_output_test.cpp`
- Modify: `packages/audio-runtime/CMakeLists.txt`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `RealtimeEngine`, Default Output Audio Unit, and a private injectable `CoreAudioServices`/`MonotonicClock` seam.
- Produces: `apple::CoreAudioOutput::start`, `stop`, `state`, and `telemetry` plus target `lmdj::audio_coreaudio` only on Apple.

- [ ] **Step 1: Add the failing adapter test and public API**

Use this Apple-only public API; it exposes no AudioUnit handle and no test seam:

```cpp
#pragma once

#include <cstdint>
#include <memory>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::audio::apple {

enum class CoreAudioState : std::uint8_t {
  stopped,
  running,
  failed,
};

struct CoreAudioTelemetry {
  std::uint64_t device_overloads;
  std::uint64_t callback_failures;
  std::uint64_t deadline_overruns;
};

class CoreAudioOutput final {
 public:
  explicit CoreAudioOutput(RealtimeEngine& engine);
  ~CoreAudioOutput();
  CoreAudioOutput(const CoreAudioOutput&) = delete;
  CoreAudioOutput& operator=(const CoreAudioOutput&) = delete;
  foundation::Result<void> start();
  foundation::Result<void> stop();
  CoreAudioState state() const noexcept;
  CoreAudioTelemetry telemetry() const noexcept;

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::audio::apple
```

The private service seam uses raw C callbacks and control-thread `Result<void>` operations:

```cpp
#pragma once

#include <AudioUnit/AudioUnit.h>
#include <CoreAudio/CoreAudio.h>

#include <atomic>
#include <cstdint>
#include <memory>

#include <lmdj/audio/apple/coreaudio_output.hpp>

namespace lmdj::audio::apple::detail {

class CoreAudioServices {
 public:
  virtual ~CoreAudioServices() = default;
  virtual foundation::Result<void> create(
      AURenderCallback render, void* context) = 0;
  virtual foundation::Result<void> configure(
      std::uint32_t sample_rate, std::uint16_t channels) = 0;
  virtual foundation::Result<void> add_overload_listener(
      AudioObjectPropertyListenerProc listener, void* context) = 0;
  virtual foundation::Result<void> initialize() = 0;
  virtual foundation::Result<void> start() = 0;
  virtual foundation::Result<void> stop() = 0;
  virtual foundation::Result<void> remove_overload_listener() = 0;
  virtual foundation::Result<void> uninitialize() = 0;
  virtual foundation::Result<void> dispose() = 0;
};

class MonotonicClock {
 public:
  virtual ~MonotonicClock() = default;
  virtual std::uint64_t now() noexcept = 0;
  virtual double seconds_between(
      std::uint64_t begin, std::uint64_t end) noexcept = 0;
};

std::unique_ptr<CoreAudioServices> make_default_coreaudio_services();
std::unique_ptr<MonotonicClock> make_mach_monotonic_clock();

class CoreAudioOutputStateMachine final {
 public:
  CoreAudioOutputStateMachine(
      RealtimeEngine& engine,
      std::unique_ptr<CoreAudioServices> services,
      std::unique_ptr<MonotonicClock> clock);
  foundation::Result<void> start();
  foundation::Result<void> stop();
  CoreAudioState state() const noexcept;
  CoreAudioTelemetry telemetry() const noexcept;

 private:
  static OSStatus render_callback(
      void* context,
      AudioUnitRenderActionFlags* flags,
      const AudioTimeStamp* timestamp,
      UInt32 bus,
      UInt32 frames,
      AudioBufferList* buffers) noexcept;
  static OSStatus overload_callback(
      AudioObjectID object,
      UInt32 address_count,
      const AudioObjectPropertyAddress* addresses,
      void* context) noexcept;

  RealtimeEngine& engine_;
  std::unique_ptr<CoreAudioServices> services_;
  std::unique_ptr<MonotonicClock> clock_;
  CoreAudioState state_{CoreAudioState::stopped};
  bool created_ = false;
  bool listener_added_ = false;
  bool initialized_ = false;
  bool unit_started_ = false;
  std::atomic<std::uint64_t> device_overloads_{0};
  std::atomic<std::uint64_t> callback_failures_{0};
  std::atomic<std::uint64_t> deadline_overruns_{0};
};

}  // namespace lmdj::audio::apple::detail
```

`coreaudio_output_test.cpp` includes the private state header and supplies fakes. Assert exact successful calls:

```text
create, configure, add_overload_listener, initialize, start,
stop, remove_overload_listener, uninitialize, dispose
```

For each start failure point, assert every acquired resource is cleaned in reverse
order. When cleanup succeeds, Engine state is stopped and a subsequent start can
succeed. Inject a dispose/cleanup failure separately and assert terminal
`CoreAudioState::failed`, preserved Engine/Sample storage, and rejected restart.
Also assert idempotent successful stop, `already_running` details for duplicate
start, callback output through Engine, invalid AudioBufferList increments
`callback_failures`, fake overload notification increments `device_overloads`,
and a fake elapsed duration greater than `frames / 48000.0` increments
`deadline_overruns`.

- [ ] **Step 2: Run RED on macOS**

```bash
scripts/core.sh configure dev
cmake --build build/core/dev --target lmdj_audio_coreaudio_tests
```

Expected: target or source is missing.

- [ ] **Step 3: Implement real Apple services**

Create `kAudioUnitType_Output` / `kAudioUnitSubType_DefaultOutput` /
`kAudioUnitManufacturer_Apple`. Install the render callback on input scope, bus 0, and set this exact client format:

```cpp
AudioStreamBasicDescription format{};
format.mSampleRate = 48'000.0;
format.mFormatID = kAudioFormatLinearPCM;
format.mFormatFlags = kAudioFormatFlagIsFloat |
                      kAudioFormatFlagsNativeEndian |
                      kAudioFormatFlagIsPacked |
                      kAudioFormatFlagIsNonInterleaved;
format.mBytesPerPacket = sizeof(float);
format.mFramesPerPacket = 1;
format.mBytesPerFrame = sizeof(float);
format.mChannelsPerFrame = 2;
format.mBitsPerChannel = 32;
```

Resolve `kAudioHardwarePropertyDefaultOutputDevice`, add/remove a
`kAudioDeviceProcessorOverload` listener, use `mach_absolute_time` with one
precomputed `mach_timebase_info`, and convert each non-zero OSStatus to
`foundation::ErrorCode::io_error` details containing `operation` and the signed
numeric `os_status`. No new Foundation error enum or Contract is allowed.
This is the processor-overload telemetry source. The listener callback enters
the same lock-free `CoreAudioCallbackContext` lifetime gate as render, records
one relaxed `device_overloads` increment only while enabled, leaves the gate,
and returns. It performs no allocation, lock, I/O, logging, or other work.

- [ ] **Step 4: Implement the callback and lifecycle**

Start sequence is create → configure → overload listener → initialize → Engine
start → Audio Unit start. Reset adapter counters before this attempt. On failure,
unwind every acquired resource; restore Engine stopped only after disposal proves
callbacks cannot recur, otherwise enter terminal `failed` and retain Engine data.

Stop first asks Audio Unit to stop, then removes the listener, uninitializes and
disposes while retaining the first error; only after callbacks cannot recur does
it call `engine.stop()`. A cleanup failure that leaves callback termination
unproven enters terminal `failed`; `start` and `stop` then return the same fixed
terminal-state error. A second successful stopped-state stop succeeds without
framework calls. `AudioObjectRemovePropertyListener` unregisters future
notifications but does not document draining an already-running listener, so
successful listener removal and Audio Unit disposal are followed by a final
shared-context drain before stopped state, Engine stop, or context release. The
render callback accepts exactly two one-channel float buffers with enough bytes,
measures elapsed monotonic time around `engine.render`, and returns
`kAudio_ParamError` plus one `callback_failures` increment for invalid buffers.

- [ ] **Step 5: Register Apple-only targets and run GREEN**

Use this Apple-only target shape:

```cmake
if(APPLE)
  find_library(LMDJ_AUDIO_UNIT_FRAMEWORK AudioUnit REQUIRED)
  find_library(LMDJ_CORE_AUDIO_FRAMEWORK CoreAudio REQUIRED)
  find_library(LMDJ_CORE_FOUNDATION_FRAMEWORK CoreFoundation REQUIRED)
  add_library(
    lmdj_audio_coreaudio STATIC
    src/apple/coreaudio_services.cpp
    src/apple/coreaudio_output.cpp
  )
  add_library(lmdj::audio_coreaudio ALIAS lmdj_audio_coreaudio)
  target_include_directories(
    lmdj_audio_coreaudio
    PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
    PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/apple"
  )
  target_link_libraries(
    lmdj_audio_coreaudio
    PUBLIC lmdj::audio_runtime
    PRIVATE
      "${LMDJ_AUDIO_UNIT_FRAMEWORK}"
      "${LMDJ_CORE_AUDIO_FRAMEWORK}"
      "${LMDJ_CORE_FOUNDATION_FRAMEWORK}"
  )
  lmdj_target_warnings(lmdj_audio_coreaudio)
  lmdj_target_sanitizers(lmdj_audio_coreaudio)

  if(BUILD_TESTING)
    add_executable(
      lmdj_audio_coreaudio_tests
      "${CMAKE_SOURCE_DIR}/tests/core/audio/coreaudio_output_test.cpp"
    )
    target_include_directories(
      lmdj_audio_coreaudio_tests
      PRIVATE "${CMAKE_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/src/apple"
    )
    target_link_libraries(
      lmdj_audio_coreaudio_tests PRIVATE lmdj::audio_coreaudio
    )
    lmdj_target_warnings(lmdj_audio_coreaudio_tests)
    lmdj_target_sanitizers(lmdj_audio_coreaudio_tests)
    lmdj_add_test(
      NAME audio.coreaudio_output
      TIER component
      COMMAND lmdj_audio_coreaudio_tests
      LABELS audio
    )
  endif()
endif()
```

In the root coverage list use `if(APPLE)` before appending
`lmdj_audio_coreaudio_tests`, so Linux never references a missing target.

```cmake
if(APPLE)
  list(APPEND lmdj_coverage_targets lmdj_audio_coreaudio_tests)
endif()
```

```bash
cmake --build build/core/dev --target lmdj_audio_coreaudio_tests
ctest --test-dir build/core/dev --output-on-failure \
  -R '^audio\.coreaudio_output$'
```

Expected: adapter test passes without opening the physical device.

- [ ] **Step 6: Prove non-Apple isolation**

On the Ubuntu CI configuration, require configuration/build success and require
`cmake --build build/core/dev --target lmdj_audio_coreaudio` to report that no
such target exists. Do not add preprocessor-based fake success implementations.

- [ ] **Step 7: Commit Task 4**

```bash
git add packages/audio-runtime/include/lmdj/audio/apple/coreaudio_output.hpp \
  packages/audio-runtime/src/apple/coreaudio_services.hpp \
  packages/audio-runtime/src/apple/coreaudio_services.cpp \
  packages/audio-runtime/src/apple/coreaudio_output_state.hpp \
  packages/audio-runtime/src/apple/coreaudio_output.cpp \
  tests/core/audio/coreaudio_output_test.cpp \
  packages/audio-runtime/CMakeLists.txt CMakeLists.txt
git diff --cached --check
git commit -m "feat(audio): add CoreAudio output adapter"
```

### Task 5: Add the Apple-only native audio probe

**Files:**

- Create: `tests/platform/audio/native_audio_probe.cpp`
- Create: `tests/platform/audio/native_audio_probe_smoke.py`
- Modify: `packages/audio-runtime/CMakeLists.txt`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `RealtimeEngine`, `apple::CoreAudioOutput`, stdin line commands, and optional `--no-device`.
- Produces: `build/core/<preset>/bin/lmdj-native-audio-probe` and `audio.native_probe_no_device` component test.

- [ ] **Step 1: Write the black-box no-device test first**

Launch the executable with `--no-device` and this input:

```text
trigger
status
stop
trigger
status
start
trigger
status
quit
```

Require ten canonical JSON lines: startup plus one response per command. The
first running status must say `enqueued_events=1`, `dequeued_events=1`,
`started_voices=1`, `completed_voices=1`, `callback_count=10`,
`rendered_frames=1280`, `max_callback_frames=128`, and all drops/failures zero.
The stopped trigger response must be `not_running`; the stopped status must show
`stopped_rejections=1`. The second successful trigger uses sequence 2 and the
post-restart status again starts its run counters at one completed voice. Also
assert EOF performs the same clean stop as `quit`, an unknown command returns a
structured error but the next command runs, and unsupported arguments exit 64.

- [ ] **Step 2: Run RED**

```bash
scripts/core.sh configure dev
cmake --build build/core/dev --target lmdj_native_audio_probe
```

Expected: target does not exist.

- [ ] **Step 3: Implement fixed Sample and command protocol**

Generate exactly 1,200 frames before start:

```cpp
std::vector<float> sample(1'200);
for (std::size_t frame = 0; frame < sample.size(); ++frame) {
  constexpr double kPi = 3.14159265358979323846;
  sample[frame] = static_cast<float>(
      std::sin(2.0 * kPi * 880.0 * static_cast<double>(frame) / 48'000.0) *
      0.12);
}
```

Default mode constructs `CoreAudioOutput`; `--no-device` starts Engine directly.
On an accepted no-device trigger, render ten 128-frame zero-initialized blocks
before reading the next command. Increment the next sequence only after an
accepted enqueue. Compose status on the control thread from Engine telemetry and
CoreAudio telemetry; no callback writes JSON or stdout/stderr.

Use fixed response keys `ok`, `command`, and `result` or `error`; status adds all
fields from the approved spec plus `device_overloads`, `callback_failures`, and
`deadline_overruns`. Unknown command continues. EOF executes quit. Initial device
start/configuration failure and a failed `start` command exit 2; invalid arguments
exit 64; normal quit exits 0.

If an adapter error leaves `CoreAudioState::failed`, write and flush its canonical
JSON error on the control thread, then call `std::_Exit(2)`. This terminal path is
intentional: ordinary stack unwinding could destroy Engine/Sample/callback state
while CoreAudio callback termination is unproven.

- [ ] **Step 4: Register the probe without creating a Host**

Inside `packages/audio-runtime/CMakeLists.txt`, add:

```cmake
if(APPLE AND BUILD_TESTING)
  add_executable(
    lmdj_native_audio_probe
    "${CMAKE_SOURCE_DIR}/tests/platform/audio/native_audio_probe.cpp"
  )
  set_target_properties(
    lmdj_native_audio_probe PROPERTIES OUTPUT_NAME lmdj-native-audio-probe
  )
  target_link_libraries(
    lmdj_native_audio_probe
    PRIVATE lmdj::audio_coreaudio lmdj::foundation
  )
  lmdj_target_warnings(lmdj_native_audio_probe)
  lmdj_target_sanitizers(lmdj_native_audio_probe)
endif()
```

In the root `CMakeLists.txt`, after Python discovery, add:

```cmake
if(APPLE AND TARGET lmdj_native_audio_probe)
  lmdj_add_test(
    NAME audio.native_probe_no_device
    TIER component
    COMMAND
      "${Python3_EXECUTABLE}"
      tests/platform/audio/native_audio_probe_smoke.py
      "$<TARGET_FILE:lmdj_native_audio_probe>"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS audio
  )
endif()
```

Do not create an `apps/` directory, `module.json`, installer entry, or Assembly
host row.

- [ ] **Step 5: Run GREEN and inspect registration**

```bash
cmake --build build/core/dev --target lmdj_native_audio_probe
python3 tests/platform/audio/native_audio_probe_smoke.py \
  build/core/dev/bin/lmdj-native-audio-probe
ctest --test-dir build/core/dev --output-on-failure \
  -R '^audio\.native_probe_no_device$'
test ! -e apps/native-test-host
```

Expected: black-box smoke and CTest pass; no formal Native Host exists.

- [ ] **Step 6: Commit Task 5**

```bash
git add tests/platform/audio/native_audio_probe.cpp \
  tests/platform/audio/native_audio_probe_smoke.py \
  packages/audio-runtime/CMakeLists.txt CMakeLists.txt
git diff --cached --check
git commit -m "feat(audio): add native CoreAudio probe"
```

### Task 6: Propagate exact versions and prove the integrated Build

**Files:**

- Modify: `packages/audio-runtime/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/core-mcp/pyproject.toml`
- Modify: `apps/core-mcp/lmdj_core_mcp/__init__.py`
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Modify: `products/lmdj/README.md`
- Modify: `scripts/core.sh`
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/version_lock_test.py`
- Modify: `tests/core/facade/application_test.cpp`
- Modify: `tests/core/facade/assembly_loader_test.cpp`
- Modify: `tests/host/cli_test.py`
- Modify: `tests/host/mcp_stdio_test.py`
- Regenerate: `products/lmdj/assembly.lock.json`

**Interfaces:**

- Consumes: Tasks 1–5 and the exact dependency graph enforced by `module_graph_test.py`.
- Produces: consistent Product Build `1.0.10.0`, Module/Host identities, generated lock, and complete local verification evidence.

- [ ] **Step 1: Change exact assertions first and run RED**

Set expected values to Product `1.0.10.0`, `audio-runtime 0.2.0`,
`application-facade 1.0.1`, `core-cli 1.0.1`, and `core-mcp 1.0.1` in the listed
tests, including MCP `pyproject` and `serverInfo` expectations.

```bash
python3 tests/build/version_test.py
python3 tests/conformance/module_graph_test.py
```

Expected: failures show current Build 9 and old exact dependency versions.

- [ ] **Step 2: Update every source identity**

Apply these exact changes:

```text
packages/audio-runtime/module.json: version 0.2.0, api_version 1
packages/application-facade/module.json: version 1.0.1,
  audio-runtime dependency 0.2.0, api_version 2
apps/core-cli/module.json: version 1.0.1,
  application-facade dependency 1.0.1, api_version 2
apps/core-mcp/module.json: version 1.0.1,
  application-facade dependency 1.0.1, api_version 2
apps/core-mcp/pyproject.toml and __init__.py: version 1.0.1
products/lmdj/version.json: build 10, patch 0
products/lmdj/assembly.json and compiled_assembly.cpp: Product 1.0.10.0
products/lmdj/assembly.json and compiled_assembly.cpp: exact new Module/Host versions
products/lmdj/README.md and scripts/core.sh: Product 1.0.10.0
products/lmdj/README.md status: 5A Probe implemented; Formal Native Host,
  Project/Snapshot integration, MIDI, capture, Creator UI, and Web product remain absent
```

- [ ] **Step 3: Regenerate, never hand-edit, the lock**

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
```

Expected: verification says `PASS (1.0.10.0)` and lock hashes match sources.

- [ ] **Step 4: Run targeted identity and audio checks**

```bash
python3 tests/build/version_test.py
python3 tests/conformance/module_graph_test.py
python3 tests/conformance/version_lock_test.py
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure \
  -R '^(audio\.|build\.version|conformance\.|facade\.application|facade\.assembly_loader|host\.(cli|mcp_stdio))'
```

Expected: new audio tests and all exact-identity consumers pass.

- [ ] **Step 5: Run complete local gates**

```bash
scripts/core.sh configure asan
scripts/core.sh build asan
scripts/core.sh test asan full
scripts/core.sh configure tsan
scripts/core.sh build tsan
scripts/core.sh test tsan stress
scripts/core.sh coverage check
scripts/core.sh proof
git diff --check
```

Expected: ASan non-stress suite, TSan stress, coverage gate, and all Release
Proof tests pass; Proof prints Product `1.0.10.0`, Channel `canary`, and Assembly
lock `MATCH`. This does not yet prove audible output.

- [ ] **Step 6: Scan for stale active identities**

```bash
test -z "$(rg -l '1\.0\.9\.0|\"build\": 9' products apps packages scripts tests)"
test -z "$(rg -l '\"audio-runtime\": \"0\.1\.0\"|\"application-facade\": \"1\.0\.0\"' products apps packages scripts tests)"
```

Expected: both commands exit 0. Provider/Contract/client versions that remain
`1.0.0` are intentionally outside these exact patterns.

- [ ] **Step 7: Commit Task 6**

Stage exactly the files declared by Task 6, inspect the staged name list and
cached whitespace check, then commit:

```bash
git add packages/audio-runtime/module.json \
  packages/application-facade/module.json \
  apps/core-cli/module.json apps/core-mcp/module.json \
  apps/core-mcp/pyproject.toml \
  apps/core-mcp/lmdj_core_mcp/__init__.py \
  products/lmdj/version.json products/lmdj/assembly.json \
  products/lmdj/assembly.lock.json \
  products/lmdj/src/compiled_assembly.cpp products/lmdj/README.md \
  scripts/core.sh tests/build/version_test.py \
  tests/conformance/version_lock_test.py \
  tests/core/facade/application_test.cpp \
  tests/core/facade/assembly_loader_test.cpp \
  tests/host/cli_test.py tests/host/mcp_stdio_test.py
git diff --cached --name-only
git diff --cached --check
git commit -m "chore(core): allocate product build 1.0.10.0"
```

### Task 7: Perform the physical CoreAudio acceptance gate

**Files:** none

**Interfaces:**

- Consumes: committed `lmdj-native-audio-probe` from Task 5 and current Mac built-in or wired output.
- Produces: human audible confirmation plus retained terminal telemetry; it does not change Web, MIDI, Touch, or release status.

- [ ] **Step 1: Select a valid output path**

Use macOS Sound settings to select built-in speakers or a wired device. Do not
use Bluetooth, aggregate output, AirPlay, or a device switch during this gate.

- [ ] **Step 2: Build the committed probe and run paced triggers**

```bash
scripts/core.sh configure dev
cmake --build build/core/dev --target lmdj_native_audio_probe
{
  for trigger_index in $(seq 1 20); do
    echo trigger
    sleep 0.15
  done
  echo status
  sleep 0.2
  echo stop
  echo trigger
  echo start
  sleep 0.2
  echo trigger
  sleep 0.3
  echo status
  echo quit
} | build/core/dev/bin/lmdj-native-audio-probe | \
  tee /tmp/lmdj-native-audio-probe-1.0.10.0.jsonl
```

Expected audible result: exactly 20 separated short tones before stop, silence
for the rejected stopped trigger, and exactly one short tone after restart.

- [ ] **Step 3: Check telemetry and obtain human confirmation**

The first status must show 20 enqueued/dequeued/started/completed voices and zero
queued/active/cancelled/drop/overload/failure/deadline counters. The stopped
trigger must return `not_running`. The final run status must show one completed
voice and zero failures. Ask the user to confirm the audible count; absence of
that confirmation leaves physical acceptance unverified.

- [ ] **Step 4: Audit the branch without expanding authority**

```bash
git log --oneline --decorate 46387c22..HEAD
git status --short --branch
git diff 46387c22...HEAD --check
```

Expected: the design, plan, and six implementation commits are present; the
worktree is clean. Do not push, open a PR, merge, tag, release, deploy, or promote
the Channel without separate authorization.

## Final Review Checklist

- [ ] Queue accepts exactly 1,024 events and the million-event TSan run preserves FIFO without duplicates or loss.
- [ ] Engine covers 64 samples, 128 voices, fixed validation results, exact telemetry relations, stop/start reset, and zero render-path C++ allocation.
- [ ] Apple adapter covers success, every injected failure cleanup, duplicate start, idempotent stop, overload notification, callback validation, and deadline detection.
- [ ] Apple probe no-device output is deterministic; non-Apple builds have no adapter/probe target or fake success.
- [ ] Probe remains outside `apps/`, Product Assembly hosts, Project parsing, Facade callbacks, and Web runtime code.
- [ ] Product/Module/Host identities and generated lock consistently describe `1.0.10.0` / `0.2.0` / `1.0.1`.
- [ ] ASan full, TSan stress, coverage, Product Proof, and physical built-in/wired output acceptance all pass.
- [ ] Web physical matrix status remains unchanged: Safari failed; Chrome/MIDI/iPad deferred.
- [ ] Branch is committed and clean; push/PR/merge/tag/release/deploy/Channel promotion remain unperformed.
