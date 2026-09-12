#pragma once

#include "screen_view.hpp"

#ifdef ESP_PLATFORM
#include <memory>

namespace lmdj::cardputer {

// All panel wiring/orientation values are supplied by Product Assembly.
struct LcdConfiguration {
  int spi_host{}, mosi{}, clock{}, chip_select{}, data_command{}, reset{}, backlight{};
  int frequency_hz{}, gap_x{}, gap_y{};
  bool swap_xy{}, mirror_x{}, mirror_y{}, invert{};
};

class LcdDisplay final {
 public:
  explicit LcdDisplay(LcdConfiguration);
  ~LcdDisplay();
  LcdDisplay(const LcdDisplay&) = delete;
  LcdDisplay& operator=(const LcdDisplay&) = delete;
  bool install() noexcept;
  // One control owner. Never waits for a color DMA transaction: while busy,
  // retain the buffer and return. Capture a whole view between frames only.
  bool poll(const ScreenView& view, std::uint64_t now_ms) noexcept;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace lmdj::cardputer
#endif
