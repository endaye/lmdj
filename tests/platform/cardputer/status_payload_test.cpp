#include "apps/cardputer-host/main/status_payload.hpp"
#include "tests/core/support/test.hpp"

int main() {
  using namespace lmdj::cardputer;
  HostStatus status;
  status.phase = lmdj::facade::RuntimePhase::running;
  status.error = HostResult::audio_error;
  status.armed = true;
  status.muted = true;
  status.volume = 7;
  status.pad_count = 4;
  // All eight bytes are distinct; small live fixtures hide the truncated MSBs.
  status.content_bytes = 0x8877665544332211ULL;
  const auto payload = encode_status_payload(status);
  const std::array<std::byte, 16> expected{
      std::byte{0}, std::byte{0}, std::byte{2}, std::byte{4},
      std::byte{1}, std::byte{1}, std::byte{7}, std::byte{4},
      std::byte{0x11}, std::byte{0x22}, std::byte{0x33}, std::byte{0x44},
      std::byte{0x55}, std::byte{0x66}, std::byte{0x77}, std::byte{0x88}};
  LMDJ_CHECK(payload == expected);
}
