#include <lmdj/audio/detail/fixed_spsc_queue.hpp>

#include <cstdint>

#include "tests/core/support/test.hpp"

namespace {
struct Event {
  std::uint64_t sequence;
};

void exact_capacity_and_fifo() {
  lmdj::audio::detail::FixedSpscQueue<Event, 1024> queue;
  static_assert(decltype(queue)::capacity() == 1024);
  for (std::uint64_t sequence = 0; sequence < 1024; ++sequence) {
    LMDJ_CHECK(queue.try_push(Event{sequence}));
  }
  LMDJ_CHECK(!queue.try_push(Event{1024}));
  LMDJ_CHECK(queue.size_approx() == 1024);
  for (std::uint64_t sequence = 0; sequence < 1024; ++sequence) {
    Event event{};
    LMDJ_CHECK(queue.try_pop(event));
    LMDJ_CHECK(event.sequence == sequence);
  }
  Event event{};
  LMDJ_CHECK(!queue.try_pop(event));
  LMDJ_CHECK(queue.size_approx() == 0);
}

void clear_requires_quiescence_and_reports_count() {
  lmdj::audio::detail::FixedSpscQueue<Event, 4> queue;
  LMDJ_CHECK(queue.try_push(Event{1}));
  LMDJ_CHECK(queue.try_push(Event{2}));
  LMDJ_CHECK(queue.clear_quiescent() == 2);
  LMDJ_CHECK(queue.size_approx() == 0);
}
}  // namespace

int main() {
  exact_capacity_and_fifo();
  clear_requires_quiescence_and_reports_count();
}
