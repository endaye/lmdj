#pragma once

#include <cstdint>
#include <memory>
#include "input_controller.hpp"
#ifdef ESP_PLATFORM
#include "driver/i2c_master.h"
#endif

namespace lmdj::cardputer {

#ifdef ESP_PLATFORM
class Tca8418Scanner final {
 public:
  Tca8418Scanner(int sda, int scl, std::uint8_t address = 0x34) noexcept;
  ~Tca8418Scanner();
  Tca8418Scanner(const Tca8418Scanner&) = delete;
  Tca8418Scanner& operator=(const Tca8418Scanner&) = delete;
  bool install() noexcept;
  i2c_master_bus_handle_t bus_handle() const noexcept;
  void poll(InputController& input) noexcept;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
#else
class Tca8418Scanner final {
 public:
  Tca8418Scanner(int, int, std::uint8_t = 0x34) noexcept {}
  bool install() noexcept { return true; }
  void poll(InputController&) noexcept {}
};
#endif

}  // namespace lmdj::cardputer
