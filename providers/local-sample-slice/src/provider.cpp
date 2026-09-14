#include <lmdj/providers/local_sample_slice/factory.hpp>
#include <lmdj/providers/local_sample_slice/validation.hpp>

#include <algorithm>
#include <lmdj/foundation/json.hpp>

#ifndef LMDJ_LOCAL_SAMPLE_SLICE_SOURCE_PACKAGE_SHA256
#error "sample Slice Provider source-package identity is required"
#endif

namespace lmdj::providers {
namespace {
using foundation::ErrorCode;
using provider::AttemptResult;

AttemptResult fail(const provider::ProviderRunContext& context, ErrorCode code,
                   std::string reason) {
  return {context.attempt_id, std::nullopt,
          foundation::Error{code, "Slice reference execution failed", {{"reason", std::move(reason)}}}};
}

bool parameter(const nlohmann::json& parameters, const char* key,
               std::uint64_t maximum, std::uint64_t& value) {
  const auto found = parameters.find(key);
  if (found == parameters.end()) return true;
  if (!found->is_number_integer() ||
      (!found->is_number_unsigned() && found->get<std::int64_t>() < 1)) return false;
  const auto decoded = found->get<std::uint64_t>();
  if (decoded < 1 || decoded > maximum) return false;
  value = decoded;
  return true;
}

class SliceProvider final : public provider::Provider {
 public:
  std::string id() const override { return "local.sample.slice"; }
  std::vector<std::string> capabilities() const override { return {"sample.slice.v1"}; }
  AttemptResult run(provider::ProviderRunContext context) override {
    const auto source = context.source("source_audio", 0);
    if (!source.has_value()) return fail(context, ErrorCode::provider_failed, "slice_analysis_failed");
    const auto decoded = sample_slice::inspect_pcm16_wav(source.value()->bytes());
    if (!decoded.has_value()) return fail(context, ErrorCode::unsupported_audio, "source_audio_unsupported");
    const auto& audio = decoded.value();
    const auto& parameters = context.request->parameters;
    std::uint64_t threshold = 4096, refractory = 240;
    if (!parameters.is_object()) {
      return fail(context, ErrorCode::invalid_argument, "slice_parameters_invalid");
    }
    for (auto item = parameters.begin(); item != parameters.end(); ++item) {
      if (item.key() != "threshold_pcm16" && item.key() != "refractory_frames")
        return fail(context, ErrorCode::invalid_argument, "slice_parameters_invalid");
    }
    if (!parameter(parameters, "threshold_pcm16", 32767, threshold) ||
        !parameter(parameters, "refractory_frames", audio.frame_rate, refractory))
      return fail(context, ErrorCode::invalid_argument, "slice_parameters_invalid");

    auto points = nlohmann::json::array();
    bool previous_above = false;
    std::uint64_t last = 0;
    for (std::uint64_t frame = 0; frame < audio.frame_count; ++frame) {
      std::uint32_t amplitude = 0;
      for (std::uint16_t channel = 0; channel < audio.channels; ++channel) {
        const auto index = static_cast<std::size_t>((frame * audio.channels + channel) * 2);
        const auto raw = std::to_integer<std::uint32_t>(audio.samples[index]) |
            (std::to_integer<std::uint32_t>(audio.samples[index + 1]) << 8);
        const auto sample = raw >= 32768 ? static_cast<std::int32_t>(raw) - 65536
                                        : static_cast<std::int32_t>(raw);
        amplitude = std::max(amplitude, static_cast<std::uint32_t>(sample < 0 ? -sample : sample));
      }
      const bool above = amplitude >= threshold;
      if (above && !previous_above && (points.empty() || frame - last >= refractory)) {
        if (points.size() == 4096) return fail(context, ErrorCode::provider_failed, "slice_analysis_failed");
        points.push_back({{"frame", frame}});
        last = frame;
      }
      previous_above = above;
    }
    const auto encoded = foundation::canonical_json({
        {"contract", "lmdj.slice-points.v1"}, {"source_sha256", source.value()->reference().sha256},
        {"frame_rate", audio.frame_rate}, {"points", std::move(points)}});
    const auto output = context.output("slice_points",
        std::as_bytes(std::span{encoded.data(), encoded.size()}), "application/json");
    if (!output.has_value()) return fail(context, ErrorCode::provider_failed, "slice_analysis_failed");
    return {context.attempt_id,
        provider::Candidate{foundation::CandidateId{context.attempt_id.value()},
            {{"slice_points", output.value()}}, nlohmann::json::object()}, std::nullopt};
  }
};
}  // namespace

provider::ProviderRegistration local_sample_slice_registration() {
  return {std::make_shared<SliceProvider>(), "1.0.2", LMDJ_LOCAL_SAMPLE_SLICE_SOURCE_PACKAGE_SHA256,
      std::nullopt,
      {{"sample.slice.v1", "1.0.0",
        {{"source_audio", {"audio/wav"}, "lmdj.audio.pcm16-wav.v1", "1.0.0", true, 1}},
        {{"slice_points", {"application/json"}, "lmdj.slice-points.v1", "1.0.0", true, 1}},
        provider::Determinism::deterministic, {"analyzing"},
        {"PROVIDER_FAILED", "UNSUPPORTED_AUDIO", "INVALID_ARGUMENT"},
        {provider::ResourceClass::cpu, 64}, {1000, 1},
        {{"public", "private"}, {"local"}, {"sample.slice.execute"}}, {"test"}, 262144}},
      {sample_slice::slice_points_validation()},
      {{"sample.slice.v1", ErrorCode::provider_failed, "slice_analysis_failed"},
       {"sample.slice.v1", ErrorCode::unsupported_audio, "source_audio_unsupported"},
       {"sample.slice.v1", ErrorCode::invalid_argument, "slice_parameters_invalid"}}};
}
}  // namespace lmdj::providers
