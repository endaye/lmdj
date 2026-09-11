#include "apps/cardputer-host/main/audio_driver.hpp"
#include <cstdlib>
#include <iostream>
#include <string_view>

#define CHECK(expr) do { if (!(expr)) { std::cerr << #expr << '\n'; std::abort(); } } while (false)
using namespace lmdj::cardputer;

int main(int argc, char** argv) {
  CHECK(argc == 2);
  const std::string_view scenario = argv[1];
  EspAudioConfig config{8, 9, 41, 43, 42, 0x18, 0x40, 2, 1};
  if (scenario == "owned") {
    EspAudioIo audio(config);
    CHECK(audio.configure()); CHECK(audio.release());
    CHECK(fake_i2c::created == 1 && fake_i2c::deleted == 1);
    return 0;
  }
  i2c_master_bus_config_t bus_config{};
  bus_config.i2c_port = I2C_NUM_1;
  bus_config.sda_io_num = 8; bus_config.scl_io_num = 9;
  i2c_master_bus_handle_t bus{};
  CHECK(i2c_new_master_bus(&bus_config, &bus) == ESP_OK);
  i2c_device_config_t keypad_config{};
  keypad_config.device_address = 0x34;
  i2c_master_dev_handle_t keypad{};
  CHECK(i2c_master_bus_add_device(bus, &keypad_config, &keypad) == ESP_OK);
  keypad->registers[4] = 0xb0;
  auto keyboard_reads = [&]() {
    const std::uint8_t reg = 4; std::uint8_t event{};
    CHECK(i2c_master_transmit_receive(keypad, &reg, 1, &event, 1, 20) == ESP_OK);
    CHECK(event == 0xb0);
  };
  keyboard_reads();
  config.shared_bus = bus;
  {
    EspAudioIo audio(config);
    if (scenario == "partial") {
      fake_i2c::fail_add = true;
      CHECK(!audio.configure());
      CHECK(audio.release());
      fake_i2c::fail_add = false;
      keyboard_reads();
    } else if (scenario == "retry") {
      CHECK(audio.configure());
      fake_i2c::fail_remove = true;
      CHECK(!audio.release());
      keyboard_reads();
      fake_i2c::fail_remove = false;
      CHECK(audio.release());
    } else {
      CHECK(scenario == "restart");
    }
    for (int cycle = 0; cycle < 3; ++cycle) {
      CHECK(audio.configure()); keyboard_reads();
      CHECK(audio.enable()); keyboard_reads();
      CHECK(audio.disable_and_quiesce());
      CHECK(audio.release()); keyboard_reads();
      CHECK(bus->devices == 1);
      CHECK(fake_i2c::created == 1 && fake_i2c::deleted == 0);
    }
  }
  keyboard_reads();
  CHECK(i2c_master_bus_rm_device(keypad) == ESP_OK);
  CHECK(i2c_del_master_bus(bus) == ESP_OK);
  CHECK(fake_i2c::deleted == 1);
}
