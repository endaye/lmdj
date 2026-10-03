#include <lmdj/providers/local_proof_stem/validation.hpp>
#include <lmdj/providers/local_sample_slice/validation.hpp>

#include <algorithm>
#include <cmath>

namespace lmdj::providers::stem {
namespace {
using foundation::ErrorCode;
using foundation::Result;

foundation::Error failure(std::string reason) {
  return {ErrorCode::provider_failed, "Stem PCM16 conversion failed", {{"reason", std::move(reason)}}};
}
foundation::Error invalid_output() {
  return {ErrorCode::invalid_argument, "Stem output does not match role, PCM16 profile and source shape"};
}
void le(std::vector<std::byte>& bytes, std::uint32_t value, unsigned width) {
  for (unsigned i = 0; i < width; ++i) bytes.push_back(static_cast<std::byte>((value >> (8 * i)) & 255));
}
void tag(std::vector<std::byte>& bytes, std::string_view value) {
  for (const char c : value) bytes.push_back(static_cast<std::byte>(c));
}
bool tag_at(std::span<const std::byte> bytes, std::size_t offset, std::string_view value) {
  return bytes.size() >= offset + value.size() &&
      std::equal(value.begin(), value.end(), bytes.begin() + static_cast<std::ptrdiff_t>(offset),
          [](char c, std::byte b) { return static_cast<unsigned char>(c) == std::to_integer<unsigned char>(b); });
}
}  // namespace

Result<std::int16_t> quantize_pcm16(double sample) {
  if (!std::isfinite(sample)) return Result<std::int16_t>::failure(failure("stem_output_nonfinite"));
  const double scaled = sample * 32768.0;
  if (!std::isfinite(scaled) || scaled < -32768.5 || scaled >= 32767.5)
    return Result<std::int16_t>::failure(failure("stem_output_out_of_range"));
  // floor and an explicit parity test are independent of the caller's fenv.
  const double lower = std::floor(scaled);
  const double fraction = scaled - lower;
  const double rounded = lower + (fraction > 0.5 ||
      (fraction == 0.5 && std::fmod(lower, 2.0) != 0.0) ? 1.0 : 0.0);
  if (rounded < -32768 || rounded > 32767)
    return Result<std::int16_t>::failure(failure("stem_output_out_of_range"));
  return Result<std::int16_t>::success(static_cast<std::int16_t>(rounded));
}

Result<std::vector<std::byte>> encode_pcm16_wav(Pcm16Shape shape, std::span<const double> samples) {
  if ((shape.frame_rate != 44100 && shape.frame_rate != 48000) ||
      (shape.channels != 1 && shape.channels != 2) || shape.frame_count == 0 ||
      shape.frame_count > (maximum_wav_bytes - 44) / 2 / shape.channels ||
      shape.frame_count * shape.channels != samples.size())
    return Result<std::vector<std::byte>>::failure(failure("stem_output_shape_invalid"));
  const auto data_bytes = static_cast<std::uint32_t>(samples.size() * 2);
  std::vector<std::byte> output;
  output.reserve(44 + data_bytes);
  tag(output, "RIFF"); le(output, 36 + data_bytes, 4); tag(output, "WAVEfmt ");
  le(output, 16, 4); le(output, 1, 2); le(output, shape.channels, 2);
  le(output, shape.frame_rate, 4); le(output, shape.frame_rate * shape.channels * 2, 4);
  le(output, shape.channels * 2, 2); le(output, 16, 2); tag(output, "data"); le(output, data_bytes, 4);
  for (double sample : samples) {
    const auto encoded = quantize_pcm16(sample);
    if (!encoded.has_value()) return Result<std::vector<std::byte>>::failure(encoded.error());
    le(output, static_cast<std::uint16_t>(encoded.value()), 2);
  }
  return Result<std::vector<std::byte>>::success(std::move(output));
}

Result<void> validate_parameters(const nlohmann::json& parameters) {
  if (!parameters.is_object() || !parameters.empty())
    return Result<void>::failure({ErrorCode::invalid_argument, "Stem parameters must be an empty object",
                                 {{"reason", "stem_parameters_invalid"}}});
  return Result<void>::success();
}

provider::OutputValidation output_validation(std::string role) {
  return {"stem.split.v1", role,
      [role](const provider::CapabilityRequest& request, std::span<const provider::ValidatedInput> inputs,
          const provider::ArtifactBinding& output, std::span<const std::byte> bytes,
          std::span<std::byte>) -> Result<void> {
        if (std::find(roles.begin(), roles.end(), role) == roles.end() || output.port != role ||
            request.capability != "stem.split.v1" || !validate_parameters(request.parameters).has_value() ||
            inputs.size() != 1 || inputs[0].binding.port != "source_audio" || !inputs[0].handle ||
            inputs[0].handle->reference() != inputs[0].binding.artifact ||
            inputs[0].binding.artifact.media_type != "audio/wav" ||
            output.artifact.media_type != "audio/wav" || output.artifact.byte_length != bytes.size())
          return Result<void>::failure(invalid_output());
        const auto source = sample_slice::inspect_pcm16_wav(inputs[0].handle->bytes());
        const auto decoded = sample_slice::inspect_pcm16_wav(bytes);
        if (!source.has_value() || !decoded.has_value()) return Result<void>::failure(invalid_output());
        const auto& input = source.value(); const auto& audio = decoded.value();
        // Outputs are canonical: no timestamp/offset or unrelated metadata chunks.
        if (bytes.size() != 44 + audio.samples.size() || !tag_at(bytes, 12, "fmt ") ||
            !tag_at(bytes, 36, "data") ||
            input.frame_rate != audio.frame_rate || input.channels != audio.channels ||
            input.frame_count != audio.frame_count)
          return Result<void>::failure(invalid_output());
        return Result<void>::success();
      }, 0};
}
}  // namespace lmdj::providers::stem
