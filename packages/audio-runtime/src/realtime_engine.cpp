#include <lmdj/audio/realtime_engine.hpp>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <iterator>
#include <limits>
#include <string>
#include <utility>

#include "pattern_generation.hpp"
#include "testing_hooks.hpp"

namespace lmdj::audio {
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
namespace testing {
namespace {

std::atomic<PatternClaimHook*> pattern_claim_hook{nullptr};
std::atomic<PatternClaimHook*> pattern_apply_hook{nullptr};

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

}  // namespace testing
#endif
namespace {

static_assert(std::atomic<std::uint64_t>::is_always_lock_free);
static_assert(std::atomic<std::uint8_t>::is_always_lock_free);

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

bool valid_control_kind(PadControlKind kind) noexcept {
  switch (kind) {
    case PadControlKind::press:
    case PadControlKind::release:
    case PadControlKind::stop_slot:
    case PadControlKind::stop_all:
    case PadControlKind::preview_set:
    case PadControlKind::preview_clear:
      return true;
  }
  return false;
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

constexpr float kRealtimeRampScale =
    1.0F / static_cast<float>(kRealtimeRampFrames);

std::uint8_t global_slot(domain::PadSlotId slot) noexcept {
  return static_cast<std::uint8_t>(slot.bank * 16U + slot.pad);
}

}  // namespace

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
  retire_current_bank();
  current_bank_slot_.store(kLegacyBankSlot, std::memory_order_relaxed);
  current_bank_generation_.store(0, std::memory_order_relaxed);
  availability_mask_.store(
      legacy_availability_mask(), std::memory_order_release);
  preview_mask_ = 0;
}

void RealtimeEngine::apply_published_bank(std::uint8_t slot_index) noexcept {
  retire_current_bank();
  auto& slot = bank_slots_[slot_index];
  slot.state.store(BankState::current, std::memory_order_release);
  current_bank_slot_.store(slot_index, std::memory_order_relaxed);
  availability_mask_.store(
      slot.bank->availability_mask(), std::memory_order_release);
  current_bank_generation_.store(
      slot.generation, std::memory_order_relaxed);
  preview_mask_ = 0;
  applied_publications_.fetch_add(1, std::memory_order_relaxed);
}

void RealtimeEngine::release_voice_bank(Voice& voice) noexcept {
  if (voice.bank_slot == kLegacyBankSlot) {
    return;
  }
  auto& slot = bank_slots_[voice.bank_slot];
  --slot.active_voices;
  if (slot.active_voices == 0 &&
      slot.state.load(std::memory_order_relaxed) == BankState::retiring) {
    slot.state.store(BankState::reclaimable, std::memory_order_release);
  }
}

const std::vector<float>& RealtimeEngine::current_sample(
    std::uint8_t slot) const noexcept {
  const auto bank_slot = current_bank_slot_.load(std::memory_order_relaxed);
  return bank_slot == kLegacyBankSlot
             ? samples_[slot]
             : bank_slots_[bank_slot].bank->sample(slot);
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
    published_voice_states_.fetch_add(1, std::memory_order_relaxed);
    return true;
  }

  auto expected = RuntimeVoiceStateStreamState::healthy;
  if (voice_state_stream_state_.compare_exchange_strong(
          expected,
          RuntimeVoiceStateStreamState::corrupted,
          std::memory_order_release,
          std::memory_order_relaxed)) {
    voice_state_drops_.fetch_add(1, std::memory_order_relaxed);
  }
  return false;
}

void RealtimeEngine::deactivate_voice(Voice& voice) noexcept {
  voice.active = false;
  release_voice_bank(voice);
  cancelled_voices_.fetch_add(1, std::memory_order_relaxed);
  active_voices_.fetch_sub(1, std::memory_order_relaxed);
}

void RealtimeEngine::apply_published_pattern(
    const PatternPublishEntry& publication,
    std::uint64_t runtime_frame) noexcept {
  const auto current =
      current_pattern_slot_.load(std::memory_order_relaxed);
  if (current != kNoPatternSlot) {
    for (auto& voice : voices_) {
      if (voice.active && voice.pattern_voice) {
        stop_voice(voice, runtime_frame);
      }
    }
    pattern_slots_[current].state.store(
        PatternState::reclaimable, std::memory_order_release);
  }
  auto& next = pattern_slots_[publication.slot];
  next.state.store(PatternState::current, std::memory_order_release);
  current_pattern_slot_.store(publication.slot, std::memory_order_release);
  pattern_origin_frame_.store(runtime_frame, std::memory_order_release);
  pattern_event_index_ = 0;
  audio_pending_pattern_generation_.store(0, std::memory_order_release);
  applied_pattern_publications_.fetch_add(1, std::memory_order_relaxed);
}

void RealtimeEngine::start_pattern_voice(
    const PreparedPatternEvent& event,
    std::uint64_t loop_origin_frame) noexcept {
  const auto slot = global_slot(event.slot);
  if ((availability_mask_.load(std::memory_order_relaxed) &
       (std::uint64_t{1} << slot)) == 0) {
    invalid_events_.fetch_add(1, std::memory_order_relaxed);
    return;
  }
  const auto& sample = current_sample(slot);
  const auto playback = published_playback(slot);
  if (!valid_playback(playback, sample.size())) {
    invalid_events_.fetch_add(1, std::memory_order_relaxed);
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
    voice_drops_.fetch_add(1, std::memory_order_relaxed);
    return;
  }
  const auto bank_slot =
      current_bank_slot_.load(std::memory_order_relaxed);
  *voice = Voice{
      0,
      slot,
      sample.data(),
      sample.size(),
      playback.start_frame,
      playback.end_frame,
      playback.start_frame,
      (static_cast<float>(event.velocity) / 127.0F) *
          playback.linear_gain,
      playback.trigger_mode,
      false,
      bank_slot,
      kRealtimeRampFrames,
      false,
      0,
      playback.trigger_mode == domain::TriggerMode::one_shot
          ? 0
          : loop_origin_frame + event.release_frame,
      true,
  };
  voice->active = true;
  if (bank_slot != kLegacyBankSlot) {
    ++bank_slots_[bank_slot].active_voices;
  }
  started_voices_.fetch_add(1, std::memory_order_relaxed);
  active_voices_.fetch_add(1, std::memory_order_relaxed);
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
      pattern_origin_frame_.load(std::memory_order_relaxed);
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
  if (!voice.pattern_voice) {
    static_cast<void>(publish_voice_state(
        voice,
        RuntimeVoiceState::stopped,
        runtime_frame,
        static_cast<std::uint32_t>(voice.cursor)));
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
      capture_origin_frame_.load(std::memory_order_relaxed);
  const auto offset = absolute_start_frame - origin;
  if (absolute_start_frame < origin ||
      offset > std::numeric_limits<std::uint32_t>::max() ||
      !capture_ring_.try_push(CapturedTriggerEvent{
          event.sequence,
          event.slot,
          event.velocity,
          static_cast<std::uint32_t>(offset),
      })) {
    capture_drops_.fetch_add(1, std::memory_order_relaxed);
    capture_state_.store(CaptureState::corrupted,
                         std::memory_order_release);
    return;
  }
  captured_events_.fetch_add(1, std::memory_order_relaxed);
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
  if (mono_pcm.size() > std::numeric_limits<std::uint32_t>::max()) {
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

PublishResult RealtimeEngine::publish_sample_bank(
    PreparedSampleBank&& bank) noexcept {
  const auto running =
      state_.load(std::memory_order_acquire) == RealtimeState::running;
  if (running && queue_.size_approx() != 0) {
    return PublishResult::events_pending;
  }

  auto slot = std::find_if(
      bank_slots_.begin(), bank_slots_.end(), [](const BankSlot& candidate) {
        return candidate.state.load(std::memory_order_acquire) ==
               BankState::empty;
      });
  if (slot == bank_slots_.end()) {
    bank_slot_rejections_.fetch_add(1, std::memory_order_relaxed);
    return PublishResult::bank_slots_full;
  }

  const auto slot_index = static_cast<std::uint8_t>(
      std::distance(bank_slots_.begin(), slot));
  slot->bank.emplace(std::move(bank));
  slot->active_voices = 0;
  slot->generation = next_bank_generation_++;

  if (!running) {
    apply_published_bank(slot_index);
    accepted_publications_.fetch_add(1, std::memory_order_relaxed);
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
    publish_queue_drops_.fetch_add(1, std::memory_order_relaxed);
    return PublishResult::publish_queue_full;
  }
  accepted_publications_.fetch_add(1, std::memory_order_relaxed);
  return PublishResult::accepted;
}

PatternPublication RealtimeEngine::publish_pattern_view(
    PreparedPatternView&& pattern,
    std::optional<std::uint64_t> requested_activation_frame,
    std::optional<PatternReplacementAuthority> replacement_authority) noexcept {
  for (;;) {
    const auto observed_mailbox =
        queued_pattern_generation_.load(std::memory_order_acquire);
    const auto observed_queued_generation =
        (observed_mailbox & detail::kPatternClaimedMask) == 0
            ? observed_mailbox
            : 0;
    const auto observed_audio_mailbox =
        audio_pending_pattern_generation_.load(std::memory_order_acquire);
    const auto observed_audio_generation =
        detail::pattern_mailbox_generation(observed_audio_mailbox);
    const auto observed_pending_generation = observed_mailbox != 0
        ? detail::pattern_mailbox_generation(observed_mailbox)
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
        pattern_publication_rejections_.fetch_add(
            1, std::memory_order_relaxed);
        return PatternPublication{
            PatternPublishResult::publication_pending, 0, 0};
      }
      authorized_replacement = replacement_authority.has_value() &&
          replacement_authority->generation == observed_pending_generation &&
          replacement_authority->pattern_id == pending->pattern->pattern_id() &&
          replacement_authority->activation_frame == pending->activation_frame;
      const auto observed_frame =
          rendered_frames_.load(std::memory_order_acquire);
      if (pending->activation_frame >= observed_frame) {
        observed_pending_activation = pending->activation_frame;
      } else if ((observed_mailbox & detail::kPatternClaimedMask) != 0 ||
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
        pattern_publication_rejections_.fetch_add(
            1, std::memory_order_relaxed);
        return PatternPublication{
            PatternPublishResult::publication_pending, 0, 0};
      }
    }

    const auto current =
        current_pattern_slot_.load(std::memory_order_acquire);
    if (current != kNoPatternSlot &&
        pattern_slots_[current].pattern->project_id() != pattern.project_id()) {
      pattern_publication_rejections_.fetch_add(1, std::memory_order_relaxed);
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
      pattern_publication_rejections_.fetch_add(1, std::memory_order_relaxed);
      return PatternPublication{PatternPublishResult::pattern_slots_full, 0, 0};
    }

    const auto slot_index = static_cast<std::uint8_t>(
        std::distance(pattern_slots_.begin(), slot));
    const auto generation =
        detail::take_pattern_generation(next_pattern_generation_);
    if (!generation.has_value()) {
      pattern_publication_rejections_.fetch_add(
          1, std::memory_order_relaxed);
      return PatternPublication{
          PatternPublishResult::generation_exhausted, 0, 0};
    }
    slot->pattern.emplace(std::move(pattern));
    slot->generation = *generation;

    const auto running =
        state_.load(std::memory_order_acquire) == RealtimeState::running;
    std::uint64_t activation_frame = 0;
    if (running) {
      const auto observed_frame =
          rendered_frames_.load(std::memory_order_acquire);
      activation_frame = observed_frame;
      if (authorized_replacement && requested_activation_frame.has_value()) {
        if (*requested_activation_frame < observed_frame) {
          slot->pattern.reset();
          slot->generation = 0;
          pattern_publication_rejections_.fetch_add(
              1, std::memory_order_relaxed);
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
          pattern_publication_rejections_.fetch_add(
              1, std::memory_order_relaxed);
          return PatternPublication{
              PatternPublishResult::publish_queue_full, 0, 0};
        }
        activation_frame = *requested_activation_frame;
      } else if (current != kNoPatternSlot) {
        const auto origin =
            pattern_origin_frame_.load(std::memory_order_acquire);
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
            pattern_publication_rejections_.fetch_add(
                1, std::memory_order_relaxed);
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
      auto expected_generation = observed_queued_generation;
      if (!queued_pattern_generation_.compare_exchange_strong(
              expected_generation,
              publication.generation,
              std::memory_order_acq_rel,
              std::memory_order_acquire)) {
        pattern = std::move(*slot->pattern);
        slot->pattern.reset();
        slot->generation = 0;
        slot->activation_frame = 0;
        slot->state.store(PatternState::empty, std::memory_order_release);
        continue;
      }
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
          superseded_pattern_publications_.fetch_add(
              1, std::memory_order_relaxed);
        }
      }
    }
    accepted_pattern_publications_.fetch_add(1, std::memory_order_relaxed);
    return PatternPublication{
        PatternPublishResult::accepted,
        publication.generation,
        activation_frame,
    };
  }
}

bool RealtimeEngine::cancel_pattern_publication(
    const PatternReplacementAuthority& authority) noexcept {
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

  auto expected = authority.generation;
  if (queued_pattern_generation_.compare_exchange_strong(
          expected,
          0,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    pending->state.store(PatternState::reclaimable, std::memory_order_release);
    canceled_pattern_publications_.fetch_add(1, std::memory_order_relaxed);
    return true;
  }

  expected = authority.generation;
  if (audio_pending_pattern_generation_.compare_exchange_strong(
          expected,
          0,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    canceled_pattern_publications_.fetch_add(1, std::memory_order_relaxed);
    return true;
  }
  return false;
}

foundation::Result<void> RealtimeEngine::clear_pattern_view() noexcept {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped) {
    return invalid_argument(
        "realtime Pattern may only be cleared while stopped");
  }
  if (queued_pattern_generation_.load(std::memory_order_acquire) != 0 ||
      audio_pending_pattern_generation_.load(std::memory_order_acquire) != 0) {
    return invalid_argument("realtime Pattern publication is pending");
  }
  const auto current =
      current_pattern_slot_.exchange(kNoPatternSlot, std::memory_order_acq_rel);
  if (current != kNoPatternSlot) {
    pattern_slots_[current].state.store(
        PatternState::reclaimable, std::memory_order_release);
  }
  pattern_origin_frame_.store(0, std::memory_order_release);
  pattern_event_index_ = 0;
  return foundation::Result<void>::success();
}

std::size_t RealtimeEngine::reclaim_retired_patterns() noexcept {
  std::size_t reclaimed = 0;
  for (auto& slot : pattern_slots_) {
    if (slot.state.load(std::memory_order_acquire) !=
        PatternState::reclaimable) {
      continue;
    }
    slot.pattern.reset();
    slot.generation = 0;
    slot.activation_frame = 0;
    slot.state.store(PatternState::empty, std::memory_order_release);
    ++reclaimed;
  }
  reclaimed_patterns_.fetch_add(reclaimed, std::memory_order_relaxed);
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
          ? detail::pattern_mailbox_generation(mailbox)
          : detail::pattern_mailbox_generation(
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
  return pattern_origin_frame_.load(std::memory_order_acquire);
}

ReclaimedBankTelemetry
RealtimeEngine::reclaim_retired_bank_telemetry() noexcept {
  ReclaimedBankTelemetry reclaimed{};
  for (auto& slot : bank_slots_) {
    if (slot.state.load(std::memory_order_acquire) !=
        BankState::reclaimable) {
      continue;
    }
    reclaimed.decoded_pcm_bytes += slot.bank->decoded_pcm_bytes();
    slot.bank.reset();
    slot.generation = 0;
    slot.state.store(BankState::empty, std::memory_order_release);
    ++reclaimed.count;
  }
  reclaimed_banks_.fetch_add(reclaimed.count, std::memory_order_relaxed);
  return reclaimed;
}

std::size_t RealtimeEngine::reclaim_retired_banks() noexcept {
  return reclaim_retired_bank_telemetry().count;
}

foundation::Result<void> RealtimeEngine::arm_capture() noexcept {
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    return invalid_argument(
        "realtime capture may only be armed while running");
  }
  auto expected = CaptureState::idle;
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
  std::size_t drained = 0;
  while (drained < output.size() &&
         capture_ring_.try_pop(output[drained])) {
    ++drained;
  }
  drained_events_.fetch_add(drained, std::memory_order_relaxed);
  return drained;
}

std::size_t RealtimeEngine::drain_trigger_outcomes(
    std::span<RuntimeTriggerOutcomeEvent> output) noexcept {
  std::size_t drained = 0;
  while (drained < output.size() &&
         trigger_outcome_ring_.try_pop(output[drained])) {
    ++drained;
  }
  drained_outcomes_.fetch_add(drained, std::memory_order_relaxed);
  return drained;
}

std::size_t RealtimeEngine::drain_voice_states(
    std::span<RuntimeVoiceStateEvent> output) noexcept {
  const auto drained = detail::drain_voice_states_fail_closed(
      voice_state_stream_state_,
      output,
      [this](RuntimeVoiceStateEvent& event) noexcept {
        return voice_state_ring_.try_pop(event);
      });
  drained_voice_states_.fetch_add(drained, std::memory_order_relaxed);
  return drained;
}

foundation::Result<void> RealtimeEngine::start() {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped) {
    return invalid_argument("realtime engine is already running");
  }

  queue_.clear_quiescent();
  publish_queue_.clear_quiescent();
  audio_pending_pattern_.reset();
  capture_ring_.clear_quiescent();
  trigger_outcome_ring_.clear_quiescent();
  voice_state_ring_.clear_quiescent();
  pending_publications_.store(0, std::memory_order_relaxed);
  queued_pattern_generation_.store(0, std::memory_order_relaxed);
  audio_pending_pattern_generation_.store(0, std::memory_order_relaxed);
  pattern_origin_frame_.store(0, std::memory_order_relaxed);
  pattern_event_index_ = 0;
  std::fill(voices_.begin(), voices_.end(), Voice{});
  preview_mask_ = 0;
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
  capture_state_.store(CaptureState::idle, std::memory_order_relaxed);
  captured_events_.store(0, std::memory_order_relaxed);
  drained_events_.store(0, std::memory_order_relaxed);
  capture_drops_.store(0, std::memory_order_relaxed);
  capture_origin_frame_.store(0, std::memory_order_relaxed);
  published_outcomes_.store(0, std::memory_order_relaxed);
  drained_outcomes_.store(0, std::memory_order_relaxed);
  runtime_outcome_drops_.store(0, std::memory_order_relaxed);
  voice_state_stream_state_.store(
      RuntimeVoiceStateStreamState::healthy, std::memory_order_relaxed);
  published_voice_states_.store(0, std::memory_order_relaxed);
  drained_voice_states_.store(0, std::memory_order_relaxed);
  voice_state_drops_.store(0, std::memory_order_relaxed);
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
      release_voice_bank(voice);
    }
    voice = Voice{};
  }
  cancelled_voices_.fetch_add(active, std::memory_order_relaxed);
  active_voices_.store(0, std::memory_order_relaxed);
  preview_mask_ = 0;

  std::uint8_t pending_slot = 0;
  while (publish_queue_.try_pop(pending_slot)) {
    bank_slots_[pending_slot].state.store(
        BankState::reclaimable, std::memory_order_release);
    pending_publications_.fetch_sub(1, std::memory_order_relaxed);
  }
  if (audio_pending_pattern_.has_value()) {
    pattern_slots_[audio_pending_pattern_->slot].state.store(
        PatternState::reclaimable, std::memory_order_release);
    audio_pending_pattern_.reset();
  }
  const auto queued_generation =
      queued_pattern_generation_.exchange(0, std::memory_order_acq_rel);
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
  }
  audio_pending_pattern_generation_.store(0, std::memory_order_release);
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
      (availability_mask_.load(std::memory_order_acquire) &
       (std::uint64_t{1} << event.slot)) != 0) {
    control.playback = published_playback(event.slot);
  }
  return enqueue_control(control);
}

EnqueueResult RealtimeEngine::enqueue_control(PadControlEvent event) noexcept {
  if (state_.load(std::memory_order_acquire) != RealtimeState::running) {
    stopped_rejections_.fetch_add(1, std::memory_order_relaxed);
    return EnqueueResult::not_running;
  }
  if (!valid_control_kind(event.kind)) {
    invalid_events_.fetch_add(1, std::memory_order_relaxed);
    return EnqueueResult::invalid_velocity;
  }
  if (event.kind != PadControlKind::stop_all &&
      event.slot >= kRealtimeSampleSlots) {
    invalid_events_.fetch_add(1, std::memory_order_relaxed);
    return EnqueueResult::invalid_slot;
  }
  if (event.kind == PadControlKind::press &&
      (event.velocity == 0 || event.velocity > 127)) {
    invalid_events_.fetch_add(1, std::memory_order_relaxed);
    return EnqueueResult::invalid_velocity;
  }
  if (event.kind == PadControlKind::press ||
      event.kind == PadControlKind::preview_set) {
    if (pending_publications_.load(std::memory_order_acquire) != 0) {
      return EnqueueResult::bank_transition;
    }
    if ((availability_mask_.load(std::memory_order_acquire) &
         (std::uint64_t{1} << event.slot)) == 0) {
      invalid_events_.fetch_add(1, std::memory_order_relaxed);
      return EnqueueResult::sample_unavailable;
    }
  }
  if (event.kind == PadControlKind::preview_set &&
      !valid_playback(event.playback, current_sample(event.slot).size())) {
    invalid_events_.fetch_add(1, std::memory_order_relaxed);
    return EnqueueResult::invalid_velocity;
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
  const auto absolute_start_frame =
      rendered_frames_.fetch_add(frames, std::memory_order_relaxed);
  update_max(max_callback_frames_, frames);

  auto capture_state = CaptureState::arm_pending;
  if (capture_state_.load(std::memory_order_acquire) ==
      CaptureState::arm_pending) {
    capture_origin_frame_.store(
        absolute_start_frame, std::memory_order_relaxed);
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
  auto mailbox = queued_pattern_generation_.load(std::memory_order_acquire);
  std::uint64_t claimed_pattern_generation = 0;
  while (mailbox != 0 && (mailbox & detail::kPatternClaimedMask) == 0) {
    const auto claimed_mailbox = mailbox | detail::kPatternClaimedMask;
    if (queued_pattern_generation_.compare_exchange_weak(
            mailbox,
            claimed_mailbox,
            std::memory_order_acq_rel,
            std::memory_order_acquire)) {
      claimed_pattern_generation = mailbox;
      break;
    }
  }
  if (claimed_pattern_generation != 0) {
    const auto claimed = std::find_if(
        pattern_slots_.begin(),
        pattern_slots_.end(),
        [claimed_pattern_generation](const PatternSlot& candidate) {
          return candidate.state.load(std::memory_order_acquire) ==
                     PatternState::pending &&
                 candidate.generation == claimed_pattern_generation;
        });
    if (claimed != pattern_slots_.end()) {
      const PatternPublishEntry publication{
          static_cast<std::uint8_t>(
              std::distance(pattern_slots_.begin(), claimed)),
          claimed->generation,
          claimed->activation_frame};
      if (audio_pending_pattern_.has_value()) {
        auto superseded_generation = audio_pending_pattern_->generation;
        const auto claimed_superseded_generation =
            superseded_generation | detail::kPatternClaimedMask;
        if (audio_pending_pattern_generation_.compare_exchange_strong(
                superseded_generation,
                claimed_superseded_generation,
                std::memory_order_acq_rel,
                std::memory_order_acquire)) {
          superseded_pattern_publications_.fetch_add(
              1, std::memory_order_relaxed);
        }
        pattern_slots_[audio_pending_pattern_->slot].state.store(
            PatternState::reclaimable, std::memory_order_release);
      }
      audio_pending_pattern_ = publication;
      audio_pending_pattern_generation_.store(
          publication.generation, std::memory_order_release);
    }
    queued_pattern_generation_.store(0, std::memory_order_release);
  }
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  testing::invoke_pattern_claim_hook();
#endif

  PadControlEvent event{};
  for (std::size_t processed = 0;
       processed < kRealtimeQueueCapacity && queue_.try_pop(event);
       ++processed) {
    dequeued_events_.fetch_add(1, std::memory_order_relaxed);
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
            (voice.trigger_mode == domain::TriggerMode::gate ||
             voice.trigger_mode == domain::TriggerMode::loop_gate)) {
          stop_voice(voice, absolute_start_frame);
        }
      }
      continue;
    }
    if (event.kind == PadControlKind::stop_slot ||
        event.kind == PadControlKind::stop_all) {
      for (auto& voice : voices_) {
        if (voice.active &&
            (event.kind == PadControlKind::stop_all ||
             voice.slot == event.slot)) {
          stop_voice(voice, absolute_start_frame);
        }
      }
      continue;
    }

    bool stopped_toggle = false;
    for (auto& candidate : voices_) {
      if (candidate.active && candidate.slot == event.slot &&
          candidate.trigger_mode == domain::TriggerMode::loop_toggle) {
        stop_voice(candidate, absolute_start_frame);
        stopped_toggle = true;
      }
    }
    if (stopped_toggle) {
      continue;
    }

    const auto& sample = current_sample(event.slot);
    auto playback = event.playback;
    if (is_default_playback_sentinel(playback)) {
      playback = (preview_mask_ & (std::uint64_t{1} << event.slot)) != 0
                     ? previews_[event.slot]
                     : published_playback(event.slot);
    }
    if (!valid_playback(playback, sample.size())) {
      invalid_events_.fetch_add(1, std::memory_order_relaxed);
      continue;
    }
    if (playback.muted) {
      continue;
    }
    if (voice_state_stream_state_.load(std::memory_order_relaxed) ==
        RuntimeVoiceStateStreamState::corrupted) {
      voice_drops_.fetch_add(1, std::memory_order_relaxed);
      continue;
    }
    auto voice = std::find_if(
        voices_.begin(), voices_.end(), [](const Voice& candidate) {
          return !candidate.active;
        });
    if (voice == voices_.end()) {
      voice_drops_.fetch_add(1, std::memory_order_relaxed);
      if (trigger_outcome_ring_.try_push(RuntimeTriggerOutcomeEvent{
              event.sequence,
              RuntimeTriggerOutcome::voice_capacity,
              absolute_start_frame,
          })) {
        published_outcomes_.fetch_add(1, std::memory_order_relaxed);
      } else {
        runtime_outcome_drops_.fetch_add(1, std::memory_order_relaxed);
      }
      continue;
    }
    const auto bank_slot =
        current_bank_slot_.load(std::memory_order_relaxed);
    *voice = Voice{
        event.sequence,
        event.slot,
        sample.data(),
        sample.size(),
        playback.start_frame,
        playback.end_frame,
        playback.start_frame,
        (static_cast<float>(event.velocity) / 127.0F) *
            playback.linear_gain,
        playback.trigger_mode,
        false,
        bank_slot,
        kRealtimeRampFrames,
        false,
        0,
        0,
        false,
    };
    if (!publish_voice_state(
            *voice,
            RuntimeVoiceState::started,
            absolute_start_frame,
            playback.start_frame)) {
      *voice = Voice{};
      voice_drops_.fetch_add(1, std::memory_order_relaxed);
      continue;
    }
    voice->active = true;
    if (bank_slot != kLegacyBankSlot) {
      ++bank_slots_[bank_slot].active_voices;
    }
    started_voices_.fetch_add(1, std::memory_order_relaxed);
    active_voices_.fetch_add(1, std::memory_order_relaxed);
    if (trigger_outcome_ring_.try_push(RuntimeTriggerOutcomeEvent{
            event.sequence,
            RuntimeTriggerOutcome::voice_started,
            absolute_start_frame,
        })) {
      published_outcomes_.fetch_add(1, std::memory_order_relaxed);
    } else {
      runtime_outcome_drops_.fetch_add(1, std::memory_order_relaxed);
    }
    capture_voice_start(event, absolute_start_frame);
  }

  for (std::uint32_t frame = 0; frame < frames; ++frame) {
    const auto runtime_frame = absolute_start_frame + frame;
    if (audio_pending_pattern_.has_value() &&
        runtime_frame >= audio_pending_pattern_->activation_frame) {
      auto expected_generation = audio_pending_pattern_->generation;
      if (audio_pending_pattern_generation_.compare_exchange_strong(
              expected_generation,
              audio_pending_pattern_->generation |
                  detail::kPatternClaimedMask,
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
    }
    for (auto& voice : voices_) {
      if (voice.active && voice.pattern_voice &&
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
      const auto value = voice.samples[voice.cursor] * voice.gain * ramp;
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
      if (!voice.pattern_voice) {
        static_cast<void>(publish_voice_state(
            voice,
            RuntimeVoiceState::completed,
            runtime_frame + 1,
            voice.end_frame));
      }
      voice.active = false;
      release_voice_bank(voice);
      completed_voices_.fetch_add(1, std::memory_order_relaxed);
      active_voices_.fetch_sub(1, std::memory_order_relaxed);
      continue;
    }
    left[frame] = std::clamp(left[frame], -1.0F, 1.0F);
    right[frame] = std::clamp(right[frame], -1.0F, 1.0F);
  }

  capture_state = CaptureState::disarm_pending;
  capture_state_.compare_exchange_strong(
      capture_state,
      CaptureState::idle,
      std::memory_order_release,
      std::memory_order_relaxed);
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

BankTelemetry RealtimeEngine::bank_telemetry() const noexcept {
  return BankTelemetry{
      current_bank_generation_.load(std::memory_order_relaxed),
      pending_publications_.load(std::memory_order_relaxed),
      accepted_publications_.load(std::memory_order_relaxed),
      applied_publications_.load(std::memory_order_relaxed),
      reclaimed_banks_.load(std::memory_order_relaxed),
      bank_slot_rejections_.load(std::memory_order_relaxed),
      publish_queue_drops_.load(std::memory_order_relaxed),
  };
}

PatternTelemetry RealtimeEngine::pattern_telemetry() const noexcept {
  const auto slot =
      current_pattern_slot_.load(std::memory_order_acquire);
  const auto mailbox =
      queued_pattern_generation_.load(std::memory_order_acquire);
  const auto pending_generation =
      mailbox != 0
          ? detail::pattern_mailbox_generation(mailbox)
          : detail::pattern_mailbox_generation(
                audio_pending_pattern_generation_.load(
                    std::memory_order_acquire));
  const auto pending = std::find_if(
      pattern_slots_.begin(),
      pattern_slots_.end(),
      [pending_generation](const PatternSlot& candidate) {
        return pending_generation != 0 &&
               candidate.state.load(std::memory_order_acquire) ==
                   PatternState::pending &&
               candidate.generation == pending_generation;
      });
  return PatternTelemetry{
      slot == kNoPatternSlot ? 0 : pattern_slots_[slot].generation,
      pending_generation,
      pending == pattern_slots_.end() ? 0 : pending->activation_frame,
      accepted_pattern_publications_.load(std::memory_order_relaxed),
      applied_pattern_publications_.load(std::memory_order_relaxed),
      superseded_pattern_publications_.load(std::memory_order_relaxed),
      canceled_pattern_publications_.load(std::memory_order_relaxed),
      reclaimed_patterns_.load(std::memory_order_relaxed),
      pattern_publication_rejections_.load(std::memory_order_relaxed),
  };
}

CaptureTelemetry RealtimeEngine::capture_telemetry() const noexcept {
  return CaptureTelemetry{
      capture_state_.load(std::memory_order_acquire),
      captured_events_.load(std::memory_order_relaxed),
      drained_events_.load(std::memory_order_relaxed),
      capture_drops_.load(std::memory_order_relaxed),
      capture_origin_frame_.load(std::memory_order_relaxed),
  };
}

RuntimeTriggerOutcomeTelemetry
RealtimeEngine::trigger_outcome_telemetry() const noexcept {
  return RuntimeTriggerOutcomeTelemetry{
      published_outcomes_.load(std::memory_order_relaxed),
      drained_outcomes_.load(std::memory_order_relaxed),
      runtime_outcome_drops_.load(std::memory_order_relaxed),
  };
}

RuntimeVoiceStateTelemetry RealtimeEngine::voice_state_telemetry()
    const noexcept {
  return RuntimeVoiceStateTelemetry{
      voice_state_stream_state_.load(std::memory_order_acquire),
      published_voice_states_.load(std::memory_order_relaxed),
      drained_voice_states_.load(std::memory_order_relaxed),
      voice_state_drops_.load(std::memory_order_relaxed),
  };
}

}  // namespace lmdj::audio
