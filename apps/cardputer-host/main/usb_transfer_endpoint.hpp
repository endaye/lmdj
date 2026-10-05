#pragma once

#include "runtime_host.hpp"
#include "transfer_session.hpp"
#include "screen_view.hpp"

#ifdef ESP_PLATFORM

#include <array>
#include <cstddef>
#include <cstdint>

namespace lmdj::cardputer {

// Serialized USB Serial/JTAG endpoint. It owns only fixed-size framing
// storage; TransferSession owns the bounded content staging allocation.
class UsbTransferEndpoint final {
 public:
  UsbTransferEndpoint(RuntimeHost& host, std::size_t maximum_content_bytes) noexcept;
  bool install() noexcept;
  void poll() noexcept;
  ScreenTransfer display_status() const noexcept {
    return {session_.active(), session_.receiving(), session_.received_bytes(), failed_};
  }

 private:
  static bool nonce_source(void*, std::array<std::byte, 16>&) noexcept;
  static bool commit_sink(void*, std::span<const std::byte>,
                          const TransferContentIdentity&) noexcept;
  void handle_frame(const TransferFrame& frame) noexcept;
  void record_result(TransferSessionResult result) noexcept;
  void respond(std::uint8_t opcode, std::uint32_t request_id,
               std::span<const std::byte> payload) noexcept;
  void respond_result_with_extra(std::uint8_t opcode, std::uint32_t request_id,
                                 TransferSessionResult result,
                                 std::span<const std::byte> extra) noexcept;
  void respond_result(std::uint8_t opcode, std::uint32_t request_id,
                     TransferSessionResult result) noexcept;
  std::uint64_t now_ms() const noexcept;

  RuntimeHost& host_;
  TransferSession session_;
  std::array<std::byte, transfer_max_frame * 2> input_{};
  std::size_t input_size_{};
  std::array<std::byte, transfer_max_frame> output_{};
  std::uint64_t received_offset_{};
  bool installed_{};
  bool failed_{};
};

}  // namespace lmdj::cardputer

#endif
