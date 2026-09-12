#include "apps/cardputer-host/main/resource_observation.hpp"
#include "apps/cardputer-host/main/runtime_host.hpp"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <string_view>
#include <type_traits>

#ifdef ESP_PLATFORM
static_assert(std::is_same_v<decltype(&lmdj::cardputer::RuntimeHost::read_resources),
                             void (lmdj::cardputer::RuntimeHost::*)(
                                 lmdj::cardputer::ResourceObservation&) const noexcept>);
static_assert(std::is_same_v<decltype(&lmdj::cardputer::RuntimeHost::read_resource_cycles),
                             void (lmdj::cardputer::RuntimeHost::*)(
                                 lmdj::cardputer::ResourceCycleReport&) const noexcept>);
static_assert(std::is_same_v<decltype(&lmdj::cardputer::AudioSession::stopped_stack_high_water_bytes),
                             std::optional<std::size_t> (lmdj::cardputer::AudioSession::*)() const noexcept>);
#endif

// Models only API arguments, returned values and elapsed time, not allocator
// locking, stack scanning, scheduler interference or idle-task reclamation.
namespace {
using namespace lmdj::cardputer;
std::array<std::uint32_t, 3> calls{};
std::array<multi_heap_info_t, 3> heaps{{{101, 37, 79}, {61, 29, 43}, {503, 211, 401}}};
std::size_t count{}, stack_bytes{19};
ResourceObservation sample(std::int64_t time, std::size_t internal_free,
                           std::size_t internal_largest, std::size_t dma_free,
                           std::size_t dma_largest, std::size_t external_free,
                           std::size_t external_largest, std::size_t stack,
                           std::optional<std::size_t> audio_stack = std::nullopt) {
  ResourceObservation result;
  result.begin_us = time;
  result.end_us = time + 1;
  result.internal_8bit = {internal_free, internal_largest, internal_free};
  result.dma_8bit = {dma_free, dma_largest, dma_free};
  result.external_8bit = {external_free, external_largest, external_free};
  result.caller_stack_high_water_bytes = stack;
  result.audio_task_stack_high_water_bytes = audio_stack;
  return result;
}

std::array<char, 64> digest(char first) {
  std::array<char, 64> result{};
  result.fill(first);
  return result;
}

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
  } else if (scenario == "ledger") {
    ResourceCycleLedger ledger;
    const auto before = sample(1000, 1000, 600, 800, 400, 500, 250, 320,
                               std::nullopt);
    auto during = sample(2000, 700, 300, 650, 200, 400, 125, 256, 64);
    during.internal_8bit.minimum_free_bytes = 580;
    during.dma_8bit.minimum_free_bytes = 540;
    during.external_8bit.minimum_free_bytes = 345;
    const auto after = sample(3000, 900, 450, 760, 350, 450, 200, 280, 96);
    require(ledger.begin(before), "first resource cycle rejected");
    require(!ledger.complete(after), "unbound cycle was published");
    const auto identity = digest('a');
    require(ledger.bind_identity(identity, 1234), "cycle identity not bound");
    require(!ledger.bind_identity(identity, 1234), "identity was rebound");
    require(ledger.observe(during), "active cycle sample rejected");
    require(ledger.complete(after), "complete cycle rejected");
    ResourceCycleReport report;
    ledger.snapshot(report);
    require(report.completed_cycles == 1 && report.aborted_cycles == 0 &&
                report.dropped_cycles == 0 && !report.active,
            "cycle counters wrong");
    const auto& record = report.records[0];
    require(record.content_sha256 == identity && record.content_bytes == 1234 &&
                record.started_us == 1000 && record.completed_us == 3001,
            "cycle identity or timestamps wrong");
    require(record.baseline_internal_free_bytes == 1000 &&
                record.minimum_internal_free_bytes == 700 &&
                record.minimum_internal_largest_free_block_bytes == 300 &&
                record.minimum_internal_low_water_bytes == 580 &&
                record.minimum_dma_free_bytes == 650 &&
                record.minimum_dma_largest_free_block_bytes == 200 &&
                record.minimum_dma_low_water_bytes == 540 &&
                record.minimum_external_free_bytes == 400 &&
                record.minimum_external_largest_free_block_bytes == 125 &&
                record.minimum_external_low_water_bytes == 345,
            "cycle heap minima mixed");
    require(record.minimum_caller_stack_high_water_bytes == 256 &&
                record.audio_stack_observed &&
                record.minimum_audio_task_stack_high_water_bytes == 64,
            "cycle stack minima mixed");
  } else if (scenario == "ledger_abort") {
    ResourceCycleLedger ledger;
    require(ledger.begin(sample(10, 100, 50, 90, 45, 80, 40, 30)),
            "abort cycle not started");
    require(!ledger.complete(sample(20, 100, 50, 90, 45, 80, 40, 30)),
            "unbound abort cycle completed");
    ledger.abort();
    ResourceCycleReport report;
    ledger.snapshot(report);
    require(report.completed_cycles == 0 && report.aborted_cycles == 1 &&
                !report.active,
            "aborted cycle was published");
    require(!ledger.complete(sample(20, 100, 50, 90, 45, 80, 40, 30)),
            "inactive cycle completed");
  } else if (scenario == "ledger_capacity") {
    ResourceCycleLedger ledger;
    for (std::size_t index = 0; index < resource_cycle_capacity; ++index) {
      require(ledger.begin(sample(static_cast<std::int64_t>(index), 100, 50,
                                  90, 45, 80, 40, 30)),
              "capacity cycle rejected early");
      auto identity = digest(static_cast<char>('a' + index % 26));
      require(ledger.bind_identity(identity, index + 1),
              "capacity identity not bound");
      require(ledger.complete(sample(static_cast<std::int64_t>(index + 1),
                                      99, 49, 89, 44, 79, 39, 29)),
              "capacity cycle not completed");
    }
    require(!ledger.begin(sample(1000, 100, 50, 90, 45, 80, 40, 30)),
            "full ledger accepted a hidden cycle");
    ResourceCycleReport report;
    ledger.snapshot(report);
    require(report.completed_cycles == resource_cycle_capacity &&
                report.dropped_cycles == 1 && report.aborted_cycles == 0 &&
                !report.active,
            "capacity accounting wrong");
  } else require(false, "unknown scenario");
}
