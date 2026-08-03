#include <lmdj/audio/prepared_sample_bank.hpp>

#include <algorithm>
#include <bit>
#include <cmath>
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

float pcm16_to_float(std::int16_t value) noexcept {
  return value < 0 ? static_cast<float>(value) / 32768.0F
                   : static_cast<float>(value) / 32767.0F;
}

std::uint8_t global_slot(domain::PadSlotId slot) noexcept {
  return static_cast<std::uint8_t>(slot.bank * 16U + slot.pad);
}

}  // namespace

PreparedSampleBank::PreparedSampleBank(foundation::ProjectId project_id,
                                       std::uint64_t project_revision)
    : project_id_(std::move(project_id)), project_revision_(project_revision) {}

foundation::Result<PreparedSampleBank> PreparedSampleBank::from_snapshot(
    const cooker::RuntimeSnapshot& snapshot) {
  if (!domain::is_valid_uuid(snapshot.project_id.value())) {
    return invalid_bank("runtime snapshot Project ID is invalid");
  }
  PreparedSampleBank bank(snapshot.project_id, snapshot.project_revision);
  std::uint8_t previous_slot = 0;
  bool has_previous_slot = false;
  for (const auto& pad : snapshot.pads) {
    if (!domain::is_valid_slot(pad.slot) || pad.sample == nullptr) {
      return invalid_bank("runtime snapshot Pad is invalid");
    }
    const auto slot = global_slot(pad.slot);
    if (has_previous_slot && slot <= previous_slot) {
      return invalid_bank("runtime snapshot Pads are not unique and ordered");
    }
    const auto& source = *pad.sample;
    if (source.sample_rate != 48'000 ||
        (source.channels != 1 && source.channels != 2) ||
        source.interleaved.empty() ||
        source.interleaved.size() % source.channels != 0) {
      return invalid_bank("runtime snapshot PCM shape is invalid");
    }
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
    const auto assigned = bank.set_sample(slot, mono);
    if (!assigned.has_value()) {
      return invalid_bank(assigned.error().message);
    }
    previous_slot = slot;
    has_previous_slot = true;
  }
  return foundation::Result<PreparedSampleBank>::success(std::move(bank));
}

PreparedSampleBank PreparedSampleBank::empty(foundation::ProjectId project_id,
                                             std::uint64_t project_revision) {
  return PreparedSampleBank(std::move(project_id), project_revision);
}

foundation::Result<void> PreparedSampleBank::set_sample(
    std::uint8_t slot, std::span<const float> mono_pcm) {
  if (slot >= samples_.size() || mono_pcm.empty() ||
      (availability_mask_ & (std::uint64_t{1} << slot)) != 0 ||
      !std::all_of(mono_pcm.begin(), mono_pcm.end(),
                   [](float value) { return std::isfinite(value); })) {
    return invalid_argument("prepared Sample Bank input is invalid");
  }
  samples_.at(slot).assign(mono_pcm.begin(), mono_pcm.end());
  availability_mask_ |= std::uint64_t{1} << slot;
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

const std::vector<float>& PreparedSampleBank::sample(
    std::uint8_t slot) const noexcept {
  return samples_[slot];
}

}  // namespace lmdj::audio
