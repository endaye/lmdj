#include "apps/cardputer-host/main/cardputer_assembly.hpp"

namespace lmdj::cardputer {

CardputerConfiguration cardputer_configuration() noexcept {
  // Cardputer ADV / ESP32-S3 wiring and the no-PSRAM admission profile are
  // product facts. They are deliberately absent from the neutral Host.
  return {
      "1.0.59.0",
      "1.0.1",
      "26da158daea830fa2e905c5cec97955a3e8b732465a0f919e6d65d8f7c74a713",
      {{131072, 96000, 19200, 4, 32}, 331176, 32768, 128, 1000, 1000000},
      {4},
      // ES8311 register 0x32 is logarithmic: 0xBF = 0 dB, not maximum
      // gain. Keep user attenuation and click-free ramps in PcmOutputStage;
      // 0x40 here adds -63.5 dB before the default 20% software volume.
      {{8, 9, 41, 43, 42, 0x18, 0xBF, 2, 1}, 8192, 20, 94, 5000},
  };
}

}  // namespace lmdj::cardputer
