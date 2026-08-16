#include <lmdj/audio/realtime_engine.hpp>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <iterator>
#include <limits>
#include <string>
#include <utility>

namespace lmdj::audio {
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

void RealtimeEngine::stop_voice(
    Voice& voice, std::uint64_t runtime_frame) noexcept {
  if (!voice.active) {
    return;
  }
  static_cast<void>(publish_voice_state(
      voice,
      RuntimeVoiceState::stopped,
      runtime_frame,
      static_cast<std::uint32_t>(voice.cursor)));
  voice.active = false;
  release_voice_bank(voice);
  cancelled_voices_.fetch_add(1, std::memory_order_relaxed);
  active_voices_.fetch_sub(1, std::memory_order_relaxed);
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
  capture_ring_.clear_quiescent();
  trigger_outcome_ring_.clear_quiescent();
  voice_state_ring_.clear_quiescent();
  pending_publications_.store(0, std::memory_order_relaxed);
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

  for (auto& voice : voices_) {
    if (!voice.active) {
      continue;
    }
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
      const auto value = voice.samples[voice.cursor] * voice.gain;
      left[frame] += value;
      right[frame] += value;
      ++voice.cursor;
      if (voice.cursor != voice.end_frame) {
        continue;
      }
      if (is_looping(voice.trigger_mode)) {
        voice.cursor = voice.start_frame;
        continue;
      }
      static_cast<void>(publish_voice_state(
          voice,
          RuntimeVoiceState::completed,
          absolute_start_frame + frame + 1,
          voice.end_frame));
      voice.active = false;
      release_voice_bank(voice);
      completed_voices_.fetch_add(1, std::memory_order_relaxed);
      active_voices_.fetch_sub(1, std::memory_order_relaxed);
      break;
    }
  }

  for (std::uint32_t frame = 0; frame < frames; ++frame) {
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
