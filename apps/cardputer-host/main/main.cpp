#include "runtime_host.hpp"
#include "cardputer_assembly.hpp"
#include "display.hpp"
#include "input_controller.hpp"
#include "usb_transfer_endpoint.hpp"
#include <algorithm>
#include <cstdio>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

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
    UsbTransferEndpoint transfer(host, config.runtime.content_limits.maximum_encoded_bytes);
    if (!transfer.install()) {
      std::puts("CARDPUTER USB transfer initialization failed");
      return;
    }
    std::printf("CARDPUTER product-build=%s host=%s assembly=%s source=%s phase=empty\n",
                config.product_build, config.host_version, config.assembly_sha256,
                LMDJ_CARDPUTER_REVISION);
    // Platform keyboard scanning feeds PhysicalKeyEvent into input. No external
    // USB/keyboard worker is granted direct Facade access, and disconnect never
    // implies stop. The display consumes only the bounded value projection.
    for (;;) {
      input.poll();
      transfer.poll();
      vTaskDelay(1);
    }
  } catch (...) {
    std::puts("CARDPUTER research boot allocation/configuration failed");
  }
}
