#pragma once

#include <cstdint>
#include <optional>

namespace lmdj::audio::detail {

// Preserve the existing exhaustion boundary even though ownership now uses a
// separate 32-bit slot token. Never recycle an externally observable identity.
inline constexpr std::uint64_t kPatternGenerationLimit =
    std::uint64_t{1} << 63U;

inline std::optional<std::uint64_t> take_pattern_generation(
    std::uint64_t& next_generation) noexcept {
  if (next_generation >= kPatternGenerationLimit) {
    return std::nullopt;
  }
  return next_generation++;
}

}  // namespace lmdj::audio::detail
