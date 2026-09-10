#include <lmdj/audio/realtime_engine.hpp>

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
static_assert(std::atomic<std::uint16_t>::is_always_lock_free);
static_assert(std::atomic<std::uint8_t>::is_always_lock_free);
static_assert(
    kRealtimeMaximumSampleFrames ==
    std::numeric_limits<decltype(cooker::ResolvedPlayback::end_frame)>::max());

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

bool valid_playback(
    const cooker::ResolvedPlayback& playback,
    std::size_t frame_count) noexcept {
  return playback.start_frame < playback.end_frame &&
         playback.end_frame <= frame_count &&
         valid_trigger_mode(playback.trigger_mode) &&
         std::isfinite(playback.linear_gain) && playback.linear_gain >= 0.0F;
}

bool is_default_playback_sentinel(
    const cooker::ResolvedPlayback& playback) noexcept {
  return playback.start_frame == 0 && playback.end_frame == 0 &&
         playback.trigger_mode == domain::TriggerMode::one_shot &&
         playback.linear_gain == 0.0F && !playback.muted;
}

bool is_looping(domain::TriggerMode mode) noexcept {
  return mode == domain::TriggerMode::loop_gate ||
         mode == domain::TriggerMode::loop_toggle;
}

bool valid_material(PreparedSampleMaterialView material) noexcept {
  return material.interleaved != nullptr && material.frame_count != 0 &&
         (material.channels == 1 || material.channels == 2);
}

constexpr float kRealtimeRampScale =
    1.0F / static_cast<float>(kRealtimeRampFrames);

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
  });
}

void RealtimeEngine::publish_transport_decision() noexcept {
  transport_decision_.publish({rendered_frames_, pattern_origin_frame_});
}

std::uint64_t RealtimeEngine::pattern_token_generation(
    std::uint32_t token) const noexcept {
  // Control only: this thread alone can reclaim or reuse the immutable payload.
  const auto slot = token & ~kPatternTokenClaimedMask;
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
  release_voice_bank(voice);
  release_voice_pattern(voice);
  cancelled_voices_ += 1;
  active_voices_ -= 1;
}

void RealtimeEngine::apply_published_pattern(
    const PatternPublishEntry& publication,
    std::uint64_t runtime_frame) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_audio_observation};
  const auto current =
      current_pattern_slot_.load(std::memory_order_relaxed);
  if (current != kNoPatternSlot) {
    for (auto& voice : voices_) {
      if (voice.active && voice.pattern_slot == current) {
        stop_voice(voice, runtime_frame);
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
  next.state.store(PatternState::current, std::memory_order_release);
  current_pattern_slot_.store(publication.slot, std::memory_order_release);
  pattern_origin_frame_ = runtime_frame;
  observed_current_pattern_generation_ = publication.generation;
  observed_audio_pending_ = {};
  publish_transport_decision();
  pattern_event_index_ = 0;
  audio_pending_pattern_generation_.store(0, std::memory_order_release);
  applied_pattern_publications_ += 1;
}

void RealtimeEngine::start_pattern_voice(
    const PreparedPatternEvent& event,
    std::uint64_t loop_origin_frame) noexcept {
  const auto slot = global_slot(event.slot);
  const auto playback = event.playback;
  if (!valid_material(event.material) ||
      !valid_playback(playback, event.material.frame_count)) {
    audio_invalid_events_ += 1;
    return;
  }
  if (playback.muted) {
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
  voice->slot = slot;
  voice->material = event.material;
  voice->frame_count = event.material.frame_count;
  voice->start_frame = playback.start_frame;
  voice->end_frame = playback.end_frame;
  voice->cursor = playback.start_frame;
  voice->gain = (static_cast<float>(event.velocity) / 127.0F) *
                playback.linear_gain;
  voice->trigger_mode = playback.trigger_mode;
  voice->attack_frames_remaining = kRealtimeRampFrames;
  voice->scheduled_release_frame =
      playback.trigger_mode == domain::TriggerMode::one_shot
          ? 0
          : loop_origin_frame + event.release_frame;
  voice->pattern_voice = true;
  voice->origin = PadControlOrigin::performance_replay;
  voice->pattern_slot = current_pattern_slot_.load(std::memory_order_relaxed);
  voice->active = true;
  ++pattern_slots_[voice->pattern_slot].active_voices;
  started_voices_ += 1;
  active_voices_ += 1;
}

void RealtimeEngine::schedule_pattern_events(
    std::uint64_t runtime_frame) noexcept {
  const auto slot =
      current_pattern_slot_.load(std::memory_order_relaxed);
  if (slot == kNoPatternSlot) {
    return;
  }
  const auto& pattern = *pattern_slots_[slot].pattern;
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
        events[pattern_event_index_], loop_origin_frame);
    ++pattern_event_index_;
  }
}

void RealtimeEngine::stop_voice(
    Voice& voice, std::uint64_t runtime_frame) noexcept {
  if (!voice.active) {
    return;
  }
  if (voice.releasing) {
    // A second stop (stop_all after a gate release, a toggle re-press, or
    // voice stealing) hard-kills the tail. The stopped edge was already
    // published when the release began, so only the physical deactivation
    // remains.
    deactivate_voice(voice);
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
        voice.cursor));
  }
  // The voice keeps rendering a kRealtimeRampFrames tail to avoid a step
  // discontinuity; the logical stop (publication) has already happened.
  voice.releasing = true;
  voice.release_frames_remaining = kRealtimeRampFrames;
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

PatternPublication RealtimeEngine::publish_pattern_view(
    PreparedPatternView&& pattern,
    std::optional<std::uint64_t> requested_activation_frame,
    std::optional<PatternReplacementAuthority> replacement_authority) noexcept {
  return publish_pattern_view_impl(
      std::move(pattern), requested_activation_frame,
      std::move(replacement_authority), PatternPublicationTiming::scheduled);
}

PatternPublication RealtimeEngine::publish_pattern_view_immediate(
    PreparedPatternView&& pattern) noexcept {
  return publish_pattern_view_impl(
      std::move(pattern), std::nullopt, std::nullopt,
      PatternPublicationTiming::immediate);
}

PatternPublication RealtimeEngine::publish_pattern_view_impl(
    PreparedPatternView&& pattern,
    std::optional<std::uint64_t> requested_activation_frame,
    std::optional<PatternReplacementAuthority> replacement_authority,
    PatternPublicationTiming timing) noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
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
    const auto observed_mailbox =
        queued_pattern_generation_.load(std::memory_order_acquire);
    if (observed_mailbox == kPatternTokenClaimedMask) {
      continue;  // Audio claimed an empty Q and will clear it without waiting.
    }
    const auto observed_queued_token =
        (observed_mailbox & kPatternTokenClaimedMask) == 0
            ? observed_mailbox : std::uint32_t{0};
    const auto observed_queued_generation =
        pattern_token_generation(observed_queued_token);
    const auto observed_audio_mailbox =
        audio_pending_pattern_generation_.load(std::memory_order_acquire);
    const auto observed_audio_generation =
        pattern_token_generation(observed_audio_mailbox);
    const auto observed_pending_generation = observed_mailbox != 0
        ? pattern_token_generation(observed_mailbox)
        : observed_audio_generation;
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
                observed_mailbox ||
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
      if (pending->activation_frame >= observed_frame) {
        observed_pending_activation = pending->activation_frame;
      } else if ((observed_mailbox & kPatternTokenClaimedMask) != 0 ||
                 (observed_mailbox == 0 && observed_audio_generation != 0)) {
        const auto bar_frames = pending->pattern->bar_frames();
        const auto elapsed = observed_frame - pending->activation_frame;
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

    const auto current =
        current_pattern_slot_.load(std::memory_order_acquire);
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

    const auto running =
        state_.load(std::memory_order_acquire) == RealtimeState::running;
    std::uint64_t activation_frame = 0;
    if (running) {
      const auto observed_frame =
          transport_decision_.read().rendered_frames;
      activation_frame = observed_frame;
      if (timing == PatternPublicationTiming::immediate) {
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
        const auto origin =
            transport_decision_.read().pattern_origin_frame;
        const auto bar_frames =
            pattern_slots_[current].pattern->bar_frames();
        if (observed_frame >= origin) {
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
    slot->state.store(PatternState::pending, std::memory_order_release);
    if (!running) {
      apply_published_pattern(publication, 0);
    } else {
      auto expected_generation = observed_queued_token;
      if (!queued_pattern_generation_.compare_exchange_strong(
              expected_generation,
              static_cast<std::uint32_t>(publication.slot) + 1,
              std::memory_order_seq_cst,
              std::memory_order_seq_cst)) {
        pattern = std::move(*slot->pattern);
        slot->pattern.reset();
        slot->generation = 0;
        slot->activation_frame = 0;
        slot->state.store(PatternState::empty, std::memory_order_release);
        continue;
      }
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
    return PatternPublication{
        PatternPublishResult::accepted,
        publication.generation,
        activation_frame,
    };
  }
}

bool RealtimeEngine::cancel_pattern_publication(
    const PatternReplacementAuthority& authority) noexcept {
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

  auto expected = static_cast<std::uint32_t>(
      std::distance(pattern_slots_.begin(), pending)) + 1;
  if (!queued_pattern_generation_.compare_exchange_strong(
          expected,
          0,
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
  if (queued_pattern_generation_.load(std::memory_order_acquire) != 0 ||
      audio_pending_pattern_generation_.load(std::memory_order_acquire) != 0) {
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
  publish_transport_decision();
  pattern_event_index_ = 0;
  return foundation::Result<void>::success();
}

std::size_t RealtimeEngine::reclaim_retired_patterns() noexcept {
  const PublishOnReturn publish{*this, &RealtimeEngine::publish_control_observation};
  std::size_t reclaimed = 0;
  for (auto& slot : pattern_slots_) {
    if (slot.state.load(std::memory_order_acquire) !=
        PatternState::reclaimable) {
      continue;
    }
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

std::optional<foundation::PatternId>
RealtimeEngine::pending_pattern_id() const {
  const auto mailbox =
      queued_pattern_generation_.load(std::memory_order_acquire);
  const auto generation =
      mailbox != 0
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
  const auto start_epoch = start_epoch_;
  if (start_epoch == std::numeric_limits<std::uint64_t>::max()) {
    return invalid_argument(
        "realtime engine start epoch is exhausted; restart the host process "
        "with a new engine instance");
  }

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
  std::fill(voices_.begin(), voices_.end(), Voice{});
  preview_mask_ = 0;
  enqueued_events_ = 0;
  queued_host_input_events_.store(0, std::memory_order_relaxed);
  dequeued_events_ = 0;
  cancelled_events_ = 0;
  started_voices_ = 0;
  completed_voices_ = 0;
  active_voices_ = 0;
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
  start_epoch_ = start_epoch + 1;
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
  if (!queue_.try_push(event)) {
    if (!replay) {
      queued_host_input_events_.fetch_sub(1, std::memory_order_relaxed);
    }
    queue_drops_ += 1;
    return EnqueueResult::queue_full;
  }

  enqueued_events_ += 1;
  return EnqueueResult::accepted;
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
          MasterFxControlKind::gesture, gesture, 0})) {
    queued_fx_gestures_.fetch_sub(1, std::memory_order_relaxed);
    fx_queue_drops_ += 1;
    return FxEnqueueResult::queue_full;
  }
  enqueued_fx_gestures_ += 1;
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
          MasterFxControlKind::tempo, {}, bpm})) {
    fx_queue_drops_ += 1;
    return FxEnqueueResult::queue_full;
  }
  enqueued_tempo_updates_ += 1;
  return FxEnqueueResult::accepted;
}

void RealtimeEngine::render(
    float* left, float* right, std::uint32_t frames) noexcept {
  std::fill_n(left, frames, 0.0F);
  std::fill_n(right, frames, 0.0F);
  callback_count_ += 1;
  const auto absolute_start_frame = rendered_frames_;
  rendered_frames_ += frames;
  publish_transport_decision();
  max_callback_frames_ = std::max(max_callback_frames_, frames);

  MasterFxControlEvent fx_control{};
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
    } else {
      static_cast<void>(master_fx_.set_bpm(fx_control.bpm));
      current_master_fx_bpm_.store(
          fx_control.bpm, std::memory_order_relaxed);
      applied_tempo_updates_ += 1;
    }
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
    pending_publications_.fetch_sub(1, std::memory_order_release);
  }
  // Before the control events below, so an audition published and started in
  // the same callback is audible in that callback rather than the next.
  std::uint8_t published_audition = 0;
  while (audition_publish_queue_.try_pop(published_audition)) {
    apply_published_audition(published_audition);
  }
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
    const auto token = queued_pattern_generation_.fetch_or(
        kPatternTokenClaimedMask, std::memory_order_seq_cst);
    if (token != 0) {
      const auto slot_index = static_cast<std::uint8_t>(token - 1);
      const auto& claimed = pattern_slots_[slot_index];
      const PatternPublishEntry publication{
          slot_index, claimed.generation, claimed.activation_frame};
      audio_pending_pattern_ = publication;
      observed_claimed_through_ = publication.generation;
      observed_audio_pending_ = {
          publication.generation, publication.activation_frame};
      audio_pending_pattern_generation_.store(token, std::memory_order_release);
    }
    // Includes claimed-empty. A/L must be established before releasing Q.
    queued_pattern_generation_.store(0, std::memory_order_seq_cst);
    pattern_claim_closed_.store(0, std::memory_order_seq_cst);
  }
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_pattern_claim_hook();
#endif

  PadControlEvent event{};
  for (std::size_t processed = 0;
       processed < kRealtimeQueueCapacity && queue_.try_pop(event);
       ++processed) {
    dequeued_events_ += 1;
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
      for (auto& voice : voices_) {
        if (voice.active && voice.slot == event.slot &&
            !is_audition_bank_slot(voice.bank_slot) &&
            voice.origin == PadControlOrigin::host_input &&
            (voice.trigger_mode == domain::TriggerMode::gate ||
             voice.trigger_mode == domain::TriggerMode::loop_gate)) {
          stop_voice(voice, absolute_start_frame);
        }
      }
      continue;
    }
    if (event.kind == PadControlKind::audition_stop) {
      for (auto& voice : voices_) {
        if (voice.active && is_audition_bank_slot(voice.bank_slot)) {
          stop_voice(voice, absolute_start_frame);
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
          stop_voice(voice, absolute_start_frame);
        }
      }
      continue;
    }

    bool stopped_toggle = false;
    if (!replay) {
      for (auto& candidate : voices_) {
        if (candidate.active && candidate.slot == event.slot &&
            candidate.origin == PadControlOrigin::host_input &&
            candidate.trigger_mode == domain::TriggerMode::loop_toggle) {
          stop_voice(candidate, absolute_start_frame);
          stopped_toggle = true;
        }
      }
    }
    if (stopped_toggle) {
      continue;
    }

    // An audition sources its bytes from the reserved audition Bank, never from
    // `current_sample`, which always reads `bank_slots_[current_bank_slot_]`.
    // This branch is the whole reason reserving a slot makes a Set audible:
    // holding a Bank the voice-start path never reads would be silent.
    const auto audition = event.kind == PadControlKind::audition_start;
    std::uint8_t audition_slot = kNoAuditionSlot;
    if (audition) {
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
    if (!valid_playback(playback, sample.frame_count)) {
      audio_invalid_events_ += 1;
      continue;
    }
    if (playback.muted) {
      continue;
    }
    if (!replay && voice_state_stream_state_.load(std::memory_order_relaxed) ==
        RuntimeVoiceStateStreamState::corrupted) {
      voice_drops_ += 1;
      continue;
    }
    auto voice = std::find_if(
        voices_.begin(), voices_.end(), [](const Voice& candidate) {
          return !candidate.active;
        });
    if (voice == voices_.end()) {
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
    voice->attack_frames_remaining = kRealtimeRampFrames;
    voice->scheduled_release_frame =
        replay && playback.trigger_mode != domain::TriggerMode::one_shot
            ? absolute_start_frame + event.duration_frames
            : 0;
    voice->origin = event.origin;
    if (!replay && !audition && !publish_voice_state(
            *voice,
            RuntimeVoiceState::started,
            absolute_start_frame,
            playback.start_frame)) {
      *voice = Voice{};
      voice_drops_ += 1;
      continue;
    }
    voice->active = true;
    if (auto* const owner = bank_slot_for(bank_slot); owner != nullptr) {
      ++owner->active_voices;
    }
    started_voices_ += 1;
    active_voices_ += 1;
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
    }
    for (auto& voice : voices_) {
      if (voice.active && !voice.releasing &&
          voice.scheduled_release_frame != 0 &&
          runtime_frame >= voice.scheduled_release_frame) {
        stop_voice(voice, runtime_frame);
      }
    }
    schedule_pattern_events(runtime_frame);

    for (auto& voice : voices_) {
      if (!voice.active) {
        continue;
      }
      // F6 amplitude ramps: attack from the per-voice counter (a looping
      // voice attacks only on its initial trigger), a stateless boundary
      // fade over the last kRealtimeRampFrames before end_frame for
      // non-looping voices, and the stop_voice release tail. Each component
      // is skipped at full scale so unramped output stays bit-identical.
      float ramp = 1.0F;
      if (voice.attack_frames_remaining != 0) {
        ramp *= static_cast<float>(
                    kRealtimeRampFrames - voice.attack_frames_remaining) *
                kRealtimeRampScale;
        --voice.attack_frames_remaining;
      }
      if (!is_looping(voice.trigger_mode)) {
        const auto boundary_remaining = voice.end_frame - voice.cursor;
        if (boundary_remaining < kRealtimeRampFrames) {
          ramp *=
              static_cast<float>(boundary_remaining) * kRealtimeRampScale;
        }
      }
      if (voice.releasing &&
          voice.release_frames_remaining < kRealtimeRampFrames) {
        ramp *=
            static_cast<float>(voice.release_frames_remaining) *
            kRealtimeRampScale;
      }
      const auto sample = voice.material.interleaved != nullptr
                              ? prepared_material_sample(
                                    voice.material, voice.cursor)
                              : voice.samples[voice.cursor];
      const auto value = sample * voice.gain * ramp;
      left[frame] += value;
      right[frame] += value;
      ++voice.cursor;
      if (voice.releasing &&
          --voice.release_frames_remaining == 0) {
        // The release tail ends at exact zero gain; deactivate immediately
        // so no denormal residue lingers.
        deactivate_voice(voice);
        continue;
      }
      if (voice.cursor != voice.end_frame) {
        continue;
      }
      if (is_looping(voice.trigger_mode)) {
        voice.cursor = voice.start_frame;
        continue;
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
        static_cast<void>(publish_voice_state(
            voice,
            RuntimeVoiceState::completed,
            runtime_frame + 1,
            voice.end_frame));
      }
      voice.active = false;
      release_voice_bank(voice);
      release_voice_pattern(voice);
      completed_voices_ += 1;
      active_voices_ -= 1;
      continue;
    }
    left[frame] = std::clamp(left[frame], -1.0F, 1.0F);
    right[frame] = std::clamp(right[frame], -1.0F, 1.0F);
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
      queue_.size_approx(),
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
      c.canceled_pattern_publications_,
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
  };
}

}  // namespace lmdj::audio
