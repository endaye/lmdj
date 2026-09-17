#include "apps/cardputer-host/main/observation_wire.hpp"
#include "tests/core/support/test.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace {
using namespace lmdj::cardputer::observation_wire;

Identity identity() {
  return {
      "1.0.59.0",
      "1.0.1",
      "0123456789abcdef0123456789abcdef01234567",
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  };
}

template <std::size_t N>
std::array<std::byte, N> filled(std::uint8_t value) {
  std::array<std::byte, N> result{};
  result.fill(std::byte(value));
  return result;
}

std::uint16_t read_u16(std::span<const std::byte> bytes, std::size_t offset) {
  return static_cast<std::uint16_t>(std::to_integer<std::uint8_t>(bytes[offset])) |
         static_cast<std::uint16_t>(std::to_integer<std::uint8_t>(bytes[offset + 1]) << 8U);
}

std::uint32_t read_u32(std::span<const std::byte> bytes, std::size_t offset) {
  return static_cast<std::uint32_t>(read_u16(bytes, offset)) |
         static_cast<std::uint32_t>(read_u16(bytes, offset + 2)) << 16U;
}

std::uint64_t read_u64(std::span<const std::byte> bytes, std::size_t offset) {
  std::uint64_t value = 0;
  for (std::size_t index = 0; index < 8; ++index)
    value |= static_cast<std::uint64_t>(
                 std::to_integer<std::uint8_t>(bytes[offset + index]))
             << (8U * index);
  return value;
}

std::string text(std::span<const std::byte> bytes, std::size_t offset,
                 std::size_t length) {
  return {reinterpret_cast<const char*>(bytes.data() + offset), length};
}

ExtendedStatus valid_status() {
  ExtendedStatus status;
  status.content_present = true;
  status.receiving = true;
  status.boot_nonce = filled<16>(0x10);
  status.phase = 2;
  status.error = 4;
  status.armed = true;
  status.muted = true;
  status.volume = 7;
  status.pad_count = 2;
  status.pad_pairs = {0, 1, 2, 3, 255, 255, 255, 255};
  status.maximum_encoded_bytes = 331176;
  status.maximum_pcm_bytes = 32768;
  status.maximum_frames = 256;
  status.maximum_pads = 4;
  status.maximum_events = 32;
  status.content_bytes = 0x8877665544332211ULL;
  status.content_sha256 = filled<32>(0xa1);
  status.transfer_id = filled<16>(0xb2);
  status.received_bytes = 64;
  status.expected_bytes = 128;
  status.observation_generation = 9;
  status.identity = identity();
  return status;
}

void valid_status_vector() {
  LMDJ_CHECK(status_max_bytes == 658);
  const auto status = valid_status();
  std::array<std::byte, 1024> output{};
  std::size_t written = 0;
  LMDJ_CHECK(encode_extended_status(status, output, written));
  LMDJ_CHECK(written == 425);
  const auto bytes = std::span<const std::byte>(output).first(written);
  LMDJ_CHECK(read_u16(bytes, 0) == 0);
  LMDJ_CHECK(std::to_integer<std::uint8_t>(bytes[2]) == 1);
  LMDJ_CHECK(std::to_integer<std::uint8_t>(bytes[3]) == 3);
  LMDJ_CHECK(read_u64(bytes, 36) == status.maximum_encoded_bytes);
  LMDJ_CHECK(read_u64(bytes, 44) == status.maximum_pcm_bytes);
  LMDJ_CHECK(read_u64(bytes, 64) == status.content_bytes);
  LMDJ_CHECK(read_u64(bytes, 120) == status.received_bytes);
  LMDJ_CHECK(read_u64(bytes, 128) == status.expected_bytes);
  LMDJ_CHECK(read_u64(bytes, 136) == status.observation_generation);
  LMDJ_CHECK(read_u16(bytes, 144) == 279);
  LMDJ_CHECK(text(bytes, 146, 279) ==
            R"({"product_build":"1.0.59.0","host_version":"1.0.1","revision":"0123456789abcdef0123456789abcdef01234567","assembly_lock_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","profile_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"})");
  LMDJ_CHECK(validate_extended_status(bytes, status.identity));
  LMDJ_CHECK(!validate_extended_status(bytes, Identity{
      "1.0.59.1", status.identity.host_version, status.identity.revision,
      status.identity.assembly_lock_sha256, status.identity.profile_sha256}));

  std::string maximum_build(241, 'x');
  auto maximum = status;
  maximum.identity.product_build = maximum_build;
  LMDJ_CHECK(encode_extended_status(maximum, output, written));
  LMDJ_CHECK(written == status_max_bytes);
  const auto maximum_bytes = std::span<const std::byte>(output).first(written);
  LMDJ_CHECK(read_u16(maximum_bytes, 144) == identity_limit);
  LMDJ_CHECK(validate_extended_status(maximum_bytes, maximum.identity));
}

void status_rejects_invalid_state() {
  std::array<std::byte, 1024> output{};
  std::size_t written = 0;
  auto status = valid_status();
  status.boot_nonce = {};
  LMDJ_CHECK(!encode_extended_status(status, output, written));
  status = valid_status();
  status.content_present = false;
  LMDJ_CHECK(!encode_extended_status(status, output, written));
  status = valid_status();
  status.receiving = false;
  LMDJ_CHECK(!encode_extended_status(status, output, written));
  status = valid_status();
  status.received_bytes = 129;
  LMDJ_CHECK(!encode_extended_status(status, output, written));
  status = valid_status();
  status.pad_pairs[4] = 0;
  LMDJ_CHECK(!encode_extended_status(status, output, written));
  status = valid_status();
  LMDJ_CHECK(!encode_extended_status(status, std::span<std::byte>(output).first(145), written));
  status = valid_status();
  status.identity.product_build = {};
  LMDJ_CHECK(!encode_extended_status(status, output, written));
}

void status_decoder_rejects_malformed() {
  const auto status = valid_status();
  std::array<std::byte, 1024> output{};
  std::size_t written = 0;
  LMDJ_CHECK(encode_extended_status(status, output, written));
  output[34] = std::byte{1};
  LMDJ_CHECK(!validate_extended_status(
      std::span<const std::byte>(output).first(written), status.identity));
  LMDJ_CHECK(encode_extended_status(status, output, written));
  output[72] = std::byte{};
  for (std::size_t index = 73; index < 104; ++index) output[index] = std::byte{};
  LMDJ_CHECK(!validate_extended_status(
      std::span<const std::byte>(output).first(written), status.identity));
  LMDJ_CHECK(encode_extended_status(status, output, written));
  output[3] = std::byte{0x80};
  LMDJ_CHECK(!validate_extended_status(
      std::span<const std::byte>(output).first(written), status.identity));
  LMDJ_CHECK(encode_extended_status(status, output, written));
  output[144] = std::byte{0};
  output[145] = std::byte{0};
  LMDJ_CHECK(!validate_extended_status(
      std::span<const std::byte>(output).first(written), status.identity));
  LMDJ_CHECK(!validate_extended_status(
      std::span<const std::byte>(output).first(written - 1), status.identity));
}

Diagnostics valid_diagnostics() {
  Diagnostics diagnostics;
  diagnostics.start_succeeded = true;
  diagnostics.quiescent = true;
  diagnostics.silent = true;
  diagnostics.diagnostics_available = true;
  diagnostics.boot_nonce = filled<16>(0x20);
  diagnostics.measured_generation = 11;
  diagnostics.content_bytes = 777;
  diagnostics.content_sha256 = filled<32>(0xc3);
  diagnostics.timing_flags = 7;
  diagnostics.attempts = 100;
  diagnostics.submitted = 98;
  diagnostics.stopped = 1;
  diagnostics.wait_failed = 1;
  diagnostics.convert_failed = 0;
  diagnostics.write_failed = 0;
  for (std::size_t index = 0; index < diagnostics.durations.size(); ++index) {
    diagnostics.durations[index] = {
        1000 + index, 0, 500 + index, 400 + static_cast<std::uint32_t>(index), true};
  }
  diagnostics.recording_samples = 100;
  diagnostics.recording_maximum_us = 3;
  diagnostics.recording_invalid = 0;
  diagnostics.identity = identity();
  return diagnostics;
}

void valid_diagnostics_vector() {
  LMDJ_CHECK(diagnostics_max_bytes == 850);
  const auto diagnostics = valid_diagnostics();
  std::array<std::byte, 1024> output{};
  std::size_t written = 0;
  LMDJ_CHECK(encode_diagnostics(diagnostics, output, written));
  LMDJ_CHECK(written == 617);
  const auto bytes = std::span<const std::byte>(output).first(written);
  LMDJ_CHECK(read_u16(bytes, 0) == 0);
  LMDJ_CHECK(std::to_integer<std::uint8_t>(bytes[2]) == 1);
  LMDJ_CHECK(std::to_integer<std::uint8_t>(bytes[3]) == 15);
  LMDJ_CHECK(read_u64(bytes, 20) == diagnostics.measured_generation);
  LMDJ_CHECK(read_u64(bytes, 28) == diagnostics.content_bytes);
  LMDJ_CHECK(read_u32(bytes, 68) == 7);
  LMDJ_CHECK(read_u64(bytes, 72) == diagnostics.attempts);
  LMDJ_CHECK(read_u64(bytes, 120) == diagnostics.durations[0].samples);
  LMDJ_CHECK(read_u64(bytes, 312) == diagnostics.recording_samples);
  LMDJ_CHECK(read_u64(bytes, 320) == diagnostics.recording_maximum_us);
  LMDJ_CHECK(read_u16(bytes, 336) == 279);
  LMDJ_CHECK(text(bytes, 338, 279).find(R"("profile_sha256":"bbbb)" ) != std::string::npos);
  LMDJ_CHECK(validate_diagnostics(bytes, diagnostics.identity));
  LMDJ_CHECK(!validate_diagnostics(bytes, Identity{
      "1.0.59.1", diagnostics.identity.host_version, diagnostics.identity.revision,
      diagnostics.identity.assembly_lock_sha256, diagnostics.identity.profile_sha256}));
}

void unavailable_diagnostics_is_explicit() {
  auto diagnostics = valid_diagnostics();
  diagnostics.diagnostics_available = false;
  diagnostics.timing_flags = 0;
  diagnostics.attempts = diagnostics.submitted = diagnostics.stopped = 0;
  diagnostics.wait_failed = diagnostics.convert_failed = diagnostics.write_failed = 0;
  diagnostics.durations = {};
  diagnostics.recording_samples = diagnostics.recording_maximum_us = diagnostics.recording_invalid = 0;
  std::array<std::byte, 1024> output{};
  std::size_t written = 0;
  LMDJ_CHECK(encode_diagnostics(diagnostics, output, written));
  LMDJ_CHECK(std::to_integer<std::uint8_t>(output[3]) == 7);
  LMDJ_CHECK(read_u32(std::span<const std::byte>(output), 68) == 0);
  diagnostics.timing_flags = 7;
  LMDJ_CHECK(!encode_diagnostics(diagnostics, output, written));
  diagnostics = valid_diagnostics();
  diagnostics.durations[0].p999_available = false;
  diagnostics.durations[0].p999_us = 1;
  LMDJ_CHECK(!encode_diagnostics(diagnostics, output, written));
  diagnostics = valid_diagnostics();
  diagnostics.measured_generation = 0;
  LMDJ_CHECK(!encode_diagnostics(diagnostics, output, written));
}

void diagnostics_decoder_rejects_malformed() {
  const auto diagnostics = valid_diagnostics();
  std::array<std::byte, 1024> output{};
  std::size_t written = 0;
  LMDJ_CHECK(encode_diagnostics(diagnostics, output, written));
  output[149] = std::byte{1};
  LMDJ_CHECK(!validate_diagnostics(
      std::span<const std::byte>(output).first(written), diagnostics.identity));
  LMDJ_CHECK(encode_diagnostics(diagnostics, output, written));
  output[3] = std::byte{0x80};
  LMDJ_CHECK(!validate_diagnostics(
      std::span<const std::byte>(output).first(written), diagnostics.identity));
  LMDJ_CHECK(encode_diagnostics(diagnostics, output, written));
  output[336] = std::byte{0};
  output[337] = std::byte{0};
  LMDJ_CHECK(!validate_diagnostics(
      std::span<const std::byte>(output).first(written), diagnostics.identity));
  LMDJ_CHECK(!validate_diagnostics(
      std::span<const std::byte>(output).first(written - 1), diagnostics.identity));
}

void escaped_identity_is_canonical() {
  auto status = valid_status();
  status.identity.product_build = "x\"\\\n";
  std::array<std::byte, 1024> output{};
  std::size_t written = 0;
  LMDJ_CHECK(encode_extended_status(status, output, written));
  const auto bytes = std::span<const std::byte>(output).first(written);
  LMDJ_CHECK(text(bytes, 146, read_u16(bytes, 144)).find(R"("product_build":"x\"\\\n")") != std::string::npos);
}

}  // namespace

int main(int argc, char** argv) {
  const std::string_view scenario = argc > 1 ? argv[1] : "all";
  if (scenario == "valid" || scenario == "all") valid_status_vector();
  if (scenario == "invalid" || scenario == "all") status_rejects_invalid_state();
  if (scenario == "decode" || scenario == "all") {
    status_decoder_rejects_malformed();
    diagnostics_decoder_rejects_malformed();
  }
  if (scenario == "diagnostics" || scenario == "all") valid_diagnostics_vector();
  if (scenario == "unavailable" || scenario == "all") unavailable_diagnostics_is_explicit();
  if (scenario == "escape" || scenario == "all") escaped_identity_is_canonical();
  return 0;
}
