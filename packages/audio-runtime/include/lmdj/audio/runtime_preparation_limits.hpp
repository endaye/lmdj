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
  std::uint64_t maximum_user_bank_bytes;
  std::uint64_t maximum_generation_bytes;
  std::uint64_t maximum_resident_bytes;

  constexpr bool allows_artifact_bytes(
      std::uint64_t observed) const noexcept {
    return observed <= maximum_artifact_bytes;
  }

  constexpr bool allows_user_bank_bytes(
      std::uint64_t observed) const noexcept {
    return observed <= maximum_user_bank_bytes;
  }

  constexpr bool allows_generation_bytes(
      std::uint64_t observed) const noexcept {
    return observed <= maximum_generation_bytes;
  }

  constexpr bool allows_resident_bytes(
      std::uint64_t observed) const noexcept {
    return observed <= maximum_resident_bytes;
  }
};

enum class RuntimeQuotaConstraint {
  none,
  user_bank,
  generation,
};

struct RuntimeQuotaAssessment {
  RuntimeQuotaConstraint constraint;
  std::uint64_t user_bank_remaining_bytes;
  std::uint64_t generation_remaining_bytes;
};

constexpr std::optional<RuntimeQuotaAssessment> assess_runtime_quota(
    std::uint64_t user_bank_used_bytes,
    std::uint64_t generation_used_bytes,
    std::uint64_t requested_bytes,
    const RuntimePreparationLimits& limits) noexcept {
  if (user_bank_used_bytes > limits.maximum_user_bank_bytes ||
      generation_used_bytes > limits.maximum_generation_bytes) {
    return std::nullopt;
  }
  const auto user_bank_remaining =
      limits.maximum_user_bank_bytes - user_bank_used_bytes;
  const auto generation_remaining =
      limits.maximum_generation_bytes - generation_used_bytes;
  const auto user_bank_exhausted = requested_bytes > user_bank_remaining;
  const auto generation_exhausted = requested_bytes > generation_remaining;
  auto constraint = RuntimeQuotaConstraint::none;
  if (user_bank_exhausted &&
      (!generation_exhausted ||
       user_bank_remaining <= generation_remaining)) {
    constraint = RuntimeQuotaConstraint::user_bank;
  } else if (generation_exhausted) {
    constraint = RuntimeQuotaConstraint::generation;
  }
  return RuntimeQuotaAssessment{
      constraint,
      user_bank_remaining,
      generation_remaining,
  };
}

}  // namespace lmdj::audio
