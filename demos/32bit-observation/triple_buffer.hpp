#pragma once

#include <array>
#include <atomic>
#include <cstdint>
#include <mutex>

namespace observation_demo {

// Values only: snapshots never lend internal references or own product objects.
struct Snapshot {
    std::uint64_t epoch = 0;
    std::uint64_t count = 0;
    std::uint64_t inverse = ~std::uint64_t{0};
    bool operator==(const Snapshot&) const = default;
};

struct TestAccess;

class TripleBuffer {
public:
    // Checks this compilation target, not ESP32 or worst-case progress.
    static_assert(std::atomic<std::uint32_t>::is_always_lock_free);

    // Exactly one publisher. Transfer publishing ownership only after quiescence
    // and external synchronization. Caller owns the authoritative counters;
    // the recycled writer slot is never an accumulation base.
    void publish(Snapshot value) noexcept {
        slots_[writer_] = value;
        writer_ = middle_.exchange(writer_ | dirty, std::memory_order_acq_rel) & index_mask;
    }

    // Non-realtime only. All readers hold the same lock through value copying.
    Snapshot read() {
        const std::lock_guard<std::mutex> lock(readers_);
        acquire_latest();
        return slots_[reader_];
    }

private:
    friend struct TestAccess; // Deterministic pauses exist only in the test harness.
    void acquire_latest() noexcept {
        if ((middle_.load(std::memory_order_acquire) & dirty) != 0) {
            reader_ = middle_.exchange(reader_, std::memory_order_acq_rel) & index_mask;
        }
    }

    static constexpr std::uint32_t dirty = 4;
    static constexpr std::uint32_t index_mask = 3;
    std::array<Snapshot, 3> slots_{};
    std::atomic<std::uint32_t> middle_{2};
    std::uint32_t writer_ = 0; // Publisher-private.
    std::uint32_t reader_ = 1; // Reader-lock-private.
    std::mutex readers_;
};

} // namespace observation_demo
