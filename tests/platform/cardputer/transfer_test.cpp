#include "apps/cardputer-host/main/transfer.hpp"
#include "tests/core/support/test.hpp"

#include <array>
#include <cstdio>
#include <cstring>
#include <string>

namespace {
using namespace lmdj::cardputer;

TransferFrame sample(std::size_t payload_size = 7) {
  TransferFrame frame;
  frame.opcode = static_cast<std::uint8_t>(TransferOpcode::data);
  frame.request_id = 42;
  frame.payload_size = static_cast<std::uint16_t>(payload_size);
  for (std::size_t i = 0; i < frame.nonce.size(); ++i) frame.nonce[i] = std::byte(i + 1);
  for (std::size_t i = 0; i < payload_size; ++i) frame.payload[i] = std::byte(0xa0 + i);
  return frame;
}

void crc_matches_iso_hdlc() {
  constexpr std::array<std::byte, 9> input{
      std::byte{'1'}, std::byte{'2'}, std::byte{'3'}, std::byte{'4'}, std::byte{'5'},
      std::byte{'6'}, std::byte{'7'}, std::byte{'8'}, std::byte{'9'}};
  LMDJ_CHECK(transfer_crc32(input) == 0xcbf43926U);
}

void frame_roundtrip_and_payload_bound() {
  const auto input = sample(transfer_max_payload);
  std::array<std::byte, transfer_max_frame> wire{};
  std::size_t written = 0;
  LMDJ_CHECK(encode_transfer_frame(input, wire, written));
  LMDJ_CHECK(written == transfer_max_frame);
  TransferFrame output;
  std::size_t consumed = 99;
  LMDJ_CHECK(decode_transfer_frame(std::span<const std::byte>(wire.data(), written), output, consumed) ==
             FrameDecode::ready);
  LMDJ_CHECK(consumed == 0);
  LMDJ_CHECK(output.version == input.version && output.opcode == input.opcode);
  LMDJ_CHECK(output.request_id == input.request_id && output.nonce == input.nonce);
  LMDJ_CHECK(output.payload_size == input.payload_size);
  LMDJ_CHECK(std::equal(input.payload.begin(), input.payload.begin() + input.payload_size,
                        output.payload.begin()));
}

void invalid_limits_are_rejected_without_writing() {
  auto frame = sample();
  std::array<std::byte, transfer_max_frame> wire{};
  wire.fill(std::byte{0x5a});
  std::size_t written = 17;
  frame.payload_size = transfer_max_payload + 1;
  LMDJ_CHECK(!encode_transfer_frame(frame, wire, written));
  LMDJ_CHECK(written == 17 && wire[0] == std::byte{0x5a});
  frame = sample();
  frame.request_id = 0;
  LMDJ_CHECK(!encode_transfer_frame(frame, wire, written));
  frame.request_id = 1;
  frame.version = 2;
  LMDJ_CHECK(!encode_transfer_frame(frame, wire, written));
}

void malformed_crc_header_and_truncation_fail_closed() {
  const auto input = sample();
  std::array<std::byte, transfer_max_frame> wire{};
  std::size_t written = 0;
  LMDJ_CHECK(encode_transfer_frame(input, wire, written));
  TransferFrame output;
  std::size_t consumed = 0;
  LMDJ_CHECK(decode_transfer_frame(std::span<const std::byte>(wire.data(), written - 1), output, consumed) ==
             FrameDecode::need_more);
  wire[written - 1] ^= std::byte{1};
  LMDJ_CHECK(decode_transfer_frame(std::span<const std::byte>(wire.data(), written), output, consumed) ==
             FrameDecode::bad_crc);
  LMDJ_CHECK(encode_transfer_frame(input, wire, written));
  wire[4] = std::byte{2};
  LMDJ_CHECK(decode_transfer_frame(std::span<const std::byte>(wire.data(), written), output, consumed) ==
             FrameDecode::bad_header);
}

void bad_magic_requests_bounded_resynchronization() {
  const auto input = sample();
  std::array<std::byte, transfer_max_frame + 1> wire{};
  wire[0] = std::byte{'x'};
  std::size_t written = 0;
  LMDJ_CHECK(encode_transfer_frame(input, std::span<std::byte>(wire.data() + 1, transfer_max_frame), written));
  TransferFrame output;
  std::size_t consumed = 0;
  LMDJ_CHECK(decode_transfer_frame(wire, output, consumed) == FrameDecode::bad_magic);
  LMDJ_CHECK(consumed == 1);
  LMDJ_CHECK(decode_transfer_frame(std::span<const std::byte>(wire.data() + 1, written), output, consumed) ==
             FrameDecode::ready);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  try {
    const std::string scenario = argv[1];
    if (scenario == "crc") crc_matches_iso_hdlc();
    else if (scenario == "roundtrip") frame_roundtrip_and_payload_bound();
    else if (scenario == "limits") invalid_limits_are_rejected_without_writing();
    else if (scenario == "malformed") malformed_crc_header_and_truncation_fail_closed();
    else if (scenario == "resync") bad_magic_requests_bounded_resynchronization();
    else return 2;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
  return 0;
}
