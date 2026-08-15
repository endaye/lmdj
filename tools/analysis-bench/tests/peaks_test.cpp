#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis_bench/peaks/factory.hpp>
#include <lmdj/provider/provider.hpp>

#include "support.hpp"

int main() {
  // 4 samples, bucket size 2 -> 2 buckets.
  const auto wav =
      analysis_bench_test::make_wav_bytes({16384, -8192, -32768, 0});
  auto registration = lmdj::analysis_bench::peaks_registration(
      analysis_bench_test::make_resolver({{"wav-sha", wav}}));
  assert(registration.implementation->id() ==
         "local.analysis-bench.peaks");
  assert(registration.capabilities.size() == 1);
  assert(
      registration.capabilities.front().id == "analysis.waveform-peaks.v1");

  lmdj::provider::CapabilityRequest request;
  request.capability = "analysis.waveform-peaks.v1";
  request.inputs = {lmdj::provider::ArtifactBinding{
      "sample",
      lmdj::foundation::ArtifactRef{"wav-sha", "audio/wav", wav.size()},
  }};
  request.parameters = {{"samples_per_bucket", 2}};

  analysis_bench_test::CaptureSink capture;
  const auto result = registration.implementation->run(
      lmdj::foundation::AttemptId{"test-attempt"}, request, capture.sink());
  assert(!result.error.has_value());
  assert(result.candidate.has_value());
  const auto& written = capture.written.at("peaks");
  const auto output = nlohmann::json::parse(
      reinterpret_cast<const char*>(written.data()),
      reinterpret_cast<const char*>(written.data()) + written.size());
  assert(output.at("contract") == "lmdj.analysis-bench.peaks.v1");
  assert(output.at("sample_rate") == 48000);
  assert(output.at("frame_count") == 4);
  assert(output.at("samples_per_bucket") == 2);
  assert(output.at("bucket_count") == 2);
  // bucket 0: max(16384, -8192): 16384/32768=0.5 -> lrint(0.5*32767)
  //         = lrint(16383.5) = 16384 (round-half-to-even);
  //         min = -8192 -> lrint(-8191.75) = -8192
  // bucket 1: min(-32768, 0) = -32768 -> -32767, max = 0
  assert(output.at("max") == std::vector<int>({16384, 0}));
  assert(output.at("min") == std::vector<int>({-8192, -32767}));

  // Bad input: unresolvable artifact -> provider_failed.
  lmdj::provider::CapabilityRequest bad = request;
  bad.inputs = {lmdj::provider::ArtifactBinding{
      "sample",
      lmdj::foundation::ArtifactRef{"missing", "audio/wav", 4},
  }};
  const auto failed = registration.implementation->run(
      lmdj::foundation::AttemptId{"test-attempt-2"}, bad, capture.sink());
  assert(failed.error.has_value());
  assert(
      failed.error->code == lmdj::foundation::ErrorCode::provider_failed);

  std::cout << "peaks_test passed\n";
  return 0;
}
