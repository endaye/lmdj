#include <lmdj/analysis_bench/onsets/factory.hpp>

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <numbers>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis/fft.hpp>
#include <lmdj/analysis/wav_pcm16.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/capability.hpp>
#include <lmdj/provider/provider.hpp>

namespace lmdj::analysis_bench {
namespace {

constexpr double kMinOnsetSpacingSeconds = 0.05;

foundation::Error failed(std::string message) {
  return foundation::Error{
      foundation::ErrorCode::provider_failed,
      std::move(message),
      nlohmann::json::object(),
  };
}

bool is_power_of_two(std::uint32_t value) {
  return value != 0 && (value & (value - 1)) == 0;
}

// Spectral flux onset times (seconds). Mirrors the compare.py algorithm:
// frames at i*hop (no centering), Hann window, half-spectrum magnitude,
// flux = sum(max(0, mag-prev)), threshold = mean + 1.5*stddev, strict local
// maximum, minimum spacing 0.05 s.
std::vector<double> detect_onsets(
    const std::vector<float>& mono,
    std::uint32_t sample_rate,
    std::uint32_t fft_size,
    std::uint32_t hop_size) {
  std::vector<float> window(fft_size);
  for (std::uint32_t i = 0; i < fft_size; ++i) {
    window[i] = 0.5F - 0.5F * std::cos(
                              2.0F * std::numbers::pi_v<float> *
                              static_cast<float>(i) /
                              static_cast<float>(fft_size - 1));
  }
  const std::size_t bin_count = fft_size / 2 + 1;
  std::vector<float> previous(bin_count, 0.0F);
  std::vector<double> flux;
  std::vector<double> times;
  for (std::size_t start = 0; start + fft_size <= mono.size();
       start += hop_size) {
    std::vector<std::complex<float>> frame(fft_size);
    for (std::uint32_t i = 0; i < fft_size; ++i) {
      frame[i] = {mono[start + i] * window[i], 0.0F};
    }
    analysis::fft(frame);
    double frame_flux = 0.0;
    for (std::size_t bin = 0; bin < bin_count; ++bin) {
      const float magnitude = std::abs(frame[bin]);
      frame_flux += std::max(0.0F, magnitude - previous[bin]);
      previous[bin] = magnitude;
    }
    flux.push_back(frame_flux);
    times.push_back(static_cast<double>(start) /
                    static_cast<double>(sample_rate));
  }
  if (flux.size() < 3) {
    return {};
  }
  double mean = 0.0;
  for (const double value : flux) {
    mean += value;
  }
  mean /= static_cast<double>(flux.size());
  double variance = 0.0;
  for (const double value : flux) {
    variance += (value - mean) * (value - mean);
  }
  variance /= static_cast<double>(flux.size());
  const double threshold = mean + 1.5 * std::sqrt(variance);

  std::vector<double> onsets;
  for (std::size_t i = 1; i + 1 < flux.size(); ++i) {
    if (flux[i] > threshold && flux[i] > flux[i - 1] &&
        flux[i] >= flux[i + 1]) {
      if (!onsets.empty() &&
          times[i] - onsets.back() < kMinOnsetSpacingSeconds) {
        continue;
      }
      onsets.push_back(times[i]);
    }
  }
  return onsets;
}

class OnsetsProvider final : public provider::Provider {
 public:
  explicit OnsetsProvider(analysis::ArtifactByteResolver resolver)
      : resolver_(std::move(resolver)) {}

  std::string id() const override { return "local.analysis-bench.onsets"; }

  std::vector<std::string> capabilities() const override {
    return {"analysis.onsets.v1"};
  }

  provider::AttemptResult run(
      foundation::AttemptId attempt_id,
      const provider::CapabilityRequest& request,
      provider::ArtifactSink output) override {
    std::uint32_t fft_size = 1024;
    std::uint32_t hop_size = 512;
    if (request.parameters.contains("fft_size")) {
      // Accept both signed and unsigned JSON integer representations
      // (nlohmann stores C++ literals as signed, parsed non-negative text as
      // unsigned); bound-check as int64 before the narrowing get.
      const auto& encoded = request.parameters.at("fft_size");
      if (!encoded.is_number_integer() ||
          encoded.get<std::int64_t>() < 0 ||
          encoded.get<std::int64_t>() > 8192) {
        return {std::move(attempt_id),
                std::nullopt,
                failed("fft_size must be an integer in 256..8192")};
      }
      fft_size = encoded.get<std::uint32_t>();
    }
    if (!is_power_of_two(fft_size) || fft_size < 256 || fft_size > 8192) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("fft_size must be a power of two in 256..8192")};
    }
    if (request.parameters.contains("hop_size")) {
      const auto& encoded = request.parameters.at("hop_size");
      if (!encoded.is_number_integer() ||
          encoded.get<std::int64_t>() < 0 ||
          encoded.get<std::int64_t>() > 65536) {
        return {std::move(attempt_id),
                std::nullopt,
                failed("hop_size must be an integer in 128..65536")};
      }
      hop_size = encoded.get<std::uint32_t>();
    }
    if (hop_size < 128) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("hop_size must be at least 128")};
    }
    const auto binding = std::find_if(
        request.inputs.begin(),
        request.inputs.end(),
        [](const provider::ArtifactBinding& input) {
          return input.port == "sample";
        });
    if (binding == request.inputs.end()) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("missing sample input binding")};
    }
    const auto bytes = resolver_(binding->artifact);
    if (!bytes.has_value()) {
      return {std::move(attempt_id), std::nullopt, failed(bytes.error().message)};
    }
    const auto wav = analysis::parse_wav_pcm16(bytes.value());
    if (!wav.has_value()) {
      return {std::move(attempt_id), std::nullopt, failed(wav.error().message)};
    }
    const auto mono = analysis::mix_to_mono(wav.value());
    const auto onsets = detect_onsets(
        mono, wav.value().sample_rate, fft_size, hop_size);

    const nlohmann::json result{
        {"contract", "lmdj.analysis-bench.onsets.v1"},
        {"sample_rate", wav.value().sample_rate},
        {"frame_count", wav.value().frame_count()},
        {"fft_size", fft_size},
        {"hop_size", hop_size},
        {"onsets_seconds", onsets},
    };
    const auto encoded = result.dump();
    const auto artifact = output(
        "onsets",
        std::span<const std::byte>(
            reinterpret_cast<const std::byte*>(encoded.data()),
            encoded.size()),
        "application/json");
    if (!artifact.has_value()) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("onsets artifact sink failed")};
    }
    return provider::AttemptResult{
        attempt_id,
        provider::Candidate{
            foundation::CandidateId{attempt_id.value()},
            {{"onsets", artifact.value()}},
            nlohmann::json::object(),
        },
        std::nullopt,
    };
  }

 private:
  analysis::ArtifactByteResolver resolver_;
};

provider::CapabilityDescriptor onsets_capability() {
  return provider::CapabilityDescriptor{
      "analysis.onsets.v1",
      "2.0.0",
      {{
          "sample",
          {"audio/wav"},
          "lmdj.artifact.audio-pcm.v1",
          "1.0.0",
          true,
          1,
      }},
      {{
          "onsets",
          {"application/json"},
          "lmdj.artifact.analysis-bench-onsets.v1",
          "1.0.0",
          true,
          1,
      }},
      provider::Determinism::deterministic,
      {},
      {"PROVIDER_FAILED"},
      provider::ResourceRequirements{
          provider::ResourceClass::cpu,
          64,
      },
      provider::ExecutionPolicy{5000, 1},
      provider::CapabilityPolicy{
          {"public"},
          {"local"},
          {"analysis-bench.execute"},
      },
      {"test"},
      1048576,
  };
}

}  // namespace

provider::ProviderRegistration onsets_registration(
    analysis::ArtifactByteResolver resolver) {
  return provider::ProviderRegistration{
      std::make_shared<OnsetsProvider>(std::move(resolver)),
      "0.1.0",
      std::string(64, '0'),
      std::nullopt,
      {onsets_capability()},
  };
}

}  // namespace lmdj::analysis_bench
