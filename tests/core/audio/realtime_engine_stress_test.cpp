#include <lmdj/audio/realtime_engine.hpp>

#include <atomic>
#include <cstdint>
#include <thread>

#include "tests/core/support/test.hpp"

namespace {

void preserves_all_trigger_events_under_spsc_contention() {
  constexpr std::uint64_t kEvents = 1'000'000;
  lmdj::audio::detail::FixedSpscQueue<lmdj::audio::TriggerEvent, 1024> queue;
  std::atomic<bool> producer_done{false};

  std::thread producer([&] {
    for (std::uint64_t sequence = 0; sequence < kEvents; ++sequence) {
      while (!queue.try_push(lmdj::audio::TriggerEvent{sequence, 0, 100})) {
        std::this_thread::yield();
      }
    }
    producer_done.store(true, std::memory_order_release);
  });

  std::uint64_t expected = 0;
  while (expected < kEvents ||
         !producer_done.load(std::memory_order_acquire)) {
    lmdj::audio::TriggerEvent event{};
    if (!queue.try_pop(event)) {
      std::this_thread::yield();
      continue;
    }
    LMDJ_CHECK(event.sequence == expected);
    ++expected;
  }
  producer.join();
  LMDJ_CHECK(expected == kEvents);
  LMDJ_CHECK(queue.size_approx() == 0);
}

}  // namespace

int main() { preserves_all_trigger_events_under_spsc_contention(); }
