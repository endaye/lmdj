#include "apps/cardputer-host/main/cardputer_assembly.hpp"

namespace lmdj::cardputer {

CardputerConfiguration cardputer_configuration() noexcept {
  // Cardputer ADV / ESP32-S3 wiring and the no-PSRAM admission profile are
  // product facts. They are deliberately absent from the neutral Host.
  return {
      "1.0.56.0",
      "1.0.0",
      "9213ef66e2b92120a4680ab49bf6ac09b4096be46378d88ae7aebd67a27f5c3d",
      {{131072, 96000, 19200, 4, 32}, 331176, 32768, 128, 1000, 1000000},
      {4},
      {{8, 9, 41, 43, 42, 0x18, 0x40, 2, 1}, 8192, 20, 94, 5000},
  };
}

}  // namespace lmdj::cardputer
