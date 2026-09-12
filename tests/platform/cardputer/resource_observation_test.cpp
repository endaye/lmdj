#include "apps/cardputer-host/main/resource_observation.hpp"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <string_view>

// Models only API arguments, returned values and elapsed time, not allocator
// locking, stack scanning, scheduler interference or idle-task reclamation.
namespace {
std::array<std::uint32_t, 3> calls{};
std::array<multi_heap_info_t, 3> heaps{{{101, 37, 79}, {61, 29, 43}, {503, 211, 401}}};
std::size_t count{}, stack_bytes{19};
void require(bool ok, const char* why) {
  if (ok) return;
  std::fprintf(stderr, "why: %s; remedy: preserve resource API units, capability masks and sample boundaries\n", why);
  std::abort();
}
}
void heap_caps_get_info(multi_heap_info_t* info, std::uint32_t caps) {
  require(count < calls.size(), "extra heap query");
  calls[count] = caps;
  *info = heaps[count++];
  fake_timer::now_us += 7;
}
std::size_t uxTaskGetStackHighWaterMark(void* task) {
  require(task == nullptr, "sampler queried a foreign task");
  fake_timer::now_us += 11;
  return stack_bytes;
}
int main(int argc, char** argv) {
  require(argc == 2, "scenario missing");
  const std::string_view scenario(argv[1]);
  fake_timer::now_us = 100;
  const auto value = lmdj::cardputer::capture_control_resources();
  if (scenario == "capabilities") {
    require(count == 3, "missing heap capability query");
    require(calls == std::array<std::uint32_t, 3>{
      MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT, MALLOC_CAP_DMA | MALLOC_CAP_8BIT,
      MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT}, "heap capabilities mixed");
  } else if (scenario == "mapping") {
    require(value.internal_8bit.free_bytes == 101 &&
      value.internal_8bit.largest_free_block_bytes == 37 &&
      value.internal_8bit.minimum_free_bytes == 79, "internal heap fields mixed");
    require(value.dma_8bit.free_bytes == 61 && value.dma_8bit.largest_free_block_bytes == 29 &&
      value.dma_8bit.minimum_free_bytes == 43, "DMA heap fields mixed");
    require(value.external_8bit.free_bytes == 503 && value.external_8bit.largest_free_block_bytes == 211 &&
      value.external_8bit.minimum_free_bytes == 401, "external heap fields mixed");
  } else if (scenario == "absent") {
    count = 0;
    heaps[2] = {};
    const auto absent = lmdj::cardputer::capture_control_resources();
    require(absent.external_8bit.free_bytes == 0 && absent.external_8bit.largest_free_block_bytes == 0 &&
      absent.external_8bit.minimum_free_bytes == 0, "absent external heap invented");
  } else if (scenario == "stack") {
    require(value.caller_stack_high_water_bytes == 19, "stack bytes scaled as words");
    stack_bytes = 0;
    require(lmdj::cardputer::current_task_stack_high_water_bytes() == 0, "zero stack low watermark hidden");
  } else if (scenario == "interval") {
    require(value.begin_us == 100 && value.end_us == 132, "collection interval excludes query overhead");
  } else if (scenario == "resample") {
    count = 0;
    heaps[0] = {89, 13, 67};
    const auto next = lmdj::cardputer::capture_control_resources();
    require(next.internal_8bit.free_bytes == 89 && next.internal_8bit.largest_free_block_bytes == 13 &&
      next.internal_8bit.minimum_free_bytes == 67, "old sample reused");
    require(value.internal_8bit.free_bytes == 101, "earlier value snapshot mutated");
  } else require(false, "unknown scenario");
}
