#include <lmdj/audio/detail/value_channel.hpp>

#include <array>
#include <atomic>
#include <cstdint>
#include <mutex>
#include <thread>

#include "tests/core/support/test.hpp"

namespace {
struct Value {
  std::uint64_t count = 0;
  std::uint64_t inverse = 0;
};
using Channel = lmdj::audio::detail::ValueChannel<Value>;
}

namespace lmdj::audio::detail {
struct ValueChannelTestAccess {
  static Value read_paused(
      const Channel& channel,
      std::atomic<bool>& copying,
      std::atomic<bool>& resume) {
    channel.acquire_read_slot();
    const auto& slot = channel.slots_[channel.reader_];
    const auto count = slot.count;
    copying.store(true, std::memory_order_release);
    while (!resume.load(std::memory_order_acquire)) {
      std::this_thread::yield();
    }
    return {count, slot.inverse};
  }
};
}

namespace {
void final_publication_survives_slot_recycling() {
  Channel channel;
  LMDJ_CHECK(channel.read().count == 0);
  // Authority is outside the output slots. Carry across the low 32 bits.
  for (std::uint64_t count = 0xfffffff0ULL; count <= 0x100000010ULL; ++count) {
    channel.publish({count, ~count});
  }
  const auto final = channel.read();
  LMDJ_CHECK(final.count == 0x100000010ULL);
  LMDJ_CHECK(final.inverse == ~final.count);
  LMDJ_CHECK(channel.read().count == final.count);
}

void paused_reader_does_not_block_or_tear_on_reuse_and_reset() {
  Channel channel;
  std::mutex readers;
  channel.publish({0x100000001ULL, ~0x100000001ULL});
  std::atomic<bool> copying{false};
  std::atomic<bool> resume{false};
  Value copied{};
  std::thread reader([&] {
    const std::lock_guard lock{readers};
    copied = lmdj::audio::detail::ValueChannelTestAccess::read_paused(
        channel, copying, resume);
  });
  while (!copying.load(std::memory_order_acquire)) {
    std::this_thread::yield();
  }
  // The reader owns its slot throughout. A whole engine epoch may reset while
  // it is paused; writer handoff publishes normally and never resets indices.
  for (std::uint64_t count = 1; count <= 65'537; ++count) {
    channel.publish({count, ~count});
  }
  channel.publish({0, ~std::uint64_t{0}});
  resume.store(true, std::memory_order_release);
  reader.join();
  LMDJ_CHECK(copied.count == 0x100000001ULL);
  LMDJ_CHECK(copied.inverse == ~copied.count);
  const auto reset = channel.read();
  LMDJ_CHECK(reset.count == 0);
  LMDJ_CHECK(reset.inverse == ~std::uint64_t{0});
}

void serialized_observers_share_one_consumer() {
  Channel channel;
  std::mutex readers;
  channel.publish({0, ~std::uint64_t{0}});
  std::atomic<bool> start{false};
  std::array<std::thread, 4> observers;
  for (auto& observer : observers) {
    observer = std::thread([&] {
      while (!start.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
      std::uint64_t previous = 0;
      for (int iteration = 0; iteration < 2'000; ++iteration) {
        const std::lock_guard lock{readers};
        const auto value = channel.read();
        LMDJ_CHECK(value.inverse == ~value.count);
        LMDJ_CHECK(value.count >= previous);
        previous = value.count;
      }
    });
  }
  start.store(true, std::memory_order_release);
  for (std::uint64_t count = 1; count <= 20'000; ++count) {
    channel.publish({count, ~count});
  }
  for (auto& observer : observers) {
    observer.join();
  }
  LMDJ_CHECK(channel.read().count == 20'000);
}
}

int main() {
  final_publication_survives_slot_recycling();
  paused_reader_does_not_block_or_tear_on_reuse_and_reset();
  serialized_observers_share_one_consumer();
}
