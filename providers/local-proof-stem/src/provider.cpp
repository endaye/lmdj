#include <lmdj/providers/local_proof_stem/factory.hpp>
#include <lmdj/providers/local_proof_stem/validation.hpp>
#include <lmdj/providers/local_sample_slice/validation.hpp>

#ifndef LMDJ_LOCAL_PROOF_STEM_SOURCE_PACKAGE_SHA256
#error "Stem Proof source-package identity is required"
#endif

namespace lmdj::providers {
namespace {
using foundation::ErrorCode;
using provider::AttemptResult;
AttemptResult fail(const provider::ProviderRunContext& context, foundation::Error error) {
  return {context.attempt_id, std::nullopt, std::move(error)};
}
AttemptResult execution_failed(const provider::ProviderRunContext& context) {
  return fail(context, {ErrorCode::provider_failed, "Stem Proof execution failed",
                        {{"reason", "stem_execution_failed"}}});
}

// This is byte-boundary Proof, not an instrument separator or a model adapter.
class StemProof final : public provider::Provider {
 public:
  std::string id() const override { return "local.proof.stem"; }
  std::vector<std::string> capabilities() const override { return {"stem.split.v1"}; }
  AttemptResult run(provider::ProviderRunContext context) override {
    const auto parameters = stem::validate_parameters(context.request->parameters);
    if (!parameters.has_value()) return fail(context, parameters.error());
    const auto source = context.source("source_audio", 0);
    if (!source.has_value()) return execution_failed(context);
    if (source.value()->bytes().size() > stem::maximum_wav_bytes) return execution_failed(context);
    const auto decoded = sample_slice::inspect_pcm16_wav(source.value()->bytes());
    if (!decoded.has_value()) return fail(context, decoded.error());
    const auto& audio = decoded.value();
    std::vector<double> samples;
    samples.reserve(audio.samples.size() / 2);
    for (std::size_t i = 0; i < audio.samples.size(); i += 2) {
      const auto raw = std::to_integer<std::uint32_t>(audio.samples[i]) |
          (std::to_integer<std::uint32_t>(audio.samples[i + 1]) << 8);
      const auto value = raw >= 32768 ? static_cast<std::int32_t>(raw) - 65536
                                     : static_cast<std::int32_t>(raw);
      samples.push_back(static_cast<double>(value) / 32768.0);
    }
    const auto encoded = stem::encode_pcm16_wav({audio.frame_rate, audio.channels, audio.frame_count}, samples);
    if (!encoded.has_value()) return fail(context, encoded.error());
    std::vector<provider::ArtifactBinding> outputs;
    for (auto role : stem::roles) {
      const auto ref = context.output(std::string(role), encoded.value(), "audio/wav");
      if (!ref.has_value()) return execution_failed(context);
      outputs.push_back({std::string(role), ref.value()});
    }
    return {context.attempt_id,
        provider::Candidate{foundation::CandidateId{context.attempt_id.value()}, std::move(outputs),
                            nlohmann::json::object()}, std::nullopt};
  }
};
}  // namespace

provider::ProviderRegistration local_proof_stem_registration() {
  std::vector<provider::ArtifactPortDescriptor> outputs;
  std::vector<provider::OutputValidation> validators;
  for (auto role : stem::roles) {
    outputs.push_back({std::string(role), {"audio/wav"}, "lmdj.audio.stem-pcm16-wav.v1", "1.0.0", true, 1});
    validators.push_back(stem::output_validation(std::string(role)));
  }
  return {std::make_shared<StemProof>(), "1.0.0", LMDJ_LOCAL_PROOF_STEM_SOURCE_PACKAGE_SHA256,
      std::nullopt,
      {{"stem.split.v1", "1.0.0",
        {{"source_audio", {"audio/wav"}, "lmdj.audio.pcm16-wav.v1", "1.0.0", true, 1}},
        std::move(outputs), provider::Determinism::nondeterministic, {"separating"},
        {"PROVIDER_FAILED", "UNSUPPORTED_AUDIO", "INVALID_ARGUMENT"},
        {provider::ResourceClass::cpu, 256}, {1000, 1},
        {{"public", "private"}, {"local"}, {"stem.split.execute"}}, {"test"}, 4 * stem::maximum_wav_bytes}},
      std::move(validators),
      {{"stem.split.v1", ErrorCode::invalid_argument, "stem_parameters_invalid"},
       {"stem.split.v1", ErrorCode::unsupported_audio, "source_audio_unsupported"},
       {"stem.split.v1", ErrorCode::provider_failed, "stem_execution_failed"},
       {"stem.split.v1", ErrorCode::provider_failed, "stem_output_nonfinite"},
       {"stem.split.v1", ErrorCode::provider_failed, "stem_output_out_of_range"},
       {"stem.split.v1", ErrorCode::provider_failed, "stem_output_shape_invalid"}}};
}
}  // namespace lmdj::providers
