#include "apps/cardputer-host/main/cardputer_assembly.hpp"
#include <array>
#include <cstdio>
#include <cstdlib>

namespace {
void require(bool value) {
  if (!value) {
    std::fputs("why: codec unity gain or quiet software output changed; remedy: keep ES8311 at 0 dB and apply user volume in PCM stage\n", stderr);
    std::abort();
  }
}
}

int main() {
  using namespace lmdj::cardputer;
  const auto config = cardputer_configuration();
  // ES8311 datasheet register 0x32: -95.5 dB + value * 0.5 dB.
  require(-955 + 5 * config.audio.io.codec_volume == 0);
  PcmOutputStage stage;
  std::array<float, AudioDriver::frames_per_block> left{}, right{};
  std::array<std::int16_t, AudioDriver::frames_per_block * 2> output{};
  left.fill(0.125F);
  right.fill(0.125F);
  require(stage.convert(left, right, output, HostStatus{}.volume, false));
  require(output.front() > 0 && output.back() == 819);
  require(stage.convert(left, right, output, 0, false));
  require(output.back() == 0);
  require(stage.convert(left, right, output, 2, true));
  for (auto value : output) require(value == 0);
}
