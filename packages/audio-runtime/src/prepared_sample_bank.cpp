#include <lmdj/audio/prepared_sample_bank.hpp>

#include <algorithm>
#include <bit>
#include <cmath>
#include <limits>
#include <string>
#include <utility>

#include <lmdj/domain/project.hpp>

namespace lmdj::audio {
namespace {

foundation::Result<void> invalid_argument(std::string message) {
  return foundation::Result<void>::failure(foundation::Error{
      foundation::ErrorCode::invalid_argument,
      std::move(message),
  });
}

foundation::Result<PreparedSampleBank> invalid_bank(std::string message) {
  return foundation::Result<PreparedSampleBank>::failure(foundation::Error{
      foundation::ErrorCode::invalid_argument,
      std::move(message),
  });
}

foundation::Result<PreparedSampleBank> preparation_limit(
    std::string resource,
    std::uint64_t observed,
    std::uint64_t limit) {
  return foundation::Result<PreparedSampleBank>::failure(foundation::Error{
      foundation::ErrorCode::cook_failed,
      "runtime preparation limit exceeded",
      {
          {"resource", std::move(resource)},
          {"observed", observed},
          {"limit", limit},
      },
  });
}

float pcm16_to_float(std::int16_t value) noexcept {
  return value < 0 ? static_cast<float>(value) / 32768.0F
                   : static_cast<float>(value) / 32767.0F;
}

std::uint8_t global_slot(domain::PadSlotId slot) noexcept {
  return static_cast<std::uint8_t>(slot.bank * 16U + slot.pad);
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

}  // namespace

PreparedSampleBank::PreparedSampleBank(foundation::ProjectId project_id,
                                       std::uint64_t project_revision)
    : project_id_(std::move(project_id)), project_revision_(project_revision) {}

foundation::Result<PreparedSampleBank> PreparedSampleBank::from_snapshot(
    const cooker::RuntimeSnapshot& snapshot) {
  constexpr auto unbounded = std::numeric_limits<std::uint64_t>::max();
  return from_snapshot(
      snapshot,
      RuntimePreparationLimits{
          unbounded,
          unbounded,
          unbounded,
          unbounded,
      });
}

foundation::Result<PreparedSampleBank> PreparedSampleBank::from_snapshot(
    const cooker::RuntimeSnapshot& snapshot,
    const RuntimePreparationLimits& limits) {
  if (!domain::is_valid_uuid(snapshot.project_id.value())) {
    return invalid_bank("runtime snapshot Project ID is invalid");
  }
  std::uint8_t previous_slot = 0;
  bool has_previous_slot = false;
  std::uint64_t prospective_bank_bytes = 0;
  for (const auto& pad : snapshot.pads) {
    if (!domain::is_valid_slot(pad.slot) || pad.sample == nullptr) {
      return invalid_bank("runtime snapshot Pad is invalid");
    }
    const auto slot = global_slot(pad.slot);
    if (has_previous_slot && slot <= previous_slot) {
      return invalid_bank("runtime snapshot Pads are not unique and ordered");
    }
    if (!limits.allows_artifact_bytes(pad.artifact.byte_length)) {
      return preparation_limit(
          "artifact_bytes",
          pad.artifact.byte_length,
          limits.maximum_artifact_bytes);
    }
    const auto& source = *pad.sample;
    if (source.sample_rate != 48'000 ||
        (source.channels != 1 && source.channels != 2) ||
        source.interleaved.empty() ||
        source.interleaved.size() % source.channels != 0) {
      return invalid_bank("runtime snapshot PCM shape is invalid");
    }
    const auto frames = static_cast<std::uint64_t>(
        source.interleaved.size() / source.channels);
    if (!valid_playback(pad.playback, static_cast<std::size_t>(frames))) {
      return invalid_bank("runtime snapshot Pad playback is invalid");
    }
    if (!limits.allows_decoded_frames_per_pad(frames)) {
      return preparation_limit(
          "decoded_frames_per_pad",
          frames,
          limits.maximum_decoded_frames_per_pad);
    }
    const auto sample_bytes = checked_mono_float_bytes(frames);
    if (!sample_bytes.has_value()) {
      return invalid_bank("runtime snapshot PCM byte length overflowed");
    }
    const auto total = checked_runtime_byte_sum(
        prospective_bank_bytes, sample_bytes.value());
    if (!total.has_value()) {
      return invalid_bank("runtime snapshot Bank byte length overflowed");
    }
    prospective_bank_bytes = total.value();
    previous_slot = slot;
    has_previous_slot = true;
  }
  if (!limits.allows_prepared_bank_bytes(prospective_bank_bytes)) {
    return preparation_limit(
        "prepared_bank_bytes",
        prospective_bank_bytes,
        limits.maximum_prepared_bank_bytes);
  }
  if (!limits.allows_live_bank_bytes(prospective_bank_bytes)) {
    return preparation_limit(
        "live_bank_bytes",
        prospective_bank_bytes,
        limits.maximum_live_bank_bytes);
  }

  PreparedSampleBank bank(snapshot.project_id, snapshot.project_revision);
  for (const auto& pad : snapshot.pads) {
    const auto slot = global_slot(pad.slot);
    const auto& source = *pad.sample;
    std::vector<float> mono;
    mono.reserve(source.interleaved.size() / source.channels);
    if (source.channels == 1) {
      for (const auto value : source.interleaved) {
        mono.push_back(pcm16_to_float(value));
      }
    } else {
      for (std::size_t index = 0; index < source.interleaved.size();
           index += 2) {
        mono.push_back((pcm16_to_float(source.interleaved.at(index)) +
                        pcm16_to_float(source.interleaved.at(index + 1))) *
                       0.5F);
      }
    }
    const auto assigned = bank.set_sample(slot, mono, pad.playback);
    if (!assigned.has_value()) {
      return invalid_bank(assigned.error().message);
    }
  }
  return foundation::Result<PreparedSampleBank>::success(std::move(bank));
}

PreparedSampleBank PreparedSampleBank::empty(foundation::ProjectId project_id,
                                             std::uint64_t project_revision) {
  return PreparedSampleBank(std::move(project_id), project_revision);
}

foundation::Result<void> PreparedSampleBank::set_sample(
    std::uint8_t slot, std::span<const float> mono_pcm) {
  if (mono_pcm.size() > std::numeric_limits<std::uint32_t>::max()) {
    return invalid_argument("prepared Sample Bank playback is invalid");
  }
  return set_sample(
      slot,
      mono_pcm,
      cooker::ResolvedPlayback{
          0,
          static_cast<std::uint32_t>(mono_pcm.size()),
          domain::TriggerMode::one_shot,
          1.0F,
          false,
      });
}

foundation::Result<void> PreparedSampleBank::set_sample(
    std::uint8_t slot,
    std::span<const float> mono_pcm,
    cooker::ResolvedPlayback playback) {
  if (slot >= samples_.size() || mono_pcm.empty() ||
      (availability_mask_ & (std::uint64_t{1} << slot)) != 0 ||
      !std::all_of(mono_pcm.begin(), mono_pcm.end(),
                   [](float value) { return std::isfinite(value); })) {
    return invalid_argument("prepared Sample Bank input is invalid");
  }
  if (!valid_playback(playback, mono_pcm.size())) {
    return invalid_argument("prepared Sample Bank playback is invalid");
  }
  const auto sample_bytes = checked_mono_float_bytes(mono_pcm.size());
  if (!sample_bytes.has_value()) {
    return invalid_argument("prepared Sample Bank byte length overflowed");
  }
  const auto prospective = checked_runtime_byte_sum(
      decoded_pcm_bytes_, sample_bytes.value());
  if (!prospective.has_value()) {
    return invalid_argument("prepared Sample Bank byte length overflowed");
  }
  samples_.at(slot).assign(mono_pcm.begin(), mono_pcm.end());
  playbacks_.at(slot) = playback;
  availability_mask_ |= std::uint64_t{1} << slot;
  decoded_pcm_bytes_ = prospective.value();
  return foundation::Result<void>::success();
}

const foundation::ProjectId& PreparedSampleBank::project_id() const noexcept {
  return project_id_;
}

std::uint64_t PreparedSampleBank::project_revision() const noexcept {
  return project_revision_;
}

std::uint64_t PreparedSampleBank::availability_mask() const noexcept {
  return availability_mask_;
}

std::size_t PreparedSampleBank::sample_count() const noexcept {
  return static_cast<std::size_t>(std::popcount(availability_mask_));
}

std::uint64_t PreparedSampleBank::decoded_pcm_bytes() const noexcept {
  return decoded_pcm_bytes_;
}

const std::vector<float>& PreparedSampleBank::sample(
    std::uint8_t slot) const noexcept {
  return samples_[slot];
}

const cooker::ResolvedPlayback& PreparedSampleBank::playback(
    std::uint8_t slot) const noexcept {
  return playbacks_[slot];
}

}  // namespace lmdj::audio
