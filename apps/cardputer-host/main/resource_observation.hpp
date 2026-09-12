#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

namespace lmdj::cardputer {
struct HeapObservation {
  std::size_t free_bytes{};
  std::size_t largest_free_block_bytes{};
  // Sum of SDK per-region low watermarks, not a simultaneous global minimum.
  std::size_t minimum_free_bytes{};
};
struct ResourceObservation {
  std::int64_t begin_us{}, end_us{};
  HeapObservation internal_8bit, dma_8bit, external_8bit;
  std::size_t caller_stack_high_water_bytes{};
  // Available only after an audio worker publishes finished; nullopt means
  // no completed worker observation exists for the current session.
  std::optional<std::size_t> audio_task_stack_high_water_bytes;
};

// One completed load -> play -> stop -> unload journey. The ledger keeps the
// sample fields needed to compute the cycle's observed allocation peak without
// retaining every poll sample. `minimum_*` fields are minima over the samples
// supplied by the serialized control owner; they are not allocator-wide
// guarantees and do not imply that overlapping capability classes can be
// summed.
struct ResourceCycleRecord {
  std::array<char, 64> content_sha256{};
  std::uint64_t content_bytes{};
  std::int64_t started_us{}, completed_us{};
  std::size_t baseline_internal_free_bytes{};
  std::size_t minimum_internal_free_bytes{};
  std::size_t minimum_internal_largest_free_block_bytes{};
  std::size_t minimum_internal_low_water_bytes{};
  std::size_t baseline_dma_free_bytes{};
  std::size_t minimum_dma_free_bytes{};
  std::size_t minimum_dma_largest_free_block_bytes{};
  std::size_t minimum_dma_low_water_bytes{};
  std::size_t baseline_external_free_bytes{};
  std::size_t minimum_external_free_bytes{};
  std::size_t minimum_external_largest_free_block_bytes{};
  std::size_t minimum_external_low_water_bytes{};
  std::size_t minimum_caller_stack_high_water_bytes{};
  std::size_t minimum_audio_task_stack_high_water_bytes{};
  bool audio_stack_observed{};
};

inline constexpr std::size_t resource_cycle_capacity = 100;

struct ResourceCycleReport {
  std::array<ResourceCycleRecord, resource_cycle_capacity> records{};
  std::size_t completed_cycles{};
  std::size_t aborted_cycles{};
  std::size_t dropped_cycles{};
  bool active{};
};

// Fixed-size control-side accumulator. It never allocates, and it does not
// sample the platform itself; RuntimeHost supplies observations at lifecycle
// boundaries and during its serialized polling. An active cycle is discarded
// explicitly on a failed load, while a full ledger reports dropped cycles
// instead of silently relabeling later journeys as measured.
class ResourceCycleLedger final {
 public:
  bool begin(const ResourceObservation& sample) noexcept {
    if (active_) return false;
    if (completed_ == records_.size()) {
      ++dropped_;
      return false;
    }
    active_record_ = {};
    identity_bound_ = false;
    active_record_.started_us = sample.begin_us;
    active_record_.baseline_internal_free_bytes = sample.internal_8bit.free_bytes;
    active_record_.minimum_internal_free_bytes = sample.internal_8bit.free_bytes;
    active_record_.minimum_internal_largest_free_block_bytes =
        sample.internal_8bit.largest_free_block_bytes;
    active_record_.minimum_internal_low_water_bytes =
        sample.internal_8bit.minimum_free_bytes;
    active_record_.baseline_dma_free_bytes = sample.dma_8bit.free_bytes;
    active_record_.minimum_dma_free_bytes = sample.dma_8bit.free_bytes;
    active_record_.minimum_dma_largest_free_block_bytes =
        sample.dma_8bit.largest_free_block_bytes;
    active_record_.minimum_dma_low_water_bytes =
        sample.dma_8bit.minimum_free_bytes;
    active_record_.baseline_external_free_bytes = sample.external_8bit.free_bytes;
    active_record_.minimum_external_free_bytes = sample.external_8bit.free_bytes;
    active_record_.minimum_external_largest_free_block_bytes =
        sample.external_8bit.largest_free_block_bytes;
    active_record_.minimum_external_low_water_bytes =
        sample.external_8bit.minimum_free_bytes;
    active_record_.minimum_caller_stack_high_water_bytes =
        sample.caller_stack_high_water_bytes;
    if (sample.audio_task_stack_high_water_bytes.has_value()) {
      active_record_.audio_stack_observed = true;
      active_record_.minimum_audio_task_stack_high_water_bytes =
          *sample.audio_task_stack_high_water_bytes;
    }
    active_ = true;
    return true;
  }

  bool bind_identity(std::span<const char> sha256,
                     std::uint64_t content_bytes) noexcept {
    if (!active_ || identity_bound_ ||
        sha256.size() != active_record_.content_sha256.size() ||
        std::any_of(sha256.begin(), sha256.end(), [](char value) {
          return value == '\0';
        })) return false;
    std::copy(sha256.begin(), sha256.end(), active_record_.content_sha256.begin());
    active_record_.content_bytes = content_bytes;
    identity_bound_ = true;
    return true;
  }

  bool observe(const ResourceObservation& sample) noexcept {
    if (!active_) return false;
    active_record_.minimum_internal_free_bytes =
        std::min(active_record_.minimum_internal_free_bytes,
                 sample.internal_8bit.free_bytes);
    active_record_.minimum_internal_largest_free_block_bytes =
        std::min(active_record_.minimum_internal_largest_free_block_bytes,
                 sample.internal_8bit.largest_free_block_bytes);
    active_record_.minimum_internal_low_water_bytes =
        std::min(active_record_.minimum_internal_low_water_bytes,
                 sample.internal_8bit.minimum_free_bytes);
    active_record_.minimum_dma_free_bytes =
        std::min(active_record_.minimum_dma_free_bytes, sample.dma_8bit.free_bytes);
    active_record_.minimum_dma_largest_free_block_bytes =
        std::min(active_record_.minimum_dma_largest_free_block_bytes,
                 sample.dma_8bit.largest_free_block_bytes);
    active_record_.minimum_dma_low_water_bytes =
        std::min(active_record_.minimum_dma_low_water_bytes,
                 sample.dma_8bit.minimum_free_bytes);
    active_record_.minimum_external_free_bytes =
        std::min(active_record_.minimum_external_free_bytes,
                 sample.external_8bit.free_bytes);
    active_record_.minimum_external_largest_free_block_bytes =
        std::min(active_record_.minimum_external_largest_free_block_bytes,
                 sample.external_8bit.largest_free_block_bytes);
    active_record_.minimum_external_low_water_bytes =
        std::min(active_record_.minimum_external_low_water_bytes,
                 sample.external_8bit.minimum_free_bytes);
    active_record_.minimum_caller_stack_high_water_bytes =
        std::min(active_record_.minimum_caller_stack_high_water_bytes,
                 sample.caller_stack_high_water_bytes);
    if (sample.audio_task_stack_high_water_bytes.has_value() &&
        (!active_record_.audio_stack_observed ||
         *sample.audio_task_stack_high_water_bytes <
             active_record_.minimum_audio_task_stack_high_water_bytes)) {
      active_record_.audio_stack_observed = true;
      active_record_.minimum_audio_task_stack_high_water_bytes =
          *sample.audio_task_stack_high_water_bytes;
    }
    return true;
  }

  bool mark_playing() noexcept {
    if (!active_ || !identity_bound_ || playing_) return false;
    playing_ = true;
    return true;
  }

  bool complete(const ResourceObservation& sample) noexcept {
    if (!active_ || !identity_bound_ || !playing_) return false;
    observe(sample);
    active_record_.completed_us = sample.end_us;
    records_[completed_++] = active_record_;
    active_record_ = {};
    identity_bound_ = false;
    playing_ = false;
    active_ = false;
    return true;
  }

  void abort() noexcept {
    if (!active_) return;
    active_record_ = {};
    identity_bound_ = false;
    playing_ = false;
    active_ = false;
    ++aborted_;
  }

  void snapshot(ResourceCycleReport& result) const noexcept {
    result = {};
    std::copy_n(records_.begin(), completed_, result.records.begin());
    result.completed_cycles = completed_;
    result.aborted_cycles = aborted_;
    result.dropped_cycles = dropped_;
    result.active = active_;
  }

 private:
  std::array<ResourceCycleRecord, resource_cycle_capacity> records_{};
  ResourceCycleRecord active_record_{};
  std::size_t completed_{}, aborted_{}, dropped_{};
  bool active_{}, identity_bound_{}, playing_{};
};
}  // namespace lmdj::cardputer

#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace lmdj::cardputer {
inline std::size_t current_task_stack_high_water_bytes() noexcept {
  // ESP-IDF returns bytes, unlike upstream FreeRTOS's word-based API.
  return uxTaskGetStackHighWaterMark(nullptr);
}

// Serialized control owner only; never render/ISR. Capabilities overlap and
// measurements occur sequentially: neither sum them nor claim atomicity.
inline ResourceObservation capture_control_resources() noexcept {
  ResourceObservation result;
  result.begin_us = esp_timer_get_time();
  const auto heap = [](std::uint32_t caps) {
    multi_heap_info_t info{};
    heap_caps_get_info(&info, caps);
    return HeapObservation{info.total_free_bytes, info.largest_free_block,
                           info.minimum_free_bytes};
  };
  result.internal_8bit = heap(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  result.dma_8bit = heap(MALLOC_CAP_DMA | MALLOC_CAP_8BIT);
  result.external_8bit = heap(MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  result.caller_stack_high_water_bytes = current_task_stack_high_water_bytes();
  result.end_us = esp_timer_get_time();
  return result;
}
}  // namespace lmdj::cardputer
#endif
