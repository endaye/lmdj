#pragma once

#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
#include <atomic>
#include <chrono>
#include <cstdint>

namespace lmdj::facade::detail::testing {
// Typed testable-library pause only. The captured clock and durable result are
// real; this gate never supplies a successful result, receipt or replacement
// clock. Its context must outlive the actual worker and all retained work.
struct PatternOpeningTestGate {
  std::atomic<bool> entered{false};
  std::atomic<bool> released{false};
  std::atomic<std::int64_t> completed_stamp{0};
  void release() noexcept {
    released.store(true, std::memory_order_release);
    released.notify_all();
  }
};
inline std::atomic<PatternOpeningTestGate*> opening_test_gate{nullptr};
inline void install_pattern_opening_test_gate(PatternOpeningTestGate* gate) noexcept {
  opening_test_gate.store(gate, std::memory_order_release);
}
inline void pause_opening_before_publication(
    std::chrono::steady_clock::time_point completed_at) noexcept {
  const auto gate = opening_test_gate.load(std::memory_order_acquire);
  if (!gate) return;
  gate->completed_stamp.store(std::chrono::duration_cast<std::chrono::nanoseconds>(
      completed_at.time_since_epoch()).count(), std::memory_order_release);
  gate->entered.store(true, std::memory_order_release);
  while (!gate->released.load(std::memory_order_acquire))
    gate->released.wait(false, std::memory_order_acquire);
}
}  // namespace lmdj::facade::detail::testing
#endif
