#pragma once

#include <array>
#include <atomic>
#include <cstdint>
#include <type_traits>

namespace lmdj::audio::detail {

// One serialized writer and one serialized reader, with independent ownership
// of W and R. Multiple callers must serialize read() externally. Never reset
// the indices: a reader may retain R across a quiescent writer handoff.
// Payload must be values only (no resource lifetime transferred by the copy).
template <typename Value>
class ValueChannel final {
  static_assert(std::is_trivially_copyable_v<Value>);
  static_assert(std::atomic<std::uint32_t>::is_always_lock_free);

 public:
  void publish(const Value& value) noexcept {
    slots_[writer_] = value;
    // release publishes the full value; acquire receives a reader's old slot
    // only after the reader has finished copying it.
    writer_ = middle_.exchange(writer_ | kDirty, std::memory_order_acq_rel) &
              kIndex;
  }

  Value read() const noexcept {
    acquire_read_slot();
    return slots_[reader_];
  }

 private:
  // Lets deterministic unit tests pause partway through the value copy without
  // adding callbacks, branches or test hooks to the production publication path.
  friend struct ValueChannelTestAccess;
  void acquire_read_slot() const noexcept {
    if ((middle_.load(std::memory_order_acquire) & kDirty) != 0) {
      reader_ = middle_.exchange(reader_, std::memory_order_acq_rel) & kIndex;
    }
  }

  static constexpr std::uint32_t kDirty = 4;
  static constexpr std::uint32_t kIndex = 3;
  std::array<Value, 3> slots_{};
  std::uint32_t writer_ = 0;
  mutable std::uint32_t reader_ = 1;
  mutable std::atomic<std::uint32_t> middle_{2};
};

}  // namespace lmdj::audio::detail
