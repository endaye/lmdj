#include "apps/cardputer-host/main/audio_diagnostics.hpp"
#include <cstdio>
#include <cstdlib>
#include <string_view>
#include <vector>

namespace {
using namespace lmdj::cardputer;
static_assert(sizeof(AudioDiagnostics) <= 13 * 1024,
              "why: diagnostic storage exceeds its declared bound; remedy: account for the new Host cost");
void require(bool ok, const char* why) {
  if (ok) return;
  std::fprintf(stderr, "why: %s; remedy: preserve exact ranks, timing boundaries and unavailable observations\n", why);
  std::abort();
}
void percentile() {
  DurationSeries series;
  require(!series.summary().p999_available, "empty percentile was available");
  std::vector<std::uint32_t> oracle;
  // Independent full-population sort, including duplicates, descending values,
  // replacement of the smallest retained tail, and exact 1000 boundaries.
  for (std::uint32_t i = 0; i != 6001; ++i) {
    const auto value = (6001 - i) * 17 % 773;
    series.record(value);
    oracle.push_back(value);
    if (i == 0 || i == 998 || i == 999 || i == 1000 || i == 5999 || i == 6000) {
      auto sorted = oracle;
      std::sort(sorted.begin(), sorted.end());
      const auto rank = (999 * sorted.size() + 999) / 1000;
      const auto result = series.summary();
      require(result.samples == sorted.size() && result.invalid == 0, "population count differs");
      require(result.maximum_us == sorted.back(), "maximum differs from full population");
      require(result.p999_available && result.p999_us == sorted[rank - 1], "nearest-rank p99.9 differs");
    }
  }
}
void capacity() {
  DurationSeries series;
  for (std::uint32_t i = 0; i != 511999; ++i) series.record(i);
  const auto last = series.summary();
  require(last.p999_available && last.p999_us == 511487, "last exact rank unavailable or wrong");
  series.record(511999);
  const auto expired = series.summary();
  require(!expired.p999_available && expired.samples == 512000 && expired.maximum_us == 511999,
          "retention exhaustion silently approximated rank or dropped counts");
  series.reset();
  series.record(0);
  require(series.summary().p999_available && series.summary().p999_us == 0, "reset retained old population");
}
void invalid() {
  DurationSeries series;
  series.record(12);
  series.record(std::uint64_t{1} << 32);
  auto result = series.summary();
  require(result.samples == 2 && result.maximum_us == (std::uint64_t{1} << 32) &&
          result.invalid == 1 && !result.p999_available, "wide observation was silently truncated");
  series.reset();
  series.record(3);
  series.invalidate();
  require(!series.summary().p999_available, "invalid observation was hidden");
}
AudioBlockTrace run(AudioBlockResult outcome) {
  std::uint64_t now{};
  unsigned renders{}, conversions{}, submissions{};
  const auto trace = service_audio_block([&] { return now; },
      [&] { now += 5000; return outcome != AudioBlockResult::wait_failed; },
      [&] { return outcome == AudioBlockResult::stopped; },
      [&] { return now - 7; },
      [&] { ++renders; now += 100; },
      [&] { ++conversions; now += 30; return outcome != AudioBlockResult::convert_failed; },
      [&] { ++submissions; now += 20; return outcome != AudioBlockResult::write_failed; });
  const bool did_render = outcome != AudioBlockResult::wait_failed && outcome != AudioBlockResult::stopped;
  require(renders == static_cast<unsigned>(did_render), "render occurred past wait failure or stop");
  require(conversions == renders, "conversion not paired with render");
  require(submissions == static_cast<unsigned>(did_render && outcome != AudioBlockResult::convert_failed),
          "submission occurred past conversion failure");
  require(trace.result == outcome, "worker result was changed by measurement");
  return trace;
}
void boundaries() {
  AudioDiagnostics diagnostics;
  diagnostics.record(run(AudioBlockResult::submitted));
  diagnostics.record_overhead(7000, 7012);
  const auto result = diagnostics.snapshot();
  require(result.attempts == 1 && result.submitted == 1, "successful block count differs");
  require(result.dma_wait.maximum_us == 5000 && result.wakeup.maximum_us == 7, "wait/wakeup boundaries mixed");
  require(result.render.maximum_us == 100 && result.convert.maximum_us == 30 && result.submit.maximum_us == 20,
          "service stages mixed");
  require(result.service.maximum_us == 150 && result.service.p999_us == 150, "DMA wait leaked into service");
  require(result.recording_samples == 1 && result.recording_maximum_us == 12, "observation overhead omitted");
}
void failures() {
  AudioDiagnostics diagnostics;
  diagnostics.record(run(AudioBlockResult::wait_failed));
  diagnostics.record(run(AudioBlockResult::stopped));
  diagnostics.record(run(AudioBlockResult::convert_failed));
  diagnostics.record(run(AudioBlockResult::write_failed));
  const auto result = diagnostics.snapshot();
  require(result.attempts == 4 && result.submitted == 0 && result.stopped == 1 &&
          result.wait_failed == 1 && result.convert_failed == 1 && result.write_failed == 1,
          "failed attempts were omitted or counted as submitted");
  require(result.dma_wait.samples == 4 && result.wakeup.samples == 3 && result.render.samples == 2 &&
          result.convert.samples == 2 && result.submit.samples == 1 && result.service.samples == 2,
          "partial-stage populations include missing work or omit failure costs");
  auto trace = run(AudioBlockResult::submitted);
  trace.time[2] = 1;
  diagnostics.record(trace);
  require(diagnostics.snapshot().render.invalid == 1 && !diagnostics.snapshot().render.p999_available,
          "backward clock was accepted");
  diagnostics.record_overhead(2, 1);
  require(diagnostics.snapshot().recording_invalid == 1, "backward overhead clock was hidden");
  diagnostics.reset();
  require(diagnostics.snapshot().attempts == 0 && !diagnostics.snapshot().service.p999_available,
          "new session inherited prior observations");
}
}
int main(int argc, char** argv) {
  // The coverage probe runs every instrumented binary with no arguments;
  // default to one scenario like the sibling suites and refuse extra ones.
  require(argc <= 2, "at most one scenario");
  const std::string_view scenario = argc > 1 ? argv[1] : "percentile";
  if (scenario == "percentile") percentile();
  else if (scenario == "capacity") capacity();
  else if (scenario == "invalid") invalid();
  else if (scenario == "boundaries") boundaries();
  else if (scenario == "failures") failures();
  else require(false, "unknown scenario");
}
