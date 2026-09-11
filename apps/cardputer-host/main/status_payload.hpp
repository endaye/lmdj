#pragma once

#include "runtime_host.hpp"

namespace lmdj::cardputer {

// Result (2), phase/error/armed/muted/volume/pads (6), uint64 length (8).
inline std::array<std::byte, 16> encode_status_payload(const HostStatus& status) noexcept {
  std::array<std::byte, 16> payload{};
  payload[2] = std::byte(static_cast<std::uint8_t>(status.phase));
  payload[3] = std::byte(static_cast<std::uint8_t>(status.error));
  payload[4] = std::byte(status.armed ? 1 : 0);
  payload[5] = std::byte(status.muted ? 1 : 0);
  payload[6] = std::byte(status.volume);
  payload[7] = std::byte(status.pad_count);
  for (std::size_t i = 8; i < payload.size(); ++i)
    payload[i] = std::byte((status.content_bytes >> (8 * (i - 8))) & 0xffU);
  return payload;
}

}  // namespace lmdj::cardputer
