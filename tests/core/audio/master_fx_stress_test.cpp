#include <lmdj/audio/master_fx.hpp>
#include <lmdj/audio/realtime_engine.hpp>

#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <exception>
#include <iostream>
#include <thread>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::FxEnqueueResult;
using lmdj::audio::FxGesture;
using lmdj::audio::FxGestureKind;
using lmdj::audio::RealtimeEngine;

#ifndef LMDJ_MASTER_FX_VERIFY_REALTIME_DEADLINE
#error "Master FX stress timing policy must be selected by CMake"
#endif

constexpr bool kVerifyRealtimeDeadline =
    LMDJ_MASTER_FX_VERIFY_REALTIME_DEADLINE != 0;

std::chrono::nanoseconds current_thread_cpu_time() {
  timespec observed{};
  LMDJ_CHECK(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &observed) == 0);
  return std::chrono::seconds(observed.tv_sec) +
         std::chrono::nanoseconds(observed.tv_nsec);
}

void all_eight_effects_sustain_maximum_gesture_rate_without_underruns() {
  constexpr std::uint32_t kFramesPerQuantum = 128;
  constexpr std::uint32_t kSimulatedSeconds = 10;
  constexpr std::uint32_t kQuanta =
      (48'000U * kSimulatedSeconds) / kFramesPerQuantum;
  RealtimeEngine engine;
  std::vector<float> sample(
      static_cast<std::size_t>(kQuanta) * kFramesPerQuantum, 0.0F);
  for (std::size_t frame = 0; frame < sample.size(); ++frame) {
    sample[frame] =
        static_cast<float>(static_cast<std::int32_t>(frame % 127U) - 63) /
        96.0F;
  }
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.prepare_master_fx(173).has_value());
  LMDJ_CHECK(engine.start().has_value());

  std::atomic<bool> render_failed{false};
  std::atomic<bool> heard_processed_voice{false};
  std::atomic<std::uint64_t> callback_overruns{0};
  std::atomic<std::uint32_t> control_ready_quanta{0};
  std::atomic<std::uint32_t> rendered_quanta{0};
  std::atomic<std::uint32_t> active_voice_quanta{0};
  std::uint64_t accepted = 0;

  for (const auto fx : lmdj::audio::kFxChainOrder) {
    LMDJ_CHECK(engine.enqueue_fx_gesture(
                   FxGesture{FxGestureKind::engage, fx, 1'000}) ==
               FxEnqueueResult::accepted);
    ++accepted;
  }
  LMDJ_CHECK(
      engine.enqueue(lmdj::audio::TriggerEvent{1, 0, 127}) ==
      lmdj::audio::EnqueueResult::accepted);

  std::thread renderer([&] {
    std::array<float, kFramesPerQuantum> left{};
    std::array<float, kFramesPerQuantum> right{};
    constexpr auto kCallbackDeadline = std::chrono::nanoseconds{
        1'000'000'000ULL * kFramesPerQuantum / 48'000U};
    for (std::uint32_t quantum = 0; quantum < kQuanta; ++quantum) {
      while (control_ready_quanta.load(std::memory_order_acquire) <= quantum) {
        std::this_thread::yield();
      }
      // A shared CI runner may deschedule this thread for longer than an audio
      // quantum, so the production timing gate uses thread CPU time. Sanitizer
      // builds retain this concurrent stress path for safety checks but cannot
      // represent production callback timing because every memory access is
      // instrumented.
      const auto started = kVerifyRealtimeDeadline
                               ? current_thread_cpu_time()
                               : std::chrono::nanoseconds::zero();
      engine.render(left.data(), right.data(), left.size());
      const auto elapsed = kVerifyRealtimeDeadline
                               ? current_thread_cpu_time() - started
                               : std::chrono::nanoseconds::zero();
      if (kVerifyRealtimeDeadline && elapsed > kCallbackDeadline) {
        callback_overruns.fetch_add(1, std::memory_order_relaxed);
      }
      for (std::size_t frame = 0; frame < left.size(); ++frame) {
        if (!std::isfinite(left[frame]) || !std::isfinite(right[frame])) {
          render_failed.store(true, std::memory_order_release);
        }
        if (std::abs(left[frame]) > 0.00001F ||
            std::abs(right[frame]) > 0.00001F) {
          heard_processed_voice.store(true, std::memory_order_relaxed);
        }
      }
      const auto realtime = engine.telemetry();
      if (realtime.active_voices == 1 ||
          (quantum + 1U == kQuanta && realtime.completed_voices == 1)) {
        active_voice_quanta.fetch_add(1, std::memory_order_relaxed);
      }
      rendered_quanta.store(quantum + 1U, std::memory_order_release);
    }
  });

  auto enqueue = [&](FxGesture gesture) {
    auto result = FxEnqueueResult::queue_full;
    while (result == FxEnqueueResult::queue_full) {
      result = engine.enqueue_fx_gesture(gesture);
      if (result == FxEnqueueResult::queue_full) {
        std::this_thread::yield();
      }
    }
    LMDJ_CHECK(result == FxEnqueueResult::accepted);
    ++accepted;
  };

  for (std::uint32_t round = 0; round < kQuanta; ++round) {
    for (std::size_t index = 0; index < lmdj::audio::kFxChainOrder.size();
         ++index) {
      const auto fx = lmdj::audio::kFxChainOrder[index];
      enqueue(FxGesture{
          FxGestureKind::move,
          fx,
          static_cast<std::uint16_t>((round * 17U + index) % 1'001U)});
    }
    control_ready_quanta.store(round + 1U, std::memory_order_release);
    while (rendered_quanta.load(std::memory_order_acquire) <= round) {
      std::this_thread::yield();
    }
  }
  renderer.join();
  engine.stop();

  const auto fx = engine.master_fx_telemetry();
  const auto realtime = engine.telemetry();
  LMDJ_CHECK(!render_failed.load(std::memory_order_acquire));
  LMDJ_CHECK(heard_processed_voice.load(std::memory_order_relaxed));
  LMDJ_CHECK(callback_overruns.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(active_voice_quanta.load(std::memory_order_relaxed) == kQuanta);
  LMDJ_CHECK(fx.enqueued_gestures == accepted);
  LMDJ_CHECK(fx.dequeued_gestures == accepted);
  LMDJ_CHECK(fx.queued_gestures == 0);
  LMDJ_CHECK(fx.processed_frames == realtime.rendered_frames);
  LMDJ_CHECK(fx.processed_frames >= kFramesPerQuantum);
  LMDJ_CHECK(realtime.started_voices == 1);
  LMDJ_CHECK(realtime.completed_voices == 1);
}

}  // namespace

int main() {
  try {
    all_eight_effects_sustain_maximum_gesture_rate_without_underruns();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
