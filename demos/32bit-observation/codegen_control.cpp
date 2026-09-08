#include <atomic>
#include <cstdint>

// Deliberate positive control: the diagnostic must see the 64-bit helper.
// Compiled separately; this is not a fallback used by the candidate publisher.
extern "C" std::uint64_t demo_atomic64_control(std::atomic<std::uint64_t>* word) {
    return word->load(std::memory_order_acquire);
}
