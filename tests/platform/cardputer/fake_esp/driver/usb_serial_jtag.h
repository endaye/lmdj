#pragma once
#include "driver/i2c_master.h"
#include <algorithm>
#include <cstring>
#include <vector>
struct usb_serial_jtag_driver_config_t { std::uint32_t rx_buffer_size{}, tx_buffer_size{}; };
namespace fake_usb {
inline bool installed{};
inline std::vector<std::byte> incoming, outgoing;
inline std::uint64_t now_us{};
}
inline bool usb_serial_jtag_is_driver_installed() { return fake_usb::installed; }
inline int usb_serial_jtag_driver_install(const usb_serial_jtag_driver_config_t*) {
  fake_usb::installed = true; return ESP_OK;
}
inline int usb_serial_jtag_read_bytes(void* data, std::size_t size, int) {
  const auto count = std::min(size, fake_usb::incoming.size());
  if (count) std::memcpy(data, fake_usb::incoming.data(), count);
  fake_usb::incoming.erase(fake_usb::incoming.begin(), fake_usb::incoming.begin() + count);
  return static_cast<int>(count);
}
inline int usb_serial_jtag_write_bytes(const void* data, std::size_t size, int) {
  const auto* begin = static_cast<const std::byte*>(data);
  fake_usb::outgoing.insert(fake_usb::outgoing.end(), begin, begin + size);
  return static_cast<int>(size);
}
