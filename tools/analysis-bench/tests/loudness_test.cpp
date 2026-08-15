#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis_bench/loudness/factory.hpp>
#include <lmdj/provider/provider.hpp>

#include "support.hpp"

namespace {

nlohmann::json run_loudness(const std::vector<std::int16_t>& samples) {
  const auto wav = analysis_bench_test::make_wav_bytes(samples);
  auto registration = lmdj::analysis_bench::loudness_registration(
      analysis_bench_test::make_resolver({{"wav-sha", wav}}));
  lmdj::provider::CapabilityRequest request;
  request.capability = "analysis.loudness.v1";
  request.inputs = {lmdj::provider::ArtifactBinding{
      "sample",
      lmdj::foundation::ArtifactRef{"wav-sha", "audio/wav", wav.size()},
  }};
  request.parameters = nlohmann::json::object();
  analysis_bench_test::CaptureSink capture;
  const auto result = registration.implementation->run(
      lmdj::foundation::AttemptId{"test-attempt"}, request, capture.sink());
  assert(!result.error.has_value());
  const auto& written = capture.written.at("loudness");
  return nlohmann::json::parse(
      reinterpret_cast<const char*>(written.data()),
      reinterpret_cast<const char*>(written.data()) + written.size());
}

}  // namespace

int main() {
  // Full-scale constant: peak 0 dBFS-ish, rms == peak, clipping true.
  const auto full = run_loudness({32767, 32767, 32767, 32767});
  assert(full.at("contract") == "lmdj.analysis-bench.loudness.v1");
  assert(full.at("clipping") == true);
  const double full_peak = full.at("peak_dbfs").get<double>();
  // 32767/32768 -> -0.000265 dBFS
  assert(std::fabs(full_peak - (-0.000265)) < 0.001);
  assert(
      std::fabs(full.at("rms_dbfs").get<double>() - full_peak) < 0.001);

  // Half amplitude (16384): peak = 20*log10(0.5) = -6.0206 dBFS.
  const auto half = run_loudness({16384, -16384, 16384, -16384});
  assert(half.at("clipping") == false);
  assert(std::fabs(half.at("peak_dbfs").get<double>() - (-6.0206)) < 0.001);

  // Silence: floored at -300 dBFS.
  const auto silence = run_loudness({0, 0, 0, 0});
  assert(silence.at("peak_dbfs") == -300.0);
  assert(silence.at("rms_dbfs") == -300.0);

  std::cout << "loudness_test passed\n";
  return 0;
}
