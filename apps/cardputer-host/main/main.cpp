#include "runtime_host.hpp"
#include "display.hpp"
#include "input_controller.hpp"
#include <algorithm>
#include <cstdio>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// The supplied file defines cardputer_configuration() returning this value.
// H1 research configuration has no Product Build or Host version. B1 owns the
// later Assembly implementation and generated identity; no probe is included.
struct CardputerConfiguration {
  lmdj::facade::RuntimeConfig runtime;
  lmdj::cardputer::HostProfile profile;
  lmdj::cardputer::EspAudioSessionConfig audio;
};
#include LMDJ_CARDPUTER_CONFIG_HEADER

namespace {
void silence(void*, float* left, float* right, std::uint32_t frames) noexcept {
  std::fill_n(left, frames, 0.0F);
  std::fill_n(right, frames, 0.0F);
}
}

extern "C" void app_main() {
  using namespace lmdj::cardputer;
  try {
    const auto config = cardputer_configuration();
    EspAudioSession audio(config.audio);
    // Establish actual codec/DMA silence even on a reset from an older image.
    // This is not a request to load content or auto-start a Pattern.
    if (!audio.start(silence, &audio, 0, true)) {
      std::puts("CARDPUTER research boot audio initialization failed");
      return;
    }
    const auto stopped = audio.stop_and_join();
    if (!stopped.quiescent || !stopped.silent) {
      std::puts("CARDPUTER research boot physical silence unconfirmed");
      return;
    }
    RuntimeHost host(config.runtime, config.profile, audio);
    Display display;
    InputController input(host, display);
    std::printf("CARDPUTER research unversioned source-base=%s phase=empty\n", LMDJ_CARDPUTER_REVISION);
    // Platform keyboard scanning feeds PhysicalKeyEvent into input. No external
    // USB/keyboard worker is granted direct Facade access, and disconnect never
    // implies stop. The display consumes only the bounded value projection.
    for (;;) {
      input.poll();
      vTaskDelay(1);
    }
  } catch (...) {
    std::puts("CARDPUTER research boot allocation/configuration failed");
  }
}
