#pragma once
#include <cstddef>
#include <cstdint>
inline constexpr std::uint32_t MALLOC_CAP_INTERNAL = 1U << 11;
inline constexpr std::uint32_t MALLOC_CAP_8BIT = 1U << 2;
inline constexpr std::uint32_t MALLOC_CAP_DMA = 1U << 3;
inline constexpr std::uint32_t MALLOC_CAP_SPIRAM = 1U << 10;
struct multi_heap_info_t {
  std::size_t total_free_bytes{}, largest_free_block{}, minimum_free_bytes{};
};
void heap_caps_get_info(multi_heap_info_t*, std::uint32_t);
