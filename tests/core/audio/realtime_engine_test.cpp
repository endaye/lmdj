#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/audio/prepared_sample_bank.hpp>

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <new>
#include <span>
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

using lmdj::audio::EnqueueResult;
using lmdj::audio::CapturedTriggerEvent;
using lmdj::audio::CaptureState;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::RealtimeState;
using lmdj::audio::RuntimeTriggerOutcome;
using lmdj::audio::RuntimeTriggerOutcomeEvent;
using lmdj::audio::TriggerEvent;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::ProjectId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";

PreparedSampleBank bank_with_sample(
    std::uint64_t revision,
    std::span<const float> sample,
    std::uint8_t slot = 0) {
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, revision);
  LMDJ_CHECK(bank.set_sample(slot, sample).has_value());
  return bank;
}

void plays_a_sample_and_reports_render_telemetry() {
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

  std::array<RuntimeTriggerOutcomeEvent, 1> outcomes{};
  LMDJ_CHECK(engine.drain_trigger_outcomes(outcomes) == 1);
  LMDJ_CHECK(outcomes.at(0).sequence == 9);
  LMDJ_CHECK(
      outcomes.at(0).outcome == RuntimeTriggerOutcome::voice_started);
  LMDJ_CHECK(outcomes.at(0).runtime_frame == 0);

  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.enqueued_events == 1);
  LMDJ_CHECK(telemetry.dequeued_events == 1);
  LMDJ_CHECK(telemetry.started_voices == 1);
  LMDJ_CHECK(telemetry.completed_voices == 1);
  LMDJ_CHECK(telemetry.active_voices == 0);
  LMDJ_CHECK(telemetry.callback_count == 2);
  LMDJ_CHECK(telemetry.rendered_frames == 2);
  LMDJ_CHECK(telemetry.max_callback_frames == 1);
  const auto outcomes_telemetry = engine.trigger_outcome_telemetry();
  LMDJ_CHECK(outcomes_telemetry.published_outcomes == 1);
  LMDJ_CHECK(outcomes_telemetry.drained_outcomes == 1);
  LMDJ_CHECK(outcomes_telemetry.runtime_outcome_drops == 0);
}

void rejects_invalid_samples_and_running_time_mutation() {
  RealtimeEngine engine;
  const std::array<float, 1> valid{0.25F};
  const std::array<float, 1> nan{std::numeric_limits<float>::quiet_NaN()};
  const std::array<float, 1> infinity{
      std::numeric_limits<float>::infinity()};
  const std::span<const float> empty;

  const auto invalid_slot = engine.load_sample(64, valid);
  LMDJ_CHECK(!invalid_slot.has_value());
  LMDJ_CHECK(invalid_slot.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(!engine.load_sample(0, empty).has_value());
  LMDJ_CHECK(!engine.load_sample(0, nan).has_value());
  LMDJ_CHECK(!engine.load_sample(0, infinity).has_value());
  LMDJ_CHECK(!engine.clear_sample(64).has_value());

  LMDJ_CHECK(engine.load_sample(0, valid).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(!engine.load_sample(0, valid).has_value());
  LMDJ_CHECK(!engine.clear_sample(0).has_value());
  LMDJ_CHECK(!engine.start().has_value());
}

void supports_exact_64_slot_boundary() {
  static_assert(lmdj::audio::kRealtimeSampleSlots == 64);

  RealtimeEngine engine;
  const std::array<float, 1> sample{0.625F};
  LMDJ_CHECK(engine.load_sample(63, sample).has_value());
  const auto invalid_load = engine.load_sample(64, sample);
  LMDJ_CHECK(!invalid_load.has_value());
  LMDJ_CHECK(invalid_load.error().code == ErrorCode::invalid_argument);

  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 63, 127}) ==
             EnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 64, 127}) ==
             EnqueueResult::invalid_slot);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] == 0.625F && right[0] == 0.625F);

  engine.stop();
  LMDJ_CHECK(engine.clear_sample(63).has_value());
  const auto invalid_clear = engine.clear_sample(64);
  LMDJ_CHECK(!invalid_clear.has_value());
  LMDJ_CHECK(invalid_clear.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{3, 63, 127}) ==
             EnqueueResult::sample_unavailable);
}

void validates_events_and_cleared_slots() {
  RealtimeEngine engine;
  const std::array<float, 1> sample{1.0F};

  LMDJ_CHECK(engine.enqueue(TriggerEvent{0, 0, 127}) ==
             EnqueueResult::not_running);
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.load_sample(1, sample).has_value());
  LMDJ_CHECK(engine.clear_sample(1).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 64, 127}) ==
             EnqueueResult::invalid_slot);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 0}) ==
             EnqueueResult::invalid_velocity);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{3, 0, 128}) ==
             EnqueueResult::invalid_velocity);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{4, 2, 127}) ==
             EnqueueResult::sample_unavailable);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{5, 1, 127}) ==
             EnqueueResult::sample_unavailable);

  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.invalid_events == 5);
  LMDJ_CHECK(telemetry.stopped_rejections == 0);
}

void applies_velocity_gain_and_clamps_after_mixing() {
  RealtimeEngine engine;
  const std::array<float, 1> unit{1.0F};
  LMDJ_CHECK(engine.load_sample(0, unit).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 64}) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] == 64.0F / 127.0F);
  LMDJ_CHECK(right[0] == 64.0F / 127.0F);

  engine.stop();
  const std::array<float, 1> loud{0.8F};
  LMDJ_CHECK(engine.load_sample(0, loud).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{3, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] == 1.0F && right[0] == 1.0F);
}

void reports_queue_capacity_and_drops() {
  RealtimeEngine engine;
  const std::array<float, 1> sample{1.0F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  for (std::uint64_t sequence = 0; sequence < 1'024; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1'024, 0, 127}) ==
             EnqueueResult::queue_full);

  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.enqueued_events == 1'024);
  LMDJ_CHECK(telemetry.queued_events == 1'024);
  LMDJ_CHECK(telemetry.queue_drops == 1);
}

void caps_simultaneous_voices_and_mixes_each_admitted_voice() {
  RealtimeEngine engine;
  constexpr float kVoiceAmplitude = 1.0F / 1'024.0F;
  constexpr float kExpectedMix = 128.0F / 1'024.0F;
  const std::array<float, 2> sample{kVoiceAmplitude, kVoiceAmplitude};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  for (std::uint64_t sequence = 0; sequence < 129; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);

  LMDJ_CHECK(left[0] == kExpectedMix);
  LMDJ_CHECK(right[0] == kExpectedMix);
  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.started_voices == 128);
  LMDJ_CHECK(telemetry.active_voices == 128);
  LMDJ_CHECK(telemetry.voice_drops == 1);
}

void publishes_ordered_mixed_outcomes_at_128_frame_boundaries() {
  RealtimeEngine engine;
  const std::array<float, 256> sample{};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());

  for (std::uint64_t sequence = 1; sequence <= 128; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  engine.render(left.data(), right.data(), 128);

  LMDJ_CHECK(engine.enqueue(TriggerEvent{129, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 128);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{130, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 128);

  std::array<RuntimeTriggerOutcomeEvent, 130> outcomes{};
  LMDJ_CHECK(engine.drain_trigger_outcomes(outcomes) == outcomes.size());
  for (std::uint64_t sequence = 1; sequence <= 128; ++sequence) {
    const auto& outcome = outcomes.at(sequence - 1);
    LMDJ_CHECK(outcome.sequence == sequence);
    LMDJ_CHECK(outcome.outcome == RuntimeTriggerOutcome::voice_started);
    LMDJ_CHECK(outcome.runtime_frame == 0);
  }
  LMDJ_CHECK(outcomes.at(128).sequence == 129);
  LMDJ_CHECK(
      outcomes.at(128).outcome == RuntimeTriggerOutcome::voice_capacity);
  LMDJ_CHECK(outcomes.at(128).runtime_frame == 128);
  LMDJ_CHECK(outcomes.at(129).sequence == 130);
  LMDJ_CHECK(
      outcomes.at(129).outcome == RuntimeTriggerOutcome::voice_started);
  LMDJ_CHECK(outcomes.at(129).runtime_frame == 256);

  const auto realtime = engine.telemetry();
  const auto outcome_telemetry = engine.trigger_outcome_telemetry();
  LMDJ_CHECK(realtime.dequeued_events == outcomes.size());
  LMDJ_CHECK(realtime.started_voices == 129);
  LMDJ_CHECK(realtime.voice_drops == 1);
  LMDJ_CHECK(outcome_telemetry.published_outcomes == outcomes.size());
  LMDJ_CHECK(outcome_telemetry.drained_outcomes == outcomes.size());
  LMDJ_CHECK(outcome_telemetry.runtime_outcome_drops == 0);
}

void outcome_ring_reports_capacity_drop_and_restart_resets_it() {
  static_assert(lmdj::audio::kRealtimeTriggerOutcomeCapacity == 4'096);
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};

  for (std::uint64_t sequence = 1;
       sequence <= lmdj::audio::kRealtimeTriggerOutcomeCapacity + 1;
       ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
    engine.render(left.data(), right.data(), 1);
  }

  const auto full = engine.trigger_outcome_telemetry();
  LMDJ_CHECK(
      full.published_outcomes == lmdj::audio::kRealtimeTriggerOutcomeCapacity);
  LMDJ_CHECK(full.drained_outcomes == 0);
  LMDJ_CHECK(full.runtime_outcome_drops == 1);
  LMDJ_CHECK(engine.telemetry().dequeued_events ==
             full.published_outcomes + full.runtime_outcome_drops);

  std::array<RuntimeTriggerOutcomeEvent, 1> first{};
  LMDJ_CHECK(engine.drain_trigger_outcomes(first) == 1);
  LMDJ_CHECK(first.at(0).sequence == 1);
  LMDJ_CHECK(first.at(0).outcome == RuntimeTriggerOutcome::voice_started);
  LMDJ_CHECK(first.at(0).runtime_frame == 0);

  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  const auto reset = engine.trigger_outcome_telemetry();
  LMDJ_CHECK(reset.published_outcomes == 0);
  LMDJ_CHECK(reset.drained_outcomes == 0);
  LMDJ_CHECK(reset.runtime_outcome_drops == 0);
  LMDJ_CHECK(engine.drain_trigger_outcomes(first) == 0);
}

void completes_a_sample_across_callback_blocks() {
  RealtimeEngine engine;
  const std::array<float, 5> sample{0.1F, 0.2F, 0.3F, 0.4F, 0.5F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 3> left{};
  std::array<float, 3> right{};
  engine.render(left.data(), right.data(), 2);
  LMDJ_CHECK(left[0] == 0.1F && left[1] == 0.2F);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);
  engine.render(left.data(), right.data(), 3);
  LMDJ_CHECK(left[0] == 0.3F && left[1] == 0.4F && left[2] == 0.5F);
  LMDJ_CHECK(engine.telemetry().completed_voices == 1);
  LMDJ_CHECK(engine.telemetry().max_callback_frames == 3);
}

void publishes_sample_banks_only_at_safe_render_boundaries() {
  static_assert(lmdj::audio::kRealtimeBankCapacity == 4);
  static_assert(lmdj::audio::kRealtimePublishQueueCapacity == 4);
  RealtimeEngine engine;
  const std::array<float, 3> old_sample{0.1F, 0.2F, 0.1F};
  auto first = bank_with_sample(10, old_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(first)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.bank_telemetry().current_generation == 1);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) == 0.1F);

  const std::array<float, 1> new_sample{0.4F};
  auto second = bank_with_sample(11, new_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(second)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.bank_telemetry().pending_publications == 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::bank_transition);

  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) == 0.2F);
  LMDJ_CHECK(engine.bank_telemetry().current_generation == 2);
  LMDJ_CHECK(engine.bank_telemetry().pending_publications == 0);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{3, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) == 0.5F);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(engine.reclaim_retired_banks() == 1);
  LMDJ_CHECK(engine.bank_telemetry().reclaimed_banks == 1);
  LMDJ_CHECK(engine.reclaim_retired_banks() == 0);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{4, 0, 127}) ==
             EnqueueResult::accepted);
}

void rejects_publication_until_trigger_queue_is_empty() {
  RealtimeEngine engine;
  const std::array<float, 1> first_sample{0.25F};
  auto first = bank_with_sample(20, first_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(first)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  const std::array<float, 1> second_sample{0.75F};
  auto second = bank_with_sample(21, second_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(second)) ==
             PublishResult::events_pending);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) == 0.25F);

  LMDJ_CHECK(engine.publish_sample_bank(std::move(second)) ==
             PublishResult::accepted);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) == 0.75F);
}

void applies_explicit_bank_slot_backpressure_until_reclaimed() {
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.125F};
  for (std::uint64_t revision = 1; revision <= 4; ++revision) {
    auto bank = bank_with_sample(revision, sample);
    LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
               PublishResult::accepted);
    if (revision == 1) {
      LMDJ_CHECK(engine.start().has_value());
    } else {
      std::array<float, 1> left{};
      std::array<float, 1> right{};
      engine.render(left.data(), right.data(), 1);
    }
  }
  auto fifth = bank_with_sample(5, sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(fifth)) ==
             PublishResult::bank_slots_full);
  LMDJ_CHECK(engine.bank_telemetry().bank_slot_rejections == 1);
  LMDJ_CHECK(engine.reclaim_retired_banks() == 3);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(fifth)) ==
             PublishResult::accepted);
}

void reports_exact_bytes_for_non_fifo_heterogeneous_bank_reclaim() {
  RealtimeEngine engine;
  const std::array<float, 512> older_large_sample{};
  const std::array<float, 1> newer_small_sample{};
  const std::array<float, 2> current_sample{};

  auto older_large = bank_with_sample(40, older_large_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(older_large)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 512> left{};
  std::array<float, 512> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);

  auto newer_small = bank_with_sample(41, newer_small_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(newer_small)) ==
             PublishResult::accepted);
  engine.render(left.data(), right.data(), 1);

  auto current = bank_with_sample(42, current_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(current)) ==
             PublishResult::accepted);
  engine.render(left.data(), right.data(), 1);

  const auto out_of_order = engine.reclaim_retired_bank_telemetry();
  LMDJ_CHECK(out_of_order.count == 1);
  LMDJ_CHECK(out_of_order.decoded_pcm_bytes == sizeof(float));
  LMDJ_CHECK(engine.telemetry().active_voices == 1);

  engine.render(left.data(), right.data(), 509);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  const auto older_after_voice = engine.reclaim_retired_bank_telemetry();
  LMDJ_CHECK(older_after_voice.count == 1);
  LMDJ_CHECK(
      older_after_voice.decoded_pcm_bytes ==
      older_large_sample.size() * sizeof(float));
  LMDJ_CHECK(engine.reclaim_retired_bank_telemetry().count == 0);
  LMDJ_CHECK(engine.bank_telemetry().reclaimed_banks == 2);
}

void captures_voice_starts_at_exact_runtime_frames_and_disarms_at_end() {
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.25F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  LMDJ_CHECK(engine.capture_telemetry().state == CaptureState::arm_pending);

  std::array<float, 6> left{};
  std::array<float, 6> right{};
  engine.render(left.data(), right.data(), 4);
  LMDJ_CHECK(engine.capture_telemetry().state == CaptureState::active);
  LMDJ_CHECK(engine.capture_telemetry().capture_origin_frame == 0);
  engine.render(left.data(), right.data(), 6);

  LMDJ_CHECK(engine.enqueue(TriggerEvent{7, 0, 100}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 3);
  LMDJ_CHECK(engine.disarm_capture().has_value());
  LMDJ_CHECK(engine.capture_telemetry().state ==
             CaptureState::disarm_pending);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{8, 0, 110}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 2);
  LMDJ_CHECK(engine.capture_telemetry().state == CaptureState::idle);

  LMDJ_CHECK(engine.enqueue(TriggerEvent{9, 0, 120}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  std::array<CapturedTriggerEvent, 3> captured{};
  LMDJ_CHECK(engine.drain_capture(captured) == 2);
  LMDJ_CHECK(captured.at(0).sequence == 7);
  LMDJ_CHECK(captured.at(0).slot == 0);
  LMDJ_CHECK(captured.at(0).velocity == 100);
  LMDJ_CHECK(captured.at(0).frame_offset == 10);
  LMDJ_CHECK(captured.at(1).sequence == 8);
  LMDJ_CHECK(captured.at(1).velocity == 110);
  LMDJ_CHECK(captured.at(1).frame_offset == 13);
  const auto telemetry = engine.capture_telemetry();
  LMDJ_CHECK(telemetry.captured_events == 2);
  LMDJ_CHECK(telemetry.drained_events == 2);
  LMDJ_CHECK(telemetry.capture_drops == 0);
}

void captures_only_successfully_allocated_voices() {
  RealtimeEngine engine;
  const std::array<float, 2> sample{0.1F, 0.2F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);

  for (std::uint64_t sequence = 0; sequence < 128; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{128, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);

  std::array<CapturedTriggerEvent, 129> captured{};
  LMDJ_CHECK(engine.drain_capture(captured) == 128);
  for (std::uint64_t sequence = 0; sequence < 128; ++sequence) {
    LMDJ_CHECK(captured.at(sequence).sequence == sequence);
  }
  LMDJ_CHECK(engine.capture_telemetry().captured_events == 128);
  LMDJ_CHECK(engine.telemetry().voice_drops == 1);
}

void capture_overflow_corrupts_and_restart_clears_stale_events() {
  static_assert(lmdj::audio::kRealtimeCaptureCapacity == 4'096);
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);

  for (std::uint64_t sequence = 1;
       sequence <= lmdj::audio::kRealtimeCaptureCapacity;
       ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
    engine.render(left.data(), right.data(), 1);
  }
  LMDJ_CHECK(engine.enqueue(TriggerEvent{4'097, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  const auto corrupted = engine.capture_telemetry();
  LMDJ_CHECK(corrupted.state == CaptureState::corrupted);
  LMDJ_CHECK(corrupted.captured_events == 4'096);
  LMDJ_CHECK(corrupted.capture_drops == 1);

  std::array<CapturedTriggerEvent, 4'095> captured{};
  LMDJ_CHECK(engine.drain_capture(captured) == captured.size());
  for (std::uint64_t index = 0; index < captured.size(); ++index) {
    LMDJ_CHECK(captured.at(index).sequence == index + 1);
    LMDJ_CHECK(captured.at(index).frame_offset == index + 1);
  }

  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  const auto reset = engine.capture_telemetry();
  LMDJ_CHECK(reset.state == CaptureState::idle);
  LMDJ_CHECK(reset.captured_events == 0);
  LMDJ_CHECK(reset.drained_events == 0);
  LMDJ_CHECK(reset.capture_drops == 0);
  LMDJ_CHECK(engine.drain_capture(captured) == 0);
}

void stop_cancels_queued_events_and_active_voices() {
  RealtimeEngine engine;
  const std::array<float, 3> sample{0.1F, 0.2F, 0.3F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::accepted);
  engine.stop();

  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.state == RealtimeState::stopped);
  LMDJ_CHECK(telemetry.cancelled_events == 1);
  LMDJ_CHECK(telemetry.cancelled_voices == 1);
  LMDJ_CHECK(telemetry.queued_events == 0);
  LMDJ_CHECK(telemetry.active_voices == 0);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{3, 0, 127}) ==
             EnqueueResult::not_running);
  LMDJ_CHECK(engine.telemetry().stopped_rejections == 1);
}

void restart_resets_counters_retains_samples_and_replays_no_event() {
  RealtimeEngine engine;
  const std::array<float, 3> sample{0.75F, 0.5F, 0.25F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{0, 64, 127}) ==
             EnqueueResult::invalid_slot);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 3> left{};
  std::array<float, 3> right{};
  engine.render(left.data(), right.data(), 3);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  for (std::uint64_t sequence = 3; sequence < 132; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  engine.render(left.data(), right.data(), 1);
  for (std::uint64_t sequence = 132; sequence < 1'156; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1'156, 0, 127}) ==
             EnqueueResult::queue_full);

  const auto before_stop = engine.telemetry();
  LMDJ_CHECK(before_stop.state == RealtimeState::running);
  LMDJ_CHECK(before_stop.queued_events > 0);
  LMDJ_CHECK(before_stop.active_voices > 0);

  engine.stop();
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1'157, 0, 127}) ==
             EnqueueResult::not_running);
  const auto after_stop = engine.telemetry();
  LMDJ_CHECK(after_stop.state == RealtimeState::stopped);
  LMDJ_CHECK(after_stop.enqueued_events > 0);
  LMDJ_CHECK(after_stop.dequeued_events > 0);
  LMDJ_CHECK(after_stop.cancelled_events > 0);
  LMDJ_CHECK(after_stop.started_voices > 0);
  LMDJ_CHECK(after_stop.completed_voices > 0);
  LMDJ_CHECK(after_stop.cancelled_voices > 0);
  LMDJ_CHECK(after_stop.invalid_events > 0);
  LMDJ_CHECK(after_stop.stopped_rejections > 0);
  LMDJ_CHECK(after_stop.queue_drops > 0);
  LMDJ_CHECK(after_stop.voice_drops > 0);
  LMDJ_CHECK(after_stop.callback_count > 0);
  LMDJ_CHECK(after_stop.rendered_frames > 0);
  LMDJ_CHECK(after_stop.max_callback_frames > 0);
  LMDJ_CHECK(after_stop.queued_events == 0);
  LMDJ_CHECK(after_stop.active_voices == 0);
  LMDJ_CHECK(after_stop.enqueued_events ==
             after_stop.dequeued_events + after_stop.cancelled_events);
  LMDJ_CHECK(after_stop.dequeued_events ==
             after_stop.started_voices + after_stop.voice_drops);
  LMDJ_CHECK(after_stop.started_voices ==
             after_stop.completed_voices + after_stop.cancelled_voices);

  LMDJ_CHECK(engine.start().has_value());
  const auto reset = engine.telemetry();
  LMDJ_CHECK(reset.state == RealtimeState::running);
  LMDJ_CHECK(reset.enqueued_events == 0);
  LMDJ_CHECK(reset.dequeued_events == 0);
  LMDJ_CHECK(reset.queued_events == 0);
  LMDJ_CHECK(reset.cancelled_events == 0);
  LMDJ_CHECK(reset.started_voices == 0);
  LMDJ_CHECK(reset.completed_voices == 0);
  LMDJ_CHECK(reset.active_voices == 0);
  LMDJ_CHECK(reset.cancelled_voices == 0);
  LMDJ_CHECK(reset.invalid_events == 0);
  LMDJ_CHECK(reset.stopped_rejections == 0);
  LMDJ_CHECK(reset.queue_drops == 0);
  LMDJ_CHECK(reset.voice_drops == 0);
  LMDJ_CHECK(reset.callback_count == 0);
  LMDJ_CHECK(reset.rendered_frames == 0);
  LMDJ_CHECK(reset.max_callback_frames == 0);

  left.fill(1.0F);
  right.fill(1.0F);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] == 0.0F && right[0] == 0.0F);

  LMDJ_CHECK(engine.enqueue(TriggerEvent{1'158, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] == 0.75F && right[0] == 0.75F);
}

void render_does_not_allocate_or_deallocate() {
  RealtimeEngine engine;
  const std::array<float, 2> old_sample{0.25F, 0.5F};
  auto first = bank_with_sample(30, old_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(first)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  g_allocations.store(0, std::memory_order_relaxed);
  g_deallocations.store(0, std::memory_order_relaxed);
  g_track_allocations.store(true, std::memory_order_relaxed);
  engine.render(left.data(), right.data(), 1);
  g_track_allocations.store(false, std::memory_order_relaxed);

  const std::array<float, 1> new_sample{0.75F};
  auto second = bank_with_sample(31, new_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(second)) ==
             PublishResult::accepted);

  g_track_allocations.store(true, std::memory_order_relaxed);
  engine.render(left.data(), right.data(), 1);
  g_track_allocations.store(false, std::memory_order_relaxed);
  LMDJ_CHECK(g_allocations.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(g_deallocations.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(left.at(0) == 0.5F);
  LMDJ_CHECK(engine.capture_telemetry().captured_events == 1);
  LMDJ_CHECK(engine.reclaim_retired_banks() == 1);
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
void operator delete[](void* memory) noexcept {
  ordinary_deallocation(memory);
}
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
  plays_a_sample_and_reports_render_telemetry();
  rejects_invalid_samples_and_running_time_mutation();
  supports_exact_64_slot_boundary();
  validates_events_and_cleared_slots();
  applies_velocity_gain_and_clamps_after_mixing();
  reports_queue_capacity_and_drops();
  caps_simultaneous_voices_and_mixes_each_admitted_voice();
  publishes_ordered_mixed_outcomes_at_128_frame_boundaries();
  outcome_ring_reports_capacity_drop_and_restart_resets_it();
  completes_a_sample_across_callback_blocks();
  publishes_sample_banks_only_at_safe_render_boundaries();
  rejects_publication_until_trigger_queue_is_empty();
  applies_explicit_bank_slot_backpressure_until_reclaimed();
  reports_exact_bytes_for_non_fifo_heterogeneous_bank_reclaim();
  captures_voice_starts_at_exact_runtime_frames_and_disarms_at_end();
  captures_only_successfully_allocated_voices();
  capture_overflow_corrupts_and_restart_clears_stale_events();
  stop_cancels_queued_events_and_active_voices();
  restart_resets_counters_retains_samples_and_replays_no_event();
  render_does_not_allocate_or_deallocate();
}
