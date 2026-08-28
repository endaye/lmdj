#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <type_traits>
#include <vector>

#include <lmdj/audio/detail/fixed_spsc_queue.hpp>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::audio {

inline constexpr std::uint32_t kRealtimeSampleRate = 48'000;
// Voice attack/release ramp length: 2 ms at the fixed realtime sample rate.
inline constexpr std::uint32_t kRealtimeRampFrames = 96;
inline constexpr std::uint16_t kRealtimeChannels = 2;
inline constexpr std::size_t kRealtimeSampleSlots = 64;
inline constexpr std::size_t kRealtimeQueueCapacity = 1'024;
inline constexpr std::size_t kRealtimeVoiceCapacity = 128;
inline constexpr std::size_t kRealtimeBankCapacity = 4;
inline constexpr std::size_t kRealtimePublishQueueCapacity = 4;
inline constexpr std::size_t kRealtimePatternCapacity = 4;
inline constexpr std::size_t kRealtimeCaptureCapacity = 4'096;
inline constexpr std::size_t kRealtimeTriggerOutcomeCapacity = 4'096;
// A legacy one-shot can publish both started and completed edges. Keep room
// for the capture backlog plus one maximum control batch so capture overflow
// remains observable to callers that do not yet consume the Stage 8 stream.
inline constexpr std::size_t kRealtimeVoiceStateCapacity =
    (kRealtimeCaptureCapacity + kRealtimeQueueCapacity) * 2;

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

enum class PatternPublishResult : std::uint8_t {
  accepted,
  project_mismatch,
  publication_pending,
  pattern_slots_full,
  publish_queue_full,
  generation_exhausted,
};

struct PatternPublication {
  PatternPublishResult result;
  std::uint64_t generation;
  std::uint64_t activation_frame;
};

struct PatternTelemetry {
  std::uint64_t current_generation;
  std::uint64_t pending_generation;
  std::uint64_t pending_activation_frame;
  std::uint64_t accepted_publications;
  std::uint64_t applied_publications;
  std::uint64_t superseded_publications;
  std::uint64_t reclaimed_patterns;
  std::uint64_t publication_rejections;
};

enum class CaptureState : std::uint8_t {
  idle,
  arm_pending,
  active,
  disarm_pending,
  corrupted,
};

enum class RuntimeTriggerOutcome : std::uint8_t {
  voice_started,
  voice_capacity,
};

struct TriggerEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
};

enum class PadControlKind : std::uint8_t {
  press,
  release,
  stop_slot,
  stop_all,
  preview_set,
  preview_clear,
};

struct PadControlEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
  PadControlKind kind;
  cooker::ResolvedPlayback playback;
};

enum class RuntimeVoiceState : std::uint8_t {
  started,
  stopped,
  completed,
};

struct RuntimeVoiceStateEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  RuntimeVoiceState state;
  std::uint64_t runtime_frame;
  std::uint32_t source_frame;
};

static_assert(std::is_trivially_copyable_v<PadControlEvent>);
static_assert(std::is_trivially_copyable_v<RuntimeVoiceStateEvent>);

struct CapturedTriggerEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
  std::uint32_t frame_offset;
};

struct RuntimeTriggerOutcomeEvent {
  std::uint64_t sequence;
  RuntimeTriggerOutcome outcome;
  std::uint64_t runtime_frame;
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

struct ReclaimedBankTelemetry {
  std::size_t count;
  std::uint64_t decoded_pcm_bytes;
};

struct CaptureTelemetry {
  CaptureState state;
  std::uint64_t captured_events;
  std::uint64_t drained_events;
  std::uint64_t capture_drops;
  std::uint64_t capture_origin_frame;
};

struct RuntimeTriggerOutcomeTelemetry {
  std::uint64_t published_outcomes;
  std::uint64_t drained_outcomes;
  std::uint64_t runtime_outcome_drops;
};

enum class RuntimeVoiceStateStreamState : std::uint8_t {
  healthy,
  corrupted,
};

struct RuntimeVoiceStateTelemetry {
  RuntimeVoiceStateStreamState state;
  std::uint64_t published_voice_states;
  std::uint64_t drained_voice_states;
  std::uint64_t voice_state_drops;
};

namespace detail {

template <typename TryPop>
std::size_t drain_voice_states_fail_closed(
    std::atomic<RuntimeVoiceStateStreamState>& state,
    std::span<RuntimeVoiceStateEvent> output,
    TryPop try_pop) noexcept {
  if (state.load(std::memory_order_acquire) ==
      RuntimeVoiceStateStreamState::corrupted) {
    return 0;
  }
  std::size_t drained = 0;
  while (drained < output.size() && try_pop(output[drained])) {
    ++drained;
  }
  if (state.load(std::memory_order_acquire) ==
      RuntimeVoiceStateStreamState::corrupted) {
    return 0;
  }
  return drained;
}

}  // namespace detail

// Threading contract. Violating it is undefined behavior, not a runtime error.
//
// Exactly two threads may touch one RealtimeEngine:
//
//   Audio thread   calls `render` and nothing else.
//   Control thread calls everything else, serialized against itself.
//
// `render` is the sole audio-thread entry point. It never allocates, frees,
// locks, blocks, or throws, and it never destroys a PreparedSampleBank.
//
// The methods marked "quiescent" below reach non-atomic state that `render`
// also touches: the Voice array, the trigger queue's consumer index, and the
// publish queue's consumer side. The caller must guarantee that `render`
// cannot be executing and cannot begin before calling them. Stopping the
// device is not sufficient on its own; the caller must also observe that any
// in-flight callback has returned. `apple::CoreAudioOutput` does this by
// draining its callback gate before it calls `stop`.
//
// `load_sample` and `clear_sample` may reallocate sample storage, so calling
// them while a Voice is live dangles that Voice's sample pointer. Their
// `stopped` state check does not establish quiescence by itself.
//
// The remaining control-thread methods are safe to call while `render` runs.
// See docs/superpowers/specs/2026-08-02-lmdj-formal-native-realtime-host-design.md
// for the full model.
class RealtimeEngine final {
 public:
  // Control thread, quiescent. May reallocate sample storage.
  foundation::Result<void> load_sample(
      std::uint8_t slot, std::span<const float> mono_pcm);
  // Control thread, quiescent. May free sample storage.
  foundation::Result<void> clear_sample(std::uint8_t slot);
  // Control thread, concurrent with render while running.
  // Publication and enqueue share one serialized control-thread producer.
  // While running, publication establishes a three-part hand-off invariant:
  // (1) the control producer initializes the pending Bank before release-
  //     incrementing `pending_publications_` and publishing its queue entry;
  // (2) render applies that entry before release-decrementing the counter; and
  // (3) enqueue acquire-loads the counter and dereferences the current Bank
  //     only after observing zero. The relaxed current-slot/Bank reads rely on
  //     this exact release/acquire chain and the serialized control producer.
  // Applies the bank directly, and so requires quiescence, when stopped.
  PublishResult publish_sample_bank(PreparedSampleBank&& bank) noexcept;
  // Control thread. The immutable view is applied immediately while stopped,
  // or atomically at the next Bar boundary while running. Journal overlays
  // remain Runtime-only and never mutate the source Runtime Snapshot.
  PatternPublication publish_pattern_view(
      PreparedPatternView&& pattern,
      std::optional<std::uint64_t> activation_frame = std::nullopt) noexcept;
  foundation::Result<void> clear_pattern_view() noexcept;
  std::size_t reclaim_retired_patterns() noexcept;
  std::optional<foundation::PatternId> current_pattern_id() const;
  std::optional<foundation::PatternId> pending_pattern_id() const;
  std::optional<bool> current_pattern_has_overlay() const noexcept;
  std::optional<std::uint64_t> current_pattern_origin_frame() const noexcept;
  // Control thread, concurrent with render. Frees only reclaimable banks,
  // which by construction hold no live Voice.
  ReclaimedBankTelemetry reclaim_retired_bank_telemetry() noexcept;
  // Compatibility count-only reclaim surface.
  std::size_t reclaim_retired_banks() noexcept;
  // Control thread, concurrent with render.
  foundation::Result<void> arm_capture() noexcept;
  foundation::Result<void> disarm_capture() noexcept;
  // Control thread, concurrent with render. Sole consumer of the capture ring.
  std::size_t drain_capture(
      std::span<CapturedTriggerEvent> output) noexcept;
  // Control thread, concurrent with render. Sole consumer of the outcome ring.
  std::size_t drain_trigger_outcomes(
      std::span<RuntimeTriggerOutcomeEvent> output) noexcept;
  // Control thread, concurrent with render. Sole consumer of the Voice ring.
  std::size_t drain_voice_states(
      std::span<RuntimeVoiceStateEvent> output) noexcept;
  // Control thread, quiescent. Resets Voice and queue state.
  foundation::Result<void> start();
  // Control thread, quiescent. Releases Voice bank references and consumes the
  // publish queue, which makes it a second consumer of an SPSC queue.
  void stop() noexcept;
  // Control thread, concurrent with render. Sole producer of the trigger queue.
  EnqueueResult enqueue(TriggerEvent event) noexcept;
  EnqueueResult enqueue_control(PadControlEvent event) noexcept;
  // Audio thread only.
  void render(float* left, float* right, std::uint32_t frames) noexcept;
  // Any thread.
  // Counters are exact after quiescence and a best-effort snapshot while running.
  RealtimeTelemetry telemetry() const noexcept;
  BankTelemetry bank_telemetry() const noexcept;
  PatternTelemetry pattern_telemetry() const noexcept;
  CaptureTelemetry capture_telemetry() const noexcept;
  RuntimeTriggerOutcomeTelemetry trigger_outcome_telemetry() const noexcept;
  RuntimeVoiceStateTelemetry voice_state_telemetry() const noexcept;

 private:
  enum class BankState : std::uint8_t {
    empty,
    current,
    pending,
    retiring,
    reclaimable,
  };
  enum class PatternState : std::uint8_t {
    empty,
    current,
    pending,
    reclaimable,
  };
  static_assert(std::atomic<BankState>::is_always_lock_free);
  static_assert(std::atomic<PatternState>::is_always_lock_free);
  static_assert(std::atomic<CaptureState>::is_always_lock_free);
  static_assert(
      std::atomic<RuntimeVoiceStateStreamState>::is_always_lock_free);

  static constexpr std::uint8_t kLegacyBankSlot = 0xff;
  static constexpr std::uint8_t kNoPatternSlot = 0xff;

  struct BankSlot {
    std::optional<PreparedSampleBank> bank;
    std::atomic<BankState> state{BankState::empty};
    std::size_t active_voices = 0;
    std::uint64_t generation = 0;
  };

  struct PatternSlot {
    std::optional<PreparedPatternView> pattern;
    std::atomic<PatternState> state{PatternState::empty};
    std::uint64_t generation = 0;
    std::uint64_t activation_frame = 0;
  };

  struct PatternPublishEntry {
    std::uint8_t slot;
    std::uint64_t generation;
    std::uint64_t activation_frame;
  };
  static_assert(std::is_trivially_copyable_v<PatternPublishEntry>);

  struct Voice {
    std::uint64_t sequence = 0;
    std::uint8_t slot = 0;
    const float* samples = nullptr;
    std::size_t frame_count = 0;
    std::uint32_t start_frame = 0;
    std::uint32_t end_frame = 0;
    std::size_t cursor = 0;
    float gain = 0.0F;
    domain::TriggerMode trigger_mode = domain::TriggerMode::one_shot;
    bool active = false;
    std::uint8_t bank_slot = kLegacyBankSlot;
    std::uint32_t attack_frames_remaining = 0;
    bool releasing = false;
    std::uint32_t release_frames_remaining = 0;
    std::uint64_t scheduled_release_frame = 0;
    bool pattern_voice = false;
  };

  std::uint64_t legacy_availability_mask() const noexcept;
  void select_legacy_samples_quiescent() noexcept;
  void retire_current_bank() noexcept;
  void apply_published_bank(std::uint8_t slot) noexcept;
  void release_voice_bank(Voice& voice) noexcept;
  void capture_voice_start(
      const PadControlEvent& event,
      std::uint64_t absolute_start_frame) noexcept;
  const std::vector<float>& current_sample(std::uint8_t slot) const noexcept;
  cooker::ResolvedPlayback published_playback(
      std::uint8_t slot) const noexcept;
  bool publish_voice_state(
      const Voice& voice,
      RuntimeVoiceState state,
      std::uint64_t runtime_frame,
      std::uint32_t source_frame) noexcept;
  void stop_voice(Voice& voice, std::uint64_t runtime_frame) noexcept;
  void deactivate_voice(Voice& voice) noexcept;
  void apply_published_pattern(
      const PatternPublishEntry& publication,
      std::uint64_t runtime_frame) noexcept;
  void schedule_pattern_events(std::uint64_t runtime_frame) noexcept;
  void start_pattern_voice(
      const PreparedPatternEvent& event,
      std::uint64_t loop_origin_frame) noexcept;

  std::array<std::vector<float>, kRealtimeSampleSlots> samples_;
  detail::FixedSpscQueue<PadControlEvent, kRealtimeQueueCapacity> queue_;
  std::array<BankSlot, kRealtimeBankCapacity> bank_slots_{};
  detail::FixedSpscQueue<
      std::uint8_t,
      kRealtimePublishQueueCapacity>
      publish_queue_;
  std::array<PatternSlot, kRealtimePatternCapacity> pattern_slots_{};
  std::optional<PatternPublishEntry> audio_pending_pattern_;
  detail::FixedSpscQueue<
      CapturedTriggerEvent,
      kRealtimeCaptureCapacity>
      capture_ring_;
  detail::FixedSpscQueue<
      RuntimeTriggerOutcomeEvent,
      kRealtimeTriggerOutcomeCapacity>
      trigger_outcome_ring_;
  detail::FixedSpscQueue<
      RuntimeVoiceStateEvent,
      kRealtimeVoiceStateCapacity>
      voice_state_ring_;
  std::array<Voice, kRealtimeVoiceCapacity> voices_{};
  std::array<cooker::ResolvedPlayback, kRealtimeSampleSlots> previews_{};
  std::uint64_t preview_mask_ = 0;
  std::atomic<std::uint64_t> availability_mask_{0};
  std::atomic<std::uint8_t> current_bank_slot_{kLegacyBankSlot};
  std::atomic<std::uint8_t> current_pattern_slot_{kNoPatternSlot};
  std::uint64_t next_bank_generation_ = 1;
  std::uint64_t next_pattern_generation_ = 1;
  std::atomic<std::uint64_t> pattern_origin_frame_{0};
  std::size_t pattern_event_index_ = 0;
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
  // A generation-valued single-slot mailbox is the pattern publication
  // linearization point. The control thread may replace an unclaimed
  // generation; render marks it claimed with CAS before touching the slot.
  std::atomic<std::uint64_t> queued_pattern_generation_{0};
  std::atomic<std::uint64_t> audio_pending_pattern_generation_{0};
  std::atomic<std::uint64_t> accepted_pattern_publications_{0};
  std::atomic<std::uint64_t> applied_pattern_publications_{0};
  std::atomic<std::uint64_t> superseded_pattern_publications_{0};
  std::atomic<std::uint64_t> reclaimed_patterns_{0};
  std::atomic<std::uint64_t> pattern_publication_rejections_{0};
  std::atomic<CaptureState> capture_state_{CaptureState::idle};
  std::atomic<std::uint64_t> captured_events_{0};
  std::atomic<std::uint64_t> drained_events_{0};
  std::atomic<std::uint64_t> capture_drops_{0};
  std::atomic<std::uint64_t> capture_origin_frame_{0};
  std::atomic<std::uint64_t> published_outcomes_{0};
  std::atomic<std::uint64_t> drained_outcomes_{0};
  std::atomic<std::uint64_t> runtime_outcome_drops_{0};
  std::atomic<RuntimeVoiceStateStreamState> voice_state_stream_state_{
      RuntimeVoiceStateStreamState::healthy};
  std::atomic<std::uint64_t> published_voice_states_{0};
  std::atomic<std::uint64_t> drained_voice_states_{0};
  std::atomic<std::uint64_t> voice_state_drops_{0};
};

}  // namespace lmdj::audio
