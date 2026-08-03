#pragma once

#include <cstdint>
#include <limits>
#include <optional>

namespace lmdj::audio {

static_assert(
    sizeof(float) == 4,
    "runtime preparation byte budgets require 32-bit float PCM");

constexpr std::optional<std::uint64_t> checked_mono_float_bytes(
    std::uint64_t decoded_frames) noexcept {
  if (decoded_frames >
      std::numeric_limits<std::uint64_t>::max() / sizeof(float)) {
    return std::nullopt;
  }
  return decoded_frames * sizeof(float);
}

constexpr std::optional<std::uint64_t> checked_runtime_byte_sum(
    std::uint64_t current,
    std::uint64_t additional) noexcept {
  if (current >
      std::numeric_limits<std::uint64_t>::max() - additional) {
    return std::nullopt;
  }
  return current + additional;
}

struct RuntimePreparationLimits {
  std::uint64_t maximum_artifact_bytes;
  std::uint64_t maximum_decoded_frames_per_pad;
  std::uint64_t maximum_prepared_bank_bytes;
  std::uint64_t maximum_live_bank_bytes;

  constexpr bool allows_artifact_bytes(
      std::uint64_t observed) const noexcept {
    return observed <= maximum_artifact_bytes;
  }

  constexpr bool allows_decoded_frames_per_pad(
      std::uint64_t observed) const noexcept {
    return observed <= maximum_decoded_frames_per_pad;
  }

  constexpr bool allows_prepared_bank_bytes(
      std::uint64_t observed) const noexcept {
    return observed <= maximum_prepared_bank_bytes;
  }

  constexpr bool allows_live_bank_bytes(
      std::uint64_t observed) const noexcept {
    return observed <= maximum_live_bank_bytes;
  }
};

}  // namespace lmdj::audio
