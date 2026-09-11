#include "transfer_session.hpp"

#include <algorithm>

namespace lmdj::cardputer {

TransferSession::TransferSession(std::size_t maximum_bytes, CommitSink sink,
                                 void* sink_context, NonceSource nonce_source,
                                 void* nonce_context) noexcept
    : receiver_(maximum_bytes, sink, sink_context), nonce_source_(nonce_source),
      nonce_context_(nonce_context) {}

bool TransferSession::zero_nonce(std::span<const std::byte> nonce) noexcept {
  return nonce.size() == 16 && std::all_of(nonce.begin(), nonce.end(),
                                           [](std::byte value) { return value == std::byte{}; });
}

TransferSessionResult TransferSession::hello(
    std::uint32_t request_id, std::span<const std::byte> nonce) noexcept {
  if (request_id != 1 || !zero_nonce(nonce) || nonce_source_ == nullptr)
    return TransferSessionResult::bad_request_id;
  std::array<std::byte, 16> generated{};
  if (!nonce_source_(nonce_context_, generated) || zero_nonce(generated))
    return TransferSessionResult::wrong_state;
  receiver_.disconnect();
  nonce_ = generated;
  next_request_id_ = 2;
  active_ = true;
  return TransferSessionResult::accepted;
}

TransferSessionResult TransferSession::authorize(
    std::uint32_t request_id, std::span<const std::byte> nonce) noexcept {
  if (!active_ || nonce.size() != nonce_.size() ||
      !std::equal(nonce.begin(), nonce.end(), nonce_.begin()))
    return TransferSessionResult::stale_session;
  if (next_request_id_ == 0 || request_id != next_request_id_)
    return TransferSessionResult::bad_request_id;
  next_request_id_ = request_id == 0xffffffffU ? 0 : request_id + 1;
  return TransferSessionResult::accepted;
}

TransferSessionResult TransferSession::begin(
    std::uint32_t request_id, std::span<const std::byte> nonce,
    const std::array<std::byte, 16>& transfer_id,
    const TransferContentIdentity& identity, std::uint64_t now_ms) noexcept {
  const auto auth = authorize(request_id, nonce);
  if (auth != TransferSessionResult::accepted) return auth;
  const auto result = receiver_.begin(request_id, transfer_id, identity, now_ms);
  switch (result) {
    case TransferTransactionResult::accepted: return TransferSessionResult::accepted;
    case TransferTransactionResult::duplicate: return TransferSessionResult::duplicate;
    case TransferTransactionResult::resource_limit: return TransferSessionResult::resource_limit;
    default: return TransferSessionResult::wrong_state;
  }
}

TransferSessionResult TransferSession::data(
    std::uint32_t request_id, std::span<const std::byte> nonce,
    const std::array<std::byte, 16>& transfer_id, std::uint64_t offset,
    std::span<const std::byte> bytes, std::uint64_t now_ms) noexcept {
  const auto auth = authorize(request_id, nonce);
  if (auth != TransferSessionResult::accepted) return auth;
  const auto result = receiver_.data(request_id, transfer_id, offset, bytes, now_ms);
  switch (result) {
    case TransferTransactionResult::accepted: return TransferSessionResult::accepted;
    case TransferTransactionResult::duplicate: return TransferSessionResult::duplicate;
    case TransferTransactionResult::identity_mismatch: return TransferSessionResult::identity_mismatch;
    case TransferTransactionResult::malformed:
    case TransferTransactionResult::offset_mismatch: return TransferSessionResult::invalid_transfer;
    default: return TransferSessionResult::wrong_state;
  }
}

TransferSessionResult TransferSession::commit(
    std::uint32_t request_id, std::span<const std::byte> nonce,
    const std::array<std::byte, 16>& transfer_id, std::uint64_t now_ms) noexcept {
  const auto auth = authorize(request_id, nonce);
  if (auth != TransferSessionResult::accepted) return auth;
  const auto result = receiver_.commit(request_id, transfer_id, now_ms);
  switch (result) {
    case TransferTransactionResult::committed: return TransferSessionResult::committed;
    case TransferTransactionResult::identity_mismatch: return TransferSessionResult::identity_mismatch;
    case TransferTransactionResult::malformed: return TransferSessionResult::invalid_transfer;
    default: return TransferSessionResult::wrong_state;
  }
}

TransferSessionResult TransferSession::abort(
    std::uint32_t request_id, std::span<const std::byte> nonce,
    const std::array<std::byte, 16>& transfer_id) noexcept {
  const auto auth = authorize(request_id, nonce);
  if (auth != TransferSessionResult::accepted) return auth;
  return receiver_.abort(request_id, transfer_id) == TransferTransactionResult::aborted
             ? TransferSessionResult::aborted
             : TransferSessionResult::invalid_transfer;
}

bool TransferSession::expire(std::uint64_t now_ms) noexcept {
  return receiver_.expire(now_ms);
}

}  // namespace lmdj::cardputer
