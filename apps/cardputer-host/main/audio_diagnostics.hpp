#pragma once

#include <algorithm>
#include <array>
#include <cstdint>
#include <functional>
#include <limits>

namespace lmdj::cardputer {

struct DurationSummary {
  std::uint64_t samples{}, invalid{}, maximum_us{};
  std::uint32_t p999_us{};
  bool p999_available{};
};

// Audio-owner writes; read only after the owner has joined. Retain the largest
// 512 observations exactly, not a sampled/approximate percentile. At n samples
// nearest-rank p99.9 is the (floor(n/1000)+1)th largest value. It is unavailable
// at n >= 512000, or after a bad/over-wide observation; count/max remain useful.
class DurationSeries final {
 public:
  static constexpr std::size_t retained = 512;
  void reset() noexcept { samples_ = invalid_ = maximum_ = 0; size_ = 0; }
  void record(std::uint64_t value) noexcept {
    if (samples_ == std::numeric_limits<std::uint64_t>::max()) { invalidate(); return; }
    ++samples_;
    maximum_ = std::max(maximum_, value);
    if (value > std::numeric_limits<std::uint32_t>::max()) { invalidate(); return; }
    const auto narrow = static_cast<std::uint32_t>(value);
    if (size_ < retained) {
      tail_[size_++] = narrow;
      std::push_heap(tail_.begin(), tail_.begin() + size_, std::greater<>{});
    } else if (narrow > tail_.front()) {
      std::pop_heap(tail_.begin(), tail_.end(), std::greater<>{});
      tail_.back() = narrow;
      std::push_heap(tail_.begin(), tail_.end(), std::greater<>{});
    }
  }
  void invalidate() noexcept {
    if (invalid_ != std::numeric_limits<std::uint64_t>::max()) ++invalid_;
  }
  DurationSummary summary() const noexcept {
    DurationSummary result{samples_, invalid_, maximum_, 0, false};
    if (samples_ == 0 || invalid_ != 0 || samples_ / 1000 >= retained) return result;
    // Only the stopped control owner pays for this temporary copy/selection.
    auto values = tail_;
    const auto index = size_ - 1 - static_cast<std::size_t>(samples_ / 1000);
    std::nth_element(values.begin(), values.begin() + index, values.begin() + size_);
    result.p999_us = values[index];
    result.p999_available = true;
    return result;
  }
 private:
  std::array<std::uint32_t, retained> tail_{};
  std::uint64_t samples_{}, invalid_{}, maximum_{};
  std::size_t size_{};
};

enum class AudioBlockResult : std::uint8_t { submitted, stopped, wait_failed, convert_failed, write_failed };
struct AudioBlockTrace {
  // Absolute timestamps from one monotonic microsecond clock. A zero timestamp
  // is valid; `stages` says which boundaries actually occurred.
  std::array<std::uint64_t, 5> time{};
  std::uint64_t eof_us{};
  std::uint8_t stages{};
  AudioBlockResult result{AudioBlockResult::wait_failed};
};

// The actual worker uses this same orchestration; tests supply deterministic
// clock/I/O functions. No std::function, allocation, lock or logging here.
template<class Clock, class Wait, class Stop, class Eof, class Render, class Convert, class Submit>
AudioBlockTrace service_audio_block(Clock clock, Wait wait, Stop stop, Eof eof,
                                    Render render, Convert convert, Submit submit) noexcept {
  AudioBlockTrace trace;
  trace.time[0] = clock();
  const bool writable = wait();
  trace.time[1] = clock();
  trace.stages = 1;
  if (!writable) return trace;
  trace.eof_us = eof();
  if (stop()) { trace.result = AudioBlockResult::stopped; return trace; }
  render();
  trace.time[2] = clock();
  trace.stages = 2;
  const bool converted = convert();
  trace.time[3] = clock();
  trace.stages = 3;
  if (!converted) { trace.result = AudioBlockResult::convert_failed; return trace; }
  const bool written = submit();
  trace.time[4] = clock();
  trace.stages = 4;
  trace.result = written ? AudioBlockResult::submitted : AudioBlockResult::write_failed;
  return trace;
}

struct AudioDiagnosticsSnapshot {
  DurationSummary dma_wait, wakeup, render, convert, submit, service;
  std::uint64_t attempts{}, submitted{}, stopped{}, wait_failed{}, convert_failed{}, write_failed{};
  std::uint64_t recording_samples{}, recording_maximum_us{}, recording_invalid{};
  // service is an elapsed upper envelope, including preemption/clock calls,
  // excluding DMA wait and this accumulator's measured recording overhead.
  // Delivered-EOF wakeup is not physical DMA wakeup/interrupt latency.
};

class AudioDiagnostics final {
 public:
  void reset() noexcept {
    for (auto& series : series_) series.reset();
    counts_ = {};
    recording_samples_ = recording_maximum_ = recording_invalid_ = 0;
  }
  void record(const AudioBlockTrace& trace) noexcept {
    increment(counts_[0]);
    increment(counts_[1 + static_cast<std::size_t>(trace.result)]);
    if (trace.stages >= 1) duration(0, trace.time[0], trace.time[1]);
    if (trace.result != AudioBlockResult::wait_failed && trace.stages >= 1)
      duration(1, trace.eof_us, trace.time[1]);
    if (trace.stages >= 2) duration(2, trace.time[1], trace.time[2]);
    if (trace.stages >= 3) duration(3, trace.time[2], trace.time[3]);
    if (trace.stages >= 4) duration(4, trace.time[3], trace.time[4]);
    // Include failed conversion/submission costs, not only successful blocks.
    if (trace.stages >= 2) duration(5, trace.time[1], trace.time[trace.stages]);
  }
  void record_overhead(std::uint64_t begin, std::uint64_t end) noexcept {
    increment(recording_samples_);
    if (end < begin) increment(recording_invalid_);
    else recording_maximum_ = std::max(recording_maximum_, end - begin);
  }
  AudioDiagnosticsSnapshot snapshot() const noexcept {
    return {series_[0].summary(), series_[1].summary(), series_[2].summary(),
            series_[3].summary(), series_[4].summary(), series_[5].summary(),
            counts_[0], counts_[1], counts_[2], counts_[3], counts_[4], counts_[5],
            recording_samples_, recording_maximum_, recording_invalid_};
  }
 private:
  static void increment(std::uint64_t& value) noexcept {
    if (value != std::numeric_limits<std::uint64_t>::max()) ++value;
  }
  void duration(std::size_t index, std::uint64_t begin, std::uint64_t end) noexcept {
    if (end < begin) series_[index].invalidate();
    else series_[index].record(end - begin);
  }
  std::array<DurationSeries, 6> series_{};
  std::array<std::uint64_t, 6> counts_{};
  std::uint64_t recording_samples_{}, recording_maximum_{}, recording_invalid_{};
};

}  // namespace lmdj::cardputer
