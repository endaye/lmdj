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
  lmdj::audio::detail::FixedSpscQueue<lmdj::audio::PadControlEvent, 1024> queue;
  std::atomic<bool> producer_done{false};

  std::thread producer([&] {
    for (std::uint64_t sequence = 0; sequence < kEvents; ++sequence) {
      while (!queue.try_push(lmdj::audio::PadControlEvent{
          sequence,
          static_cast<std::uint8_t>(sequence % 64),
          100,
          lmdj::audio::PadControlKind::preview_set,
          lmdj::cooker::ResolvedPlayback{
              1,
              3,
              lmdj::domain::TriggerMode::loop_gate,
              0.5F,
              false,
          },
      })) {
        std::this_thread::yield();
      }
    }
    producer_done.store(true, std::memory_order_release);
  });

  std::uint64_t expected = 0;
  while (expected < kEvents ||
         !producer_done.load(std::memory_order_acquire)) {
    lmdj::audio::PadControlEvent event{};
    if (!queue.try_pop(event)) {
      std::this_thread::yield();
      continue;
    }
    LMDJ_CHECK(event.sequence == expected);
    LMDJ_CHECK(event.slot == expected % 64);
    LMDJ_CHECK(event.velocity == 100);
    LMDJ_CHECK(event.kind == lmdj::audio::PadControlKind::preview_set);
    LMDJ_CHECK(event.playback.start_frame == 1);
    LMDJ_CHECK(event.playback.end_frame == 3);
    LMDJ_CHECK(
        event.playback.trigger_mode == lmdj::domain::TriggerMode::loop_gate);
    LMDJ_CHECK(event.playback.linear_gain == 0.5F);
    LMDJ_CHECK(!event.playback.muted);
    ++expected;
  }
  producer.join();
  LMDJ_CHECK(expected == kEvents);
  LMDJ_CHECK(queue.size_approx() == 0);
}

void transports_all_voice_starts_to_concurrent_bounded_drains() {
  constexpr std::uint64_t kEvents = 100'000;
  constexpr std::uint64_t kMaxInFlightVoices = 1;
  constexpr std::uint64_t kMaxCaptureBacklog = 256;
  constexpr std::uint64_t kMaxOutcomeBacklog = 256;
  constexpr std::uint64_t kMaxVoiceStateBacklog = 512;
  lmdj::audio::RealtimeEngine engine;
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};

  std::atomic<bool> render_done{false};
  std::vector<std::uint64_t> admitted(kEvents);
  std::vector<lmdj::audio::CapturedTriggerEvent> captured(kEvents);
  std::vector<lmdj::audio::RuntimeTriggerOutcomeEvent> outcomes(kEvents);
  std::vector<lmdj::audio::RuntimeVoiceStateEvent> voice_states(kEvents * 2);
  std::size_t captured_count = 0;
  std::size_t outcome_count = 0;
  std::size_t voice_state_count = 0;

  std::thread renderer([&] {
    while (!render_done.load(std::memory_order_acquire)) {
      engine.render(left.data(), right.data(), 1);
    }
  });

  while (engine.capture_telemetry().state !=
         lmdj::audio::CaptureState::active) {
    std::this_thread::yield();
  }

  std::uint64_t admitted_count = 0;
  while (admitted_count < kEvents) {
    bool made_progress = false;
    const auto realtime = engine.telemetry();
    const auto capture = engine.capture_telemetry();
    const auto outcome = engine.trigger_outcome_telemetry();
    const auto voice_state = engine.voice_state_telemetry();
    const auto capture_backlog =
        capture.captured_events >= capture.drained_events
            ? capture.captured_events - capture.drained_events
            : 0;
    const auto outcome_backlog =
        outcome.published_outcomes >= outcome.drained_outcomes
            ? outcome.published_outcomes - outcome.drained_outcomes
            : 0;
    const auto voice_state_backlog =
        voice_state.published_voice_states >= voice_state.drained_voice_states
            ? voice_state.published_voice_states -
                  voice_state.drained_voice_states
            : 0;
    if (admitted_count - realtime.completed_voices < kMaxInFlightVoices &&
        capture_backlog < kMaxCaptureBacklog &&
        outcome_backlog < kMaxOutcomeBacklog &&
        voice_state_backlog < kMaxVoiceStateBacklog) {
      const auto sequence = admitted_count * 3 + 7;
      if (engine.enqueue_control(lmdj::audio::PadControlEvent{
              sequence,
              0,
              100,
              lmdj::audio::PadControlKind::press,
              {},
          }) ==
          lmdj::audio::EnqueueResult::accepted) {
        admitted.at(admitted_count) = sequence;
        ++admitted_count;
        made_progress = true;
      }
    }

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
    const auto voice_state_capacity =
        std::min<std::size_t>(128, voice_states.size() - voice_state_count);
    if (voice_state_capacity != 0) {
      const auto drained = engine.drain_voice_states(
          std::span<lmdj::audio::RuntimeVoiceStateEvent>(
              voice_states.data() + voice_state_count,
              voice_state_capacity));
      voice_state_count += drained;
      made_progress = made_progress || drained != 0;
    }
    if (!made_progress) {
      std::this_thread::yield();
    }
  }

  while (engine.telemetry().completed_voices < kEvents) {
    const auto captured_now = engine.drain_capture(
        std::span<lmdj::audio::CapturedTriggerEvent>(
            captured.data() + captured_count,
            std::min<std::size_t>(
                64, captured.size() - captured_count)));
    const auto outcomes_now = engine.drain_trigger_outcomes(
        std::span<lmdj::audio::RuntimeTriggerOutcomeEvent>(
            outcomes.data() + outcome_count,
            std::min<std::size_t>(
                64, outcomes.size() - outcome_count)));
    const auto voice_states_now = engine.drain_voice_states(
        std::span<lmdj::audio::RuntimeVoiceStateEvent>(
            voice_states.data() + voice_state_count,
            std::min<std::size_t>(
                128, voice_states.size() - voice_state_count)));
    captured_count += captured_now;
    outcome_count += outcomes_now;
    voice_state_count += voice_states_now;
    if (captured_now == 0 && outcomes_now == 0 && voice_states_now == 0) {
      std::this_thread::yield();
    }
  }

  render_done.store(true, std::memory_order_release);
  renderer.join();
  LMDJ_CHECK(engine.disarm_capture().has_value());
  engine.stop();

  while (captured_count < captured.size() ||
         outcome_count < outcomes.size() ||
         voice_state_count < voice_states.size()) {
    const auto captured_now = engine.drain_capture(
        std::span<lmdj::audio::CapturedTriggerEvent>(
            captured.data() + captured_count,
            std::min<std::size_t>(
                64, captured.size() - captured_count)));
    const auto outcomes_now = engine.drain_trigger_outcomes(
        std::span<lmdj::audio::RuntimeTriggerOutcomeEvent>(
            outcomes.data() + outcome_count,
            std::min<std::size_t>(
                64, outcomes.size() - outcome_count)));
    const auto voice_states_now = engine.drain_voice_states(
        std::span<lmdj::audio::RuntimeVoiceStateEvent>(
            voice_states.data() + voice_state_count,
            std::min<std::size_t>(
                128, voice_states.size() - voice_state_count)));
    captured_count += captured_now;
    outcome_count += outcomes_now;
    voice_state_count += voice_states_now;
    if (captured_now == 0 && outcomes_now == 0 && voice_states_now == 0) {
      break;
    }
  }

  LMDJ_CHECK(captured_count == captured.size());
  LMDJ_CHECK(outcome_count == outcomes.size());
  LMDJ_CHECK(voice_state_count == voice_states.size());
  for (std::uint64_t sequence = 0; sequence < kEvents; ++sequence) {
    LMDJ_CHECK(captured.at(sequence).sequence == admitted.at(sequence));
    LMDJ_CHECK(outcomes.at(sequence).sequence == admitted.at(sequence));
    LMDJ_CHECK(
        outcomes.at(sequence).outcome ==
        lmdj::audio::RuntimeTriggerOutcome::voice_started);
    LMDJ_CHECK(outcomes.at(sequence).runtime_frame ==
               captured.at(sequence).frame_offset);
    const auto& started = voice_states.at(sequence * 2);
    const auto& completed = voice_states.at(sequence * 2 + 1);
    LMDJ_CHECK(started.sequence == admitted.at(sequence));
    LMDJ_CHECK(started.slot == 0);
    LMDJ_CHECK(started.state == lmdj::audio::RuntimeVoiceState::started);
    LMDJ_CHECK(started.runtime_frame == captured.at(sequence).frame_offset);
    LMDJ_CHECK(started.source_frame == 0);
    LMDJ_CHECK(completed.sequence == admitted.at(sequence));
    LMDJ_CHECK(completed.slot == 0);
    LMDJ_CHECK(completed.state == lmdj::audio::RuntimeVoiceState::completed);
    LMDJ_CHECK(completed.runtime_frame == started.runtime_frame + 1);
    LMDJ_CHECK(completed.source_frame == 1);
  }
  const auto realtime = engine.telemetry();
  const auto capture = engine.capture_telemetry();
  const auto outcome = engine.trigger_outcome_telemetry();
  const auto voice_state = engine.voice_state_telemetry();
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
  LMDJ_CHECK(voice_state.published_voice_states == kEvents * 2);
  LMDJ_CHECK(voice_state.drained_voice_states == kEvents * 2);
  LMDJ_CHECK(voice_state.voice_state_drops == 0);
  LMDJ_CHECK(capture.state == lmdj::audio::CaptureState::idle);
  LMDJ_CHECK(capture.captured_events == kEvents);
  LMDJ_CHECK(capture.drained_events == kEvents);
  LMDJ_CHECK(capture.capture_drops == 0);
}

void corrupted_voice_state_stream_never_returns_a_partial_drain() {
  std::atomic<lmdj::audio::RuntimeVoiceStateStreamState> state{
      lmdj::audio::RuntimeVoiceStateStreamState::healthy};
  std::array<lmdj::audio::RuntimeVoiceStateEvent, 2> output{};
  std::size_t pops = 0;
  const auto drained = lmdj::audio::detail::drain_voice_states_fail_closed(
      state,
      output,
      [&](lmdj::audio::RuntimeVoiceStateEvent& event) noexcept {
        if (pops != 0) {
          return false;
        }
        event = lmdj::audio::RuntimeVoiceStateEvent{
            71,
            3,
            lmdj::audio::RuntimeVoiceState::started,
            11,
            5,
        };
        ++pops;
        state.store(
            lmdj::audio::RuntimeVoiceStateStreamState::corrupted,
            std::memory_order_release);
        return true;
      });

  LMDJ_CHECK(pops == 1);
  LMDJ_CHECK(output.at(0).sequence == 71);
  LMDJ_CHECK(drained == 0);
}

}  // namespace

int main() {
  preserves_all_trigger_events_under_spsc_contention();
  transports_all_voice_starts_to_concurrent_bounded_drains();
  corrupted_voice_state_stream_never_returns_a_partial_drain();
}
