#include <lmdj/audio/detail/fixed_spsc_queue.hpp>
#include <lmdj/audio/detail/runtime_spsc_storage.hpp>
#include <lmdj/audio/realtime_engine.hpp>

#include <array>
#include <cstdint>
#include <limits>

#include "tests/core/support/test.hpp"

namespace {
struct Event {
  std::uint64_t sequence;
};

using VoiceEvent = lmdj::audio::RuntimeVoiceStateEvent;
using VoiceState = lmdj::audio::RuntimeVoiceState;

void check_same_event(const VoiceEvent& actual, const VoiceEvent& expected) {
  LMDJ_CHECK(actual.sequence == expected.sequence);
  LMDJ_CHECK(actual.slot == expected.slot);
  LMDJ_CHECK(actual.state == expected.state);
  LMDJ_CHECK(actual.runtime_frame == expected.runtime_frame);
  LMDJ_CHECK(actual.source_frame == expected.source_frame);
}

VoiceEvent voice_event(std::uint64_t index) {
  return VoiceEvent{
      std::numeric_limits<std::uint64_t>::max() - index,
      static_cast<std::uint8_t>(index % 256),
      static_cast<VoiceState>(index % 3),
      (std::uint64_t{1} << 63) + index,
      std::numeric_limits<std::uint32_t>::max() -
          static_cast<std::uint32_t>(index),
  };
}

void voice_state_storage_uses_compact_cells() {
  constexpr auto capacity = lmdj::audio::kRealtimeVoiceStateCapacity;
  static_assert(capacity == 10'240);
  // 24-byte naturally aligned cells plus unchanged cache-line index overhead.
  // The old 32-byte cells exceed this bound by about 80 KiB.
  LMDJ_CHECK(sizeof(lmdj::audio::detail::RuntimeVoiceStateQueue<capacity>) <=
             24 * (capacity + 1) + 192);
}

void engine_does_not_embed_the_voice_backlog() {
  using namespace lmdj::audio;
  // A small-profile Engine must not still contain the default backlog inline.
  LMDJ_CHECK(sizeof(RealtimeEngine) <
             sizeof(detail::RuntimeVoiceStateQueue<kRealtimeVoiceStateCapacity>));
}

void runtime_storage_validates_allocation_size() {
  using Storage = lmdj::audio::detail::RuntimeSpscStorage<Event>;
  static_assert(alignof(Storage) >= 64);
  for (const std::size_t capacity : {1U, 128U, 1024U}) {
    LMDJ_CHECK(Storage::allocation_bytes(capacity) == (capacity + 1) * sizeof(Event));
  }
  const auto maximum_cells = std::numeric_limits<std::size_t>::max() / sizeof(Event);
  LMDJ_CHECK(Storage::allocation_bytes(maximum_cells - 1) == maximum_cells * sizeof(Event));
  for (const auto invalid : {std::size_t{0}, maximum_cells,
                             std::numeric_limits<std::size_t>::max()}) {
    LMDJ_CHECK(!Storage::allocation_bytes(invalid));
    bool rejected = false;
    try { Storage queue(invalid); }
    catch (const std::bad_array_new_length&) { rejected = true; }
    LMDJ_CHECK(rejected);
  }
}

void runtime_storage_preserves_fifo_and_wrap(std::size_t capacity) {
  lmdj::audio::detail::RuntimeSpscStorage<Event> queue(capacity);
  LMDJ_CHECK(queue.capacity() == capacity);
  Event actual{99};
  LMDJ_CHECK(!queue.try_pop(actual) && actual.sequence == 99);
  const auto event = [](std::uint64_t index) {
    return Event{std::numeric_limits<std::uint64_t>::max() - index};
  };
  for (std::size_t index = 0; index < capacity; ++index) {
    LMDJ_CHECK(queue.try_push(event(index)));
  }
  LMDJ_CHECK(queue.size_approx() == capacity);
  for (std::size_t index = 0; index < capacity * 3; ++index) {
    LMDJ_CHECK(!queue.try_push(event(99)));
    LMDJ_CHECK(queue.try_pop(actual));
    LMDJ_CHECK(actual.sequence == event(index).sequence);
    LMDJ_CHECK(queue.try_push(event(index + capacity)));
  }
  LMDJ_CHECK(queue.clear_quiescent() == capacity);
  LMDJ_CHECK(queue.size_approx() == 0);
  LMDJ_CHECK(queue.clear_quiescent() == 0);
  LMDJ_CHECK(queue.try_push(event(3)));
  LMDJ_CHECK(queue.try_pop(actual) && actual.sequence == event(3).sequence);
}

void sized_voice_storage_preserves_exact_capacity(std::size_t pending) {
  using namespace lmdj::audio;
  const auto capacity = 2 * pending + 128;
  detail::RuntimeVoiceStateStorage queue(true, pending);
  LMDJ_CHECK(queue.capacity() == capacity);
  LMDJ_CHECK(detail::RuntimeVoiceStateStorage::receipt_allocation_bytes(pending) ==
             (capacity + 1) * sizeof(detail::RuntimeVoiceStateCell));
  for (std::size_t index = 0; index < capacity; ++index) {
    LMDJ_CHECK(queue.try_push(voice_event(index)));
  }
  LMDJ_CHECK(!queue.try_push(voice_event(capacity)));
  for (std::size_t index = 0; index < capacity * 3; ++index) {
    VoiceEvent actual{};
    LMDJ_CHECK(queue.try_pop(actual));
    check_same_event(actual, voice_event(index));
    LMDJ_CHECK(queue.try_push(voice_event(index + capacity)));
    LMDJ_CHECK(!queue.try_push(voice_event(99)));
  }
  LMDJ_CHECK(queue.clear_quiescent() == capacity);
  LMDJ_CHECK(queue.size_approx() == 0);
  auto actual = voice_event(99);
  LMDJ_CHECK(!queue.try_pop(actual));
  check_same_event(actual, voice_event(99));
  LMDJ_CHECK(queue.try_push(voice_event(7)));
  LMDJ_CHECK(queue.try_pop(actual));
  check_same_event(actual, voice_event(7));
}

void selected_voice_storage_preserves_capacity_and_events(bool bounded) {
  using namespace lmdj::audio;
  static_assert(kRealtimeReceiptVoiceStateCapacity == 2176);
  const auto capacity = bounded ? kRealtimeReceiptVoiceStateCapacity
                                : kRealtimeVoiceStateCapacity;
  detail::RuntimeVoiceStateStorage queue(bounded);
  auto actual = voice_event(99);
  LMDJ_CHECK(!queue.try_pop(actual));
  check_same_event(actual, voice_event(99));
  for (std::size_t index = 0; index < capacity; ++index) {
    LMDJ_CHECK(queue.try_push(voice_event(index)));
  }
  LMDJ_CHECK(!queue.try_push(voice_event(capacity)));
  LMDJ_CHECK(queue.size_approx() == capacity);
  // Keep the queue full across two whole wraparounds, with a rejected push at
  // each boundary proving that failure did not overwrite the oldest event.
  for (std::size_t index = 0; index < capacity * 2; ++index) {
    LMDJ_CHECK(queue.try_pop(actual));
    check_same_event(actual, voice_event(index));
    LMDJ_CHECK(queue.try_push(voice_event(index + capacity)));
    LMDJ_CHECK(!queue.try_push(voice_event(99)));
  }
  LMDJ_CHECK(queue.clear_quiescent() == capacity);
  LMDJ_CHECK(queue.size_approx() == 0);
  LMDJ_CHECK(queue.try_push(voice_event(7)));
  LMDJ_CHECK(queue.try_pop(actual));
  check_same_event(actual, voice_event(7));
}

void voice_state_transport_preserves_boundary_values() {
  constexpr auto max64 = std::numeric_limits<std::uint64_t>::max();
  constexpr auto max32 = std::numeric_limits<std::uint32_t>::max();
  const std::array<VoiceEvent, 3> events{{
      {0, 0, VoiceState::started, max64, 0},
      {max64, 63, VoiceState::stopped, 0, max32},
      {(std::uint64_t{1} << 32) + 1, 255, VoiceState::completed,
       (std::uint64_t{1} << 63) + 7, (std::uint32_t{1} << 31) + 3},
  }};
  lmdj::audio::detail::RuntimeVoiceStateQueue<3> queue;
  for (const auto& event : events) {
    LMDJ_CHECK(queue.try_push(event));
  }
  for (const auto& expected : events) {
    VoiceEvent actual{};
    LMDJ_CHECK(queue.try_pop(actual));
    check_same_event(actual, expected);
  }
}

void voice_state_exact_capacity_and_fifo() {
  constexpr auto capacity = lmdj::audio::kRealtimeVoiceStateCapacity;
  lmdj::audio::detail::RuntimeVoiceStateQueue<capacity> queue;
  static_assert(decltype(queue)::capacity() == capacity);
  for (std::size_t index = 0; index < capacity; ++index) {
    LMDJ_CHECK(queue.try_push(voice_event(index)));
  }
  LMDJ_CHECK(!queue.try_push(voice_event(capacity)));
  LMDJ_CHECK(queue.size_approx() == capacity);
  for (std::size_t index = 0; index < capacity; ++index) {
    VoiceEvent actual{};
    LMDJ_CHECK(queue.try_pop(actual));
    check_same_event(actual, voice_event(index));
  }
  LMDJ_CHECK(queue.size_approx() == 0);
}

void voice_state_wraparound_preserves_pending_events() {
  lmdj::audio::detail::RuntimeVoiceStateQueue<3> queue;
  LMDJ_CHECK(queue.try_push(voice_event(0)));
  LMDJ_CHECK(queue.try_push(voice_event(1)));
  for (std::uint64_t index = 0; index < 32; ++index) {
    VoiceEvent actual{};
    LMDJ_CHECK(queue.try_pop(actual));
    check_same_event(actual, voice_event(index));
    LMDJ_CHECK(queue.try_push(voice_event(index + 2)));
    LMDJ_CHECK(queue.size_approx() == 2);
  }
  for (std::uint64_t index = 32; index < 34; ++index) {
    VoiceEvent actual{};
    LMDJ_CHECK(queue.try_pop(actual));
    check_same_event(actual, voice_event(index));
  }
}

void voice_state_empty_pop_leaves_output_unchanged() {
  lmdj::audio::detail::RuntimeVoiceStateQueue<1> queue;
  auto actual = voice_event(99);
  LMDJ_CHECK(!queue.try_pop(actual));
  check_same_event(actual, voice_event(99));
}

void voice_state_clear_and_reuse() {
  lmdj::audio::detail::RuntimeVoiceStateQueue<3> queue;
  for (std::uint64_t index = 0; index < 3; ++index) {
    LMDJ_CHECK(queue.try_push(voice_event(index)));
  }
  LMDJ_CHECK(queue.clear_quiescent() == 3);
  LMDJ_CHECK(queue.size_approx() == 0);
  VoiceEvent actual{};
  LMDJ_CHECK(!queue.try_pop(actual));
  LMDJ_CHECK(queue.clear_quiescent() == 0);
  LMDJ_CHECK(queue.try_push(voice_event(7)));
  LMDJ_CHECK(queue.try_pop(actual));
  check_same_event(actual, voice_event(7));
}

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
  runtime_storage_validates_allocation_size();
  for (const std::size_t pending : {1U, 128U, 1024U}) {
    runtime_storage_preserves_fifo_and_wrap(pending);
    sized_voice_storage_preserves_exact_capacity(pending);
  }
  engine_does_not_embed_the_voice_backlog();
  selected_voice_storage_preserves_capacity_and_events(false);
  selected_voice_storage_preserves_capacity_and_events(true);
  voice_state_storage_uses_compact_cells();
  voice_state_transport_preserves_boundary_values();
  voice_state_exact_capacity_and_fifo();
  voice_state_wraparound_preserves_pending_events();
  voice_state_empty_pop_leaves_output_unchanged();
  voice_state_clear_and_reuse();
  exact_capacity_and_fifo();
  clear_requires_quiescence_and_reports_count();
}
