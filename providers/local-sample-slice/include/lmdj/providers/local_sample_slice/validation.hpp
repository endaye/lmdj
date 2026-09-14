#pragma once

#include <lmdj/provider/registry.hpp>

namespace lmdj::providers::sample_slice {

// A borrowed view: the caller retains the owning ArtifactHandle while using it.
struct Pcm16Audio {
  std::uint32_t frame_rate;
  std::uint16_t channels;
  std::uint64_t frame_count;
  std::span<const std::byte> samples;
};

foundation::Result<Pcm16Audio> inspect_pcm16_wav(std::span<const std::byte> bytes);
foundation::Result<void> validate_slice_points(
    std::span<const std::byte> bytes, const foundation::ArtifactRef& source,
    std::uint32_t frame_rate, std::uint64_t frame_count);
provider::OutputValidation slice_points_validation();

}  // namespace lmdj::providers::sample_slice
