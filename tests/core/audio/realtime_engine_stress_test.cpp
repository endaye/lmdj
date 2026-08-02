#include <lmdj/audio/realtime_engine.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <span>
#include <thread>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

void preserves_all_trigger_events_under_spsc_contention() {
  constexpr std::uint64_t kEvents = 1'000'000;
  lmdj::audio::detail::FixedSpscQueue<lmdj::audio::TriggerEvent, 1024> queue;
  std::atomic<bool> producer_done{false};

  std::thread producer([&] {
    for (std::uint64_t sequence = 0; sequence < kEvents; ++sequence) {
      while (!queue.try_push(lmdj::audio::TriggerEvent{sequence, 0, 100})) {
        std::this_thread::yield();
      }
    }
    producer_done.store(true, std::memory_order_release);
  });

  std::uint64_t expected = 0;
  while (expected < kEvents ||
         !producer_done.load(std::memory_order_acquire)) {
    lmdj::audio::TriggerEvent event{};
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
}

void transports_all_voice_starts_to_a_concurrent_capture_drain() {
  constexpr std::uint64_t kEvents = 100'000;
  constexpr std::uint64_t kMaxInFlightVoices = 64;
  constexpr std::uint64_t kMaxCaptureBacklog = 256;
  lmdj::audio::RealtimeEngine engine;
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(
      engine.capture_telemetry().state == lmdj::audio::CaptureState::active);

  std::atomic<bool> producer_done{false};
  std::atomic<bool> capture_done{false};
  std::vector<lmdj::audio::CapturedTriggerEvent> captured(kEvents);
  std::size_t captured_count = 0;

  std::thread producer([&] {
    for (std::uint64_t sequence = 0; sequence < kEvents;) {
      const auto telemetry = engine.telemetry();
      if (sequence - telemetry.completed_voices >= kMaxInFlightVoices) {
        std::this_thread::yield();
        continue;
      }
      if (engine.enqueue(lmdj::audio::TriggerEvent{sequence, 0, 100}) ==
          lmdj::audio::EnqueueResult::accepted) {
        ++sequence;
      } else {
        std::this_thread::yield();
      }
    }
    producer_done.store(true, std::memory_order_release);
  });

  std::thread renderer([&] {
    while (!producer_done.load(std::memory_order_acquire) ||
           engine.telemetry().dequeued_events < kEvents) {
      const auto capture = engine.capture_telemetry();
      if (capture.captured_events - capture.drained_events >=
          kMaxCaptureBacklog) {
        std::this_thread::yield();
        continue;
      }
      engine.render(left.data(), right.data(), 1);
    }
  });

  std::thread drain([&] {
    while (!capture_done.load(std::memory_order_acquire)) {
      const auto capacity =
          std::min<std::size_t>(64, captured.size() - captured_count);
      if (capacity == 0 ||
          engine.drain_capture(std::span<lmdj::audio::CapturedTriggerEvent>(
              captured.data() + captured_count,
              capacity)) == 0) {
        std::this_thread::yield();
        continue;
      }
      captured_count = static_cast<std::size_t>(
          engine.capture_telemetry().drained_events);
    }
    while (captured_count < captured.size()) {
      const auto drained = engine.drain_capture(
          std::span<lmdj::audio::CapturedTriggerEvent>(
              captured.data() + captured_count,
              captured.size() - captured_count));
      if (drained == 0) {
        break;
      }
      captured_count += drained;
    }
  });

  producer.join();
  renderer.join();
  LMDJ_CHECK(engine.disarm_capture().has_value());
  engine.render(left.data(), right.data(), 1);
  capture_done.store(true, std::memory_order_release);
  drain.join();

  LMDJ_CHECK(captured_count == captured.size());
  for (std::uint64_t sequence = 0; sequence < kEvents; ++sequence) {
    LMDJ_CHECK(captured.at(sequence).sequence == sequence);
  }
  const auto realtime = engine.telemetry();
  const auto capture = engine.capture_telemetry();
  LMDJ_CHECK(realtime.enqueued_events == kEvents);
  LMDJ_CHECK(realtime.dequeued_events == kEvents);
  LMDJ_CHECK(realtime.started_voices == kEvents);
  LMDJ_CHECK(realtime.completed_voices == kEvents);
  LMDJ_CHECK(realtime.queue_drops == 0);
  LMDJ_CHECK(realtime.voice_drops == 0);
  LMDJ_CHECK(capture.state == lmdj::audio::CaptureState::idle);
  LMDJ_CHECK(capture.captured_events == kEvents);
  LMDJ_CHECK(capture.drained_events == kEvents);
  LMDJ_CHECK(capture.capture_drops == 0);
}

}  // namespace

int main() {
  preserves_all_trigger_events_under_spsc_contention();
  transports_all_voice_starts_to_a_concurrent_capture_drain();
}
