#pragma once

#include <array>
#include <string_view>
#include <lmdj/provider/registry.hpp>

namespace lmdj::providers::stem {

inline constexpr std::array<std::string_view, 4> roles{"drums", "bass", "vocals", "other"};
inline constexpr std::uint64_t maximum_wav_bytes = 16777216;

struct Pcm16Shape {
  std::uint32_t frame_rate;
  std::uint16_t channels;
  std::uint64_t frame_count;
  bool operator==(const Pcm16Shape&) const = default;
};

foundation::Result<std::int16_t> quantize_pcm16(double sample);
// Interleaved samples, unit gain and frame zero relative to the source. This
// Proof codec has a bounded allocation; it makes no model alignment claim.
foundation::Result<std::vector<std::byte>> encode_pcm16_wav(
    Pcm16Shape shape, std::span<const double> samples);
foundation::Result<void> validate_parameters(const nlohmann::json& parameters);
provider::OutputValidation output_validation(std::string role);

}  // namespace lmdj::providers::stem
