#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/audio/detail/voice_dsp.hpp>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <iterator>
#include <limits>
#include <new>
#include <stdexcept>
#include <string>
#include <utility>

#include "pattern_generation.hpp"
#include "testing_hooks.hpp"

namespace lmdj::audio {

PatternPublicationLease::PatternPublicationLease(
    PatternPublicationLease&& other) noexcept
    : engine_(std::exchange(other.engine_, nullptr)),
      slot_(other.slot_), generation_(other.generation_) {}

PatternPublicationLease& PatternPublicationLease::operator=(
    PatternPublicationLease&& other) noexcept {
  if (this != &other) {
    reset();
    engine_ = std::exchange(other.engine_, nullptr);
    slot_ = other.slot_;
    generation_ = other.generation_;
  }
  return *this;
}

PatternPublicationLease::~PatternPublicationLease() { reset(); }

void PatternPublicationLease::reset() noexcept {
  if (auto* engine = std::exchange(engine_, nullptr))
    engine->release_pattern_publication_lease(slot_, generation_);
}

namespace {
std::size_t checked_receipt_pending(std::size_t pending) {
  if (!RealtimeEngine::receipt_bounded_storage_bytes(pending)) {
    throw std::invalid_argument("receipt-bounded pending capacity must be 1..1024");
  }
  return pending;
}
}  // namespace

RealtimeEngine::RealtimeEngine(ReceiptBoundedVoiceStates, std::size_t pending)
    : queue_(checked_receipt_pending(pending)),
      trigger_outcome_ring_(pending),
      voice_state_ring_(true, pending) {}

std::optional<std::uint64_t> RealtimeEngine::receipt_bounded_storage_bytes(
    std::size_t pending) noexcept {
  const auto voices = detail::RuntimeVoiceStateStorage::receipt_allocation_bytes(pending);
  const auto controls = detail::RuntimeSpscStorage<PadControlEvent>::allocation_bytes(pending);
  const auto outcomes =
      detail::RuntimeSpscStorage<RuntimeTriggerOutcomeEvent>::allocation_bytes(pending);
  if (!voices || !controls || !outcomes) return std::nullopt;
  const auto first = checked_runtime_byte_sum(*controls, *outcomes);
  return first ? checked_runtime_byte_sum(*first, *voices) : std::nullopt;
}

#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
namespace testing {
namespace {

std::atomic<PatternClaimHook*> pattern_claim_hook{nullptr};
std::atomic<PatternClaimHook*> pattern_apply_hook{nullptr};
std::array<std::atomic<PatternClaimHook*>,
           static_cast<std::size_t>(RealtimeHookPoint::count)> realtime_hooks{};

}  // namespace

void set_pattern_claim_hook(PatternClaimHook* hook) noexcept {
  pattern_claim_hook.store(hook, std::memory_order_release);
}

void invoke_pattern_claim_hook() noexcept {
  auto* hook = pattern_claim_hook.exchange(nullptr, std::memory_order_acq_rel);
  if (hook != nullptr && hook->invoke != nullptr) {
    hook->invoke(hook->context);
  }
}

void set_pattern_apply_hook(PatternClaimHook* hook) noexcept {
  pattern_apply_hook.store(hook, std::memory_order_release);
}

void invoke_pattern_apply_hook() noexcept {
  auto* hook = pattern_apply_hook.exchange(nullptr, std::memory_order_acq_rel);
  if (hook != nullptr && hook->invoke != nullptr) {
    hook->invoke(hook->context);
  }
}

void set_realtime_hook(RealtimeHookPoint point, PatternClaimHook* hook) noexcept {
  realtime_hooks[static_cast<std::size_t>(point)].store(
      hook, std::memory_order_release);
}

void invoke_realtime_hook(RealtimeHookPoint point) noexcept {
  auto* hook = realtime_hooks[static_cast<std::size_t>(point)].exchange(
      nullptr, std::memory_order_acq_rel);
  if (hook != nullptr && hook->invoke != nullptr) {
    hook->invoke(hook->context);
  }
}

}  // namespace testing
#endif
namespace {

static_assert(std::atomic<std::uint32_t>::is_always_lock_free);
constexpr std::uint32_t kPatternTokenClaimedMask = std::uint32_t{1} << 31U;
constexpr std::uint32_t kPatternControlReservedMask = std::uint32_t{1} << 30U;
constexpr std::uint32_t kPatternAdmissionInvalidatedMask = std::uint32_t{1} << 29U;
constexpr std::uint32_t kPatternAdmissionMask =
    kPatternControlReservedMask | kPatternAdmissionInvalidatedMask;
constexpr std::uint32_t pattern_slot_token(std::uint32_t mailbox) noexcept {
  return mailbox & ~(kPatternTokenClaimedMask | kPatternAdmissionMask);
}

// Only serialized control reserves publication admission. Audio invalidates
// that reservation without waiting and preserves it through every empty Q
// claim. Cleanup is an RMW, so audio cannot resurrect a released reservation.
class PatternPublicationAdmission {
 public:
  explicit PatternPublicationAdmission(std::atomic<std::uint32_t>& mailbox)
      : mailbox_(mailbox) {}
  ~PatternPublicationAdmission() {
    if (reserved_)
      mailbox_.fetch_and(~kPatternAdmissionMask, std::memory_order_seq_cst);
  }
  void committed() noexcept { reserved_ = false; }

 private:
  std::atomic<std::uint32_t>& mailbox_;
  bool reserved_ = true;
};

// Control-only. Beat boundaries use the same independently rounded ticks
// within each rounded loop as Pattern events; repeating one rounded beat
// would drift away from those events at BPMs such as 123. Bar intentionally
// retains the existing repeated rounded-Bar policy (#1973).
std::optional<std::uint64_t> next_pattern_switch_frame(
    const PreparedPatternView& pattern, std::uint64_t origin,
    std::uint64_t observed, PatternSwitchSnap snap) noexcept {
  constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
  const auto elapsed = std::max(observed, origin) - origin;
  if (snap == PatternSwitchSnap::bar || snap == PatternSwitchSnap::pattern_end) {
    const auto period = snap == PatternSwitchSnap::bar
        ? pattern.bar_frames() : pattern.loop_frames();
    const auto count = elapsed / period;
    if (count == maximum || count + 1 > (maximum - origin) / period)
      return std::nullopt;
    return origin + (count + 1) * period;
  }
  if (snap != PatternSwitchSnap::beat) return std::nullopt;
  const auto local = elapsed % pattern.loop_frames();
  const auto numerator = integrate_tick_numerator(0, local, pattern.bpm(), pattern.ppq());
  if (!numerator) return std::nullopt;
  const auto next_tick = (whole_tick(*numerator) / pattern.ppq() + 1) * pattern.ppq();
  const auto boundary = tick_boundary_frame(next_tick, pattern.bpm(), pattern.ppq());
  const auto loop_offset = elapsed - local;
  if (!boundary.has_value() || loop_offset > maximum - origin ||
      boundary.value() > maximum - origin - loop_offset) return std::nullopt;
  return origin + loop_offset + boundary.value();
}
// Continuous clocks select the next musical multiple from the exact retained
// numerator. The physical origin is intentionally absent from this calculation.
std::optional<std::uint64_t> next_continuous_pattern_switch_frame(
    const PreparedPatternView& pattern, const TransportAnchor& anchor,
    std::uint64_t observed, PatternSwitchSnap snap) noexcept {
  if (observed < anchor.runtime_frame) return std::nullopt;
  const auto numerator = integrate_tick_numerator(anchor.tick_numerator,
      observed - anchor.runtime_frame, anchor.bpm, pattern.ppq());
  if (!numerator) return std::nullopt;
  const auto period = snap == PatternSwitchSnap::beat ? pattern.ppq()
      : snap == PatternSwitchSnap::bar ? domain::kBarTicks4x4
      : snap == PatternSwitchSnap::pattern_end ? pattern.loop_length_ticks() : 0;
  if (period == 0) return std::nullopt;
  const auto count = whole_tick(*numerator) / period;
  constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
  if (count == maximum || count + 1 > maximum / period) return std::nullopt;
  return anchored_tick_boundary_frame(anchor, (count + 1) * period);
}
static_assert(std::atomic<std::uint16_t>::is_always_lock_free);
static_assert(std::atomic<std::uint8_t>::is_always_lock_free);
static_assert(
    kRealtimeMaximumSampleFrames ==
    std::numeric_limits<decltype(cooker::ResolvedPlayback::end_frame)>::max());
// prepare_master_fx prepares the chain at the fixed realtime rate, which is
// exactly the typed Filter admission rate; this pin keeps the chain's
// non-48 kHz typed refusal unreachable through the engine, so the accepted
// shadow and the audio thread can never diverge on it.
static_assert(kFilterTypedSampleRate == kRealtimeSampleRate);

foundation::Result<void> invalid_argument(std::string message) {
  return foundation::Result<void>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::move(message),
      });
}


bool valid_control_kind(PadControlKind kind) noexcept {
  switch (kind) {
    case PadControlKind::press:
    case PadControlKind::release:
    case PadControlKind::stop_slot:
    case PadControlKind::stop_all:
    case PadControlKind::stop_slot_live:
    case PadControlKind::preview_set:
    case PadControlKind::preview_clear:
    case PadControlKind::audition_start:
    case PadControlKind::audition_stop:
      return true;
  }
  return false;
}

bool valid_fx_gesture(FxGesture gesture) noexcept {
  switch (gesture.kind) {
    case FxGestureKind::hold_on:
    case FxGestureKind::hold_off:
      return true;
    case FxGestureKind::engage:
    case FxGestureKind::move:
    case FxGestureKind::release:
      break;
  }
  const auto index = static_cast<std::size_t>(gesture.fx);
  return index < kFxChainOrder.size() && kFxChainOrder[index] == gesture.fx;
}

bool valid_trigger_mode(domain::TriggerMode mode) noexcept {
  switch (mode) {
    case domain::TriggerMode::one_shot:
    case domain::TriggerMode::gate:
    case domain::TriggerMode::loop_gate:
    case domain::TriggerMode::loop_toggle:
      return true;
  }
  return false;
}

// The playback's trim, mode and gain, without its DSP block. A trigger checks
// the block by preparing it (prepare_voice_kernel), so a voice designs its
// filters once per trigger, not once to validate and again to play.
bool valid_playback_range(
    const cooker::ResolvedPlayback& playback,
    std::size_t frame_count) noexcept {
  return playback.start_frame < playback.end_frame &&
         playback.end_frame <= frame_count &&
         valid_trigger_mode(playback.trigger_mode) &&
         std::isfinite(playback.linear_gain) && playback.linear_gain >= 0.0F;
}

bool valid_playback(
    const cooker::ResolvedPlayback& playback,
    std::size_t frame_count) noexcept {
  return valid_playback_range(playback, frame_count) &&
         detail::voice_dsp_fits(playback, frame_count);
}

bool is_default_playback_sentinel(
    const cooker::ResolvedPlayback& playback) noexcept {
  return playback.start_frame == 0 && playback.end_frame == 0 &&
         playback.trigger_mode == domain::TriggerMode::one_shot &&
         playback.linear_gain == 0.0F && !playback.muted &&
         cooker::is_neutral(playback.dsp);
}

bool is_looping(domain::TriggerMode mode) noexcept {
  return mode == domain::TriggerMode::loop_gate ||
         mode == domain::TriggerMode::loop_toggle;
}

// Prepares the kernel for a non-neutral voice. A neutral block leaves the
// state inactive; false means the block does not fit and the event is refused.
bool prepare_voice_kernel(
    const cooker::ResolvedPlayback& playback,
    std::size_t material_frames,
    bool& active,
    detail::VoiceDspState& state) noexcept {
  active = !cooker::is_neutral(playback.dsp);
  return !active ||
         detail::prepare_voice_dsp(playback, material_frames, state);
}

bool valid_material(PreparedSampleMaterialView material) noexcept {
  return material.interleaved != nullptr && material.frame_count != 0 &&
         (material.channels == 1 || material.channels == 2);
}

constexpr float kRealtimeRampScale =
    1.0F / static_cast<float>(kRealtimeRampFrames);
static_assert(kRealtimeRampFrames == detail::kVoiceDspRampFrames);

// Fixes a voice's envelope at trigger: both ramp lengths, their scales and the
// attack counter. A default envelope is the 96-frame declick at scale 1/96.
template <typename VoiceType>
void set_voice_envelope(
    VoiceType& voice, const cooker::ResolvedPlayback& playback) noexcept {
  const auto envelope = detail::voice_envelope(playback);
  voice.attack_frames_remaining = envelope.attack_frames;
#if LMDJ_VOICE_DSP
  voice.attack_frames = envelope.attack_frames;
  voice.attack_scale = envelope.attack_scale;
  voice.release_frames = envelope.release_frames;
  voice.release_scale = envelope.release_scale;
#endif
}

std::uint8_t global_slot(domain::PadSlotId slot) noexcept {
  return static_cast<std::uint8_t>(slot.bank * 16U + slot.pad);
}

}  // namespace

void RealtimeEngine::publish_audio_observation() noexcept {
  audio_observation_.publish({
      pattern_origin_frame_,
      dequeued_events_,
      started_voices_,
      completed_voices_,
      active_voices_,
      cancelled_voices_,
      audio_invalid_events_,
      voice_drops_,
      callback_count_,
      rendered_frames_,
      max_callback_frames_,
      current_bank_generation_,
      applied_publications_,
      applied_pattern_publications_,
      captured_events_,
      capture_drops_,
      capture_origin_frame_,
      published_outcomes_,
      runtime_outcome_drops_,
      published_voice_states_,
      voice_state_drops_,
      dequeued_fx_gestures_,
      master_fx_processed_frames_,
      applied_tempo_updates_,
      start_epoch_, observed_claimed_through_,
      observed_current_pattern_generation_, observed_audio_pending_,
      transport_canceled_publications_,
      dequeued_filter_controls_,
  });
}

void RealtimeEngine::publish_control_observation() noexcept {
  control_observation_.publish({
      start_epoch_,
      enqueued_events_,
      cancelled_events_,
      invalid_events_,
      stopped_rejections_,
      queue_drops_,
      accepted_publications_,
      reclaimed_banks_,
      bank_slot_rejections_,
      publish_queue_drops_,
      accepted_pattern_publications_,
      superseded_pattern_publications_,
      canceled_pattern_publications_,
      reclaimed_patterns_,
      pattern_publication_rejections_,
      drained_events_,
      drained_outcomes_,
      drained_voice_states_,
      enqueued_fx_gestures_,
      fx_queue_drops_,
      enqueued_tempo_updates_,
      observed_last_queued_, observed_last_audio_cancel_,
      enqueued_filter_controls_,
  });
}

void RealtimeEngine::publish_transport_decision() noexcept {
  transport_decision_.publish({rendered_frames_, pattern_origin_frame_,
      observed_current_pattern_generation_,
      {start_epoch_, observed_current_pattern_generation_,
       pattern_tempo_applied_frame_, pattern_tempo_anchor_,
       state_.load(std::memory_order_relaxed) == RealtimeState::running &&
           (!pattern_transport_enabled_ || pattern_playing_)},
      pattern_continuous_timing_, pattern_position_available_});
}

std::uint64_t RealtimeEngine::pattern_token_generation(
    std::uint32_t token) const noexcept {
  // Control only: this thread alone can reclaim or reuse the immutable payload.
  const auto slot = pattern_slot_token(token);
  return slot == 0 ? 0 : pattern_slots_[slot - 1].generation;
}

std::uint64_t RealtimeEngine::legacy_availability_mask() const noexcept {
  std::uint64_t mask = 0;
  for (std::size_t slot = 0; slot < samples_.size(); ++slot) {
    if (!samples_[slot].empty()) {
      mask |= std::uint64_t{1} << slot;
    }
  }
  return mask;
}

void RealtimeEngine::retire_current_bank() noexcept {
  const auto current = current_bank_slot_.load(std::memory_order_relaxed);
  if (current == kLegacyBankSlot) {
    return;
  }
  auto& slot = bank_slots_[current];
  slot.state.store(BankState::retiring, std::memory_order_release);
  if (slot.active_voices == 0) {
    slot.state.store(BankState::reclaimable, std::memory_order_release);
  }
}

void RealtimeEngine::select_legacy_samples_quiescent() noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_audio_observation};
  retire_current_bank();
  current_bank_slot_.store(kLegacyBankSlot, std::memory_order_relaxed);
  current_bank_generation_ = 0;
  availability_mask_ = legacy_availability_mask();
  preview_mask_ = 0;
}

void RealtimeEngine::apply_published_bank(std::uint8_t slot_index) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_audio_observation};
  retire_current_bank();
  auto& slot = bank_slots_[slot_index];
  slot.state.store(BankState::current, std::memory_order_release);
  current_bank_slot_.store(slot_index, std::memory_order_relaxed);
  availability_mask_ = slot.bank->availability_mask();
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::bank_mask_written);
#endif
  current_bank_generation_ = slot.generation;
  preview_mask_ = 0;
  applied_publications_ += 1;
}

void RealtimeEngine::release_voice_bank(Voice& voice) noexcept {
  auto* const owner = bank_slot_for(voice.bank_slot);
  if (owner == nullptr) {
    return;
  }
  auto& slot = *owner;
  --slot.active_voices;
  if (slot.active_voices == 0 &&
      slot.state.load(std::memory_order_relaxed) == BankState::retiring) {
    slot.state.store(BankState::reclaimable, std::memory_order_release);
  }
  voice.bank_slot = kLegacyBankSlot;
}

RealtimeEngine::BankSlot* RealtimeEngine::bank_slot_for(
    std::uint8_t bank_slot) noexcept {
  if (bank_slot == kLegacyBankSlot) {
    return nullptr;
  }
  if (bank_slot >= kAuditionBankSlotBase) {
    return &audition_slots_[bank_slot - kAuditionBankSlotBase];
  }
  return &bank_slots_[bank_slot];
}

RealtimeEngine::SampleView RealtimeEngine::bank_sample(
    const PreparedSampleBank& bank, std::uint8_t slot) noexcept {
  const auto material = bank.material(slot);
  const auto& floats = bank.sample(slot);
  return {material.interleaved ? nullptr : floats.data(), material,
          material.interleaved ? material.frame_count : floats.size()};
}

RealtimeEngine::SampleView RealtimeEngine::audition_sample(
    std::uint8_t slot) const noexcept {
  return bank_sample(*audition_slots_[slot].bank, kAuditionSampleSlot);
}

// Audition retirement mirrors `retire_current_bank` but never touches
// `current_bank_slot_` or `availability_mask_`: an audition is not a Project
// Bank, and the Pad availability the Host reports must not move for a preview.
void RealtimeEngine::retire_audition(std::uint8_t slot) noexcept {
  auto& audition = audition_slots_[slot];
  if (audition.state.load(std::memory_order_acquire) != BankState::current) {
    return;
  }
  audition.state.store(BankState::retiring, std::memory_order_release);
  if (audition.active_voices == 0) {
    audition.state.store(BankState::reclaimable, std::memory_order_release);
  }
}

// Audio thread only. Retirement and voice starts are therefore serialised by
// the render callback, which is the whole point of routing publication through
// the queue: a Bank cannot be retired between a voice reading it and that voice
// counting itself against it.
void RealtimeEngine::apply_published_audition(std::uint8_t slot) noexcept {
  const auto live = current_audition_slot_.load(std::memory_order_relaxed);
  audition_slots_[slot].state.store(
      BankState::current, std::memory_order_release);
  current_audition_slot_.store(
      static_cast<std::uint8_t>(kAuditionBankSlotBase + slot),
      std::memory_order_release);
  if (live != kNoAuditionSlot) {
    retire_audition(static_cast<std::uint8_t>(live - kAuditionBankSlotBase));
  }
}

void RealtimeEngine::release_voice_pattern(Voice& voice) noexcept {
  if (voice.pattern_slot == kNoPatternSlot) {
    return;
  }
  auto& slot = pattern_slots_[voice.pattern_slot];
  --slot.active_voices;
  if (slot.active_voices == 0 &&
      slot.state.load(std::memory_order_relaxed) == PatternState::retiring) {
    slot.state.store(PatternState::reclaimable, std::memory_order_release);
  }
  voice.pattern_slot = kNoPatternSlot;
}

RealtimeEngine::SampleView RealtimeEngine::current_sample(
    std::uint8_t slot) const noexcept {
  const auto bank_slot = current_bank_slot_.load(std::memory_order_relaxed);
  return bank_slot == kLegacyBankSlot
             ? SampleView{samples_[slot].data(), {}, samples_[slot].size()}
             : bank_sample(*bank_slots_[bank_slot].bank, slot);
}

cooker::ResolvedPlayback RealtimeEngine::published_playback(
    std::uint8_t slot) const noexcept {
  const auto bank_slot = current_bank_slot_.load(std::memory_order_relaxed);
  if (bank_slot != kLegacyBankSlot) {
    return bank_slots_[bank_slot].bank->playback(slot);
  }
  return cooker::ResolvedPlayback{
      0,
      static_cast<std::uint32_t>(samples_[slot].size()),
      domain::TriggerMode::one_shot,
      1.0F,
      false,
  };
}

bool RealtimeEngine::publish_voice_state(
    const Voice& voice,
    RuntimeVoiceState state,
    std::uint64_t runtime_frame,
    std::uint32_t source_frame) noexcept {
  if (voice_state_stream_state_.load(std::memory_order_relaxed) ==
      RuntimeVoiceStateStreamState::corrupted) {
    return false;
  }
  if (voice_state_ring_.try_push(RuntimeVoiceStateEvent{
          voice.sequence,
          voice.slot,
          state,
          runtime_frame,
          source_frame,
      })) {
    published_voice_states_ += 1;
    return true;
  }

  auto expected = RuntimeVoiceStateStreamState::healthy;
  if (voice_state_stream_state_.compare_exchange_strong(
          expected,
          RuntimeVoiceStateStreamState::corrupted,
          std::memory_order_release,
          std::memory_order_relaxed)) {
    voice_state_drops_ += 1;
  }
  return false;
}

void RealtimeEngine::deactivate_voice(Voice& voice) noexcept {
  voice.active = false;
  trim_voice_scan_extent();
  release_voice_bank(voice);
  release_voice_pattern(voice);
  cancelled_voices_ += 1;
  active_voices_ -= 1;
}

void RealtimeEngine::trim_voice_scan_extent() noexcept {
  while (voice_scan_extent_ != 0 &&
         !voices_[voice_scan_extent_ - 1].active) {
    --voice_scan_extent_;
  }
}

void RealtimeEngine::apply_published_pattern(
    const PatternPublishEntry& publication,
    std::uint64_t runtime_frame) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_audio_observation};
  const auto current =
      current_pattern_slot_.load(std::memory_order_relaxed);
  const auto preserve_phase = pattern_slots_[publication.slot].preserve_phase;
  const auto tempo_transition = pattern_slots_[publication.slot].tempo_transition;
  const auto playing = state_.load(std::memory_order_relaxed) == RealtimeState::running &&
      (!pattern_transport_enabled_ || pattern_playing_);
  const auto position = preserve_phase
      ? pattern_position_numerator(runtime_frame) : std::optional<std::uint64_t>{0};
  const auto previous_position = preserve_phase && playing && runtime_frame != 0
      ? pattern_position_numerator(runtime_frame - 1) : std::nullopt;
  if (tempo_transition && !position) {
    // No allocation/error construction on audio, and no invented applied
    // anchor. The admitted material is retired without changing the old grid.
    pattern_slots_[publication.slot].state.store(
        PatternState::reclaimable, std::memory_order_release);
    audio_pending_pattern_generation_.store(0, std::memory_order_release);
    observed_audio_pending_ = {};
    ++transport_canceled_publications_;
    ++audio_invalid_events_;
    publish_transport_decision();
    return;
  }
  if (current != kNoPatternSlot) {
    for (auto& voice : voices_) {
      if (!preserve_phase && voice.active && voice.pattern_voice) {
        stop_voice(voice, runtime_frame, VoiceStop::declick);
      }
    }
    auto& previous = pattern_slots_[current];
    previous.state.store(
        PatternState::retiring, std::memory_order_release);
    if (previous.active_voices == 0) {
      previous.state.store(PatternState::reclaimable, std::memory_order_release);
    }
  }
  auto& next = pattern_slots_[publication.slot];
  pattern_applied_generations_[publication.slot] = publication.generation;
  pattern_applied_frames_[publication.slot] = runtime_frame;
  pattern_applied_positions_[publication.slot] = position;
  next.state.store(PatternState::current, std::memory_order_release);
  current_pattern_slot_.store(publication.slot, std::memory_order_release);
  if (!preserve_phase) {
    pattern_origin_frame_ = runtime_frame;
    pattern_continuous_timing_ = false;
    pattern_tempo_anchor_ = {runtime_frame, 0, next.pattern->bpm()};
    pattern_position_available_ = true;
    pattern_event_loop_ = 0;
  } else if (tempo_transition) {
    pattern_tempo_anchor_ = {runtime_frame, *position, next.pattern->bpm()};
    pattern_position_available_ = true;
    pattern_continuous_timing_ = true;
    for (auto& voice : voices_) {
      if (voice.active && voice.pattern_voice && !voice.releasing &&
          voice.scheduled_release_frame != 0) {
        const auto release = anchored_tick_boundary_frame(
            pattern_tempo_anchor_, voice.pattern_release_tick);
        if (release) voice.scheduled_release_frame = *release;
        else stop_voice(voice, runtime_frame, VoiceStop::declick);
      }
    }
  }
  pattern_tempo_applied_frame_ = runtime_frame;
  observed_current_pattern_generation_ = publication.generation;
  observed_audio_pending_ = {};
  publish_transport_decision();
  pattern_event_index_ = 0;
  if (preserve_phase && pattern_continuous_timing_) {
    seek_continuous_pattern_events(previous_position
        ? whole_tick(*previous_position) + 1 : 0);
  } else if (preserve_phase && runtime_frame >= pattern_origin_frame_) {
    const auto local_frame =
        (runtime_frame - pattern_origin_frame_) % next.pattern->loop_frames();
    const auto& events = next.pattern->events();
    pattern_event_index_ = static_cast<std::size_t>(std::lower_bound(
        events.begin(), events.end(), local_frame,
        [](const PreparedPatternEvent& event, std::uint64_t frame) {
          return event.start_frame < frame;
        }) - events.begin());
  }
  audio_pending_pattern_generation_.store(0, std::memory_order_release);
  applied_pattern_publications_ += 1;
}

void RealtimeEngine::start_pattern_voice(
    const PreparedPatternEvent& event,
    std::uint64_t loop_origin_frame, std::uint64_t loop_tick) noexcept {
  const auto slot = global_slot(event.slot);
  const auto playback = event.playback;
  const auto event_end_tick =
      static_cast<std::uint64_t>(event.onset_tick) + event.duration_tick;
  if (loop_tick > std::numeric_limits<std::uint64_t>::max() - event_end_tick) {
    ++audio_invalid_events_;
    return;
  }
  const auto release_tick = loop_tick + event_end_tick;
  std::uint64_t release_frame = 0;
  if (playback.trigger_mode != domain::TriggerMode::one_shot) {
    if (pattern_continuous_timing_) {
      const auto release = anchored_tick_boundary_frame(pattern_tempo_anchor_, release_tick);
      if (!release) {
        ++audio_invalid_events_;
        return;
      }
      release_frame = *release;
    } else {
      if (loop_origin_frame > std::numeric_limits<std::uint64_t>::max() - event.release_frame) {
        ++audio_invalid_events_;
        return;
      }
      release_frame = loop_origin_frame + event.release_frame;
    }
  }
  if (!valid_material(event.material) ||
      !valid_playback_range(playback, event.material.frame_count)) {
    audio_invalid_events_ += 1;
    return;
  }
  if (playback.muted) {
    return;
  }
  bool dsp_active = false;
  detail::VoiceDspState dsp{};
  if (!prepare_voice_kernel(
          playback, event.material.frame_count, dsp_active, dsp)) {
    audio_invalid_events_ += 1;
    return;
  }
  auto voice = std::find_if(
      voices_.begin(), voices_.end(), [](const Voice& candidate) {
        return !candidate.active;
      });
  if (voice == voices_.end()) {
    voice_drops_ += 1;
    return;
  }
  *voice = Voice{};
  voice->dsp_active = dsp_active;
  voice->dsp = dsp;
  voice->slot = slot;
  voice->material = event.material;
  voice->frame_count = event.material.frame_count;
  voice->start_frame = playback.start_frame;
  voice->end_frame = playback.end_frame;
  voice->cursor = playback.start_frame;
  voice->gain = (static_cast<float>(event.velocity) / 127.0F) *
                playback.linear_gain;
  voice->trigger_mode = playback.trigger_mode;
  set_voice_envelope(*voice, playback);
  voice->pattern_release_tick = release_tick;
  voice->scheduled_release_frame = release_frame;
  voice->pattern_voice = true;
  voice->origin = PadControlOrigin::performance_replay;
  voice->pattern_slot = current_pattern_slot_.load(std::memory_order_relaxed);
  voice->pattern_generation = pattern_slots_[voice->pattern_slot].generation;
  voice->active = true;
  voice_scan_extent_ = std::max(
      voice_scan_extent_, static_cast<std::size_t>(voice - voices_.begin()) + 1);
  ++pattern_slots_[voice->pattern_slot].active_voices;
  started_voices_ += 1;
  active_voices_ += 1;
  peak_voices_ = std::max(peak_voices_, active_voices_);
}

std::optional<std::uint64_t> RealtimeEngine::pattern_position_numerator(
    std::uint64_t frame) const noexcept {
  const auto slot = current_pattern_slot_.load(std::memory_order_relaxed);
  if (slot == kNoPatternSlot || !pattern_position_available_) return std::nullopt;
  if (pattern_transport_enabled_ && !pattern_playing_)
    return pattern_tempo_anchor_.tick_numerator;
  const auto& pattern = *pattern_slots_[slot].pattern;
  if (pattern_continuous_timing_) {
    if (frame < pattern_tempo_anchor_.runtime_frame) return std::nullopt;
    return integrate_tick_numerator(pattern_tempo_anchor_.tick_numerator,
        frame - pattern_tempo_anchor_.runtime_frame, pattern_tempo_anchor_.bpm);
  }
  if (frame < pattern_origin_frame_) return std::nullopt;
  const auto elapsed = frame - pattern_origin_frame_;
  const auto loops = elapsed / pattern.loop_frames();
  const auto loop_numerator =
      static_cast<std::uint64_t>(pattern.loop_length_ticks()) * kTickDenominator;
  if (loops > std::numeric_limits<std::uint64_t>::max() / loop_numerator)
    return std::nullopt;
  return integrate_tick_numerator(loops * loop_numerator,
      elapsed % pattern.loop_frames(), pattern.bpm(), pattern.ppq());
}

void RealtimeEngine::seek_continuous_pattern_events(std::uint64_t first_tick) noexcept {
  const auto slot = current_pattern_slot_.load(std::memory_order_relaxed);
  const auto& pattern = *pattern_slots_[slot].pattern;
  pattern_event_loop_ = first_tick / pattern.loop_length_ticks();
  const auto local_tick = first_tick % pattern.loop_length_ticks();
  const auto& events = pattern.events();
  pattern_event_index_ = static_cast<std::size_t>(std::lower_bound(
      events.begin(), events.end(), local_tick,
      [](const PreparedPatternEvent& event, std::uint64_t tick) {
        return event.onset_tick < tick;
      }) - events.begin());
  if (!events.empty() && pattern_event_index_ == events.size()) {
    pattern_event_index_ = 0;
    ++pattern_event_loop_;
  }
}

void RealtimeEngine::schedule_pattern_events(
    std::uint64_t runtime_frame) noexcept {
  const auto slot =
      current_pattern_slot_.load(std::memory_order_relaxed);
  if (slot == kNoPatternSlot) {
    return;
  }
  const auto& pattern = *pattern_slots_[slot].pattern;
  if (pattern_continuous_timing_) {
    const auto numerator = pattern_position_numerator(runtime_frame);
    const auto& events = pattern.events();
    if (!numerator || events.empty()) return;
    const auto length = pattern.loop_length_ticks();
    while (pattern_event_index_ < events.size()) {
      const auto& event = events[pattern_event_index_];
      if (pattern_event_loop_ >
          (std::numeric_limits<std::uint64_t>::max() - event.onset_tick) / length)
        return;
      const auto loop_tick = pattern_event_loop_ * length;
      const auto tick = loop_tick + event.onset_tick;
      if (tick > *numerator / kTickDenominator) return;
      start_pattern_voice(event, runtime_frame, loop_tick);
      if (++pattern_event_index_ == events.size()) {
        pattern_event_index_ = 0;
        ++pattern_event_loop_;
      }
    }
    return;
  }
  const auto origin =
      pattern_origin_frame_;
  if (runtime_frame < origin) {
    return;
  }
  const auto elapsed = runtime_frame - origin;
  const auto local_frame = elapsed % pattern.loop_frames();
  const auto loop_origin_frame = runtime_frame - local_frame;
  if (local_frame == 0) {
    pattern_event_index_ = 0;
  }
  const auto& events = pattern.events();
  while (pattern_event_index_ < events.size() &&
         events[pattern_event_index_].start_frame == local_frame) {
    start_pattern_voice(
        events[pattern_event_index_], loop_origin_frame,
        (elapsed / pattern.loop_frames()) * pattern.loop_length_ticks());
    ++pattern_event_index_;
  }
}

void RealtimeEngine::stop_voice(
    Voice& voice, std::uint64_t runtime_frame, VoiceStop how) noexcept {
  if (!voice.active) {
    return;
  }
  if (voice.releasing) {
    // A second stop (any stop that reaches a voice already in its release
    // tail) ends the tail. The stopped edge was already published when the release began,
    // so only the physical end remains. A neutral voice's 96-frame tail is
    // hard-killed, as it always has been. A kernel voice never steps to
    // silence: a tail with at most 96 frames left finishes, and a longer one
    // fades from its current gain over the declick.
    if (voice.release_frames_remaining <= kRealtimeRampFrames) {
      if (!voice.dsp_active) {
        deactivate_voice(voice);
      }
      return;
    }
#if LMDJ_VOICE_DSP
    const float current =
        voice.release_frames_remaining < voice.release_frames
            ? static_cast<float>(voice.release_frames_remaining) *
                  voice.release_scale
            : 1.0F;
    voice.release_scale = current / static_cast<float>(kRealtimeRampFrames);
    voice.release_frames = kRealtimeRampFrames + 1;
    voice.release_frames_remaining = kRealtimeRampFrames;
#endif
    return;
  }
  // `RuntimeVoiceState` is keyed by Pad slot. An audition owns no Pad, so
  // publishing one would report a Pad the user never triggered as playing.
  if (!voice.pattern_voice && !is_audition_bank_slot(voice.bank_slot) &&
      voice.origin == PadControlOrigin::host_input) {
    static_cast<void>(publish_voice_state(
        voice,
        RuntimeVoiceState::stopped,
        runtime_frame,
        voice.dsp_active ? detail::voice_dsp_source_frame(voice.dsp)
                         : voice.cursor));
  }
  // The voice keeps rendering its release tail (at least kRealtimeRampFrames)
  // to avoid a step discontinuity; the logical stop (publication) has
  // already happened.
  voice.releasing = true;
#if LMDJ_VOICE_DSP
  // Only a release event plays the Pad's release; any other stop ends the
  // voice over the declick (decision 2026-09-30 point 5, owner 2026-10-02).
  if (how == VoiceStop::declick) {
    voice.release_frames = kRealtimeRampFrames;
    voice.release_scale = kRealtimeRampScale;
  }
  // A release that starts during a user attack fades from the attack's
  // current level, so it never grows louder after the stop. The tail keeps
  // its length; its first frame is that level, so nothing steps.
  if (voice.attack_frames_remaining != 0 &&
      voice.attack_frames > kRealtimeRampFrames) {
    const float level =
        static_cast<float>(voice.attack_frames - voice.attack_frames_remaining) *
        voice.attack_scale;
    if (level == 0.0F) {
      // Released before its attack sounded (a press and its release in one
      // callback): nothing to fade, so the voice ends now instead of holding
      // a slot through a silent tail (owner 2026-10-02). An offline release
      // always starts at least one frame into its voice.
      deactivate_voice(voice);
      return;
    }
    voice.attack_frames_remaining = 0;
    voice.release_scale = level / static_cast<float>(voice.release_frames);
    voice.release_frames_remaining = voice.release_frames;
    voice.release_frames += 1;
    return;
  }
#else
  static_cast<void>(how);
#endif
  voice.release_frames_remaining = voice.release_frames;
}

void RealtimeEngine::capture_voice_start(
    const PadControlEvent& event,
    std::uint64_t absolute_start_frame) noexcept {
  const auto state = capture_state_.load(std::memory_order_acquire);
  if (state != CaptureState::active &&
      state != CaptureState::disarm_pending) {
    return;
  }

  const auto origin =
      capture_origin_frame_;
  const auto offset = absolute_start_frame - origin;
  if (absolute_start_frame < origin ||
      offset > std::numeric_limits<std::uint32_t>::max() ||
      !capture_ring_->try_push(CapturedTriggerEvent{
          event.sequence,
          event.slot,
          event.velocity,
          static_cast<std::uint32_t>(offset),
      })) {
    capture_drops_ += 1;
    capture_state_.store(CaptureState::corrupted,
                         std::memory_order_release);
    return;
  }
  captured_events_ += 1;
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::capture_event_published);
#endif
}

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
  if (mono_pcm.size() > kRealtimeMaximumSampleFrames) {
    return invalid_argument("realtime sample PCM is too large");
  }
  if (!std::all_of(mono_pcm.begin(), mono_pcm.end(), [](float value) {
        return std::isfinite(value);
      })) {
    return invalid_argument(
        "realtime sample PCM must contain only finite values");
  }

  samples_[slot].assign(mono_pcm.begin(), mono_pcm.end());
  select_legacy_samples_quiescent();
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
  select_legacy_samples_quiescent();
  return foundation::Result<void>::success();
}

// The Sound Set audition publication path (#799). It mirrors
// `publish_sample_bank`'s protocol rather than inventing one, and that is
// load-bearing rather than tidiness.
//
// An earlier revision published, swapped `current_audition_slot_` and retired
// the outgoing Bank all on the control thread, on the reasoning that an
// audition shares nothing with a Project Bank. It raced: every Bank read on the
// voice-start path happens before `++owner->active_voices`, so a control-thread
// `retire_audition` could observe `active_voices == 0`, mark the Bank
// reclaimable, and have the sweep free it while a voice was mid-read of that
// same `std::vector`. It also read `active_voices` across threads, which is a
// data race in its own right. Neither is visible to a single-threaded test.
//
// The Project protocol is not more complicated than it needs to be; it is that
// complicated because of exactly this. Priming an `empty` slot here and letting
// the audio thread apply and retire inside `render` is what serialises
// retirement against voice starts.
//
// What stays different is only what must: the audition pool is outside
// `bank_slots_`, so this never reports `bank_slot_rejections_`, never calls
// `apply_published_bank`, and so never writes `current_bank_slot_` or
// `availability_mask_`.
PublishResult RealtimeEngine::publish_audition_bank(
    PreparedSampleBank&& bank) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};

  auto free_slot = std::find_if(
      audition_slots_.begin(),
      audition_slots_.end(),
      [](const BankSlot& candidate) {
        return candidate.state.load(std::memory_order_acquire) ==
               BankState::empty;
      });
  if (free_slot == audition_slots_.end()) {
    // Both audition slots are still draining. This never consumes or reports a
    // Project Bank slot, so `bank_slot_rejections_` is deliberately untouched:
    // that counter measures Project pressure, and audition pressure reported
    // through it would misdescribe the Project pool.
    //
    // Nor is `state_` re-checked here. A slot stays non-empty until the audio
    // thread drains it, so this refusal is correct whether or not the engine
    // stopped in the meantime, and re-reading `state_` would only widen the
    // window without changing the answer.
    return PublishResult::bank_slots_full;
  }

  // Deliberately no `events_pending` guard, unlike `publish_sample_bank`. That
  // guard is Pad-pool-specific: `enqueue_control` validates a press against
  // `availability_mask_`, so an in-flight press admitted against Bank N must
  // not be served by Bank N+1. An audition publication writes no
  // `availability_mask_` and can serve no Pad event, so no in-flight event can
  // be mis-served by it.
  //
  // The audition's own in-flight case is decided rather than accidental:
  // publish A, enqueue `audition_start`, publish B, then render plays B,
  // because `render` drains this queue before the control events. That is
  // replace semantics working as specified -- the last publication wins -- and
  // reaching it at all requires two publications inside one callback, which is
  // a user clicking preview twice in under a buffer. Do not "fix" this
  // asymmetry into an `events_pending` refusal; it would refuse exactly the
  // browse-and-preview sequence the feature exists for.

  const auto slot_index = static_cast<std::uint8_t>(
      std::distance(audition_slots_.begin(), free_slot));
  // Safe on the control thread only because the slot is `empty`: no voice can
  // reference a Bank that was never current, so nothing reads these writes.
  free_slot->bank.emplace(std::move(bank));
  free_slot->active_voices = 0;
  free_slot->generation = next_bank_generation_++;

  const auto running =
      state_.load(std::memory_order_acquire) == RealtimeState::running;
  if (!running) {
    // Nothing is rendering, so there is no voice to race and applying here is
    // the same quiescent case `publish_sample_bank` handles inline.
    apply_published_audition(slot_index);
    return PublishResult::accepted;
  }

  free_slot->state.store(BankState::pending, std::memory_order_release);
  if (!audition_publish_queue_.try_push(slot_index)) {
    // Unreachable while the queue is sized to the pool -- a full queue needs
    // every slot `pending`, and reaching this push needed one `empty`. Kept
    // complete anyway, because a future capacity divergence makes it live.
    free_slot->bank.reset();
    free_slot->generation = 0;
    free_slot->state.store(BankState::empty, std::memory_order_release);
    return PublishResult::publish_queue_full;
  }
  return PublishResult::accepted;
}

PublishResult RealtimeEngine::publish_sample_bank(
    PreparedSampleBank&& bank) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  const auto running =
      state_.load(std::memory_order_acquire) == RealtimeState::running;
  if (running &&
      queued_host_input_events_.load(std::memory_order_acquire) != 0) {
    return PublishResult::events_pending;
  }

  auto slot = std::find_if(
      bank_slots_.begin(), bank_slots_.end(), [](const BankSlot& candidate) {
        return candidate.state.load(std::memory_order_acquire) ==
               BankState::empty;
      });
  if (slot == bank_slots_.end()) {
    bank_slot_rejections_ += 1;
    return PublishResult::bank_slots_full;
  }

  const auto slot_index = static_cast<std::uint8_t>(
      std::distance(bank_slots_.begin(), slot));
  slot->bank.emplace(std::move(bank));
  slot->active_voices = 0;
  slot->generation = next_bank_generation_++;

  if (!running) {
    apply_published_bank(slot_index);
    accepted_publications_ += 1;
    return PublishResult::accepted;
  }

  slot->state.store(BankState::pending, std::memory_order_release);
  pending_publications_.fetch_add(1, std::memory_order_release);
  // With the current equal Bank and publish-queue capacities this push cannot
  // fail: a full queue already owns every Bank slot in `pending`, while
  // reaching this point requires another slot found in `empty`. Keep the
  // rollback defensive and complete, though, because a future capacity
  // divergence can make the queue the first wall (Issue #205).
  if (!publish_queue_.try_push(slot_index)) {
    pending_publications_.fetch_sub(1, std::memory_order_release);
    slot->bank.reset();
    slot->generation = 0;
    slot->state.store(BankState::empty, std::memory_order_release);
    publish_queue_drops_ += 1;
    return PublishResult::publish_queue_full;
  }
  accepted_publications_ += 1;
  return PublishResult::accepted;
}

foundation::Result<void> RealtimeEngine::enable_pattern_transport(
    std::uint64_t generation) {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped ||
      generation == 0 || generation <= last_pattern_transport_generation_ ||
      !scheduled_pattern_record_quiescent()) {
    return invalid_argument("Pattern transport requires a fresh quiescent generation");
  }
  scheduled_record_enabled_ = false;
  pattern_transport_enabled_ = true;
  pattern_transport_generation_ = generation;
  last_pattern_transport_generation_ = generation;
  pattern_transport_epoch_ = 0;
  return foundation::Result<void>::success();
}

PatternTransportSubmit RealtimeEngine::submit_pattern_transport(
    const PatternTransportCommand& command) {
  if (!pattern_transport_enabled_) return PatternTransportSubmit::disabled;
  if (state_.load(std::memory_order_acquire) != RealtimeState::running)
    return PatternTransportSubmit::not_running;
  if (pattern_transport_generation_ == 0 ||
      command.runtime_generation != pattern_transport_generation_)
    return PatternTransportSubmit::stale_generation;
  const auto schedule = scheduled_tag_.load(std::memory_order_seq_cst);
  const bool scheduled_cutoff = scheduled_request_ && scheduled_cancel_ &&
      !scheduled_cancel_won_ && command.epoch == scheduled_cancel_->epoch &&
      (schedule_phase(schedule) == ScheduledPatternPhase::starting ||
       schedule_phase(schedule) == ScheduledPatternPhase::applied) &&
      command.action != PatternTransportAction::start;
  if (pattern_transport_reserved_ || (scheduled_request_ && !scheduled_cutoff))
    return PatternTransportSubmit::busy;
  if (command.epoch == 0 || command.epoch <= pattern_transport_epoch_ ||
      (pattern_transport_epoch_ == 0 && command.epoch != 1))
    return PatternTransportSubmit::stale_epoch;
  if (command.action != PatternTransportAction::start &&
      command.action != PatternTransportAction::stop &&
      command.action != PatternTransportAction::fence)
    return PatternTransportSubmit::invalid_action;
  if (command.action == PatternTransportAction::start && control_pattern_playing_)
    return PatternTransportSubmit::invalid_action;
  if (command.action == PatternTransportAction::fence &&
      !control_pattern_playing_ && !scheduled_cutoff)
    return PatternTransportSubmit::not_running;

  PatternTransportCommandCell cell{command.runtime_generation, command.epoch,
      0, command.action, kNoPatternSlot};
  if (command.pending_switch_predecessor && !command.pending_switch)
    return PatternTransportSubmit::identity_mismatch;
  if (command.pending_switch && command.pending_switch_predecessor &&
      command.pending_switch->generation ==
          command.pending_switch_predecessor->generation)
    return PatternTransportSubmit::identity_mismatch;
  const auto name = [&](const std::optional<PatternReplacementAuthority>& authority,
                        std::uint8_t& named_slot,
                        std::uint64_t& named_generation) {
    if (!authority) return PatternTransportSubmit::accepted;
    if (command.action == PatternTransportAction::start)
      return PatternTransportSubmit::invalid_action;
    if (authority->generation == 0 ||
        authority->generation == command.expected_pattern_generation)
      return PatternTransportSubmit::identity_mismatch;
    for (std::size_t i = 0; i < pattern_slots_.size(); ++i) {
      const auto& slot = pattern_slots_[i];
      const auto slot_state = slot.state.load(std::memory_order_acquire);
      if ((slot_state == PatternState::current || slot_state == PatternState::pending) &&
          slot.generation == authority->generation &&
          slot.activation_frame == authority->activation_frame &&
          slot.pattern->pattern_id() == authority->pattern_id) {
        named_slot = static_cast<std::uint8_t>(i);
        named_generation = slot.generation;
        return PatternTransportSubmit::accepted;
      }
    }
    return PatternTransportSubmit::identity_mismatch;
  };
  auto named = name(command.pending_switch, cell.switch_slot, cell.switch_generation);
  if (named != PatternTransportSubmit::accepted) return named;
  named = name(command.pending_switch_predecessor,
               cell.predecessor_slot, cell.predecessor_generation);
  if (named != PatternTransportSubmit::accepted) return named;
  const auto names_generation = [&](std::uint64_t generation) {
    return generation != 0 &&
        (generation == cell.switch_generation ||
         generation == cell.predecessor_generation);
  };
  // Every outstanding slot/token must be named. The additional authority
  // extends the bounded set, never the accepted predecessor or ownership rule.
  for (const auto& slot : pattern_slots_) {
    if (slot.state.load(std::memory_order_acquire) == PatternState::pending &&
        !names_generation(slot.generation))
      return PatternTransportSubmit::identity_mismatch;
  }
  // Q releases after A; A releases after current. Keep this admission order.
  const auto queued = queued_pattern_generation_.load(std::memory_order_acquire);
  const auto pending = audio_pending_pattern_generation_.load(std::memory_order_acquire);
  if ((pattern_token_generation(queued) != 0 &&
       !names_generation(pattern_token_generation(queued))) ||
      (pattern_token_generation(pending) != 0 &&
       !names_generation(pattern_token_generation(pending))))
    return PatternTransportSubmit::identity_mismatch;
  const auto current = current_pattern_slot_.load(std::memory_order_acquire);
  if (current == kNoPatternSlot ||
      (pattern_slots_[current].generation != command.expected_pattern_generation &&
       (!names_generation(pattern_slots_[current].generation) ||
        acknowledged_pattern_generation_ == 0 ||
        command.expected_pattern_generation != acknowledged_pattern_generation_)))
    return PatternTransportSubmit::identity_mismatch;
  for (std::size_t i = 0; i < pattern_slots_.size(); ++i) {
    if (pattern_slots_[i].pattern) {
      retained_transport_ids_[i] = pattern_slots_[i].pattern->pattern_id();
      retained_transport_bpms_[i] = pattern_slots_[i].pattern->bpm();
    } else {
      retained_transport_ids_[i].reset();
    }
  }
  retained_transport_switch_ = command.pending_switch;
  retained_transport_predecessor_ = command.pending_switch_predecessor;
  pattern_transport_reserved_ = true;
  pattern_transport_epoch_ = command.epoch;
  static_cast<void>(pattern_transport_commands_.try_push(cell));
  return PatternTransportSubmit::accepted;
}

std::optional<PatternTransportReceipt>
RealtimeEngine::inspect_pattern_transport_receipt(
    std::uint64_t generation, std::uint64_t epoch) const {
  if (generation == 0 || epoch == 0 ||
      !pattern_transport_reserved_ || generation != pattern_transport_generation_ ||
      epoch != pattern_transport_epoch_) return std::nullopt;
  if (!retained_transport_receipt_) {
    PatternTransportReceiptCell cell;
    if (!pattern_transport_receipts_.try_pop(cell)) return std::nullopt;
    if (cell.generation != generation || cell.epoch != epoch) return std::nullopt;
    retained_transport_receipt_ = cell;
  }
  const auto& cell = *retained_transport_receipt_;
  if (cell.generation != generation || cell.epoch != epoch) return std::nullopt;
  if (scheduled_cancel_ && !scheduled_cancel_won_ &&
      scheduled_cancel_->epoch == epoch) scheduled_cutoff_receipt_ = cell;
  const auto legacy_decision = cell.legacy_is_predecessor
      ? cell.predecessor_decision : cell.decision;
  const auto legacy_authority = cell.legacy_is_predecessor
      ? retained_transport_predecessor_ : retained_transport_switch_;
  const auto legacy_frame = cell.legacy_is_predecessor
      ? cell.predecessor_applied_frame : cell.switch_applied_frame;
  PatternTransportReceipt receipt{cell.generation, cell.epoch, cell.effective_frame,
      cell.origin_frame, cell.pattern_generation,
      *retained_transport_ids_[cell.pattern_slot],
      retained_transport_bpms_[cell.pattern_slot], cell.playing, legacy_decision,
      legacy_authority,
      legacy_decision == PatternCutoffDecision::applied_before_cutoff
          ? std::optional<std::uint64_t>{legacy_frame} : std::nullopt};
  const auto outcome = [](const auto& authority, auto decision, auto frame)
      -> std::optional<PatternTransportSwitchOutcome> {
    if (!authority) return std::nullopt;
    return PatternTransportSwitchOutcome{*authority, decision,
        decision == PatternCutoffDecision::applied_before_cutoff
            ? std::optional<std::uint64_t>{frame} : std::nullopt};
  };
  receipt.tempo_anchor = cell.tempo_anchor;
  receipt.switch_outcomes[0] = outcome(
      retained_transport_switch_, cell.decision, cell.switch_applied_frame);
  receipt.switch_outcomes[1] = outcome(retained_transport_predecessor_,
      cell.predecessor_decision, cell.predecessor_applied_frame);
  return receipt;
}

bool RealtimeEngine::acknowledge_pattern_transport_receipt(
    std::uint64_t generation, std::uint64_t epoch) noexcept {
  if (generation == 0 || epoch == 0 ||
      !pattern_transport_reserved_ || !retained_transport_receipt_ ||
      generation != pattern_transport_generation_ || epoch != pattern_transport_epoch_ ||
      retained_transport_receipt_->generation != generation ||
      retained_transport_receipt_->epoch != epoch)
    return false;
  if (scheduled_cancel_ && !scheduled_cancel_won_ &&
      scheduled_cancel_->epoch == epoch)
    scheduled_cutoff_receipt_ = *retained_transport_receipt_;
  control_pattern_playing_ = retained_transport_receipt_->playing;
  acknowledged_pattern_generation_ = retained_transport_receipt_->pattern_generation;
  retained_transport_receipt_.reset();
  retained_transport_switch_.reset();
  retained_transport_predecessor_.reset();
  pattern_transport_reserved_ = false;
  return true;
}

void RealtimeEngine::apply_pattern_transport(std::uint64_t frame) noexcept {
  PatternTransportCommandCell command;
  if (!pattern_transport_commands_.try_pop(command)) return;
  PatternTransportReceiptCell receipt{};
  receipt.generation = command.generation;
  receipt.epoch = command.epoch;
  receipt.effective_frame = frame;
  const auto resolve = [&](std::uint8_t slot_index, std::uint64_t generation,
                           PatternCutoffDecision& decision,
                           std::uint64_t& applied_frame) noexcept {
    if (slot_index == kNoPatternSlot) return;
    auto& slot = pattern_slots_[slot_index];
    const auto slot_state = slot.state.load(std::memory_order_relaxed);
    // A second successor can make an applied first one retiring. Its payload
    // and apply evidence remain retained; never free its sounding voices.
    if (slot.generation == generation &&
        pattern_applied_generations_[slot_index] == generation &&
        slot_state != PatternState::pending &&
        (slot_state == PatternState::current || slot_state == PatternState::retiring ||
         slot_state == PatternState::reclaimable) &&
        pattern_applied_frames_[slot_index] < frame) {
      decision = PatternCutoffDecision::applied_before_cutoff;
      applied_frame = pattern_applied_frames_[slot_index];
      return;
    }
    std::uint32_t canceled_token = 0;
    if (audio_pending_pattern_ &&
        audio_pending_pattern_->generation == generation) {
      canceled_token = audio_pending_pattern_generation_.exchange(
          0, std::memory_order_acq_rel);
      audio_pending_pattern_.reset();
      observed_audio_pending_ = {};
    } else {
      canceled_token = queued_pattern_generation_.exchange(
          0, std::memory_order_seq_cst);
    }
    slot.state.store(PatternState::reclaimable, std::memory_order_release);
    decision = PatternCutoffDecision::canceled_at_cutoff;
    observed_claimed_through_ = std::max(observed_claimed_through_, generation);
    if (pattern_slot_token(canceled_token) != 0)
      ++transport_canceled_publications_;
  };
  // Resolve the audio-owned predecessor first, then Q. Both are immutable and
  // fully named by admission; no control mutation can enter while reserved.
  resolve(command.predecessor_slot, command.predecessor_generation,
          receipt.predecessor_decision, receipt.predecessor_applied_frame);
  resolve(command.switch_slot, command.switch_generation,
          receipt.decision, receipt.switch_applied_frame);
  receipt.legacy_is_predecessor =
      receipt.predecessor_decision == PatternCutoffDecision::applied_before_cutoff &&
      receipt.decision != PatternCutoffDecision::applied_before_cutoff;
  const auto cutoff_position = pattern_position_numerator(frame);
  const auto current_slot = current_pattern_slot_.load(std::memory_order_relaxed);
  const auto bpm = pattern_slots_[current_slot].pattern->bpm();
  if (command.action == PatternTransportAction::start) {
    pattern_playing_ = true;
    pattern_origin_frame_ = frame;
    pattern_event_index_ = 0;
    pattern_event_loop_ = 0;
    pattern_tempo_anchor_ = {frame, 0, bpm};
    pattern_position_available_ = true;
    pattern_tempo_applied_frame_ = frame;
    pattern_continuous_timing_ = false;
  } else if (command.action == PatternTransportAction::stop) {
    pattern_position_available_ = cutoff_position.has_value();
    if (cutoff_position) pattern_tempo_anchor_ = {frame, *cutoff_position, bpm};
    pattern_playing_ = false;
    for (auto& voice : voices_) {
      if (voice.active && voice.pattern_voice &&
          voice.pattern_slot < pattern_slots_.size() &&
          voice.pattern_generation == pattern_slots_[voice.pattern_slot].generation)
        stop_voice(voice, frame, VoiceStop::declick);
    }
  }
  if (command.action != PatternTransportAction::start) {
    const auto tag = scheduled_tag_.load(std::memory_order_seq_cst);
    if (schedule_phase(tag) == ScheduledPatternPhase::starting ||
        schedule_phase(tag) == ScheduledPatternPhase::applied ||
        schedule_phase(tag) == ScheduledPatternPhase::empty)
      scheduled_cutoff_serial_.store(tag >> 4U, std::memory_order_seq_cst);
  }
  receipt.origin_frame = pattern_origin_frame_;
  if (command.action == PatternTransportAction::start)
    receipt.tempo_anchor = TransportAnchor{frame, 0, bpm};
  else if (cutoff_position)
    receipt.tempo_anchor = TransportAnchor{frame, *cutoff_position, bpm};
  receipt.playing = pattern_playing_;
  receipt.pattern_slot = current_pattern_slot_.load(std::memory_order_relaxed);
  receipt.pattern_generation = pattern_slots_[receipt.pattern_slot].generation;
  publish_transport_decision();
  static_cast<void>(pattern_transport_receipts_.try_push(receipt));
}

foundation::Result<void> RealtimeEngine::enable_scheduled_pattern_record(
    std::uint64_t generation) {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped ||
      !pattern_transport_enabled_ || generation == 0 ||
      generation != pattern_transport_generation_ ||
      !scheduled_pattern_record_quiescent())
    return invalid_argument("scheduled Record requires a quiescent transport generation");
  scheduled_record_enabled_ = true;
  scheduled_settled_serial_.store(0, std::memory_order_release);
  return foundation::Result<void>::success();
}

ScheduledPatternSubmit RealtimeEngine::submit_scheduled_pattern_record(
    const ScheduledPatternRecordRequest& request) {
  if (!scheduled_record_enabled_) return ScheduledPatternSubmit::disabled;
  if (state_.load(std::memory_order_acquire) != RealtimeState::running)
    return ScheduledPatternSubmit::not_running;
  if (request.runtime_generation == 0 ||
      request.runtime_generation != pattern_transport_generation_)
    return ScheduledPatternSubmit::stale_generation;
  if (request.frame_epoch == 0 || request.frame_epoch != start_epoch_)
    return ScheduledPatternSubmit::stale_frame_epoch;
  if (scheduled_request_ || pattern_transport_reserved_)
    return ScheduledPatternSubmit::busy;
  if (request.epoch == 0 || request.epoch <= pattern_transport_epoch_ ||
      (pattern_transport_epoch_ == 0 && request.epoch != 1))
    return ScheduledPatternSubmit::stale_epoch;
  if (request.epoch == std::numeric_limits<std::uint64_t>::max())
    return ScheduledPatternSubmit::exhausted;
  if (last_schedule_serial_ == kScheduledPatternSerialMaximum ||
      request.serial > kScheduledPatternSerialMaximum)
    return ScheduledPatternSubmit::exhausted;
  if (request.serial == 0 || request.serial <= last_schedule_serial_)
    return ScheduledPatternSubmit::stale_serial;
  if (request.bars != 1 && request.bars != 2)
    return ScheduledPatternSubmit::invalid_bars;
  if (control_pattern_playing_) return ScheduledPatternSubmit::not_stopped;
  const auto observation = pattern_transport_observation();
  if (!observation || observation->pending_switches[0] ||
      observation->pending_switches[1] || observation->outstanding_cancellation)
    return ScheduledPatternSubmit::busy;
  const auto slot = current_pattern_slot_.load(std::memory_order_acquire);
  if (slot == kNoPatternSlot || request.expected_pattern_generation == 0 ||
      pattern_slots_[slot].generation != request.expected_pattern_generation ||
      pattern_slots_[slot].pattern->pattern_id() != request.pattern_id)
    return ScheduledPatternSubmit::identity_mismatch;
  const auto& pattern = *pattern_slots_[slot].pattern;
  const auto maximum = std::numeric_limits<std::uint64_t>::max();
  const auto frontier = transport_decision_.read().rendered_frames;
  if (pattern.bar_frames() == 0 ||
      frontier == maximum ||
      pattern.bar_frames() > (maximum - frontier - 1) / request.bars ||
      next_cue_batch_id_.load(std::memory_order_acquire) == maximum)
    return ScheduledPatternSubmit::exhausted;
  // Control pins protect the payload until Preparing establishes its separate
  // audio borrow. Acknowledgment releases only this pin, never that borrow.
  scheduled_request_ = request;
  ++pattern_slots_[slot].scheduled_control_pins;
  scheduled_payload_ = {request.runtime_generation, request.frame_epoch,
      request.epoch, request.serial, request.expected_pattern_generation,
      pattern.bar_frames(), 0, 0, pattern.bpm(), request.bars, slot, false};
  scheduled_cancel_.reset();
  scheduled_start_acknowledged_ = false;
  scheduled_cancel_acknowledged_ = false;
  scheduled_cancel_won_ = false;
  scheduled_cancel_invalidated_ = false;
  scheduled_cutoff_receipt_.reset();
  last_schedule_serial_ = request.serial;
  scheduled_settled_serial_.store(0, std::memory_order_release);
  pattern_transport_epoch_ = request.epoch;
  scheduled_tag_.store(schedule_tag(request.serial, ScheduledPatternPhase::submitted),
      std::memory_order_seq_cst);
  return ScheduledPatternSubmit::accepted;
}

std::optional<ScheduledPatternRecordStatus>
RealtimeEngine::inspect_scheduled_pattern_record(
    std::uint64_t generation, std::uint64_t serial) const {
  if (!scheduled_request_ || generation == 0 || serial == 0 ||
      scheduled_request_->runtime_generation != generation ||
      scheduled_request_->serial != serial) return std::nullopt;
  const auto tag = scheduled_tag_.load(std::memory_order_seq_cst);
  if ((tag >> 4U) != serial) return std::nullopt;
  const auto phase = schedule_phase(tag);
  const auto timing = scheduled_timing_.read();
  const auto& request = *scheduled_request_;
  ScheduledPatternRecordStatus result{generation, request.frame_epoch, serial,
      phase, request.bars, scheduled_payload_.bpm, scheduled_payload_.bar_frames,
      {}, {}, {}, {}};
  if (timing.serial == serial && timing.timed) {
    result.count_in_frame = timing.count_in_frame;
    result.start_frame = timing.start_frame;
  }
  const auto receipt = [&](std::uint64_t epoch, ScheduledPatternResult outcome,
                           std::optional<std::uint64_t> frame, bool playing) {
    return ScheduledPatternRecordReceipt{generation, request.frame_epoch, serial,
        epoch, request.expected_pattern_generation, request.pattern_id,
        outcome, outcome == ScheduledPatternResult::applied ? frame : std::nullopt,
        outcome == ScheduledPatternResult::applied ? result.start_frame : std::nullopt, playing};
  };
  if (!scheduled_start_acknowledged_) {
    if (phase == ScheduledPatternPhase::applied)
      result.start_receipt = receipt(request.epoch, ScheduledPatternResult::applied,
          result.start_frame, true);
    else if (phase == ScheduledPatternPhase::cancelled)
      result.start_receipt = receipt(request.epoch, ScheduledPatternResult::cancelled,
          std::nullopt, false);
    else if (phase == ScheduledPatternPhase::refused)
      result.start_receipt = receipt(request.epoch, ScheduledPatternResult::refused,
          std::nullopt, false);
  }
  if (scheduled_cancel_ && !scheduled_cancel_acknowledged_) {
    if (scheduled_cancel_won_ && phase == ScheduledPatternPhase::cancelled)
      result.cancel_receipt = receipt(scheduled_cancel_->epoch,
          ScheduledPatternResult::cancelled, std::nullopt, false);
    else if (scheduled_cancel_invalidated_) {
      // Exceptional owner invalidation has NO e2 command, effective F or
      // origin F. Failure evidence does not claim a durable closure.
      result.cancel_receipt = ScheduledPatternRecordReceipt{generation,
          request.frame_epoch, serial, scheduled_cancel_->epoch,
          request.expected_pattern_generation, request.pattern_id,
          ScheduledPatternResult::refused, {}, {}, false};
    } else if (!scheduled_cancel_won_) {
      if (!scheduled_cutoff_receipt_)
        static_cast<void>(inspect_pattern_transport_receipt(generation,
            scheduled_cancel_->epoch));
      if (scheduled_cutoff_receipt_) {
        const auto& cutoff = *scheduled_cutoff_receipt_;
        result.cancel_receipt = receipt(cutoff.epoch, ScheduledPatternResult::applied,
            cutoff.effective_frame, cutoff.playing);
      }
    }
  }
  return result;
}

ScheduledPatternSubmit RealtimeEngine::cancel_scheduled_pattern_record(
    const ScheduledPatternCancelRequest& request) {
  if (!scheduled_request_ || request.runtime_generation == 0 ||
      request.runtime_generation != scheduled_request_->runtime_generation)
    return ScheduledPatternSubmit::stale_generation;
  if (request.frame_epoch != scheduled_request_->frame_epoch)
    return ScheduledPatternSubmit::stale_frame_epoch;
  if (request.serial == 0 || request.serial != scheduled_request_->serial)
    return ScheduledPatternSubmit::stale_serial;
  if (scheduled_cancel_ || pattern_transport_reserved_)
    return ScheduledPatternSubmit::busy;
  if (request.epoch == 0 || request.epoch <= pattern_transport_epoch_)
    return ScheduledPatternSubmit::stale_epoch;
  // Control may retry a racing phase change; the audio thread never retries.
  auto tag = scheduled_tag_.load(std::memory_order_seq_cst);
  for (;;) {
    const auto phase = schedule_phase(tag);
    auto target = ScheduledPatternPhase::cancelled;
    if (phase == ScheduledPatternPhase::preparing)
      target = ScheduledPatternPhase::cancel_preparing;
    else if (phase == ScheduledPatternPhase::starting ||
             phase == ScheduledPatternPhase::applied) {
      // Retain the second intent without consuming its epoch/reservation.
      // Facade submits its genuine ordinary Stop or recording fence; only that
      // command's applied receipt establishes F and closes input admission.
      scheduled_cancel_ = request;
      scheduled_cancel_won_ = false;
      // A retained Applied start can receive its original second intent only
      // after the callback owner has stopped. With no submitted command or
      // actual F left to reconcile, retain terminal refusal for that exact e2;
      // do not spend its ordinary epoch or manufacture a cutoff frame.
      if (phase == ScheduledPatternPhase::applied &&
          state_.load(std::memory_order_acquire) == RealtimeState::stopped &&
          !pattern_transport_reserved_ && !scheduled_cutoff_receipt_ &&
          !retained_transport_receipt_ && pattern_transport_commands_.size_approx() == 0)
        scheduled_cancel_invalidated_ = true;
      return ScheduledPatternSubmit::start_won;
    } else if (phase != ScheduledPatternPhase::submitted &&
               phase != ScheduledPatternPhase::armed) {
      return ScheduledPatternSubmit::busy;
    }
    if (scheduled_tag_.compare_exchange_strong(tag,
            schedule_tag(request.serial, target), std::memory_order_seq_cst,
            std::memory_order_seq_cst)) {
      scheduled_cancel_ = request;
      scheduled_cancel_won_ = true;
      pattern_transport_epoch_ = request.epoch;
      return ScheduledPatternSubmit::accepted;
    }
  }
}

void RealtimeEngine::retire_scheduled_control_cell() noexcept {
  if (!scheduled_request_ || !scheduled_start_acknowledged_ ||
      (scheduled_cancel_ && !scheduled_cancel_acknowledged_)) return;
  --pattern_slots_[scheduled_payload_.pattern_slot].scheduled_control_pins;
  scheduled_request_.reset();
  scheduled_cancel_.reset();
  scheduled_cutoff_receipt_.reset();
  if (state_.load(std::memory_order_acquire) == RealtimeState::stopped) {
    pattern_transport_generation_ = 0;
    pattern_transport_epoch_ = 0;
  }
  scheduled_tag_.store(schedule_tag(last_schedule_serial_, ScheduledPatternPhase::empty),
      std::memory_order_seq_cst);
}

bool RealtimeEngine::acknowledge_scheduled_pattern_record(
    std::uint64_t generation, std::uint64_t serial, std::uint64_t epoch) noexcept {
  if (!scheduled_request_ || scheduled_request_->runtime_generation != generation ||
      scheduled_request_->serial != serial || generation == 0 || serial == 0) return false;
  const auto tag = scheduled_tag_.load(std::memory_order_seq_cst);
  if ((tag >> 4U) != serial) return false;
  const auto phase = schedule_phase(tag);
  if (!scheduled_start_acknowledged_ && epoch == scheduled_request_->epoch &&
      (phase == ScheduledPatternPhase::applied || phase == ScheduledPatternPhase::cancelled ||
       phase == ScheduledPatternPhase::refused)) {
    scheduled_start_acknowledged_ = true;
    control_pattern_playing_ = phase == ScheduledPatternPhase::applied;
    acknowledged_pattern_generation_ = scheduled_request_->expected_pattern_generation;
    if (phase == ScheduledPatternPhase::applied)
      acknowledged_record_authority_ = {serial, epoch, true};
  } else if (scheduled_start_acknowledged_ && scheduled_cancel_ &&
      !scheduled_cancel_acknowledged_ && epoch == scheduled_cancel_->epoch) {
    if (scheduled_cancel_won_) {
      if (phase != ScheduledPatternPhase::cancelled) return false;
      control_pattern_playing_ = false;
    } else if (scheduled_cancel_invalidated_) {
      control_pattern_playing_ = false;
    } else {
      // No DTO construction/allocation on this noexcept acknowledgment path.
      // The ordinary consumer may already have copied and acknowledged e2.
      if (!scheduled_cutoff_receipt_) {
        if (!retained_transport_receipt_) {
          PatternTransportReceiptCell cell;
          if (!pattern_transport_receipts_.try_pop(cell)) return false;
          retained_transport_receipt_ = cell;
        }
        const auto& cell = *retained_transport_receipt_;
        if (cell.generation != generation || cell.epoch != epoch) return false;
        scheduled_cutoff_receipt_ = cell;
      }
      if (pattern_transport_reserved_ &&
          !acknowledge_pattern_transport_receipt(generation, epoch)) return false;
      control_pattern_playing_ = scheduled_cutoff_receipt_->playing;
    }
    scheduled_cancel_acknowledged_ = true;
  } else return false;
  retire_scheduled_control_cell();
  return true;
}

void RealtimeEngine::set_count_in_metronome(bool enabled) noexcept {
  count_in_metronome_.store(enabled, std::memory_order_release);
}

bool RealtimeEngine::take_count_in_cue_batch_audio(CountInCueBatch& batch) noexcept {
  if (cue_batch_pending_.load(std::memory_order_acquire) == 0 || cue_batch_taken_)
    return false;
  batch = cue_batch_;
  cue_batch_taken_ = true;
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::scheduled_cue_consumption);
#endif
  return true;
}

bool RealtimeEngine::acknowledge_count_in_cue_batch_audio(std::uint64_t id) noexcept {
  if (id == 0 || !cue_batch_taken_ ||
      cue_batch_pending_.load(std::memory_order_acquire) != id) return false;
  cue_batch_taken_ = false;
  cue_batch_pending_.store(0, std::memory_order_release);
  return true;
}

bool RealtimeEngine::scheduled_pattern_record_quiescent() const noexcept {
  if (scheduled_request_ || pattern_transport_reserved_ ||
      pattern_transport_commands_.size_approx() != 0 ||
      cue_batch_pending_.load(std::memory_order_acquire) != 0 || active_voices_ != 0)
    return false;
  if (input_profile_) {
    const auto inputs = pattern_input_profile_status();
    if (inputs.ordinary_pending || inputs.held_release_reservations || inputs.retained_completions)
      return false;
  }
  for (const auto& slot : pattern_slots_)
    if (slot.scheduled_control_pins != 0 ||
        slot.scheduled_borrows.load(std::memory_order_acquire) != 0) return false;
  return true;
}

bool RealtimeEngine::scheduled_pattern_record_settled(
    std::uint64_t generation, std::uint64_t frame_epoch, std::uint64_t serial) const noexcept {
  if (state_.load(std::memory_order_acquire) != RealtimeState::running ||
      !scheduled_record_enabled_ ||
      generation == 0 || generation != pattern_transport_generation_ ||
      frame_epoch == 0 || frame_epoch != start_epoch_ ||
      serial == 0 || serial != last_schedule_serial_ ||
      scheduled_payload_.runtime_generation != generation ||
      scheduled_payload_.frame_epoch != frame_epoch || scheduled_payload_.serial != serial ||
      scheduled_request_ || pattern_transport_reserved_ ||
      pattern_transport_commands_.size_approx() != 0 || queue_.size_approx() != 0 ||
      cue_batch_pending_.load(std::memory_order_acquire) != 0) return false;
  if (input_profile_) {
    const auto inputs = pattern_input_profile_status();
    if (inputs.ordinary_pending || inputs.held_release_reservations || inputs.retained_completions)
      return false;
  }
  for (const auto& slot : pattern_slots_)
    if (slot.scheduled_control_pins != 0 ||
        slot.scheduled_borrows.load(std::memory_order_acquire) != 0) return false;
  // Read last: terminal input publication acquires the callback's entry
  // invalidation; a consumed Release is never mistaken for the voice tail's
  // last use. Only audio, after that last use, can publish this serial again.
  return scheduled_settled_serial_.load(std::memory_order_acquire) == serial;
}

void RealtimeEngine::release_scheduled_borrow_audio() noexcept {
  if (!scheduled_audio_.borrowed) return;
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::scheduled_before_last_use);
#endif
  const auto slot = scheduled_audio_.scalars.pattern_slot;
  scheduled_audio_.pattern = nullptr;
  scheduled_audio_.borrowed = false;
  pattern_slots_[slot].scheduled_borrows.fetch_sub(1, std::memory_order_release);
}

void RealtimeEngine::prepare_scheduled_record_audio() noexcept {
  const auto tag = scheduled_tag_.load(std::memory_order_seq_cst);
  if (scheduled_audio_.borrowed) {
    if ((tag >> 4U) == scheduled_audio_.scalars.serial &&
        (schedule_phase(tag) == ScheduledPatternPhase::armed ||
         schedule_phase(tag) == ScheduledPatternPhase::preparing ||
         ((schedule_phase(tag) == ScheduledPatternPhase::applied ||
           schedule_phase(tag) == ScheduledPatternPhase::empty) && scheduled_audio_.started &&
          scheduled_cutoff_serial_.load(std::memory_order_seq_cst) != (tag >> 4U)))) return;
    release_scheduled_borrow_audio();
  }
  if (schedule_phase(tag) != ScheduledPatternPhase::submitted) return;
  auto expected = tag;
  if (!scheduled_tag_.compare_exchange_strong(expected,
          schedule_tag(tag >> 4U, ScheduledPatternPhase::preparing),
          std::memory_order_seq_cst, std::memory_order_seq_cst)) return;
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::scheduled_preparing);
#endif
  // The cell cannot be acknowledged in Preparing/CancelPreparing. All bounded
  // data and the immutable material owner are acquired BEFORE publishing Armed.
  scheduled_audio_ = {};
  scheduled_audio_.scalars = scheduled_payload_;
  const auto slot = scheduled_audio_.scalars.pattern_slot;
  pattern_slots_[slot].scheduled_borrows.fetch_add(1, std::memory_order_acq_rel);
  scheduled_audio_.borrowed = true;
  scheduled_audio_.pattern = &*pattern_slots_[slot].pattern;
}

bool RealtimeEngine::commit_count_in_span(
    CountInCueSpan span, ScheduledPatternPhase phase) noexcept {
  // Complete pointer-free descriptor exists before the RMW. After it wins we
  // read only the private copy; the control payload can be recycled immediately.
  if (cue_batch_blocked_ || cue_batch_.span_count == cue_batch_.spans.size()) return false;
  const auto tag = schedule_tag(scheduled_audio_.scalars.serial, phase);
  auto expected = tag;
  if (!scheduled_tag_.compare_exchange_strong(expected, tag,
          std::memory_order_seq_cst, std::memory_order_seq_cst)) return false;
  cue_batch_.spans[cue_batch_.span_count++] = span;
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::scheduled_cue_committed);
#endif
  return true;
}

void RealtimeEngine::advance_scheduled_record_audio(
    std::uint64_t frame, std::uint64_t end) noexcept {
  if (!scheduled_audio_.borrowed) return;
  auto& local = scheduled_audio_;
  auto& s = local.scalars;
  auto tag = scheduled_tag_.load(std::memory_order_seq_cst);
  if ((tag >> 4U) != s.serial) {
    if (!cue_batch_blocked_ && !cue_batch_.cancellation_frame)
      cue_batch_.cancellation_frame = frame;
    return;
  }
  auto phase = schedule_phase(tag);
  if ((cue_batch_blocked_ || end < frame) && phase == ScheduledPatternPhase::armed) {
    auto expected = tag;
    if (scheduled_tag_.compare_exchange_strong(expected,
        schedule_tag(s.serial, ScheduledPatternPhase::failing),
        std::memory_order_seq_cst, std::memory_order_seq_cst))
      scheduled_tag_.store(schedule_tag(s.serial, ScheduledPatternPhase::refused),
          std::memory_order_seq_cst);
    return;
  }
  if (phase == ScheduledPatternPhase::cancel_preparing) {
    auto expected = tag;
    scheduled_tag_.compare_exchange_strong(expected,
        schedule_tag(s.serial, ScheduledPatternPhase::cancelled),
        std::memory_order_seq_cst, std::memory_order_seq_cst);
    return;
  }
  if (phase == ScheduledPatternPhase::cancelled ||
      (phase == ScheduledPatternPhase::empty && !local.started)) {
    // Fast control ACK may already have retired the cancelled cell. The
    // independently copied committed prefix still carries its first cutoff.
    if (!cue_batch_blocked_ && !cue_batch_.cancellation_frame)
      cue_batch_.cancellation_frame = frame;
    return;
  }
  if (phase == ScheduledPatternPhase::preparing) {
    // Only an old Pattern tail delays C; live Pad and replay voices stay live.
    for (const auto& voice : voices_)
      if (voice.active && voice.pattern_voice) return;
    constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
    if (cue_batch_blocked_ || end < frame ||
        frame == maximum || s.bar_frames > (maximum - frame - 1) / s.bars) {
      auto expected = tag;
      if (scheduled_tag_.compare_exchange_strong(expected,
              schedule_tag(s.serial, ScheduledPatternPhase::failing),
              std::memory_order_seq_cst, std::memory_order_seq_cst))
        scheduled_tag_.store(schedule_tag(s.serial, ScheduledPatternPhase::refused),
            std::memory_order_seq_cst);
      return;
    }
    s.count_in_frame = frame;
    s.start_frame = frame + s.bars * s.bar_frames;
    s.timed = true;
    for (std::size_t i = 0; i < static_cast<std::size_t>(s.bars) * 4; ++i)
      local.markers[i] = frame + (i / 4) * s.bar_frames +
          ((i % 4) * s.bar_frames + 2) / 4;
    scheduled_timing_.publish(s);
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
    testing::invoke_realtime_hook(testing::RealtimeHookPoint::scheduled_before_arm);
#endif
    auto expected = tag;
    if (!scheduled_tag_.compare_exchange_strong(expected,
            schedule_tag(s.serial, ScheduledPatternPhase::armed),
            std::memory_order_seq_cst, std::memory_order_seq_cst)) return;
    local.armed = true;
    phase = ScheduledPatternPhase::armed;
  }
  if (scheduled_cutoff_serial_.load(std::memory_order_seq_cst) == s.serial) return;
  if (phase != ScheduledPatternPhase::armed && phase != ScheduledPatternPhase::applied &&
      !(phase == ScheduledPatternPhase::empty && local.started)) return;
  const auto envelope_end = [](std::uint64_t marker) noexcept {
    constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
    return marker > maximum - kCountInCueEnvelopeFrames
        ? maximum : marker + kCountInCueEnvelopeFrames;
  };
  if (local.carried_cue && frame == cue_batch_.begin_frame &&
      frame < envelope_end(local.carried_cue->marker_frame)) {
    auto span = *local.carried_cue;
    span.begin_frame = frame;
    span.end_frame = std::min(end, envelope_end(span.marker_frame));
    span.marker = false;
    static_cast<void>(commit_count_in_span(span, phase));
  }
  if (phase == ScheduledPatternPhase::armed &&
      local.next_marker < static_cast<std::size_t>(s.bars) * 4 &&
      frame == local.markers[local.next_marker]) {
    const CountInCueSpan span{frame, frame, std::min(end, envelope_end(frame)),
        local.next_marker % 4 == 0, true, true};
    if (commit_count_in_span(span, ScheduledPatternPhase::armed)) {
      local.carried_cue = span;
      ++local.next_marker;
    }
  }
  if (phase != ScheduledPatternPhase::armed || frame != s.start_frame) return;
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::scheduled_before_start);
#endif
  auto expected = schedule_tag(s.serial, ScheduledPatternPhase::armed);
  if (!scheduled_tag_.compare_exchange_strong(expected,
          schedule_tag(s.serial, ScheduledPatternPhase::starting),
          std::memory_order_seq_cst, std::memory_order_seq_cst)) return;
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::scheduled_start_committed);
#endif
  // The actual CAS, not the already-published callback frontier, admits input.
  pattern_playing_ = true;
  pattern_origin_frame_ = s.start_frame;
  pattern_event_index_ = 0;
  // Scheduled S is the same tick-zero restart as an ordinary Start. A prior
  // tempo transition/Stop must not carry its continuous clock into this run.
  pattern_event_loop_ = 0;
  pattern_tempo_anchor_ = {s.start_frame, 0, s.bpm};
  pattern_position_available_ = true;
  pattern_tempo_applied_frame_ = s.start_frame;
  pattern_continuous_timing_ = false;
  local.started = true;
  publish_transport_decision();
  scheduled_tag_.store(schedule_tag(s.serial, ScheduledPatternPhase::applied),
      std::memory_order_seq_cst);
  if (count_in_metronome_.load(std::memory_order_acquire)) {
    const CountInCueSpan downbeat{frame, frame,
        std::min(end, envelope_end(frame)), true, false, true};
    if (commit_count_in_span(downbeat, ScheduledPatternPhase::applied))
      local.carried_cue = downbeat;
  }
}

void RealtimeEngine::finish_scheduled_record_audio() noexcept {
  if (!cue_batch_blocked_ && cue_batch_.span_count != 0) {
    cue_batch_.batch_id = next_cue_batch_id_.fetch_add(1, std::memory_order_acq_rel);
    cue_batch_.runtime_generation = scheduled_audio_.scalars.runtime_generation;
    cue_batch_.frame_epoch = scheduled_audio_.scalars.frame_epoch;
    cue_batch_.serial = scheduled_audio_.scalars.serial;
    cue_batch_pending_.store(cue_batch_.batch_id, std::memory_order_release);
  }
  if (!scheduled_audio_.borrowed) return;
  const auto tag = scheduled_tag_.load(std::memory_order_seq_cst);
  auto phase = schedule_phase(tag);
  if (phase == ScheduledPatternPhase::cancel_preparing) {
    auto expected = tag;
    if (scheduled_tag_.compare_exchange_strong(expected,
        schedule_tag(tag >> 4U, ScheduledPatternPhase::cancelled),
        std::memory_order_seq_cst, std::memory_order_seq_cst))
      phase = ScheduledPatternPhase::cancelled;
  }
  const auto marker = scheduled_audio_.carried_cue
      ? scheduled_audio_.carried_cue->marker_frame : 0;
  const auto exhausted_envelope = !scheduled_audio_.carried_cue ||
      (cue_batch_.end_frame >= marker && cue_batch_.end_frame - marker >= kCountInCueEnvelopeFrames);
  if ((tag >> 4U) != scheduled_audio_.scalars.serial ||
      phase == ScheduledPatternPhase::cancelled || phase == ScheduledPatternPhase::refused ||
      (phase == ScheduledPatternPhase::empty && !scheduled_audio_.started) ||
      scheduled_cutoff_serial_.load(std::memory_order_seq_cst) == scheduled_audio_.scalars.serial ||
      ((phase == ScheduledPatternPhase::applied || phase == ScheduledPatternPhase::empty) &&
       exhausted_envelope))
    release_scheduled_borrow_audio();
}

PatternPublication RealtimeEngine::publish_pattern_view(
    PreparedPatternView&& pattern,
    std::optional<std::uint64_t> requested_activation_frame,
    std::optional<PatternReplacementAuthority> replacement_authority) noexcept {
  return publish_pattern_view_impl(
      std::move(pattern), requested_activation_frame,
      std::move(replacement_authority), PatternPublicationTiming::scheduled);
}

PatternPublication RealtimeEngine::publish_pattern_switch_view(
    PreparedPatternView&& pattern,
    std::optional<PatternReplacementAuthority> replacement_authority) noexcept {
  return publish_pattern_switch_view(std::move(pattern), PatternSwitchSnap::bar,
      std::move(replacement_authority));
}

PatternPublication RealtimeEngine::publish_pattern_switch_view(
    PreparedPatternView&& pattern, PatternSwitchSnap snap,
    std::optional<PatternReplacementAuthority> replacement_authority) noexcept {
  return publish_pattern_view_impl(std::move(pattern), std::nullopt,
      std::move(replacement_authority), PatternPublicationTiming::switch_bar, 0, snap);
}

RetainedPatternPublication RealtimeEngine::publish_retained_pattern_switch_view(
    PreparedPatternView&& pattern, PatternSwitchSnap snap,
    std::optional<PatternReplacementAuthority> replacement_authority) noexcept {
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    ++pattern_publication_rejections_;
    publish_control_observation();
    return {{PatternPublishResult::phase_mismatch, 0, 0}, {}};
  }
  PatternPublicationLease lease;
  const auto publication = publish_pattern_view_impl(std::move(pattern),
      std::nullopt, std::move(replacement_authority),
      PatternPublicationTiming::switch_bar, 0, snap, &lease);
  return {publication, std::move(lease)};
}

std::optional<PatternPublicationObservation>
RealtimeEngine::observe_pattern_publication(
    const PatternPublicationLease& lease) const {
  if (lease.engine_ != this || lease.slot_ >= pattern_slots_.size())
    return std::nullopt;
  const auto& slot = pattern_slots_[lease.slot_];
  const auto state = slot.state.load(std::memory_order_acquire);
  if (state == PatternState::empty || !slot.pattern ||
      slot.generation != lease.generation_ || slot.scheduled_control_pins == 0)
    return std::nullopt;
  PatternPublicationObservation result{
      {slot.generation, slot.pattern->pattern_id(), slot.activation_frame},
      PatternPublicationDisposition::pending, std::nullopt};
  // While pending, audio may still write apply metadata. Its acquire-published
  // current/retired state makes that generation's write stable under this pin.
  if (state == PatternState::pending) return result;
  if (pattern_applied_generations_[lease.slot_] == lease.generation_) {
    result.disposition = PatternPublicationDisposition::applied;
    result.applied_frame = pattern_applied_frames_[lease.slot_];
  } else if (state == PatternState::reclaimable) {
    result.disposition = PatternPublicationDisposition::cancelled;
  }
  return result;
}

std::optional<PatternPublicationClockObservation>
RealtimeEngine::observe_pattern_publication_clock(
    const PatternPublicationLease& lease) const {
  auto publication = observe_pattern_publication(lease);
  if (!publication) return std::nullopt;
  const auto& view = *pattern_slots_[lease.slot_].pattern;
  PatternPublicationClockObservation result{
      std::move(*publication), std::nullopt, view.ppq(), view.loop_length_ticks()};
  // Pending can still be written by audio. Only applied disposition acquired
  // the slot state publishing its metadata; the lease prevents later reuse.
  if (result.publication.disposition == PatternPublicationDisposition::applied &&
      pattern_applied_positions_[lease.slot_]) {
    result.applied_anchor = TransportAnchor{
        *result.publication.applied_frame, *pattern_applied_positions_[lease.slot_],
        view.bpm()};
  }
  return result;
}

void RealtimeEngine::release_pattern_publication_lease(
    std::uint8_t slot, std::uint64_t generation) noexcept {
  if (slot < pattern_slots_.size() && pattern_slots_[slot].generation == generation &&
      pattern_slots_[slot].scheduled_control_pins != 0)
    --pattern_slots_[slot].scheduled_control_pins;
}

PatternPublication RealtimeEngine::publish_pattern_view_immediate(
    PreparedPatternView&& pattern) noexcept {
  return publish_pattern_view_impl(
      std::move(pattern), std::nullopt, std::nullopt,
      PatternPublicationTiming::immediate);
}

PatternPublication RealtimeEngine::publish_pattern_view_preserving_phase(
    PreparedPatternView&& pattern, std::uint64_t expected_generation) noexcept {
  return publish_pattern_view_impl(std::move(pattern), std::nullopt, std::nullopt,
      PatternPublicationTiming::preserve_phase, expected_generation);
}

RetainedPatternPublication RealtimeEngine::publish_retained_pattern_view_preserving_phase(
    PreparedPatternView&& pattern, std::uint64_t expected_generation) noexcept {
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    ++pattern_publication_rejections_;
    publish_control_observation();
    return {{PatternPublishResult::phase_mismatch, 0, 0}, {}};
  }
  PatternPublicationLease lease;
  const auto publication = publish_pattern_view_impl(std::move(pattern),
      std::nullopt, std::nullopt, PatternPublicationTiming::preserve_phase,
      expected_generation, PatternSwitchSnap::bar, &lease);
  return {publication, std::move(lease)};
}

PatternPublication RealtimeEngine::publish_pattern_tempo_transition(
    PreparedPatternView&& pattern, std::uint64_t expected_generation) noexcept {
  return publish_pattern_view_impl(std::move(pattern), std::nullopt, std::nullopt,
      PatternPublicationTiming::tempo_transition, expected_generation);
}

PatternPublication RealtimeEngine::publish_pattern_view_impl(
    PreparedPatternView&& pattern,
    std::optional<std::uint64_t> requested_activation_frame,
    std::optional<PatternReplacementAuthority> replacement_authority,
    PatternPublicationTiming timing, std::uint64_t expected_generation,
    PatternSwitchSnap snap, PatternPublicationLease* retained) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  const bool tempo_transition = timing == PatternPublicationTiming::tempo_transition;
  const bool preserves_position = tempo_transition ||
      timing == PatternPublicationTiming::preserve_phase;
  // Once S has applied, overlay publication no longer competes with the
  // scheduled start. Its original material stays independently pinned until
  // the recording owner consumes e1/e2 and every audio borrow has ended.
  if (pattern_transport_reserved_ || (scheduled_request_ &&
      schedule_phase(scheduled_tag_.load(std::memory_order_seq_cst)) != ScheduledPatternPhase::applied)) {
    ++pattern_publication_rejections_;
    return {PatternPublishResult::publication_pending, 0, 0};
  }
  for (;;) {
    // Only non-realtime control retries. Audio closes admission without
    // waiting: at most one previously admitted control CAS remains in flight.
    if (pattern_claim_closed_.load(std::memory_order_seq_cst) != 0) {
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
      testing::invoke_realtime_hook(
          testing::RealtimeHookPoint::control_pattern_admission_retry);
#endif
      continue;
    }
    auto observed_mailbox =
        queued_pattern_generation_.load(std::memory_order_acquire);
    if ((observed_mailbox & kPatternTokenClaimedMask) != 0) {
      continue;  // Audio claimed an empty Q and will clear it without waiting.
    }
    // Couple every timing read to this exact admission, not just a slot token
    // that returns to zero after audio consumes an empty Q. No finite epoch or
    // elapsed-time assumption can make a paused control publisher valid again.
    const auto admitted_mailbox =
        (observed_mailbox & ~kPatternAdmissionInvalidatedMask) |
        kPatternControlReservedMask;
    if (!queued_pattern_generation_.compare_exchange_strong(
            observed_mailbox, admitted_mailbox,
            std::memory_order_seq_cst, std::memory_order_seq_cst))
      continue;
    PatternPublicationAdmission admission{queued_pattern_generation_};
    const auto observed_queued_token = pattern_slot_token(observed_mailbox);
    const auto observed_queued_generation =
        pattern_token_generation(observed_queued_token);
    const auto observed_audio_mailbox =
        audio_pending_pattern_generation_.load(std::memory_order_acquire);
    const auto observed_audio_generation =
        pattern_token_generation(observed_audio_mailbox);
    const auto observed_pending_generation = observed_queued_token != 0
        ? observed_queued_generation
        : observed_audio_generation;
    if (preserves_position && observed_pending_generation != 0) {
      ++pattern_publication_rejections_;
      return {PatternPublishResult::publication_pending, 0, 0};
    }
    if (timing == PatternPublicationTiming::switch_bar && observed_audio_generation != 0) {
      const auto& predecessor =
          pattern_slots_[pattern_slot_token(observed_audio_mailbox) - 1];
      const auto decision = transport_decision_.read();
      if (predecessor.tempo_transition &&
          (decision.current_pattern_generation != observed_audio_generation ||
           !decision.tempo_available)) {
        // A claim (including render(0)) is not an applied tempo anchor. Keep
        // every accepted owner untouched; the caller can retry after apply.
        ++pattern_publication_rejections_;
        return {PatternPublishResult::publication_pending, 0, 0};
      }
    }
    std::optional<std::uint64_t> observed_pending_activation;
    std::optional<std::uint64_t> claimed_next_activation;
    bool authorized_replacement = false;
    if (observed_pending_generation != 0) {
      const auto pending = std::find_if(
          pattern_slots_.begin(),
          pattern_slots_.end(),
          [observed_pending_generation](const PatternSlot& candidate) {
            return candidate.state.load(std::memory_order_acquire) ==
                       PatternState::pending &&
                   candidate.generation == observed_pending_generation;
          });
      if (pending == pattern_slots_.end()) {
        if (queued_pattern_generation_.load(std::memory_order_acquire) !=
                admitted_mailbox ||
            audio_pending_pattern_generation_.load(
                std::memory_order_acquire) != observed_audio_mailbox) {
          continue;
        }
        pattern_publication_rejections_ += 1;
        return PatternPublication{
            PatternPublishResult::publication_pending, 0, 0};
      }
      authorized_replacement = replacement_authority.has_value() &&
          replacement_authority->generation == observed_pending_generation &&
          replacement_authority->pattern_id == pending->pattern->pattern_id() &&
          replacement_authority->activation_frame == pending->activation_frame;
      const auto observed_frame =
          transport_decision_.read().rendered_frames;
      const bool claimed_switch = timing == PatternPublicationTiming::switch_bar &&
          observed_queued_token == 0 && observed_audio_generation != 0;
      if (pending->activation_frame >= observed_frame && !claimed_switch) {
        observed_pending_activation = pending->activation_frame;
      } else if (timing != PatternPublicationTiming::switch_bar &&
                 observed_queued_token == 0 && observed_audio_generation != 0) {
        const auto bar_frames = pending->pattern->bar_frames();
        const auto elapsed = std::max(observed_frame, pending->activation_frame) -
            pending->activation_frame;
        const auto bars = elapsed / bar_frames;
        if (bars != std::numeric_limits<std::uint64_t>::max() &&
            (bars + 1) <=
                (std::numeric_limits<std::uint64_t>::max() -
                 pending->activation_frame) /
                    bar_frames) {
          claimed_next_activation =
              pending->activation_frame + (bars + 1) * bar_frames;
        }
      }
      if (pending->pattern->project_id() != pattern.project_id() ||
          (!authorized_replacement &&
           (pending->pattern->pattern_id() != pattern.pattern_id() ||
            (requested_activation_frame.has_value() &&
             observed_pending_activation.has_value() &&
             *requested_activation_frame != *observed_pending_activation)))) {
        pattern_publication_rejections_ += 1;
        return PatternPublication{
            PatternPublishResult::publication_pending, 0, 0};
      }
    }

#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
    testing::invoke_realtime_hook(
        testing::RealtimeHookPoint::control_pattern_timing_captured);
#endif
    const auto current =
        current_pattern_slot_.load(std::memory_order_acquire);
    const auto decision = transport_decision_.read();
    if (current != kNoPatternSlot &&
        decision.current_pattern_generation != pattern_slots_[current].generation)
      continue; // Audio is publishing the coherent current/anchor pair.
    if (preserves_position) {
      if (current == kNoPatternSlot || expected_generation == 0 ||
          pattern_slots_[current].generation != expected_generation) {
        ++pattern_publication_rejections_;
        return {PatternPublishResult::phase_mismatch, 0, 0};
      }
      const auto& previous = *pattern_slots_[current].pattern;
      if (previous.project_id() != pattern.project_id() ||
          previous.pattern_id() != pattern.pattern_id() ||
          (!tempo_transition && previous.bpm() != pattern.bpm()) ||
          previous.ppq() != pattern.ppq() ||
          previous.loop_length_ticks() != pattern.loop_length_ticks() ||
          (tempo_transition && (previous.project_revision() != pattern.project_revision() ||
              previous.has_overlay() != pattern.has_overlay() ||
              previous.events().size() != pattern.events().size() ||
              !std::equal(previous.events().begin(), previous.events().end(), pattern.events().begin(),
                  [](PreparedPatternEvent source, const PreparedPatternEvent& target) {
                    source.start_frame = target.start_frame;
                    source.release_frame = target.release_frame;
                    return source == target;
                  })))) {
        ++pattern_publication_rejections_;
        return {PatternPublishResult::phase_mismatch, 0, 0};
      }
    }
    if (current != kNoPatternSlot &&
        pattern_slots_[current].pattern->project_id() != pattern.project_id()) {
      pattern_publication_rejections_ += 1;
      return PatternPublication{PatternPublishResult::project_mismatch, 0, 0};
    }

    auto slot = std::find_if(
        pattern_slots_.begin(),
        pattern_slots_.end(),
        [](const PatternSlot& candidate) {
          return candidate.state.load(std::memory_order_acquire) ==
                 PatternState::empty;
        });
    if (slot == pattern_slots_.end()) {
      pattern_publication_rejections_ += 1;
      return PatternPublication{PatternPublishResult::pattern_slots_full, 0, 0};
    }

    const auto slot_index = static_cast<std::uint8_t>(
        std::distance(pattern_slots_.begin(), slot));
    const auto generation =
        detail::take_pattern_generation(next_pattern_generation_);
    if (!generation.has_value()) {
      pattern_publication_rejections_ += 1;
      return PatternPublication{
          PatternPublishResult::generation_exhausted, 0, 0};
    }
    slot->pattern.emplace(std::move(pattern));
    slot->active_voices = 0;
    slot->generation = *generation;
    slot->preserve_phase = preserves_position;
    slot->tempo_transition = tempo_transition;
    slot->switch_bar = timing == PatternPublicationTiming::switch_bar;

    const auto running =
        state_.load(std::memory_order_acquire) == RealtimeState::running;
    std::uint64_t activation_frame = 0;
    if (running) {
      const auto observed_frame = decision.rendered_frames;
      activation_frame = observed_frame;
      if (timing == PatternPublicationTiming::switch_bar && current != kNoPatternSlot) {
        const auto* geometry = &*pattern_slots_[current].pattern;
        auto origin = decision.pattern_origin_frame;
        const bool claimed_predecessor = observed_audio_generation != 0 &&
            observed_audio_generation != decision.current_pattern_generation;
        bool use_continuous_clock = !claimed_predecessor && decision.continuous_timing;
        if (claimed_predecessor) {
          // Includes replacing unclaimed C while B already belongs to audio:
          // C still follows B's geometry, never the old current A's clock.
          const auto& predecessor = pattern_slots_[pattern_slot_token(observed_audio_mailbox) - 1];
          const auto& before = *geometry;
          const auto& after = *predecessor.pattern;
          // A same-BPM edit keeps the actually retained clock. Prove its
          // geometry equivalent before using the current owner's anchor;
          // an ordinary claimed Pattern still starts at its own tick zero.
          use_continuous_clock = decision.continuous_timing &&
              predecessor.preserve_phase && !predecessor.tempo_transition &&
              before.project_id() == after.project_id() &&
              before.pattern_id() == after.pattern_id() &&
              before.bpm() == after.bpm() && before.ppq() == after.ppq() &&
              before.loop_length_ticks() == after.loop_length_ticks();
          geometry = &after;
          origin = predecessor.activation_frame;
        }
        const auto selected = use_continuous_clock
            ? (decision.tempo_available
                ? next_continuous_pattern_switch_frame(
                    *geometry, decision.tempo.anchor, observed_frame, snap) : std::nullopt)
            : next_pattern_switch_frame(*geometry, origin, observed_frame, snap);
        if (!selected) {
          slot->pattern.reset();
          slot->generation = 0;
          ++pattern_publication_rejections_;
          return {PatternPublishResult::publish_queue_full, 0, 0};
        }
        activation_frame = *selected;
      } else if (timing == PatternPublicationTiming::immediate || preserves_position) {
        activation_frame = observed_frame;
      } else if (authorized_replacement &&
                 requested_activation_frame.has_value()) {
        if (*requested_activation_frame < observed_frame) {
          slot->pattern.reset();
          slot->generation = 0;
          pattern_publication_rejections_ += 1;
          return PatternPublication{
              PatternPublishResult::publish_queue_full, 0, 0};
        }
        activation_frame = *requested_activation_frame;
      } else if (observed_pending_activation.has_value()) {
        activation_frame = *observed_pending_activation;
      } else if (claimed_next_activation.has_value()) {
        activation_frame = *claimed_next_activation;
      } else if (requested_activation_frame.has_value()) {
        if (*requested_activation_frame < observed_frame) {
          slot->pattern.reset();
          slot->generation = 0;
          pattern_publication_rejections_ += 1;
          return PatternPublication{
              PatternPublishResult::publish_queue_full, 0, 0};
        }
        activation_frame = *requested_activation_frame;
      } else if (current != kNoPatternSlot) {
        const auto origin = decision.pattern_origin_frame;
        const auto bar_frames =
            pattern_slots_[current].pattern->bar_frames();
        if (decision.continuous_timing) {
          const auto boundary = decision.tempo_available
              ? next_continuous_pattern_switch_frame(*pattern_slots_[current].pattern,
                  decision.tempo.anchor, observed_frame, PatternSwitchSnap::bar)
              : std::nullopt;
          if (!boundary) {
            slot->pattern.reset();
            slot->generation = 0;
            ++pattern_publication_rejections_;
            return {PatternPublishResult::publish_queue_full, 0, 0};
          }
          activation_frame = *boundary;
        } else if (observed_frame >= origin) {
          const auto elapsed = observed_frame - origin;
          const auto bars = elapsed / bar_frames;
          if (bars == std::numeric_limits<std::uint64_t>::max() ||
              (bars + 1) >
                  (std::numeric_limits<std::uint64_t>::max() - origin) /
                      bar_frames) {
            slot->pattern.reset();
            slot->generation = 0;
            pattern_publication_rejections_ += 1;
            return PatternPublication{
                PatternPublishResult::publish_queue_full, 0, 0};
          }
          activation_frame = origin + (bars + 1) * bar_frames;
        }
      }
    }

    const PatternPublishEntry publication{
        slot_index, slot->generation, activation_frame};
    slot->activation_frame = activation_frame;
    // Only this serialized control producer can reclaim/reuse slots. Pin before
    // the release mailbox CAS can expose this immutable generation to audio.
    if (retained != nullptr) ++slot->scheduled_control_pins;
    slot->state.store(PatternState::pending, std::memory_order_release);
    if (!running) {
      apply_published_pattern(publication, 0);
    } else {
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
      testing::invoke_realtime_hook(
          testing::RealtimeHookPoint::control_pattern_before_publication);
#endif
      auto expected_generation = admitted_mailbox;
      if (!queued_pattern_generation_.compare_exchange_strong(
              expected_generation,
              static_cast<std::uint32_t>(publication.slot) + 1,
              std::memory_order_seq_cst,
              std::memory_order_seq_cst)) {
        if (retained != nullptr) --slot->scheduled_control_pins;
        pattern = std::move(*slot->pattern);
        slot->pattern.reset();
        slot->generation = 0;
        slot->activation_frame = 0;
        slot->state.store(PatternState::empty, std::memory_order_release);
        continue;
      }
      admission.committed();
      observed_last_queued_ = {publication.generation, activation_frame};
      if (observed_queued_generation != 0) {
        const auto superseded = std::find_if(
            pattern_slots_.begin(),
            pattern_slots_.end(),
            [observed_queued_generation](const PatternSlot& candidate) {
              return candidate.state.load(std::memory_order_acquire) ==
                         PatternState::pending &&
                     candidate.generation == observed_queued_generation;
            });
        if (superseded != pattern_slots_.end()) {
          superseded->state.store(
              PatternState::reclaimable, std::memory_order_release);
          superseded_pattern_publications_ += 1;
        }
      }
    }
    accepted_pattern_publications_ += 1;
    if (retained != nullptr)
      *retained = PatternPublicationLease{*this, slot_index, publication.generation};
    return PatternPublication{
        PatternPublishResult::accepted,
        publication.generation,
        activation_frame,
    };
  }
}

bool RealtimeEngine::cancel_pattern_publication(
    const PatternReplacementAuthority& authority) noexcept {
  if (pattern_transport_reserved_ || (scheduled_request_ &&
      schedule_phase(scheduled_tag_.load(std::memory_order_seq_cst)) != ScheduledPatternPhase::applied)) return false;
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  if (cancel_unclaimed_pattern_publication(authority)) {
    return true;
  }
  const auto pending = std::find_if(
      pattern_slots_.begin(),
      pattern_slots_.end(),
      [&authority](const PatternSlot& candidate) {
        return candidate.state.load(std::memory_order_acquire) ==
                   PatternState::pending &&
               candidate.generation == authority.generation &&
               candidate.activation_frame == authority.activation_frame &&
               candidate.pattern->pattern_id() == authority.pattern_id;
      });
  if (pending == pattern_slots_.end()) {
    return false;
  }

  auto expected = static_cast<std::uint32_t>(
      std::distance(pattern_slots_.begin(), pending)) + 1;
  if (audio_pending_pattern_generation_.compare_exchange_strong(
          expected,
          0,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    canceled_pattern_publications_ += 1;
    observed_last_audio_cancel_ = authority.generation;
    return true;
  }
  return false;
}

bool RealtimeEngine::cancel_unclaimed_pattern_publication(
    const PatternReplacementAuthority& authority) noexcept {
  if (pattern_transport_reserved_ || (scheduled_request_ &&
      schedule_phase(scheduled_tag_.load(std::memory_order_seq_cst)) != ScheduledPatternPhase::applied)) return false;
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  while (pattern_claim_closed_.load(std::memory_order_seq_cst) != 0) {
    // Control only; do not issue another Q modification during audio claim.
  }
  const auto pending = std::find_if(
      pattern_slots_.begin(),
      pattern_slots_.end(),
      [&authority](const PatternSlot& candidate) {
        return candidate.state.load(std::memory_order_acquire) ==
                   PatternState::pending &&
               candidate.generation == authority.generation &&
               candidate.activation_frame == authority.activation_frame &&
               candidate.pattern->pattern_id() == authority.pattern_id;
      });
  if (pending == pattern_slots_.end()) {
    return false;
  }

  const auto expected_slot = static_cast<std::uint32_t>(
      std::distance(pattern_slots_.begin(), pending)) + 1;
  auto expected = queued_pattern_generation_.load(std::memory_order_acquire);
  if (pattern_slot_token(expected) != expected_slot ||
      (expected & kPatternTokenClaimedMask) != 0)
    return false;
  if (!queued_pattern_generation_.compare_exchange_strong(
          expected,
          expected & kPatternAdmissionMask,
          std::memory_order_seq_cst,
          std::memory_order_seq_cst)) {
    return false;
  }
  pending->state.store(PatternState::reclaimable, std::memory_order_release);
  observed_last_queued_ = {};
  canceled_pattern_publications_ += 1;
  return true;
}

foundation::Result<void> RealtimeEngine::clear_pattern_view() noexcept {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped) {
    return invalid_argument(
        "realtime Pattern may only be cleared while stopped");
  }
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_audio_observation};
  if (pattern_slot_token(queued_pattern_generation_.load(
          std::memory_order_acquire)) != 0 ||
      pattern_slot_token(audio_pending_pattern_generation_.load(
          std::memory_order_acquire)) != 0) {
    return invalid_argument("realtime Pattern publication is pending");
  }
  const auto current =
      current_pattern_slot_.exchange(kNoPatternSlot, std::memory_order_acq_rel);
  if (current != kNoPatternSlot) {
    auto& slot = pattern_slots_[current];
    slot.state.store(
        PatternState::retiring, std::memory_order_release);
    if (slot.active_voices == 0) {
      slot.state.store(PatternState::reclaimable, std::memory_order_release);
    }
  }
  pattern_origin_frame_ = 0;
  observed_current_pattern_generation_ = 0;
  pattern_tempo_anchor_ = {};
  pattern_position_available_ = true;
  pattern_tempo_applied_frame_ = 0;
  pattern_continuous_timing_ = false;
  pattern_event_loop_ = 0;
  publish_transport_decision();
  pattern_event_index_ = 0;
  return foundation::Result<void>::success();
}

std::size_t RealtimeEngine::reclaim_retired_patterns() noexcept {
  if (pattern_transport_reserved_) return 0;
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  std::size_t reclaimed = 0;
  for (auto& slot : pattern_slots_) {
    if (slot.state.load(std::memory_order_acquire) !=
        PatternState::reclaimable) {
      continue;
    }
    if (slot.scheduled_control_pins != 0 ||
        slot.scheduled_borrows.load(std::memory_order_acquire) != 0) continue;
    slot.pattern.reset();
    slot.generation = 0;
    slot.activation_frame = 0;
    slot.active_voices = 0;
    slot.state.store(PatternState::empty, std::memory_order_release);
    ++reclaimed;
  }
  reclaimed_patterns_ += reclaimed;
  return reclaimed;
}

std::optional<foundation::PatternId>
RealtimeEngine::current_pattern_id() const {
  const auto slot = current_pattern_slot_.load(std::memory_order_acquire);
  if (slot == kNoPatternSlot) {
    return std::nullopt;
  }
  return pattern_slots_[slot].pattern->pattern_id();
}

std::optional<PatternTransportObservation>
RealtimeEngine::pattern_transport_observation() const {
  for (unsigned attempt = 0; attempt != 8; ++attempt) {
    while (pattern_claim_closed_.load(std::memory_order_seq_cst) != 0) {
      // Control only, like publication: audio closes admission without
      // waiting, so the window always reopens. A preempted callback can hold
      // it for milliseconds; spending the bounded attempts inside it reports
      // a stable owner as unavailable.
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
      testing::invoke_realtime_hook(
          testing::RealtimeHookPoint::control_pattern_admission_retry);
#endif
    }
    const auto queued = queued_pattern_generation_.load(std::memory_order_acquire);
    const auto pending = audio_pending_pattern_generation_.load(std::memory_order_acquire);
    const auto current = current_pattern_slot_.load(std::memory_order_acquire);
    const auto decision = transport_decision_.read();
    PatternTransportObservation observation{};
    if (current != kNoPatternSlot) {
      if (pattern_slots_[current].state.load(std::memory_order_acquire) !=
          PatternState::current) continue;
      observation.current_generation = pattern_slots_[current].generation;
      observation.current_pattern = pattern_slots_[current].pattern->pattern_id();
      observation.current_origin_frame = decision.pattern_origin_frame;
      if (decision.current_pattern_generation != observation.current_generation)
        continue;
    }
    const auto authority = [&](std::uint32_t token)
        -> std::optional<PatternReplacementAuthority> {
      const auto encoded_slot = pattern_slot_token(token);
      if (encoded_slot == 0) return std::nullopt;
      const auto& slot = pattern_slots_[encoded_slot - 1];
      if (slot.generation == observation.current_generation ||
          slot.state.load(std::memory_order_acquire) != PatternState::pending)
        return std::nullopt;
      return PatternReplacementAuthority{
          slot.generation, slot.pattern->pattern_id(), slot.activation_frame};
    };
    observation.pending_switches[0] = authority(pending);
    observation.pending_switches[1] = authority(queued);
    if (observation.pending_switches[0] && observation.pending_switches[1] &&
        observation.pending_switches[0]->generation ==
            observation.pending_switches[1]->generation)
      observation.pending_switches[1].reset();
    // Control-canceled A retains its audio-local slot until audio retires it.
    // Its token is zero, but admission still requires that exact immutable
    // slot authority. Do not hide it behind the latest-only mailbox view.
    bool overflow = false;
    for (const auto& slot : pattern_slots_) {
      if (slot.state.load(std::memory_order_acquire) != PatternState::pending ||
          slot.generation == observation.current_generation) continue;
      bool named = false;
      for (const auto& item : observation.pending_switches)
        named |= item && item->generation == slot.generation;
      if (named) continue;
      if (observation.outstanding_cancellation ||
          (observation.pending_switches[0] && observation.pending_switches[1])) {
        overflow = true;
        break;
      }
      observation.outstanding_cancellation = PatternReplacementAuthority{
          slot.generation, slot.pattern->pattern_id(), slot.activation_frame};
    }
    if (overflow) continue;
    if (pattern_claim_closed_.load(std::memory_order_seq_cst) == 0 &&
        queued_pattern_generation_.load(std::memory_order_acquire) == queued &&
        audio_pending_pattern_generation_.load(std::memory_order_acquire) == pending &&
        current_pattern_slot_.load(std::memory_order_acquire) == current &&
        (current == kNoPatternSlot ||
         pattern_slots_[current].state.load(std::memory_order_acquire) ==
             PatternState::current))
      return observation;
  }
  return std::nullopt;
}

std::optional<PatternTempoObservation> RealtimeEngine::pattern_tempo_observation(
    std::uint64_t expected_generation) const noexcept {
  const auto decision = transport_decision_.read();
  if (expected_generation == 0 ||
      decision.current_pattern_generation != expected_generation ||
      !decision.tempo_available || decision.tempo.anchor.bpm == 0)
    return std::nullopt;
  return decision.tempo;
}

std::optional<foundation::PatternId>
RealtimeEngine::pending_pattern_id() const {
  const auto mailbox =
      queued_pattern_generation_.load(std::memory_order_acquire);
  const auto generation =
      pattern_slot_token(mailbox) != 0
          ? pattern_token_generation(mailbox)
          : pattern_token_generation(
                audio_pending_pattern_generation_.load(
                    std::memory_order_acquire));
  if (generation == 0) {
    return std::nullopt;
  }
  const auto slot = std::find_if(
      pattern_slots_.begin(),
      pattern_slots_.end(),
      [generation](const PatternSlot& candidate) {
        return candidate.state.load(std::memory_order_acquire) ==
                   PatternState::pending &&
               candidate.generation == generation;
      });
  return slot == pattern_slots_.end()
             ? std::nullopt
             : std::optional<foundation::PatternId>{
                   slot->pattern->pattern_id()};
}

std::optional<bool> RealtimeEngine::current_pattern_has_overlay() const
    noexcept {
  const auto slot = current_pattern_slot_.load(std::memory_order_acquire);
  if (slot == kNoPatternSlot) {
    return std::nullopt;
  }
  return pattern_slots_[slot].pattern->has_overlay();
}

std::optional<std::uint64_t>
RealtimeEngine::current_pattern_origin_frame() const noexcept {
  if (current_pattern_slot_.load(std::memory_order_acquire) == kNoPatternSlot) {
    return std::nullopt;
  }
  return transport_decision_.read().pattern_origin_frame;
}

ReclaimedBankTelemetry
RealtimeEngine::reclaim_retired_bank_telemetry() noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  ReclaimedBankTelemetry reclaimed{};
  const auto sweep = [&reclaimed](BankSlot& slot, bool project_bank) {
    if (slot.state.load(std::memory_order_acquire) !=
        BankState::reclaimable) {
      return;
    }
    if (project_bank) reclaimed.decoded_pcm_bytes += slot.bank->decoded_pcm_bytes();
    slot.bank.reset();
    slot.generation = 0;
    slot.state.store(BankState::empty, std::memory_order_release);
    ++reclaimed.count;
  };
  for (auto& slot : bank_slots_) {
    sweep(slot, true);
  }
  // Retired audition Banks are reclaimed by the same sweep; otherwise a
  // replaced audition would hold its slot forever and the second publication
  // after it would report the pool full. Their storage belongs to the reserved
  // audition pool and must not refund the Host's Project Bank PCM reservation.
  for (auto& slot : audition_slots_) {
    sweep(slot, false);
  }
  reclaimed_banks_ += reclaimed.count;
  return reclaimed;
}

std::size_t RealtimeEngine::reclaim_retired_banks() noexcept {
  return reclaim_retired_bank_telemetry().count;
}

bool RealtimeEngine::prepare_capture() noexcept {
  if (capture_ring_) {
    return true;
  }
  try {
    capture_ring_ = std::make_unique<CaptureRing>();
    return true;
  } catch (const std::bad_alloc&) {
    return false;
  }
}

foundation::Result<void> RealtimeEngine::arm_capture() noexcept {
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    return invalid_argument(
        "realtime capture may only be armed while running");
  }
  auto expected = CaptureState::idle;
  if (capture_state_.load(std::memory_order_acquire) != expected) {
    return invalid_argument("realtime capture is not idle");
  }
  if (!prepare_capture()) {
    // Error's default details object and a descriptive string may allocate.
    // Do not attempt a second allocation while reporting exhausted storage.
    return foundation::Result<void>::failure(
        {foundation::ErrorCode::internal_error, {}, nullptr});
  }
  if (!capture_state_.compare_exchange_strong(
          expected,
          CaptureState::arm_pending,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    return invalid_argument("realtime capture is not idle");
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> RealtimeEngine::disarm_capture() noexcept {
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    return invalid_argument(
        "realtime capture may only be disarmed while running");
  }
  auto expected = CaptureState::active;
  if (!capture_state_.compare_exchange_strong(
          expected,
          CaptureState::disarm_pending,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    if (expected == CaptureState::corrupted ||
        expected == CaptureState::disarm_pending) {
      return foundation::Result<void>::success();
    }
    return invalid_argument("realtime capture is not active");
  }
  return foundation::Result<void>::success();
}

std::size_t RealtimeEngine::drain_capture(
    std::span<CapturedTriggerEvent> output) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  std::size_t drained = 0;
  while (capture_ring_ && drained < output.size() &&
         capture_ring_->try_pop(output[drained])) {
    ++drained;
  }
  drained_events_ += drained;
  return drained;
}

std::size_t RealtimeEngine::drain_trigger_outcomes(
    std::span<RuntimeTriggerOutcomeEvent> output) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  std::size_t drained = 0;
  while (drained < output.size() &&
         trigger_outcome_ring_.try_pop(output[drained])) {
    ++drained;
  }
  drained_outcomes_ += drained;
  return drained;
}

std::size_t RealtimeEngine::drain_voice_states(
    std::span<RuntimeVoiceStateEvent> output) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  const auto drained = detail::drain_voice_states_fail_closed(
      voice_state_stream_state_,
      output,
      [this](RuntimeVoiceStateEvent& event) noexcept {
        return voice_state_ring_.try_pop(event);
      });
  drained_voice_states_ += drained;
  return drained;
}

foundation::Result<void> RealtimeEngine::start() {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped) {
    return invalid_argument("realtime engine is already running");
  }
  if (!scheduled_pattern_record_quiescent() ||
      (input_profile_ && (pattern_input_profile_status().retained_completions != 0 ||
                         pattern_input_profile_status().held_release_reservations != 0)))
    return invalid_argument("companion ownership must settle before restart");
  const auto start_epoch = start_epoch_;
  if (start_epoch == std::numeric_limits<std::uint64_t>::max()) {
    return invalid_argument(
        "realtime engine start epoch is exhausted; restart the host process "
        "with a new engine instance");
  }

  pattern_transport_commands_.clear_quiescent();
  pattern_transport_receipts_.clear_quiescent();
  retained_transport_receipt_.reset();
  pattern_transport_reserved_ = false;
  control_pattern_playing_ = false;
  acknowledged_pattern_generation_ = 0;
  acknowledged_record_authority_ = {};
  pattern_playing_ = false;
  queue_.clear_quiescent();
  fx_queue_.clear_quiescent();
  master_fx_.reset();
  publish_queue_.clear_quiescent();
  audio_pending_pattern_.reset();
  if (capture_ring_) {
    capture_ring_->clear_quiescent();
  }
  trigger_outcome_ring_.clear_quiescent();
  voice_state_ring_.clear_quiescent();
  pending_publications_.store(0, std::memory_order_relaxed);
  queued_pattern_generation_.store(0, std::memory_order_relaxed);
  audio_pending_pattern_generation_.store(0, std::memory_order_relaxed);
  pattern_origin_frame_ = 0;
  pattern_event_index_ = 0;
  pattern_event_loop_ = 0;
  pattern_continuous_timing_ = false;
  pattern_tempo_applied_frame_ = 0;
  pattern_position_available_ = true;
  const auto tempo_slot = current_pattern_slot_.load(std::memory_order_relaxed);
  pattern_tempo_anchor_ = {0, 0, tempo_slot == kNoPatternSlot
      ? std::uint16_t{0} : pattern_slots_[tempo_slot].pattern->bpm()};
  std::fill(voices_.begin(), voices_.end(), Voice{});
  voice_scan_extent_ = 0;
  preview_mask_ = 0;
  enqueued_events_ = 0;
  queued_host_input_events_.store(0, std::memory_order_relaxed);
  dequeued_events_ = 0;
  cancelled_events_ = 0;
  started_voices_ = 0;
  completed_voices_ = 0;
  active_voices_ = 0;
  peak_voices_ = 0;
  cancelled_voices_ = 0;
  invalid_events_ = 0;
  audio_invalid_events_ = 0;
  stopped_rejections_ = 0;
  queue_drops_ = 0;
  voice_drops_ = 0;
  callback_count_ = 0;
  rendered_frames_ = 0;
  max_callback_frames_ = 0;
  capture_state_.store(CaptureState::idle, std::memory_order_relaxed);
  captured_events_ = 0;
  drained_events_ = 0;
  capture_drops_ = 0;
  capture_origin_frame_ = 0;
  published_outcomes_ = 0;
  drained_outcomes_ = 0;
  runtime_outcome_drops_ = 0;
  voice_state_stream_state_.store(
      RuntimeVoiceStateStreamState::healthy, std::memory_order_relaxed);
  published_voice_states_ = 0;
  drained_voice_states_ = 0;
  voice_state_drops_ = 0;
  enqueued_fx_gestures_ = 0;
  dequeued_fx_gestures_ = 0;
  fx_queue_drops_ = 0;
  master_fx_processed_frames_ = 0;
  queued_fx_gestures_.store(0, std::memory_order_relaxed);
  enqueued_tempo_updates_ = 0;
  applied_tempo_updates_ = 0;
  current_master_fx_bpm_.store(master_fx_.bpm(), std::memory_order_relaxed);
  accepted_filter_state_ = FilterLiveState{};
  accepted_filter_sequence_ = 0;
  enqueued_filter_controls_ = 0;
  applied_filter_sequence_ = 0;
  dequeued_filter_controls_ = 0;
  start_epoch_ = start_epoch + 1;
  // Quiescent writer handoff: the new epoch's applied Filter state is the
  // chain's reset independent OFF, so a stale pre-restart ACK is distinguishable
  // by epoch and content.
  filter_applied_channel_.publish(
      FilterAppliedState{master_fx_.filter_state(), 0, start_epoch_});
  // The live Pad gates follow the same rule: a start leaves no old mask, and
  // the new epoch's neutral applied pair distinguishes any stale snapshot.
  accepted_pad_gates_ = PadGatesState{};
  accepted_pad_gates_sequence_ = 0;
  enqueued_pad_gates_ = 0;
  dequeued_pad_gates_ = 0;
  audio_pad_gates_ = PadGatesState{};
  applied_pad_gates_sequence_ = 0;
  pad_gates_applied_channel_.publish(
      PadGatesAppliedState{{}, 0, start_epoch_});
  observed_audio_pending_ = {};
  observed_last_queued_ = {};
  observed_claimed_through_ = 0;
  observed_last_audio_cancel_ = 0;
  pattern_claim_closed_.store(0, std::memory_order_seq_cst);
  publish_transport_decision();
  publish_audio_observation();
  publish_control_observation();
  state_.store(RealtimeState::running, std::memory_order_release);
  return foundation::Result<void>::success();
}

void RealtimeEngine::stop() noexcept {
  // Callback/adapter gate is drained by the Host before this quiescent entry.
  // Retain companion evidence rather than silently treating shutdown as ACK.
  if (scheduled_cancel_ && !scheduled_cancel_won_ && pattern_transport_reserved_ &&
      !retained_transport_receipt_) {
    apply_pattern_transport(rendered_frames_);
    PatternTransportReceiptCell cell;
    if (pattern_transport_receipts_.try_pop(cell)) {
      retained_transport_receipt_ = cell;
      scheduled_cutoff_receipt_ = cell;
    }
  }
  if (scheduled_cancel_ && !scheduled_cancel_won_ &&
      !pattern_transport_reserved_ && !scheduled_cutoff_receipt_)
    scheduled_cancel_invalidated_ = true; // Unsent e2 only; never replace actual evidence.
  auto tag = scheduled_tag_.load(std::memory_order_seq_cst);
  const auto phase = schedule_phase(tag);
  if (phase == ScheduledPatternPhase::submitted || phase == ScheduledPatternPhase::preparing ||
      phase == ScheduledPatternPhase::cancel_preparing || phase == ScheduledPatternPhase::armed)
    // Only the retained real cancellation intent can claim cancellation
    // success. Exceptional quiescent owner loss before S refuses e1 instead.
    scheduled_tag_.store(schedule_tag(tag >> 4U, scheduled_cancel_won_
        ? ScheduledPatternPhase::cancelled : ScheduledPatternPhase::refused),
        std::memory_order_seq_cst);
  scheduled_cutoff_serial_.store(tag >> 4U, std::memory_order_seq_cst);
  release_scheduled_borrow_audio();
  invalidate_profile_inputs_quiescent();
  // The callback is quiescent here. Discard volatile transport state together
  // with its generation; obsolete reservations must not block stopped setup.
  if (!scheduled_cancel_ || scheduled_cancel_won_) pattern_transport_generation_ = 0;
  if (!scheduled_request_) pattern_transport_epoch_ = 0;
  pattern_transport_commands_.clear_quiescent();
  pattern_transport_receipts_.clear_quiescent();
  if (!scheduled_cancel_ || scheduled_cancel_won_) retained_transport_receipt_.reset();
  retained_transport_switch_.reset();
  retained_transport_predecessor_.reset();
  if (!scheduled_cancel_ || scheduled_cancel_won_) {
    for (auto& id : retained_transport_ids_) id.reset();
    retained_transport_bpms_.fill(0);
  }
  if (!scheduled_cancel_ || scheduled_cancel_won_) pattern_transport_reserved_ = false;
  control_pattern_playing_ = false;
  acknowledged_pattern_generation_ = 0;
  pattern_playing_ = false;
  const PublishOnReturn audio_publish{*this, &RealtimeEngine::publish_audio_observation};
  const PublishOnReturn control_publish{*this, &RealtimeEngine::publish_control_observation};
  observed_last_queued_ = {};
  observed_audio_pending_ = {};
  pattern_claim_closed_.store(0, std::memory_order_seq_cst);
  state_.store(RealtimeState::stopped, std::memory_order_release);
  cancelled_events_ += queue_.clear_quiescent();
  queued_host_input_events_.store(0, std::memory_order_relaxed);
  fx_queue_.clear_quiescent();
  queued_fx_gestures_.store(0, std::memory_order_relaxed);
  master_fx_.reset();
  // Stopped is neutral: the accepted shadow and the applied snapshot both
  // return to the default independent OFF of the current epoch.
  accepted_filter_state_ = FilterLiveState{};
  accepted_filter_sequence_ = 0;
  applied_filter_sequence_ = 0;
  filter_applied_channel_.publish(
      FilterAppliedState{master_fx_.filter_state(), 0, start_epoch_});

  std::uint64_t active = 0;
  for (auto& voice : voices_) {
    if (voice.active) {
      ++active;
      release_voice_bank(voice);
      release_voice_pattern(voice);
    }
    voice = Voice{};
  }
  cancelled_voices_ += active;
  voice_scan_extent_ = 0;
  active_voices_ = 0;
  preview_mask_ = 0;

  std::uint8_t pending_slot = 0;
  while (publish_queue_.try_pop(pending_slot)) {
    bank_slots_[pending_slot].state.store(
        BankState::reclaimable, std::memory_order_release);
    pending_publications_.fetch_sub(1, std::memory_order_relaxed);
  }
  const auto audio_pending_generation = pattern_token_generation(
      audio_pending_pattern_generation_.exchange(
          0, std::memory_order_acq_rel));
  const auto queued_generation = pattern_token_generation(
      queued_pattern_generation_.exchange(0, std::memory_order_acq_rel));
  if (audio_pending_pattern_.has_value()) {
    pattern_slots_[audio_pending_pattern_->slot].state.store(
        PatternState::reclaimable, std::memory_order_release);
    audio_pending_pattern_.reset();
  }
  if (audio_pending_generation != 0) {
    canceled_pattern_publications_ += 1;
  }
  if (queued_generation != 0) {
    const auto queued = std::find_if(
        pattern_slots_.begin(),
        pattern_slots_.end(),
        [queued_generation](const PatternSlot& candidate) {
          return candidate.state.load(std::memory_order_acquire) ==
                     PatternState::pending &&
                 candidate.generation == queued_generation;
        });
    if (queued != pattern_slots_.end()) {
      queued->state.store(
          PatternState::reclaimable, std::memory_order_release);
    }
    if (queued_generation != audio_pending_generation) {
      canceled_pattern_publications_ += 1;
    }
  }
  if (capture_state_.load(std::memory_order_relaxed) !=
      CaptureState::corrupted) {
    capture_state_.store(CaptureState::idle, std::memory_order_release);
  }
  // Stopping leaves no old mask: both gate halves go neutral at once and the
  // applied snapshot is republished so no stale pair survives the stop.
  accepted_pad_gates_ = PadGatesState{};
  accepted_pad_gates_sequence_ = 0;
  audio_pad_gates_ = PadGatesState{};
  applied_pad_gates_sequence_ = 0;
  pad_gates_applied_channel_.publish(
      PadGatesAppliedState{{}, 0, start_epoch_});
  publish_transport_decision();

}

EnqueueResult RealtimeEngine::enqueue(TriggerEvent event) noexcept {
  PadControlEvent control{
      event.sequence,
      event.slot,
      event.velocity,
      PadControlKind::press,
      {},
  };
  if (state_.load(std::memory_order_acquire) == RealtimeState::running &&
      event.slot < kRealtimeSampleSlots &&
      pending_publications_.load(std::memory_order_acquire) == 0 &&
      (availability_mask_ &
       (std::uint64_t{1} << event.slot)) != 0) {
    control.playback = published_playback(event.slot);
  }
  return enqueue_control(control);
}

EnqueueResult RealtimeEngine::enqueue_control(PadControlEvent event) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    stopped_rejections_ += 1;
    return EnqueueResult::not_running;
  }
  if (!valid_control_kind(event.kind)) {
    invalid_events_ += 1;
    return EnqueueResult::invalid_velocity;
  }
  // `stop_all` and the two audition kinds address no Pad, so `slot` carries no
  // meaning for them and must not be validated as one.
  const auto pad_addressed = event.kind != PadControlKind::stop_all &&
                             event.kind != PadControlKind::audition_start &&
                             event.kind != PadControlKind::audition_stop;
  if (pad_addressed && event.slot >= kRealtimeSampleSlots) {
    invalid_events_ += 1;
    return EnqueueResult::invalid_slot;
  }
  // Refuse an audition with nothing published rather than letting the audio
  // thread discard it silently: the caller can see this, an `audio_invalid_`
  // increment three milliseconds later is not. `sample_unavailable` is the
  // existing member for "the bytes you asked for are not there"; auditions add
  // no new result vocabulary.
  if (event.kind == PadControlKind::audition_start) {
    // `current` or `pending`: since publication is applied by the audio thread,
    // a Bank published moments ago is still `pending` here, and the render that
    // processes this event drains the audition queue before the control events,
    // so it will be current by the time the voice starts. Requiring `current`
    // would refuse the ordinary publish-then-play sequence.
    const auto playable = std::any_of(
        audition_slots_.begin(),
        audition_slots_.end(),
        [](const BankSlot& candidate) {
          const auto state = candidate.state.load(std::memory_order_acquire);
          return state == BankState::current || state == BankState::pending;
        });
    if (!playable) {
      invalid_events_ += 1;
      return EnqueueResult::sample_unavailable;
    }
  }
  if (event.kind == PadControlKind::press &&
      (event.velocity == 0 || event.velocity > 127)) {
    invalid_events_ += 1;
    return EnqueueResult::invalid_velocity;
  }
  const auto replay = event.origin == PadControlOrigin::performance_replay;
  if (event.origin != PadControlOrigin::host_input && !replay) {
    invalid_events_ += 1;
    return EnqueueResult::invalid_velocity;
  }
  if (replay &&
      (event.kind != PadControlKind::press || !valid_material(event.material) ||
       event.duration_frames == 0 ||
       !valid_playback(event.playback, event.material.frame_count))) {
    invalid_events_ += 1;
    return EnqueueResult::invalid_velocity;
  }
  if (!replay &&
      (event.kind == PadControlKind::press ||
       event.kind == PadControlKind::preview_set)) {
    if (pending_publications_.load(std::memory_order_acquire) != 0) {
      return EnqueueResult::bank_transition;
    }
    if ((availability_mask_ &
         (std::uint64_t{1} << event.slot)) == 0) {
      invalid_events_ += 1;
      return EnqueueResult::sample_unavailable;
    }
  }
  if (!replay && event.kind == PadControlKind::preview_set &&
      !valid_playback(event.playback, current_sample(event.slot).frame_count)) {
    invalid_events_ += 1;
    return EnqueueResult::invalid_velocity;
  }
  if (!replay) {
    queued_host_input_events_.fetch_add(1, std::memory_order_relaxed);
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
    testing::invoke_realtime_hook(testing::RealtimeHookPoint::host_input_reserved);
#endif
  }
  if (input_profile_ && !replay &&
      (event.kind == PadControlKind::press || event.kind == PadControlKind::release)) {
    queued_host_input_events_.fetch_sub(1, std::memory_order_relaxed);
    return EnqueueResult::invalid_velocity;  // Use the negotiated companion identity.
  }
  if (!(input_profile_ ? push_profile_control(event) : queue_.try_push(event))) {
    if (!replay) {
      queued_host_input_events_.fetch_sub(1, std::memory_order_relaxed);
    }
    queue_drops_ += 1;
    return EnqueueResult::queue_full;
  }

  enqueued_events_ += 1;
  return EnqueueResult::accepted;
}

std::optional<std::uint64_t> RealtimeEngine::pattern_input_profile_storage_bytes(
    std::size_t pending) noexcept {
  if (pending == 0 || pending > kRealtimeQueueCapacity) return std::nullopt;
  const auto queue = detail::RuntimeSpscStorage<ProfileInputCell>::allocation_bytes(2 * pending);
  if (!queue) return std::nullopt;
  const auto first = checked_runtime_byte_sum(sizeof(PatternInputProfile), *queue);
  const auto second = first ? checked_runtime_byte_sum(*first,
      2 * pending * sizeof(InputCompletionCell)) : std::nullopt;
  return second ? checked_runtime_byte_sum(*second, pending * sizeof(HeldInput)) : std::nullopt;
}

foundation::Result<void> RealtimeEngine::enable_pattern_input_profile(
    std::uint64_t generation) {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped ||
      generation == 0 || generation != pattern_transport_generation_ ||
      queue_.size_approx() != 0 || active_voices_ != 0 ||
      !scheduled_pattern_record_quiescent())
    return invalid_argument("input profile requires quiescent generation activation");
  if (input_profile_) {
    const auto status = pattern_input_profile_status();
    if (status.ordinary_pending || status.held_release_reservations ||
        status.retained_completions)
      return invalid_argument("input profile still owns accepted operations or holds");
    if (generation < input_profile_->generation)
      return invalid_argument("input profile generation is stale");
  } else {
    input_profile_ = std::make_unique<PatternInputProfile>(queue_.capacity());
  }
  input_profile_->generation = generation;
  input_profile_observed_.store(input_profile_.get(), std::memory_order_release);
  return foundation::Result<void>::success();
}

PatternInputAdmission RealtimeEngine::enqueue_pattern_input(
    const PatternInputCommand& command) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  const auto refuse = [](PatternInputSubmit result) {
    return PatternInputAdmission{result};
  };
  if (!input_profile_) return refuse(PatternInputSubmit::disabled);
  if (state_.load(std::memory_order_acquire) != RealtimeState::running)
    return refuse(PatternInputSubmit::not_running);
  auto& profile = *input_profile_;
  if (command.runtime_generation == 0 || command.runtime_generation != profile.generation ||
      command.runtime_generation != pattern_transport_generation_)
    return refuse(PatternInputSubmit::stale_generation);
  if (command.frame_epoch == 0 || command.frame_epoch != start_epoch_)
    return refuse(PatternInputSubmit::stale_frame_epoch);
  if (command.slot >= kRealtimeSampleSlots ||
      (!command.release && (command.velocity == 0 || command.velocity > 127)) ||
      (!command.release && command.held_press_sequence != 0))
    return refuse(PatternInputSubmit::invalid_input);
  if (profile.last_sequence == std::numeric_limits<std::uint64_t>::max() ||
      profile.last_ordinal == std::numeric_limits<std::uint64_t>::max())
    return refuse(PatternInputSubmit::exhausted);
  const auto n = profile.capacity;
  std::size_t completion = 2 * n, hold = n;
  PatternInputAuthority authority{};
  if (command.release) {
    for (std::size_t i = 0; i < n; ++i)
      if (command.held_press_sequence != 0 &&
          profile.holds[i].sequence == command.held_press_sequence &&
          profile.holds[i].slot == command.slot && !profile.holds[i].release_queued) {
        hold = i;
        break;
      }
    if (hold == n) return refuse(PatternInputSubmit::stale_hold);
    completion = n + hold;
    if (profile.completions[completion].state.load(std::memory_order_acquire) !=
        InputCompletionState::reserved) return refuse(PatternInputSubmit::stale_hold);
    authority = profile.holds[hold].authority;
  } else {
    if (pending_publications_.load(std::memory_order_acquire) != 0)
      return refuse(PatternInputSubmit::bank_transition);
    if ((availability_mask_ & (std::uint64_t{1} << command.slot)) == 0)
      return refuse(PatternInputSubmit::sample_unavailable);
    if (!is_default_playback_sentinel(command.playback) &&
        !valid_playback(command.playback, current_sample(command.slot).frame_count))
      return refuse(PatternInputSubmit::invalid_input);
    if (profile.ordinary_pending.load(std::memory_order_acquire) >= n)
      return refuse(PatternInputSubmit::queue_full);
    for (std::size_t i = 0; i < n; ++i)
      if (profile.completions[i].state.load(std::memory_order_acquire) ==
          InputCompletionState::empty) { completion = i; break; }
    if (completion == 2 * n) return refuse(PatternInputSubmit::completion_full);
    if (command.held) {
      for (std::size_t i = 0; i < n; ++i)
        if (profile.holds[i].sequence == 0 &&
            profile.completions[n + i].state.load(std::memory_order_acquire) ==
                InputCompletionState::empty) { hold = i; break; }
      if (hold == n) return refuse(PatternInputSubmit::release_full);
    }
    // This acquire is the press admission point. A callback may have already
    // published a frontier beyond S while its actual start CAS has not happened.
    const auto tag = scheduled_tag_.load(std::memory_order_seq_cst);
    const auto phase = schedule_phase(tag);
    if (scheduled_request_ && (tag >> 4U) == scheduled_request_->serial &&
        (phase == ScheduledPatternPhase::starting || phase == ScheduledPatternPhase::applied))
      authority = {scheduled_request_->serial, scheduled_request_->epoch, true};
    else if (phase == ScheduledPatternPhase::empty)
      authority = acknowledged_record_authority_;
    if (authority.recording && scheduled_cutoff_serial_.load(std::memory_order_seq_cst) ==
        authority.schedule_serial) authority.recording = false;
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
    testing::invoke_realtime_hook(testing::RealtimeHookPoint::pattern_input_authority_acquired);
#endif
  }
  // Capacity escrow also promises a future positive operation identity. Do
  // not let an ordinary input spend the last IDs owed to physical releases.
  // A queued release already owns its identity and needs no second one.
  std::uint64_t future_release_identities = 0;
  for (std::size_t i = 0; i < n; ++i)
    future_release_identities += profile.holds[i].sequence != 0 &&
        !profile.holds[i].release_queued;
  if (command.release) --future_release_identities; // Actual matching hold above.
  else if (command.held) ++future_release_identities;
  const auto identity_maximum = std::numeric_limits<std::uint64_t>::max();
  if (identity_maximum - profile.last_sequence <= future_release_identities ||
      identity_maximum - profile.last_ordinal <= future_release_identities)
    return refuse(PatternInputSubmit::exhausted);
  const auto sequence = profile.last_sequence + 1;
  const auto ordinal = profile.last_ordinal + 1;
  auto& ledger = profile.completions[completion];
  ledger.result = {command.runtime_generation, command.frame_epoch, sequence,
      command.held_press_sequence, ordinal, 0, command.slot, authority,
      PatternInputDisposition::invalidated_before_consume};
  ledger.state.store(InputCompletionState::pending, std::memory_order_release);
  if (!command.release) {
    profile.ordinary_pending.fetch_add(1, std::memory_order_acq_rel);
    if (hold != n) {
      profile.holds[hold] = {sequence, command.slot, authority, false};
      profile.completions[n + hold].state.store(InputCompletionState::reserved,
          std::memory_order_release);
    }
  } else profile.holds[hold].release_queued = true;
  const PadControlEvent event{sequence, command.slot, command.velocity,
      command.release ? PadControlKind::release : PadControlKind::press, command.playback};
  queued_host_input_events_.fetch_add(1, std::memory_order_relaxed);
  const ProfileInputCell cell{event, ordinal, static_cast<std::uint16_t>(completion),
      hold == n ? kNoInputCell : static_cast<std::uint16_t>(hold), command.release};
  if (!profile.queue.try_push(cell)) {
    queued_host_input_events_.fetch_sub(1, std::memory_order_relaxed);
    ledger.state.store(command.release ? InputCompletionState::reserved :
        InputCompletionState::empty, std::memory_order_release);
    if (!command.release) {
      profile.ordinary_pending.fetch_sub(1, std::memory_order_release);
      if (hold != n) {
        profile.holds[hold] = {};
        profile.completions[n + hold].state.store(InputCompletionState::empty,
            std::memory_order_release);
      }
    } else profile.holds[hold].release_queued = false;
    return refuse(PatternInputSubmit::queue_full);
  }
  profile.last_sequence = sequence;
  profile.last_ordinal = ordinal;
  scheduled_settled_serial_.store(0, std::memory_order_release);
  ++enqueued_events_;
  return {PatternInputSubmit::accepted, sequence, ordinal, authority};
}

std::optional<PatternInputCompletion> RealtimeEngine::inspect_pattern_input_completion(
    std::uint64_t generation, std::uint64_t epoch, std::uint64_t sequence) const noexcept {
  if (!input_profile_ || generation == 0 || epoch == 0 || sequence == 0 ||
      generation != input_profile_->generation) return std::nullopt;
  for (std::size_t i = 0; i < 2 * input_profile_->capacity; ++i) {
    const auto& cell = input_profile_->completions[i];
    if (cell.state.load(std::memory_order_acquire) == InputCompletionState::terminal &&
        cell.result.runtime_generation == generation && cell.result.frame_epoch == epoch &&
        cell.result.sequence == sequence) return cell.result;
  }
  return std::nullopt;
}

bool RealtimeEngine::consume_pattern_input_completion(
    std::uint64_t generation, std::uint64_t epoch, std::uint64_t sequence) noexcept {
  if (!inspect_pattern_input_completion(generation, epoch, sequence)) return false;
  auto& profile = *input_profile_;
  for (std::size_t i = 0; i < 2 * profile.capacity; ++i) {
    auto& cell = profile.completions[i];
    if (cell.state.load(std::memory_order_acquire) != InputCompletionState::terminal ||
        cell.result.sequence != sequence) continue;
    // Only a RELEASE ticket retires its physical escrow. Consuming the press
    // ticket, including muted/toggle/capacity, does not touch its HeldInput.
    if (i >= profile.capacity) profile.holds[i - profile.capacity] = {};
    cell.state.store(InputCompletionState::empty, std::memory_order_release);
    return true;
  }
  return false;
}

PatternInputProfileStatus RealtimeEngine::pattern_input_profile_status() const noexcept {
  if (!input_profile_) return {};
  const auto& p = *input_profile_;
  PatternInputProfileStatus result{true, p.generation, p.capacity, 2 * p.capacity,
      p.ordinary_pending.load(std::memory_order_acquire), 0, 0};
  for (std::size_t i = 0; i < p.capacity; ++i)
    result.held_release_reservations += p.holds[i].sequence != 0;
  for (std::size_t i = 0; i < 2 * p.capacity; ++i) {
    const auto state = p.completions[i].state.load(std::memory_order_acquire);
    result.retained_completions += state == InputCompletionState::pending ||
        state == InputCompletionState::terminal;
  }
  return result;
}

bool RealtimeEngine::revoke_pattern_input_holds_quiescent(std::uint64_t generation) noexcept {
  if (!input_profile_ || generation == 0 || generation != input_profile_->generation ||
      state_.load(std::memory_order_acquire) != RealtimeState::stopped ||
      input_profile_->queue.size_approx() != 0 || active_voices_ != 0) return false;
  auto& p = *input_profile_;
  for (std::size_t i = 0; i < p.capacity; ++i) {
    if (p.holds[i].release_queued) continue;  // Retained release ticket still owns it.
    p.holds[i] = {};
    p.completions[p.capacity + i].state.store(InputCompletionState::empty,
        std::memory_order_release);
  }
  return true;
}

bool RealtimeEngine::push_profile_control(PadControlEvent event) noexcept {
  auto& p = *input_profile_;
  if (p.ordinary_pending.load(std::memory_order_acquire) >= p.capacity ||
      p.last_ordinal == std::numeric_limits<std::uint64_t>::max()) return false;
  std::uint64_t future_release_ordinals = 0;
  for (std::size_t i = 0; i < p.capacity; ++i)
    future_release_ordinals += p.holds[i].sequence != 0 && !p.holds[i].release_queued;
  if (std::numeric_limits<std::uint64_t>::max() - p.last_ordinal <=
      future_release_ordinals) return false;
  p.ordinary_pending.fetch_add(1, std::memory_order_acq_rel);
  const ProfileInputCell cell{event, p.last_ordinal + 1};
  if (!p.queue.try_push(cell)) {
    p.ordinary_pending.fetch_sub(1, std::memory_order_release);
    return false;
  }
  ++p.last_ordinal;
  return true;
}

void RealtimeEngine::complete_profile_input(const ProfileInputCell& input,
    PatternInputDisposition disposition, std::uint64_t frame) noexcept {
  if (!input_profile_ || input.completion == kNoInputCell) return;
  auto& cell = input_profile_->completions[input.completion];
  cell.result.runtime_frame = frame;
  cell.result.disposition = disposition;
  cell.state.store(InputCompletionState::terminal, std::memory_order_release);
}

void RealtimeEngine::invalidate_profile_inputs_quiescent() noexcept {
  if (!input_profile_) return;
  ProfileInputCell cell{};
  while (input_profile_->queue.try_pop(cell)) {
    complete_profile_input(cell, PatternInputDisposition::invalidated_before_consume,
        rendered_frames_);
    ++cancelled_events_;
  }
  input_profile_->ordinary_pending.store(0, std::memory_order_release);
}

foundation::Result<void> RealtimeEngine::prepare_master_fx(
    std::uint16_t bpm) {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped) {
    return invalid_argument("Master FX must be prepared while stopped");
  }
  auto prepared =
      master_fx_.prepare(MasterFxPreparation{kRealtimeSampleRate, bpm});
  if (prepared.has_value()) {
    current_master_fx_bpm_.store(bpm, std::memory_order_relaxed);
  }
  return prepared;
}

FxEnqueueResult RealtimeEngine::enqueue_fx_gesture(
    FxGesture gesture) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    return FxEnqueueResult::not_running;
  }
  if (!master_fx_.prepared()) {
    return FxEnqueueResult::not_prepared;
  }
  if (!valid_fx_gesture(gesture)) {
    return FxEnqueueResult::invalid_fx;
  }
  if (gesture.value > kMasterFxValueMaximum) {
    return FxEnqueueResult::invalid_value;
  }
  // Publish the count before the SPSC release-store makes the entry visible;
  // render can therefore never subtract a gesture that is still uncounted.
  queued_fx_gestures_.fetch_add(1, std::memory_order_relaxed);
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::fx_reserved);
#endif
  if (!fx_queue_.try_push(MasterFxControlEvent{
          MasterFxControlKind::gesture, gesture, {}, {}, 0, 0})) {
    queued_fx_gestures_.fetch_sub(1, std::memory_order_relaxed);
    fx_queue_drops_ += 1;
    return FxEnqueueResult::queue_full;
  }
  enqueued_fx_gestures_ += 1;
  // Legacy Filter gestures and HOLD move the accepted Filter shadow with the
  // same pure transition the chain applies on the audio thread.
  accepted_filter_state_ = MasterFxChain::filter_live_state_after(
      accepted_filter_state_, gesture);
  return FxEnqueueResult::accepted;
}

FxEnqueueResult RealtimeEngine::enqueue_master_fx_tempo(
    std::uint16_t bpm) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    return FxEnqueueResult::not_running;
  }
  if (!master_fx_.prepared()) {
    return FxEnqueueResult::not_prepared;
  }
  if (bpm < 40 || bpm > 240) {
    return FxEnqueueResult::invalid_bpm;
  }
  if (!fx_queue_.try_push(MasterFxControlEvent{
          MasterFxControlKind::tempo, {}, {}, {}, 0, bpm})) {
    fx_queue_drops_ += 1;
    return FxEnqueueResult::queue_full;
  }
  enqueued_tempo_updates_ += 1;
  return FxEnqueueResult::accepted;
}

FxEnqueueResult RealtimeEngine::enqueue_filter_gesture(
    FilterGesture gesture) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    return FxEnqueueResult::not_running;
  }
  if (!master_fx_.prepared()) {
    return FxEnqueueResult::not_prepared;
  }
  // engage/move carry the full typed tuple; a release's parameters come from
  // current state, so only engage/move validate the tuple.
  if (gesture.phase != FilterPhase::release &&
      !MasterFxChain::valid_filter_parameters(gesture.parameters)) {
    return FxEnqueueResult::invalid_value;
  }
  // Reserve a cell of the same bounded queue before assigning the accepted
  // sequence: a full queue rejects without touching the accepted shadow.
  queued_fx_gestures_.fetch_add(1, std::memory_order_relaxed);
  if (!fx_queue_.try_push(MasterFxControlEvent{
          MasterFxControlKind::filter,
          {},
          gesture,
          {},
          accepted_filter_sequence_ + 1,
          0})) {
    queued_fx_gestures_.fetch_sub(1, std::memory_order_relaxed);
    fx_queue_drops_ += 1;
    return FxEnqueueResult::queue_full;
  }
  accepted_filter_sequence_ += 1;
  accepted_filter_state_ = MasterFxChain::filter_live_state_after(
      accepted_filter_state_, gesture);
  enqueued_filter_controls_ += 1;
  return FxEnqueueResult::accepted;
}

FilterControlStatus RealtimeEngine::filter_control_status() const noexcept {
  return FilterControlStatus{
      accepted_filter_state_,
      accepted_filter_sequence_,
      filter_applied_channel_.read()};
}

FxEnqueueResult RealtimeEngine::enqueue_pad_gates(
    std::uint64_t muted_mask, std::uint64_t solo_mask) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    return FxEnqueueResult::not_running;
  }
  // The gate is a voice-level gain, not an FX stage: it works whether or not
  // the Master FX chain has been prepared, and every bit pattern is legal.
  // Reserve a cell of the same bounded queue before assigning the accepted
  // sequence: a full queue rejects without touching the accepted shadow.
  queued_fx_gestures_.fetch_add(1, std::memory_order_relaxed);
  if (!fx_queue_.try_push(MasterFxControlEvent{
          MasterFxControlKind::pad_gates,
          {},
          {},
          PadGatesState{muted_mask, solo_mask},
          accepted_pad_gates_sequence_ + 1,
          0})) {
    queued_fx_gestures_.fetch_sub(1, std::memory_order_relaxed);
    fx_queue_drops_ += 1;
    return FxEnqueueResult::queue_full;
  }
  accepted_pad_gates_ = PadGatesState{muted_mask, solo_mask};
  accepted_pad_gates_sequence_ += 1;
  enqueued_pad_gates_ += 1;
  return FxEnqueueResult::accepted;
}

PadGatesControlStatus RealtimeEngine::pad_gates_status() const noexcept {
  return PadGatesControlStatus{
      accepted_pad_gates_,
      accepted_pad_gates_sequence_,
      pad_gates_applied_channel_.read()};
}

bool RealtimeEngine::pad_live_gated(std::uint8_t slot) const noexcept {
  const auto muted = (audio_pad_gates_.muted_mask >> slot) & 1U;
  const auto soloed = (audio_pad_gates_.solo_mask >> slot) & 1U;
  return muted != 0 ||
         (audio_pad_gates_.solo_mask != 0 && soloed == 0);
}

void RealtimeEngine::claim_queued_pattern(bool switch_only) noexcept {
  if (!audio_pending_pattern_.has_value()) {
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
    testing::invoke_realtime_hook(testing::RealtimeHookPoint::before_pattern_claim);
#endif
    pattern_claim_closed_.store(1, std::memory_order_seq_cst);
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
    testing::invoke_realtime_hook(
        testing::RealtimeHookPoint::pattern_admission_closed);
#endif
    // RMW returns the immediately preceding owner, never a saved token that
    // could have been reclaimed/reused while audio was paused.
    const auto mailbox = queued_pattern_generation_.fetch_or(
        kPatternTokenClaimedMask | kPatternAdmissionInvalidatedMask,
        std::memory_order_seq_cst);
    const auto token = pattern_slot_token(mailbox);
    if (token != 0) {
      const auto slot_index = static_cast<std::uint8_t>(token - 1);
      const auto& claimed = pattern_slots_[slot_index];
      if (switch_only && !claimed.switch_bar) {
        // General/overlay publication keeps its original callback-start
        // semantics. Admission is still closed while Q is restored.
        queued_pattern_generation_.fetch_and(
            ~kPatternTokenClaimedMask, std::memory_order_seq_cst);
        pattern_claim_closed_.store(0, std::memory_order_seq_cst);
        return;
      }
      const PatternPublishEntry publication{
          slot_index, claimed.generation, claimed.activation_frame};
      audio_pending_pattern_ = publication;
      observed_claimed_through_ = publication.generation;
      observed_audio_pending_ = {
          publication.generation, publication.activation_frame};
      audio_pending_pattern_generation_.store(token, std::memory_order_release);
    }
    // Includes claimed-empty. A/L must be established before releasing Q.
    queued_pattern_generation_.fetch_and(
        kPatternAdmissionMask, std::memory_order_seq_cst);
    pattern_claim_closed_.store(0, std::memory_order_seq_cst);
  }
}

void RealtimeEngine::render(
    float* left, float* right, std::uint32_t frames) noexcept {
  scheduled_settled_serial_.store(0, std::memory_order_release);
  std::fill_n(left, frames, 0.0F);
  std::fill_n(right, frames, 0.0F);
  callback_count_ += 1;
  cue_batch_blocked_ = cue_batch_pending_.load(std::memory_order_acquire) != 0 ||
      next_cue_batch_id_.load(std::memory_order_acquire) ==
          std::numeric_limits<std::uint64_t>::max();
  if (!cue_batch_blocked_) cue_batch_ = {};
  const auto absolute_start_frame = rendered_frames_;
  rendered_frames_ += frames;
  publish_transport_decision();
  max_callback_frames_ = std::max(max_callback_frames_, frames);
  if (!cue_batch_blocked_) {
    cue_batch_.begin_frame = absolute_start_frame;
    cue_batch_.end_frame = rendered_frames_;
  }
  if (frames != 0) prepare_scheduled_record_audio();

  MasterFxControlEvent fx_control{};
  auto filter_state_dirty = false;
  auto pad_gates_dirty = false;
  for (std::size_t processed = 0;
       processed < kRealtimeQueueCapacity &&
       fx_queue_.try_pop(fx_control);
       ++processed) {
    if (fx_control.kind == MasterFxControlKind::gesture) {
      static_cast<void>(master_fx_.apply_gesture(fx_control.gesture));
      dequeued_fx_gestures_ += 1;
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
      testing::invoke_realtime_hook(testing::RealtimeHookPoint::fx_popped);
#endif
      queued_fx_gestures_.fetch_sub(1, std::memory_order_relaxed);
      filter_state_dirty = true;
    } else if (fx_control.kind == MasterFxControlKind::filter) {
      static_cast<void>(master_fx_.apply_filter_gesture(fx_control.filter));
      applied_filter_sequence_ = fx_control.sequence;
      dequeued_filter_controls_ += 1;
      queued_fx_gestures_.fetch_sub(1, std::memory_order_relaxed);
      filter_state_dirty = true;
    } else if (fx_control.kind == MasterFxControlKind::pad_gates) {
      // The pair applies together: one dequeue swaps both masks atomically
      // with respect to the voice mix below.
      audio_pad_gates_ = fx_control.gates;
      applied_pad_gates_sequence_ = fx_control.sequence;
      dequeued_pad_gates_ += 1;
      queued_fx_gestures_.fetch_sub(1, std::memory_order_relaxed);
      pad_gates_dirty = true;
    } else {
      static_cast<void>(master_fx_.set_bpm(fx_control.bpm));
      current_master_fx_bpm_.store(
          fx_control.bpm, std::memory_order_relaxed);
      applied_tempo_updates_ += 1;
    }
  }
  if (pad_gates_dirty) {
    pad_gates_applied_channel_.publish(PadGatesAppliedState{
        audio_pad_gates_, applied_pad_gates_sequence_, start_epoch_});
  }
  if (filter_state_dirty) {
    // Publish the coherent applied Filter state once per quantum, after the
    // drain: accepted and applied stay separate, and the epoch stamps which
    // engine start produced this snapshot.
    filter_applied_channel_.publish(FilterAppliedState{
        master_fx_.filter_state(), applied_filter_sequence_, start_epoch_});
  }

  auto capture_state = CaptureState::arm_pending;
  if (capture_state_.load(std::memory_order_acquire) ==
      CaptureState::arm_pending) {
    capture_origin_frame_ = absolute_start_frame;
    // Capture consumers may drain an event before this callback returns. Make
    // its origin visible before active state and before any capture ring push.
    publish_audio_observation();
    capture_state_.compare_exchange_strong(
        capture_state,
        CaptureState::active,
        std::memory_order_release,
        std::memory_order_relaxed);
  }

  std::uint8_t published_slot = 0;
  while (publish_queue_.try_pop(published_slot)) {
    apply_published_bank(published_slot);
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
    testing::invoke_realtime_hook(
        testing::RealtimeHookPoint::bank_applied_before_pending_release);
#endif
    pending_publications_.fetch_sub(1, std::memory_order_release);
  }
  const auto refresh_audition_publications = [this]() noexcept {
    std::uint8_t published_audition = 0;
    for (std::size_t applied = 0;
         applied < kRealtimeAuditionBankCapacity &&
         audition_publish_queue_.try_pop(published_audition);
         ++applied) {
      apply_published_audition(published_audition);
    }
  };
  // Apply publication-only updates even when no audition start is queued.
  refresh_audition_publications();
  if (frames != 0) apply_pattern_transport(absolute_start_frame);
  claim_queued_pattern();
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_pattern_claim_hook();
#endif

  PadControlEvent event{};
  ProfileInputCell profile_input{};
  const auto pop_input = [&]() noexcept {
    profile_input = {};
    if (!input_profile_) return queue_.try_pop(event);
    if (!input_profile_->queue.try_pop(profile_input)) return false;
    event = profile_input.event;
    if (!profile_input.release)
      input_profile_->ordinary_pending.fetch_sub(1, std::memory_order_release);
    return true;
  };
  for (std::size_t processed = 0;
       processed < kRealtimeQueueCapacity && pop_input();
       ++processed) {
    dequeued_events_ += 1;
    auto disposition = PatternInputDisposition::invalidated_before_consume;
    struct CompleteOnReturn {
      RealtimeEngine& engine;
      const ProfileInputCell& input;
      PatternInputDisposition& disposition;
      std::uint64_t frame;
      ~CompleteOnReturn() { engine.complete_profile_input(input, disposition, frame); }
    } completion{*this, profile_input, disposition, absolute_start_frame};
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
    if (input_profile_) testing::invoke_realtime_hook(
        testing::RealtimeHookPoint::pattern_input_consumed);
#endif
    const auto replay = event.origin == PadControlOrigin::performance_replay;
    if (!replay) {
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
      testing::invoke_realtime_hook(testing::RealtimeHookPoint::host_input_popped);
#endif
      queued_host_input_events_.fetch_sub(1, std::memory_order_relaxed);
    }
    if (event.kind == PadControlKind::preview_set) {
      previews_[event.slot] = event.playback;
      preview_mask_ |= std::uint64_t{1} << event.slot;
      continue;
    }
    if (event.kind == PadControlKind::preview_clear) {
      preview_mask_ &= ~(std::uint64_t{1} << event.slot);
      continue;
    }
    if (event.kind == PadControlKind::release) {
      disposition = PatternInputDisposition::release_no_voice;
      const auto correlated = input_profile_ && profile_input.completion != kNoInputCell
          ? input_profile_->completions[profile_input.completion].result.held_press_sequence : 0;
      for (auto& voice : voices_) {
        // A Pad already in its release tail is not released again, so a
        // repeated release never shortens a long tail.
        if (voice.active && !voice.releasing && voice.slot == event.slot &&
            !is_audition_bank_slot(voice.bank_slot) &&
            voice.origin == PadControlOrigin::host_input &&
            (correlated == 0 || voice.sequence == correlated) &&
            (voice.trigger_mode == domain::TriggerMode::gate ||
             voice.trigger_mode == domain::TriggerMode::loop_gate)) {
          disposition = PatternInputDisposition::release_applied;
          stop_voice(voice, absolute_start_frame, VoiceStop::release);
        }
      }
      continue;
    }
    if (event.kind == PadControlKind::audition_stop) {
      for (auto& voice : voices_) {
        if (voice.active && is_audition_bank_slot(voice.bank_slot)) {
          stop_voice(voice, absolute_start_frame, VoiceStop::declick);
        }
      }
      continue;
    }
    if (event.kind == PadControlKind::stop_slot_live) {
      for (auto& voice : voices_) {
        if (voice.active && !is_audition_bank_slot(voice.bank_slot) &&
            voice.slot == event.slot && !voice.pattern_voice &&
            voice.origin == PadControlOrigin::host_input) {
          stop_voice(voice, absolute_start_frame, VoiceStop::declick);
        }
      }
      continue;
    }
    if (event.kind == PadControlKind::stop_slot ||
        event.kind == PadControlKind::stop_all) {
      for (auto& voice : voices_) {
        // An audition is not a Pad, so neither a Pad stop nor stop-all reaches
        // it; only `audition_stop` does. Otherwise stopping Pad 0 would cut a
        // preview, and stop-all would make auditions unusable during playback.
        if (voice.active && !is_audition_bank_slot(voice.bank_slot) &&
            (event.kind == PadControlKind::stop_all ||
             voice.slot == event.slot)) {
          stop_voice(voice, absolute_start_frame, VoiceStop::declick);
        }
      }
      continue;
    }

    bool stopped_toggle = false;
    if (!replay) {
      for (auto& candidate : voices_) {
        // A toggle in its release tail is already off: a press then starts
        // the Pad again, beside the fading tail.
        if (candidate.active && !candidate.releasing &&
            candidate.slot == event.slot &&
            candidate.origin == PadControlOrigin::host_input &&
            candidate.trigger_mode == domain::TriggerMode::loop_toggle) {
          stop_voice(candidate, absolute_start_frame, VoiceStop::release);
          stopped_toggle = true;
        }
      }
    }
    if (stopped_toggle) {
      disposition = PatternInputDisposition::toggle_stopped;
      continue;
    }

    // An audition sources its bytes from the reserved audition Bank, never from
    // `current_sample`, which always reads `bank_slots_[current_bank_slot_]`.
    // This branch is the whole reason reserving a slot makes a Set audible:
    // holding a Bank the voice-start path never reads would be silent.
    const auto audition = event.kind == PadControlKind::audition_start;
    std::uint8_t audition_slot = kNoAuditionSlot;
    if (audition) {
      // Acquiring this command orders the producer's preceding publications.
      // The initial drain may predate them; refresh before choosing the latest
      // source, with a fixed pool-sized bound even if control keeps publishing.
      refresh_audition_publications();
      audition_slot = current_audition_slot_.load(std::memory_order_acquire);
      if (audition_slot == kNoAuditionSlot) {
        audio_invalid_events_ += 1;
        continue;
      }
      auto& source = audition_slots_[audition_slot - kAuditionBankSlotBase];
      if (source.state.load(std::memory_order_acquire) != BankState::current) {
        audio_invalid_events_ += 1;
        continue;
      }
    }

    auto playback = event.playback;
    if (audition && is_default_playback_sentinel(playback)) {
      playback = audition_slots_[audition_slot - kAuditionBankSlotBase]
                     .bank->playback(kAuditionSampleSlot);
    } else if (!replay && is_default_playback_sentinel(playback)) {
      playback = (preview_mask_ & (std::uint64_t{1} << event.slot)) != 0
                     ? previews_[event.slot]
                     : published_playback(event.slot);
    }
    const auto sample =
        audition ? audition_sample(
                       static_cast<std::uint8_t>(
                           audition_slot - kAuditionBankSlotBase))
        : replay ? SampleView{nullptr, event.material, event.material.frame_count}
                 : current_sample(event.slot);
    if (!valid_playback_range(playback, sample.frame_count)) {
      audio_invalid_events_ += 1;
      continue;
    }
    if (playback.muted) {
      disposition = PatternInputDisposition::muted_no_voice;
      continue;
    }
    // A currently gated Pad accepts no new input either: the press is
    // blocked, not queued into a silent voice, so unmuting later does not
    // resurrect it. Audition starts bypass the gate entirely.
    if (!audition && pad_live_gated(event.slot)) {
      // Live gating silences an actually consumed press; its recording and
      // physical-release owners still need the successful no-voice result.
      disposition = PatternInputDisposition::muted_no_voice;
      continue;
    }
    bool dsp_active = false;
    detail::VoiceDspState dsp{};
    if (!prepare_voice_kernel(playback, sample.frame_count, dsp_active, dsp)) {
      audio_invalid_events_ += 1;
      continue;
    }
    if (!replay && voice_state_stream_state_.load(std::memory_order_relaxed) ==
        RuntimeVoiceStateStreamState::corrupted) {
      voice_drops_ += 1;
      disposition = PatternInputDisposition::voice_capacity;
      continue;
    }
    auto voice = std::find_if(
        voices_.begin(), voices_.end(), [](const Voice& candidate) {
          return !candidate.active;
        });
    if (voice == voices_.end()) {
      disposition = PatternInputDisposition::voice_capacity;
      voice_drops_ += 1;
      // Trigger outcomes describe Pad triggers the Host reports back to the
      // performer. An audition that loses the voice race is silent, not a
      // dropped Pad trigger.
      if (!replay && !audition) {
        if (trigger_outcome_ring_.try_push(RuntimeTriggerOutcomeEvent{
                event.sequence,
                RuntimeTriggerOutcome::voice_capacity,
                absolute_start_frame,
            })) {
          published_outcomes_ += 1;
        } else {
          runtime_outcome_drops_ += 1;
        }
      }
      continue;
    }
    if (replay && playback.trigger_mode != domain::TriggerMode::one_shot &&
        event.duration_frames >
            std::numeric_limits<std::uint64_t>::max() - absolute_start_frame) {
      audio_invalid_events_ += 1;
      continue;
    }
    const auto bank_slot =
        audition ? audition_slot
        : replay ? kLegacyBankSlot
                 : current_bank_slot_.load(std::memory_order_relaxed);
    *voice = Voice{};
    voice->dsp_active = dsp_active;
    voice->dsp = dsp;
    voice->sequence = event.sequence;
    voice->slot = event.slot;
    voice->samples = sample.samples;
    voice->material = sample.material;
    voice->frame_count = sample.frame_count;
    voice->start_frame = playback.start_frame;
    voice->end_frame = playback.end_frame;
    voice->cursor = playback.start_frame;
    voice->gain = (static_cast<float>(event.velocity) / 127.0F) *
                  playback.linear_gain;
    voice->trigger_mode = playback.trigger_mode;
    voice->bank_slot = bank_slot;
    set_voice_envelope(*voice, playback);
    voice->scheduled_release_frame =
        replay && playback.trigger_mode != domain::TriggerMode::one_shot
            ? absolute_start_frame + event.duration_frames
            : 0;
    voice->origin = event.origin;
    if (!replay && !audition && !publish_voice_state(
            *voice,
            RuntimeVoiceState::started,
            absolute_start_frame,
            dsp_active ? detail::voice_dsp_source_frame(dsp)
                       : playback.start_frame)) {
      *voice = Voice{};
      voice_drops_ += 1;
      disposition = PatternInputDisposition::voice_capacity;
      continue;
    }
    disposition = PatternInputDisposition::voice_started;
    voice->active = true;
    voice_scan_extent_ = std::max(
        voice_scan_extent_, static_cast<std::size_t>(voice - voices_.begin()) + 1);
    if (auto* const owner = bank_slot_for(bank_slot); owner != nullptr) {
      ++owner->active_voices;
    }
    started_voices_ += 1;
    active_voices_ += 1;
    peak_voices_ = std::max(peak_voices_, active_voices_);
    if (!replay && !audition) {
      if (trigger_outcome_ring_.try_push(RuntimeTriggerOutcomeEvent{
              event.sequence,
              RuntimeTriggerOutcome::voice_started,
              absolute_start_frame,
          })) {
        published_outcomes_ += 1;
      } else {
        runtime_outcome_drops_ += 1;
      }
      capture_voice_start(event, absolute_start_frame);
    }
  }

  for (std::uint32_t frame = 0; frame < frames; ++frame) {
    const auto runtime_frame = absolute_start_frame + frame;
    advance_scheduled_record_audio(runtime_frame, rendered_frames_);
    if (audio_pending_pattern_.has_value() &&
        runtime_frame >= audio_pending_pattern_->activation_frame) {
      auto expected_generation =
          static_cast<std::uint32_t>(audio_pending_pattern_->slot) + 1;
      if (audio_pending_pattern_generation_.compare_exchange_strong(
              expected_generation,
              expected_generation | kPatternTokenClaimedMask,
              std::memory_order_acq_rel,
              std::memory_order_acquire)) {
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
        testing::invoke_pattern_apply_hook();
#endif
        apply_published_pattern(*audio_pending_pattern_, runtime_frame);
      } else {
        pattern_slots_[audio_pending_pattern_->slot].state.store(
            PatternState::reclaimable, std::memory_order_release);
      }
      audio_pending_pattern_.reset();
      observed_audio_pending_ = {};
      // C was already published while B belonged to audio. Claim it now so
      // its returned frame is honored even within this same long callback.
      // One fixed mailbox RMW; no retry loop or per-frame empty polling.
      claim_queued_pattern(true);
    }
    for (std::size_t index = 0; index < voice_scan_extent_; ++index) {
      auto& voice = voices_[index];
      if (voice.active && !voice.releasing &&
          voice.scheduled_release_frame != 0 &&
          runtime_frame >= voice.scheduled_release_frame) {
        stop_voice(voice, runtime_frame, VoiceStop::release);
      }
    }
    if (!pattern_transport_enabled_ || pattern_playing_)
      schedule_pattern_events(runtime_frame);

    for (std::size_t index = 0; index < voice_scan_extent_; ++index) {
      auto& voice = voices_[index];
      if (!voice.active) {
        continue;
      }
      // F6 amplitude ramps: the voice's attack (a looping voice attacks only
      // on its initial trigger), a stateless boundary fade over the last
      // kRealtimeRampFrames before end_frame for non-looping voices, and the
      // stop_voice release tail. Attack and release use the voice's envelope
      // lengths, which default to the same 96 frames at scale 1/96. Each
      // component is skipped at full scale so unramped output stays
      // bit-identical.
      float ramp = 1.0F;
      if (voice.attack_frames_remaining != 0) {
        ramp *= static_cast<float>(
                    voice.attack_frames - voice.attack_frames_remaining) *
                voice.attack_scale;
        --voice.attack_frames_remaining;
      }
      if (voice.dsp_active) {
        // The kernel's end fade is measured in output frames, so a pitched
        // voice still fades over its last 96 frames.
        ramp *= detail::voice_dsp_end_fade(voice.dsp);
      } else if (!is_looping(voice.trigger_mode)) {
        const auto boundary_remaining = voice.end_frame - voice.cursor;
        if (boundary_remaining < kRealtimeRampFrames) {
          ramp *=
              static_cast<float>(boundary_remaining) * kRealtimeRampScale;
        }
      }
      if (voice.releasing &&
          voice.release_frames_remaining < voice.release_frames) {
        ramp *=
            static_cast<float>(voice.release_frames_remaining) *
            voice.release_scale;
      }
      // The live Pad gate (D04 Mute/Solo): a project Pad voice whose Pad is
      // muted, or unsoloed while any Solo is active, contributes no input
      // from the first frame under the applied mask. DSP and cursor/lifetime
      // still advance; re-allowing ramps back to the current sound without
      // retriggering. Audition bypasses the gate, and already accepted shared
      // Delay/Reverb tails remain in the shared bus.
      const bool live_gated = !is_audition_bank_slot(voice.bank_slot) &&
                              pad_live_gated(voice.slot);
      if (live_gated) {
        voice.live_gate = 0.0F;
      } else if (voice.live_gate < 1.0F) {
        voice.live_gate += kRealtimeRampScale;
        if (voice.live_gate > 1.0F) {
          voice.live_gate = 1.0F;
        }
      }
      const auto live_gate = voice.live_gate;
      if (voice.dsp_active) {
        const auto& material = voice.material;
        const float* const samples = voice.samples;
        auto value =
            detail::voice_dsp_read(
                voice.dsp,
                [&material, samples](std::uint32_t source_frame) {
                  return material.interleaved != nullptr
                             ? prepared_material_sample(material, source_frame)
                             : samples[source_frame];
                }) *
            voice.gain * ramp;
        if (live_gate != 1.0F) {
          value *= live_gate;
        }
        // Tone and EQ follow the envelope. They are linear and the gain is
        // constant, so filtering after it equals the decision's order.
        if (voice.dsp.filter_count != 0) {
          value = detail::voice_dsp_filter(
              voice.dsp, voice.filter_memory, value);
          // A filter still rings when its input reaches zero, so the declick
          // that ends the voice runs again on the filtered output: its last
          // 96 frames fade to zero instead of stepping to silence (owner
          // decision 2026-10-02).
          value *= detail::voice_dsp_end_fade(voice.dsp) *
                   detail::voice_dsp_release_declick(
                       voice.releasing, voice.release_frames_remaining);
        }
        // Zero filter input still leaves Tone/EQ memory. Keep evaluating it,
        // but block its contribution before it enters the shared FX bus.
        if (live_gated) {
          value = 0.0F;
        }
        left[frame] += value * voice.dsp.pan_left;
        right[frame] += value * voice.dsp.pan_right;
      } else {
        const auto sample = voice.material.interleaved != nullptr
                                ? prepared_material_sample(
                                      voice.material, voice.cursor)
                                : voice.samples[voice.cursor];
        auto value = sample * voice.gain * ramp;
        if (live_gate != 1.0F) {
          value *= live_gate;
        }
        left[frame] += value;
        right[frame] += value;
        ++voice.cursor;
      }
      if (voice.releasing &&
          --voice.release_frames_remaining == 0) {
        // The release tail ends at exact zero gain; deactivate immediately
        // so no denormal residue lingers.
        deactivate_voice(voice);
        continue;
      }
      if (voice.dsp_active) {
        // The kernel wraps loops and reflects ping-pong itself; it reports
        // only that a non-looping voice passed its last frame.
        if (detail::voice_dsp_advance(voice.dsp)) {
          continue;
        }
      } else {
        if (voice.cursor != voice.end_frame) {
          continue;
        }
        if (is_looping(voice.trigger_mode)) {
          voice.cursor = voice.start_frame;
          continue;
        }
      }
      if (voice.releasing) {
        // The tail reached end_frame: the terminal state was already
        // published as stopped at stop initiation, so no completed edge.
        deactivate_voice(voice);
        continue;
      }
      // An audition is outside the voice-state stream, and the start edge
      // already says so: `!replay && !audition` guards it where the voice is
      // created. This edge had no such guard, so an audition published a
      // `completed` with no `started` before it -- and carrying
      // `sequence == 0`, because an audition is enqueued as
      // `PadControlEvent{0, 0, 127, audition_start, {}}` and has no request
      // to number. The Web session requires a positive sequence, rejected the
      // event, and failed the whole Host with HOST_PROTOCOL_MISMATCH about a
      // second after an audition that had answered `played: true` (#799).
      if (!voice.pattern_voice &&
          !is_audition_bank_slot(voice.bank_slot) &&
          voice.origin == PadControlOrigin::host_input) {
        // A reversed voice completes at its trim start.
        static_cast<void>(publish_voice_state(
            voice,
            RuntimeVoiceState::completed,
            runtime_frame + 1,
            voice.dsp_active && voice.dsp.reverse ? voice.start_frame
                                                  : voice.end_frame));
      }
      voice.active = false;
      trim_voice_scan_extent();
      release_voice_bank(voice);
      release_voice_pattern(voice);
      completed_voices_ += 1;
      active_voices_ -= 1;
      continue;
    }
    left[frame] = std::clamp(left[frame], -1.0F, 1.0F);
    right[frame] = std::clamp(right[frame], -1.0F, 1.0F);
  }

  finish_scheduled_record_audio();

  // A fading or silent voice's filter memory decays toward denormals; flush
  // it to exact zero once per block.
  for (std::size_t index = 0; index < voice_scan_extent_; ++index) {
    auto& voice = voices_[index];
    if (voice.active && voice.dsp_active && voice.dsp.filter_count != 0) {
      detail::voice_dsp_flush_filters(voice.dsp, voice.filter_memory);
    }
  }

  if (master_fx_.prepared()) {
    master_fx_.process(left, right, frames);
    master_fx_processed_frames_ += frames;
  }

  // A consumer observing idle may finish and report final capture accounting
  // before this callback returns. Publish those counts before releasing idle.
  publish_audio_observation();
  capture_state = CaptureState::disarm_pending;
  capture_state_.compare_exchange_strong(
      capture_state,
      CaptureState::idle,
      std::memory_order_release,
      std::memory_order_relaxed);
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::capture_idle_published);
#endif
  const auto settled_tag = scheduled_tag_.load(std::memory_order_seq_cst);
  if (schedule_phase(settled_tag) == ScheduledPatternPhase::empty &&
      (settled_tag >> 4U) != 0 && active_voices_ == 0 && !scheduled_audio_.borrowed &&
      cue_batch_pending_.load(std::memory_order_acquire) == 0) {
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
    testing::invoke_realtime_hook(testing::RealtimeHookPoint::scheduled_before_settled_publish);
#endif
    // Logical failed-ticket consumption may observe this completed last use.
    // The adapter can still be running; its physical barrier remains separate.
    scheduled_settled_serial_.store(settled_tag >> 4U, std::memory_order_release);
  }
}

RealtimeTelemetry RealtimeEngine::telemetry() const noexcept {
  const std::lock_guard lock{observation_reader_mutex_};
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::observation_read);
#endif
  [[maybe_unused]] const auto a = audio_observation_.read();
  [[maybe_unused]] const auto c = control_observation_.read();
  return RealtimeTelemetry{
      state_.load(std::memory_order_acquire),
      c.start_epoch_,
      c.enqueued_events_,
      a.dequeued_events_,
      input_profile_observed_.load(std::memory_order_acquire)
          ? input_profile_observed_.load(std::memory_order_acquire)->queue.size_approx()
          : queue_.size_approx(),
      c.cancelled_events_,
      a.started_voices_,
      a.completed_voices_,
      a.active_voices_,
      a.cancelled_voices_,
      c.invalid_events_ + a.audio_invalid_events_,
      c.stopped_rejections_,
      c.queue_drops_,
      a.voice_drops_,
      a.callback_count_,
      a.rendered_frames_,
      a.max_callback_frames_,
  };
}

#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
void RealtimeEngine::set_start_epoch_for_testing(
    std::uint64_t epoch) noexcept {
  if (state_.load(std::memory_order_acquire) == RealtimeState::stopped) {
    start_epoch_ = epoch;
    publish_audio_observation();
    publish_control_observation();
  }
}

void RealtimeEngine::set_next_pattern_generation_for_testing(
    std::uint64_t generation) noexcept {
  if (state_.load(std::memory_order_acquire) == RealtimeState::stopped &&
      generation >= next_pattern_generation_) {
    next_pattern_generation_ = generation;
  }
}

void RealtimeEngine::set_rendered_frames_quiescent_for_testing(
    std::uint64_t frames) noexcept {
  rendered_frames_ = frames;
  publish_transport_decision();
  publish_audio_observation();
}

void RealtimeEngine::set_scheduled_serial_quiescent_for_testing(std::uint64_t serial) noexcept {
  if (!scheduled_request_ && serial <= kScheduledPatternSerialMaximum &&
      serial >= last_schedule_serial_) last_schedule_serial_ = serial;
}
void RealtimeEngine::set_pattern_input_sequence_quiescent_for_testing(
    std::uint64_t sequence) noexcept {
  if (input_profile_ && pattern_input_profile_status().retained_completions == 0 &&
      sequence >= input_profile_->last_sequence) input_profile_->last_sequence = sequence;
}
void RealtimeEngine::set_pattern_input_ordinal_quiescent_for_testing(
    std::uint64_t ordinal) noexcept {
  if (input_profile_ && pattern_input_profile_status().retained_completions == 0 &&
      ordinal >= input_profile_->last_ordinal) input_profile_->last_ordinal = ordinal;
}

std::uint32_t RealtimeEngine::queued_host_input_events_for_testing() const noexcept {
  return queued_host_input_events_.load(std::memory_order_acquire);
}
#endif

BankTelemetry RealtimeEngine::bank_telemetry() const noexcept {
  const std::lock_guard lock{observation_reader_mutex_};
  [[maybe_unused]] const auto a = audio_observation_.read();
  [[maybe_unused]] const auto c = control_observation_.read();
  return BankTelemetry{
      a.current_bank_generation_,
      pending_publications_.load(std::memory_order_relaxed),
      c.accepted_publications_,
      a.applied_publications_,
      c.reclaimed_banks_,
      c.bank_slot_rejections_,
      c.publish_queue_drops_,
  };
}

PatternTelemetry RealtimeEngine::pattern_telemetry() const noexcept {
  const std::lock_guard lock{observation_reader_mutex_};
  [[maybe_unused]] const auto a = audio_observation_.read();
  [[maybe_unused]] const auto c = control_observation_.read();
  const bool same_epoch = a.start_epoch_ == c.start_epoch_;
  const auto queued = same_epoch &&
      c.last_queued.generation > a.claimed_through
          ? c.last_queued : PatternObservation{};
  const auto pending = same_epoch &&
      a.pending.generation != c.last_audio_cancel
          ? a.pending : PatternObservation{};
  const auto selected = queued.generation != 0 ? queued : pending;
  const std::uint64_t count = (queued.generation != 0 ? 1U : 0U) +
      (pending.generation != 0 && pending.generation != queued.generation
           ? 1U : 0U);
  return PatternTelemetry{
      a.current_pattern_generation,
      selected.generation,
      selected.activation_frame,
      count,
      c.accepted_pattern_publications_,
      a.applied_pattern_publications_,
      c.superseded_pattern_publications_,
      c.canceled_pattern_publications_ + a.transport_canceled_publications,
      c.reclaimed_patterns_,
      c.pattern_publication_rejections_,
  };
}

CaptureTelemetry RealtimeEngine::capture_telemetry() const noexcept {
  const std::lock_guard lock{observation_reader_mutex_};
  // Acquire the active/idle handoff before consuming its published origin or
  // final counts. Reading state after the value could pair new idle with an
  // older value obtained before the final publication.
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_realtime_hook(testing::RealtimeHookPoint::capture_observe_state);
#endif
  const auto state = capture_state_.load(std::memory_order_acquire);
  [[maybe_unused]] const auto a = audio_observation_.read();
  [[maybe_unused]] const auto c = control_observation_.read();
  return CaptureTelemetry{
      state,
      a.captured_events_,
      c.drained_events_,
      a.capture_drops_,
      a.capture_origin_frame_,
  };
}

RuntimeTriggerOutcomeTelemetry
RealtimeEngine::trigger_outcome_telemetry() const noexcept {
  const std::lock_guard lock{observation_reader_mutex_};
  [[maybe_unused]] const auto a = audio_observation_.read();
  [[maybe_unused]] const auto c = control_observation_.read();
  return RuntimeTriggerOutcomeTelemetry{
      a.published_outcomes_,
      c.drained_outcomes_,
      a.runtime_outcome_drops_,
  };
}

RuntimeVoiceStateTelemetry RealtimeEngine::voice_state_telemetry()
    const noexcept {
  const std::lock_guard lock{observation_reader_mutex_};
  [[maybe_unused]] const auto a = audio_observation_.read();
  [[maybe_unused]] const auto c = control_observation_.read();
  return RuntimeVoiceStateTelemetry{
      voice_state_stream_state_.load(std::memory_order_acquire),
      a.published_voice_states_,
      c.drained_voice_states_,
      a.voice_state_drops_,
  };
}

MasterFxTelemetry RealtimeEngine::master_fx_telemetry() const noexcept {
  const std::lock_guard lock{observation_reader_mutex_};
  [[maybe_unused]] const auto a = audio_observation_.read();
  [[maybe_unused]] const auto c = control_observation_.read();
  return MasterFxTelemetry{
      c.enqueued_fx_gestures_,
      a.dequeued_fx_gestures_,
      queued_fx_gestures_.load(std::memory_order_relaxed),
      c.fx_queue_drops_,
      a.master_fx_processed_frames_,
      c.enqueued_tempo_updates_,
      a.applied_tempo_updates_,
      current_master_fx_bpm_.load(std::memory_order_relaxed),
      c.enqueued_filter_controls_,
      a.dequeued_filter_controls_,
  };
}

}  // namespace lmdj::audio
