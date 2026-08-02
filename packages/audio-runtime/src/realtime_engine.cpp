#include <lmdj/audio/realtime_engine.hpp>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <string>
#include <utility>

namespace lmdj::audio {
namespace {

static_assert(std::atomic<std::uint64_t>::is_always_lock_free);

foundation::Result<void> invalid_argument(std::string message) {
  return foundation::Result<void>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::move(message),
      });
}

void update_max(
    std::atomic<std::uint64_t>& maximum, std::uint64_t candidate) noexcept {
  auto observed = maximum.load(std::memory_order_relaxed);
  while (observed < candidate &&
         !maximum.compare_exchange_weak(
             observed,
             candidate,
             std::memory_order_relaxed,
             std::memory_order_relaxed)) {
  }
}

}  // namespace

foundation::Result<void> RealtimeEngine::load_sample(
    std::uint8_t slot, std::span<const float> mono_pcm) {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped) {
    return invalid_argument(
        "realtime samples may only be changed while stopped");
  }
  if (slot >= kRealtimeSampleSlots) {
    return invalid_argument("realtime sample slot is out of range");
  }
  if (mono_pcm.empty()) {
    return invalid_argument("realtime sample PCM must not be empty");
  }
  if (!std::all_of(mono_pcm.begin(), mono_pcm.end(), [](float value) {
        return std::isfinite(value);
      })) {
    return invalid_argument(
        "realtime sample PCM must contain only finite values");
  }

  samples_[slot].assign(mono_pcm.begin(), mono_pcm.end());
  return foundation::Result<void>::success();
}

foundation::Result<void> RealtimeEngine::clear_sample(std::uint8_t slot) {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped) {
    return invalid_argument(
        "realtime samples may only be changed while stopped");
  }
  if (slot >= kRealtimeSampleSlots) {
    return invalid_argument("realtime sample slot is out of range");
  }

  samples_[slot].clear();
  return foundation::Result<void>::success();
}

foundation::Result<void> RealtimeEngine::start() {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped) {
    return invalid_argument("realtime engine is already running");
  }

  queue_.clear_quiescent();
  std::fill(voices_.begin(), voices_.end(), Voice{});
  enqueued_events_.store(0, std::memory_order_relaxed);
  dequeued_events_.store(0, std::memory_order_relaxed);
  cancelled_events_.store(0, std::memory_order_relaxed);
  started_voices_.store(0, std::memory_order_relaxed);
  completed_voices_.store(0, std::memory_order_relaxed);
  active_voices_.store(0, std::memory_order_relaxed);
  cancelled_voices_.store(0, std::memory_order_relaxed);
  invalid_events_.store(0, std::memory_order_relaxed);
  stopped_rejections_.store(0, std::memory_order_relaxed);
  queue_drops_.store(0, std::memory_order_relaxed);
  voice_drops_.store(0, std::memory_order_relaxed);
  callback_count_.store(0, std::memory_order_relaxed);
  rendered_frames_.store(0, std::memory_order_relaxed);
  max_callback_frames_.store(0, std::memory_order_relaxed);
  state_.store(RealtimeState::running, std::memory_order_release);
  return foundation::Result<void>::success();
}

void RealtimeEngine::stop() noexcept {
  state_.store(RealtimeState::stopped, std::memory_order_release);
  cancelled_events_.fetch_add(
      queue_.clear_quiescent(), std::memory_order_relaxed);

  std::uint64_t active = 0;
  for (auto& voice : voices_) {
    if (voice.active) {
      ++active;
    }
    voice = Voice{};
  }
  cancelled_voices_.fetch_add(active, std::memory_order_relaxed);
  active_voices_.store(0, std::memory_order_relaxed);
}

EnqueueResult RealtimeEngine::enqueue(TriggerEvent event) noexcept {
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    stopped_rejections_.fetch_add(1, std::memory_order_relaxed);
    return EnqueueResult::not_running;
  }
  if (event.slot >= kRealtimeSampleSlots) {
    invalid_events_.fetch_add(1, std::memory_order_relaxed);
    return EnqueueResult::invalid_slot;
  }
  if (event.velocity == 0 || event.velocity > 127) {
    invalid_events_.fetch_add(1, std::memory_order_relaxed);
    return EnqueueResult::invalid_velocity;
  }
  if (samples_[event.slot].empty()) {
    invalid_events_.fetch_add(1, std::memory_order_relaxed);
    return EnqueueResult::sample_unavailable;
  }
  if (!queue_.try_push(event)) {
    queue_drops_.fetch_add(1, std::memory_order_relaxed);
    return EnqueueResult::queue_full;
  }

  enqueued_events_.fetch_add(1, std::memory_order_relaxed);
  return EnqueueResult::accepted;
}

void RealtimeEngine::render(
    float* left, float* right, std::uint32_t frames) noexcept {
  std::fill_n(left, frames, 0.0F);
  std::fill_n(right, frames, 0.0F);
  callback_count_.fetch_add(1, std::memory_order_relaxed);
  rendered_frames_.fetch_add(frames, std::memory_order_relaxed);
  update_max(max_callback_frames_, frames);

  TriggerEvent event{};
  while (queue_.try_pop(event)) {
    dequeued_events_.fetch_add(1, std::memory_order_relaxed);
    auto voice = std::find_if(
        voices_.begin(), voices_.end(), [](const Voice& candidate) {
          return !candidate.active;
        });
    if (voice == voices_.end()) {
      voice_drops_.fetch_add(1, std::memory_order_relaxed);
      continue;
    }
    const auto& sample = samples_[event.slot];
    *voice = Voice{
        sample.data(),
        sample.size(),
        0,
        static_cast<float>(event.velocity) / 127.0F,
        true,
    };
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
}

RealtimeTelemetry RealtimeEngine::telemetry() const noexcept {
  return RealtimeTelemetry{
      state_.load(std::memory_order_acquire),
      enqueued_events_.load(std::memory_order_relaxed),
      dequeued_events_.load(std::memory_order_relaxed),
      queue_.size_approx(),
      cancelled_events_.load(std::memory_order_relaxed),
      started_voices_.load(std::memory_order_relaxed),
      completed_voices_.load(std::memory_order_relaxed),
      active_voices_.load(std::memory_order_relaxed),
      cancelled_voices_.load(std::memory_order_relaxed),
      invalid_events_.load(std::memory_order_relaxed),
      stopped_rejections_.load(std::memory_order_relaxed),
      queue_drops_.load(std::memory_order_relaxed),
      voice_drops_.load(std::memory_order_relaxed),
      callback_count_.load(std::memory_order_relaxed),
      rendered_frames_.load(std::memory_order_relaxed),
      max_callback_frames_.load(std::memory_order_relaxed),
  };
}

}  // namespace lmdj::audio
