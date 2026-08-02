#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

#include <lmdj/audio/detail/fixed_spsc_queue.hpp>
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
  // Counters are exact after quiescence and a best-effort snapshot while running.
  RealtimeTelemetry telemetry() const noexcept;

 private:
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
  std::atomic<std::uint64_t> enqueued_events_{0};
  std::atomic<std::uint64_t> dequeued_events_{0};
  std::atomic<std::uint64_t> cancelled_events_{0};
  std::atomic<std::uint64_t> started_voices_{0};
  std::atomic<std::uint64_t> completed_voices_{0};
  std::atomic<std::uint64_t> active_voices_{0};
  std::atomic<std::uint64_t> cancelled_voices_{0};
  std::atomic<std::uint64_t> invalid_events_{0};
  std::atomic<std::uint64_t> stopped_rejections_{0};
  std::atomic<std::uint64_t> queue_drops_{0};
  std::atomic<std::uint64_t> voice_drops_{0};
  std::atomic<std::uint64_t> callback_count_{0};
  std::atomic<std::uint64_t> rendered_frames_{0};
  std::atomic<std::uint64_t> max_callback_frames_{0};
};

}  // namespace lmdj::audio
