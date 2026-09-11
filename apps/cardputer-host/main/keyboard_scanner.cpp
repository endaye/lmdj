#include "keyboard_scanner.hpp"

#ifdef ESP_PLATFORM
#include "driver/i2c_master.h"

namespace lmdj::cardputer {
struct Tca8418Scanner::Impl {
  i2c_master_bus_handle_t bus{};
  i2c_master_dev_handle_t dev{};
  int sda{}, scl{};
  std::uint8_t address{};
  bool installed{};
  bool write(std::uint8_t reg, std::uint8_t value) noexcept {
    const std::uint8_t bytes[]{reg, value};
    return i2c_master_transmit(dev, bytes, sizeof(bytes), 20) == ESP_OK;
  }
  bool read(std::uint8_t reg, std::uint8_t& value) noexcept {
    return i2c_master_transmit_receive(dev, &reg, 1, &value, 1, 20) == ESP_OK;
  }
};

Tca8418Scanner::Tca8418Scanner(int sda, int scl, std::uint8_t address) noexcept
    : impl_(std::make_unique<Impl>(Impl{.sda = sda, .scl = scl, .address = address})) {}
Tca8418Scanner::~Tca8418Scanner() {
  if (impl_->dev) (void)i2c_master_bus_rm_device(impl_->dev);
  if (impl_->bus) (void)i2c_del_master_bus(impl_->bus);
}

i2c_master_bus_handle_t Tca8418Scanner::bus_handle() const noexcept {
  return impl_->installed ? impl_->bus : nullptr;
}

bool Tca8418Scanner::install() noexcept {
  auto& s = *impl_;
  if (s.installed) return true;
  i2c_master_bus_config_t config{};
  config.i2c_port = I2C_NUM_1;
  config.sda_io_num = static_cast<gpio_num_t>(s.sda);
  config.scl_io_num = static_cast<gpio_num_t>(s.scl);
  config.clk_source = I2C_CLK_SRC_DEFAULT;
  config.glitch_ignore_cnt = 7;
  config.flags.enable_internal_pullup = true;
  if (i2c_new_master_bus(&config, &s.bus) != ESP_OK) return false;
  i2c_device_config_t device{};
  device.dev_addr_length = I2C_ADDR_BIT_LEN_7;
  device.device_address = s.address;
  device.scl_speed_hz = 400000;
  if (i2c_master_bus_add_device(s.bus, &device, &s.dev) != ESP_OK) return false;
  // TCA8418: seven rows and eight columns are wired on Cardputer ADV.
  if (!s.write(0x1d, 0x7f) || !s.write(0x1e, 0xff) ||
      !s.write(0x01, 0x81)) return false;
  // A MCU reset does not necessarily reset the keypad controller. Discard
  // stale FIFO entries and acknowledge its interrupt before admitting input.
  std::uint8_t pending{};
  if (!s.read(0x03, pending)) return false;
  pending &= 0x0f;
  while (pending-- != 0) {
    std::uint8_t discarded{};
    if (!s.read(0x04, discarded)) return false;
  }
  if (!s.write(0x02, 0x01) || !s.write(0x03, 0x00)) return false;
  s.installed = true;
  return true;
}

void Tca8418Scanner::poll(InputController& input) noexcept {
  auto& s = *impl_;
  if (!s.installed) return;
  std::uint8_t count{};
  if (!s.read(0x03, count)) return;
  count &= 0x0f;
  while (count-- != 0) {
    std::uint8_t event{};
    if (!s.read(0x04, event) || event == 0) break;
    // Cardputer's TCA8418 event table uses 0x01..0x50 for presses and
    // 0x81..0xd0 for releases (KEA[7] is the release marker).
    const bool pressed = (event & 0x80) == 0;
    const auto encoded = static_cast<std::uint8_t>(event & 0x7f);
    // 0x01..0x50 are matrix events; GPIO events and empty reads are not keys.
    if (encoded == 0 || encoded > 0x50) continue;
    const auto code = static_cast<std::uint8_t>(encoded - 1);
    const auto raw_row = static_cast<std::uint8_t>(code / 10);
    const auto raw_col = static_cast<std::uint8_t>(code % 10);
    const auto row = static_cast<std::uint8_t>((raw_col + 4) % 4);
    const auto col = static_cast<std::uint8_t>(raw_row * 2 + (raw_col > 3 ? 1 : 0));
    PhysicalKey key = PhysicalKey::unknown;
    if (row == 0 && col == 0) key = PhysicalKey::escape;
    else if (row == 0 && col == 11) key = PhysicalKey::minus;
    else if (row == 0 && col == 12) key = PhysicalKey::equal;
    else if (row == 2 && col == 2) key = PhysicalKey::a;
    else if (row == 2 && col == 3) key = PhysicalKey::s;
    else if (row == 2 && col == 4) key = PhysicalKey::d;
    else if (row == 2 && col == 5) key = PhysicalKey::f;
    else if (row == 2 && col == 13) key = PhysicalKey::enter;
    else if (row == 3 && col == 9) key = PhysicalKey::m;
    else if (row == 3 && col == 13) key = PhysicalKey::space;
    if (key != PhysicalKey::unknown) (void)input.enqueue({key, pressed, false});
  }
}
}  // namespace lmdj::cardputer
#endif
