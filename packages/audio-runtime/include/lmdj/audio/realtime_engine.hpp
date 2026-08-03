#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <vector>

#include <lmdj/audio/detail/fixed_spsc_queue.hpp>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::audio {

inline constexpr std::uint32_t kRealtimeSampleRate = 48'000;
inline constexpr std::uint16_t kRealtimeChannels = 2;
inline constexpr std::size_t kRealtimeSampleSlots = 64;
inline constexpr std::size_t kRealtimeQueueCapacity = 1'024;
inline constexpr std::size_t kRealtimeVoiceCapacity = 128;
inline constexpr std::size_t kRealtimeBankCapacity = 4;
inline constexpr std::size_t kRealtimePublishQueueCapacity = 4;
inline constexpr std::size_t kRealtimeCaptureCapacity = 4'096;

enum class RealtimeState : std::uint8_t { stopped, running };
enum class EnqueueResult : std::uint8_t {
  accepted,
  invalid_slot,
  invalid_velocity,
  sample_unavailable,
  not_running,
  bank_transition,
  queue_full,
};

enum class PublishResult : std::uint8_t {
  accepted,
  events_pending,
  bank_slots_full,
  publish_queue_full,
};

enum class CaptureState : std::uint8_t {
  idle,
  arm_pending,
  active,
  disarm_pending,
  corrupted,
};

struct TriggerEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
};

struct CapturedTriggerEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
  std::uint32_t frame_offset;
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

struct BankTelemetry {
  std::uint64_t current_generation;
  std::uint64_t pending_publications;
  std::uint64_t accepted_publications;
  std::uint64_t applied_publications;
  std::uint64_t reclaimed_banks;
  std::uint64_t bank_slot_rejections;
  std::uint64_t publish_queue_drops;
};

struct CaptureTelemetry {
  CaptureState state;
  std::uint64_t captured_events;
  std::uint64_t drained_events;
  std::uint64_t capture_drops;
  std::uint64_t capture_origin_frame;
};

class RealtimeEngine final {
 public:
  foundation::Result<void> load_sample(
      std::uint8_t slot, std::span<const float> mono_pcm);
  foundation::Result<void> clear_sample(std::uint8_t slot);
  // Publication and enqueue share one serialized control-thread producer.
  PublishResult publish_sample_bank(PreparedSampleBank&& bank) noexcept;
  std::size_t reclaim_retired_banks() noexcept;
  foundation::Result<void> arm_capture() noexcept;
  foundation::Result<void> disarm_capture() noexcept;
  std::size_t drain_capture(
      std::span<CapturedTriggerEvent> output) noexcept;
  foundation::Result<void> start();
  void stop() noexcept;
  EnqueueResult enqueue(TriggerEvent event) noexcept;
  void render(float* left, float* right, std::uint32_t frames) noexcept;
  // Counters are exact after quiescence and a best-effort snapshot while running.
  RealtimeTelemetry telemetry() const noexcept;
  BankTelemetry bank_telemetry() const noexcept;
  CaptureTelemetry capture_telemetry() const noexcept;

 private:
  enum class BankState : std::uint8_t {
    empty,
    current,
    pending,
    retiring,
    reclaimable,
  };
  static_assert(std::atomic<BankState>::is_always_lock_free);
  static_assert(std::atomic<CaptureState>::is_always_lock_free);

  static constexpr std::uint8_t kLegacyBankSlot = 0xff;

  struct BankSlot {
    std::optional<PreparedSampleBank> bank;
    std::atomic<BankState> state{BankState::empty};
    std::size_t active_voices = 0;
    std::uint64_t generation = 0;
  };

  struct Voice {
    const float* samples = nullptr;
    std::size_t frame_count = 0;
    std::size_t cursor = 0;
    float gain = 0.0F;
    bool active = false;
    std::uint8_t bank_slot = kLegacyBankSlot;
  };

  std::uint64_t legacy_availability_mask() const noexcept;
  void select_legacy_samples_quiescent() noexcept;
  void retire_current_bank() noexcept;
  void apply_published_bank(std::uint8_t slot) noexcept;
  void release_voice_bank(Voice& voice) noexcept;
  void capture_voice_start(
      const TriggerEvent& event,
      std::uint64_t absolute_start_frame) noexcept;

  std::array<std::vector<float>, kRealtimeSampleSlots> samples_;
  detail::FixedSpscQueue<TriggerEvent, kRealtimeQueueCapacity> queue_;
  std::array<BankSlot, kRealtimeBankCapacity> bank_slots_{};
  detail::FixedSpscQueue<
      std::uint8_t,
      kRealtimePublishQueueCapacity>
      publish_queue_;
  detail::FixedSpscQueue<
      CapturedTriggerEvent,
      kRealtimeCaptureCapacity>
      capture_ring_;
  std::array<Voice, kRealtimeVoiceCapacity> voices_{};
  std::atomic<std::uint64_t> availability_mask_{0};
  std::atomic<std::uint8_t> current_bank_slot_{kLegacyBankSlot};
  std::uint64_t next_bank_generation_ = 1;
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
  std::atomic<std::uint64_t> current_bank_generation_{0};
  std::atomic<std::uint64_t> pending_publications_{0};
  std::atomic<std::uint64_t> accepted_publications_{0};
  std::atomic<std::uint64_t> applied_publications_{0};
  std::atomic<std::uint64_t> reclaimed_banks_{0};
  std::atomic<std::uint64_t> bank_slot_rejections_{0};
  std::atomic<std::uint64_t> publish_queue_drops_{0};
  std::atomic<CaptureState> capture_state_{CaptureState::idle};
  std::atomic<std::uint64_t> captured_events_{0};
  std::atomic<std::uint64_t> drained_events_{0};
  std::atomic<std::uint64_t> capture_drops_{0};
  std::atomic<std::uint64_t> capture_origin_frame_{0};
};

}  // namespace lmdj::audio
