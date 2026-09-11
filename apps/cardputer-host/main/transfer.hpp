#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace lmdj::cardputer {

inline constexpr std::size_t transfer_max_payload = 1024;
inline constexpr std::size_t transfer_header_bytes = 28;
inline constexpr std::size_t transfer_max_frame = transfer_header_bytes +
                                                    transfer_max_payload + 4;

enum class TransferOpcode : std::uint8_t {
  hello = 1,
  status = 2,
  begin = 3,
  data = 4,
  commit = 5,
  abort = 6,
};

enum class FrameDecode : std::uint8_t {
  ready,
  need_more,
  bad_magic,
  bad_header,
  bad_crc,
};

struct TransferFrame {
  std::uint8_t version{1};
  std::uint8_t opcode{};
  std::uint16_t payload_size{};
  std::uint32_t request_id{};
  std::array<std::byte, 16> nonce{};
  std::array<std::byte, transfer_max_payload> payload{};
};

std::uint32_t transfer_crc32(std::span<const std::byte> bytes) noexcept;

// Encodes exactly one bounded frame. `written` is unchanged on failure.
bool encode_transfer_frame(const TransferFrame& frame,
                           std::span<std::byte> output,
                           std::size_t& written) noexcept;

// Decodes from the start of a candidate frame. On bad magic the caller may
// discard one byte and retry; malformed/incomplete candidates never reach a
// handler. `consumed` is nonzero only for a bad magic candidate.
FrameDecode decode_transfer_frame(std::span<const std::byte> input,
                                  TransferFrame& frame,
                                  std::size_t& consumed) noexcept;

bool put_u64_le(std::span<std::byte> output, std::uint64_t value) noexcept;
bool get_u64_le(std::span<const std::byte> input, std::uint64_t& value) noexcept;

}  // namespace lmdj::cardputer
