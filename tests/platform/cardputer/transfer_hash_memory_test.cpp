#include "apps/cardputer-host/main/transfer_transaction.hpp"
#include "apps/cardputer-host/main/transfer_session.hpp"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>
#include <string_view>

namespace {
std::size_t allocation_limit = std::numeric_limits<std::size_t>::max();
std::size_t maximum_request{};
void require(bool value) {
  if (!value) {
    std::fputs("why: bounded transfer integrity invariant failed; remedy: inspect hash allocation and sink publication\n", stderr);
    std::abort();
  }
}
void* allocate(std::size_t bytes) {
  maximum_request = std::max(maximum_request, bytes);
  if (bytes > allocation_limit) throw std::bad_alloc{};
  if (void* result = std::malloc(bytes == 0 ? 1 : bytes)) return result;
  throw std::bad_alloc{};
}
struct Sink {
  unsigned calls{};
  static bool commit(void* context, std::span<const std::byte> bytes,
                     const lmdj::cardputer::TransferContentIdentity& identity) noexcept {
    auto& self = *static_cast<Sink*>(context);
    require(bytes.size() == 96808 && identity.byte_length == bytes.size());
    for (std::size_t i = 0; i < bytes.size(); ++i)
      require(bytes[i] == std::byte(i % 251));
    ++self.calls;
    return true;
  }
};
}
void* operator new(std::size_t bytes) { return allocate(bytes); }
void* operator new[](std::size_t bytes) { return allocate(bytes); }
void operator delete(void* value) noexcept { std::free(value); }
void operator delete[](void* value) noexcept { std::free(value); }
void operator delete(void* value, std::size_t) noexcept { std::free(value); }
void operator delete[](void* value, std::size_t) noexcept { std::free(value); }

int main(int argc, char** argv) {
  using namespace lmdj::cardputer;
  const std::string_view scenario = argc > 1 ? argv[1] : "bounded";
  std::vector<std::byte> content(96808);
  for (std::size_t i = 0; i < content.size(); ++i) content[i] = std::byte(i % 251);
  TransferContentIdentity identity;
  identity.byte_length = content.size();
  // Independent Python hashlib oracle for bytes(i % 251 for i in range(96808)).
  constexpr std::string_view hex = "91cfc690a6e677c9cee5cdbc6e56e591dc0b3cb23c0805ecc84dbcaa8c8d6419";
  const auto nibble = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
  for (std::size_t i = 0; i < 32; ++i)
    identity.sha256[i] = std::byte(nibble(hex[i * 2]) * 16 + nibble(hex[i * 2 + 1]));
  Sink sink;
  if (scenario == "session_allocation_failure") {
    const auto nonce_source = [](void*, std::array<std::byte, 16>& nonce) noexcept {
      nonce.fill(std::byte{1});
      return true;
    };
    TransferSession session(content.size(), Sink::commit, &sink, nonce_source, nullptr);
    const std::array<std::byte, 16> zero{};
    auto transfer_id = zero;
    transfer_id[0] = std::byte{1};
    require(session.hello(1, zero) == TransferSessionResult::accepted);
    require(session.begin(2, session.nonce(), transfer_id, identity, 0) ==
            TransferSessionResult::accepted);
    require(session.data(3, session.nonce(), transfer_id, 0, content, 1) ==
            TransferSessionResult::accepted);
    allocation_limit = 0;
    const auto result = session.commit(4, session.nonce(), transfer_id, 2);
    allocation_limit = std::numeric_limits<std::size_t>::max();
    require(result == TransferSessionResult::resource_limit && sink.calls == 0);
    return 0;
  }
  TransferReceiver receiver(content.size(), Sink::commit, &sink);
  auto load = [&] {
    require(receiver.begin(7, identity) == TransferTransactionResult::accepted);
    for (std::size_t offset = 0; offset < content.size(); offset += 1000)
      require(receiver.data(7, offset, std::span(content).subspan(
          offset, std::min<std::size_t>(1000, content.size() - offset))) ==
          TransferTransactionResult::accepted);
  };
  if (scenario == "corrupt") content.back() ^= std::byte{1};
  load();
  maximum_request = 0;
  allocation_limit = scenario == "allocation_failure" ? 0 : 2048;
  const auto result = receiver.commit(7);
  allocation_limit = std::numeric_limits<std::size_t>::max();
  require(!receiver.receiving());
  if (scenario == "allocation_failure") {
    require(result == TransferTransactionResult::resource_limit && sink.calls == 0);
    load();
    require(receiver.commit(7) == TransferTransactionResult::committed && sink.calls == 1);
  } else if (scenario == "corrupt") {
    require(result == TransferTransactionResult::identity_mismatch && sink.calls == 0);
  } else {
    require(result == TransferTransactionResult::committed && sink.calls == 1);
    require(maximum_request <= 2048);
  }
}
