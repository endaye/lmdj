#pragma once

#include "transfer.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

namespace lmdj::cardputer {

struct TransferContentIdentity {
  std::array<std::byte, 16> transfer_id{};
  std::array<std::byte, 32> sha256{};
  std::uint64_t byte_length{};
  bool operator==(const TransferContentIdentity&) const = default;
};

enum class TransferTransactionResult : std::uint8_t {
  accepted,
  duplicate,
  committed,
  aborted,
  wrong_state,
  malformed,
  unsupported,
  identity_mismatch,
  offset_mismatch,
  resource_limit,
};

// The receiver owns only a bounded staging buffer. The sink is called once,
// after COMMIT has verified length and SHA-256; no partial bytes are exposed.
class TransferReceiver final {
 public:
  using CommitSink = bool (*)(void*, std::span<const std::byte>,
                              const TransferContentIdentity&) noexcept;

  TransferReceiver(std::size_t maximum_bytes, CommitSink sink,
                   void* sink_context) noexcept;
  TransferTransactionResult begin(std::uint32_t request_id,
                                  const TransferContentIdentity& identity) noexcept;
  // Protocol-facing overload. A transfer ID is independent of the wire
  // request sequence and the timeout clock is advanced only by new bytes.
  TransferTransactionResult begin(std::uint32_t request_id,
                                  const std::array<std::byte, 16>& transfer_id,
                                  const TransferContentIdentity& identity,
                                  std::uint64_t now_ms) noexcept;
  TransferTransactionResult data(std::uint32_t request_id, std::uint64_t offset,
                                 std::span<const std::byte> bytes) noexcept;
  TransferTransactionResult data(std::uint32_t request_id,
                                 const std::array<std::byte, 16>& transfer_id,
                                 std::uint64_t offset,
                                 std::span<const std::byte> bytes,
                                 std::uint64_t now_ms) noexcept;
  TransferTransactionResult commit(std::uint32_t request_id) noexcept;
  TransferTransactionResult commit(std::uint32_t request_id,
                                   const std::array<std::byte, 16>& transfer_id,
                                   std::uint64_t now_ms) noexcept;
  TransferTransactionResult abort(std::uint32_t request_id) noexcept;
  TransferTransactionResult abort(std::uint32_t request_id,
                                  const std::array<std::byte, 16>& transfer_id) noexcept;
  void disconnect() noexcept;
  // Returns true only when an active transaction was discarded. Repeated
  // calls after expiry are inert; this clock is not tied to audio deadlines.
  bool expire(std::uint64_t now_ms) noexcept;
  bool receiving() const noexcept { return receiving_; }
  std::uint64_t received_bytes() const noexcept { return received_; }
  const std::array<std::byte, 16>& transfer_id() const noexcept {
    return transfer_id_;
  }

 private:
  void clear() noexcept;
  std::size_t maximum_bytes_{};
  CommitSink sink_{};
  void* sink_context_{};
  std::vector<std::byte> staging_;
  std::array<std::byte, 16> transfer_id_{};
  TransferContentIdentity identity_{};
  std::uint32_t request_id_{};
  std::uint64_t received_{};
  std::uint64_t last_progress_ms_{};
  bool receiving_{};
};

}  // namespace lmdj::cardputer
