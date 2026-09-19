#include "apps/cardputer-host/main/audio_driver.hpp"
#include "driver/i2c_master.h"
#include <cstdio>
#include <cstdlib>
#include <string_view>
#include <utility>
#include <vector>

namespace {
using Write = std::pair<std::uint8_t, std::uint8_t>;
std::vector<Write> writes;
bool reject_power_up{};
bool observe(std::uint8_t address, std::uint8_t value) {
  writes.emplace_back(address, value);
  return !(reject_power_up && address == 0x12 && value == 0);
}
void require(bool value, const char* why) {
  if (value) return;
  std::fprintf(stderr, "why: %s; remedy: keep DAC down through clock startup and enable it before restoring gain/unmute\n", why);
  std::abort();
}
void configure_and_enable(lmdj::cardputer::EspAudioIo& io) {
  writes.clear();
  require(io.configure(), "ESP audio configuration failed");
  require(io.enable(), "I2S clock startup failed");
  bool powered_down = false;
  for (const auto& [address, value] : writes) {
    if (address != 0x12) continue;
    require(value == 0x02, "DAC was enabled before clock prewarm");
    powered_down = true;
  }
  require(powered_down, "configuration omitted explicit DAC power-down");
}
void release(lmdj::cardputer::EspAudioIo& io) {
  require(io.mute(true), "hardware stop mute failed");
  require(io.disable_and_quiesce(), "I2S stop failed");
  require(io.release(), "audio resource release failed");
}
}

int main(int argc, char** argv) {
  // Coverage probe: no arguments means the first registered scenario.
  require(argc <= 2, "at most one startup scenario");
  const std::string_view scenario = argc > 1 ? argv[1] : "order";
  require(scenario == "order" || scenario == "power_failure", "unknown startup scenario");
  fake_i2c::before_transmit = observe;
  lmdj::cardputer::EspAudioIo io({8, 9, 41, 43, 42, 0x18, 0xBF, 2, 1});
  // Real ESP register code, fake I2C/I2S: no analogue transient, DMA timing or
  // audibility proof. audio.prewarm/explicit_prewarm/drain_failure separately
  // prove AudioDriver reaches mute(false) only after silent prewarm + drain.
  // Device listening is recorded separately in the Task plan.
  for (int cycle = 0; cycle != 2; ++cycle) {
    configure_and_enable(io);
    writes.clear();
    reject_power_up = scenario == "power_failure";
    if (reject_power_up) {
      require(!io.mute(false), "failed DAC power-up was accepted");
      require(writes == std::vector<Write>{{0x12, 0}},
              "gain or unmute continued after failed DAC power-up");
    } else {
      require(io.mute(false), "DAC startup transition failed");
      require(writes == std::vector<Write>{{0x12, 0}, {0x32, 0xBF}, {0x31, 0}},
              "DAC power-up, gain and unmute order changed");
    }
    reject_power_up = false;
    release(io);
  }
}
