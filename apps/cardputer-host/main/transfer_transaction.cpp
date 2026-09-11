#include "transfer_transaction.hpp"

#include <algorithm>
#include <picosha2.h>

namespace lmdj::cardputer {
namespace {
std::array<std::byte, 32> digest(std::span<const std::byte> bytes) noexcept {
  std::array<std::byte, 32> result{};
  try {
    picosha2::hash256_one_by_one hasher;
    if (!bytes.empty()) {
      const auto* begin = reinterpret_cast<const unsigned char*>(bytes.data());
      hasher.process(begin, begin + bytes.size());
    }
    hasher.finish();
    const auto hex = picosha2::get_hash_hex_string(hasher);
    for (std::size_t i = 0; i < result.size(); ++i) {
      const auto nibble = [](char c) -> std::uint8_t {
        return c <= '9' ? static_cast<std::uint8_t>(c - '0')
                        : static_cast<std::uint8_t>(c - 'a' + 10);
      };
      result[i] = std::byte((nibble(hex[i * 2]) << 4U) | nibble(hex[i * 2 + 1]));
    }
  } catch (...) {
    result.fill(std::byte{0});
  }
  return result;
}
}

TransferReceiver::TransferReceiver(std::size_t maximum_bytes, CommitSink sink,
                                   void* sink_context) noexcept
    : maximum_bytes_(maximum_bytes), sink_(sink), sink_context_(sink_context) {}

void TransferReceiver::clear() noexcept {
  staging_.clear();
  transfer_id_ = {};
  identity_ = {};
  request_id_ = 0;
  received_ = 0;
  last_progress_ms_ = 0;
  receiving_ = false;
}

TransferTransactionResult TransferReceiver::begin(
    std::uint32_t request_id, const TransferContentIdentity& identity) noexcept {
  std::array<std::byte, 16> legacy_id{};
  legacy_id[0] = std::byte{1};
  return begin(request_id, legacy_id, identity, 0);
}

TransferTransactionResult TransferReceiver::begin(
    std::uint32_t request_id, const std::array<std::byte, 16>& transfer_id,
    const TransferContentIdentity& identity, std::uint64_t now_ms) noexcept {
  if (request_id == 0 || identity.byte_length > maximum_bytes_ || sink_ == nullptr ||
      transfer_id == std::array<std::byte, 16>{} ||
      (identity.transfer_id != std::array<std::byte, 16>{} &&
       identity.transfer_id != transfer_id))
    return TransferTransactionResult::unsupported;
  if (receiving_) {
    if (request_id == request_id_ && transfer_id == transfer_id_ && identity == identity_)
      return TransferTransactionResult::duplicate;
    return TransferTransactionResult::wrong_state;
  }
  try {
    staging_.assign(static_cast<std::size_t>(identity.byte_length), std::byte{0});
  } catch (...) {
    clear();
    return TransferTransactionResult::resource_limit;
  }
  transfer_id_ = transfer_id;
  identity_ = identity;
  request_id_ = request_id;
  last_progress_ms_ = now_ms;
  receiving_ = true;
  return TransferTransactionResult::accepted;
}

TransferTransactionResult TransferReceiver::data(
    std::uint32_t request_id, const std::array<std::byte, 16>& transfer_id,
    std::uint64_t offset, std::span<const std::byte> bytes,
    std::uint64_t now_ms) noexcept {
  (void)request_id;
  if (transfer_id != transfer_id_) return TransferTransactionResult::wrong_state;
  if (bytes.empty()) return TransferTransactionResult::malformed;
  // The session owns the wire request sequence; the transaction receiver's
  // stored request ID is only the legacy transaction handle.
  const auto result = data(request_id_, offset, bytes);
  // Exact duplicate chunks do not count as progress and cannot keep a
  // stalled transaction alive.
  if (result == TransferTransactionResult::accepted && !bytes.empty())
    last_progress_ms_ = now_ms;
  return result;
}

TransferTransactionResult TransferReceiver::data(
    std::uint32_t request_id, std::uint64_t offset,
    std::span<const std::byte> bytes) noexcept {
  if (!receiving_ || request_id != request_id_) return TransferTransactionResult::wrong_state;
  if (offset > received_ || offset > identity_.byte_length ||
      bytes.size() > identity_.byte_length - offset)
    return TransferTransactionResult::offset_mismatch;
  if (offset < received_) {
    const auto overlap = std::min<std::uint64_t>(received_ - offset, bytes.size());
    if (!std::equal(bytes.begin(), bytes.begin() + static_cast<std::ptrdiff_t>(overlap),
                    staging_.begin() + static_cast<std::ptrdiff_t>(offset)))
      return TransferTransactionResult::malformed;
    if (overlap == bytes.size()) return TransferTransactionResult::duplicate;
    bytes = bytes.subspan(static_cast<std::size_t>(overlap));
    offset += overlap;
  }
  if (offset != received_) return TransferTransactionResult::offset_mismatch;
  std::copy(bytes.begin(), bytes.end(), staging_.begin() + static_cast<std::ptrdiff_t>(offset));
  received_ += bytes.size();
  return TransferTransactionResult::accepted;
}

TransferTransactionResult TransferReceiver::commit(std::uint32_t request_id) noexcept {
  if (!receiving_ || request_id != request_id_) return TransferTransactionResult::wrong_state;
  if (received_ != identity_.byte_length) return TransferTransactionResult::malformed;
  if (digest(staging_) != identity_.sha256) {
    clear();
    return TransferTransactionResult::identity_mismatch;
  }
  const bool published = sink_(sink_context_, staging_, identity_);
  clear();
  return published ? TransferTransactionResult::committed
                   : TransferTransactionResult::malformed;
}

TransferTransactionResult TransferReceiver::commit(
    std::uint32_t request_id, const std::array<std::byte, 16>& transfer_id,
    std::uint64_t now_ms) noexcept {
  (void)request_id;
  (void)now_ms;
  if (transfer_id != transfer_id_) return TransferTransactionResult::wrong_state;
  return commit(request_id_);
}

TransferTransactionResult TransferReceiver::abort(std::uint32_t request_id) noexcept {
  if (!receiving_ || request_id != request_id_) return TransferTransactionResult::wrong_state;
  clear();
  return TransferTransactionResult::aborted;
}

TransferTransactionResult TransferReceiver::abort(
    std::uint32_t request_id,
    const std::array<std::byte, 16>& transfer_id) noexcept {
  (void)request_id;
  if (transfer_id != transfer_id_) return TransferTransactionResult::wrong_state;
  return abort(request_id_);
}

void TransferReceiver::disconnect() noexcept { clear(); }

bool TransferReceiver::expire(std::uint64_t now_ms) noexcept {
  if (!receiving_ || now_ms < last_progress_ms_ ||
      now_ms - last_progress_ms_ < 5000) return false;
  clear();
  return true;
}

}  // namespace lmdj::cardputer
