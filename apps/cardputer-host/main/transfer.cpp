#include "transfer.hpp"

#include <algorithm>

namespace lmdj::cardputer {
namespace {
constexpr std::array<std::byte, 4> kMagic{
    std::byte{'L'}, std::byte{'M'}, std::byte{'C'}, std::byte{'P'}};

std::uint16_t read_u16(const std::byte* bytes) noexcept {
  return static_cast<std::uint16_t>(std::to_integer<std::uint8_t>(bytes[0])) |
         static_cast<std::uint16_t>(std::to_integer<std::uint8_t>(bytes[1]) << 8U);
}
std::uint32_t read_u32(const std::byte* bytes) noexcept {
  return static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(bytes[0])) |
         (static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(bytes[1])) << 8U) |
         (static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(bytes[2])) << 16U) |
         (static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(bytes[3])) << 24U);
}
void write_u16(std::byte* bytes, std::uint16_t value) noexcept {
  bytes[0] = std::byte(value & 0xffU);
  bytes[1] = std::byte((value >> 8U) & 0xffU);
}
void write_u32(std::byte* bytes, std::uint32_t value) noexcept {
  for (std::size_t i = 0; i < 4; ++i) bytes[i] = std::byte((value >> (8U * i)) & 0xffU);
}
bool valid_opcode(std::uint8_t opcode) noexcept {
  return (opcode >= 1U && opcode <= 6U) ||
         (opcode >= 0x81U && opcode <= 0x86U);
}
}  // namespace

std::uint32_t transfer_crc32(std::span<const std::byte> bytes) noexcept {
  std::uint32_t crc = 0xffffffffU;
  for (const auto byte : bytes) {
    crc ^= std::to_integer<std::uint8_t>(byte);
    for (int bit = 0; bit < 8; ++bit)
      crc = (crc & 1U) != 0U ? (crc >> 1U) ^ 0xedb88320U : crc >> 1U;
  }
  return crc ^ 0xffffffffU;
}

bool encode_transfer_frame(const TransferFrame& frame,
                           std::span<std::byte> output,
                           std::size_t& written) noexcept {
  if (frame.version != 1 || !valid_opcode(frame.opcode) || frame.request_id == 0 ||
      frame.payload_size > transfer_max_payload || output.size() <
          transfer_header_bytes + frame.payload_size + 4) return false;
  const auto size = transfer_header_bytes + frame.payload_size + 4;
  std::copy(kMagic.begin(), kMagic.end(), output.begin());
  output[4] = std::byte(frame.version);
  output[5] = std::byte(frame.opcode);
  write_u16(output.data() + 6, frame.payload_size);
  write_u32(output.data() + 8, frame.request_id);
  std::copy(frame.nonce.begin(), frame.nonce.end(), output.begin() + 12);
  std::copy_n(frame.payload.begin(), frame.payload_size, output.begin() + 28);
  write_u32(output.data() + 28 + frame.payload_size,
            transfer_crc32(std::span<const std::byte>(output.data(), 28 + frame.payload_size)));
  written = size;
  return true;
}

FrameDecode decode_transfer_frame(std::span<const std::byte> input,
                                  TransferFrame& frame,
                                  std::size_t& consumed) noexcept {
  consumed = 0;
  if (input.size() < 4) return FrameDecode::need_more;
  if (!std::equal(kMagic.begin(), kMagic.end(), input.begin())) {
    consumed = 1;
    return FrameDecode::bad_magic;
  }
  if (input.size() < transfer_header_bytes) return FrameDecode::need_more;
  const auto version = std::to_integer<std::uint8_t>(input[4]);
  const auto opcode = std::to_integer<std::uint8_t>(input[5]);
  const auto payload_size = read_u16(input.data() + 6);
  const auto request_id = read_u32(input.data() + 8);
  if (version != 1 || !valid_opcode(opcode) || request_id == 0 ||
      payload_size > transfer_max_payload) return FrameDecode::bad_header;
  const auto size = transfer_header_bytes + payload_size + 4;
  if (input.size() < size) return FrameDecode::need_more;
  if (read_u32(input.data() + 28 + payload_size) !=
      transfer_crc32(input.first(28 + payload_size))) return FrameDecode::bad_crc;
  frame.version = version;
  frame.opcode = opcode;
  frame.payload_size = payload_size;
  frame.request_id = request_id;
  std::copy_n(input.begin() + 12, 16, frame.nonce.begin());
  std::copy_n(input.begin() + 28, payload_size, frame.payload.begin());
  return FrameDecode::ready;
}

bool put_u64_le(std::span<std::byte> output, std::uint64_t value) noexcept {
  if (output.size() < 8) return false;
  for (std::size_t i = 0; i < 8; ++i) output[i] = std::byte((value >> (8U * i)) & 0xffU);
  return true;
}

bool get_u64_le(std::span<const std::byte> input, std::uint64_t& value) noexcept {
  if (input.size() < 8) return false;
  value = 0;
  for (std::size_t i = 0; i < 8; ++i)
    value |= static_cast<std::uint64_t>(std::to_integer<std::uint8_t>(input[i])) << (8U * i);
  return true;
}

}  // namespace lmdj::cardputer
