#pragma once

#include <cstdint>
#include <limits>

namespace lmdj::audio::detail {

constexpr std::int64_t floor_div(
    std::int64_t numerator,
    std::int64_t denominator) {
  const auto quotient = numerator / denominator;
  const auto remainder = numerator % denominator;
  return remainder != 0 && ((remainder < 0) != (denominator < 0))
      ? quotient - 1
      : quotient;
}

constexpr std::int32_t scale_velocity(
    std::int16_t sample,
    std::uint8_t velocity) {
  return static_cast<std::int32_t>(
      floor_div(
          static_cast<std::int64_t>(sample) * velocity + 63,
          127));
}

constexpr std::int16_t saturating_add(
    std::int16_t current,
    std::int32_t sample) {
  const auto mixed =
      static_cast<std::int64_t>(current) +
      static_cast<std::int64_t>(sample);
  if (mixed > std::numeric_limits<std::int16_t>::max()) {
    return std::numeric_limits<std::int16_t>::max();
  }
  if (mixed < std::numeric_limits<std::int16_t>::min()) {
    return std::numeric_limits<std::int16_t>::min();
  }
  return static_cast<std::int16_t>(mixed);
}

}  // namespace lmdj::audio::detail
