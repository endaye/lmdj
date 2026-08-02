#include <lmdj/audio/realtime_engine.hpp>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <iterator>
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

std::size_t RealtimeEngine::reclaim_retired_banks() noexcept {
  std::size_t reclaimed = 0;
  for (auto& slot : bank_slots_) {
    if (slot.state.load(std::memory_order_acquire) !=
        BankState::reclaimable) {
      continue;
    }
    slot.bank.reset();
    slot.generation = 0;
    slot.state.store(BankState::empty, std::memory_order_release);
    ++reclaimed;
  }
  reclaimed_banks_.fetch_add(reclaimed, std::memory_order_relaxed);
  return reclaimed;
}

foundation::Result<void> RealtimeEngine::start() {
  if (state_.load(std::memory_order_acquire) != RealtimeState::stopped) {
    return invalid_argument("realtime engine is already running");
  }

  queue_.clear_quiescent();
  publish_queue_.clear_quiescent();
  pending_publications_.store(0, std::memory_order_relaxed);
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
      release_voice_bank(voice);
    }
    voice = Voice{};
  }
  cancelled_voices_.fetch_add(active, std::memory_order_relaxed);
  active_voices_.store(0, std::memory_order_relaxed);

  std::uint8_t pending_slot = 0;
  while (publish_queue_.try_pop(pending_slot)) {
    bank_slots_[pending_slot].state.store(
        BankState::reclaimable, std::memory_order_release);
    pending_publications_.fetch_sub(1, std::memory_order_relaxed);
  }
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
  if (pending_publications_.load(std::memory_order_acquire) != 0) {
    return EnqueueResult::bank_transition;
  }
  if ((availability_mask_.load(std::memory_order_acquire) &
       (std::uint64_t{1} << event.slot)) == 0) {
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

  std::uint8_t published_slot = 0;
  while (publish_queue_.try_pop(published_slot)) {
    apply_published_bank(published_slot);
    pending_publications_.fetch_sub(1, std::memory_order_release);
  }

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
    const auto bank_slot =
        current_bank_slot_.load(std::memory_order_relaxed);
    const auto& sample = bank_slot == kLegacyBankSlot
                             ? samples_[event.slot]
                             : bank_slots_[bank_slot].bank->sample(event.slot);
    *voice = Voice{
        sample.data(),
        sample.size(),
        0,
        static_cast<float>(event.velocity) / 127.0F,
        true,
        bank_slot,
    };
    if (bank_slot != kLegacyBankSlot) {
      ++bank_slots_[bank_slot].active_voices;
    }
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
      release_voice_bank(voice);
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

}  // namespace lmdj::audio
