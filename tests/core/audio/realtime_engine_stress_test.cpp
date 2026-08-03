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

void transports_all_voice_starts_to_concurrent_bounded_drains() {
  constexpr std::uint64_t kEvents = 100'000;
  constexpr std::uint64_t kMaxInFlightVoices = 64;
  constexpr std::uint64_t kMaxCaptureBacklog = 256;
  constexpr std::uint64_t kMaxOutcomeBacklog = 256;
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
  std::atomic<bool> drain_done{false};
  std::vector<std::uint64_t> admitted(kEvents);
  std::vector<lmdj::audio::CapturedTriggerEvent> captured(kEvents);
  std::vector<lmdj::audio::RuntimeTriggerOutcomeEvent> outcomes(kEvents);
  std::size_t captured_count = 0;
  std::size_t outcome_count = 0;

  std::thread producer([&] {
    for (std::uint64_t admitted_count = 0; admitted_count < kEvents;) {
      const auto telemetry = engine.telemetry();
      if (admitted_count - telemetry.completed_voices >=
          kMaxInFlightVoices) {
        std::this_thread::yield();
        continue;
      }
      const auto sequence = admitted_count * 3 + 7;
      if (engine.enqueue(lmdj::audio::TriggerEvent{sequence, 0, 100}) ==
          lmdj::audio::EnqueueResult::accepted) {
        admitted.at(admitted_count) = sequence;
        ++admitted_count;
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
      const auto outcomes = engine.trigger_outcome_telemetry();
      const auto capture_backlog =
          capture.captured_events >= capture.drained_events
              ? capture.captured_events - capture.drained_events
              : 0;
      const auto outcome_backlog =
          outcomes.published_outcomes >= outcomes.drained_outcomes
              ? outcomes.published_outcomes - outcomes.drained_outcomes
              : 0;
      if (capture_backlog >= kMaxCaptureBacklog ||
          outcome_backlog >= kMaxOutcomeBacklog) {
        std::this_thread::yield();
        continue;
      }
      engine.render(left.data(), right.data(), 1);
    }
  });

  std::thread drain([&] {
    while (!drain_done.load(std::memory_order_acquire)) {
      bool made_progress = false;
      const auto capture_capacity =
          std::min<std::size_t>(64, captured.size() - captured_count);
      if (capture_capacity != 0) {
        const auto drained = engine.drain_capture(
            std::span<lmdj::audio::CapturedTriggerEvent>(
              captured.data() + captured_count,
              capture_capacity));
        captured_count += drained;
        made_progress = made_progress || drained != 0;
      }
      const auto outcome_capacity =
          std::min<std::size_t>(64, outcomes.size() - outcome_count);
      if (outcome_capacity != 0) {
        const auto drained = engine.drain_trigger_outcomes(
            std::span<lmdj::audio::RuntimeTriggerOutcomeEvent>(
                outcomes.data() + outcome_count,
                outcome_capacity));
        outcome_count += drained;
        made_progress = made_progress || drained != 0;
      }
      if (!made_progress) {
        std::this_thread::yield();
      }
    }
    while (captured_count < captured.size() ||
           outcome_count < outcomes.size()) {
      const auto captured_now = engine.drain_capture(
          std::span<lmdj::audio::CapturedTriggerEvent>(
              captured.data() + captured_count,
              captured.size() - captured_count));
      const auto outcomes_now = engine.drain_trigger_outcomes(
          std::span<lmdj::audio::RuntimeTriggerOutcomeEvent>(
              outcomes.data() + outcome_count,
              outcomes.size() - outcome_count));
      captured_count += captured_now;
      outcome_count += outcomes_now;
      if (captured_now == 0 && outcomes_now == 0) {
        break;
      }
    }
  });

  producer.join();
  renderer.join();
  LMDJ_CHECK(engine.disarm_capture().has_value());
  engine.render(left.data(), right.data(), 1);
  drain_done.store(true, std::memory_order_release);
  drain.join();

  LMDJ_CHECK(captured_count == captured.size());
  LMDJ_CHECK(outcome_count == outcomes.size());
  for (std::uint64_t sequence = 0; sequence < kEvents; ++sequence) {
    LMDJ_CHECK(captured.at(sequence).sequence == admitted.at(sequence));
    LMDJ_CHECK(outcomes.at(sequence).sequence == admitted.at(sequence));
    LMDJ_CHECK(
        outcomes.at(sequence).outcome ==
        lmdj::audio::RuntimeTriggerOutcome::voice_started);
    LMDJ_CHECK(outcomes.at(sequence).runtime_frame ==
               captured.at(sequence).frame_offset);
  }
  const auto realtime = engine.telemetry();
  const auto capture = engine.capture_telemetry();
  const auto outcome = engine.trigger_outcome_telemetry();
  LMDJ_CHECK(realtime.enqueued_events == kEvents);
  LMDJ_CHECK(realtime.dequeued_events == kEvents);
  LMDJ_CHECK(realtime.started_voices == kEvents);
  LMDJ_CHECK(realtime.completed_voices == kEvents);
  LMDJ_CHECK(realtime.queue_drops == 0);
  LMDJ_CHECK(realtime.voice_drops == 0);
  LMDJ_CHECK(
      realtime.dequeued_events ==
      outcome.published_outcomes + outcome.runtime_outcome_drops);
  LMDJ_CHECK(realtime.started_voices + realtime.voice_drops ==
             realtime.dequeued_events);
  LMDJ_CHECK(outcome.published_outcomes == kEvents);
  LMDJ_CHECK(outcome.drained_outcomes == kEvents);
  LMDJ_CHECK(outcome.runtime_outcome_drops == 0);
  LMDJ_CHECK(capture.state == lmdj::audio::CaptureState::idle);
  LMDJ_CHECK(capture.captured_events == kEvents);
  LMDJ_CHECK(capture.drained_events == kEvents);
  LMDJ_CHECK(capture.capture_drops == 0);
}

}  // namespace

int main() {
  preserves_all_trigger_events_under_spsc_contention();
  transports_all_voice_starts_to_concurrent_bounded_drains();
}
