#include "apps/cardputer-host/main/usb_transfer_endpoint.hpp"
#include "driver/usb_serial_jtag.h"
#include "tests/core/support/test.hpp"
#include <cstdio>
#include <string_view>
#include <memory>
#include <string>
#include <lmdj/cooker/runtime_content.hpp>

namespace {
using namespace lmdj::cardputer;
lmdj::cooker::EncodedRuntimeContent valid_content() {
  using namespace lmdj;
  auto pcm = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{
      48000, 1, std::vector<std::int16_t>(16, 1000)});
  cooker::RuntimeSnapshot snapshot{
      foundation::ProjectId{"00000000-0000-4000-8000-000000000001"},
      foundation::PatternId{"00000000-0000-4000-8000-000000000002"}, 1, 120,
      1, 960, 3840,
      {{{2, 7}, {}, pcm, {0, 16, domain::TriggerMode::one_shot, 1.0F, false}}}, {}};
  auto encoded = cooker::encode_runtime_content(snapshot, {1048576, 262144, 65536, 64, 1024});
  LMDJ_CHECK(encoded.has_value());
  return std::move(encoded.value());
}
struct Audio final : AudioSession {
  bool start(Render, void*, std::uint8_t, bool) noexcept override { return true; }
  AudioStopResult stop_and_join() noexcept override { return {true, true}; }
  void set_output(std::uint8_t, bool) noexcept override {}
  bool healthy() const noexcept override { return true; }
};
struct Fixture {
  Audio audio;
  RuntimeHost host{{{1048576, 262144, 65536, 64, 1024}, 16777216, 65536, 128, 100, 10000}, {4}, audio};
  UsbTransferEndpoint endpoint{host, 1048576};
  std::array<std::byte, 16> nonce{};
  std::uint32_t request{1};

  TransferFrame send(TransferOpcode opcode, std::span<const std::byte> payload = {}) {
    TransferFrame frame;
    frame.opcode = static_cast<std::uint8_t>(opcode);
    frame.request_id = request++;
    frame.nonce = nonce;
    frame.payload_size = static_cast<std::uint16_t>(payload.size());
    std::copy(payload.begin(), payload.end(), frame.payload.begin());
    std::array<std::byte, transfer_max_frame> encoded{};
    std::size_t size{};
    LMDJ_CHECK(encode_transfer_frame(frame, encoded, size));
    fake_usb::incoming.assign(encoded.begin(), encoded.begin() + size);
    fake_usb::outgoing.clear();
    endpoint.poll();
    TransferFrame response;
    std::size_t consumed{};
    LMDJ_CHECK(decode_transfer_frame(fake_usb::outgoing, response, consumed) == FrameDecode::ready);
    return response;
  }
  void begin(const lmdj::cooker::EncodedRuntimeContent* content = nullptr) {
    LMDJ_CHECK(host.begin_receive() == HostResult::ok);
    request = 1; nonce = {};
    const auto hello = send(TransferOpcode::hello);
    LMDJ_CHECK(hello.payload[0] == std::byte{});
    nonce = hello.nonce;
    std::array<std::byte, 56> payload{};
    payload[0] = std::byte{7};
    payload[16] = std::byte{4}; // Four bytes, deliberately invalid runtime content.
    if (content) {
      const auto length = static_cast<std::uint64_t>(content->bytes.size());
      for (unsigned i = 0; i < 8; ++i) payload[16 + i] = std::byte((length >> (8U * i)) & 255U);
      const auto nibble = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
      for (std::size_t i = 0; i < 32; ++i)
        payload[24 + i] = std::byte((nibble(content->identity.sha256[2 * i]) << 4) |
                                   nibble(content->identity.sha256[2 * i + 1]));
    }
    LMDJ_CHECK(send(TransferOpcode::begin, payload).payload[0] == std::byte{});
  }
  void data() {
    std::array<std::byte, 26> payload{};
    payload[0] = std::byte{7};
    payload[24] = std::byte{'a'}; payload[25] = std::byte{'b'};
    LMDJ_CHECK(send(TransferOpcode::data, payload).payload[0] == std::byte{});
  }
};
void progress() {
  Fixture f;
  f.begin();
  LMDJ_CHECK(f.endpoint.display_status().session_active);
  LMDJ_CHECK(f.endpoint.display_status().receiving);
  f.data();
  LMDJ_CHECK(f.endpoint.display_status().received_bytes == 2);
  f.data(); // Exact duplicate, new request sequence.
  LMDJ_CHECK(f.endpoint.display_status().received_bytes == 2);
}
void timeout() {
  Fixture f;
  f.begin(); f.data();
  fake_usb::now_us += 6000000;
  f.endpoint.poll();
  const auto view = f.endpoint.display_status();
  LMDJ_CHECK(!view.receiving && view.received_bytes == 0);
  LMDJ_CHECK(view.failed);
  f.begin();
  LMDJ_CHECK(f.endpoint.display_status().receiving);
  LMDJ_CHECK(!f.endpoint.display_status().failed);
}
void cancel() {
  Fixture f;
  f.begin(); f.data();
  LMDJ_CHECK(f.host.cancel_receive() == HostResult::ok);
  f.endpoint.poll();
  const auto view = f.endpoint.display_status();
  LMDJ_CHECK(!view.receiving && view.received_bytes == 0);
  LMDJ_CHECK(!view.session_active);
  LMDJ_CHECK(f.host.read_status().content_bytes == 0);
  std::array<std::byte, 16> transfer_id{};
  transfer_id[0] = std::byte{7};
  LMDJ_CHECK(f.send(TransferOpcode::commit, transfer_id).payload[0] == std::byte{3});
  LMDJ_CHECK(!f.endpoint.display_status().session_active);
  LMDJ_CHECK(!f.endpoint.display_status().failed);
}

void rejection_and_retry() {
  Fixture f;
  f.begin(); f.data();
  std::array<std::byte, 26> rest{};
  rest[0] = std::byte{7}; rest[16] = std::byte{2};
  rest[24] = std::byte{'c'}; rest[25] = std::byte{'d'};
  LMDJ_CHECK(f.send(TransferOpcode::data, rest).payload[0] == std::byte{});
  std::array<std::byte, 16> transfer_id{};
  transfer_id[0] = std::byte{7};
  LMDJ_CHECK(f.send(TransferOpcode::commit, transfer_id).payload[0] != std::byte{});
  LMDJ_CHECK(f.endpoint.display_status().failed);
  LMDJ_CHECK(!f.endpoint.display_status().receiving);
  LMDJ_CHECK(f.endpoint.display_status().received_bytes == 0);
  LMDJ_CHECK(f.host.read_status().content_bytes == 0);

  const auto content = valid_content();
  f.begin(&content);
  for (std::size_t offset = 0; offset < content.bytes.size();) {
    const auto count = std::min<std::size_t>(128, content.bytes.size() - offset);
    std::array<std::byte, 24 + 128> packet{};
    packet[0] = std::byte{7};
    for (unsigned i = 0; i < 8; ++i)
      packet[16 + i] = std::byte((static_cast<std::uint64_t>(offset) >> (8U * i)) & 255U);
    std::copy_n(content.bytes.begin() + offset, count, packet.begin() + 24);
    LMDJ_CHECK(f.send(TransferOpcode::data, std::span(packet).first(24 + count)).payload[0] == std::byte{});
    offset += count;
    LMDJ_CHECK(f.endpoint.display_status().received_bytes == offset);
  }
  LMDJ_CHECK(f.send(TransferOpcode::commit, transfer_id).payload[0] == std::byte{});
  LMDJ_CHECK(!f.endpoint.display_status().receiving);
  LMDJ_CHECK(!f.endpoint.display_status().failed);
  LMDJ_CHECK(f.endpoint.display_status().received_bytes == 0);
  const auto status = f.host.read_status();
  LMDJ_CHECK(status.phase == lmdj::facade::RuntimePhase::ready);
  LMDJ_CHECK(status.content_bytes == content.bytes.size());
  LMDJ_CHECK(std::string_view(status.content_sha256.data(), 64) == content.identity.sha256);
}
void abort_and_new_session_clear_progress() {
  Fixture f;
  f.begin(); f.data();
  std::array<std::byte, 16> transfer_id{};
  transfer_id[0] = std::byte{7};
  LMDJ_CHECK(f.send(TransferOpcode::abort, transfer_id).payload[0] == std::byte{});
  LMDJ_CHECK(!f.endpoint.display_status().receiving);
  LMDJ_CHECK(f.endpoint.display_status().received_bytes == 0);
  LMDJ_CHECK(!f.endpoint.display_status().failed);
  f.begin(); f.data();
  f.request = 1; f.nonce = {};
  LMDJ_CHECK(f.send(TransferOpcode::hello).payload[0] == std::byte{});
  LMDJ_CHECK(f.endpoint.display_status().session_active);
  LMDJ_CHECK(!f.endpoint.display_status().receiving);
  LMDJ_CHECK(f.endpoint.display_status().received_bytes == 0);
}
}
int main(int argc, char** argv) {
  if (argc != 2) return 2;
  try {
    const std::string_view name = argv[1];
    if (name == "progress") progress();
    else if (name == "timeout") timeout();
    else if (name == "cancel") cancel();
    else if (name == "retry") rejection_and_retry();
    else if (name == "reset_progress") abort_and_new_session_clear_progress();
    else return 2;
  } catch (const std::exception& error) {
    return std::fprintf(stderr, "%s\n", error.what()), 1;
  }
  return 0;
}
