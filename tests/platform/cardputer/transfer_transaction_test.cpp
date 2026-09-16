// LMDJ_CHECK, not assert: the Release preset builds this target with NDEBUG,
// where assert() vanishes, its arguments read as unused variables under
// -Werror, and every scenario would verify nothing.
#include "apps/cardputer-host/main/transfer_transaction.hpp"
#include "tests/core/support/test.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>
#include <picosha2.h>

using namespace lmdj::cardputer;

namespace {
struct Sink {
  std::vector<std::byte> bytes;
  std::uint64_t length{};
  bool accept{true};
  static bool commit(void* context, std::span<const std::byte> bytes,
                     const TransferContentIdentity& identity) noexcept {
    auto& self = *static_cast<Sink*>(context);
    if (!self.accept) return false;
    self.bytes.assign(bytes.begin(), bytes.end());
    self.length = identity.byte_length;
    return true;
  }
};

TransferContentIdentity identity(std::span<const std::byte> bytes) {
  TransferContentIdentity result;
  result.byte_length = bytes.size();
  picosha2::hash256_one_by_one hasher;
  const auto* begin = reinterpret_cast<const unsigned char*>(bytes.data());
  hasher.process(begin, begin + bytes.size());
  hasher.finish();
  const auto hex = picosha2::get_hash_hex_string(hasher);
  const auto nibble = [](char c) -> std::uint8_t {
    return c <= '9' ? static_cast<std::uint8_t>(c - '0')
                    : static_cast<std::uint8_t>(c - 'a' + 10);
  };
  for (std::size_t i = 0; i < result.sha256.size(); ++i)
    result.sha256[i] = std::byte((nibble(hex[i * 2]) << 4U) | nibble(hex[i * 2 + 1]));
  return result;
}
}

void run(const std::string& scenario) {
  const std::array<std::byte, 4> content{std::byte{'c'}, std::byte{'1'},
                                          std::byte{'!' }, std::byte{'\n'}};
  Sink sink;
  TransferReceiver receiver(content.size(), Sink::commit, &sink);
  auto expected = identity(content);
  if (scenario == "reject_identity") {
    auto wrong = expected;
    wrong.sha256[0] ^= std::byte{1};
    LMDJ_CHECK(receiver.begin(7, wrong) == TransferTransactionResult::accepted);
    LMDJ_CHECK(receiver.data(7, 0, content) == TransferTransactionResult::accepted);
    LMDJ_CHECK(receiver.commit(7) == TransferTransactionResult::identity_mismatch);
    LMDJ_CHECK(!receiver.receiving());
    return;
  }
  LMDJ_CHECK(receiver.begin(7, expected) == TransferTransactionResult::accepted);
  LMDJ_CHECK(receiver.begin(7, expected) == TransferTransactionResult::duplicate);
  LMDJ_CHECK(receiver.data(7, 1, std::span<const std::byte>{content}.subspan(1, 1)) ==
             TransferTransactionResult::offset_mismatch);
  LMDJ_CHECK(receiver.abort(7) == TransferTransactionResult::aborted);
  LMDJ_CHECK(!receiver.receiving());
  if (scenario == "disconnect") {
    LMDJ_CHECK(receiver.begin(8, expected) == TransferTransactionResult::accepted);
    LMDJ_CHECK(receiver.data(8, 0, std::span<const std::byte>{content}.subspan(0, 2)) ==
               TransferTransactionResult::accepted);
    receiver.disconnect();
    LMDJ_CHECK(!receiver.receiving());
    LMDJ_CHECK(receiver.begin(9, expected) == TransferTransactionResult::accepted);
    return;
  }
  LMDJ_CHECK(receiver.begin(10, expected) == TransferTransactionResult::accepted);
  LMDJ_CHECK(receiver.data(10, 0, std::span<const std::byte>{content}.subspan(0, 2)) ==
             TransferTransactionResult::accepted);
  LMDJ_CHECK(receiver.data(10, 2, std::span<const std::byte>{content}.subspan(2, 2)) ==
             TransferTransactionResult::accepted);
  LMDJ_CHECK(receiver.data(10, 0, std::span<const std::byte>{content}.subspan(0, 2)) ==
             TransferTransactionResult::duplicate);
  LMDJ_CHECK(receiver.commit(10) == TransferTransactionResult::committed);
  LMDJ_CHECK(sink.bytes.size() == content.size());
  LMDJ_CHECK(std::equal(sink.bytes.begin(), sink.bytes.end(), content.begin()));
  std::array<std::byte, 16> transfer_id{};
  for (std::size_t i = 0; i < transfer_id.size(); ++i)
    transfer_id[i] = std::byte(i + 1);
  auto timed_identity = identity(content);
  timed_identity.transfer_id = transfer_id;
  LMDJ_CHECK(receiver.begin(20, transfer_id, timed_identity, 100) ==
             TransferTransactionResult::accepted);
  std::array<std::byte, 16> wrong_transfer{};
  wrong_transfer[0] = std::byte{9};
  LMDJ_CHECK(receiver.abort(20, wrong_transfer) == TransferTransactionResult::wrong_state);
  LMDJ_CHECK(receiver.data(20, transfer_id, 0, {}, 150) ==
             TransferTransactionResult::malformed);
  LMDJ_CHECK(receiver.data(20, transfer_id, 0,
                           std::span<const std::byte>{content}.subspan(0, 2), 200) ==
             TransferTransactionResult::accepted);
  LMDJ_CHECK(receiver.data(20, transfer_id, 0,
                           std::span<const std::byte>{content}.subspan(0, 2), 4900) ==
             TransferTransactionResult::duplicate);
  LMDJ_CHECK(!receiver.expire(5199));
  LMDJ_CHECK(receiver.expire(5200));
  LMDJ_CHECK(!receiver.receiving());
}

int main(int argc, char** argv) {
  try {
    run(argc > 1 ? argv[1] : "happy");
  } catch (const std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
  return 0;
}
