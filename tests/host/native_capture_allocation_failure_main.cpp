// Test-only executable: run the real Host with exactly its first Capture-ring
// allocation refused. No fault switch or alternate recording path is compiled
// into the distributed Host. The component suite separately refuses *all*
// allocations while arm_capture reports its noexcept failure.
#include <atomic>
#include <cstdlib>
#include <new>
#include <lmdj/audio/realtime_engine.hpp>

namespace {
std::atomic<bool> fail_capture_allocation{true};
using CaptureRing = lmdj::audio::detail::FixedSpscQueue<
    lmdj::audio::CapturedTriggerEvent, lmdj::audio::kRealtimeCaptureCapacity>;
}

void* operator new(std::size_t size, std::align_val_t alignment) {
  if (size == sizeof(CaptureRing) &&
      static_cast<std::size_t>(alignment) == alignof(CaptureRing) &&
      fail_capture_allocation.exchange(false)) {
    throw std::bad_alloc{};
  }
  void* memory = nullptr;
  if (posix_memalign(&memory, static_cast<std::size_t>(alignment),
                    size == 0 ? 1 : size) != 0) {
    throw std::bad_alloc{};
  }
  return memory;
}

void operator delete(void* memory, std::align_val_t) noexcept {
  std::free(memory);
}
void operator delete(void* memory, std::size_t, std::align_val_t) noexcept {
  std::free(memory);
}

#include "../../apps/native-host/src/main.cpp"
