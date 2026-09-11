#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

using gpio_num_t = int;
inline constexpr int ESP_OK = 0, I2C_NUM_0 = 0, I2C_NUM_1 = 1;
inline constexpr int I2C_CLK_SRC_DEFAULT = 0, I2C_ADDR_BIT_LEN_7 = 0;
struct FakeBus { int port, sda, scl, devices{}; };
struct FakeDevice { FakeBus* bus; std::array<std::uint8_t, 256> registers{}; };
using i2c_master_bus_handle_t = FakeBus*;
using i2c_master_dev_handle_t = FakeDevice*;
struct i2c_master_bus_config_t {
  int i2c_port{}, sda_io_num{}, scl_io_num{}, clk_source{}, glitch_ignore_cnt{};
  struct { bool enable_internal_pullup{}; } flags;
};
struct i2c_device_config_t { int dev_addr_length{}, device_address{}, scl_speed_hz{}; };
namespace fake_i2c {
inline std::array<FakeBus*, 64> routing{};
inline int created{}, deleted{};
inline bool fail_add{}, fail_remove{};
inline bool connected(FakeBus* bus) {
  return routing[bus->sda] == bus && routing[bus->scl] == bus;
}
}
inline int i2c_new_master_bus(const i2c_master_bus_config_t* c, FakeBus** out) {
  *out = new FakeBus{c->i2c_port, c->sda_io_num, c->scl_io_num};
  // Model GPIO matrix output ownership: a second controller steals the pins.
  fake_i2c::routing[c->sda_io_num] = fake_i2c::routing[c->scl_io_num] = *out;
  ++fake_i2c::created;
  return ESP_OK;
}
inline int i2c_del_master_bus(FakeBus* bus) {
  if (bus->devices) return -1;
  if (fake_i2c::routing[bus->sda] == bus) fake_i2c::routing[bus->sda] = nullptr;
  if (fake_i2c::routing[bus->scl] == bus) fake_i2c::routing[bus->scl] = nullptr;
  delete bus; ++fake_i2c::deleted; return ESP_OK;
}
inline int i2c_master_bus_add_device(FakeBus* bus, const i2c_device_config_t*, FakeDevice** out) {
  if (fake_i2c::fail_add) return -1;
  *out = new FakeDevice{bus, {}}; ++bus->devices; return ESP_OK;
}
inline int i2c_master_bus_rm_device(FakeDevice* device) {
  if (fake_i2c::fail_remove) return -1;
  --device->bus->devices; delete device; return ESP_OK;
}
inline int i2c_master_transmit(FakeDevice* device, const void* data, std::size_t size, int) {
  if (!fake_i2c::connected(device->bus) || size != 2) return -1;
  const auto* bytes = static_cast<const std::uint8_t*>(data);
  device->registers[bytes[0]] = bytes[1]; return ESP_OK;
}
inline int i2c_master_transmit_receive(FakeDevice* device, const void* reg, std::size_t,
                                       void* data, std::size_t, int) {
  if (!fake_i2c::connected(device->bus)) return -1;
  *static_cast<std::uint8_t*>(data) = device->registers[*static_cast<const std::uint8_t*>(reg)];
  return ESP_OK;
}
