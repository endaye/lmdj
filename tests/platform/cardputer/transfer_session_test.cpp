// LMDJ_CHECK, not assert: the Release preset builds this target with NDEBUG,
// where assert() vanishes, its arguments read as unused variables under
// -Werror, and every scenario would verify nothing.
#include "apps/cardputer-host/main/transfer_session.hpp"
#include "tests/core/support/test.hpp"

#include <array>
#include <cstdio>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <vector>
#include <picosha2.h>

using namespace lmdj::cardputer;

namespace {
std::array<std::byte, 32> hash(std::span<const std::byte> bytes) {
  std::array<std::byte, 32> result{};
  picosha2::hash256_one_by_one hasher;
  const auto* begin = reinterpret_cast<const unsigned char*>(bytes.data());
  hasher.process(begin, begin + bytes.size());
  hasher.finish();
  const auto hex = picosha2::get_hash_hex_string(hasher);
  const auto nibble = [](char c) -> std::uint8_t {
    return c <= '9' ? static_cast<std::uint8_t>(c - '0')
                    : static_cast<std::uint8_t>(c - 'a' + 10);
  };
  for (std::size_t i = 0; i < result.size(); ++i)
    result[i] = std::byte((nibble(hex[i * 2]) << 4U) | nibble(hex[i * 2 + 1]));
  return result;
}

bool nonce_source(void*, std::array<std::byte, 16>& nonce) noexcept {
  for (std::size_t i = 0; i < nonce.size(); ++i) nonce[i] = std::byte(i + 1);
  return true;
}

struct Sink {
  std::vector<std::byte> published;
  static bool commit(void* context, std::span<const std::byte> bytes,
                     const TransferContentIdentity&) noexcept {
    auto& sink = *static_cast<Sink*>(context);
    sink.published.assign(bytes.begin(), bytes.end());
    return true;
  }
};

void lifecycle() {
  Sink sink;
  TransferSession session(64, Sink::commit, &sink, nonce_source, nullptr);
  std::array<std::byte, 16> zero{};
  LMDJ_CHECK(session.hello(1, zero) == TransferSessionResult::accepted);
  const auto nonce = session.nonce();
  std::array<std::byte, 16> transfer_id{};
  transfer_id[0] = std::byte{7};
  const std::array<std::byte, 4> content{std::byte{'o'}, std::byte{'k'},
                                         std::byte{'!'}, std::byte{'\n'}};
  TransferContentIdentity identity{transfer_id, hash(content), content.size()};
  LMDJ_CHECK(session.begin(2, nonce, transfer_id, identity, 100) ==
             TransferSessionResult::accepted);
  LMDJ_CHECK(session.data(3, nonce, transfer_id, 0, content, 200) ==
             TransferSessionResult::accepted);
  LMDJ_CHECK(session.commit(4, nonce, transfer_id, 300) ==
             TransferSessionResult::committed);
  LMDJ_CHECK(sink.published == std::vector<std::byte>(content.begin(), content.end()));
}

void stale() {
  Sink sink;
  TransferSession session(64, Sink::commit, &sink, nonce_source, nullptr);
  std::array<std::byte, 16> zero{};
  LMDJ_CHECK(session.hello(1, zero) == TransferSessionResult::accepted);
  const auto nonce = session.nonce();
  std::array<std::byte, 16> wrong = nonce;
  wrong[0] ^= std::byte{1};
  LMDJ_CHECK(session.begin(2, wrong, {}, {}, 0) == TransferSessionResult::stale_session);
  LMDJ_CHECK(session.next_request_id() == 2);
  LMDJ_CHECK(session.begin(4, nonce, {}, {}, 0) == TransferSessionResult::bad_request_id);
  LMDJ_CHECK(session.next_request_id() == 2);
  LMDJ_CHECK(session.hello(1, zero) == TransferSessionResult::accepted);
  LMDJ_CHECK(session.nonce() == nonce);
}
}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  try {
    const std::string scenario = argv[1];
    if (scenario == "lifecycle") lifecycle();
    else if (scenario == "stale") stale();
    else return 2;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
  return 0;
}
