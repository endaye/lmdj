#pragma once

#include <array>
#include <cstdint>
#include <string_view>

#include "runtime_host.hpp"

namespace lmdj::cardputer {

struct DisplayFrame {
  HostStatus status{};
  std::array<bool, 4> pad_active{};
  std::array<char, 16> phase_label{};
  std::array<char, 32> error_label{};
};

// A bounded state projection for the physical display adapter. The adapter
// owns a value copy, so an I2C/display task never reads RuntimeHost directly.
class Display final {
 public:
  void present(const HostStatus& status,
               const std::array<bool, 4>& pad_active) noexcept;
  const DisplayFrame& frame() const noexcept { return frame_; }

 private:
  DisplayFrame frame_{};
};

std::string_view phase_label(facade::RuntimePhase phase) noexcept;
std::string_view error_label(HostResult result) noexcept;

}  // namespace lmdj::cardputer
