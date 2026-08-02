#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <type_traits>

namespace lmdj::audio::detail {

template <typename T, std::size_t Capacity>
class FixedSpscQueue {
  static_assert(Capacity > 0);
  static_assert(std::is_trivially_copyable_v<T>);
  static_assert(std::atomic<std::size_t>::is_always_lock_free);

 public:
  static consteval std::size_t capacity() noexcept { return Capacity; }

  bool try_push(const T& value) noexcept {
    const auto write = write_.load(std::memory_order_relaxed);
    const auto next = increment(write);
    if (next == read_.load(std::memory_order_acquire)) {
      return false;
    }
    cells_[write] = value;
    write_.store(next, std::memory_order_release);
    return true;
  }

  bool try_pop(T& value) noexcept {
    const auto read = read_.load(std::memory_order_relaxed);
    if (read == write_.load(std::memory_order_acquire)) {
      return false;
    }
    value = cells_[read];
    read_.store(increment(read), std::memory_order_release);
    return true;
  }

  std::size_t size_approx() const noexcept {
    const auto read = read_.load(std::memory_order_acquire);
    const auto write = write_.load(std::memory_order_acquire);
    return write >= read ? write - read : kStorage - read + write;
  }

  std::size_t clear_quiescent() noexcept {
    const auto count = size_approx();
    read_.store(write_.load(std::memory_order_relaxed),
                std::memory_order_release);
    return count;
  }

 private:
  static constexpr std::size_t kStorage = Capacity + 1;
  static constexpr std::size_t increment(std::size_t value) noexcept {
    return value + 1 == kStorage ? 0 : value + 1;
  }

  std::array<T, kStorage> cells_{};
  alignas(64) std::atomic<std::size_t> read_{0};
  alignas(64) std::atomic<std::size_t> write_{0};
};

}  // namespace lmdj::audio::detail
