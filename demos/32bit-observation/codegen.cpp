#include "triple_buffer.hpp"

static_assert(sizeof(void*) == 4, "This experiment must target a 32-bit ABI");
static_assert(!std::atomic<std::uint64_t>::is_always_lock_free,
              "Expected target without lock-free atomic64");

extern "C" void demo_publish(observation_demo::TripleBuffer* buffer,
                              const observation_demo::Snapshot* snapshot) {
    buffer->publish(*snapshot);
}

extern "C" std::uint32_t demo_exchange(std::atomic<std::uint32_t>* word,
                                      std::uint32_t value) {
    return word->exchange(value, std::memory_order_acq_rel);
}

extern "C" std::uint32_t demo_claim(std::atomic<std::uint32_t>* word) {
    return word->fetch_or(8, std::memory_order_seq_cst);
}

extern "C" void demo_close(std::atomic<std::uint32_t>* word) {
    word->store(1, std::memory_order_seq_cst);
}

extern "C" std::uint32_t demo_check(std::atomic<std::uint32_t>* word) {
    return word->load(std::memory_order_seq_cst);
}
