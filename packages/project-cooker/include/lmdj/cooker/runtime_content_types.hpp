#pragma once

#include <cstdint>
#include <string>

namespace lmdj::cooker {

struct RuntimeContentIdentity {
  std::string sha256;
  std::uint64_t byte_length{};
  bool operator==(const RuntimeContentIdentity&) const = default;
};

// Codec allowances, not an Engine/FX/device memory budget. Zero is never
// unlimited. PCM bytes count unique samples rather than per-Pad expansion.
struct RuntimeContentLimits {
  std::uint64_t maximum_encoded_bytes{};
  std::uint64_t maximum_pcm_bytes{};
  std::uint32_t maximum_sample_frames{};
  std::uint32_t maximum_pads{};
  std::uint32_t maximum_events{};
};

struct RuntimeContentFootprint {
  std::uint64_t encoded_bytes{};
  std::uint64_t pcm_bytes{};
  std::uint64_t prepared_float_bytes{};
  std::uint64_t largest_float_sample_bytes{};
  std::uint32_t pads{};
  std::uint32_t events{};
  std::uint32_t samples{};
};

}  // namespace lmdj::cooker
