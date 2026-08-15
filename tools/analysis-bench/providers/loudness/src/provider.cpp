#include <lmdj/analysis_bench/loudness/factory.hpp>

#include <algorithm>
#include <cmath>
#include <cstddef>
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

constexpr double kSilenceDbfs = -300.0;

foundation::Error failed(std::string message) {
  return foundation::Error{
      foundation::ErrorCode::provider_failed,
      std::move(message),
      nlohmann::json::object(),
  };
}

double to_dbfs(double amplitude) {
  if (amplitude <= 0.0) {
    return kSilenceDbfs;
  }
  return 20.0 * std::log10(amplitude);
}

class LoudnessProvider final : public provider::Provider {
 public:
  explicit LoudnessProvider(analysis::ArtifactByteResolver resolver)
      : resolver_(std::move(resolver)) {}

  std::string id() const override {
    return "local.analysis-bench.loudness";
  }

  std::vector<std::string> capabilities() const override {
    return {"analysis.loudness.v1"};
  }

  provider::AttemptResult run(
      foundation::AttemptId attempt_id,
      const provider::CapabilityRequest& request,
      provider::ArtifactSink output) override {
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

    double peak = 0.0;
    double square_sum = 0.0;
    for (const float sample : mono) {
      const double value = sample;
      peak = std::max(peak, std::fabs(value));
      square_sum += value * value;
    }
    const double rms =
        mono.empty() ? 0.0
                     : std::sqrt(square_sum /
                                 static_cast<double>(mono.size()));
    const bool clipping = std::any_of(
        wav.value().interleaved.begin(),
        wav.value().interleaved.end(),
        [](std::int16_t sample) {
          return sample == 32767 || sample == -32768;
        });

    const nlohmann::json result{
        {"contract", "lmdj.analysis-bench.loudness.v1"},
        {"sample_rate", wav.value().sample_rate},
        {"channels", wav.value().channels},
        {"frame_count", wav.value().frame_count()},
        {"peak_dbfs", to_dbfs(peak)},
        {"rms_dbfs", to_dbfs(rms)},
        {"clipping", clipping},
    };
    const auto encoded = result.dump();
    const auto artifact = output(
        "loudness",
        std::span<const std::byte>(
            reinterpret_cast<const std::byte*>(encoded.data()),
            encoded.size()),
        "application/json");
    if (!artifact.has_value()) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("loudness artifact sink failed")};
    }
    return provider::AttemptResult{
        attempt_id,
        provider::Candidate{
            foundation::CandidateId{attempt_id.value()},
            {{"loudness", artifact.value()}},
            nlohmann::json::object(),
        },
        std::nullopt,
    };
  }

 private:
  analysis::ArtifactByteResolver resolver_;
};

provider::CapabilityDescriptor loudness_capability() {
  return provider::CapabilityDescriptor{
      "analysis.loudness.v1",
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
          "loudness",
          {"application/json"},
          "lmdj.artifact.analysis-bench-loudness.v1",
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
      65536,
  };
}

}  // namespace

provider::ProviderRegistration loudness_registration(
    analysis::ArtifactByteResolver resolver) {
  return provider::ProviderRegistration{
      std::make_shared<LoudnessProvider>(std::move(resolver)),
      "0.1.0",
      std::string(64, '0'),
      std::nullopt,
      {loudness_capability()},
  };
}

}  // namespace lmdj::analysis_bench
