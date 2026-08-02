#include <lmdj/audio/realtime_engine.hpp>

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <new>

#include "tests/core/support/test.hpp"

namespace {

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

using lmdj::audio::EnqueueResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::RealtimeState;
using lmdj::audio::TriggerEvent;
using lmdj::foundation::ErrorCode;

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

  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.enqueued_events == 1);
  LMDJ_CHECK(telemetry.dequeued_events == 1);
  LMDJ_CHECK(telemetry.started_voices == 1);
  LMDJ_CHECK(telemetry.completed_voices == 1);
  LMDJ_CHECK(telemetry.active_voices == 0);
  LMDJ_CHECK(telemetry.callback_count == 2);
  LMDJ_CHECK(telemetry.rendered_frames == 2);
  LMDJ_CHECK(telemetry.max_callback_frames == 1);
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

void render_does_not_allocate() {
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.5F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};

  g_allocations.store(0, std::memory_order_relaxed);
  g_track_allocations.store(true, std::memory_order_relaxed);
  engine.render(left.data(), right.data(), 1);
  g_track_allocations.store(false, std::memory_order_relaxed);
  LMDJ_CHECK(g_allocations.load(std::memory_order_relaxed) == 0);
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

int main() {
  plays_a_sample_and_reports_render_telemetry();
  rejects_invalid_samples_and_running_time_mutation();
  validates_events_and_cleared_slots();
  applies_velocity_gain_and_clamps_after_mixing();
  reports_queue_capacity_and_drops();
  caps_simultaneous_voices_and_mixes_each_admitted_voice();
  completes_a_sample_across_callback_blocks();
  stop_cancels_queued_events_and_active_voices();
  restart_resets_counters_retains_samples_and_replays_no_event();
  render_does_not_allocate();
}
