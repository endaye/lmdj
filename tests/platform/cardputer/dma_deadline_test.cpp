#include "apps/cardputer-host/main/audio_driver.hpp"
#include "driver/i2s_std.h"
#include "esp_timer.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string_view>

namespace {
std::array<std::array<std::int16_t, 512>, 2> buffers{};
unsigned eof_count{}, writes{};
bool interrupt_write{};
void require(bool ok, const char* why) {
  if (ok) return;
  std::fprintf(stderr, "why: %s; remedy: reject a reservation once DMA has started its next transmission\n", why);
  std::abort();
}
void eof() {
  auto& buffer = buffers[eof_count++ % buffers.size()];
  i2s_event_data_t event{buffer.data(), sizeof(buffer)};
  fake_i2s::callbacks.on_sent(nullptr, &event, fake_i2s::context);
  // IDF auto_clear_after_cb clears the completed descriptor, then queues it
  // for writing. DMA now transmits the next descriptor. No physical timing,
  // masked/delayed IRQ, or analogue output is modeled by this fixture.
  buffer.fill(0);
}
int write(const void* data, std::size_t size, std::size_t* bytes) {
  ++writes;
  if (interrupt_write) eof();
  std::memcpy(buffers[0].data(), data, size);
  *bytes = size;
  return ESP_OK;
}
}
int main(int argc, char** argv) {
  require(argc == 2, "scenario required");
  const std::string_view scenario(argv[1]);
  require(scenario == "ontime" || scenario == "before" || scenario == "during", "unknown scenario");
  lmdj::cardputer::EspAudioIo io({8, 9, 41, 43, 42, 0x18, 0xBF, 2, 1});
  require(io.configure() && io.enable(), "configure/enable failed");
  fake_i2s::write = write;
  fake_timer::now_us = 1000;
  eof();
  fake_timer::now_us = 2000;
  require(io.wait_writable(), "initial reservation failed");
  require(io.reserved_eof_us() == 1000, "reservation lost the delivered EOF timestamp");
  if (scenario == "before") eof();
  interrupt_write = scenario == "during";
  std::array<std::int16_t, 512> pcm{};
  pcm.fill(1234);
  std::size_t accepted{};
  const bool ok = io.write(pcm, accepted);
  if (scenario == "ontime") {
    require(ok && accepted == pcm.size() && writes == 1, "valid submission rejected");
  } else {
    require(!ok, "late submission reported successful");
    if (scenario == "before") require(writes == 0 && accepted == 0, "expired reservation reached DMA write");
    else require(writes == 1 && accepted == pcm.size(), "late copy lost actual accepted count");
    require(!io.wait_writable(), "deadline failure did not fence later writes");
  }
  require(io.disable_and_quiesce() && io.release(), "cleanup failed");
}
