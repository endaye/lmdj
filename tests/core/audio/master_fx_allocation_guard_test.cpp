#include <lmdj/audio/master_fx.hpp>
#include <lmdj/audio/realtime_engine.hpp>

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <iostream>
#include <iterator>
#include <new>
#include <regex>
#include <string>
#include <type_traits>
#include <utility>

#include "tests/core/support/test.hpp"

namespace {

std::atomic<bool> g_track_allocations{false};
std::atomic<std::uint64_t> g_allocations{0};
std::atomic<std::uint64_t> g_deallocations{0};

void count_allocation() noexcept {
  if (g_track_allocations.load(std::memory_order_relaxed)) {
    g_allocations.fetch_add(1, std::memory_order_relaxed);
  }
}

void ordinary_deallocation(void* memory) noexcept {
  if (g_track_allocations.load(std::memory_order_relaxed)) {
    g_deallocations.fetch_add(1, std::memory_order_relaxed);
  }
  std::free(memory);
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

std::string read_code(const char* path) {
  std::ifstream source(path);
  LMDJ_CHECK(source.is_open());
  const std::string text{std::istreambuf_iterator<char>{source}, {}};
  // Explanatory comments must not trip an absence check on code syntax.
  return std::regex_replace(text, std::regex{R"(/\*[\s\S]*?\*/|//[^\n]*)"}, "");
}

std::string without_observation_methods(std::string source) {
  // The approved reader-only mutex is confined to these non-realtime APIs.
  // Keep scanning every other Engine function, not just the top-level render.
  for (const auto method : {
           "telemetry", "bank_telemetry", "pattern_telemetry",
           "capture_telemetry", "trigger_outcome_telemetry",
           "voice_state_telemetry", "master_fx_telemetry"}) {
    const auto begin = source.find(std::string{"RealtimeEngine::"} + method + "()");
    LMDJ_CHECK(begin != std::string::npos);
    const auto body = source.find('{', begin);
    LMDJ_CHECK(body != std::string::npos);
    std::size_t depth = 1;
    auto end = body + 1;
    for (; end < source.size() && depth != 0; ++end) {
      if (source[end] == '{') ++depth;
      if (source[end] == '}') --depth;
    }
    LMDJ_CHECK(depth == 0);
    source.erase(begin, end - begin);
  }
  return source;
}

void check_no_lock(const std::string& source, const char* boundary) {
  for (const auto forbidden : {
           "std::mutex", "std::lock_guard", "std::unique_lock",
           "std::scoped_lock", "observation_reader_mutex_"}) {
    if (source.find(forbidden) != std::string::npos) {
      std::cerr << "why: " << boundary << " contains forbidden lock syntax "
                << forbidden << ".\nremedy: keep the reader-only lock in the "
                   "seven non-realtime observation methods; audio adapters "
                   "must use their audio-owned value access.\n";
      LMDJ_CHECK(false);
    }
  }
}

void lock_syntax_is_confined_to_non_realtime_observers() {
  check_no_lock(read_code("packages/audio-runtime/src/master_fx.cpp"), "Master FX");
  check_no_lock(read_code("packages/audio-runtime/src/voice_dsp.cpp"), "voice DSP kernel");
  check_no_lock(
      read_code("packages/audio-runtime/include/lmdj/audio/detail/voice_dsp.hpp"),
      "voice DSP kernel header");
  check_no_lock(without_observation_methods(read_code(
      "packages/audio-runtime/src/realtime_engine.cpp")), "Engine writer paths");
  check_no_lock(read_code("packages/audio-runtime/src/realtime_engine_audio_access.hpp"),
                "audio-owned adapter access");
  const auto worklet = read_code(
      "packages/audio-runtime/src/web/realtime_audio_worklet.cpp");
  const auto begin = worklet.find("static bool process(");
  const auto end = worklet.find("void signal_quiescence_waiters()", begin);
  LMDJ_CHECK(begin != std::string::npos && end != std::string::npos);
  const auto callback = worklet.substr(begin, end - begin);
  check_no_lock(callback, "Web Audio callback");
  if (callback.find("_telemetry(") != std::string::npos ||
      callback.find(".telemetry(") != std::string::npos) {
    std::cerr << "why: Web Audio callback calls a reader-locking observation API.\n"
                 "remedy: read the adapter's audio-owned status after render.\n";
    LMDJ_CHECK(false);
  }
}

void typed_filter_controls_are_allocation_free_and_lock_free() {
  using lmdj::audio::EnqueueResult;
  using lmdj::audio::FxEnqueueResult;
  using lmdj::audio::FxGesture;
  using lmdj::audio::FxGestureKind;
  using lmdj::audio::FilterGesture;
  using lmdj::audio::FilterPhase;
  using lmdj::audio::FilterType;
  using lmdj::audio::RealtimeEngine;
  using lmdj::audio::TriggerEvent;

  static_assert(noexcept(std::declval<RealtimeEngine&>().enqueue_filter_gesture(
      std::declval<FilterGesture>())));
  static_assert(
      noexcept(std::declval<const RealtimeEngine&>().filter_control_status()));

  RealtimeEngine engine;
  const auto sample = [] {
    std::array<float, 8'192> result{};
    for (std::size_t frame = 0; frame < result.size(); ++frame) {
      result[frame] = static_cast<float>(frame % 127U) / 160.0F;
    }
    return result;
  }();
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.prepare_master_fx(120).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue(TriggerEvent{1, 0, 127}) == EnqueueResult::accepted);

  // Invalid tuples are refused before any queue or accepted-state change.
  const auto before = engine.filter_control_status();
  LMDJ_CHECK(before.accepted_sequence == 0);
  LMDJ_CHECK(engine.enqueue_filter_gesture(FilterGesture{
                 FilterPhase::engage, {FilterType::low_pass, 19, 0}}) ==
             FxEnqueueResult::invalid_value);
  LMDJ_CHECK(engine.enqueue_filter_gesture(FilterGesture{
                 FilterPhase::engage, {FilterType::low_pass, 20'001, 0}}) ==
             FxEnqueueResult::invalid_value);
  LMDJ_CHECK(engine.enqueue_filter_gesture(FilterGesture{
                 FilterPhase::engage, {FilterType::low_pass, 800, 1'001}}) ==
             FxEnqueueResult::invalid_value);
  LMDJ_CHECK(engine.enqueue_filter_gesture(FilterGesture{
                 FilterPhase::engage,
                 {static_cast<FilterType>(7), 800, 0}}) ==
             FxEnqueueResult::invalid_value);
  LMDJ_CHECK(engine.filter_control_status().accepted_sequence == 0);

  // Every new parameter change plus HOLD/release/neutral.
  const std::array<FilterGesture, 6> controls{{
      FilterGesture{FilterPhase::engage, {FilterType::low_pass, 800, 250}},
      FilterGesture{FilterPhase::move, {FilterType::low_pass, 20, 0}},
      FilterGesture{FilterPhase::move, {FilterType::high_pass, 20'000, 1'000}},
      FilterGesture{FilterPhase::move, {FilterType::band_pass, 1'200, 500}},
      FilterGesture{FilterPhase::release, {}},
      FilterGesture{FilterPhase::engage, {FilterType::low_pass, 100, 1'000}},
  }};
  for (const auto& control : controls) {
    LMDJ_CHECK(engine.enqueue_filter_gesture(control) ==
               FxEnqueueResult::accepted);
  }
  LMDJ_CHECK(engine.enqueue_fx_gesture(FxGesture{
                 FxGestureKind::hold_on, lmdj::domain::PerformanceFx::filter,
                 0}) == FxEnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue_filter_gesture(
                 FilterGesture{FilterPhase::release, {}}) ==
             FxEnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue_fx_gesture(FxGesture{
                 FxGestureKind::hold_off, lmdj::domain::PerformanceFx::filter,
                 0}) == FxEnqueueResult::accepted);

  std::array<float, 4'096> left{};
  std::array<float, 4'096> right{};
  g_allocations.store(0, std::memory_order_relaxed);
  g_deallocations.store(0, std::memory_order_relaxed);
  g_track_allocations.store(true, std::memory_order_relaxed);
  engine.render(left.data(), right.data(), left.size());
  const auto status = engine.filter_control_status();
  const auto accepted = status.accepted;
  g_track_allocations.store(false, std::memory_order_relaxed);

  LMDJ_CHECK(g_allocations.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(g_deallocations.load(std::memory_order_relaxed) == 0);

  // The drain applied every accepted control exactly once and the coherent
  // applied state caught up with the accepted shadow.
  LMDJ_CHECK(status.accepted_sequence == 7);
  LMDJ_CHECK(status.applied.sequence == 7);
  LMDJ_CHECK(status.applied.epoch == engine.telemetry().start_epoch);
  LMDJ_CHECK(status.applied.state.mode == accepted.mode);
  LMDJ_CHECK(status.applied.state.engaged == accepted.engaged);
  LMDJ_CHECK(status.applied.state.frozen == accepted.frozen);
  LMDJ_CHECK(status.applied.state.hold == accepted.hold);
  LMDJ_CHECK(status.applied.state.legacy_value == accepted.legacy_value);
  LMDJ_CHECK(status.applied.state.parameters.type == accepted.parameters.type);
  LMDJ_CHECK(status.applied.state.parameters.cutoff_hz ==
             accepted.parameters.cutoff_hz);
  LMDJ_CHECK(status.applied.state.parameters.resonance_milli ==
             accepted.parameters.resonance_milli);
  const auto fx = engine.master_fx_telemetry();
  LMDJ_CHECK(fx.enqueued_filter_controls == 7);
  LMDJ_CHECK(fx.dequeued_filter_controls == 7);
}

void full_chain_render_is_noexcept_allocation_free_and_lock_free() {
  using lmdj::audio::EnqueueResult;
  using lmdj::audio::FxEnqueueResult;
  using lmdj::audio::FxGesture;
  using lmdj::audio::FxGestureKind;
  using lmdj::audio::MasterFxChain;
  using lmdj::audio::RealtimeEngine;
  using lmdj::audio::TriggerEvent;

  static_assert(noexcept(std::declval<MasterFxChain&>().process(
      static_cast<float*>(nullptr), static_cast<float*>(nullptr), 0)));
  static_assert(noexcept(std::declval<RealtimeEngine&>().render(
      static_cast<float*>(nullptr), static_cast<float*>(nullptr), 0)));

  RealtimeEngine engine;
  RealtimeEngine dry_engine;
  const auto sample = [] {
    std::array<float, 8'192> result{};
    for (std::size_t frame = 0; frame < result.size(); ++frame) {
      result[frame] = static_cast<float>(frame % 127U) / 160.0F;
    }
    return result;
  }();
  LMDJ_CHECK(dry_engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(dry_engine.prepare_master_fx(120).has_value());
  LMDJ_CHECK(dry_engine.start().has_value());
  LMDJ_CHECK(
      dry_engine.enqueue(TriggerEvent{1, 0, 127}) ==
      EnqueueResult::accepted);
  std::array<float, 4'096> dry_left{};
  std::array<float, 4'096> dry_right{};
  dry_engine.render(dry_left.data(), dry_right.data(), dry_left.size());

  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.prepare_master_fx(120).has_value());
  LMDJ_CHECK(engine.start().has_value());
  for (const auto fx : lmdj::audio::kFxChainOrder) {
    LMDJ_CHECK(engine.enqueue_fx_gesture(
                   FxGesture{FxGestureKind::engage, fx, 1'000}) ==
               FxEnqueueResult::accepted);
  }
  LMDJ_CHECK(
      engine.enqueue(TriggerEvent{1, 0, 127}) == EnqueueResult::accepted);

  std::array<float, 4'096> left{};
  std::array<float, 4'096> right{};
  g_allocations.store(0, std::memory_order_relaxed);
  g_deallocations.store(0, std::memory_order_relaxed);
  g_track_allocations.store(true, std::memory_order_relaxed);
  engine.render(left.data(), right.data(), left.size());
  g_track_allocations.store(false, std::memory_order_relaxed);

  LMDJ_CHECK(g_allocations.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(g_deallocations.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(left != dry_left || right != dry_right);
  const auto fx = engine.master_fx_telemetry();
  LMDJ_CHECK(fx.dequeued_gestures == lmdj::audio::kFxChainOrder.size());
  LMDJ_CHECK(fx.processed_frames == left.size());
}

void pad_gates_controls_are_allocation_free_and_lock_free() {
  using lmdj::audio::FxEnqueueResult;
  using lmdj::audio::RealtimeEngine;

  static_assert(noexcept(std::declval<RealtimeEngine&>().enqueue_pad_gates(
      0, 0)));
  static_assert(
      noexcept(std::declval<const RealtimeEngine&>().pad_gates_status()));

  RealtimeEngine engine;
  std::array<float, 64> sample{};
  sample.fill(0.1F);
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());

  // Gates are voice-level, not an FX stage: no prepared Master FX needed.
  // Warm up any first-touch queue storage outside the tracked region.
  std::array<float, 256> left{};
  std::array<float, 256> right{};
  LMDJ_CHECK(engine.enqueue_pad_gates(0x1, 0) == FxEnqueueResult::accepted);
  engine.render(left.data(), right.data(), left.size());
  LMDJ_CHECK(engine.pad_gates_status().applied.sequence == 1);

  g_allocations.store(0, std::memory_order_relaxed);
  g_deallocations.store(0, std::memory_order_relaxed);
  g_track_allocations.store(true, std::memory_order_relaxed);
  LMDJ_CHECK(engine.enqueue_pad_gates(0, 0x1) == FxEnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue_pad_gates(
                 0x1 | (std::uint64_t{1} << 63), 0) ==
             FxEnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue_pad_gates(0, 0) == FxEnqueueResult::accepted);
  engine.render(left.data(), right.data(), left.size());
  const auto status = engine.pad_gates_status();
  g_track_allocations.store(false, std::memory_order_relaxed);

  LMDJ_CHECK(g_allocations.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(g_deallocations.load(std::memory_order_relaxed) == 0);

  // The drain applied every accepted pair exactly once and the coherent
  // applied state caught up with the accepted shadow.
  LMDJ_CHECK(status.accepted_sequence == 4);
  LMDJ_CHECK(status.applied.sequence == 4);
  LMDJ_CHECK(status.applied.epoch == engine.telemetry().start_epoch);
  LMDJ_CHECK(status.applied.state.muted_mask == 0);
  LMDJ_CHECK(status.applied.state.solo_mask == 0);
}

}  // namespace

void* operator new(std::size_t size) { return ordinary_allocation(size); }void* operator new[](std::size_t size) { return ordinary_allocation(size); }
void* operator new(std::size_t size, std::align_val_t alignment) {
  return aligned_allocation(size, static_cast<std::size_t>(alignment));
}
void* operator new[](std::size_t size, std::align_val_t alignment) {
  return aligned_allocation(size, static_cast<std::size_t>(alignment));
}
void operator delete(void* memory) noexcept { ordinary_deallocation(memory); }
void operator delete[](void* memory) noexcept { ordinary_deallocation(memory); }
void operator delete(void* memory, std::size_t) noexcept {
  ordinary_deallocation(memory);
}
void operator delete[](void* memory, std::size_t) noexcept {
  ordinary_deallocation(memory);
}
void operator delete(void* memory, std::align_val_t) noexcept {
  ordinary_deallocation(memory);
}
void operator delete[](void* memory, std::align_val_t) noexcept {
  ordinary_deallocation(memory);
}
void operator delete(
    void* memory, std::size_t, std::align_val_t) noexcept {
  ordinary_deallocation(memory);
}
void operator delete[](
    void* memory, std::size_t, std::align_val_t) noexcept {
  ordinary_deallocation(memory);
}

int main() {
  try {
    lock_syntax_is_confined_to_non_realtime_observers();
    full_chain_render_is_noexcept_allocation_free_and_lock_free();
    typed_filter_controls_are_allocation_free_and_lock_free();
    pad_gates_controls_are_allocation_free_and_lock_free();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
