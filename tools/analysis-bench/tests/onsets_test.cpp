#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis/fft.hpp>
#include <lmdj/analysis_bench/onsets/factory.hpp>
#include <lmdj/provider/provider.hpp>

#include "support.hpp"

namespace {

std::vector<std::byte> make_wav_bytes(
    const std::vector<std::int16_t>& samples,
    std::uint32_t sample_rate = 48000) {
  const std::uint32_t data_size =
      static_cast<std::uint32_t>(samples.size() * 2);
  std::vector<std::byte> bytes(44 + data_size);
  auto* p = reinterpret_cast<char*>(bytes.data());
  std::memcpy(p, "RIFF", 4);
  const std::uint32_t riff_size = 36 + data_size;
  std::memcpy(p + 4, &riff_size, 4);
  std::memcpy(p + 8, "WAVEfmt ", 8);
  const std::uint32_t fmt_size = 16;
  std::memcpy(p + 16, &fmt_size, 4);
  const std::uint16_t format = 1;
  const std::uint16_t channels = 1;
  const std::uint32_t byte_rate = sample_rate * 2;
  const std::uint16_t block_align = 2;
  const std::uint16_t bits = 16;
  std::memcpy(p + 20, &format, 2);
  std::memcpy(p + 22, &channels, 2);
  std::memcpy(p + 24, &sample_rate, 4);
  std::memcpy(p + 28, &byte_rate, 4);
  std::memcpy(p + 32, &block_align, 2);
  std::memcpy(p + 34, &bits, 2);
  std::memcpy(p + 36, "data", 4);
  std::memcpy(p + 40, &data_size, 4);
  std::memcpy(p + 44, samples.data(), data_size);
  return bytes;
}

}  // namespace

int main() {
  // FFT sanity: impulse at index 0 -> flat magnitude 1 everywhere.
  std::vector<std::complex<float>> impulse(8, {0.0F, 0.0F});
  impulse[0] = {1.0F, 0.0F};
  lmdj::analysis::fft(impulse);
  for (const auto& value : impulse) {
    assert(std::fabs(std::abs(value) - 1.0F) < 1e-5F);
  }

  // 1 s of audio (48000 samples) with 4 broadband clicks at 0.1 s intervals
  // starting at 0.1 s (4800, 9600, 14400, 19200 samples). A click is a short
  // burst of alternating full-scale samples (rich in high frequencies).
  std::vector<std::int16_t> samples(48000, 0);
  for (int click = 1; click <= 4; ++click) {
    const std::size_t start = static_cast<std::size_t>(click) * 4800;
    for (std::size_t i = 0; i < 64; ++i) {
      samples[start + i] = (i % 2 == 0) ? 24000 : -24000;
    }
  }
  const auto wav = make_wav_bytes(samples);
  auto registration = lmdj::analysis_bench::onsets_registration(
      analysis_bench_test::make_resolver({{"wav-sha", wav}}));
  lmdj::provider::CapabilityRequest request;
  request.capability = "analysis.onsets.v1";
  request.inputs = {lmdj::provider::ArtifactBinding{
      "sample",
      lmdj::foundation::ArtifactRef{"wav-sha", "audio/wav", wav.size()},
  }};
  request.parameters = nlohmann::json::object();
  analysis_bench_test::CaptureSink capture;
  const auto result = registration.implementation->run(
      lmdj::foundation::AttemptId{"test-attempt"}, request, capture.sink());
  assert(!result.error.has_value());
  const auto& written = capture.written.at("onsets");
  const auto output = nlohmann::json::parse(
      reinterpret_cast<const char*>(written.data()),
      reinterpret_cast<const char*>(written.data()) + written.size());
  assert(output.at("contract") == "lmdj.analysis-bench.onsets.v1");
  const auto onsets =
      output.at("onsets_seconds").get<std::vector<double>>();
  assert(onsets.size() == 4);
  for (std::size_t click = 0; click < 4; ++click) {
    const double expected = 0.1 * static_cast<double>(click + 1);
    assert(std::fabs(onsets[click] - expected) < 0.03);
  }

  std::cout << "onsets_test passed\n";
  return 0;
}
