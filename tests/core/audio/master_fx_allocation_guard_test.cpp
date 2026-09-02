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

  std::ifstream master_fx_source("packages/audio-runtime/src/master_fx.cpp");
  std::ifstream engine_source("packages/audio-runtime/src/realtime_engine.cpp");
  const std::string master_fx_text{
      std::istreambuf_iterator<char>{master_fx_source}, {}};
  const std::string engine_text{
      std::istreambuf_iterator<char>{engine_source}, {}};
  for (const auto forbidden : {
           "std::mutex", "std::lock_guard", "std::unique_lock",
           "std::scoped_lock"}) {
    LMDJ_CHECK(master_fx_text.find(forbidden) == std::string::npos);
    LMDJ_CHECK(engine_text.find(forbidden) == std::string::npos);
  }

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

}  // namespace

void* operator new(std::size_t size) { return ordinary_allocation(size); }
void* operator new[](std::size_t size) { return ordinary_allocation(size); }
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
    full_chain_render_is_noexcept_allocation_free_and_lock_free();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
