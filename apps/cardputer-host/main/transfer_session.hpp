#pragma once

#include "transfer_transaction.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace lmdj::cardputer {

enum class TransferSessionResult : std::uint8_t {
  accepted,
  duplicate,
  wrong_state,
  stale_session,
  bad_request_id,
  invalid_transfer,
  committed,
  aborted,
  identity_mismatch,
  resource_limit,
};

// Session/request sequencing around the bounded transaction receiver. The
// nonce is an isolation marker, not an authentication key; entropy is injected
// by the Product Assembly so tests never fall back to a fixed seed.
class TransferSession final {
 public:
  using NonceSource = bool (*)(void*, std::array<std::byte, 16>&) noexcept;
  using CommitSink = TransferReceiver::CommitSink;

  TransferSession(std::size_t maximum_bytes, CommitSink sink, void* sink_context,
                  NonceSource nonce_source, void* nonce_context) noexcept;

  TransferSessionResult hello(std::uint32_t request_id,
                              std::span<const std::byte> nonce) noexcept;
  TransferSessionResult begin(std::uint32_t request_id,
                              std::span<const std::byte> nonce,
                              const std::array<std::byte, 16>& transfer_id,
                              const TransferContentIdentity& identity,
                              std::uint64_t now_ms) noexcept;
  TransferSessionResult data(std::uint32_t request_id,
                             std::span<const std::byte> nonce,
                             const std::array<std::byte, 16>& transfer_id,
                             std::uint64_t offset,
                             std::span<const std::byte> bytes,
                             std::uint64_t now_ms) noexcept;
  TransferSessionResult commit(std::uint32_t request_id,
                               std::span<const std::byte> nonce,
                               const std::array<std::byte, 16>& transfer_id,
                               std::uint64_t now_ms) noexcept;
  TransferSessionResult abort(std::uint32_t request_id,
                              std::span<const std::byte> nonce,
                              const std::array<std::byte, 16>& transfer_id) noexcept;
  bool expire(std::uint64_t now_ms) noexcept;

  bool active() const noexcept { return active_; }
  std::uint32_t next_request_id() const noexcept { return next_request_id_; }
  const std::array<std::byte, 16>& nonce() const noexcept { return nonce_; }
  bool receiving() const noexcept { return receiver_.receiving(); }

 private:
  TransferSessionResult authorize(std::uint32_t request_id,
                                  std::span<const std::byte> nonce) noexcept;
  static bool zero_nonce(std::span<const std::byte> nonce) noexcept;

  TransferReceiver receiver_;
  NonceSource nonce_source_{};
  void* nonce_context_{};
  std::array<std::byte, 16> nonce_{};
  std::uint32_t next_request_id_{1};
  bool active_{};
};

}  // namespace lmdj::cardputer
