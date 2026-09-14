#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>

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
