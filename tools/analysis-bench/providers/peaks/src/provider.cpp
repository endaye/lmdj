#include <lmdj/analysis_bench/peaks/factory.hpp>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis/wav_pcm16.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/capability.hpp>
#include <lmdj/provider/provider.hpp>

namespace lmdj::analysis_bench {
namespace {

foundation::Error failed(std::string message) {
  return foundation::Error{
      foundation::ErrorCode::provider_failed,
      std::move(message),
      nlohmann::json::object(),
  };
}

std::int16_t scale_peak(float value) {
  const auto scaled = std::lrint(value * 32767.0F);
  return static_cast<std::int16_t>(
      std::clamp<long>(scaled, -32767, 32767));
}

class PeaksProvider final : public provider::Provider {
 public:
  explicit PeaksProvider(analysis::ArtifactByteResolver resolver)
      : resolver_(std::move(resolver)) {}

  std::string id() const override { return "local.analysis-bench.peaks"; }

  std::vector<std::string> capabilities() const override {
    return {"analysis.waveform-peaks.v1"};
  }

  provider::AttemptResult run(
      foundation::AttemptId attempt_id,
      const provider::CapabilityRequest& request,
      provider::ArtifactSink output) override {
    std::uint32_t samples_per_bucket = 256;
    if (request.parameters.contains("samples_per_bucket")) {
      // nlohmann stores C++ integer literals as signed number_integer and
      // text-parsed non-negative integers as number_unsigned; accept any
      // integer representation and validate the value range instead.
      const auto& encoded = request.parameters.at("samples_per_bucket");
      if (!encoded.is_number_integer() ||
          encoded.get<std::int64_t>() < 2 ||
          encoded.get<std::int64_t>() > 65536) {
        return {std::move(attempt_id),
                std::nullopt,
                failed("samples_per_bucket must be 2..65536")};
      }
      samples_per_bucket = encoded.get<std::uint32_t>();
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

    const std::size_t bucket_count =
        mono.empty()
            ? 0
            : (mono.size() + samples_per_bucket - 1) / samples_per_bucket;
    std::vector<std::int16_t> minima;
    std::vector<std::int16_t> maxima;
    minima.reserve(bucket_count);
    maxima.reserve(bucket_count);
    for (std::size_t bucket = 0; bucket < bucket_count; ++bucket) {
      const std::size_t begin = bucket * samples_per_bucket;
      const std::size_t end =
          std::min(begin + samples_per_bucket, mono.size());
      const auto [low, high] =
          std::minmax_element(mono.begin() + static_cast<std::ptrdiff_t>(begin),
                              mono.begin() + static_cast<std::ptrdiff_t>(end));
      minima.push_back(scale_peak(*low));
      maxima.push_back(scale_peak(*high));
    }

    const nlohmann::json result{
        {"contract", "lmdj.analysis-bench.peaks.v1"},
        {"sample_rate", wav.value().sample_rate},
        {"channels", wav.value().channels},
        {"frame_count", wav.value().frame_count()},
        {"samples_per_bucket", samples_per_bucket},
        {"bucket_count", bucket_count},
        {"min", std::move(minima)},
        {"max", std::move(maxima)},
    };
    const auto encoded = result.dump();
    const auto artifact = output(
        "peaks",
        std::span<const std::byte>(
            reinterpret_cast<const std::byte*>(encoded.data()),
            encoded.size()),
        "application/json");
    if (!artifact.has_value()) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("peaks artifact sink failed")};
    }
    return provider::AttemptResult{
        attempt_id,
        provider::Candidate{
            foundation::CandidateId{attempt_id.value()},
            {{"peaks", artifact.value()}},
            nlohmann::json::object(),
        },
        std::nullopt,
    };
  }

 private:
  analysis::ArtifactByteResolver resolver_;
};

provider::CapabilityDescriptor peaks_capability() {
  return provider::CapabilityDescriptor{
      "analysis.waveform-peaks.v1",
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
          "peaks",
          {"application/json"},
          "lmdj.artifact.analysis-bench-peaks.v1",
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
      4194304,
  };
}

}  // namespace

provider::ProviderRegistration peaks_registration(
    analysis::ArtifactByteResolver resolver) {
  return provider::ProviderRegistration{
      std::make_shared<PeaksProvider>(std::move(resolver)),
      "0.1.0",
      std::string(64, '0'),
      std::nullopt,
      {peaks_capability()},
  };
}

}  // namespace lmdj::analysis_bench
