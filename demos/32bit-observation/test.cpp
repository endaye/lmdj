#include "triple_buffer.hpp"

#include <barrier>
#include <chrono>
#include <cstdlib>
#include <future>
#include <iostream>
#include <thread>
#include <vector>

using namespace observation_demo;
using namespace std::chrono_literals;

void require(bool condition, const char* defect) {
    if (!condition) {
        std::cerr << "FAIL: " << defect << '\n';
        std::abort(); // Fail immediately, including when a regression deadlocks a worker.
    }
}

Snapshot value(std::uint64_t epoch, std::uint64_t count) {
    return {epoch, count, ~count};
}

namespace observation_demo {
struct TestAccess {
    static Snapshot paused_read(TripleBuffer& buffer, std::promise<void>& held,
                                std::future<void>& resume) {
        const std::lock_guard<std::mutex> lock(buffer.readers_);
        buffer.acquire_latest();
        const auto before = buffer.slots_[buffer.reader_];
        held.set_value();
        require(resume.wait_for(10s) == std::future_status::ready,
                "harness did not release paused reader");
        const auto after = buffer.slots_[buffer.reader_];
        require(before == after, "publisher overwrote reader-owned payload");
        return after;
    }
};
} // namespace observation_demo

void initial_and_carry() {
    TripleBuffer buffer;
    require(buffer.read() == value(0, 0), "initial snapshot is invalid");
    buffer.publish(value(1, 0xffffffffULL));
    require(buffer.read() == value(1, 0xffffffffULL), "low-word boundary lost");
    buffer.publish(value(1, 0x100000000ULL));
    require(buffer.read() == value(1, 0x100000000ULL), "64-bit carry was truncated");
}

void recycled_slot_is_not_counter() {
    TripleBuffer buffer;
    std::uint64_t authoritative = 0;
    for (unsigned i = 0; i < 31; ++i) {
        buffer.publish(value(1, ++authoritative));
        require(buffer.read() == value(1, authoritative),
                "recycled writer slot regressed authoritative counter");
    }
}

void paused_reader(bool reset) {
    TripleBuffer buffer;
    const auto old = value(1, 0xffffffffULL);
    buffer.publish(old);
    std::promise<void> held, resume, published;
    auto held_future = held.get_future();
    auto resume_future = resume.get_future();
    auto published_future = published.get_future();
    Snapshot observed;
    std::thread reader([&] { observed = TestAccess::paused_read(buffer, held, resume_future); });
    require(held_future.wait_for(10s) == std::future_status::ready,
            "reader never acquired its snapshot");
    // The first publisher (this thread) is quiescent. std::thread startup
    // transfers its writer-private state to the new owner with happens-before.
    const auto final = reset ? value(2, 0) : value(1, 0x100010000ULL);
    std::thread writer([&] {
        for (std::uint64_t n = 1; n <= 65536; ++n) {
            buffer.publish(value(1, 0xffffffffULL + n));
        }
        buffer.publish(final); // No callback or publish after this one.
        published.set_value();
    });
    require(published_future.wait_for(10s) == std::future_status::ready,
            "publisher waited for a paused telemetry reader");
    writer.join();
    resume.set_value();
    reader.join();
    require(observed == old, "paused read did not retain its complete old snapshot");
    require(buffer.read() == final, "final/reset publication lost without another callback");
    // A synchronized different publisher may take over; do not reset slot roles.
    buffer.publish(value(3, 7));
    require(buffer.read() == value(3, 7), "quiescent publisher handoff lost state");
}

void multiple_readers_stress() {
    TripleBuffer buffer;
    constexpr std::uint64_t first = 0xffff0000ULL;
    constexpr std::uint64_t writes = 200000;
    buffer.publish(value(9, first));
    std::barrier start(5);
    std::vector<std::thread> readers;
    for (unsigned r = 0; r < 4; ++r) {
        readers.emplace_back([&] {
            start.arrive_and_wait();
            auto previous = first;
            for (unsigned i = 0; i < 100000; ++i) {
                const auto current = buffer.read();
                require(current.inverse == ~current.count, "reader obtained a torn payload");
                require(current.epoch == 9, "reader obtained a stale or mixed epoch");
                require(current.count >= previous && current.count <= first + writes,
                        "reader observed counter regression or an unpublished value");
                previous = current.count;
            }
        });
    }
    start.arrive_and_wait();
    for (std::uint64_t n = 1; n <= writes; ++n) buffer.publish(value(9, first + n));
    for (auto& reader : readers) reader.join();
    require(buffer.read() == value(9, first + writes), "quiescent final value is stale");
}

int main() {
    initial_and_carry();
    recycled_slot_is_not_counter();
    paused_reader(false);
    paused_reader(true);
    multiple_readers_stress();
    std::cout << "PASS: initial/carry, recycled slots, paused reader, reset/handoff, 4-reader stress\n";
}
