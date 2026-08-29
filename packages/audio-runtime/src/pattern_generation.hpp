#pragma once

#include <cstdint>
#include <optional>

namespace lmdj::audio::detail {

inline constexpr std::uint64_t kPatternClaimedMask =
    std::uint64_t{1} << 63U;

inline std::optional<std::uint64_t> take_pattern_generation(
    std::uint64_t& next_generation) noexcept {
  if (next_generation >= kPatternClaimedMask) {
    return std::nullopt;
  }
  return next_generation++;
}

inline std::uint64_t pattern_mailbox_generation(
    std::uint64_t value) noexcept {
  return value & ~kPatternClaimedMask;
}

}  // namespace lmdj::audio::detail
