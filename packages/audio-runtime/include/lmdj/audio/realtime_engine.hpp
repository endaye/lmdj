#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <type_traits>
#include <vector>

#include <lmdj/audio/detail/fixed_spsc_queue.hpp>
#include <lmdj/audio/detail/value_channel.hpp>
#include <lmdj/audio/master_fx.hpp>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::audio {

inline constexpr std::uint32_t kRealtimeSampleRate = 48'000;
inline constexpr std::uint32_t kRealtimeMaximumSampleFrames =
    std::numeric_limits<std::uint32_t>::max();
// Voice attack/release ramp length: 2 ms at the fixed realtime sample rate.
inline constexpr std::uint32_t kRealtimeRampFrames = 96;
inline constexpr std::uint16_t kRealtimeChannels = 2;
inline constexpr std::size_t kRealtimeSampleSlots = 64;
inline constexpr std::size_t kRealtimeQueueCapacity = 1'024;
inline constexpr std::size_t kRealtimeVoiceCapacity = 128;
inline constexpr std::size_t kRealtimeBankCapacity = 4;
// Sound Set audition Banks live outside `kRealtimeBankCapacity` so a preview
// costs the Project no hot-swap headroom (#799). Two, not one: replacing a
// ringing audition must publish the new Bank while the outgoing one is still
// being read by draining voices, which is the same reason the Project Bank
// pool is larger than one. Two is the minimum that supports replace.
inline constexpr std::size_t kRealtimeAuditionBankCapacity = 2;
// An audition Bank carries exactly one sound, at a fixed index. The Bank type
// is reused rather than duplicated (#799), so the other 63 sample slots stay
// empty and only this one is ever read.
inline constexpr std::uint8_t kAuditionSampleSlot = 0;
inline constexpr std::size_t kRealtimePublishQueueCapacity = 4;
inline constexpr std::size_t kRealtimePatternCapacity = 4;
// Occupancy includes the full ring, one producer reservation and one entry
// popped but not yet subtracted. Bank reservations each own a distinct slot.
static_assert(kRealtimeQueueCapacity <= std::numeric_limits<std::uint32_t>::max() - 2);
static_assert(kRealtimeBankCapacity <= std::numeric_limits<std::uint32_t>::max());
static_assert(kRealtimeVoiceCapacity <= std::numeric_limits<std::uint32_t>::max());
inline constexpr std::size_t kRealtimeCaptureCapacity = 4'096;
inline constexpr std::size_t kRealtimeTriggerOutcomeCapacity = 4'096;
// A legacy one-shot can publish both started and completed edges. Keep room
// for the capture backlog plus one maximum control batch so capture overflow
// remains observable to callers that do not yet consume the Stage 8 stream.
inline constexpr std::size_t kRealtimeVoiceStateCapacity =
    (kRealtimeCaptureCapacity + kRealtimeQueueCapacity) * 2;
// Receipt-bounded callers drain states before retiring consumed commands.
// At most two edges per pending command, plus one terminal per existing Voice.
inline constexpr std::size_t kRealtimeReceiptVoiceStateCapacity =
    kRealtimeQueueCapacity * 2 + kRealtimeVoiceCapacity;

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

// Exact control-thread authority for replacing a pending Pattern publication
// with a different Pattern. Ordinary publications may only supersede the same
// Pattern at the same boundary; Sequence switching and cancellation must prove
// the generation, Pattern identity, and boundary they were authorized to
// supersede.
struct PatternReplacementAuthority {
  std::uint64_t generation;
  foundation::PatternId pattern_id;
  std::uint64_t activation_frame;
};

struct PatternTelemetry {
  std::uint64_t current_generation;
  std::uint64_t pending_generation;
  std::uint64_t pending_activation_frame;
  std::uint64_t pending_publications;
  std::uint64_t accepted_publications;
  std::uint64_t applied_publications;
  std::uint64_t superseded_publications;
  std::uint64_t canceled_publications;
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
  // Sound Set audition (#799). These address the audition Bank, never a Pad,
  // so `slot` is ignored and `stop_slot` / `stop_all` do not reach them.
  audition_start,
  audition_stop,
};

enum class PadControlOrigin : std::uint8_t {
  host_input,
  performance_replay,
};

struct PadControlEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
  PadControlKind kind;
  cooker::ResolvedPlayback playback;
  PadControlOrigin origin{PadControlOrigin::host_input};
  std::uint64_t duration_frames{};
  PreparedSampleMaterialView material{};
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
  // Monotone process-local identity for the current start/render frame epoch.
  // A successful start increments it before publishing the running state.
  std::uint64_t start_epoch;
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
  // Project Bank reservation refund; reserved audition storage is excluded.
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

template <std::size_t Capacity>
class RuntimeVoiceStateQueue {
  // Natural alignment removes per-cell padding without changing the public
  // event's aggregate order, widths or ABI. Queue ownership remains SPSC.
  struct Cell {
    std::uint64_t sequence;
    std::uint64_t runtime_frame;
    std::uint32_t source_frame;
    std::uint8_t slot;
    RuntimeVoiceState state;
  };
  static_assert(sizeof(Cell) <= 24);
  static_assert(std::is_trivially_copyable_v<Cell>);

 public:
  static consteval std::size_t capacity() noexcept { return Capacity; }

  bool try_push(const RuntimeVoiceStateEvent& event) noexcept {
    return queue_.try_push(Cell{
        event.sequence, event.runtime_frame, event.source_frame,
        event.slot, event.state});
  }

  bool try_pop(RuntimeVoiceStateEvent& event) noexcept {
    Cell cell;
    if (!queue_.try_pop(cell)) {
      return false;
    }
    event = RuntimeVoiceStateEvent{
        cell.sequence, cell.slot, cell.state,
        cell.runtime_frame, cell.source_frame};
    return true;
  }

  std::size_t size_approx() const noexcept { return queue_.size_approx(); }
  std::size_t clear_quiescent() noexcept { return queue_.clear_quiescent(); }

 private:
  FixedSpscQueue<Cell, Capacity> queue_;
};

// Construct once on the control side; selection and pointees never change.
// Both alternatives retain the same SPSC publication and compact-cell format.
class RuntimeVoiceStateStorage {
 public:
  using Full = RuntimeVoiceStateQueue<kRealtimeVoiceStateCapacity>;
  using ReceiptBounded = RuntimeVoiceStateQueue<kRealtimeReceiptVoiceStateCapacity>;

  explicit RuntimeVoiceStateStorage(bool receipt_bounded = false)
      : full_(receipt_bounded ? nullptr : std::make_unique<Full>()),
        bounded_(receipt_bounded ? std::make_unique<ReceiptBounded>() : nullptr) {}

  bool try_push(const RuntimeVoiceStateEvent& event) noexcept {
    return full_ ? full_->try_push(event) : bounded_->try_push(event);
  }
  bool try_pop(RuntimeVoiceStateEvent& event) noexcept {
    return full_ ? full_->try_pop(event) : bounded_->try_pop(event);
  }
  std::size_t size_approx() const noexcept {
    return full_ ? full_->size_approx() : bounded_->size_approx();
  }
  std::size_t clear_quiescent() noexcept {
    return full_ ? full_->clear_quiescent() : bounded_->clear_quiescent();
  }

 private:
  std::unique_ptr<Full> full_;
  std::unique_ptr<ReceiptBounded> bounded_;
};

struct RealtimeEngineAudioAccess;

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
// One audio thread and one serialized control thread own mutable state:
//
//   Audio thread   calls `render` and nothing else.
//   Control thread calls the other non-telemetry methods, serialized against itself.
//   Observer threads may call telemetry methods concurrently. They serialize
//   with one another using a reader-only mutex; render never touches that mutex.
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
// See docs/design/2026-08-02-lmdj-formal-native-realtime-host-design.md
// for the full model.
class RealtimeEngine final {
 public:
  // Construction allocates the complete Voice-state queue, before publication
  // to audio. Default callers retain the full Capture-backlog capacity.
  RealtimeEngine() = default;
  // Opt-in only for a caller retaining <= kRealtimeQueueCapacity commands until
  // receipt retirement. It must acquire audio consumption, drain Voice states,
  // then retire receipts, in that order. No switching after construction.
  struct ReceiptBoundedVoiceStates {};
  explicit RealtimeEngine(ReceiptBoundedVoiceStates) : voice_state_ring_(true) {}
  static constexpr std::size_t receipt_bounded_voice_state_storage_bytes() noexcept {
    return sizeof(detail::RuntimeVoiceStateStorage::ReceiptBounded);
  }
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

  // Publish a Sound Set audition Bank (#799). It goes to the reserved audition
  // pool, never to `bank_slots_`, so it can neither displace the Project's Bank
  // nor consume its hot-swap headroom, and it never returns `bank_slots_full`.
  // A second publication replaces the first: the outgoing Bank is retired and
  // its voices drain on the ordinary release ramp. Returns `bank_slots_full`
  // only when both audition slots are still draining an earlier audition.
  PublishResult publish_audition_bank(PreparedSampleBank&& bank) noexcept;
  // Control thread. The immutable view is applied immediately while stopped,
  // or atomically at the next Bar boundary while running. Journal overlays
  // remain Runtime-only and never mutate the source Runtime Snapshot.
  PatternPublication publish_pattern_view(
      PreparedPatternView&& pattern,
      std::optional<std::uint64_t> activation_frame = std::nullopt,
      std::optional<PatternReplacementAuthority> replacement_authority =
          std::nullopt) noexcept;
  // Control thread. Publishes at the first render frame that can observe the
  // new mailbox entry. Unlike exact scheduled publication, a render callback
  // racing this call cannot make the internally observed frame stale.
  PatternPublication publish_pattern_view_immediate(
      PreparedPatternView&& pattern) noexcept;
  // Control thread, concurrent with render. Cancels the exact pending
  // publication until the render apply point claims it. False means the
  // authority was stale or the apply point already won.
  bool cancel_pattern_publication(
      const PatternReplacementAuthority& authority) noexcept;
  // Control thread, concurrent with render. Cancels only an exact publication
  // still owned by the control mailbox. False includes audio-owned pending
  // material, so latest-wins callers can defer instead of replacing it.
  bool cancel_unclaimed_pattern_publication(
      const PatternReplacementAuthority& authority) noexcept;
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
  // Serialized control thread, concurrent with render. Idempotently allocates
  // the full Capture ring without arming. False means allocation failed; no
  // state changes or allocating error payload. Retained until destruction.
  bool prepare_capture() noexcept;
  // Control thread, concurrent with render. Implicitly prepares for existing
  // callers. Allocation failure is internal_error with empty message/null
  // details (allocation-free); Hosts can preflight before opening a session.
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
  // Control thread, quiescent. Allocates all Master FX render storage.
  foundation::Result<void> prepare_master_fx(std::uint16_t bpm);
  // Control thread, concurrent with render. Sole producer of the FX queue.
  FxEnqueueResult enqueue_fx_gesture(FxGesture gesture) noexcept;
  // Control thread, concurrent with render. Ordered with FX gestures and
  // applied at the next render quantum boundary.
  FxEnqueueResult enqueue_master_fx_tempo(std::uint16_t bpm) noexcept;
  // Audio thread only.
  void render(float* left, float* right, std::uint32_t frames) noexcept;
  // Sole audio consumer or quiescent caller only. Exact consumed control count
  // for a narrow owner to publish after render; not evidence of audible voices.
  std::uint64_t consumed_controls_audio() const noexcept {
    return dequeued_events_;
  }
  // Any non-realtime thread (including control), not the audio callback.
  // Counters are exact after quiescence and a best-effort snapshot while running.
  RealtimeTelemetry telemetry() const noexcept;
  BankTelemetry bank_telemetry() const noexcept;
  PatternTelemetry pattern_telemetry() const noexcept;
  CaptureTelemetry capture_telemetry() const noexcept;
  RuntimeTriggerOutcomeTelemetry trigger_outcome_telemetry() const noexcept;
  RuntimeVoiceStateTelemetry voice_state_telemetry() const noexcept;
  MasterFxTelemetry master_fx_telemetry() const noexcept;
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  // Test-only overflow seam. The engine must be stopped.
  void set_start_epoch_for_testing(std::uint64_t epoch) noexcept;
  void set_next_pattern_generation_for_testing(std::uint64_t generation) noexcept;
  // Test-only writer handoff: no render may execute or begin during this call.
  void set_rendered_frames_quiescent_for_testing(std::uint64_t frames) noexcept;
  std::uint32_t queued_host_input_events_for_testing() const noexcept;
#endif

 private:
  friend struct detail::RealtimeEngineAudioAccess;
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
    retiring,
    reclaimable,
  };
  enum class PatternPublicationTiming : std::uint8_t {
    scheduled,
    immediate,
  };
  static_assert(std::atomic<BankState>::is_always_lock_free);
  static_assert(std::atomic<PatternState>::is_always_lock_free);
  static_assert(std::atomic<CaptureState>::is_always_lock_free);
  static_assert(
      std::atomic<RuntimeVoiceStateStreamState>::is_always_lock_free);

  static constexpr std::uint8_t kLegacyBankSlot = 0xff;
  static constexpr std::uint8_t kNoPatternSlot = 0xff;
  // Audition Bank slots are addressed as `kAuditionBankSlotBase + index` in
  // `Voice::bank_slot`, so a voice records which pool it drew from without a
  // second field, and `bank_slots_` indices stay 0..kRealtimeBankCapacity-1.
  static constexpr std::uint8_t kAuditionBankSlotBase = 0xf0;
  static constexpr std::uint8_t kNoAuditionSlot = 0xff;
  // `kLegacyBankSlot` is 0xff and so is also >= the audition base; a bare
  // `>= base` test would misclassify every legacy voice as an audition. The
  // range must be closed at both ends.
  static constexpr bool is_audition_bank_slot(std::uint8_t bank_slot) noexcept {
    return bank_slot >= kAuditionBankSlotBase && bank_slot != kLegacyBankSlot;
  }
  static_assert(
      kRealtimeBankCapacity <= kAuditionBankSlotBase,
      "Project Bank indices must not collide with the audition sentinel base");
  static_assert(
      kAuditionBankSlotBase + kRealtimeAuditionBankCapacity <= kLegacyBankSlot,
      "audition sentinels must not collide with kLegacyBankSlot");

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
    std::size_t active_voices = 0;
  };

  struct PatternPublishEntry {
    std::uint8_t slot;
    std::uint64_t generation;
    std::uint64_t activation_frame;
  };
  static_assert(std::is_trivially_copyable_v<PatternPublishEntry>);

  enum class MasterFxControlKind : std::uint8_t { gesture, tempo };
  struct MasterFxControlEvent {
    MasterFxControlKind kind;
    FxGesture gesture;
    std::uint16_t bpm;
  };
  static_assert(std::is_trivially_copyable_v<MasterFxControlEvent>);

  struct Voice {
    std::uint64_t sequence = 0;
    std::uint8_t slot = 0;
    const float* samples = nullptr;
    PreparedSampleMaterialView material{};
    std::size_t frame_count = 0;
    std::uint32_t start_frame = 0;
    std::uint32_t end_frame = 0;
    std::uint32_t cursor = 0;
    float gain = 0.0F;
    domain::TriggerMode trigger_mode = domain::TriggerMode::one_shot;
    bool active = false;
    std::uint8_t bank_slot = kLegacyBankSlot;
    std::uint32_t attack_frames_remaining = 0;
    bool releasing = false;
    std::uint32_t release_frames_remaining = 0;
    std::uint64_t scheduled_release_frame = 0;
    bool pattern_voice = false;
    PadControlOrigin origin = PadControlOrigin::host_input;
    std::uint8_t pattern_slot = kNoPatternSlot;
  };

  std::uint64_t legacy_availability_mask() const noexcept;
  void select_legacy_samples_quiescent() noexcept;
  void retire_current_bank() noexcept;
  void apply_published_bank(std::uint8_t slot) noexcept;
  void release_voice_bank(Voice& voice) noexcept;
  void release_voice_pattern(Voice& voice) noexcept;
  void capture_voice_start(
      const PadControlEvent& event,
      std::uint64_t absolute_start_frame) noexcept;
  const std::vector<float>& current_sample(std::uint8_t slot) const noexcept;
  // Resolves `Voice::bank_slot` to the slot that owns the voice's samples,
  // across both pools. Returns nullptr for `kLegacyBankSlot`, which owns none.
  BankSlot* bank_slot_for(std::uint8_t bank_slot) noexcept;
  const std::vector<float>& audition_sample(std::uint8_t slot) const noexcept;
  void retire_audition(std::uint8_t slot) noexcept;
  void apply_published_audition(std::uint8_t slot) noexcept;
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
  PatternPublication publish_pattern_view_impl(
      PreparedPatternView&& pattern,
      std::optional<std::uint64_t> activation_frame,
      std::optional<PatternReplacementAuthority> replacement_authority,
      PatternPublicationTiming timing) noexcept;
  void schedule_pattern_events(std::uint64_t runtime_frame) noexcept;
  void start_pattern_voice(
      const PreparedPatternEvent& event,
      std::uint64_t loop_origin_frame) noexcept;

  std::array<std::vector<float>, kRealtimeSampleSlots> samples_;
  detail::FixedSpscQueue<PadControlEvent, kRealtimeQueueCapacity> queue_;
  detail::FixedSpscQueue<MasterFxControlEvent, kRealtimeQueueCapacity>
      fx_queue_;
  MasterFxChain master_fx_;
  std::array<BankSlot, kRealtimeBankCapacity> bank_slots_{};
  // Reserved for Sound Set audition (#799). Never becomes `current_bank_slot_`
  // and never writes `availability_mask_`: an audition is not a Project Bank.
  std::array<BankSlot, kRealtimeAuditionBankCapacity> audition_slots_{};
  std::atomic<std::uint8_t> current_audition_slot_{kNoAuditionSlot};
  // Its own queue, sized to the audition pool for the same reason the Project
  // queue is sized to the Project pool: pushing requires a slot found `empty`,
  // and a full queue would require every slot `pending`, so the two conditions
  // cannot hold at once and `publish_queue_full` stays unreachable here too.
  // Sharing the Project queue would have broken that argument on both sides.
  detail::FixedSpscQueue<std::uint8_t, kRealtimeAuditionBankCapacity>
      audition_publish_queue_;
  detail::FixedSpscQueue<
      std::uint8_t,
      kRealtimePublishQueueCapacity>
      publish_queue_;
  std::array<PatternSlot, kRealtimePatternCapacity> pattern_slots_{};
  std::optional<PatternPublishEntry> audio_pending_pattern_;
  using CaptureRing = detail::FixedSpscQueue<
      CapturedTriggerEvent, kRealtimeCaptureCapacity>;
  // Initialized once by control before release-publishing arm_pending. Audio
  // only dereferences after acquiring an admitted CaptureState. Never replaced
  // or freed on disarm/stop: unread events still belong to the control drain.
  std::unique_ptr<CaptureRing> capture_ring_;
  detail::FixedSpscQueue<
      RuntimeTriggerOutcomeEvent,
      kRealtimeTriggerOutcomeCapacity>
      trigger_outcome_ring_;
  detail::RuntimeVoiceStateStorage voice_state_ring_;
  std::array<Voice, kRealtimeVoiceCapacity> voices_{};
  std::array<cooker::ResolvedPlayback, kRealtimeSampleSlots> previews_{};
  std::uint64_t preview_mask_ = 0;
  // Full 64-Pad mask, read only by control after acquire pending == 0. The
  // serialized control producer cannot start another publication during that
  // read; audio writes before release-subtracting the final pending Bank.
  std::uint64_t availability_mask_ = 0;
  std::atomic<std::uint8_t> current_bank_slot_{kLegacyBankSlot};
  std::atomic<std::uint8_t> current_pattern_slot_{kNoPatternSlot};
  std::uint64_t next_bank_generation_ = 1;
  std::uint64_t next_pattern_generation_ = 1;
  std::uint64_t pattern_origin_frame_ = 0;
  std::size_t pattern_event_index_ = 0;
  std::atomic<RealtimeState> state_{RealtimeState::stopped};
  std::uint64_t start_epoch_ = 0;
  std::uint64_t enqueued_events_ = 0;
  std::atomic<std::uint32_t> queued_host_input_events_{0};
  std::uint64_t dequeued_events_ = 0;
  std::uint64_t cancelled_events_ = 0;
  std::uint64_t started_voices_ = 0;
  std::uint64_t completed_voices_ = 0;
  std::uint32_t active_voices_ = 0;
  std::uint64_t cancelled_voices_ = 0;
  std::uint64_t invalid_events_ = 0;
  std::uint64_t audio_invalid_events_ = 0;
  std::uint64_t stopped_rejections_ = 0;
  std::uint64_t queue_drops_ = 0;
  std::uint64_t voice_drops_ = 0;
  std::uint64_t callback_count_ = 0;
  std::uint64_t rendered_frames_ = 0;
  std::uint32_t max_callback_frames_ = 0;
  std::uint64_t current_bank_generation_ = 0;
  std::atomic<std::uint32_t> pending_publications_{0};
  std::uint64_t accepted_publications_ = 0;
  std::uint64_t applied_publications_ = 0;
  std::uint64_t reclaimed_banks_ = 0;
  std::uint64_t bank_slot_rejections_ = 0;
  std::uint64_t publish_queue_drops_ = 0;
  // 0 = empty, 1..4 = slot + 1, bit 31 = claimed. Payload retains the full
  // non-reused 64-bit generation. Only the serialized control thread reuses
  // slots; audio-owned cancellation does not release the audio-local owner.
  std::atomic<std::uint32_t> pattern_claim_closed_{0};
  std::atomic<std::uint32_t> queued_pattern_generation_{0};
  std::atomic<std::uint32_t> audio_pending_pattern_generation_{0};
  std::uint64_t accepted_pattern_publications_ = 0;
  std::uint64_t applied_pattern_publications_ = 0;
  std::uint64_t superseded_pattern_publications_ = 0;
  std::uint64_t canceled_pattern_publications_ = 0;
  std::uint64_t reclaimed_patterns_ = 0;
  std::uint64_t pattern_publication_rejections_ = 0;
  std::atomic<CaptureState> capture_state_{CaptureState::idle};
  std::uint64_t captured_events_ = 0;
  std::uint64_t drained_events_ = 0;
  std::uint64_t capture_drops_ = 0;
  std::uint64_t capture_origin_frame_ = 0;
  std::uint64_t published_outcomes_ = 0;
  std::uint64_t drained_outcomes_ = 0;
  std::uint64_t runtime_outcome_drops_ = 0;
  std::atomic<RuntimeVoiceStateStreamState> voice_state_stream_state_{
      RuntimeVoiceStateStreamState::healthy};
  std::uint64_t published_voice_states_ = 0;
  std::uint64_t drained_voice_states_ = 0;
  std::uint64_t voice_state_drops_ = 0;
  std::uint64_t enqueued_fx_gestures_ = 0;
  std::uint64_t dequeued_fx_gestures_ = 0;
  std::uint64_t fx_queue_drops_ = 0;
  std::uint64_t master_fx_processed_frames_ = 0;
  std::atomic<std::uint32_t> queued_fx_gestures_{0};
  std::uint64_t enqueued_tempo_updates_ = 0;
  std::uint64_t applied_tempo_updates_ = 0;
  std::atomic<std::uint16_t> current_master_fx_bpm_{0};
  struct PatternObservation {
    std::uint64_t generation = 0;
    std::uint64_t activation_frame = 0;
  };
  struct AudioObservation {
    std::uint64_t pattern_origin_frame_ = 0;
    std::uint64_t dequeued_events_ = 0;
    std::uint64_t started_voices_ = 0;
    std::uint64_t completed_voices_ = 0;
    std::uint32_t active_voices_ = 0;
    std::uint64_t cancelled_voices_ = 0;
    std::uint64_t audio_invalid_events_ = 0;
    std::uint64_t voice_drops_ = 0;
    std::uint64_t callback_count_ = 0;
    std::uint64_t rendered_frames_ = 0;
    std::uint32_t max_callback_frames_ = 0;
    std::uint64_t current_bank_generation_ = 0;
    std::uint64_t applied_publications_ = 0;
    std::uint64_t applied_pattern_publications_ = 0;
    std::uint64_t captured_events_ = 0;
    std::uint64_t capture_drops_ = 0;
    std::uint64_t capture_origin_frame_ = 0;
    std::uint64_t published_outcomes_ = 0;
    std::uint64_t runtime_outcome_drops_ = 0;
    std::uint64_t published_voice_states_ = 0;
    std::uint64_t voice_state_drops_ = 0;
    std::uint64_t dequeued_fx_gestures_ = 0;
    std::uint64_t master_fx_processed_frames_ = 0;
    std::uint64_t applied_tempo_updates_ = 0;
    std::uint64_t start_epoch_ = 0;
    std::uint64_t claimed_through = 0;
    std::uint64_t current_pattern_generation = 0;
    PatternObservation pending{};
  };
  struct ControlObservation {
    std::uint64_t start_epoch_ = 0;
    std::uint64_t enqueued_events_ = 0;
    std::uint64_t cancelled_events_ = 0;
    std::uint64_t invalid_events_ = 0;
    std::uint64_t stopped_rejections_ = 0;
    std::uint64_t queue_drops_ = 0;
    std::uint64_t accepted_publications_ = 0;
    std::uint64_t reclaimed_banks_ = 0;
    std::uint64_t bank_slot_rejections_ = 0;
    std::uint64_t publish_queue_drops_ = 0;
    std::uint64_t accepted_pattern_publications_ = 0;
    std::uint64_t superseded_pattern_publications_ = 0;
    std::uint64_t canceled_pattern_publications_ = 0;
    std::uint64_t reclaimed_patterns_ = 0;
    std::uint64_t pattern_publication_rejections_ = 0;
    std::uint64_t drained_events_ = 0;
    std::uint64_t drained_outcomes_ = 0;
    std::uint64_t drained_voice_states_ = 0;
    std::uint64_t enqueued_fx_gestures_ = 0;
    std::uint64_t fx_queue_drops_ = 0;
    std::uint64_t enqueued_tempo_updates_ = 0;
    PatternObservation last_queued{};
    std::uint64_t last_audio_cancel = 0;
  };
  struct TransportDecision {
    std::uint64_t rendered_frames = 0;
    std::uint64_t pattern_origin_frame = 0;
  };
  // Writer-private authority is separate from the recycled output slots.
  PatternObservation observed_audio_pending_{};
  PatternObservation observed_last_queued_{};
  std::uint64_t observed_claimed_through_ = 0;
  std::uint64_t observed_current_pattern_generation_ = 0;
  std::uint64_t observed_last_audio_cancel_ = 0;
  detail::ValueChannel<AudioObservation> audio_observation_;
  detail::ValueChannel<ControlObservation> control_observation_;
  detail::ValueChannel<TransportDecision> transport_decision_;
  mutable std::mutex observation_reader_mutex_;
  void publish_audio_observation() noexcept;
  void publish_control_observation() noexcept;
  void publish_transport_decision() noexcept;
  std::uint64_t pattern_token_generation(std::uint32_t token) const noexcept;
  struct PublishOnReturn {
    RealtimeEngine& engine;
    void (RealtimeEngine::*publish)() noexcept;
    ~PublishOnReturn() { (engine.*publish)(); }
  };

};

}  // namespace lmdj::audio
