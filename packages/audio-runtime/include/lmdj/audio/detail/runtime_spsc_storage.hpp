#pragma once

#include <atomic>
#include <cstddef>
#include <limits>
#include <memory>
#include <new>
#include <optional>
#include <type_traits>

namespace lmdj::audio::detail {

// Fixed capacity chosen once on control, before publication to audio. Only
// storage placement differs from FixedSpscQueue: the SPSC indices, ordering,
// sentinel and cache-line separation are unchanged. Never resize or move this
// object while either owner can access it; destruction requires quiescence.
template <typename T>
class RuntimeSpscStorage {
  static_assert(std::is_trivially_copyable_v<T>);
  static_assert(std::atomic<std::size_t>::is_always_lock_free);

 public:
  // Exact payload allocation, including the sentinel. The wrapper (including
  // aligned indices) belongs in its owner's sizeof; allocator overhead does not.
  static constexpr std::optional<std::size_t> allocation_bytes(
      std::size_t capacity) noexcept {
    if (capacity == 0 ||
        capacity >= std::numeric_limits<std::size_t>::max() / sizeof(T)) {
      return std::nullopt;
    }
    return (capacity + 1) * sizeof(T);
  }

  explicit RuntimeSpscStorage(std::size_t capacity)
      : storage_(checked_storage(capacity)),
        cells_(std::make_unique<T[]>(storage_)) {}

  std::size_t capacity() const noexcept { return storage_ - 1; }

  bool try_push(const T& value) noexcept {
    const auto write = write_.load(std::memory_order_relaxed);
    const auto next = increment(write);
    if (next == read_.load(std::memory_order_acquire)) return false;
    cells_[write] = value;
    write_.store(next, std::memory_order_release);
    return true;
  }

  bool try_pop(T& value) noexcept {
    const auto read = read_.load(std::memory_order_relaxed);
    if (read == write_.load(std::memory_order_acquire)) return false;
    value = cells_[read];
    read_.store(increment(read), std::memory_order_release);
    return true;
  }

  std::size_t size_approx() const noexcept {
    const auto read = read_.load(std::memory_order_acquire);
    const auto write = write_.load(std::memory_order_acquire);
    return write >= read ? write - read : storage_ - read + write;
  }

  std::size_t clear_quiescent() noexcept {
    const auto count = size_approx();
    read_.store(write_.load(std::memory_order_relaxed), std::memory_order_release);
    return count;
  }

 private:
  static std::size_t checked_storage(std::size_t capacity) {
    if (!allocation_bytes(capacity)) throw std::bad_array_new_length{};
    return capacity + 1;
  }
  std::size_t increment(std::size_t value) const noexcept {
    return value + 1 == storage_ ? 0 : value + 1;
  }

  const std::size_t storage_;
  const std::unique_ptr<T[]> cells_;
  alignas(64) std::atomic<std::size_t> read_{0};
  alignas(64) std::atomic<std::size_t> write_{0};
};

}  // namespace lmdj::audio::detail
