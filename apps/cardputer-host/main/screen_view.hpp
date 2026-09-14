#pragma once

#include "display.hpp"

#include <array>
#include <cstdint>
#include <string_view>

namespace lmdj::cardputer {

struct ScreenIdentity {
  std::string_view product_build;
  std::string_view host_version;
  std::string_view source_revision;
};

struct ScreenTransfer {
  // Protocol session state; this is not a claim that a USB cable is present.
  bool session_active{};
  bool receiving{};
  std::uint64_t received_bytes{};
  bool failed{};
};

// 6x8 glyph cells on the 240x135 panel. All text is bounded and terminated;
// the rasterizer consumes a complete value snapshot, never a live Host.
struct ScreenView {
  static constexpr std::size_t columns = 40;
  static constexpr std::size_t rows = 16;
  std::array<std::array<char, columns + 1>, rows> lines{};
  bool operator==(const ScreenView&) const = default;
};

ScreenView make_screen_view(const DisplayFrame&, const ScreenTransfer&,
                            const ScreenIdentity&) noexcept;

}  // namespace lmdj::cardputer
